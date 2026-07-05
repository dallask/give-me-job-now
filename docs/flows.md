# Flows — the give-me-job runtime sequences

> **Every command and script named here resolves to a real file on disk.**
> `python3 tests/test_docs_current.py` (`test_every_docs_command_exists`,
> `test_every_docs_script_exists`) fails the build if any `/gmj-…` command token or `gmj_*.py`
> script name drifts. The authoritative runtime contract is
> [docs/ARCHITECTURE.md](ARCHITECTURE.md) §5 (data flow) and §5.1 (runtime control loop); this page
> is the reader-facing catalog of the real end-to-end sequences.

This page documents **what actually happens** when each entry command runs — the ordered script and
`Task` sequence, and where the non-bypassable gates sit. Two invariants hold across every gated flow:

- **Gate A (truth) passes before Gate B (fit).** `gmj-truth-verifier` re-grounds every claim against
  `config/candidate.yaml` first; only a Gate-A-passed draft is scored for target-fit by
  `gmj-fit-evaluator`. A fabrication is a hard block, never bypassable in any mode.
- **Mode gates only the post-PASS human pause, never the machine gate.** `execution_mode` (frozen at
  `init_run`) is consulted at exactly one point — the pause after a gate PASS. `human_in_the_loop`
  pauses for approval; `autonomous` proceeds automatically. Neither the gate scripts nor the fail
  path ever see the mode. Loops are bounded by a frozen retry cap; cap exhaustion is a hard stop,
  never ship-last-attempt.

See [commands.md](commands.md) for the command surface, [agents.md](agents.md) for the roster, and
[cli-tools.md](cli-tools.md) for each script's contract. For a hands-on walkthrough of a real run,
read [docs/RUNBOOK.md](RUNBOOK.md); for the manual acceptance matrix, read
[docs/HUMAN-TESTING-PLAN.md](HUMAN-TESTING-PLAN.md) — those documents are linked rather than
duplicated here.

---

## Single-offer pipeline

**Entry:** `/gmj-pipeline-run` — the whole offer→artifacts flow in one command (dual-mode, gated,
retry-capped). This is the flow the RUNBOOK exercises end to end; see
[docs/RUNBOOK.md](RUNBOOK.md) §2.

```
/gmj-pipeline-run  (params: mode?, offer, run_id?)
   │
   ▼
1. init_run     gmj_state_write.py    freeze execution_mode + retry_cap + run_id
                                      into .pipeline/runs/<run_id>/state.json
2. loop:
   a. gmj_route.py        --state runs/<run_id>/state.json  → next_step   (pure (state, dag) → step)
   b. gmj_check_offer.py  --file offer-spec.json            (before each dispatch; STALE ⇒ abort)
   c. Task(spoke for next_step):
        scout    → gmj-offer-scout           (rank offers within sources.yaml scope)
        freeze   → gmj_freeze_offer.py        (immutable offer-spec)
        compose  → gmj-artifact-composer ×3   (cv / cover_letter / interview_prep; gmj_record_retry.py)
   d. GATE node?
        Gate A (truth):  gmj_check_truth.py → gmj_record_gate.py       exit 0/1 — NO bypass
        Gate B (fit):    gmj_score_fit.py   → gmj_record_gate.py       exit 0/1 — NO bypass
        FAIL ⇒ gmj_record_retry.py --increment → gmj_check_cap.py
                 ├ below cap ⇒ gmj_map_feedback.py → Task(gmj-artifact-composer) ↺
                 └ at cap    ⇒ HARD STOP report (names failing artifact + reason)
        PASS ⇒ (human_in_the_loop: pause for approval) → route advances
3. deliver:     gmj_check_delivery.py   (Gate A ∧ Gate B recorded pass?)  else blocked
   │
   ▼
   output/cv/*.pdf   rendered by gmj-cv-generator via gmj_render_cv.py
```

1. **init_run.** `gmj_state_write.py` freezes `execution_mode`, `retry_cap`, and `run_id` into
   `.pipeline/runs/<run_id>/state.json`.
