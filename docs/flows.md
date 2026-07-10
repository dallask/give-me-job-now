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
/gmj-pipeline-run  (params: mode?, offer, run_id?, artifact-types?)
   │
   ▼
0. resolve+derive  gmj_pipeline_run.py --run-id <run_id> --artifact-types <list>
                    validates the 3-item enum (cv / cover_letter / interview_prep), hard-fails
                    BEFORE any dispatch on an unknown/typo'd type, and derives ONE run_id PER
                    type: <run_id>-cv / <run_id>-cl / <run_id>-ip  (defaults to all three)
   │
   ▼
1. init_run     gmj_state_write.py    freeze execution_mode + retry_cap + run_id
                                      into .pipeline/runs/<run_id>-{cv,cl,ip}/state.json — ITS
                                      OWN file per derived type, never one shared file
2. loop (per artifact type; parallel Task fan-out for the default 3 types in one hub turn):
   a. gmj_route.py        --state runs/<run_id>-{cv,cl,ip}/state.json  → next_step   (pure (state, dag) → step)
   b. gmj_check_offer.py  --file offer-spec.json            (before each dispatch; STALE ⇒ abort)
   c. Task(spoke for next_step):
        scout    → gmj-offer-scout           (rank offers within sources.yaml scope; once, shared offer-spec)
        freeze   → gmj_freeze_offer.py        (immutable offer-spec)
        compose  → gmj-artifact-composer      (one Task per type; gmj_record_retry.py)
   d. GATE node?  (recorded independently per type — never a shared/collapsed verdict)
        Gate A (truth):  gmj_check_truth.py → gmj_record_gate.py       exit 0/1 — NO bypass
        Gate B (fit):    gmj_score_fit.py   → gmj_record_gate.py       exit 0/1 — NO bypass
        FAIL ⇒ gmj_record_retry.py --increment → gmj_check_cap.py  (3-way exit contract)
                 ├ exit 0 continue      ⇒ gmj_map_feedback.py → Task(gmj-artifact-composer) ↺ (this type only)
                 ├ exit 2 propose_raise ⇒ first time at frozen cap: HITL asks approval / autonomous
                 │                         applies+logs a fixed +1 raise, then re-enters the SAME
                 │                         recompose→Gate A/B path (still non-bypassable)
                 └ exit 1 exhausted     ⇒ HARD STOP report (names failing artifact + reason + failure_class)
        PASS ⇒ (human_in_the_loop: pause for approval) → route advances
