# /gmj-pipeline/verify — Step 4: Gate A (truth) + record verdict

---
allowed-tools: Bash(*), Read(*), LS(*)
description: Run the deterministic Gate-A truth check (gmj_check_truth.py, exit 0/1, no bypass) and record the verdict (gmj_record_gate.py).
---

## What this step names (thin wrapper — deterministic gate, no LLM judgment)

- **Gate A — truth** (hard block; every claim must trace to `candidate.yaml`):
  ```bash
  python3 scripts/artifacts/gmj_check_truth.py \
    --file <artifact_draft.json> --candidate config/candidate.yaml
  # exit 0 ⇒ pass, exit 1 ⇒ fail — IDENTICAL in both modes (no --mode/--force/--bypass flag exists)
  ```
- **Record the verdict** (audit artifact + `state.gate_results`):
  ```bash
  python3 scripts/pipeline/gmj_record_gate.py \
    --state .pipeline/runs/<run_id>/state.json \
    --node gmj-truth-verifier --artifact-type <type> --attempt <n> --file <gate_result.json>
  ```

The gate blocks the same way regardless of `execution_mode`; mode only decides whether the hub pauses for a human after a PASS. On FAIL the hub increments the retry counter and consults `gmj_check_cap.py` (see `/gmj-pipeline/compose` + `docs/ARCHITECTURE.md` §5.1). Gate A must pass before `/gmj-pipeline/evaluate` runs.
