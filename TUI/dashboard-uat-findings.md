# gmj-dashboard — UAT Findings & Fix Milestone Handoff

> **Status:** Handoff artifact for follow-up dashboard milestones (Sessions 1–5).  
> **Sessions:** July 2026 human UAT; **July 6, 2026** layout/diagnostics refactor (§ Session 2); **July 6, 2026** features panel, live heartbeat, layout polish (§ Session 3); **July 6, 2026** visual polish — heartbeat, counters, panel colors (§ Session 4); **July 6, 2026** grid layout, spacing, panel sizing (§ Session 5).  
> **Companion docs:** [TUI/testing-plan.md](testing-plan.md), [TUI/cli-dashboard-proposal.md](cli-dashboard-proposal.md).  
> **Codebase at handoff:** uncommitted working-tree changes on `scripts/dashboard/` (incl. `gmj_dashboard_features.py`), `scripts/pipeline/gmj_runs.py`, `tests/test_gmj_dashboard*.py`, `gmj-core/` mirror (partial — manifest may be stale).

**Sessions documented**

| Session | Date | Focus |
|---------|------|--------|
| **Session 1** | July 2026 (human UAT + first fix pass) | Layout starvation, modal deadlock, manage keys, vacancies table |
| **Session 2** | July 6, 2026 (Cursor agent) | Diagnostics tab panel, config file browser, brand/counters UX — **§ Session 2** |
| **Session 3** | July 6, 2026 (Cursor agent, continued) | Features panel, live heartbeat, pipeline reload detection, layout/focus — **§ Session 3** |
| **Session 4** | July 6, 2026 (Cursor agent, polish) | Heartbeat full-width + task label, counters `label: value` colors, panel border palette — **§ Session 4** |
| **Session 5** | July 6, 2026 (Cursor agent, layout) | Single-column grid, equal spacing, titled status/heartbit, table row heights, diag panel restore — **§ Session 5** |

**Legend**

| Status | Meaning |
|--------|---------|
| **FIXED** | Implemented and covered by automated tests in this session |
| **PARTIAL** | Mitigation shipped; architectural gap remains |
| **OPEN** | Identified, not yet implemented |
| **PASS** | UAT step passed (no code change required) |
| **BY-DESIGN** | Observed behaviour matches pipeline contracts; UX/docs gap only |
| **FEATURE** | Planned enhancement; not a defect — scoped for a future milestone |

---

## Executive summary

Human verification of the `gmj-dashboard` TUI surfaced **one layout blocker**, **one critical interaction deadlock**, several **UX honesty gaps** (frozen vs default mode, status semantics, pipeline-dir mismatch), and **systematic test blind spots** (fixture-only data, collector overrides bypassing real modals, short candidate profile in tests).

This session **fixed** the layout starvation, prompt-modal deadlock, drill-in modal formatting, mode-labelling confusion, and added partial live-feedback for `R`/`r` launches (fast poll + in-flight `running` overlay). **Still open** for a dedicated milestone: threading `--pipeline-dir` into launched `claude` children, geometry tests against real `config/candidate.yaml`, and deeper status projection honesty during resume. **Planned feature** (post-UAT): vacancies `DataTable` + **row filter** + offer drill-in modal — see **FEATURE-12 (VIEW-17 / VIEW-18)**.

**Session 2 (July 6, 2026)** added: full-width **7-tab diagnostics panel** (FEATURE-21), **config YAML file browser** (FEATURE-23), figlet banner + slogan, **centered counters**, runs/vac panel layout parity, and fixes for tab labels, Tab focus trap, and modal sizing. See **§ Session 2**.

**Session 3 (July 6, 2026, continued)** added: **features panel** (replaced candidate), **live heartbeat strip**, **pipeline-on-disk activity detection** after reload, Ukrainian-flag banner colors, feature-run live tracking, **row order swap** (features/config above runs/vac), **taller tables** (~5 rows), and **no default focus** at startup (FIND-03 **FIXED**). See **§ Session 3**.

**Session 4 (July 6, 2026, polish)** refined: **heartbeat** shows the primary in-flight task on line 1 + **full-width** animated bar on line 2 (no trailing panel-name list); **counters strip** uses `label: value` with **per-segment colors**; **four main panels** get distinct border/accent colors (orange features, blue config, gold runs, green vacancies). See **§ Session 4**.

**Session 5 (July 6, 2026, layout)** fixed: **uneven vertical gaps** between panels; **empty features/configuration** rows; **missing diagnostics tabs** band; restored **figlet descenders** (`g`/`j`); **1.5× taller** table panels (17 rows each). Shipped: **single-column grid** (`grid-size: 1`), **titled `status` / `heartbit` panels**, fixed `grid-rows: auto auto auto 17 17 12`, `Horizontal` side-by-side pairs, flex `1fr` DataTables. See **§ Session 5**.

**Automated gate at handoff (Session 1):** 54 tests across `test_gmj_dashboard*.py` + `test_gmj_dashboard_actions.py`.

**Automated gate at handoff (Sessions 2–5):** 59 tests across `tests/test_gmj_dashboard.py` + `tests/test_gmj_dashboard_model.py` (plain `python3` harness). Run:

```bash
python3 -m pytest tests/test_gmj_dashboard.py tests/test_gmj_dashboard_model.py -q
```

---

## UAT traceability matrix

| UAT step | Result | Related finding IDs |
|----------|--------|---------------------|
| Step 0 — deps / launch | PASS | — |
| Step 1 — read-only board renders | PASS (after FIND-01 fix) | FIND-01 |
| Step 2 — drill-in, filter, palette, read-only keys | PASS | FIND-05 (modal layout fixed during step) |
| Step 3 — `--manage` `m`/`c`/`b` | PASS (after FIND-02 fix) | FIND-02, FIND-06, FIND-07 |
| Step 3 — `--manage` `R`/`r` | PARTIAL | FIND-08, FIND-09, FIND-10 |
| Cross-terminal (DASH-UAT-03) | Not run | — |
| Vacancies table + filter + drill-in (planned) | Implemented | **FEATURE-12 (VIEW-17 / VIEW-18)** |
| Session 2 — diagnostics tabs + config browser | Implemented | **FEATURE-21–25**, **FIX-21-01–06** — § Session 2 |
| Session 3 — features panel + live heartbeat | Implemented | **FEATURE-26–30**, **FIX-28-01–03**, **FIND-03** — § Session 3 |
| Session 4 — heartbeat / counters / panel colors | Implemented | **FEATURE-31–33**, **FIX-31-01–02** — § Session 4 |
| Session 5 — grid layout / spacing / panel sizing | Implemented | **FEATURE-34–36**, **FIX-34-01–06** — § Session 5 |

---

## FIND-01 — Runs table + vacancies row collapses to zero height

**Severity:** High (primary interactive panel unreachable)  
**Status:** **FIXED**

### Symptom

On a normal terminal (e.g. 120×40), the board showed banner, counters, metrics, DAG, filter, candidate, configuration, charts, errors, activity, commands, and debug — but **not** the runs `DataTable` or vacancies panel. User reported: “I do not see runs table.”

### Reproduce

1. Install deps: `pip install -r scripts/dashboard/requirements.txt`
2. Launch against the **real** repo (not fixture pipeline):
   ```bash
   python3 scripts/dashboard/gmj_dashboard.py
   ```
3. Use a machine where `config/candidate.yaml` has a long `summary` + large `expertise` block (the real profile in this repo).
4. Terminal height ≤ ~50 rows with default font.

**Expected (broken):** runs/vacancies band has zero visible height.  
**Expected (fixed):** runs table shows ≥8 rows of height; vacancies panel visible beside it.

### Root cause

[`scripts/dashboard/gmj_dashboard.tcss`](../scripts/dashboard/gmj_dashboard.tcss) grid:

```css
/* before fix */
grid-rows: auto auto 8 3 1fr auto 3 10 12 8;
```

- Row 5 (`1fr`) held **only** `#runs` + `#vac-placeholder` — the sole flexible row.
- Row 6 (`auto`) held `#candidate` + `#config` with `height: 100%; overflow-y: auto`.
- Real `candidate.yaml` expanded the `auto` row to dozens of lines.
- Fixed rows (metrics 8, filter 3, throughput 3, charts 10, errors/activity 12, commands/debug 8, banner/counters `auto`) consumed the viewport.
- The single `1fr` row was starved → **0px** for runs + vacancies.

### Implementation gap

- Automated headless tests use `repo_root=tests/fixtures/dashboard` (short synthetic candidate) and `size=(120, 40)` — they never exercised a long real profile.
- No assertion on `#runs` widget height or `row_count` visibility under realistic data.

### Solution applied

[`scripts/dashboard/gmj_dashboard.tcss`](../scripts/dashboard/gmj_dashboard.tcss):

```css
grid-rows: auto auto 8 3 12 10 3 10 12 8;
```

```css
#runs {
    height: 100%;
    min-height: 8;
    overflow-x: auto;
}
```

Row 5 fixed at **12** lines; candidate/config row fixed at **10** with internal scroll.

Mirrored to `gmj-core/scripts/dashboard/gmj_dashboard.tcss`; payload rebuilt via `python3 scripts/gmj_build_payload.py`.

### Test coverage

| Coverage | Status |
|----------|--------|
| Existing table row-count / cursor tests | Unchanged (fixture data) |
| Headless probe with real `config/candidate.yaml` | Manual only (session) |
| Automated min-height / geometry under long candidate | **OPEN** — see FIND-14 |

### Follow-up (milestone)

- Add `test_layout_runs_visible_with_long_candidate_profile()` — construct app with `repo_root=REPO_ROOT`, assert `#runs.size.height >= 8` after mount.
- Document minimum terminal size in `TUI/testing-plan.md` UAT prerequisites.

---

## FIND-02 — `--manage` prompt modal deadlock (`c`, `b`, and real `r`/`R` collectors)

**Severity:** Critical (manage layer unusable)  
**Status:** **FIXED**

### Symptom

After pressing `c` (retry cap) or `b` (batch), a prompt appeared with a blinking cursor but **keyboard input did nothing**; `Escape` did not dismiss. User: “cannot type anything in the input fields … cannot return back.”

### Reproduce

1. `python3 scripts/dashboard/gmj_dashboard.py --manage`
2. Focus runs table (click a row) — only needed when exercising table-specific keys; manage keys work at startup since Session 3 (FIND-03 fixed).
3. Press `c` or `b`.
4. **Broken:** modal visible, keys ignored, UI wedged until force-quit.

**Headless repro (deterministic):**

```python
# pilot.press("c") with focus on #runs, NO _prompt_cap override
# → asyncio.wait_for(..., 12) TIMEOUT — action never completes
```

Direct `await app.action_cap()` without keypress works; isolated `_PromptModal` works; **only keypress-dispatched async actions deadlock**.

### Root cause

`action_cap`, `action_batch`, `action_run`, `action_resume` are `async def` handlers that:

```python
self.push_screen(_PromptModal(...))
return await future  # blocks the action coroutine on the message pump
```

When Textual dispatches a binding, it **awaits the action on the message-processing path**. The pump cannot deliver keystrokes to the modal `Input` while blocked → classic modal deadlock.

### Implementation gap

All `--manage` tests **override** collectors:

```python
app._prompt_cap = lambda: _aval(7)
app._prompt_batch = lambda: _aval(("shortlist.json", "1,3"))
app._prompt_offer = lambda: _aval("https://...")
```

The real `_ask` → `_PromptModal` path **never ran under a keypress** in CI.

### Solution applied

[`scripts/dashboard/gmj_dashboard.py`](../scripts/dashboard/gmj_dashboard.py) — decorate prompt-driven actions with Textual `@work`:

- `action_cap`
- `action_batch`
- `action_run`
- `action_resume`

Modal/`_ask` unchanged; workers run off the pump.

New regression test: `test_manage_prompt_modal_is_interactive_under_keypress` — presses `c` with **no** override, types `42`, submits, asserts config write; bounded by 20s timeout.

