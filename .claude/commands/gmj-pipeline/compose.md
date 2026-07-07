# /gmj-pipeline/compose — Step 3: compose one artifact type

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the gmj-artifact-composer spoke for one artifact type (CV | cover_letter | interview_prep); names gmj_record_retry.py for the per-type counter.
---

## What this step names (thin wrapper — no control logic here)

- **Spoke:** `Task(subagent_type: gmj-artifact-composer)` for **one** artifact type (`cv` | `cover_letter` | `interview_prep`), reading canonical `config/candidate.yaml` (read-only) + the frozen `offer-spec.json`. On a retry it also receives ONLY the structured `gmj_map_feedback.py` output (`{missing_must_haves, fabricated_claims, gate}`) — never gate prose or a transcript.
- **First resolve the pipeline root** `<root>` (as in `/gmj-pipeline-run`): the `pipeline-dir=<dir>`
  prompt arg if present, else the `GMJ_PIPELINE_DIR` environment variable, else `.pipeline`
  (the `runs/<run_id>/` layout is identical — only the ROOT is configurable).
- **Per-(offer, type) retry counter** (deterministic):
  ```bash
  python3 scripts/artifacts/gmj_record_retry.py \
    --state <root>/runs/<run_id>/state.json \
    --offer-slug <offer-slug> --artifact-type <cv|cover_letter|interview_prep> --increment
  ```

The three artifact types compose as parallel `Task` fan-out (each has its own isolated `retry_counts[offer][type]` slot and its own isolated `state.json` (`<run_id>-cv`/`-cl`/`-ip`)); each type's gate loop then runs sequentially. Emits an `artifact_draft` (file artifact).
