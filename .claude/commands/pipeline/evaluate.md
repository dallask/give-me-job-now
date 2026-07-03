# /pipeline/evaluate — Step 5: Gate B (target-fit) + record verdict

---
allowed-tools: Bash(*), Read(*), LS(*)
description: Run the deterministic Gate-B fit scorer (score_fit.py, exit 0/1, no bypass) and record the verdict (record_gate.py).
---

## What this step names (thin wrapper — deterministic gate, no LLM judgment)

- **Gate B — target-fit** (hard block on must-have coverage; Gate C polish is advisory only):
  ```bash
  python3 scripts/artifacts/score_fit.py \
    --file <gate-A-passed_draft.json> --offer <offer-spec.json>
  # exit 0 ⇒ pass, exit 1 ⇒ fail — IDENTICAL in both modes (no --mode/--force/--bypass flag exists)
  ```
- **Record the verdict** (audit artifact + `state.gate_results`; record the inner `gate_b` envelope, not the `{gate_b, gate_c}` wrapper):
  ```bash
  python3 scripts/pipeline/record_gate.py \
    --state .pipeline/runs/<run_id>/state.json \
    --node fit-evaluator --artifact-type <type> --attempt <n> --file <gate_b_result.json>
  ```

Runs only on a Gate-A-passed draft. On FAIL the hub increments the retry counter and consults `check_cap.py`; below-cap loops back through `/pipeline/compose` with `map_feedback.py` output, at-cap HARD STOPs. `execution_mode` gates only the post-PASS human pause, never this gate.