### Test coverage

| Test | Covers |
|------|--------|
| `test_manage_prompt_modal_is_interactive_under_keypress` | Real modal + keypress + Enter |
| `test_manage_config_edit` | `m`/`c` with overrides (not modal path) |
| `test_manage_batch_action` | `b` with override |
| `test_manage_binds_real_actions` | `r`/`R` with overrides |

**Gap:** no headless test for `b` with real two-step modal sequence (OPEN).

### Follow-up (milestone)

- `test_manage_batch_modal_two_step_under_keypress` — real `_prompt_batch`, Escape on step 2 cancels cleanly.

---

## FIND-03 — Filter input steals manage keybindings on startup

**Severity:** Medium (foot-gun; workaround existed)  
**Status:** **FIXED** (Session 3 — inverted approach)

### Original symptom (Session 1)

Pressing `m`, `c`, `b`, `r`, or `R` typed into the **filter** bar instead of firing the action — unless the user first clicked the runs table.

### Root cause

Textual auto-focused the first focusable widget — the `#filter` `Input` in `#runs-panel`.

### Session 1 proposed fix (superseded)

Focus `#runs` on mount — **not** what UAT wanted in Session 3.

### Session 3 fix (shipped)

- `GmjDashboard.AUTO_FOCUS = ""` — disable Textual auto-focus.
- `_clear_startup_focus()` called via `call_after_refresh` after first paint → `set_focus(None)`.
- **No panel or filter focused at startup** — user clicks a panel or presses Tab to focus.
- Manage keys (`r`/`R`/`b`/`m`/`c`) work immediately when nothing has focus; filter inputs only steal keys after clicked.

### Test

- `test_startup_has_no_default_focus` — asserts `app.focused` is `None` after mount.

### Test coverage

| Test | Status |
|------|--------|
| `test_startup_has_no_default_focus` | **Present** — asserts `app.focused is None` after mount |
| Manage-key tests that call `#runs`.focus() | Still valid when exercising table-specific flows |

### Files touched

- `scripts/dashboard/gmj_dashboard.py` — `AUTO_FOCUS = ""`, `_clear_startup_focus()`
- `tests/test_gmj_dashboard.py` — `test_startup_has_no_default_focus`

---

## FIND-04 — Drill-in modal: all fields on one line

**Severity:** Low (readability)  
**Status:** **FIXED**

### Symptom

Run detail modal (Enter on a row) showed:

```
status running   mode human_in_the_loop   A:pass B:fail
offer_spec_hash bbbb...
```

User requested one property per line, bold labels, colored status.

### Reproduce

1. Read-only dashboard with any runs.
2. Select row → Enter.
3. Observe cramped single-line status/mode/gates.

### Root cause

`RunDetailModal.compose()` built a single f-string line for status/mode/gates.

### Solution applied

`RunDetailModal` now renders Rich `Text` in `on_mount()`:

- Bold `label:` prefix per field
- `status`, `gate_a`, `gate_b` colored via `self.app.get_css_variables()` (`status-*`, `gate-*` theme keys)
- Fields: `run_id`, `status`, `mode (frozen)`, `gate_a`, `gate_b`, `current_step`, `retry_cap (frozen)`, `offer_spec_hash`, `offer_spec_path`, `attempts`, `artifacts`, `Resume`

### Test coverage

| Test | Status |
|------|--------|
| `test_drill_in_modal_open_and_resume_printed_not_run` | Asserts content substrings still present |
| Per-line layout / bold labels | **NOT asserted** — add snapshot or `"\nstatus:" in body` check |

---

## FIND-05 — `m` (mode toggle) appears to do nothing in runs table / modal

**Severity:** Medium (UX honesty)  
**Status:** **PARTIAL** (labelling + immediate poll); **BY-DESIGN** for per-run column

### Symptom

Press `m` → toast `✓ execution_mode → autonomous`, but runs table `mode` column and drill-in modal `mode` unchanged.

### Reproduce

1. `python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir .pipeline`
2. Note `configuration` panel `mode: human_in_the_loop`.
3. Press `m` → toast success.
4. Runs table `mode` column still shows per-run frozen values (e.g. `human_in_the_loop` on old runs).
5. Enter drill-in → `mode` still frozen value.

### Root cause

Two different concepts conflated in the UI:

| Concept | Source | What `m` changes |
|---------|--------|------------------|
| **Default mode** | `config/pipeline.config.yaml` | **Yes** — `toggle_execution_mode()` |
| **Per-run mode** | `.pipeline/runs/<id>/state.json` frozen at `init_run` | **No** — immutable for in-flight/historical runs |

Architecture: [`.claude/agents/gmj-orchestrator.md`](../.claude/agents/gmj-orchestrator.md) § init_run — `execution_mode` frozen into run state.

### Solution applied

- Config panel: `mode` → **`default_mode`**
- Counters strip: `mode` → **`default_mode`**
- Runs column header: `mode` → **`run_mode`**
- Modal label: **`mode (frozen)`**
- Toast: **`✓ default_mode → {value} (existing runs unchanged)`**
- `action_mode` / `action_cap` call `_poll()` immediately after write

### Test coverage

| Test | Status |
|------|--------|
| `test_manage_config_edit` | File + toast assertions (updated toast string) |
| `test_header_and_counters_render` | `default_mode` label |
| User education in commands panel | **OPEN** — one-line hint under `m` row |

### Follow-up (milestone)

- Add to `commands` panel static text: `m = default for NEW runs only`
- Optional: show `default_mode` in drill-in modal footer from `snapshot()["config"]` for contrast

---

## FIND-06 — `R` / `r` launch works but runs table `status` appears stuck

**Severity:** Medium  
**Status:** **PARTIAL**

### Symptom

Press `R` → toast `▸ resuming …`, `pgrep` shows real `claude` child, disk `state.json` may update — but runs table **`status`** column does not visibly change.

### Reproduce

**Case A — fixture display / real writes mismatch:**

1. `python3 scripts/dashboard/gmj_dashboard.py --manage` (default reads `.pipeline` OR user views fixture-like runs from copied fixture dir).
2. Select fixture run_id `20260604T120000-pend` → `R`.
3. Toast appears; `pgrep` shows resume for that id.
4. Table row unchanged — fixture run does not exist under `.pipeline/runs/`.

Verified: `.pipeline/runs/20260604T120000-pend` **does not exist**; child works on `.pipeline` only.

**Case B — status already `running`:**

1. `--pipeline-dir .pipeline`, select `20260706T105643-bee63e000000` (already `running`).
2. Press `R`.
3. Status stays `running` — **expected**; watch **`step`** and **`A`/`B`** columns.

**Case C — resume `failed` run:**

1. Select run with `project_status == failed` (retry cap exhausted).
2. Press `R` — work starts but status stays `failed` until `state.json` gate/retry fields change.

### Root cause(s)

1. **Display vs write path:** `build_pipeline_prompt()` / `launch_pipeline()` do not pass dashboard `--pipeline-dir`. Child `claude` hub hardcodes `.pipeline` in Bash per orchestrator docs. Dashboard `--pipeline-dir` affects **read model only** (except `b` batch which threads `pipeline_dir` correctly).

2. **Status projection semantics:** `gmj_runs.project_status()` is first-match on **frozen gate state**, not “is claude alive”:
   - `delivered` if Gate A ∧ B pass
   - `failed` if retry cap hit
   - `pending` if fresh signature
   - else `running`

   Resuming a terminal-state run does not flip status until disk state changes.

3. **Poll cadence:** 1.5s default refresh — step/gate updates feel laggy.

### Solution applied (partial)

[`scripts/dashboard/gmj_dashboard.py`](../scripts/dashboard/gmj_dashboard.py):

- `_track_launch(proc, run_id=...)` — holds child ref, starts **0.4s fast poll** while alive
- `_table_status()` — while resume child alive for that `run_id`, show theme-derived **in-flight** status (amber `running`) even if projection still `failed`/`delivered`
- Toast: `▸ resuming {id} (autonomous) — watch step/gates; fast refresh while active`
- Background `asyncio.create_task(_watch_launch)` — ends fast poll when child exits

**Not fixed:** pipeline-dir in child prompt; projection semantics; `r` fresh run has no `run_id` overlay until row appears.

### Test coverage

| Test | Status |
|------|--------|
| `test_manage_binds_real_actions` | Launch argv only |
| Fast poll / `_table_status` overlay | **MISSING** |
| Integration: resume updates `step` in table within N polls | **MISSING** |

### Proposed solutions (milestone)

**P1 — Thread pipeline dir into launch (HIGH)**

Extend `build_pipeline_prompt()`:

```python
# if dashboard --pipeline-dir != ".pipeline"
parts.append(f"pipeline_dir={pipeline_dir}")
```

Requires orchestrator + `gmj-pipeline-run` slash command + hub Bash templates to honour `pipeline_dir=` **or** set `env["GMJ_PIPELINE_DIR"]` read by all `gmj_*.py` scripts (larger change).

**P2 — Honest status semantics (MEDIUM)**

Options:

- Add `active` / `resuming` to projection when `state.json` mtime changes within last N seconds — **model change**, not view-only.
- Keep view overlay but add `†` suffix + legend in commands panel.
- Teach users to watch **`step`** column (docs).

**P3 — Activity panel streams launch events (LOW)**

On `_track_launch`, inject a synthetic activity row: `resumed <run_id> (dashboard launch)` before next disk poll.

### Verification commands (UAT)

```bash
# Confirm child
pgrep -fl "gmj-pipeline-run"

# Confirm disk movement (correct subcommand: inspect, not show)
python3 scripts/pipeline/gmj_runs.py run inspect <run_id> --pipeline-dir .pipeline

watch -n 1 'stat -f "%Sm" -t "%H:%M:%S" .pipeline/runs/<run_id>/state.json'
```

---

## FIND-07 — `gmj_runs.py run show` documentation typo

**Severity:** Trivial  
**Status:** **RESOLVED** (docs only — Phase 30, DOCS-03)

### Symptom

UAT verification snippet used `gmj_runs.py run show` → error: valid verb is **`inspect`**.
*(This heading and symptom preserve the original typo verbatim as the audit record; the strings
above are the documented bug, not live commands.)*

### Resolution

The valid `gmj_runs.py` verb is **`inspect`** (confirmed in the argparse — there is no `show`
subparser). The corrected form is now the canonical one used in the new
[TUI/testing-plan.md](testing-plan.md) verification snippet and in any UAT script:

```bash
python3 scripts/pipeline/gmj_runs.py run inspect <run_id> [--pipeline-dir .pipeline]
```

No live stale verb remains in `docs/`, `.claude/commands/`, or `TUI/testing-plan.md`.

---

## FIND-08 — UAT mutates real `config/pipeline.config.yaml`

**Severity:** Low (operator surprise)  
**Status:** **OPEN**

### Symptom

Pressing `m` / `c` in `--manage` writes the **real** `config/pipeline.config.yaml` (default `--config`). Session left repo at `execution_mode: autonomous`, `retry_cap: 4/9`.

### Reproduce

1. `python3 scripts/dashboard/gmj_dashboard.py --manage`
2. Press `m`, `c` repeatedly.
3. `git diff config/pipeline.config.yaml`

### Root cause

By design — `action_mode` / `action_cap` target `DEFAULT_CONFIG`. Tests use temp config copies; humans often do not.

### Proposed solutions

| Option | Effort |
|--------|--------|
| Document in UAT: use `--config /tmp/pipeline.config.yaml` copy | Low |
| `gmj-dashboard` warns on startup when `--manage` and config path is repo default | Low |
| Batch-like temp config for UAT in testing-plan fixture script | Medium |

---

## FIND-09 — Automated tests use short fixture profile; miss layout + modal paths

**Severity:** Medium (process gap)  
**Status:** **PARTIAL**

### Gaps identified

