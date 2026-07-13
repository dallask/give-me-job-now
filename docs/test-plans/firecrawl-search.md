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

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| `scripts/offers/gmj_firecrawl_search.py` is invoked only when `config/preferences.yaml`'s `search_provider` field equals the single allowed enum value `"firecrawl"` (`schemas/preferences.schema.json` `search_provider` property, `enum: ["firecrawl"]`); a successful run produces the same shortlist/offer-spec artifacts as any other scout transport | Missing `FIRECRAWL_API_KEY` env var — the script prints `FIRECRAWL_API_KEY not set; add it to .env (see .env.example)` to stderr and returns exit code 1, checked before any `firecrawl.Firecrawl(...)` client construction (confirmed by direct read of `scripts/offers/gmj_firecrawl_search.py`, lines 61-67) | `schemas/preferences.schema.json`'s `search_provider` enum + `FIRECRAWL_API_KEY` env var presence + `scripts/offers/gmj_firecrawl_search.py` exit code 1 on the missing-key path + the same shortlist/offer-spec artifacts Flow 2 uses downstream | None — fully mechanical |

---

_Generated from `.claude/commands/gmj-pipeline/scout.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
