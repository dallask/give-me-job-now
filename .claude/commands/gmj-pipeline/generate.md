# /gmj-pipeline/generate — Step 6: render the approved artifact

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the gmj-cv-generator spoke to render a gate-passed artifact to PDF via scripts/cv/gmj_render_cv.py (live E2E is Phase 8).
---

## What this step names (thin wrapper — no control logic here)

- **Delivery precondition first** (deterministic — Gate A ∧ Gate B recorded pass):
  ```bash
  python3 scripts/pipeline/gmj_check_delivery.py --state .pipeline/runs/<run_id>/state.json
  # blocked unless BOTH gates recorded a pass — no ship-last-attempt
  ```
- **Spoke:** `Task(subagent_type: gmj-cv-generator)` — render-only, renders the gate-passed artifact:
  ```bash
  python3 scripts/cv/gmj_render_cv.py [--lang ua|ru]   # → output/cv/*.pdf
  ```

`gmj-cv-generator` never authors content — content is fixed upstream by the gates. This command just names the render entry point; the live end-to-end run against a real offer is exercised in Phase 8.