| Gap | Session impact |
|-----|----------------|
| `repo_root=tests/fixtures/dashboard` — short candidate | FIND-01 invisible in CI |
| `_prompt_*` overrides in all manage tests | FIND-02 shipped undetected |
| Headless `size=(120,40)` only | Layout edge cases |
| No test with `--pipeline-dir .pipeline` integration | FIND-06 mismatch undetected |

### Proposed test additions (milestone backlog)

1. `test_layout_runs_visible_with_real_candidate` — `repo_root=REPO_ROOT`, assert `#runs` height.
2. `test_manage_batch_modal_two_step_under_keypress` — real modals.
3. `test_resume_shows_inflight_running_overlay` — mock proc with `returncode=None`, assert status cell style.
4. ~~`test_default_focus_is_runs_table`~~ — superseded by `test_startup_has_no_default_focus` (Session 3).
5. Optional nightly: `--pipeline-dir .pipeline` smoke with temp run dir copy.

---

## FIND-10 — Step 2 read-only interactions (PASS)

**Status:** **PASS** (no further code required)

Verified via screenshots + session:

| Check | Result |
|-------|--------|
| Enter → drill-in modal | PASS |
| Filter substring narrows table | PASS |
| Read-only: mutating keys documented as gated | PASS |
| `^p` palette / footer | PASS |
| Poll under modal (no TooManyMatches) | PASS (existing test) |

---

## FIND-11 — Step 3 manage: `c` and `b` after deadlock fix (PASS)

**Status:** **PASS** (after FIND-02)

User confirmed: “focus works as expected and I can use b and c commands.”

| Check | Result |
|-------|--------|
| `c` → modal → integer → config write | PASS |
| `b` → shortlist + select → batch manifest | PASS (when using isolated `--pipeline-dir`) |
| `m` → default_mode toggle | PASS (with FIND-05 labelling) |

---

## FEATURE-12 (VIEW-17 / VIEW-18) — Vacancies table, filter, and offer drill-in modal

**Type:** Feature enhancement (not a UAT defect)  
**Severity:** Medium (operator ergonomics)  
**Status:** **FEATURE** — **IMPLEMENTED** (VIEW-17 table + drill-in, VIEW-18 filter)  
**View IDs:** VIEW-17 (table + drill-in), VIEW-18 (vacancies row filter — parity with VIEW-11 runs filter)

### Request / intent

Show frozen vacancies in the **vacancies** panel similarly to the **runs** table:

1. A selectable `DataTable` listing all found (frozen) offers.
2. A **filter field** above the vacancies table (same UX as the runs `#filter` input) to narrow rows by substring.
3. A **detail popup** when the user chooses a row (Enter), mirroring the run drill-in modal (VIEW-09).

Raised during UAT review: the current vacancies band is a static, single-line-per-offer text list with no filter, no selection, and no full offer inspection.

### Current behaviour (baseline)

| Area | Today |
|------|--------|
| Widget | `#vac-placeholder` — `Static` text |
| Data source | `DashboardModel._vacancies()` globs `sources/offers/*.offer-spec.json` |
| List fields | `title`, `company`, `location`, `seniority`, `salary_range`, `n_must_haves`, `offer_spec_hash` |
| Interaction | None — no row cursor, no drill-in, **no filter** |
| Batch rollup | Appended below offer lines in the same `Static` (`batches:` section) |
| Detail accessor | **None** — no `offer_detail()` (unlike `run_detail(run_id)`) |

List rendering lives in `_apply_vacancies()` ([`scripts/dashboard/gmj_dashboard.py`](../scripts/dashboard/gmj_dashboard.py)); thin reader in [`scripts/dashboard/gmj_dashboard_model.py`](../scripts/dashboard/gmj_dashboard_model.py) `_vacancies()`.

**Data boundary:** the panel shows **frozen** offer-specs on disk only (`sources/offers/*.offer-spec.json`). It does **not** show live in-flight scout/web results until an offer is frozen (scout → freeze) or a spec file is placed manually. This matches VIEW-10 and [TUI/cli-dashboard-proposal.md](cli-dashboard-proposal.md) § panels.

### Reproduce (current limitation)

1. `python3 scripts/dashboard/gmj_dashboard.py --pipeline-dir .pipeline`
2. Ensure `sources/offers/*.offer-spec.json` exists (fixture: `tests/fixtures/dashboard/sources/offers/`).
3. Observe the right-hand vacancies panel: prose lines like  
   `Backend Engineer · TestCorp · senior · 4000-6000 USD · mh 3`
4. Try to select a row or open details → **not possible** (no table, no modal).
5. Note: the **runs** table already has a full-width `#filter` input (VIEW-11); vacancies have **no equivalent**.

### Root cause (why it is limited today)

Phase 22 (VIEW-10) deliberately shipped a **minimal read-only rollup**: one formatted line per frozen offer + batch summary, filling the placeholder frame reserved in Phase 21. Interactive parity with the runs table (filter, `DataTable`, drill-in) was deferred; VIEW-11 was scoped to runs only. The original proposal ASCII layout ([cli-dashboard-proposal.md](cli-dashboard-proposal.md) §6) showed vacancies as a short list, not a full interactive panel.

### Proposed solution

Mirror the runs-table pattern end-to-end.

#### 1. Model — on-demand `offer_detail(offer_spec_hash)`

Add to [`gmj_dashboard_model.py`](../scripts/dashboard/gmj_dashboard_model.py):

```python
def offer_detail(self, offer_spec_hash: str) -> dict:
    """Return a drill-in payload for one frozen offer-spec, else {}."""
```

- Lookup by `offer_spec_hash` against the same `sources/offers/*.offer-spec.json` glob used by `_vacancies()` (do **not** follow `state.offer_spec_path` from run state — T-20-02 / T-22-07).
- Whitelist modal fields from `content` + envelope:
  - `title`, `company`, `location`, `seniority`, `employment_type`, `language`
  - `salary_range` (verbatim dict or null)
  - `must_haves`, `nice_to_haves`, `responsibilities` (lists)
  - `source_url`, `raw_text_excerpt` (display only — **never** fetched/opened by dashboard)
  - `offer_spec_hash`, `captured_at`
  - `spec_basename` — filename only (e.g. `alpha-backend-engineer.offer-spec.json`) for operator reference
- Keep `snapshot()["vacancies"]` thin; load full detail only on drill-in (same perf pattern as `run_detail`).

Optional cross-link (phase 2): scan `.pipeline/runs/*/state.json` for matching `offer_spec_hash` and include `linked_runs: [{run_id, status, …}]` in the modal.

#### 2. View — vacancies panel stack (`#vac-filter` + `DataTable` + batches)

Replace `#vac-placeholder` with a **vertical stack** inside the right-hand grid cell (row 5):

```
┌─ vacancies (border_title) ─────────────┐
│  #vac-filter  Input  (height 3)        │  ← VIEW-18 (new)
│  #vacancies   DataTable (flex/scroll)  │  ← VIEW-17
│  #vac-batches Static  (auto, optional) │  ← batch rollup footer
└────────────────────────────────────────┘
```

Implementation: wrap in a `Vertical` container (`id="vac-panel"`) or use a nested grid; the outer dashboard grid cell stays one column of row 5.

**Table columns**

| Column label | Row key / field |
|--------------|-----------------|
| title | `title` |
| company | `company` |
| seniority | `seniority` |
| salary | formatted `salary_range` |
| mh | `n_must_haves` |

- Widget id: `#vacancies` (`DataTable`, `cursor_type="row"`).
- Row key: `offer_spec_hash` (stable, unique).
- `_apply_vacancies()` diffs rows like `_apply_runs()` — targeted `update_cell` / `add_row` / `remove_row`, never `clear()` + refill.
- **Batch rollup:** `#vac-batches` `Static` below the table inside the same panel frame — do not drop batch visibility.

#### 3. View — vacancies row filter (VIEW-18, parity with VIEW-11)

Mirror the runs filter contract exactly — **view-only predicate, no new data source**:

| Runs (existing) | Vacancies (proposed) |
|-----------------|----------------------|
| `#filter` Input, full-width row 4 | `#vac-filter` Input, top of vacancies panel |
| `self._filter` | `self._vac_filter` |
| `_match(r)` on `run_id` \|\| `status` | `_vac_match(v)` on projected fields |
| `on_input_changed` → re-apply from `_last_snap` | same handler branch for `event.input.id == "vac-filter"` |
| `_apply_runs` skips non-matching rows every poll (Pitfall 4) | `_apply_vacancies` skips non-matching rows every poll |

**Placeholder text:**

```text
filter vacancies (title / company / seniority substring)…
```

**`_vac_match(v)` predicate** (all comparisons lowercased; `f` = `self._vac_filter`):

- Empty filter → keep all rows.
- Else keep row if `f` is a substring of **any** of:
  - `v["title"]`
  - `v["company"]`
  - `v["seniority"]`
  - `v.get("location")` (if present in list projection — add to thin reader if missing)
  - `v["offer_spec_hash"]` (prefix search for operator paste)

Do **not** match on `raw_text_excerpt` in the list path (not in thin projection); drill-in shows full text.

**Focus / manage keys (FIND-03 — fixed Session 3):**

- **No default focus** at startup — manage keys work immediately; click a filter/table to type.
- When `#filter` or `#vac-filter` is focused, single-letter manage keys (`m`, `c`, …) type into the filter — same foot-gun as before, but only after the user focuses that input.
- When `#features-filter` is focused, same rule applies.

#### 4. Interaction — `VacancyDetailModal`

Copy VIEW-09 (`RunDetailModal`):

- `on_data_table_row_selected` on `#vacancies` when table focused → `open_offer_detail(hash)`.
- `VacancyDetailModal(offer_detail)` — frozen payload at open; one labeled field per line; bold labels (same Rich `Text` pattern as the fixed run modal).
- `Escape` → `action_dismiss`.
- Namespaced ids: `#vac-modal-body` (never collide with `#modal-body` on run modal).
- Read-only: `source_url` and resume/run commands are **displayed, never executed** (SAFETY-02).

Optional `--manage` enhancement (separate sub-task):

- Modal footer hint or key: launch pipeline for this offer → `build_pipeline_prompt(offer=source_url)` (reuses existing `action_run` / launcher seam).

#### 5. Layout & CSS

Vacancies share **grid row 5** with the runs table ([`gmj_dashboard.tcss`](../scripts/dashboard/gmj_dashboard.tcss) — fixed height 12). The panel stack fits the existing frame with internal scroll.

```css
#vac-panel {
    height: 100%;
    layout: vertical;
}

#vac-filter {
    height: 3;
    border: round #3fb950;
    background: #0d1117;
    color: #c9d1d9;
}

#vacancies {
    height: 1fr;
    min-height: 4;
    border: round #3fb950;
    overflow-x: auto;
}

#vac-batches {
    height: auto;
    max-height: 4;
    overflow-y: auto;
}
```

The vacancies filter lives **inside the right column** (not full-width like runs `#filter`), so runs and vacancies can be filtered independently.

### Architecture constraints (must respect)

| Rule | Implication |
|------|-------------|
| SAFETY-02 | View/model stay read-only; scout/freeze only via `--manage` + `gmj_dashboard_actions` |
| T-20-02 | Detail loaded from offers **glob**, not from run `offer_spec_path` |
| Projection invariant | No fit scoring or gate verdicts re-derived in vacancies panel |
| Phase-20 grep-guard | No bare status literals in `.py`; use theme vars for any colored badges |
| Pitfall 3 (modal ids) | `#vac-modal-*` namespace; poll must not `query_one` collide across stacked screens |
| Pitfall 4 (filter + poll) | Vacancies filter applied inside `_apply_vacancies` every tick — poll must not resurrect filtered-out rows |

### Implementation gaps (why not done in UAT session)

| Gap | Notes |
|-----|-------|
| VIEW-10 shipped static list only | Sufficient for Phase 22 acceptance |
| No `offer_detail` accessor | Model stops at thin `_vacancies()` projection |
| No Pilot test for vacancy selection | Only `test_probe_vacancies_panel` asserts substring in `Static` text |
| Proposal ASCII showed short list | Feature request extends proposal without breaking invariants |

