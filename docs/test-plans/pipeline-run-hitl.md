# Test Plan — pipeline-run-hitl

This file verifies the `pipeline-run-hitl` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — pipeline-run-hitl

**Proves:** EXEC-07 — Run the full offer→artifacts pipeline end to end (dual-mode HITL/autonomous, hard gates, retry cap).

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
claude --dangerously-skip-permissions
```

Inside the now-live REPL session, type:
```
/gmj-pipeline-run   # then state your mode / offer / run_id
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-pipeline-run.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| Per artifact type, `.pipeline/runs/<run_id>-{cv,cl,ip}/state.json`'s `gate_results["gmj-truth-verifier"] == "pass"` AND `gate_results["gmj-fit-evaluator"] == "pass"` — the exact predicate `gmj_check_delivery.py`'s `blocked_reason()` checks; on pass it prints `deliverable` and exits 0. Rendered output then exists at `output/cv/*.pdf` (+ `.html` sibling for CV) | `gmj_check_delivery.py` prints `blocked: gmj-truth-verifier=<verdict-or-missing>, gmj-fit-evaluator=<verdict-or-missing>` to stderr and exits 1; underlying gate failure is `gmj_check_truth.py` (Gate A) or `gmj_score_fit.py` (Gate B) each independently exiting 1 on FAIL | `.pipeline/runs/<run_id>-{cv,cl,ip}/state.json`'s `gate_results` field + `scripts/pipeline/gmj_check_delivery.py` exit 0/1 + `schemas/gate_result.schema.json`'s `content.verdict` enum (`["pass","fail"]`) (Gate C `polish` sub-scores are advisory-only and never gate delivery) | Gate A's verdict is a gmj-truth-verifier judgment call: `rule_violated` enum values (`unresolved_span`, `scope_inflation`, `numeric_invention`, `cross_entry_merge` — `schemas/gate_result.schema.json`'s `offending_claim` $def) encode a reframe-vs-fabrication line that is a judgment call, not machine-checkable. Gate B's hard-block half (`coverage.score >= coverage_threshold`, currently 0.7 in `config/fit_thresholds.yaml`) is mechanical, but the underlying coverage-map input and `why.missing_must_haves` narrative depend on an LLM composer's claim-to-must-have mapping judgment |

---

_Generated from `.claude/commands/gmj-pipeline-run.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
