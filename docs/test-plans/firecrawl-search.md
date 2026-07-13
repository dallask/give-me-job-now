# Test Plan — scout

> ⚠️ **live-cost**: Running this flow's live steps incurs real LLM/API spend and makes real external network calls. There is no human pause to abort mid-run in autonomous mode. Confirm cost expectations before running the live steps.

This file verifies the `scout` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — scout

**Proves:** GUIDE-04 — Run the gmj-offer-scout spoke (board-search or single-offer), scoped by config/sources.yaml, then hand to /gmj-pipeline/freeze.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps:**
```bash
# See .claude/commands/gmj-pipeline/scout.md for the exact invocation.
```

**Expected:** running the steps above against `.claude/commands/gmj-pipeline/scout.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**
- A human operator confirms the observed output/state matches GUIDE-04's documented behavior above by reading the real output, not by delegating to a script's exit code alone.

---

_Generated from `.claude/commands/gmj-pipeline/scout.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