### Test coverage plan

| Test | Asserts |
|------|---------|
| `test_vacancies_table_rows` (model + view) | `DataTable.row_count == len(snapshot["vacancies"])` |
| `test_offer_detail_reader` (model) | Full fields from `alpha-backend-engineer.offer-spec.json` fixture |
| `test_offer_detail_modal_open` (view) | Enter on focused row → `VacancyDetailModal`; `must_haves` visible |
| `test_offer_detail_unknown_hash` | Missing hash → graceful empty modal body |
| `test_vacancies_filter_narrows_table` (view) | Type into `#vac-filter` → `row_count` drops; clear filter → all rows return; poll does not resurrect filtered rows |
| `test_vacancy_modal_poll_safe` | Poll ticks under modal do not raise `TooManyMatches` (Pitfall 3) |
| `test_vacancy_source_url_printed_not_run` | `source_url` present in body; AST still has no subprocess in view |

Update [TUI/testing-plan.md](testing-plan.md) UAT matrix with **DASH-UAT-04** — vacancies table drill-in (human: verify must-haves readable, Escape closes).

### Files to touch (estimate)

| File | Change |
|------|--------|
| `scripts/dashboard/gmj_dashboard_model.py` | `offer_detail()`; optional `spec_basename` in list rows |
| `scripts/dashboard/gmj_dashboard.py` | `#vac-panel` stack; `#vac-filter` + `#vacancies` `DataTable`; `_vac_filter` / `_vac_match`; `_apply_vacancies` diff; `VacancyDetailModal`; row handler |
| `scripts/dashboard/gmj_dashboard.tcss` | `#vac-panel`, `#vac-filter`, `#vacancies`, `#vac-batches` styles |
| `tests/test_gmj_dashboard_model.py` | `test_offer_detail_reader` |
| `tests/test_gmj_dashboard.py` | Modal + table Pilot tests |
| `gmj-core/scripts/dashboard/*` | Mirror via `gmj_build_payload.py` |
| `TUI/cli-dashboard-proposal.md` | Optional: update §6 ASCII + panel list to mention table + drill-in |
| `docs/cli-tools.md` | Note VIEW-17 if user-facing behaviour changes |

**Rough effort:** ~½–1 day (VIEW-09 drill-in + VIEW-11 filter parity + nested panel layout).

### Acceptance criteria

1. All frozen offers under `sources/offers/*.offer-spec.json` appear as rows in `#vacancies`.
2. `#vac-filter` narrows visible rows by substring (title / company / seniority / location / hash); clearing the filter restores all rows; polling does not resurrect filtered-out rows.
3. Arrow keys move row cursor on `#vacancies`; **Enter** opens `VacancyDetailModal` with full whitelisted fields.
4. **Escape** closes modal; base board keeps polling without error.
5. Batch rollup still visible when batches exist.
6. Read-only mode: no disk writes, no subprocess, no URL fetch from modal.
7. Automated tests above pass; grep-guard and SAFETY-02 AST tests stay green.

---

## FEATURE-13 (VIEW-19) — Configuration table + select/edit

**Type:** Feature enhancement  
**Status:** **SUPERSEDED** by **FEATURE-23 (VIEW-19 v2)** — Session 2 replaced knob-summary rows with a `config/**/*.yaml` file browser. `m` / `c` manage keys still work globally; **Enter on config row no longer edits** — it opens read-only file content.

### Original behaviour (Session 1 — no longer current)

| Mode | Interaction |
|------|-------------|
| Read-only | `#config-table` lists governing knobs; **Enter** on a row opens `ConfigDetailModal` (value, source file, help) |
| `--manage` | Rows `default_mode *` and `retry_cap *` are editable — **Enter** toggles mode or prompts for cap (same as `m` / `c`) |

Rows: `boards`, `cities`, `languages`, `default_mode`, `retry_cap`, `fit.coverage_threshold`. Only pipeline knobs use the existing `gmj_dashboard_actions` write path; sources/fit rows are drill-in only (edit source YAML).

### Tests (Session 1 — removed/replaced in Session 2)

- ~~`test_config_table_edit_row_under_manage`~~ — removed (Enter no longer triggers cap edit on table row)
- `test_config_table_drill_in` — updated for file-path rows + `ConfigFileModal` YAML body

---

## FEATURE-20 (VIEW-20) — Live refresh + foldable diagnostics panels

**Status:** **PARTIAL** — live refresh **IMPLEMENTED**; **Collapsible fold UI SUPERSEDED** by **FEATURE-21 (VIEW-21)** tabbed panel (Session 2)

### Live refresh (errors · activity · debug)

After **`r` / `R` / `b`** under `--manage`, the board enters a **fast-poll window** (~0.4s) for up to 90–120s (extends while the launched child lives, +60s after exit) so `errors`, `activity (events)`, and `debug` mirror on-disk pipeline writes without waiting for the 1.5s idle interval.

- **`R` (resume):** auto-selects the resumed run in **debug**
- **`r` (fresh run):** tracks the newest run in **debug** for ~2 min
- **`b` (batch):** immediate poll + 45s fast refresh (was missing before)
- **Activity** panel auto-expands on kick

### Foldable panels (Collapsible) — superseded

~~`errors`, `activity (events)`, and `debug` are **Textual `Collapsible` spoilers**~~ — replaced by a single full-width **`TabbedContent`** bar (FEATURE-21). `_kick_live_refresh()` still switches active tab to `pane-activity` after manage launches.

---

## Files changed in Session 1 (for milestone cherry-pick)

| File | Changes |
|------|---------|
| `scripts/dashboard/gmj_dashboard.tcss` | Fixed grid rows; `#runs` min-height |
| `scripts/dashboard/gmj_dashboard.py` | `@work` on manage actions; modal layout; default_mode labels; `_track_launch` / fast poll; `_table_status` overlay |
| `tests/test_gmj_dashboard.py` | `test_manage_prompt_modal_is_interactive_under_keypress`; toast/counter label updates |
| `gmj-core/scripts/dashboard/*` | Mirrored via `gmj_build_payload.py` |
| `gmj-core/gmj-file-manifest.json` | Rehashed |

**Not committed** at Session 1 handoff — milestone session should commit with message summarising UAT fixes.

---

## Session 2 — Layout consolidation, diagnostics tabs, config browser (July 6, 2026)

> **Audience:** Next AI agent or human continuing dashboard UX work.  
> **Agent transcript:** [`075cbecc-46a8-4f27-b0c7-a88b5f2d6d0b.jsonl`](/Users/Ievgen_Kyvgyla/.cursor/projects/Users-Ievgen-Kyvgyla-tmp-give-me-job/agent-transcripts/075cbecc-46a8-4f27-b0c7-a88b5f2d6d0b/075cbecc-46a8-4f27-b0c7-a88b5f2d6d0b.jsonl) — search for keywords (`VIEW-21`, `TabbedContent`, `ConfigFileModal`, `focus trap`, etc.) rather than reading linearly.  
> **Primary files:** `scripts/dashboard/gmj_dashboard.py`, `gmj_dashboard.tcss`, `gmj_dashboard_model.py`, `tests/test_gmj_dashboard.py`, `tests/test_gmj_dashboard_model.py`, mirrored copies under `gmj-core/scripts/dashboard/`.

### Session 2 executive summary

Human UAT screenshots drove a **major layout refactor**: standalone metrics, pipeline stages, charts, errors, activity, commands, and debug panels were **consolidated into one full-width tabbed diagnostics band** (`#diag-tabs-panel`). The configuration panel became a **scrollable `config/**/*.yaml` file list** with a **wide, centered, scrollable read-only modal**. Brand banner restored as **colorful ASCII figlet** with slogan **“Your career's wingman”**. Counters strip **centered** with **` │ `** delimiters.

Several **implementation bugs** were hit and fixed: invisible tab labels (global `Static` border on `Tab`), Tab focus trap, modal width collapse (`Screen { layout: grid }` inherited by `ModalScreen`), TCSS parser break on `*/` inside comments.

### Session 2 traceability matrix

| ID | Type | Status | Summary |
|----|------|--------|---------|
| **FEATURE-21** | Feature | **IMPLEMENTED** | Full-width `TabbedContent` diagnostics: 7 tabs |
| **FEATURE-22** | Feature | **IMPLEMENTED** | Runs/vacancies panel parity — filter inside titled `Vertical` frame |
| **FEATURE-23** | Feature | **IMPLEMENTED** | Config `config/**/*.yaml` browser + `ConfigFileModal` |
| **FEATURE-24** | Feature | **IMPLEMENTED** | Colorful ASCII figlet banner + slogan |
| **FEATURE-25** | UX | **IMPLEMENTED** | Counters strip centered + ` │ ` delimiter |
| **FIX-21-01** | Bug | **FIXED** | Tab titles invisible (empty bordered boxes) |
| **FIX-21-02** | Bug | **FIXED** | Tab / Shift+Tab trapped focus inside tab bar |
| **FIX-21-03** | Bug | **FIXED** | Config modal narrow / top-left (grid layout on modal) |
| **FIX-21-04** | Bug | **FIXED** | TCSS `TokenError` from `*/` in comment |
| **FIX-21-05** | Test | **FIXED** | `test_manage_config_edit` used live repo config — isolated seed YAML |
| **FIX-21-06** | Test | **FIXED** | AST guard tripped on `str.replace` in model — use `Path.as_posix()` |

### FEATURE-21 (VIEW-21) — Tabbed diagnostics panel

**Status:** **IMPLEMENTED**

#### Tab order (left → right)

1. `errors` — failed-run gate detail (`#errors`)
2. `debug` — selected run internals (`#debug`)
3. `activity (events)` — event timeline (`#activity`)
4. `commands` — keybinding reference (`#commands`)
5. `metrics` — status bars + gate tallies + sparkline (`#metrics`, `#throughput`)
6. `pipeline stages` — DAG strip (`#dag-placeholder`)
7. `throughput / gates` — block charts (`#charts`)

#### Widget tree (compose)

```python
with TabbedContent(id="diag-tabs-panel", initial="pane-errors"):
    with TabPane("errors", id="pane-errors"):
        with VerticalScroll():
            yield Static("", id="errors")
    # ... same pattern per tab; metrics tab wraps Static + Sparkline in Vertical
```

#### Constants (`gmj_dashboard.py`)

- Pane ids: `pane-errors`, `pane-debug`, `pane-activity`, `pane-commands`, `pane-metrics`, `pane-stages`, `pane-charts`
- Tab color classes seeded in `_seed_widgets()`: `diag-tab-errors`, `diag-tab-debug`, `diag-tab-activity`, `diag-tab-commands`, `diag-tab-metrics`, `diag-tab-stages`, `diag-tab-charts`

#### Keyboard / mouse

| Action | Behaviour |
|--------|-----------|
| Click tab | Switch pane (Textual default) |
| Tab bar focused + **← / →** | Switch pane (Textual `ContentTabs` bindings) |
| **Tab / Shift+Tab** | Move focus through **whole app** (do **not** cycle tabs — FIX-21-02 removed custom trap) |
| Pane body | **VerticalScroll** — ↑/↓, PgUp/PgDn, mouse wheel when scroll area focused |

#### Grid layout (`gmj_dashboard.tcss`) — superseded by Session 5 (FEATURE-34)

Session 2 layout:

```css
grid-rows: auto auto 10 10 12;
/* banner | counters | runs+vac | candidate+config | diag-tabs (full width) */
```

Session 3 layout (superseded):

```css
grid-rows: auto auto auto 15 15 12;
grid-size: 2;
/* banner | counters | heartbeat | features+config | runs+vac | diag-tabs */
#diag-tabs-panel { column-span: 2; ... }
```

Session 5 layout (**current**):

```css
Screen {
    layout: grid;
    grid-size: 1;           /* full-width rows — avoids column-span auto-height bug */
    grid-gutter: 1;         /* uniform 1-row gaps (vertical + horizontal) */
    grid-rows: auto auto auto 17 17 12;
}
/* banner | status-band (status + heartbit) | features|config | runs|vac | diag-tabs */
```

