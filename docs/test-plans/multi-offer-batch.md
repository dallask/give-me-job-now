# Test Plan — gmj-batch

> ⚠️ **live-cost**: Running this flow's live steps incurs real LLM/API spend and makes real external network calls. There is no human pause to abort mid-run in autonomous mode. Confirm cost expectations before running the live steps.

This file verifies the `gmj-batch` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — gmj-batch

**Proves:** SELECT-05 — Select several shortlisted offers; freeze + run each as its own gated pipeline under a resumable batch manifest.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
claude --dangerously-skip-permissions
```

Inside the now-live REPL session, type:
```
/gmj-batch            # then state your selection (1,3,5 | all) and mode
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-batch.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| Per offer, per artifact type, the same `gate_results` dual-pass predicate as Flow 2, rolled up in `batch_manifest.json`'s per-offer `runs.{cv,cover_letter,interview_prep}` entries with `status: "delivered"`. Batch-level rollup: `gmj_runs.py`'s `_offer_status_counts()` projects `by_offer_status` as a 5-value vocabulary count over the same statuses | Any offer/type entry with `status: "gate_exhausted"` or `status: "error"` in `batch_manifest.json`'s `runs` object — one offer's gate exhaustion is isolated and never stalls or corrupts a sibling offer's run | `schemas/batch_manifest.schema.json`'s `offers[].runs.{cv,cover_letter,interview_prep}.status` enum (`["waiting","in_flight","delivered","gate_exhausted","error"]`) + `.pipeline/runs/<batch_id>/batch_manifest.json` + `gmj_dispatch_cap.py`'s frozen `max_parallel_offers` bound (default 3, `config/pipeline.config.yaml`) | Gate A's verdict is a gmj-truth-verifier judgment call: `rule_violated` enum values (`unresolved_span`, `scope_inflation`, `numeric_invention`, `cross_entry_merge` — `schemas/gate_result.schema.json`'s `offending_claim` $def) encode a reframe-vs-fabrication line that is a judgment call, not machine-checkable. Gate B's hard-block half (`coverage.score >= coverage_threshold`, currently 0.7 in `config/fit_thresholds.yaml`) is mechanical, but the underlying coverage-map input and `why.missing_must_haves` narrative depend on an LLM composer's claim-to-must-have mapping judgment — batching adds no new semantic-truth risk beyond the per-offer pipeline's own Gate A/B judgment calls, isolated per `retry_counts[offer][type]` |

---

_Generated from `.claude/commands/gmj-batch.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
