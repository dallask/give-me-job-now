# /gmj-pipeline-run — Whole offer→artifacts pipeline (dual-mode, retry-capped)

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the full offer→artifacts pipeline end to end (dual-mode HITL/autonomous, hard gates, retry cap).
---

## What to do

1. **Hub runs here (top level):** Follow `.claude/agents/gmj-orchestrator.md` **in this chat session**—you are the hub. Use **`Task`** only to spawn **spokes** (`gmj-offer-scout`, `gmj-artifact-composer`, `gmj-truth-verifier`, `gmj-fit-evaluator`, `gmj-cv-generator`). **Never** call `Task` with `subagent_type: gmj-orchestrator`. Nesting the hub inside `Task` removes `Task` from that context ("Task is not available inside subagents"), which breaks the whole pipeline (Pitfall 5).
2. Drive the deterministic control plane via **`Bash`** for every safety decision — the hub never judges a gate, a cap, or delivery. **First resolve the pipeline root:** use the `pipeline-dir=<dir>` prompt arg if present, else the `GMJ_PIPELINE_DIR` environment variable, else `.pipeline`. Next, resolve the requested artifact-type subset (default all three: `cv, cover_letter, interview_prep`) and derive one run_id per type by running `scripts/pipeline/gmj_pipeline_run.py --run-id <run_id> --artifact-types <list>` via `Bash` — it hard-fails BEFORE any dispatch on an unknown/typo'd type, naming the invalid value and the valid set; never derive or validate this list by reasoning alone. Call this resolved root `<root>` and construct **every** run-state path under it — `<root>/runs/<run_id>/state.json`, `--run-dir <root>/runs/<run_id>` — and pass `--pipeline-dir <root>` to every `gmj_runs.py` / `gmj_batch.py` invocation. The on-disk `<root>/runs/<run_id>/` layout is identical; only the ROOT is configurable (`.pipeline` is the fallback, not the only path). The runtime loop is documented in `docs/ARCHITECTURE.md` §5.1:
   - `init_run` — freeze `execution_mode` + `retry_cap` + `run_id` into `<root>/runs/<run_id>-{cv,cl,ip}/state.json` for each type in the resolved `--artifact-types` subset — once per derived run_id, never one shared file for all three types (`scripts/pipeline/gmj_state_write.py`).
   - loop — `gmj_route.py` → next step; `gmj_check_offer.py` before each dispatch; `Task(spoke)`; on a gate node run `gmj_check_truth.py` / `gmj_score_fit.py` (exit 0/1, no bypass) → `gmj_record_gate.py`; on FAIL `gmj_record_retry.py --increment` → `gmj_check_cap.py` (below-cap → `gmj_map_feedback.py` → `Task(gmj-artifact-composer)`; at-cap → HARD STOP naming the failing artifact + reason).
   - deliver — `gmj_check_delivery.py` (Gate A ∧ Gate B recorded pass) before any artifact is delivered, called once per derived run_id; aggregate the N independent results into a per-type breakdown (e.g. cv: delivered, cover_letter: delivered, interview_prep: pending — Gate B retry 1/2) — never a single collapsed boolean.
3. **`execution_mode` gates ONLY the human pause**, never the machine gate: HITL pauses for approval after a PASS; autonomous proceeds automatically. Truthfulness (Gate A) and target-fit (Gate B) block identically in both modes.

## Parameters

- **`mode`** — `human_in_the_loop` | `autonomous`. Overrides the `execution_mode` default in `config/pipeline.config.yaml`; frozen into run state at `init_run` (a mid-run config edit cannot change an in-flight run).
- **`offer`** — a pasted offer URL / text (single-offer intake) **or** the path to an already-frozen `offer-spec.json`.
- **`run_id`** — optional; a fresh id is generated if absent. Scopes `<root>/runs/<run_id>/` (state + gate logs), where `<root>` is resolved from the `pipeline-dir=<dir>` prompt arg, else the `GMJ_PIPELINE_DIR` environment variable, else `.pipeline`. Passing an existing `run_id` **resumes** that run via `gmj_route.py`.
- **`pipeline-dir`** — optional; the run-state root the operator wants this run to act on. When present it takes precedence over `GMJ_PIPELINE_DIR`; when absent the orchestrator falls back to `GMJ_PIPELINE_DIR`, else `.pipeline`.
- **`artifact-types`** — optional; comma-list narrowing the default 3 (`cv,cover_letter,interview_prep`) to a subset, e.g. `--artifact-types=cv,cover_letter`. An unknown/typo'd value hard-fails before any dispatch, naming the invalid value and the valid set.

## CLI-only invocation (EXEC-07)

```bash
claude --dangerously-skip-permissions
# then, in the session:
/gmj-pipeline-run   # then state your mode / offer / run_id
```

There is no UI — the collective runs entirely from the CLI.

## Per-step commands

Each step is independently invocable (EXEC-05) — see `.claude/commands/gmj-pipeline/`:
`/gmj-pipeline/scout`, `/gmj-pipeline/freeze`, `/gmj-pipeline/compose`, `/gmj-pipeline/verify`,
`/gmj-pipeline/evaluate`, `/gmj-pipeline/generate`. Use them to run or resume a single step;
`/gmj-pipeline-run` runs the whole flow.