- `#status-band` — `Vertical` stacking `#status-panel` (counters, `border_title: status`) + optional `#heartbit-panel` (`border_title: heartbit`) with internal `.panel-v-gap` (1 row) when active.
- `#features-config-row` / `#runs-vac-row` — `Horizontal` containers (`width: 1fr` children); **fixed height 17** each (Session 5: 1.5× prior 11-row band).
- `#diag-tabs-panel` — **fixed height 12** (`min-height` / `max-height` 12).
- DataTables (`#features-table`, `#config-table`, `#runs`, `#vacancies`) — `height: 1fr` inside panel `Vertical` stacks.

Removed standalone rows for: metrics, DAG, throughput sparkline row, charts band, separate commands/debug rows.

#### Tests

- `test_diag_tabs_panel_switch` — tab labels + content
- `test_diag_tab_bar_allows_tab_focus_escape` — Tab leaves tab bar; ←/→ switches panes
- Existing: `test_errors_panel_renders`, `test_activity_panel_renders`, `test_debug_panel_on_selection`, `test_commands_panel_mode_aware`, `test_metrics_panel_and_sparkline`, `test_charts_panel_renders`, DAG tests

#### Removed code

- `Collapsible` wrappers (`#diag-tab-fold`, `#debug-fold`)
- Custom `_select_diag_tab`, `_sync_diag_tab_ui`, diag tab `on_key` click handlers
- Per-tab `display=False` toggling

---

### FEATURE-22 — Runs / vacancies panel layout

**Status:** **IMPLEMENTED**

- `#runs-panel` / `#vac-panel`: `Vertical` containers with `border_title`, filter `Input` **inside** panel (not full-width grid row).
- `#vacancies` `DataTable`: `height: 7` (fixed — `height: 1fr` collapsed to header-only).
- Grid lost dedicated filter row from `grid-rows`.

---

### FEATURE-23 (VIEW-19 v2) — Configuration YAML file browser

**Status:** **IMPLEMENTED**

#### Behaviour

| Mode | Interaction |
|------|-------------|
| Read-only | `#config-table` lists every `config/**/*.yaml` under `repo_root` (sorted). **Enter** / row click → `ConfigFileModal` with full file text |
| `--manage` | `m` / `c` still toggle `execution_mode` / `retry_cap` via footer keys only — **not** via config table Enter |

#### Model (`gmj_dashboard_model.py`)

- `snapshot()["config_files"]` — `_config_yaml_files()` via `config_dir.rglob("*.yaml")`
- `config_file_text(rel_path)` — path-validated read (`config/` prefix, no `..`, containment check)
- `snapshot()["config"]` dict **unchanged** — still powers counters / metrics projection

#### View

- `#config-panel` → `Vertical` + scrollable `#config-table` (single `file` column)
- `ConfigFileModal` replaces `ConfigDetailModal`
- Modal: `#cfg-modal-card` (90% × 90%) + `#cfg-modal-scroll` + `#cfg-modal-body`

#### Tests

- `test_features_and_config_panels` — expects `config/pipeline.config.yaml`, `config/sources.yaml` in config table; features catalog non-empty
- `test_config_table_drill_in` — modal shows `execution_mode` YAML
- `test_config_yaml_files_and_file_text` (model)
- Removed: `test_config_table_edit_row_under_manage`

---

### FIX-21-01 — Tab titles render as empty bordered boxes

**Severity:** High (tabs unusable — switching worked but labels invisible)  
**Status:** **FIXED**

#### Symptom

Four dark rectangles in tab row; green underline shows active tab; no text.

#### Root cause

1. `Tab` extends `Static`; global rule `Static { border: round #1a2b28; }` drew a frame on each tab.
2. `Tab { height: 1; }` + border consumed the only text row → clipped labels.
3. Textual `Tabs:ansi` theme sets active tab `color: transparent` — needed override.

#### Fix

```css
#diag-tabs-panel Tab { border: none; height: auto; min-height: 1; }
#diag-tabs-panel Tab.diag-tab-errors { color: #f85149; }
/* ... per-class colors + Tabs:ansi overrides */
```

Class tags applied in `_seed_widgets()` via `tab_bar.get_content_tab(pane_id).add_class(...)`. Avoid CSS ids `#--content-tab-pane-*` (awkward `--` prefix).

---

### FIX-21-03 — Config file modal narrow / not centered

**Severity:** Medium  
**Status:** **FIXED**

#### Symptom

Modal ~35% width, hugging top-left; long YAML not scrollable.

#### Root cause

`Screen { layout: grid; grid-size: 2; }` in `gmj_dashboard.tcss` **inherits onto `ModalScreen`**, breaking centered percentage sizing. `Static` alone does not scroll — need `VerticalScroll`.

#### Fix

```css
ConfigFileModal { layout: vertical; align: center middle; background: $background 60%; }
RunDetailModal, VacancyDetailModal { layout: vertical; ... }  /* same fix for all modals */

#cfg-modal-card { width: 90%; height: 90%; layout: vertical; ... }
#cfg-modal-scroll { height: 1fr; width: 100%; }
```

Compose:

```python
with Vertical(id="cfg-modal-card"):
    with VerticalScroll(id="cfg-modal-scroll"):
        yield Static("", id="cfg-modal-body")
```

Focus scroll area on mount for immediate wheel/arrow scrolling.

---

### FIX-21-02 — Tab key focus trap in diagnostics tab bar

**Severity:** Medium  
**Status:** **FIXED**

#### Symptom

Once tab bar focused, **Tab** cycled panes and user could not Tab out; **Shift+Tab** could not go back.

#### Cause

Custom `GmjDashboard.on_key` intercepted `tab` / `shift+tab` when `ContentTabs.has_focus` and called `action_next_tab` / `action_previous_tab`.

#### Fix

Removed `on_key` handler entirely. Document in `#commands` panel: `diagnostics: ←/→ switch pane when tab bar focused`.

---

### FIX-21-04 — TCSS parse error breaks entire dashboard

**Severity:** High (all tests fail — `TokenError`)  
**Status:** **FIXED**

#### Cause

Comment contained `config/**/*.yaml` — the `*/` closed the block comment early:

```css
/* ... list of config/**/*.yaml paths. */   /* BROKEN */
```

#### Fix

Rephrase comment: `/* ... list of config YAML paths. */`

---

### FEATURE-24 — Colorful ASCII figlet banner

**Status:** **IMPLEMENTED** (palette updated in Session 3 — see FEATURE-26)

- Restored original figlet block (`_BANNER_ASCII_LINES` from multiline raw string).
- Session 2: `_render_banner()` → per-line rainbow colors + italic slogan.
- **Session 3:** Ukrainian-flag palette — top 3 figlet lines `#0057B7` (blue), bottom 2 `#FFD700` (yellow); slogan **Your career's wingman** italic yellow, padded to figlet width (figlet rows stay **left-aligned** — per-line center padding broke `\_` alignment).
- Seeded once in `_seed_widgets()`; `#banner { content-align: center top; border: none; }` (Session 5 — was `center middle`; **do not** omit figlet descender row to tighten slogan — breaks `g`/`j` tails)

#### Tests

`test_header_and_counters_render` asserts figlet markers (`| |__` or `__ _ ___`) + slogan text.

---

### FEATURE-25 — Counters strip centering + delimiter

**Status:** **IMPLEMENTED** (format extended in Session 4 — **FEATURE-32**)

- `#counters { content-align: center middle; }`
- `_COUNTERS_DELIM = " │ "` (was ` · `)
- Constant at top of `gmj_dashboard.py` — easy swap
- **Session 4:** each segment now `label: value` with independent color via `_counter_item_style()` — see **FEATURE-32**

**Delimiter options documented for future UAT:** ` │ ` (current), ` ┆ `, ` ║ `, ` • `, ` · `, ` ◆ `, ` ▸ `, ` ╱ `

---

### Session 2 — errors & iterations log (chronological)

| # | Issue | Resolution |
|---|--------|------------|
| 1 | User: move debug after errors; remove “details” fold; tab keyboard; colored tabs; empty tab content | Migrated to `TabbedContent`; removed `Collapsible` |
| 2 | Tab labels not visible in real terminal | FIX-21-01 |
| 3 | User: Tab traps focus in tab bar | Added `on_key` cycle → user asked to undo → FIX-21-02 removed handler |
| 4 | User: add metrics + pipeline stages as tabs | New `TabPane`s; removed top-row panels |
| 5 | User: add throughput/gates charts as tab | `pane-charts`; removed `#charts` grid row |
| 6 | User: config panel → full yaml list + modal | FEATURE-23 + model methods |
| 7 | Config modal too narrow | FIX-21-03 (modal `layout: vertical`) |
| 8 | `test_manage_config_edit` failed — repo `execution_mode: autonomous` | `_MANAGE_TEST_CONFIG` fixture in tests |
| 9 | `test_view_has_no_write_or_subprocess_api` failed on `.replace` | `Path(rel_path).as_posix()` in model |
| 10 | User: counters centered + nicer delimiter | FEATURE-25 |
| 11 | User: plain “Give Me Job!” wordmark | Implemented then **reverted** to colorful ASCII per follow-up |
| 12 | `test_charts_panel_renders` flaky in full suite | Timing — passes in isolation; may need extra `pilot.pause()` |
| 13 | Banner `SyntaxError` when figlet stored as single-line `r"..."` | Use **triple-quoted** multiline raw string for `_BANNER_ASCII_LINES` (trailing `\_` line breaks parser) |

---

### Session 2 — files changed

| File | Changes |
|------|---------|
| `scripts/dashboard/gmj_dashboard.py` | Tabbed diagnostics; `ConfigFileModal`; `_render_banner()`; `_COUNTERS_DELIM`; config file browser; removed `_edit_config_row` / knob metadata |
| `scripts/dashboard/gmj_dashboard.tcss` | Grid rows; `#diag-tabs-panel` + tab styles; `#config-panel`; modal `layout: vertical`; `#counters` center; `#banner` |
| `scripts/dashboard/gmj_dashboard_model.py` | `_config_yaml_files()`, `config_file_text()`, `snapshot()["config_files"]` |
| `tests/test_gmj_dashboard.py` | Tab tests; config browser tests; banner assertions; `_MANAGE_TEST_CONFIG`; removed row-edit test |
| `tests/test_gmj_dashboard_model.py` | `test_config_yaml_files_and_file_text`; `config_files` in shape test |
| `gmj-core/scripts/dashboard/*` | **Manually copied** — run `python3 scripts/gmj_build_payload.py` before standalone ship |

**Docs not updated in Session 2:** `docs/cli-tools.md`, `TUI/testing-plan.md`, `test_docs_current.py` — still **OPEN**.

---

### Session 2 — reproduce / verify checklist

```bash
cd /path/to/give-me-job
pip install -r scripts/dashboard/requirements.txt

# Automated
python3 -m pytest tests/test_gmj_dashboard.py tests/test_gmj_dashboard_model.py -q

# Human UAT (isolated pipeline)
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir /tmp/gmj-uat-pipeline
```

**Verify manually:**

1. Banner: colorful ASCII figlet + “Your career's wingman” (full descenders on `g`/`j`); **Session 5:** `content-align: center top`.
2. **Status / heartbit (Session 5):** titled cyan **status** + green **heartbit** panels; counters inside status; heartbit hidden when idle.
3. Counters: centered strip with ` │ ` separators; **Session 4:** `label: value` + per-segment colors.
4. Runs + vacancies: filters inside **color-coded** panels (Session 4: gold runs, green vacancies); table rows visible (**Session 5:** 17-row band).
5. Features + configuration: same row above runs/vac; not empty (**Session 5** layout).
6. Configuration: lists all `config/**/*.yaml`; Enter opens **wide centered scrollable** modal.
7. Diagnostics tabs: 7 labeled colored tabs; **12-row** band visible at bottom (**Session 5**); content scrolls; ←/→ on tab bar; Tab moves focus out.
8. After `r`/`R`/`b` under `--manage`: activity tab auto-selected; errors/activity/debug refresh during fast-poll window (VIEW-20).

