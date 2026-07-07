# gmj-dashboard — Testing Plan

> **Scope.** Manual UAT plan for the `gmj-dashboard` btop-style pipeline cockpit
> (`scripts/dashboard/gmj_dashboard.py`). It curates the runnable UAT steps from the
> Session 1–5 handoff in [dashboard-uat-findings.md](dashboard-uat-findings.md) into a
> repeatable checklist. This document is not scanned by the docs-currency gate
> (`tests/test_docs_current.py` covers `docs/*.md` + root `README.md` only), so every
> `gmj_*` token here is kept accurate by hand.

## Legend

| Status | Meaning |
|--------|---------|
| **PASS** | UAT step passed (no code change required) |
| **PARTIAL** | Mitigation shipped; architectural gap remains |
| **DEFERRED** | Carried as a human UAT; not executed this phase |
| **Implemented** | Behavior shipped; re-verify against the current board |

## Prerequisites

- **`textual` installed:** `pip install -r scripts/dashboard/requirements.txt`.
- **Minimum terminal height ≈ 60 rows** *(grid-derived estimate — no code constant pins it:
  the fixed `17 + 17 + 12` grid rows plus banner, status band, gutters, header, and footer).
  Below that the runs/vacancies band starves (FIND-01).*
- **Use a COPY of the pipeline dir for `--manage` UAT.** Pressing `m` / `c` under `--manage`
  writes the real `--config` (default `config/pipeline.config.yaml`); run against a copy so a
  UAT session never mutates the repo default (FIND-08).

## Canonical launch recipe

Read-only board (default — binds no mutating keys):

```bash
python3 scripts/dashboard/gmj_dashboard.py --pipeline-dir <dir>
```

Manage mode (opt into the `r`/`R`/`b`/`m`/`c` action keys — use a COPY of `<dir>`):

```bash
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir <dir>
```

## UAT traceability matrix

Curated from the Session 1–5 matrix in `dashboard-uat-findings.md` (:55–69).

| UAT step | Result | Related finding IDs |
|----------|--------|---------------------|
| Step 0 — deps / launch | PASS | — |
| Step 1 — read-only board renders (Session-5 grid, ~60-row min) | PASS (after FIND-01 fix) | FIND-01 |
| Step 2 — drill-in, filter, panel palette, read-only keys | PASS | FIND-05 |
| Step 3 — `--manage` `m` / `c` / `b` | PASS (after FIND-02 fix) | FIND-02, FIND-06, FIND-07 |
| Step 3 — `--manage` `R` / `r` launch + live heartbeat | PARTIAL | FIND-08, FIND-09, FIND-10 |
| DASH-UAT-03 — cross-terminal / SSH / tmux rendering | DEFERRED (human UAT) | — |
| DASH-UAT-04 — vacancies table + filter + drill-in | Implemented | FEATURE-12 (VIEW-17 / VIEW-18) |
| Session 2 — diagnostics tabs (7) + config browser | Implemented | FEATURE-21–25 |
| Session 3 — features panel + live heartbeat | Implemented | FEATURE-26–30, FIND-03 |
| Session 4 — heartbeat / counters / panel colors | Implemented | FEATURE-31–33 |
| Session 5 — grid layout / spacing / panel sizing | Implemented | FEATURE-34–36 |

## DASH-UAT-03 — cross-terminal / SSH / tmux rendering (deferred human UAT)

**Status: DEFERRED.** This is a v2 deferred **human** UAT (REQUIREMENTS.md:62), carried — not
executed — this phase. A human must launch the board across representative terminals and confirm
the Session-5 grid, panel colors, figlet banner (incl. `g`/`j` descenders), and the two-line
heartbeat all render without corruption:

- A local terminal (baseline).
- An SSH session (remote TERM).
- Inside a `tmux` pane (nested terminal geometry).

Confirm the ~60-row minimum holds and the diagnostics tab bar (`←` / `→` to switch panes) is
navigable in each.

## DASH-UAT-04 — vacancies drill-in (optional, matrix parity)

Open the `vacancies` panel, apply the row filter, and drill into an offer to open its detail modal
(`enter` to open, `escape` to dismiss). Implemented via FEATURE-12 (VIEW-17 / VIEW-18); included
here for matrix parity.

## Verification snippet

While a `--manage` launch (`r`/`R`/`b`) is in flight, confirm the child moved run state on disk.
The valid `gmj_runs.py` verb is **`inspect`** (there is no `show` subcommand — FIND-07 resolved):

```bash
python3 scripts/pipeline/gmj_runs.py run inspect <run_id> --pipeline-dir .pipeline
```
