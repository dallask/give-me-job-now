# /pipeline-run — Whole offer→artifacts pipeline (dual-mode, retry-capped)

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the full offer→artifacts pipeline end to end (dual-mode HITL/autonomous, hard gates, retry cap).
---

## What to do

1. **Hub runs here (top level):** Follow `.claude/agents/vacancy-orchestrator.md` **in this chat session**—you are the hub. Use **`Task`** only to spawn **spokes** (`offer-scout`, `artifact-composer`, `truth-verifier`, `fit-evaluator`, `cv-generator`). **Never** call `Task` with `subagent_type: vacancy-orchestrator`. Nesting the hub inside `Task` removes `Task` from that context ("Task is not available inside subagents"), which breaks the whole pipeline (Pitfall 5).
2. Drive the deterministic control plane via **`Bash`** for every safety decision — the hub never judges a gate, a cap, or delivery. The runtime loop is documented in `docs/ARCHITECTURE.md` §5.1:
   - `init_run` — freeze `execution_mode` + `retry_cap` + `run_id` into `.pipeline/runs/<run_id>/state.json` (`scripts/pipeline/gmj_state_write.py`).
   - loop — `gmj_route.py` → next step; `gmj_check_offer.py` before each dispatch; `Task(spoke)`; on a gate node run `gmj_check_truth.py` / `gmj_score_fit.py` (exit 0/1, no bypass) → `gmj_record_gate.py`; on FAIL `gmj_record_retry.py --increment` → `gmj_check_cap.py` (below-cap → `gmj_map_feedback.py` → `Task(artifact-composer)`; at-cap → HARD STOP naming the failing artifact + reason).
   - deliver — `gmj_check_delivery.py` (Gate A ∧ Gate B recorded pass) before any artifact is delivered.
3. **`execution_mode` gates ONLY the human pause**, never the machine gate: HITL pauses for approval after a PASS; autonomous proceeds automatically. Truthfulness (Gate A) and target-fit (Gate B) block identically in both modes.

## Parameters

- **`mode`** — `human_in_the_loop` | `autonomous`. Overrides the `execution_mode` default in `config/pipeline.config.yaml`; frozen into run state at `init_run` (a mid-run config edit cannot change an in-flight run).
- **`offer`** — a pasted offer URL / text (single-offer intake) **or** the path to an already-frozen `offer-spec.json`.
- **`run_id`** — optional; a fresh id is generated if absent. Scopes `.pipeline/runs/<run_id>/` (state + gate logs). Passing an existing `run_id` **resumes** that run via `gmj_route.py`.

## CLI-only invocation (EXEC-07)

```bash
claude --dangerously-skip-permissions
# then, in the session:
/pipeline-run   # then state your mode / offer / run_id
```

There is no UI — the collective runs entirely from the CLI.

## Per-step commands

Each step is independently invocable (EXEC-05) — see `.claude/commands/pipeline/`:
`/pipeline/scout`, `/pipeline/freeze`, `/pipeline/compose`, `/pipeline/verify`,
`/pipeline/evaluate`, `/pipeline/generate`. Use them to run or resume a single step;
`/pipeline-run` runs the whole flow.