**Restart required** after code changes — old dashboard process keeps prior layout.

---

### Session 2 — still OPEN from Session 1 (superseded partially by Session 3)

| ID | Item | Session 3 note |
|----|------|----------------|
| ~~FIND-03~~ | ~~Default focus to `#runs` on mount~~ | **FIXED** — no default focus (FEATURE-30) |
| FIND-06 P1 | Thread `--pipeline-dir` into `claude` child for `r`/`R` | Still open |
| FIND-06 P2 | Status vs step honesty during resume | Still open |
| FIND-08 | Warn when UAT mutates real `config/pipeline.config.yaml` | Still open |
| FIND-09 | Layout test with real long `candidate.yaml` | Lower priority — `#candidate` removed |
| FIND-14 | Automated `#runs` min-height under real profile | May repurpose for features/runs row |
| Docs | `docs/cli-tools.md`, `test_docs_current.py`, `gmj-file-manifest.json` rebuild | Still open |

---

### Session 2 — suggested next commits (for milestone agent)

1. `feat(dashboard): consolidate diagnostics into tabbed panel (VIEW-21)`
2. `feat(dashboard): config yaml file browser + scrollable modal (VIEW-19 v2)`
3. `fix(dashboard): modal layout override + tab label visibility`
4. `ui(dashboard): colorful figlet banner, centered counters`
5. `docs: refresh cli-tools + UAT handoff after Session 2`

---

## Session 3 — features panel, live heartbeat, layout polish (July 6, 2026)

**Agent:** Cursor (continued from Session 2)  
**Scope:** Replace candidate panel with a scrollable **features catalog**; unify **live refresh** for all panels; animated **heartbeat** strip during background work; detect **in-flight pipeline work from disk** after dashboard reload; swap grid rows and increase table height; **no startup focus**.

### Session 3 — feature / fix index

| ID | Type | Status | Summary |
|----|------|--------|---------|
| **FEATURE-26** | Feature | **IMPLEMENTED** | Features panel — skills / agents / commands / flows catalog + filter + drill-in modal + `--manage` Run |
| **FEATURE-27** | Feature | **IMPLEMENTED** | Live heartbeat strip + rapid poll during child launches and post-launch sync window |
| **FEATURE-28** | Feature | **IMPLEMENTED** | Pipeline activity on reload — disk-backed in-flight runs/batches → heartbeat + auto debug selection |
| **FEATURE-29** | UX | **IMPLEMENTED** (height revised Session 5) | Grid row swap (features/config above runs/vac) + table height ~11 (~5 visible rows); **Session 5:** rows **17** each (1.5×) |
| **FEATURE-30** | UX | **IMPLEMENTED** | No default focus at startup — **FIND-03 FIXED** |
| **FIX-28-01** | Bug | **FIXED** | Feature Run did not enable live refresh — `_launch_feature` now calls `_track_launch(proc)` |
| **FIX-28-02** | Bug | **FIXED** | Banner figlet misalignment — slogan-only centering; figlet lines left-aligned |
| **FIX-28-03** | Bug | **FIXED** | Idle tests broken by auto-debug on in-flight pipeline — `_temp_idle_pipeline()` helper |

---

### FEATURE-26 — Features panel (replaces `#candidate`)

**Status:** **IMPLEMENTED**

#### Motivation

Human UAT: candidate YAML summary was low-signal on the main board; operators need a **launch surface** for collective skills, agents, slash commands, and documented flows without memorizing footer keys.

#### New module

[`scripts/dashboard/gmj_dashboard_features.py`](../scripts/dashboard/gmj_dashboard_features.py):

- Discovers **commands** (`.claude/commands/gmj*.md`, `gmj-pipeline/*.md`), **agents** (`.claude/agents/gmj-*.md`), **skills** (`.claude/skills/gmj-*/SKILL.md`), **flows** (`docs/flows.md` sections).
- `build_feature_prompt(kind, name, params)` → detached `claude -p` prompt (consumed by manage launcher).
- Param schemas per command stem (`gmj-pipeline-run`, `gmj-batch`, `gmj-collective`, …).

#### Model

- `snapshot()["features"]` — filtered catalog rows (`kind`, `name`, `summary`).
- `feature_detail(kind, name)` — description + param specs for modal.
- `candidate` removed from snapshot shape (thin `_candidate()` reader retained for model unit tests only).

#### View

- `#features-panel` — `border_title: features`; `#features-filter` + `#features-table` (`kind | name | summary`).
- **Enter** on row → `FeatureModal` — description, dynamic inputs, **Run** (requires `--manage`) / Close.
- `_launch_feature` → same `_track_launch(proc)` path as `action_run` / `action_resume` (FIX-28-01).

#### Tests

- `test_features_and_config_panels` — table seeds from catalog
- `test_features_table_drill_in` — modal opens with description
- `test_feature_launch_enables_live_refresh` — fast poll / heartbeat after Run

---

### FEATURE-27 — Live heartbeat + unified panel refresh

**Status:** **IMPLEMENTED** (heartbeat UX refined in Session 4 — **FEATURE-31**)

#### Behaviour (Session 3 baseline)

- `#heartbeat` strip (full width, below counters) — hidden when idle.
- Animated `█░` bar at **0.12s** when active (`_heartbeat_anim`).
- `_needs_rapid_poll()` → **0.4s** interval when launching or syncing; baseline `--refresh` default changed **1.5s → 1.0s**.
- All panels (features, config, runs, vac, diag tabs) refresh on the same poll tick — no stale island panels during background work.

#### Session 4 refinements (FEATURE-31)

- **Two-line layout:** line 1 = `● {primary_task}`; line 2 = animated bar spanning **full row width** (`_heartbeat_content_width`).
- **Primary task only** when several items in flight — e.g. `20260604T120000-pend → gmj-artifact-composer (+2 more)`; child launches show `resume {run_id}` / feature name / `pipeline run (new offer)`.
- Removed trailing grey list (`updating runs · errors · activity · …`).
- `_track_launch(..., label=...)` records human-readable labels for pending children.
- **FIX-31-01:** long single-line label + fixed 56-char bar left only a few animated blocks — fixed by separating label and full-width bar.
- **FIX-31-02:** heartbeat status fallback `"running"` tripped grep-guard — replaced with `"—"`.

#### Tests

- `test_heartbeat_strip_shows_during_live_refresh`
- `test_feature_launch_enables_live_refresh`
- `test_heartbeat_on_reload_when_pipeline_active_on_disk` (asserts task label + bar, not generic `pipeline` word)

---

### FEATURE-28 — Pipeline activity detection on reload (VIEW-28)

**Status:** **IMPLEMENTED** (pipeline runs + batches only)

#### `gmj_runs.py` helpers

```python
is_pipeline_in_flight_status(status)  # not in terminal set
is_batch_in_flight(batch_row)         # ok batch with undelivered offers
```

#### Model

- `pipeline_activity()` → `{ "active", "active_run_ids", "active_batch_ids" }`
- Included in `snapshot()["pipeline_activity"]`

#### View

- `_sync_pipeline_activity()` on each poll:
  - Sets `_disk_pipeline_active`, stores `snapshot()["pipeline_activity"]` in `_pipeline_activity`
  - Heartbeat shows primary in-flight run/batch (FEATURE-31)
  - Auto-selects first in-flight `run_id` for debug panel when none selected

#### Limitation (still OPEN)

Non-pipeline feature launches (collective, interview, template, …) are **not** recovered from disk on reload — only pipeline run/batch state. Future: launch sidecar file under `.pipeline/` or similar.

#### Tests

- `test_pipeline_activity_detects_in_flight_work` (model)
- `test_heartbeat_on_reload_when_pipeline_active_on_disk` (view)

---

### FEATURE-29 — Grid layout: row swap + taller tables

**Status:** **IMPLEMENTED**

#### Compose order (top → bottom)

```
banner → counters → heartbeat
features | configuration     (grid row 15)
runs     | vacancies         (grid row 15)
diag-tabs (full width, grid 12)
```

#### TCSS

```css
grid-rows: auto auto auto 15 15 12;
/* banner | counters | heartbeat | features+config | runs+vac | diag-tabs */
```

- `#features-table`, `#config-table`, `#runs`, `#vacancies`: `height: 11` (was 7) — ~5 visible data rows at typical terminal width.
- `#candidate` panel and grid slot **removed**.

#### Tests

- `test_features_and_config_panels` — both panels mount in new positions
- Existing runs/vac layout tests still pass with updated heights

---

### FEATURE-30 — No default focus (FIND-03 fix)

**Status:** **IMPLEMENTED**

- `GmjDashboard.AUTO_FOCUS = ""`
- `_clear_startup_focus()` via `call_after_refresh` → `set_focus(None)`
- Manage keys (`r`/`R`/`b`/`m`/`c`) fire at startup without clicking away from filter.
- `test_startup_has_no_default_focus`

---

### Session 3 — errors & iterations log

| # | Issue | Resolution |
|---|--------|------------|
| 1 | User: replace candidate with features table + filter + modal Run | FEATURE-26 + `gmj_dashboard_features.py` |
| 2 | Feature Run did not trigger live refresh | FIX-28-01 — `_track_launch` in `_launch_feature` |
| 3 | User: all panels must update live; heartbeat during background work | FEATURE-27 |
| 4 | User: on dashboard restart, show activity if pipeline still running on disk | FEATURE-28 + `gmj_runs` helpers |
| 5 | User: Ukrainian flag banner colors + centered slogan | FEATURE-24 palette update; FIX-28-02 alignment |
| 6 | Per-line figlet center padding broke `\_` char alignment | Left-align figlet; pad slogan only |
| 7 | User: features/config row above runs/vac; taller panels (~5 rows) | FEATURE-29 |
| 8 | Runs filter stole focus at startup (FIND-03) | FEATURE-30 — no default focus |
| 9 | Tests assumed idle pipeline but fixture had in-flight runs | `_temp_idle_pipeline()` context manager |
| 10 | Full suite occasional flake on activity/errors probes | Extra `pilot.pause()` ticks in some tests; passes in isolation |

---

### Session 3 — files changed

| File | Changes |
|------|---------|
| `scripts/dashboard/gmj_dashboard_features.py` | **NEW** — catalog discovery + prompt builder |
| `scripts/dashboard/gmj_dashboard.py` | Features panel, `FeatureModal`, heartbeat, `_sync_pipeline_activity`, layout compose order, `AUTO_FOCUS`, banner UA colors |
| `scripts/dashboard/gmj_dashboard_model.py` | `features`, `feature_detail`, `pipeline_activity`; snapshot shape |
| `scripts/dashboard/gmj_dashboard.tcss` | Grid rows `auto auto auto 15 15 12`; `#heartbeat`; `#features-panel`; table heights 11; removed `#candidate` |
| `scripts/pipeline/gmj_runs.py` | `is_pipeline_in_flight_status`, `is_batch_in_flight` |
| `tests/test_gmj_dashboard.py` | Features, heartbeat, reload, startup focus tests; `_temp_idle_pipeline` |
| `tests/test_gmj_dashboard_model.py` | `test_pipeline_activity_detects_in_flight_work`; snapshot shape |
| `gmj-core/scripts/dashboard/*` | Mirror of above (partial — rebuild manifest before ship) |

---

### Session 3 — still OPEN from Sessions 1–2

| ID | Item |
|----|------|
| FIND-06 P1 | Thread `--pipeline-dir` into `claude` child for `r`/`R` / feature launches |
| FIND-06 P2 | Status vs step honesty during resume |
| FIND-08 | Warn when UAT mutates real `config/pipeline.config.yaml` |
| FIND-09 | Layout test with real long `candidate.yaml` (candidate panel removed — lower priority) |
| FIND-14 | Automated min-height under real profile (may repurpose for features/runs row) |
| VIEW-28 gap | Non-pipeline feature detection on reload (launch sidecar) |
| Docs | `docs/cli-tools.md`, `test_docs_current.py`, `gmj-file-manifest.json` rebuild |

