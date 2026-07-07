# /gmj-pipeline/generate — Step 6: render the approved artifact

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the gmj-cv-generator spoke to render a gate-passed artifact to PDF via scripts/cv/gmj_render_cv.py (live E2E is Phase 8).
---

## What this step names (thin wrapper — no control logic here)

- **First resolve the pipeline root** `<root>` (as in `/gmj-pipeline-run`): the `pipeline-dir=<dir>`
  prompt arg if present, else the `GMJ_PIPELINE_DIR` environment variable, else `.pipeline`
  (the `runs/<run_id>/` layout is identical — only the ROOT is configurable).
- **Delivery precondition first** (deterministic — Gate A ∧ Gate B recorded pass), run **once per derived run_id** — for the default 3-artifact-type run:
  ```bash
  python3 scripts/pipeline/gmj_check_delivery.py --state <root>/runs/<run_id>-cv/state.json
  python3 scripts/pipeline/gmj_check_delivery.py --state <root>/runs/<run_id>-cl/state.json
  python3 scripts/pipeline/gmj_check_delivery.py --state <root>/runs/<run_id>-ip/state.json
  # blocked unless BOTH gates recorded a pass in THAT type's own state.json — no ship-last-attempt
  ```
- **Spoke:** `Task(subagent_type: gmj-cv-generator)` — render-only, renders the gate-passed artifact:
  ```bash
  python3 scripts/cv/gmj_render_cv.py [--lang ua|ru]   # → output/cv/*.pdf
  ```

`gmj-cv-generator` never authors content — content is fixed upstream by the gates. This command just names the render entry point; the live end-to-end run against a real offer is exercised in Phase 8. No type shares another's gate verdict; the N independent results are aggregated into an explicit per-type breakdown — never a single collapsed boolean.
