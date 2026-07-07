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
root (`.pipeline` by default). `gmj_dashboard.py` owns the projection and the key bindings — it
is the source of truth. The behavior summarized below (tabs, keyboard, grid, colors, heartbeat,
counters) is transcribed from `scripts/dashboard/gmj_dashboard.py` + `gmj_dashboard.tcss` so the
operator knows what to expect; this DOCS-01 currency pass intentionally overrides the earlier
"name the script only" stance for the named elements. Keep it in sync with source, never invent.

## Invocation

```bash
python3 scripts/dashboard/gmj_dashboard.py            # read-only live board (default)
python3 scripts/dashboard/gmj_dashboard.py --manage   # opt into the r/R/b/m/c action layer
```

## Flags

- **`--pipeline-dir <dir>`** — pipeline root to project (and batch into). Default `.pipeline`.
- **`--refresh <float>`** — poll interval in seconds. Default `1.0`.
- **`--read-only`** — explicit read-only (the default; binds no mutating keys).
- **`--manage`** — bind the live mutating action keys (`r`/`R`/`b`/`m`/`c`). Opt-in only.
- **`--config <path>`** — config file the `m`/`c` knobs edit under `--manage`.

## Layout — the Session-5 grid

Single-column grid (`grid-size: 1`, `grid-rows: auto auto auto 17 17 12`). Rows, top→bottom:

1. **banner** (`auto`) — figlet wordmark + slogan.
2. **status band** (`auto`) — a `status` panel (holds the `#counters` strip) stacked over a
   `heartbit` panel (holds the heartbeat).
3. **features + configuration row** (`17`) — `features` panel beside `configuration` panel.
4. **runs + vacancies row** (`17`) — `runs` panel beside `vacancies` panel.
5. **diagnostics tabs** (`12`) — full-width tabbed diagnostics.

**Panel border-color legend** (from `gmj_dashboard.tcss`): status `#39d0d8` (cyan) ·
heartbit `#3fb950` (green) · features `#f0883e` (orange) · configuration `#58a6ff` (blue) ·
runs `#e3b341` (gold) · vacancies `#3fb950` (green).

**Minimum terminal height ≈ 60 rows** *(grid-derived estimate — no code constant pins it:
`17 + 17 + 12` fixed rows plus banner, status band, gutters, header, and footer)*. Below that
the runs/vacancies band starves.

## Diagnostics tabs

Seven panes, `initial = errors`:
**errors · debug · activity (events) · commands · metrics · pipeline stages · throughput / gates**.
Each pane body scrolls (↑/↓, PgUp/PgDn, wheel).

## Keyboard

- **Always bound:** `q` quit · `enter` drill-in (opens the focused panel's detail modal) ·
  `escape` dismiss the open modal.
- **Only under `--manage`** (the `_MANAGE_KEYS` set): `r` run · `R` resume · `b` batch ·
  `m` default-mode toggle · `c` retry cap. Without `--manage` these keys are never bound, so no
  run/batch/config write can happen.
- **Diagnostics tab bar (when focused):** `←` / `→` switch panes; `Tab` / `Shift+Tab` move focus
  through the app (they do NOT cycle tabs).

## Status band — heartbeat + counters

- **Heartbeat (two lines, shown only while a fast-poll window is active** — a background launch or
  a live-sync; hidden otherwise): line 1 is `● {task}` (the in-flight task, or `syncing`, or
  `{item} (+N more)`); line 2 is a full-width animated bar (a `░` track with marching `█` blocks).
- **Counters strip:** `label: value` segments joined by ` │ `, centered, each segment colored.
  The mode label is `default_mode` (renamed from `mode`).

## Phase-26/27/28 behavior

- **`--manage` safety gate (SAFE-02):** when `--manage` is on AND the resolved `--config` is the
  repo-default `config/pipeline.config.yaml`, a warning banner is seeded and the operator is warned
  before `m`/`c` can write that file. Run UAT against a COPY of the config/pipeline dir.
- **`--pipeline-dir` / `GMJ_PIPELINE_DIR` honoring (HON-01/02):** a launched child (`r`/`R`/`b`)
  receives the operator's pipeline root via the `GMJ_PIPELINE_DIR` child-env carrier plus a readable
  `pipeline_dir=` prompt arg. Resolution order: **explicit arg > `GMJ_PIPELINE_DIR` env > `.pipeline`**.
- **Frozen-vs-live legend (HON-03):** an in-flight overlay distinguishes frozen run-status from live
  step progress (a view-layer overlay only; it does not fork `project_status()`).
- **Feature-launch reload recovery (RELOAD-01/02):** a non-pipeline feature launch
  (collective/interview/template) writes a launch sidecar that survives dashboard exit; on reload the
  heartbeat/activity recovers those in-flight non-pipeline launches from the sidecar.

## Dependency

The dashboard requires `textual`; the pinned range lives in
`scripts/dashboard/requirements.txt`. Install with
`pip install -r scripts/dashboard/requirements.txt` before first launch.
