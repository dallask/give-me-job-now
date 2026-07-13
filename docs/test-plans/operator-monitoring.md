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
```bash
1. python3 scripts/dashboard/gmj_dashboard.py            # read-only live board (default)
2. python3 scripts/dashboard/gmj_dashboard.py --manage   # opt into the r/R/b/m/c action layer
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-dashboard.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**
- A human operator confirms the observed output/state matches DOCS-01's documented behavior above by reading the real output, not by delegating to a script's exit code alone.

---

_Generated from `.claude/commands/gmj-dashboard.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