---

### Session 3 — suggested next commits

1. `feat(dashboard): features catalog panel with filter and run modal (VIEW-26)`
2. `feat(dashboard): live heartbeat strip and unified poll refresh (VIEW-27)`
3. `feat(dashboard): detect in-flight pipeline work on reload (VIEW-28)`
4. `ui(dashboard): swap features/config above runs/vac; taller tables; UA banner`
5. `fix(dashboard): no default focus at startup (FIND-03)`
6. `docs: refresh cli-tools + UAT handoff after Session 3`

---

### Session 3 — reproduce / verify checklist

```bash
cd /path/to/give-me-job
pip install -r scripts/dashboard/requirements.txt

# Automated (59 tests)
python3 -m pytest tests/test_gmj_dashboard.py tests/test_gmj_dashboard_model.py -q

# Human UAT — features + live heartbeat
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir /tmp/gmj-uat-pipeline
# or with real pipeline dir while a run is in-flight:
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir .pipeline
```

**Verify manually:**

1. Banner: Ukrainian blue/yellow figlet + centered slogan **Your career's wingman**.
2. **No widget focused** at startup — `r`/`R`/`b`/`m`/`c` work without clicking runs table first.
3. **Features** (top-left, **orange** border): filter + table of commands/agents/skills/flows; Enter → modal with Run under `--manage`.
4. **Configuration** (top-right, **blue** border): yaml file list unchanged from Session 2.
5. **Runs / vacancies** (second row, **gold** / **green** borders): ~5 visible table rows; filters inside panels.
6. **Heartbeat**: hidden when idle; line 1 shows primary task (`run_id → step` or launch label); line 2 is full-width animated bar (Session 4).
7. **Reload test**: start a pipeline run, quit dashboard, relaunch with same `--pipeline-dir` — heartbeat shows in-flight task and debug auto-selects a run.
8. Diagnostics tabs: unchanged from Session 2.

**Restart required** after code changes.

---

## Session 4 — Heartbeat, counters, panel colors (July 6, 2026)

**Agent:** Cursor (continued from Session 3)  
**Scope:** Human UAT polish on the status strip, heartbeat task display, and main-panel visual identity.

### Session 4 — feature / fix index

| ID | Type | Status | Summary |
|----|------|--------|---------|
| **FEATURE-31** | UX | **IMPLEMENTED** | Heartbeat: primary task label + full-width animated bar (two lines); launch labels on `_track_launch` |
| **FEATURE-32** | UX | **IMPLEMENTED** | Counters: `label: value` with `: ` separator; per-segment colors; bold values |
| **FEATURE-33** | UX | **IMPLEMENTED** | Panel border + table/filter accent colors (orange / blue / gold / green) |
| **FIX-31-01** | Bug | **FIXED** | Long heartbeat label squeezed animation to ~4 blocks — split label vs full-width bar |
| **FIX-31-02** | Bug | **FIXED** | Grep-guard trip on `"running"` literal in heartbeat fallback — use `"—"` |

---

### FEATURE-31 — Heartbeat task label + full-width bar

**Status:** **IMPLEMENTED**

#### User request

Remove the grey trailing panel list; make the strip span the full terminal width; show the **exact** in-flight task (run id + step, batch id, or launched feature).

#### View (`gmj_dashboard.py`)

| Helper | Role |
|--------|------|
| `_heartbeat_task_items()` | Collect all in-flight labels (child procs, then disk runs/batches) |
| `_heartbeat_primary_task()` | First item, or `{item} (+N more)` when multiple |
| `_heartbeat_content_width(hb)` | Row width from `content_region` / widget / screen |
| `_heartbeat_bar(width, phase)` | `█░` animation cells |
| `_render_heartbeat()` | Line 1: `● {task}`; line 2: full-width bar |

**Child launch labels** via `_track_launch(proc, *, run_id=None, label=None)`:

| Action | Label |
|--------|-------|
| `action_run` | `pipeline run (new offer)` |
| `action_resume` | `resume {run_id}` |
| `_launch_feature` | feature `name` / `slash` |

**Disk pipeline:** `{run_id} → {current_step}` from cached snapshot runs; `batch {batch_id}` for in-flight batches.

#### TCSS (Session 5)

```css
#heartbit-panel {
    border: round #3fb950;
    display: none;   /* _set_heartbeat_chrome toggles */
}
#heartbeat {
    max-height: 2;
    content-align: left top;
}
```

(Heartbeat lives inside `#heartbit-panel` within `#status-band` — not a standalone grid row.)

#### Tests

- `test_heartbeat_strip_shows_during_live_refresh` — task name or `syncing` in output
- `test_heartbeat_on_reload_when_pipeline_active_on_disk` — `→` or `batch` in label; full-width `█`/`░` bar present

---

### FEATURE-32 — Counters `label: value` + per-segment colors

**Status:** **IMPLEMENTED** (extends **FEATURE-25**)

#### Format

```
runs: 7 │ delivered: 3 │ failed: 1 │ pending: 1 │ running: 1 │ unknown: 1 │ offers: 3 │ default_mode: autonomous │ cap: 4
```

#### Implementation

- `_apply_counters()` builds a Rich `Text` — no plain-string join.
- `_counter_item_style(label)` — status buckets use theme `status-*` vars at runtime (grep-guard safe); fixed palette for structural keys.

| Segment | Color |
|---------|-------|
| `runs` | cyan `#39d0d8` |
| `delivered` / `failed` / `pending` / `running` / `unknown` | theme `status-*` (green / red / gray / amber / purple) |
| `offers` | purple `#bc8cff` |
| `default_mode` | amber `#d29922` |
| `cap` | green `#3fb950` |
| `│` delimiter | dim `#6e7681` |

Values rendered **bold** in the same color as their label.

#### Tests

- `test_header_and_counters_render` — asserts `runs:` and `delivered:\s*\d+`

---

### FEATURE-33 — Color-coded main panels

**Status:** **IMPLEMENTED**

Distinct border + filter border + table text accent per panel (`gmj_dashboard.tcss`):

| Panel | Border | Table / accent |
|-------|--------|----------------|
| **features** (`#features-panel`) | orange `#f0883e` | `#f0883e` |
| **configuration** (`#config-panel`) | blue `#58a6ff` | `#79c0ff` |
| **runs** (`#runs-panel`) | gold `#e3b341` | `#e3b341` |
| **vacancies** (`#vac-panel`) | green `#3fb950` | `#56d364` (slightly brighter for readability) |

Filter inputs (`#features-filter`, `#filter`, `#vac-filter`) use matching border + soft tinted text.

Replaces Session 2/3 default green/cyan-only panel borders.

---

### Session 4 — errors & iterations log

| # | Issue | Resolution |
|---|--------|------------|
| 1 | User: remove heartbeat trailing panel-name list | FEATURE-31 — dropped grey suffix |
| 2 | User: heartbeat should name exact running task | `_heartbeat_task_items` / `_heartbeat_primary_task` |
| 3 | User: heartbeat bar not full width | Two-line layout + `_heartbeat_content_width` |
| 4 | Feature Run didn't show in heartbeat | Already fixed Session 3 (`_track_launch`); labels added Session 4 |
| 5 | User: counters need `label: value` + colors | FEATURE-32 |
| 6 | User: each main panel a different color | FEATURE-33 palette |
| 7 | `test_grep_guard_no_rederived_literals` failed on `"running"` | FIX-31-02 |

---

### Session 4 — files changed

| File | Changes |
|------|---------|
| `scripts/dashboard/gmj_dashboard.py` | Heartbeat helpers; `_track_launch(label=)`; `_counter_item_style`; Rich counters |
| `scripts/dashboard/gmj_dashboard.tcss` | `#heartbeat` full width; per-panel color rules |
| `tests/test_gmj_dashboard.py` | Counters `:` assertions; heartbeat reload probe |
| `gmj-core/scripts/dashboard/*` | Mirror of above |

---

### Session 4 — still OPEN (unchanged from Session 3)

| ID | Item |
|----|------|
| FIND-06 P1 | Thread `--pipeline-dir` into `claude` child for `r`/`R` / feature launches |
| FIND-06 P2 | Status vs step honesty during resume |
| FIND-08 | Warn when UAT mutates real `config/pipeline.config.yaml` |
| FIND-09 / FIND-14 | Layout geometry tests (lower priority) |
| VIEW-28 gap | Non-pipeline feature detection on reload |
| Docs | `docs/cli-tools.md`, `test_docs_current.py`, `gmj-file-manifest.json` rebuild |

---

### Session 4 — suggested next commits

1. `ui(dashboard): heartbeat primary task + full-width animation bar (VIEW-27 v2)`
2. `ui(dashboard): counters label:value with per-segment colors`
3. `ui(dashboard): color-coded panel borders (features/config/runs/vac)`
4. `docs: refresh cli-tools + UAT handoff after Session 4`

---

### Session 4 — reproduce / verify checklist

```bash
python3 -m pytest tests/test_gmj_dashboard.py tests/test_gmj_dashboard_model.py -q
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir .pipeline
```

**Verify manually:**

1. **Counters:** `runs: 7 │ delivered: 3 │ …` — each segment a different color; values bold.
2. **Panels:** orange features, blue configuration, gold runs, green vacancies (borders + table tint).
3. **Heartbeat (idle):** hidden.
4. **Heartbeat (in-flight):** `● 20260602T120000-run-ws → gmj-truth-verifier (+N more)` on line 1; full-width `█░` bar on line 2.
5. **Heartbeat (after `r`/`R`/feature Run):** shows launch label (`pipeline run (new offer)`, `resume …`, or feature name).

---

## Session 5 — Grid layout, spacing, panel sizing (July 6, 2026)

**Agent:** Cursor (continued from Session 4)  
**Scope:** Human UAT on **vertical rhythm**, **titled status strips**, **table panel visibility**, **diagnostics tabs band**, **banner slogan proximity**, and **taller main panels**.

### Session 5 — feature / fix index

| ID | Type | Status | Summary |
|----|------|--------|---------|
| **FEATURE-34** | UX | **IMPLEMENTED** | Single-column grid + `grid-gutter: 1` for equal inter-panel spacing; `#status-band` stacks status + heartbit |
| **FEATURE-35** | UX | **IMPLEMENTED** | Bordered titled panels: `status` (cyan) + `heartbit` (green); counters moved inside `#status-panel` |
| **FEATURE-36** | UX | **IMPLEMENTED** | Table band height **1.5×** — `#features-config-row` / `#runs-vac-row` **11 → 17** rows |
| **FIX-34-01** | Bug | **FIXED** | Uneven vertical gaps — `margin-bottom` on grid children stacked with `grid-gutter` / auto-row stretch |
| **FIX-34-02** | Bug | **FIXED** | `column-span: 2` + `auto` rows — Textual measures width at **half** screen → status/heartbit row too tall, gaps uneven |
| **FIX-34-03** | Bug | **FIXED** | Empty **features** / **configuration** — first `1fr` grid row collapsed to ~2 lines after Session 4 `grid-size: 2` revert path |
| **FIX-34-04** | Bug | **FIXED** | Missing **diagnostics tabs** — `#tables-stack` `1fr` wrapper expanded and starved `#diag-tabs-panel` (height 0) |
| **FIX-34-05** | Bug | **FIXED** | Logo `g`/`j` descenders clipped — reverted mistaken omission of figlet tail row; slogan spacing via `content-align: center top` only |
| **FIX-34-06** | Bug | **FIXED** | Dashboard failed to start — `line-pad: 0` rejected by Textual CSS parser (removed; default is fine) |

---

### FEATURE-34 — Single-column grid + equal spacing

**Status:** **IMPLEMENTED**

#### Symptoms (human UAT)

- Large gap between **status** and **heartbit**, smaller gap below heartbit.
- After partial fixes, **features/configuration** empty while **runs/vacancies** rendered.

