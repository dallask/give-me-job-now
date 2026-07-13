# Test Plan — pipeline-run-autonomous

> ⚠️ **live-cost**: Running this flow's live steps incurs real LLM/API spend and makes real external network calls. There is no human pause to abort mid-run in autonomous mode. Confirm cost expectations before running the live steps.

This file verifies the `pipeline-run-autonomous` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — pipeline-run-autonomous

**Proves:** EXEC-07 — Run the full offer→artifacts pipeline end to end (dual-mode HITL/autonomous, hard gates, retry cap).

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
1. claude --dangerously-skip-permissions
2. /gmj-pipeline-run   # then state your mode / offer / run_id
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-pipeline-run.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| Identical mechanical predicate to Flow 2 (`gate_results` dual-pass via `gmj_check_delivery.py`) — `execution_mode` only gates the human pause after a gate PASS, never the gate mechanism itself | Same as Flow 2, plus `gmj_check_cap.py`'s 3-way exit contract: exit 0 (`"continue"`), exit 2 (`{"status":"propose_raise",...}` — first time `current_count == cap` and not yet raised), exit 1 (`{"status":"exhausted","failure_class":"narrow"\\|"systemic",...}` — final, no further retry) | Same `state.json`/`gmj_check_delivery.py` as Flow 2, plus `scripts/pipeline/gmj_check_cap.py`'s 3-way exit code (0/1/2) and its JSON `status` (`continue`/`propose_raise`/`exhausted`) and `failure_class` (`narrow`/`systemic`) fields | Gate A's verdict is a gmj-truth-verifier judgment call: `rule_violated` enum values (`unresolved_span`, `scope_inflation`, `numeric_invention`, `cross_entry_merge` — `schemas/gate_result.schema.json`'s `offending_claim` $def) encode a reframe-vs-fabrication line that is a judgment call, not machine-checkable. Gate B's hard-block half (`coverage.score >= coverage_threshold`, currently 0.7 in `config/fit_thresholds.yaml`) is mechanical, but the underlying coverage-map input and `why.missing_must_haves` narrative depend on an LLM composer's claim-to-must-have mapping judgment autonomous mode removes only the human pause, never the machine gate, so the same reframe-vs-fabrication judgment call is present, now with no human present to catch a borderline case before the auto-approved raise or delivery |

---

_Generated from `.claude/commands/gmj-pipeline-run.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
