# /gmj-pipeline/evaluate — Step 5: Gate B (target-fit) + record verdict

---
allowed-tools: Bash(*), Read(*), LS(*)
description: Run the deterministic Gate-B fit scorer (gmj_score_fit.py, exit 0/1, no bypass) and record the verdict (gmj_record_gate.py).
---

## What this step names (thin wrapper — deterministic gate, no LLM judgment)

- **Gate B — target-fit** (hard block on must-have coverage; Gate C polish is advisory only):
  ```bash
  python3 scripts/artifacts/gmj_score_fit.py \
    --file <gate-A-passed_draft.json> --offer <offer-spec.json>
  # exit 0 ⇒ pass, exit 1 ⇒ fail — IDENTICAL in both modes (no --mode/--force/--bypass flag exists)
  ```
- **First resolve the pipeline root** `<root>` (as in `/gmj-pipeline-run`): the `pipeline-dir=<dir>`
  prompt arg if present, else the `GMJ_PIPELINE_DIR` environment variable, else `.pipeline`
  (the `runs/<run_id>/` layout is identical — only the ROOT is configurable).
- **Record the verdict** (audit artifact + `state.gate_results`; record the inner `gate_b` envelope, not the `{gate_b, gate_c}` wrapper):
  ```bash
  python3 scripts/pipeline/gmj_record_gate.py \
    --state <root>/runs/<run_id>/state.json \
    --node gmj-fit-evaluator --artifact-type <type> --attempt <n> --file <gate_b_result.json>
  ```

Runs only on a Gate-A-passed draft. On FAIL the hub increments the retry counter and consults `gmj_check_cap.py`; below-cap loops back through `/gmj-pipeline/compose` with `gmj_map_feedback.py` output, at-cap HARD STOPs. `execution_mode` gates only the post-PASS human pause, never this gate.

Runs once per derived run_id (once per requested artifact type) — the `<run_id>` above is that type's own `<base_run_id>-cv`/`-cl`/`-ip`.
