# Test Plan — scheduled-runs

> ⚠️ **live-cost**: Running this flow's live steps incurs real LLM/API spend and makes real external network calls. There is no human pause to abort mid-run in autonomous mode. Confirm cost expectations before running the live steps.

This file verifies the `scheduled-runs` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — scheduled-runs

**Proves:** OPS-02 — Run the autonomous pipeline (/gmj-batch mode=autonomous) unattended on a recurring OS-native schedule (cron or launchd) via scripts/ops/gmj_cron_run.sh, with a non-blocking overlap guard.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
bash scripts/ops/gmj_cron_run.sh
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `docs/RUNBOOK.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| The wrapper's own exit code mirrors the underlying `claude -p "/gmj-batch mode=autonomous"` invocation's exit code verbatim — no retry loop, ever. No overlap detected: lock acquired via `fcntl.flock(LOCK_EX \\| LOCK_NB)` at `.pipeline/cron.lock` (or `--lock-path` override) succeeds. Downstream pass signal is Flow 4's batch-manifest `delivered` rollup | Overlap detected — wrapper prints `gmj_cron_run: another run holds <lock_path>; exiting` to stderr and exits 1 (fail-closed, no queue, no retry). Missing `claude` on PATH — wrapper prints `gmj_cron_run: 'claude' not found on PATH; check cron/launchd PATH env` and exits non-zero. Missing `--lock-path` value or unknown argument also exits 1 with a named stderr message | `scripts/ops/gmj_cron_run.sh` exit code (verbatim pass-through of `claude -p`'s own exit code) + `.pipeline/cron.lock` (fcntl-lock presence/absence) + operator-visible stderr text, surfaced to cron's mail-on-error or `launchd`'s `StandardErrorPath` log | Gate A's verdict is a gmj-truth-verifier judgment call: `rule_violated` enum values (`unresolved_span`, `scope_inflation`, `numeric_invention`, `cross_entry_merge` — `schemas/gate_result.schema.json`'s `offending_claim` $def) encode a reframe-vs-fabrication line that is a judgment call, not machine-checkable. Gate B's hard-block half (`coverage.score >= coverage_threshold`, currently 0.7 in `config/fit_thresholds.yaml`) is mechanical, but the underlying coverage-map input and `why.missing_must_haves` narrative depend on an LLM composer's claim-to-must-have mapping judgment this flow always drives the autonomous path, with the added operational fact that no human is present at all to observe a borderline case in real time |

---

_Generated from `docs/RUNBOOK.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
