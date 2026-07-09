# SHOWCASE — the give-me-job collective, end-to-end

This is the narrative tour of the give-me-job collective: what problem it solves, the shape of the
system, and a single concrete offer walked all the way from intake to a rendered PDF — with both
hard gates visibly firing. It **narrates**; for the authoritative roster, boundaries, and control
loop see **[docs/ARCHITECTURE.md](ARCHITECTURE.md)**. To *run* the flow yourself, follow
**[docs/DEMO-WALKTHROUGH.md](DEMO-WALKTHROUGH.md)** and **[docs/RUNBOOK.md](RUNBOOK.md)**.

---

## The problem

Given a **real job offer**, produce a **truthful, offer-optimized** set of application
artifacts — a CV (PDF), a cover letter, and an interview-prep document — that **provably trace back
to the candidate's real profile** (`config/candidate.yaml`) and **pass mandatory quality gates**.

The whole design is a defense against the classic multi-agent failure modes:

- **Fabricated facts** — an agent invents a credential, a number, or a seniority the candidate does
  not have.
- **Off-target drift** — the artifacts read well but do not actually answer the offer's must-haves.
- **Context bloat** — agents pass whole transcripts around and lose the thread.
- **Silent quality decay** — nobody notices the output got worse over a retry loop.

The core promise: **if everything else fails, the artifacts still never fabricate and still actually
target the offer.** Reframing and emphasis of a real fact are allowed; invention is hard-blocked.

---

## The shape

A single top-level hub — **`gmj-orchestrator`** — is the only role that holds `Task` and delegates
to bounded spokes. Spokes never spawn spokes (a nested hub loses `Task` in Claude Code), so routing
stays a clean loop: **User Request → Routing → Agent Selection → Task Delegation → Quality Gate →
Result**.

- **Hub (1):** `gmj-orchestrator` — routes, dispatches, runs the gates, tracks cycles.
- **Core spokes (5):** `gmj-offer-scout` (discover + rank + freeze the offer),
  `gmj-artifact-composer` (compose the three artifacts), `gmj-truth-verifier` (Gate A, truth),
  `gmj-fit-evaluator` (Gate B/C, fit + polish), `gmj-cv-generator` (render to PDF).
- **Supporting (2):** `gmj-candidate-analyzer` (parse candidate source materials),
  `gmj-candidate-configurator` (canonical write/merge into `config/candidate.yaml`).
- **Optional:** `gmj-template-creator` (branded-CV HTML template from a screenshot).

Every hop between roles is a **typed file-artifact path, never a transcript**. A draft is a file, a
gate verdict is a file, the offer-spec is a file. This is what keeps context lean and the audit
trail honest.

---

## A walked offer

Take one concrete offer to make the guarantees fire. The candidate's `config/candidate.yaml`
contains (abbreviated):

```yaml
professional_experience:
  - title: "Sample Backend Engineer"
    achievements:
      - "Led AI-assisted engineering adoption across the 20-person delivery team in 2025–2026"
```

The offer is a **Senior Backend Engineer** posting whose frozen `offer_spec` carries these
`must_haves` (5 required):

```
MH-1  Python backend services
MH-2  REST / HTTP API design
MH-3  PostgreSQL / relational data
MH-4  Team leadership
MH-5  CI/CD delivery pipelines
```

The flow:

1. **Intake.** `gmj-offer-scout` reads `config/sources.yaml` (mandatory), stays inside its
   allow-list, normalizes and ranks candidate offers, and **freezes** the chosen one as a
   hash-stamped `offer_spec` file. Every downstream spoke reads that same frozen artifact.
2. **Compose.** `gmj-artifact-composer` reads `config/candidate.yaml` (read-only) plus the
   `offer_spec` and emits three `artifact_draft` files — CV, cover letter, interview-prep. It owns
   the gap-report pass and the enhance loop.
3. **Gate A — truth** (below) must pass first.
4. **Gate B/C — fit** (below) scores the truth-passed draft.
5. **Render** — a draft that clears both gates reaches `gmj-cv-generator`.

The two gates are where the guarantees become visible.

---

## Gate A — truth

`gmj-truth-verifier` re-grounds **every claim** in the draft against the cited span in
`config/candidate.yaml`. It emits a `gate_result` file; the deterministic `gmj_check_truth.py` script
makes the exit-0/1 decision — the model never decides whether truth passed. The reframe-vs-fabrication
boundary is the **`gmj-truth-rubric`** skill (four rules, applied in order).

**A truthful reframe — ALLOWED (PASS).** The composer foregrounds a real fact in different words:

```
span   professional_experience[0].achievements[0]:
       "Led AI-assisted engineering adoption across the 20-person delivery team in 2025–2026"
claim  "Led a 20-person delivery team"          → PASS
```

The digit `20` is literally present in the cited span, so surfacing "20-person delivery team" is an
emphasis reframe, not an invention. This is exactly the kind of offer-optimization the collective is
built to do: it covers must-have **MH-4 (Team leadership)** *without adding a fact*.