3. deliver:     gmj_check_delivery.py   (per type: Gate A ∧ Gate B recorded pass?)  else blocked
                 — runs once per derived run_id, reported as a per-type breakdown, never a
                   single collapsed boolean
   │
   ▼
   output/cv/*.pdf + *.html sibling (ARTF-02)   rendered by gmj-cv-generator via gmj_render_cv.py
   (plus the cover-letter / interview-prep artifacts for the other requested types)
```

1. **Resolve + derive.** `gmj_pipeline_run.py` validates `--artifact-types` against the 3-item
   enum and derives one run_id per requested type (`<run_id>-cv` / `-cl` / `-ip`), defaulting to
   all three (ARTF-01/03).
2. **init_run.** `gmj_state_write.py` freezes `execution_mode`, `retry_cap`, and `run_id` into
   each type's OWN `.pipeline/runs/<run_id>-{cv,cl,ip}/state.json` — never one shared file,
   because `gate_results` is keyed flatly by DAG node with no artifact-type dimension.
3. **Route + guard.** `gmj_route.py` returns the next step as a pure `(state, dag) → step` replay;
   `gmj_check_offer.py` re-checks the frozen offer-spec for tampering before each dispatch (STALE ⇒
   abort).
4. **Scout + freeze.** `gmj-offer-scout` ranks offers within `config/sources.yaml` scope, then
   `gmj_freeze_offer.py` freezes the chosen one into an immutable offer-spec shared by all
   requested types.
5. **Compose.** `gmj-artifact-composer` composes each requested type as its own `Task`, dispatched
   in parallel in one hub turn; `gmj_record_retry.py` holds each type's isolated retry counter.
6. **Gate A → Gate B, per type.** `gmj_check_truth.py` (truth) then `gmj_score_fit.py` (fit), each
   recorded independently per type by `gmj_record_gate.py` — one type's PASS never satisfies
   another's delivery. On failure, `gmj_map_feedback.py` projects a structured feedback packet back
   to the composer for that type only, bounded by `gmj_check_cap.py`'s 3-way exit contract (`0`
   continue / `2` propose_raise / `1` exhausted-final). On the first cap-exhaustion for a given
   offer/type, `gmj_check_cap.py` differentiates a systemic composer failure from a narrow
   single-claim slip in its report and the hub automatically proposes one bounded cap raise (fixed
   +1 increment) before the final hard-stop — presented as an explicit approval prompt in
   `human_in_the_loop` mode, applied once automatically and logged in `autonomous` mode. The
   recomposed artifact still must pass both gates via the unchanged, non-bypassable gate mechanism;
   a second exhaustion after the raise is an unconditional hard stop (Gate A/B are never weakened by
   this).
7. **Deliver.** `gmj_check_delivery.py` runs once per derived run_id and refuses delivery for any
   type lacking its own recorded Gate A ∧ Gate B PASS, reported as a per-type breakdown. A passing
   CV draft reaches `gmj-cv-generator`, which renders `output/cv/*.pdf` **and** a first-class
   `.html` sibling by default (ARTF-02) via `gmj_render_cv.py`; cover-letter and interview-prep
   drafts render via `gmj_render_cover_letter.py` / `gmj_render_interview_prep.py`.

Narrow the default set with `--artifact-types=cv,cover_letter` (ARTF-03); an unknown/typo'd type
hard-fails before any dispatch.

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

**Entry:** `/gmj-batch` — freeze + run several shortlisted offers **concurrently**, each as its own
gated pipeline, under one resumable manifest, bounded by a frozen `max_parallel_offers` cap
(CONC-01..06).

1. `gmj_batch.py init` writes a resumable **batch manifest** grouping the selected offers by
   `run_id`, freezing `max_parallel_offers` (default 3, `config/pipeline.config.yaml`) into the
   manifest at init time — the same freeze-once pattern as `execution_mode`/`retry_cap`.
2. **Bounded concurrent dispatch.** `gmj_dispatch_cap.py --batch <batch_id>` is the sole
   deterministic decider of which offers' runs are dispatchable right now (never the model); the
   hub dispatches up to that many offers' next steps as **parallel `Task` calls in one hub turn**.
   Each offer still runs the **existing single-offer loop, per artifact type** — same Gate A →
   Gate B → deliver ordering — each with its own isolated `retry_counts[offer][type]` slot; Gate
   A/B are still enforced non-bypassably per-offer-per-type, with no shared/aggregate gate
   shortcut introduced by concurrency.
3. **Mark + greedy refill.** `gmj_batch.py mark` records each terminal per-(offer, type) completion
   into the concurrent-safe `batch_manifest.json` (serialized writes — no lost updates when two or
   more offers finish in the same wave); the hub immediately re-asks `gmj_dispatch_cap.py` to top
   back up to the cap until every offer's 3 runs reach a terminal status. One offer's gate
   exhaustion or error is isolated — it never stalls or corrupts a sibling offer's run.
4. `/gmj-runs` (see [runs inspection](#runs-inspection)) surfaces the batch timeline and the resume
   command for any interrupted offer.

No nested sub-orchestrator: concurrency is expressed as multiple `Task` calls issued in one hub
turn (extending the existing 3-artifact-type fan-out idiom), never a per-offer nested hub — the
batch layer is a deterministic control plane over the same per-offer flow.

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

An eighth **docs** tab (DOCTAB-01..03) lists every `docs/*.md` file by name in a `DataTable`;
selecting one opens a wide, dismissible `ModalScreen` rendering that file's full content via a
read-only Textual `Markdown` widget, re-read fresh from disk on each open (no stale caching, no
new write path) — the same pure-projection discipline as the rest of the board.

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