2. **Route + guard.** `gmj_route.py` returns the next step as a pure `(state, dag) → step` replay;
   `gmj_check_offer.py` re-checks the frozen offer-spec for tampering before each dispatch (STALE ⇒
   abort).
3. **Scout + freeze.** `gmj-offer-scout` ranks offers within `config/sources.yaml` scope, then
   `gmj_freeze_offer.py` freezes the chosen one into an immutable offer-spec.
4. **Compose.** `gmj-artifact-composer` composes the three artifact types; `gmj_record_retry.py`
   holds each type's isolated retry counter.
5. **Gate A → Gate B.** `gmj_check_truth.py` (truth) then `gmj_score_fit.py` (fit), each recorded by
   `gmj_record_gate.py`. On failure, `gmj_map_feedback.py` projects a structured feedback packet back
   to the composer, bounded by `gmj_check_cap.py`.
6. **Deliver.** `gmj_check_delivery.py` refuses delivery unless both gates recorded a PASS; a passing
   draft reaches `gmj-cv-generator`, which renders `output/cv/*.pdf` via `gmj_render_cv.py`.

---

## Per-step pipeline

**Entry:** the six [`gmj-pipeline/` leaf commands](commands.md#pipeline-steps-6--gmj-pipeline). Each
is a thin wrapper naming exactly one script or `Task` of the loop above — no control logic is
duplicated.

| Step | Command | Names |
|------|---------|-------|
| 1 | `/gmj-pipeline/scout` | `Task(gmj-offer-scout)` |
| 2 | `/gmj-pipeline/freeze` | `gmj_freeze_offer.py`, `gmj_state_write.py` |
| 3 | `/gmj-pipeline/compose` | `Task(gmj-artifact-composer)`, `gmj_record_retry.py` |
| 4 | `/gmj-pipeline/verify` (Gate A) | `gmj_check_truth.py`, `gmj_record_gate.py` |
| 5 | `/gmj-pipeline/evaluate` (Gate B) | `gmj_score_fit.py`, `gmj_record_gate.py` |
| 6 | `/gmj-pipeline/generate` | `Task(gmj-cv-generator)`, `gmj_render_cv.py` |

Because state lives in `.pipeline/runs/<run_id>/state.json`, resuming a run is a pure
`(state, dag) → next_step` replay: passing an existing `run_id` to any step continues exactly where
the last one left off.

---

## Batch (multi-offer)

**Entry:** `/gmj-batch` — freeze + run several shortlisted offers, each as its own gated pipeline,
under one resumable manifest.

1. `gmj_batch.py` writes a resumable **batch manifest** grouping the selected offers by `run_id`.
2. It runs the **existing single-offer loop once per offer** — same Gate A → Gate B → deliver
   ordering — each with an isolated `retry_counts[offer][type]` slot.
3. `/gmj-runs` (see [runs inspection](#runs-inspection)) surfaces the batch timeline and the resume
   command for any interrupted offer.

No new control logic: the batch layer is a deterministic control plane over the same per-offer flow.

---

## Interview / preferences capture

**Entry:** `/gmj-interview` — a standalone interviewer persona (no `Task`).

1. Reads the real profile (`config/candidate.yaml`) and the analyzer's coverage manifest, and asks
   **only about real gaps**, one question at a time.
2. Captures search-narrowing preferences to `config/preferences.yaml` behind the validator guard
   `gmj_validate_preferences.py` (shape + subset-of-`sources.yaml`).
3. Hands the confirmed profile facts to `gmj-candidate-configurator` for the canonical YAML write —
   the interviewer never writes the master profile itself.

Run this before a pipeline to fill profile gaps and record ranking preferences that later scope
`gmj-offer-scout`.

---

## Template creation

**Entry:** `/gmj-template` — turn a pasted CV design screenshot into a reusable branded template.

1. The command persona spawns `gmj-template-creator` as its sole `Task`.
2. A bounded **WeasyPrint compare==ship loop** matches the render to the design: `gmj_render_cv.py`
   renders a candidate binding, `gmj_visual_diff.py` scores the pixel diff, and `gmj_template_lint.py`
   fails closed on any leftover sample strings.
3. The loop is capped (cap 5, diff-ratio ≤ 0.10, keep-best); the accepted `{{ candidate.* }}`-bound
   HTML/Jinja2 template lands under `templates/cv/` for later renders.

---

## Runs inspection

**Entry:** `/gmj-runs` — a read-only timeline of runs and batches.

`gmj_runs.py` (the read-only mirror of the `gmj_batch.py` writer) prints a terse run/batch timeline
and **surfaces — never executes** — the exact resume command for each entry. Use it to find run
state and the command to continue an interrupted single-offer or batch pipeline.

---

## Simple full-CV render

**Entry:** `/gmj-collective` (or a direct script call) — the classic full-CV pipeline, no offer and
no gates.

```
config/candidate.yaml  →  gmj_render_cv.py [--lang ua|ru]  →  output/cv/*.pdf
```

`gmj_render_cv.py` renders the canonical profile to PDF (ReportLab by default; an optional Jinja2
HTML template via WeasyPrint), deep-merging a `config/candidate.{lang}.yaml` prose overlay when a
language is requested. The hub can drive an optional review/enhance loop on top, but the base render
is a single deterministic script call. Related renderers cover the other artifact types:
`gmj_render_cover_letter.py` (cover letter PDF) and `gmj_render_interview_prep.py` (interview-prep
markdown).

---

## Dashboard

**Entry:** `/gmj-dashboard` — a live, btop-style cockpit over pipeline run/batch state.

`python3 scripts/dashboard/gmj_dashboard.py` opens a Textual board that projects the run/batch
state the pipeline already wrote under the pipeline root (`.pipeline` by default) — it derives
nothing new. Two facts define the flow:

- **Read-only is the default.** Launched bare, the board binds **no** mutating keys: it only
  *displays* the timeline (the same facts `/gmj-runs` prints), so no run/batch/config write can
  happen from it.
- **`--manage` is an explicit opt-in.** Passing `python3 scripts/dashboard/gmj_dashboard.py --manage`
  binds the live action layer (`r`/`R`/`b`/`m`/`c`) that can drive runs/batches and edit config from
  the board. Without it those keys are not even bound.

The board is a pure inspector — it holds no `Task` and never spawns a spoke; every action it can take
under `--manage` shells to the same deterministic scripts the pipeline already uses.

---

## Milestone-complete refresh

**Entry:** convention (milestone finalization) — the documentation-currency invariant.

This repo treats the authored docs as a machine-verified surface. On each milestone finalization the
docs MUST be refreshed and re-verified so no `gmj-` entity token drifts from disk. The invariant is
stated in [rules/docs-currency.md](../rules/docs-currency.md) (a Read-on-demand, frontmatter-scoped
rule) and enforced by the gate:

```
python3 tests/test_docs_current.py
```

which asserts every `gmj-` agent / `/gmj-` command / `gmj_*.py` script named in `docs/*.md` +
`README.md` resolves to a real file, and that no superseded legacy-roster token is presented as
current. Refresh the affected `docs/` sections, then re-run the gate until it is green before closing
the milestone.

## Related sections

- [commands.md](commands.md) — the command surface that triggers each flow.
- [agents.md](agents.md) — the roster the flows chain across.
- [cli-tools.md](cli-tools.md) — the deterministic scripts each flow calls.
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) §5 / §5.1 — authoritative data flow + control loop.
- [docs/RUNBOOK.md](RUNBOOK.md) — hands-on real-offer walkthrough.
- [docs/HUMAN-TESTING-PLAN.md](HUMAN-TESTING-PLAN.md) — manual acceptance matrix.
- [rules/docs-currency.md](../rules/docs-currency.md) — the docs-refresh invariant.
