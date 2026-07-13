# Test Plan — gmj-runs

This file verifies the `gmj-runs` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — gmj-runs

**Proves:** ERGO-04 — Terse, read-only timeline of pipeline runs and batches; surfaces (never executes) the resume command for each.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
claude --dangerously-skip-permissions
```

Inside the now-live REPL session, type:
```
/gmj-runs                 # terse newest-first timeline of every run
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-runs.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| No single pass/fail signal exists at the inspection step itself. Nearest qualitative check: `/gmj-runs`'s `project_status()` function returns one of exactly 4 string values via a locked top-down, first-match-wins order: `"delivered"` (gate_results dual-pass, reusing `blocked_reason()`), `"failed"` (any nested `retry_counts[...][...]` value >= the frozen `retry_cap` int), `"pending"` (empty `gate_results` AND empty `retry_counts` AND `current_step` is `None`/`"gmj-artifact-composer"`), else `"running"`. The inspector only prints the resume command — it never itself resumes; the resume flow's own pass signal is that same 4-value status advancing toward `"delivered"` on the next invocation of the resumed command | Status stays `"failed"` after resuming (retry cap already exhausted with no further raise available) — or a resumed run's state file is malformed/missing, which `gmj_runs.py` degrades to `"unknown"` rather than raising | `scripts/pipeline/gmj_runs.py`'s `project_status()` 4-value vocabulary (`delivered`/`failed`/`pending`/`running`, plus inspector-only `unknown` on read-degrade) + `.pipeline/runs/<run_id>/state.json`'s `current_step`, `gate_results`, `retry_counts`, `retry_cap` fields | None — fully mechanical |

---

_Generated from `.claude/commands/gmj-runs.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
