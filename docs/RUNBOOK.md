# RUNBOOK — End-to-end real-offer run

Operator guide for running the give-me-job collective against a **real, current job
offer** and producing the truthful, offer-optimized artifacts (CV PDF + cover-letter PDF +
interview-prep document) end to end via `/pipeline-run`.

This runbook maps the two done-criteria for Phase 8:

- **E2E-01 — deterministic guard demo (DONE).** Proven, repeatable, no human judgment.
- **E2E-03 — live real-offer run (human-acceptance UAT).** Requires an operator driving a
  real offer and accepting the delivered artifacts.

`cv-generator` renders every artifact through Python scripts — **E2E-02** (Python-rendered
CV + cover, no manual authoring) is covered by the bridge + renderers named below.

---

## 1. Setup (dependencies)

From the repository root:

```bash
pip install -r scripts/cv/requirements.txt
```

This installs the render stack — notably **reportlab** (the built-in ReportLab CV layout
engine) and **PyYAML** / **pypdf**. The **bundled DejaVu fonts** under `scripts/cv/fonts/`
(`DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`) cover **ua/ru Cyrillic** rendering, so no system
font install is required. **All deps are already declared — no new package installs are
needed for this phase.** WeasyPrint (HTML templates) stays optional.

---

## 2. Running a real offer

Drive a live run against a **real, current offer** plus a **real, populated**
`config/candidate.yaml` (the single source of truth — every artifact claim must trace back
to it):

```bash
claude --dangerously-skip-permissions
# then, in the session:
/pipeline-run
# state your: mode (human_in_the_loop | autonomous), offer (URL/text or offer-spec.json), run_id?
```

### Hub-at-top-level rule (Pitfall 6 / T-08-12)

The **hub runs at top level in this chat session** — you are the `vacancy-orchestrator`.
`Task` spawns **spokes only** (`offer-scout`, `artifact-composer`, `truth-verifier`,
`fit-evaluator`, `cv-generator`). **Never** call `Task` with
`subagent_type: vacancy-orchestrator` — nesting the hub inside `Task` removes `Task` from
that context and breaks the whole pipeline (see `.claude/CLAUDE.md` hub-and-spoke rule).

### Control loop (`docs/ARCHITECTURE.md` §5.1)

The deterministic control plane makes every safety decision; the hub calls scripts via
`Bash` and never judges a gate itself:

1. **init_run** — freeze `execution_mode` + `retry_cap` + `run_id` into
   `.pipeline/runs/<run_id>/state.json`.
2. **route** — `gmj_route.py` picks the next step; `gmj_check_offer.py` runs before each dispatch
   (stale offer aborts); `Task(spoke)` produces a draft or gate_result.
3. **gate** — at a gate node, `gmj_check_truth.py` (Gate A) / `gmj_score_fit.py` (Gate B) exit 0/1
   with no bypass; `gmj_record_gate.py` records the verdict. FAIL → `gmj_record_retry.py` →
   `gmj_check_cap.py` (below cap: `gmj_map_feedback.py` → re-compose; at cap: HARD STOP).
4. **deliver** — `gmj_check_delivery.py` confirms **Gate A ∧ Gate B recorded pass** before any
   artifact is delivered.

`execution_mode` gates **only the human pause**, never the machine gate: HITL pauses for
approval after a PASS; autonomous proceeds automatically. Truth (Gate A) and target-fit
(Gate B) block identically in both modes.

---

## 3. Outputs

Each delivered artifact passes **Gate A (truth)** and **Gate B (target-fit)** before it
ships:

- **CV** — PDF under `output/cv/` (draft → `gmj_draft_to_cv_yaml.py` bridge →
  `gmj_render_cv.py --lang <lang>`).
- **Cover letter** — PDF under `output/cv/` (`gmj_render_cover_letter.py`).
- **Interview-prep** — markdown document (`gmj_render_interview_prep.py`).

Gate verdicts and run state are logged under **`.pipeline/runs/<run_id>/`** — the audit
trail (GUARD-03 / T-08-13): the recorded `gate_result` artifacts prove which verdicts
passed for each delivered artifact.

---

## 4. Done-criteria map

| Criterion | What it proves | How it is exercised | Status |
|-----------|----------------|---------------------|--------|
| **E2E-01** | Deterministic guard enforcement: nothing fabricated/off-target ships; an approved draft renders to a real PDF with zero manual authoring | `python3 tests/test_e2e_guards.py` (matrix + dry-run + wiring + runbook assertions) | **DONE** — deterministic, repeatable |
| **E2E-02** | CV + cover letter rendered via Python, no manual PDF authoring | bridge (`gmj_draft_to_cv_yaml.py`) + renderers (`gmj_render_cv.py`, `gmj_render_cover_letter.py`, `gmj_render_interview_prep.py`), wired in `.claude/agents/cv-generator.md` | Covered |
| **E2E-03** | Live real-offer run produces accepted artifacts end to end | `/pipeline-run` on a real offer + populated `config/candidate.yaml` | **Human-acceptance UAT** — operator drives + accepts |

**E2E-01** is the deterministic floor (machine-proven). **E2E-03** is the live acceptance
run a human performs with a real offer; it cannot be auto-asserted because it depends on a
current external posting and human judgment of the delivered artifacts.
