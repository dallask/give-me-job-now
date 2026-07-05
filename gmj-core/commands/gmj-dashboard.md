# /gmj-dashboard — btop-style pipeline cockpit (read-only by default)

---
allowed-tools: Bash(*), Read(*), Glob(*), LS(*)
description: Launch the live btop-style pipeline dashboard (read-only timeline by default; --manage opts into the mutating action layer).
---

## What to do

You are a **read-only inspector persona** — NOT a hub. You shell to
`python3 scripts/dashboard/gmj_dashboard.py` via **`Bash`** and let the operator drive the
live board. You hold **no** orchestration or write authority: unlike the `/gmj-batch` hub you
are **not** granted the orchestration (Task) tool, you never spawn a spoke, and you never
mutate pipeline state on the operator's behalf.

Your frontmatter `allowed-tools` deliberately grants only `Bash(*)`, `Read(*)`, `Glob(*)`,
`LS(*)` — no orchestration/dispatch grant. This is by design (hub-holds-Task): an inspector
inspects, it does not spawn spokes.

**Read-only is the default.** Without `--manage` the dashboard binds no mutating keys — the
live `r`/`R`/`b`/`m`/`c` action layer is not even bound, so no run/batch/config write can
happen. `--manage` is an explicit, opt-in flag; `--read-only` states the default explicitly.

The board reads every fact from the artifacts the pipeline already wrote under the pipeline
root (`.pipeline` by default). Do **not** re-derive dashboard behavior in prose beyond naming
the script — `gmj_dashboard.py` owns the projection and the key bindings.

## Invocation

```bash
python3 scripts/dashboard/gmj_dashboard.py            # read-only live board (default)
python3 scripts/dashboard/gmj_dashboard.py --manage   # opt into the r/R/b/m/c action layer
```

## Flags

- **`--pipeline-dir <dir>`** — pipeline root to project (and batch into). Default `.pipeline`.
- **`--refresh <float>`** — poll interval in seconds. Default `1.5`.
- **`--read-only`** — explicit read-only (the default; binds no mutating keys).
- **`--manage`** — bind the live mutating action keys (`r`/`R`/`b`/`m`/`c`). Opt-in only.
- **`--config <path>`** — config file the `m`/`c` knobs edit under `--manage`.

## Dependency

The dashboard requires `textual`; the pinned range lives in
`scripts/dashboard/requirements.txt`. Install with
`pip install -r scripts/dashboard/requirements.txt` before first launch.