**A fabrication — HARD-BLOCKED (FAIL, loops back).** Suppose an over-eager draft line reads:

```
span   professional_experience[0].achievements[0]:  (contains no percentage)
claim  "Cut delivery time by 40%"                → FAIL  (numeric_invention)
```

The digit `40` is absent from the cited span. Gate A hard-blocks, names the offending line back to
`gmj-artifact-composer`, and the draft loops for a re-compose. **Gate A is non-bypassable in any
mode** — autonomous mode removes the human pause, never the machine gate. The fabricated line never
reaches the reader.

---

## Gate B/C — fit

Once Gate A passes, `gmj-fit-evaluator` scores the truth-passed draft against the frozen
`offer_spec`. Gate B is a **coverage-only hard block**; Gate C is **advisory polish that never
blocks**. The deterministic `gmj_score_fit.py` script computes the verdict; the scoring rubric is the
**`gmj-fit-rubric`** skill.

Coverage is a literal count: `covered_count / total_count` of the offer's `must_haves`, and it must
be `>=` the `coverage_threshold` in `config/fit_thresholds.yaml` (derived, not guessed — the seeded
anchor is `0.7`).

**A below-threshold draft — LOOPS BACK.** The first composed CV covers only 3 of the 5 must-haves:

```
MH-1  Python backend services      ✓
MH-2  REST / HTTP API design        ✓
MH-4  Team leadership               ✓   (the truthful "20-person delivery team" reframe)
MH-3  PostgreSQL / relational data  ✗
MH-5  CI/CD delivery pipelines      ✗

coverage = 3/5 = 0.60   <   0.70 threshold   → Gate B FAIL
```

Gate B hard-blocks and loops back to `gmj-artifact-composer` with structured feedback
`{missing_must_haves: [MH-3, MH-5]}`, bounded by the retry cap. The secondary signals
(keyword alignment, language match, seniority scope) are reported for context but **never rescue a
coverage failure**.

The composer re-drafts, surfacing the candidate's *real* PostgreSQL and CI/CD experience from
`config/candidate.yaml` (both must still pass Gate A):

```
coverage = 5/5 = 1.00   >=   0.70 threshold   → Gate B PASS
```

Gate C then scores advisory polish (five dimensions) and reports it in the `why` — it never blocks
delivery. Both hard gates are now green.

---

## Render

A draft that passes **Gate A ∧ Gate B** reaches `gmj-cv-generator`, which renders it to a real PDF
**and HTML** under `output/cv/` via `scripts/cv/gmj_render_cv.py` (template mode by default). The
companion renderers produce the cover letter and interview-prep document. All three artifact types
are produced by default per run, each independently gated. Before anything ships, the
deterministic `gmj_check_delivery.py` guard refuses to deliver any artifact lacking a **recorded**
Gate A ∧ Gate B pass — so even a loop bug cannot ship a failed draft.

Run state and every `gate_result` verdict are logged under `.pipeline/runs/<run_id>/`, the audit
trail proving which verdicts passed for each delivered artifact.

---

## The cockpit

The operator watches all of this from the btop-style Textual dashboard,
`scripts/dashboard/gmj_dashboard.py`. It is **read-only by default**; `--manage` opts into the action
keys, and `--pipeline-dir <dir>` threads the operator's run directory to any launched children.
Internally it splits into three modules: `gmj_dashboard_model.py` (read), `gmj_dashboard.py` (UI),
and `gmj_dashboard_actions.py` (mutate). Its diagnostics tabs include a **docs** pane — a browser
over the top-level `docs/*.md` files, opened straight from the cockpit.

Real dashboard screenshots are a **deferred manual capture** (headless environment) — capture them
yourself and drop them in:

> **[SCREENSHOT: read-only dashboard board]** — capture manually with
> `python3 scripts/dashboard/gmj_dashboard.py --pipeline-dir <dir>` in a ≥60-row terminal,
> then save to `docs/img/dashboard-board.png` and replace this placeholder.

> **[SCREENSHOT: `--manage` mode with a run in flight]** — capture manually with
> `python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir <dir>` (use a **COPY** of
> `<dir>` — `--manage` writes the real config) in a ≥60-row terminal, then save to
> `docs/img/dashboard-manage.png` and replace this placeholder.

---

## Where to go next

- **[docs/ARCHITECTURE.md](ARCHITECTURE.md)** — the authoritative roster, per-spoke boundaries, the
  offer→artifacts data flow (§5), and the runtime control loop (§5.1).
- **[docs/RUNBOOK.md](RUNBOOK.md)** — the operator guide for an end-to-end real-offer run.
- **[docs/DEMO-WALKTHROUGH.md](DEMO-WALKTHROUGH.md)** — the exact command sequence + narration beats
  + an asciinema recording plan to demo the pipeline and the dashboard live.