#### Root causes

1. **`grid-size: 2` + `column-span: 2`** on full-width widgets: Textual `auto` row height uses **single-column width** for `get_content_height`, inflating row size vs rendered width → uneven gutters.
2. **`margin-bottom: 1`** on grid children **plus** `grid-gutter` duplicated vertical space.
3. **Two separate `1fr` rows** for table bands: Textual assigns first `1fr` row minimum content height (~2), second row takes remainder.
4. **`#tables-stack` `Vertical` wrapping both `1fr` rows**: outer `1fr` expanded to content minima and pushed `#diag-tabs-panel` off-screen.

#### Solution (current)

```css
Screen {
    layout: grid;
    grid-size: 1;
    grid-gutter: 1;
    grid-rows: auto auto auto 17 17 12;
}
```

- No `margin-bottom` on panel rows — spacing from **`grid-gutter` only**.
- Side-by-side pairs via `#features-config-row` / `#runs-vac-row` **`Horizontal`** containers (not second grid column on `grid-size: 2`).
- `#status-band` — one `auto` grid row; internal `.panel-v-gap` (height 1) between status and heartbit when active (`_set_heartbeat_chrome`).

#### Compose (`gmj_dashboard.py`)

```
Header → #banner → #status-band → #features-config-row → #runs-vac-row → #diag-tabs-panel → Footer
```

---

### FEATURE-35 — Titled `status` + `heartbit` panels

**Status:** **IMPLEMENTED**

- `#status-panel` — `border_title: "status"`, border `#39d0d8`; contains `#counters` only.
- `#heartbit-panel` — `border_title: "heartbit"`, border `#3fb950`; contains `#heartbeat`; hidden when idle.
- `_set_heartbeat_chrome(visible)` toggles heartbit panel, gap widget, and heartbeat `Static` together.

Replaces Session 3–4 pattern of bare `#counters` + `#heartbeat` grid rows.

---

### FEATURE-36 — Taller features / config / runs / vacancies panels

**Status:** **IMPLEMENTED** (extends **FEATURE-29**)

Human UAT: four main table panels too short after spacing fixes.

| Row | Session 3–4 height | Session 5 height |
|-----|-------------------|------------------|
| `#features-config-row` | 11 | **17** (×1.5, rounded up) |
| `#runs-vac-row` | 11 | **17** |
| `#diag-tabs-panel` | 12 | **12** (unchanged) |

```css
#features-config-row,
#runs-vac-row {
    height: 17;
    min-height: 17;
    layout: horizontal;
    overflow: hidden;
}
```

DataTables use `height: 1fr; min-height: 3` to fill the taller panel body.

**Viewport:** recommend **≥64 terminal rows** for comfortable fit (was ~52 with 11-row table bands).

---

### FIX-34-05 — Banner slogan vs figlet descenders

**Status:** **FIXED**

- **Wrong fix (reverted):** skip `_BANNER_ASCII_LINES[-1]` to move slogan up — removed `g`/`j` descender art.
- **Correct fix:** render all five figlet lines; tighten vertical packing with `#banner { content-align: center top; }` (not `center middle`).
- **Invalid:** `line-pad: 0` — Textual requires positive integer if set (**FIX-34-06**).

---

### Session 5 — errors & iterations log

| # | Issue | Resolution |
|---|--------|------------|
| 1 | User: unequal vertical panel gaps | FEATURE-34 — `grid-size: 1`, `grid-gutter: 1`, `#status-band` |
| 2 | User: status + heartbit should be titled panels like others | FEATURE-35 |
| 3 | User: heartbeat green, compact, full-width bar | Carried from Session 4; framed in `#heartbit-panel` |
| 4 | User: features/configuration panels empty | FIX-34-03 — fixed row heights; abandoned `tables-stack` `1fr` wrapper (FIX-34-04) |
| 5 | User: diagnostics tabs band missing | FIX-34-04 — direct grid children `17 17 12`; fixed `#diag-tabs-panel` height |
| 6 | User: move slogan one row closer | Attempted tail-row drop → FIX-34-05 revert + `content-align: top` |
| 7 | User: `g`/`j` in logo broken | FIX-34-05 — restore full figlet |
| 8 | Launch crash: `line-pad: 0` invalid | FIX-34-06 — remove property |
| 9 | User: table panels 1.5× taller | FEATURE-36 — 17-row bands |

---

### Session 5 — files changed

| File | Changes |
|------|---------|
| `scripts/dashboard/gmj_dashboard.py` | `#status-band` compose; `_set_heartbeat_chrome` gap toggle; full figlet render |
| `scripts/dashboard/gmj_dashboard.tcss` | `grid-size: 1`; `grid-rows: auto auto auto 17 17 12`; status/heartbit panels; horizontal rows; flex tables; banner `center top` |
| `gmj-core/scripts/dashboard/*` | Mirror of above |
| `TUI/dashboard-uat-findings.md` | Session 5 handoff (this section) |

---

### Session 5 — still OPEN (unchanged from Session 4)

| ID | Item |
|----|------|
| FIND-06 P1 | Thread `--pipeline-dir` into `claude` child for `r`/`R` / feature launches |
| FIND-06 P2 | Status vs step honesty during resume |
| FIND-08 | Warn when UAT mutates real `config/pipeline.config.yaml` |
| FIND-09 / FIND-14 | Layout geometry tests under real profile / min heights |
| VIEW-28 gap | Non-pipeline feature detection on reload |
| Docs | `docs/cli-tools.md`, `test_docs_current.py`, `gmj-file-manifest.json` rebuild |

---

### Session 5 — reproduce / verify checklist

```bash
python3 -m pytest tests/test_gmj_dashboard.py tests/test_gmj_dashboard_model.py -q
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir /tmp/gmj-uat-pipeline
```

**Verify manually (terminal ≥64 rows recommended):**

1. **Spacing:** uniform 1-row gaps between banner → status → heartbit (when active) → features row → runs row → diag tabs.
2. **Status / heartbit:** cyan **status** and green **heartbit** titled borders; heartbit hidden when idle.
3. **Tables:** features, configuration, runs, vacancies all show filter + scrollable rows (not empty frames).
4. **Diagnostics:** 7-tab band visible at bottom (errors tab default); not clipped to height 0.
5. **Banner:** full figlet with `g`/`j` descenders; slogan directly below tail row; no CSS parse error on launch.
6. **Panel height:** table bands visibly taller than Session 4 (~17 lines each).

---

### Wave A — Close OPEN UX foot-guns (small)

1. ~~**FIND-03**~~ — **DONE** (Session 3 — no default focus + `test_startup_has_no_default_focus`).
2. **FIND-07** — fix docs (`run inspect`).
3. **FIND-08** — `--manage` config path warning or UAT script with temp config.

### Wave B — Test gaps (medium)

4. **FIND-09** / **FIND-01** — long-candidate layout test.
5. **FIND-02** — batch two-step modal keypress test.
6. **FIND-06** — in-flight status overlay unit test.

### Wave C — Architectural honesty (larger)

7. **FIND-06 P1** — thread `pipeline_dir` into `r`/`R` launch prompt + orchestrator support.
8. **FIND-06 P2** — projection or UI legend for status vs step during resume.
9. **DASH-UAT-03** — cross-terminal / SSH / tmux rendering pass (human).

### Wave D — Docs & ops

10. Update [TUI/testing-plan.md](testing-plan.md) UAT section with findings matrix + correct launch recipe:

    ```bash
    python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir .pipeline
    ```

11. Update [docs/cli-tools.md](../docs/cli-tools.md) / slash command wrapper if behaviour changes.

12. Run `python3 tests/test_docs_current.py` at milestone finalization per [rules/docs-currency.md](../rules/docs-currency.md).

### Wave E — New read-only panel feature

13. **FEATURE-12 (VIEW-17 / VIEW-18)** — vacancies `#vac-filter` + `DataTable` + `offer_detail()` + `VacancyDetailModal` + filter/table tests + `gmj-core` mirror (see full spec above).

14. Optional follow-ups (same feature family, lower priority):
    - Link offer → active pipeline run(s) by `offer_spec_hash` in modal.
    - `--manage`: “Run pipeline for this offer” from modal (prefill `r` prompt).

### Wave F — Session 2 follow-ups (docs + polish)

15. Document VIEW-21 tab order + keyboard (`←/→` on tab bar; Tab escapes) in `docs/cli-tools.md` / slash command.
16. Rebuild `gmj-core` payload + `gmj-file-manifest.json` after mirror sync (`python3 scripts/gmj_build_payload.py`).
17. Stabilize `test_charts_panel_renders` if full-suite flake persists (extra `pilot.pause()` tick).
18. Optional: config table filename filter (parity with runs/vac/features filters).

### Wave G — Session 3 follow-ups (docs + gaps)

19. Document features panel + heartbeat + reload behaviour in `docs/cli-tools.md` / `/gmj-dashboard` slash command.
20. **VIEW-28 gap** — launch sidecar for non-pipeline feature runs (collective, interview, template).
21. **FIND-06 P1** — thread `pipeline_dir` into feature Run prompts (same as `r`/`R`).
22. Rebuild `gmj-core` payload + `gmj-file-manifest.json` after mirror sync.
23. Stabilize full-suite flake (`test_charts_panel_renders`, activity/errors probes) if CI reports failures.

### Wave H — Session 4 follow-ups (docs)

24. Document counters `label: value` format + panel color legend in `docs/cli-tools.md`.
25. Document heartbeat two-line layout + primary-task semantics in `/gmj-dashboard` slash command.
26. Optional: panel title color matches border (Textual `border_title` styling if supported).

### Wave I — Session 5 follow-ups (docs + hardening)

27. Document Session 5 grid layout (`grid-size: 1`, fixed row heights, min terminal rows) in `docs/cli-tools.md`.
28. Add headless geometry test: `#features-config-row` / `#runs-vac-row` height ≥15 and `#diag-tabs-panel` height ≥12 at `size=(120, 64)` (**FIND-09** / **FIND-14** partial).
29. Rebuild `gmj-core` payload + `gmj-file-manifest.json` after mirror sync.
30. Optional: responsive row heights via env/flag instead of fixed `17` for short terminals.

---

## Launch recipe (canonical for all future UAT)

```bash
cd /path/to/give-me-job
pip install -r scripts/dashboard/requirements.txt

# Read-only smoke (fixture pipeline — demo data)
python3 scripts/dashboard/gmj_dashboard.py --pipeline-dir tests/fixtures/pipeline

# Real operator board + manage actions
python3 scripts/dashboard/gmj_dashboard.py --manage --pipeline-dir .pipeline

# Isolated batch writes (optional)
python3 scripts/dashboard/gmj_dashboard.py --manage \
  --pipeline-dir /tmp/gmj-uat-pipeline

# Safe config edits (optional)
cp config/pipeline.config.yaml /tmp/pipeline.config.yaml
python3 scripts/dashboard/gmj_dashboard.py --manage \
  --pipeline-dir .pipeline \
  --config /tmp/pipeline.config.yaml
```

**Manage keys:** work at startup with no focused widget (FIND-03 fixed). If a filter input is focused, click away before pressing `r`/`R`/`b`/`m`/`c`.

**Terminal size:** after Session 5 fixed row heights (`17+17+12` table/diag bands), use **≥64 rows** height for all panels + diagnostics tabs to fit without clipping.

---

## Appendix — `project_status` decision tree (reference)

From [`scripts/pipeline/gmj_runs.py`](../scripts/pipeline/gmj_runs.py) `project_status()`:

```
if Gate A ∧ Gate B pass        → delivered
elif any retry_count >= cap    → failed
elif fresh pending signature   → pending
else                           → running
```

Dashboard **must not** re-implement this tree (grep-guard enforced). Session 3 **VIEW-27/28** add a view-layer heartbeat overlay and `pipeline_activity()` projection with tests mirroring `gmj_runs` — they do not fork `project_status()` logic.

---

*End of handoff document. Last updated: Session 4 — July 6, 2026.*
