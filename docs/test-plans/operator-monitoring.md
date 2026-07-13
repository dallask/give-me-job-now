# Test Plan — gmj-dashboard

This file verifies the `gmj-dashboard` flow for a human operator running it directly.

## Setup & Preconditions

- `--pipeline-dir` — pipeline root to project (and batch into). Default `.pipeline`.
- `--refresh` — poll interval in seconds. Default `1.0`.
- `--read-only` — explicit read-only (the default; binds no mutating keys).
- `--manage` — bind the live mutating action keys (`r`/`R`/`b`/`m`/`c`). Opt-in only.
- `--config` — config file the `m`/`c` knobs edit under `--manage`.

## Test 1 — gmj-dashboard

**Proves:** DOCS-01 — Launch the live btop-style pipeline dashboard (read-only timeline by default; --manage opts into the mutating action layer).

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
Run ONE of the following, not both — these are independent, mutually-exclusive entry points. Inspect the output before proceeding.

Option 1:
```bash
python3 scripts/dashboard/gmj_dashboard.py            # read-only live board (default)
```

Option 2:
```bash
python3 scripts/dashboard/gmj_dashboard.py --manage   # opt into the r/R/b/m/c action layer
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-dashboard.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| No single pass/fail signal exists for "monitoring" itself — it is a read-only projection, never an action with a terminal state. The nearest qualitative check is that the dashboard's displayed rollup values agree byte-for-byte with the same facts `/gmj-runs` would print: the dashboard is correct if and only if its `DashboardModel.snapshot()` projection matches `gmj_runs.py`'s own read of the identical `.pipeline/runs/**/state.json` and `batch_manifest.json` files, re-read fresh from disk on each open with no stale caching and no new write path | No terminal fail state exists for the monitoring flow itself. The nearest observable failure would be the board falling out of sync with disk state, but per design this cannot happen since every value is re-derived fresh, nothing new; state honestly: no discrete pass/fail signal exists for this flow, the qualitative check is agreement with `/gmj-runs`'s own values on the same underlying file | `scripts/dashboard/gmj_dashboard_model.py`'s `DashboardModel.snapshot()` + `scripts/pipeline/gmj_runs.py`'s equivalent read of the same `.pipeline/runs/**/state.json` and `.pipeline/runs/**/batch_manifest.json` files (both read-only default; `--manage` opts into a separate mutating action layer out of this flow's default scope) | None — fully mechanical |

---

_Generated from `.claude/commands/gmj-dashboard.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
