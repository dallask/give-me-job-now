#!/usr/bin/env python3
"""Tests for scripts/dashboard/gmj_dashboard.py (VIEW-01/02/04/07 + SAFETY-02, Plan 21-01).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_dashboard.py``. Mirrors the structure of
``tests/test_gmj_dashboard_model.py``: module-level ``REPO_ROOT`` / fixture constants, the
``sys.path.insert`` import idiom, a ``main()`` that runs every ``test_*`` and returns 1 on any
failure, and the never-a-traceback discipline (a stray crash can never masquerade as a pass).

The App is driven headlessly via ``App.run_test(size=(120, 40))`` → ``Pilot`` inside
``asyncio.run(...)`` (the repo has no pytest). The model is always constructed against a COPY of
``tests/fixtures/pipeline/`` inside a ``TemporaryDirectory`` (via ``_temp_pipeline``) so a bug in
the view can never mutate the committed fixtures, and ``repo_root`` is pointed at the deterministic
``tests/fixtures/dashboard`` corpus for the config/candidate/offers panels.

Requirement coverage (this plan):
- VIEW-01  ``test_readonly_no_mutating_bindings``       — mutating keys unbound without --manage
- VIEW-07  ``test_footer_mode_aware_bindings``          — mutating keys bound under --manage
- VIEW-02  ``test_header_and_counters_render``          — banner + generic counters strip render
- VIEW-04  ``test_refresh_tick_applies_without_block``  — off-thread poll marshals a result back
- VIEW-03  ``test_runs_table_rows_and_status_labels``   — one row per run, status WORD text, stable cursor
- SAFETY-02 ``test_no_write_invariant``                 — no bytes/mtime change to on-disk state
- SAFETY-02 ``test_view_has_no_write_or_subprocess_api`` — AST: no write/subprocess API in the view
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from rich.text import Text

from textual.widgets import DataTable, Input, Markdown, Sparkline, Static, TabbedContent

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline"
DASH_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "dashboard"
DASHBOARD_PY = REPO_ROOT / "scripts" / "dashboard" / "gmj_dashboard.py"
# MANAGE-06: the extended SAFETY-02 no-write AST test scans the VIEW + MODEL as a pair; the actions
# module (gmj_dashboard_actions.py) is DELIBERATELY excluded — it is the one place a config write +
# detached subprocess launch are legitimate (its own safety is proven by SAFETY-01 in Plan 24-01).
MODEL_PY = REPO_ROOT / "scripts" / "dashboard" / "gmj_dashboard_model.py"
CONFIG_SRC = REPO_ROOT / "config" / "pipeline.config.yaml"
# Stable seed for manage-mode config-edit tests — must not depend on the live repo config file.
_MANAGE_TEST_CONFIG = """\
# FREEZE CONTRACT: at run start, gmj_state_write.py copies these values into state.json.
execution_mode: human_in_the_loop
retry_cap: 4
"""

# Import the App + the model via the same sys.path idiom the model test uses.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dashboard"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_dashboard  # noqa: E402
import gmj_dashboard_actions as actions  # noqa: E402
import gmj_dashboard_model  # noqa: E402

# Keys that must NEVER be bound without --manage (VIEW-01) and MUST be bound with it (VIEW-07).
_MUTATING_KEYS = ("r", "R", "b", "m", "c")
# The REAL action name each mutating key must bind to under --manage (MANAGE-01) — NOT the inert noop.
_MANAGE_ACTIONS = {"r": "run", "R": "resume", "b": "batch", "m": "mode", "c": "cap"}


# ── fakes (mirror tests/test_gmj_dashboard_actions.py — no test spawns a REAL claude) ──────────────

class _FakeProc:
    """A stand-in async subprocess whose ``.wait`` / ``.communicate`` are spies (fire-and-forget proof)."""

    def __init__(self) -> None:
        self.wait_calls = 0
        self.communicate_calls = 0
        # 28-03: the sidecar writer records the child pid — a live self-pid keeps the reaper's
        # dead-pid prune from clearing a just-written sidecar mid-test (os.getpid() is always alive).
        self.pid = os.getpid()

    async def wait(self) -> int:
        self.wait_calls += 1
        return 0

    async def communicate(self):
        self.communicate_calls += 1
        return (b"", b"")


class _BlockingProc(_FakeProc):
    """A ``_FakeProc`` whose ``wait()`` never returns — so ``_watch_launch`` does NOT reap the sidecar
    during a launch-write assertion window (the sidecar-write test inspects disk while the child lives)."""

    async def wait(self) -> int:
        self.wait_calls += 1
        await asyncio.Event().wait()  # blocks forever — the child is treated as still alive
        return 0  # pragma: no cover — never reached


class _RecordingLauncher:
    """A fake launcher recording ``(argv, kwargs)`` and returning a fresh ``_FakeProc`` (never awaited)."""

    def __init__(self) -> None:
        self.argv: tuple = ()
        self.kwargs: dict = {}
        self.calls = 0
        self.proc = _FakeProc()

    async def __call__(self, *argv, **kwargs):
        self.calls += 1
        self.argv = argv
        self.kwargs = kwargs
        return self.proc


async def _aval(value):
    """A trivial coroutine so an overridden collector (``app._prompt_offer = lambda: _aval(x)``) awaits."""
    return value


# ── WR-01/HON-01: a relative --pipeline-dir must not diverge board vs launched child ────────────────

def test_relative_pipeline_dir_agrees_board_and_child() -> None:
    """A RELATIVE ``--pipeline-dir`` is absolutized ONCE so the read model and the launched child's
    ``GMJ_PIPELINE_DIR`` carrier point at the SAME dir regardless of launch cwd.

    The bug this guards (WR-01): the launch paths force the child ``cwd=REPO_ROOT`` while the model
    resolves ``--pipeline-dir`` against the dashboard's own process cwd — so a relative dir makes the
    child write ``<REPO_ROOT>/dir`` while the board reads ``<cwd>/dir`` (a stale board, HON-01 defeat).
    Deterministic — asserts on the resolved value only; no Textual Pilot render (avoids D-27-A flake).
    """
    resolved = gmj_dashboard.resolve_operator_pipeline_dir("relboard")
    assert Path(resolved).is_absolute(), f"a relative operator dir must be absolutized: {resolved!r}"

    # The read model projects exactly this absolute dir (expanduser on an absolute path is a no-op),
    # so the board is anchored to a cwd-independent root — not the dashboard's own process cwd.
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=resolved)
    assert str(model.pipeline_dir) == resolved, (
        f"the board must project the absolutized dir verbatim: {model.pipeline_dir!r} != {resolved!r}"
    )

    # The child env (the AUTHORITATIVE HON-01 carrier, built inside launch_pipeline) stamps the SAME
    # absolute dir — so a run launched with cwd=REPO_ROOT writes exactly where the board reads.
    launcher = _RecordingLauncher()

    async def _go():
        return await actions.launch_pipeline(
            "PROMPT-X", launcher=launcher, cwd=str(gmj_dashboard.REPO_ROOT), pipeline_dir=resolved
        )

    asyncio.run(_go())
    env = launcher.kwargs.get("env")
    assert env is not None and env.get("GMJ_PIPELINE_DIR") == resolved, (
        f"child env carrier must carry the absolutized dir: {env and env.get('GMJ_PIPELINE_DIR')!r}"
    )
    # The single load-bearing assertion: board and child agree on ONE absolute dir.
    assert env["GMJ_PIPELINE_DIR"] == str(model.pipeline_dir), (
        "board and launched child must resolve --pipeline-dir to the SAME absolute dir (HON-01)"
    )


@contextmanager
def _temp_pipeline():
    """Yield a Path to a throwaway COPY of tests/fixtures/pipeline/ (bug-proofs the committed corpus)."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "pipeline"
        shutil.copytree(FIXTURES, dst)
        yield dst


@contextmanager
def _temp_idle_pipeline():
    """Yield a pipeline dir with only terminal runs — no disk-backed live activity."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "pipeline"
        for run_id in ("20260601T120000-del", "20260603T120000-fail"):
            run_src = FIXTURES / "runs" / run_id
            run_dst = dst / "runs" / run_id
            run_dst.mkdir(parents=True)
            shutil.copy2(run_src / "state.json", run_dst / "state.json")
        yield dst


def _build_app(
    pipeline_dir: Path,
    *,
    manage: bool = False,
    refresh: float = 1.5,
    config_path: Path | None = None,
    launcher=None,
    repo_root: Path | None = None,
) -> "gmj_dashboard.GmjDashboard":
    """Construct the App around a pre-built model reading the temp pipeline + dashboard fixtures.

    ``config_path`` (a temp copy) and ``launcher`` (a recording fake) are the Plan 24-02 --manage seams;
    they default to the read-only behaviour so every pre-existing test is unaffected.
    """
    model = gmj_dashboard_model.DashboardModel(
        pipeline_dir=str(pipeline_dir), repo_root=repo_root or DASH_FIXTURES
    )
    return gmj_dashboard.GmjDashboard(
        model,
        manage=manage,
        refresh=refresh,
        config_path=config_path,
        launcher=launcher,
        pipeline_dir=str(pipeline_dir),
        cwd=REPO_ROOT,
    )


async def _settle(pilot, predicate, *, tries: int = 50, delay: float = 0.05) -> None:
    """Await the app's off-thread poll until ``predicate()`` holds (bounded).

    The poll runs ``model.snapshot()`` on a BACKGROUND THREAD (``run_worker(thread=True,
    exclusive=True, group="poll")``) and marshals rows back with ``call_from_thread(self._apply,
    snap)``; a fixed ``pilot.pause()`` count can return before that thread finishes under CPU
    contention (the documented 26/27/28 flake). This loop pauses AND yields wall-clock so the worker
    can complete and re-tick the ~0.1s interval, then re-checks the REAL seeding condition. It fails
    loudly so a genuine regression (predicate never true) still surfaces — never a silent infinite
    wait.
    """
    for _ in range(tries):
        await pilot.pause()
        if predicate():
            return
        await asyncio.sleep(delay)   # let the BG poll thread run + re-tick the ~0.1s interval
    await pilot.pause()
    if not predicate():
        raise AssertionError(f"predicate never settled after {tries} tries")


async def _bound_keys(pipeline_dir: Path, *, manage: bool) -> set[str]:
    """Launch, let the interval + first snapshot run, and return the set of bound keys."""
    app = _build_app(pipeline_dir, manage=manage)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        # app._bindings.key_to_bindings is private but stable in 6.x (21-RESEARCH A3); the public
        # fallback is App.check_action. We assert on the binding map directly here.
        return set(app._bindings.key_to_bindings.keys())


def _run_with_stderr(coro) -> str:
    """Run an async coroutine with stderr captured; return the captured stderr text."""
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        asyncio.run(coro)
    return buf.getvalue()


# --- VIEW-01: read-only launch binds no mutating keys -------------------------

async def _readonly_launcher_never_invoked(pipeline_dir: Path) -> int:
    """Read-only launch: inject a spy launcher, focus the table, press every mutating key → zero calls.

    Proves T-24-06: without --manage the mutating keys are genuinely unbound AND the launcher seam is
    never invoked (a keypress reaches no launch handler). Focusing the runs table takes focus off the
    filter Input so a bound letter key WOULD reach the App binding — yet in read-only none is bound.
    """
    app = _build_app(pipeline_dir, manage=False)
    spy = _RecordingLauncher()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        app._launcher = spy
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()
        for key in _MUTATING_KEYS:
            await pilot.press(key)
            await pilot.pause()
    return spy.calls


def test_readonly_no_mutating_bindings() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            bound = asyncio.run(_bound_keys(pipe, manage=False))
            launcher_calls = asyncio.run(_readonly_launcher_never_invoked(pipe))
        assert "Traceback" not in buf.getvalue(), f"read-only launch leaked a traceback: {buf.getvalue()}"
    for key in _MUTATING_KEYS:
        assert key not in bound, f"mutating key {key!r} must NOT be bound in read-only mode: {sorted(bound)}"
    assert "q" in bound, "the read-only quit key must be bound in read-only mode"
    # T-24-06: the launcher seam is NEVER invoked without --manage (pressing r/R/b reaches no handler).
    assert launcher_calls == 0, (
        f"the launcher must NEVER be invoked in read-only mode; recorded {launcher_calls} call(s)"
    )


# --- VIEW-07: --manage makes the footer mode-aware (mutating keys bound) ------

def test_footer_mode_aware_bindings() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            bound = asyncio.run(_bound_keys(pipe, manage=True))
        assert "Traceback" not in buf.getvalue(), f"--manage launch leaked a traceback: {buf.getvalue()}"
    for key in _MUTATING_KEYS:
        assert key in bound, f"mutating key {key!r} must be bound under --manage (footer mode-aware): {sorted(bound)}"
    assert "q" in bound, "the quit key must be bound under --manage too"


# --- VIEW-02: brand banner + global counters render --------------------------

async def _counters_and_banner(pipeline_dir: Path) -> tuple[str, str]:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(4):
            await pilot.pause()
        counters = app.query_one("#counters", Static).render()
        banner = app.query_one("#banner", Static).render()
        return str(counters), str(banner)


def test_header_and_counters_render() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            counters_text, banner_text = asyncio.run(_counters_and_banner(pipe))
        assert "Traceback" not in buf.getvalue(), f"render leaked a traceback: {buf.getvalue()}"
    # The counters strip is rendered generically from snapshot()["counters"].
    assert counters_text.strip(), f"counters strip must render non-empty text: {counters_text!r}"
    for label in ("runs", "offers", "default_mode", "cap"):
        assert label in counters_text, f"counters must carry the {label!r} label: {counters_text!r}"
    # The delivered headline number appears (rendered from by_status.items(), not a .py literal).
    assert re.search(r"delivered:\s*\d+", counters_text), (
        f"counters must show a numeric delivered count from by_status: {counters_text!r}"
    )
    assert "runs:" in counters_text, f"counters must use label: value form: {counters_text!r}"
    # The colored ASCII figlet + slogan render non-empty.
    assert banner_text.strip(), f"banner must render non-empty: {banner_text!r}"
    assert "| |__" in banner_text or "__ _ ___" in banner_text, f"banner must show ASCII figlet: {banner_text!r}"
    assert "Your career's wingman" in banner_text, f"banner must show the slogan: {banner_text!r}"


# --- VIEW-04: an off-thread poll tick applies a result without blocking -------

async def _tick_and_read_counters(pipeline_dir: Path) -> tuple[str, int]:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Two+ ticks let the threaded worker run snapshot() off-thread and marshal back via
        # call_from_thread — a blocking poll would never populate the strip.
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        counters = str(app.query_one("#counters", Static).render())
        # The app is still queryable/responsive (no hang, no leaked exception).
        row_count = app.query_one("#runs", DataTable).row_count
        return counters, row_count


def test_refresh_tick_applies_without_block() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            counters_text, row_count = asyncio.run(_tick_and_read_counters(pipe))
        assert "Traceback" not in buf.getvalue(), f"poll tick leaked a traceback: {buf.getvalue()}"
    assert counters_text.strip(), (
        "the counters strip must be populated by the threaded poll (call_from_thread marshalled a "
        f"snapshot back); a blocking poll would leave it empty: {counters_text!r}"
    )
    assert "runs" in counters_text, f"the applied counters must be snapshot-derived: {counters_text!r}"
    assert isinstance(row_count, int), "the app must stay queryable/responsive after the poll ticks"


# --- SAFETY-02: no disk write / no mtime change during launch + refresh -------

async def _launch_and_tick(pipeline_dir: Path) -> None:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()


def test_no_write_invariant() -> None:
    with _temp_pipeline() as pipe:
        # Snapshot bytes + st_mtime_ns of every state.json under the temp .pipeline/ ...
        before = {
            p: (p.read_bytes(), p.stat().st_mtime_ns) for p in pipe.rglob("state.json")
        }
        assert before, "the pipeline fixture must contain at least one state.json to prove no-write"
        # ... plus config/candidate.yaml (criterion 5 names it explicitly). It is read via repo_root.
        cand = DASH_FIXTURES / "config" / "candidate.yaml"
        assert cand.is_file(), f"the dashboard candidate fixture must exist: {cand}"
        before[cand] = (cand.read_bytes(), cand.stat().st_mtime_ns)

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            asyncio.run(_launch_and_tick(pipe))
        assert "Traceback" not in buf.getvalue(), f"launch+refresh leaked a traceback: {buf.getvalue()}"

        for path, (raw, mtime) in before.items():
            assert path.read_bytes() == raw, f"{path} bytes changed — the view must never write disk"
            assert path.stat().st_mtime_ns == mtime, f"{path} mtime changed — the view must never touch disk"


# --- SAFETY-02 / MANAGE-06: AST proof the VIEW *and* MODEL have no write / subprocess API ----------

def _no_write_or_subprocess_offenders(path: Path) -> list[str]:
    """AST-scan one module for any write / subprocess API. Returns the list of offenders (empty = clean).

    Identical detector to the original SAFETY-02 view scan, factored so Plan 24-02 can run it over BOTH
    the view and the model (MANAGE-06): open(write-mode), a banned write/exec attribute, or a
    subprocess reference/import. The actions module is never passed here — its config write + detached
    launch are legitimate and proven safe by SAFETY-01 in Plan 24-01.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    write_modes = {"w", "a", "x", "w+", "a+", "wb", "ab", "xb", "r+", "rb+"}
    banned_attrs = {"write_text", "write_bytes", "replace", "rename", "remove", "unlink", "system"}
    banned_module_names = {"subprocess"}
    exec_prefixes = ("exec", "spawn")  # os.exec* / os.spawn*

    offenders: list[str] = []

    for node in ast.walk(tree):
        # (a) open(..., <write-mode>) — a literal write/append/exclusive mode argument.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            for arg in node.args[1:]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value in write_modes:
                    offenders.append(f"{path.name}: open(mode={arg.value!r})")
            for kw in node.keywords:
                if (
                    kw.arg == "mode"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                    and kw.value.value in write_modes
                ):
                    offenders.append(f"{path.name}: open(mode={kw.value.value!r})")
        # (b) a banned write/subprocess attribute call: x.write_text(...), os.replace(...),
        #     os.remove(...), os.system(...), os.exec*/os.spawn*(...).
        if isinstance(node, ast.Attribute):
            if node.attr in banned_attrs:
                offenders.append(f"{path.name}: .{node.attr}")
            if node.attr.startswith(exec_prefixes) and node.attr not in ("execute",):
                offenders.append(f"{path.name}: .{node.attr}")
        # (c) a subprocess / os.system reference anywhere (import or attribute base).
        if isinstance(node, ast.Name) and node.id in banned_module_names:
            offenders.append(f"{path.name}: {node.id}")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in banned_module_names:
            offenders.append(f"{path.name}: {node.value.id}.{node.attr}")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = {a.name for a in node.names}
            if mod in banned_module_names or names & banned_module_names:
                offenders.append(f"{path.name}: import {mod or ','.join(sorted(names))}")

    return offenders


def test_view_has_no_write_or_subprocess_api() -> None:
    # MANAGE-06: the VIEW and the MODEL must BOTH stay write/subprocess-free — the view only ever CALLS
    # the actions module (lazily, under --manage); it never launches/writes itself. The actions module
    # is EXCLUDED (its config write + detached launch are legitimate, proven by SAFETY-01 in 24-01).
    offenders = _no_write_or_subprocess_offenders(DASHBOARD_PY) + _no_write_or_subprocess_offenders(MODEL_PY)
    assert not offenders, (
        f"the view + model must expose NO write/subprocess API (SAFETY-02/MANAGE-06): {offenders}"
    )


# --- VIEW-03 (+ strengthened VIEW-04): live runs table rows, status labels, stability -----------

# A well-formed fixture run with a clear projected status (composition documented in
# tests/test_gmj_dashboard_model.py). This test file lives under tests/, which the Phase-20 grep-guard
# does NOT scan, so it may freely name the status WORD it expects the status cell to render.
_KNOWN_RUN_ID = "20260601T120000-del"


async def _probe_runs_table(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll seed the table, then probe rows / status cell / cursor stability."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the REAL seeding condition (IN-02): the threaded poll seeds every run row via
        # _apply_runs (add_row keyed by run_id) — a fixed pause count races the ~0.1s worker. _settle
        # blocks on wall-clock and fails loudly if the rows never arrive (loud-fail guarantee).
        await _settle(pilot, lambda: app.query_one("#runs", DataTable).row_count > 0)
        table = app.query_one("#runs", DataTable)
        # The projection the view is rendering — one row per run (strayonly already excluded by model).
        expected_runs = app._model.snapshot()["runs"]

        # Move the cursor OFF the top row so a clear+refill / recompose would visibly reset it.
        table.move_cursor(row=1)
        cursor_before = table.cursor_row
        count_before = table.row_count

        # Another poll tick: a targeted update_cell diff keeps the cursor + row count; a recompose loses them.
        await pilot.pause()
        await pilot.pause()
        cursor_after = table.cursor_row
        count_after = table.row_count

        # Fetch the status column cell for a known run — it must be the status WORD as visible text.
        status_cell = table.get_cell(_KNOWN_RUN_ID, "status")
        status_plain = getattr(status_cell, "plain", None)
        if status_plain is None:
            status_plain = str(status_cell)
        by_id = {r["run_id"]: r for r in expected_runs}
        return {
            "row_count": table.row_count,
            "expected_count": len(expected_runs),
            "count_before": count_before,
            "count_after": count_after,
            "cursor_before": cursor_before,
            "cursor_after": cursor_after,
            "status_plain": status_plain,
            "known_status": by_id.get(_KNOWN_RUN_ID, {}).get("status"),
        }


def test_runs_table_rows_and_status_labels() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_runs_table(pipe))
        assert "Traceback" not in buf.getvalue(), f"runs table probe leaked a traceback: {buf.getvalue()}"

    # VIEW-03: exactly one row per projected run (the no-state strayonly dir is already excluded).
    assert probe["row_count"] == probe["expected_count"], (
        f"the runs table must render one row per projected run: "
        f"row_count={probe['row_count']} vs snapshot runs={probe['expected_count']}"
    )
    assert probe["row_count"] >= 1, f"the fixture corpus must yield at least one run row: {probe['row_count']}"

    # VIEW-03: the status CELL carries the status WORD as visible text (color paired with a label,
    # never color-only) and equals that run's projected status verbatim.
    assert probe["known_status"], f"the known fixture run {_KNOWN_RUN_ID!r} must project a status"
    assert probe["status_plain"] == probe["known_status"], (
        f"the status cell text must equal the projected status word: "
        f"cell={probe['status_plain']!r} projected={probe['known_status']!r}"
    )
    assert probe["status_plain"].strip(), f"the status cell must render a non-empty status word: {probe['status_plain']!r}"

    # Strengthened VIEW-04: targeted per-cell updates keep the row count AND the cursor stable across a
    # refresh tick — a clear()+refill or recompose() would rebuild the rows and snap the cursor to row 0.
    assert probe["count_after"] == probe["count_before"], (
        f"the row count must stay stable across a refresh tick (no clear+refill): "
        f"{probe['count_before']} -> {probe['count_after']}"
    )
    assert probe["cursor_after"] == probe["cursor_before"], (
        f"the row cursor must not jump on refresh (no recompose): {probe['cursor_before']} -> {probe['cursor_after']}"
    )
    assert probe["cursor_after"] != 0, (
        "the cursor must remain where the user put it (row 1), not snap back to the top row on a poll tick"
    )


# --- VIEW-05: domain-metrics panel + throughput sparkline --------------------

async def _probe_metrics_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill the metrics panel, then read its text + sparkline data."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the REAL seeding condition (metrics text marshalled back off-thread) rather than a
        # fixed pause count — a bare `pilot.pause()` triple races the ~0.1s poll worker and rotates into
        # the documented render-settle flake (29-01 retrofit; this probe was one the earlier pass missed).
        await _settle(pilot, lambda: str(app.query_one("#metrics", Static).render()).strip() != "")
        metrics_text = str(app.query_one("#metrics", Static).render())
        spark_data = app.query_one("#throughput", Sparkline).data
        return {"metrics_text": metrics_text, "spark_data": spark_data}


def test_metrics_panel_and_sparkline() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_metrics_panel(pipe))
        assert "Traceback" not in buf.getvalue(), f"metrics probe leaked a traceback: {buf.getvalue()}"

    text = probe["metrics_text"]
    assert text.strip(), f"the metrics panel must render non-empty text: {text!r}"
    # The panel carries the Gate A/B lines and the retry-vs-cap meter label...
    for label in ("Gate A", "Gate B", "retries"):
        assert label in text, f"the metrics panel must carry the {label!r} line: {text!r}"
    # ...and at least one status bar rendered from by_status (block glyphs paired with a count).
    assert "█" in text, f"the metrics panel must render at least one status bar glyph: {text!r}"

    # The throughput sparkline's .data is a non-empty list of ints reassigned in place each poll.
    data = probe["spark_data"]
    assert isinstance(data, list) and data, f"the sparkline .data must be a non-empty list: {data!r}"
    assert all(isinstance(x, int) for x in data), f"the sparkline .data must be all ints: {data!r}"


# --- VIEW-26: features catalog + configuration panels --------------------------

async def _probe_features_config(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill the features + config panels."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1, repo_root=REPO_ROOT)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the real seeding (features catalog marshalled off-thread) — a fixed pause triple
        # races the poll worker under CPU contention (the 29-01 render-settle flake class; this probe
        # was one the earlier retrofit pass missed).
        await _settle(pilot, lambda: app.query_one("#features-table", DataTable).row_count > 0)
        feat_table = app.query_one("#features-table", DataTable)
        feat_rows = [
            (
                str(feat_table.get_cell(rk, "kind")),
                str(feat_table.get_cell(rk, "name")),
            )
            for rk in feat_table.rows
        ]
        cfg_table = app.query_one("#config-table", DataTable)
        cfg_rows = [str(cfg_table.get_cell(rk, "file")) for rk in cfg_table.rows]
        return {
            "feat_rows": feat_rows,
            "feat_count": feat_table.row_count,
            "cfg_rows": cfg_rows,
            "cfg_text": "\n".join(cfg_rows),
            "config_count": cfg_table.row_count,
        }


def test_features_and_config_panels() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_features_config(pipe))
        assert "Traceback" not in buf.getvalue(), f"features/config probe leaked a traceback: {buf.getvalue()}"

    assert probe["feat_count"] >= 10, f"features table must list catalog items: {probe['feat_count']}"
    kinds = {k for k, _ in probe["feat_rows"]}
    assert "command" in kinds, f"expected command rows: {probe['feat_rows'][:5]}"
    assert any(name == "gmj-pipeline-run" for _, name in probe["feat_rows"]), probe["feat_rows"]

    cfg = probe["cfg_text"]
    assert probe["config_count"] >= 6, f"the config table must list yaml files: {probe['config_count']}"
    assert cfg.strip(), f"the config table must render rows: {cfg!r}"
    assert "config/pipeline.config.yaml" in cfg, f"missing pipeline.config.yaml: {cfg!r}"
    assert "config/sources.yaml" in cfg, f"missing sources.yaml: {cfg!r}"


async def _probe_features_drill_in(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1, repo_root=REPO_ROOT)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#features-table", DataTable).row_count > 0)
        table = app.query_one("#features-table", DataTable)
        table.focus()
        idx = None
        for i, rk in enumerate(table.rows):
            if str(table.get_cell(rk, "name")) == "gmj-pipeline-run":
                idx = table.get_row_index(rk)
                break
        assert idx is not None, "gmj-pipeline-run row must exist"
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        body = str(app.screen.query_one("#feat-modal-body", Static).render())
        header = str(app.screen.query_one("#feat-modal-header", Static).render())
        offer_input = app.screen.query_one("#feat-param-offer", Input)
        await pilot.press("escape")
        await pilot.pause()
        return {"body": body, "header": header, "offer_input": offer_input}


def test_features_table_drill_in() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_features_drill_in(pipe))
    assert "gmj-pipeline-run" in probe["header"] or "pipeline" in probe["body"].lower()
    assert probe["offer_input"] is not None


# --- VIEW-06 (legacy): configuration panel drill-in ----------------------------

async def _probe_config_drill_in(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#config-table", DataTable).row_count > 0)
        table = app.query_one("#config-table", DataTable)
        table.focus()
        idx = table.get_row_index("config/pipeline.config.yaml")
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        body = str(app.screen.query_one("#cfg-modal-body", Static).render())
        await pilot.press("escape")
        await pilot.pause()
        return {"top_name": type(app.screen).__name__, "body": body}


def test_config_table_drill_in() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_config_drill_in(pipe))
    assert "autonomous" in probe["body"]
    assert "config/pipeline.config.yaml" in probe["body"]
    assert "execution_mode" in probe["body"]


# --- DOCTAB-01/02/03: docs tab row-select -> modal -> content -> dismiss + fresh-read + empty-state ---

async def _probe_docs_drill_in(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#docs-table", DataTable).row_count > 0)
        table = app.query_one("#docs-table", DataTable)
        table.focus()
        idx = table.get_row_index("docs/alpha.md")
        table.move_cursor(row=idx)
        await pilot.press("enter")
        await pilot.pause()
        screen_type_open = type(app.screen).__name__
        body_markdown = app.screen.query_one("#doc-modal-body", Markdown)._markdown
        await pilot.press("escape")
        await pilot.pause()
        screen_type_after_escape = type(app.screen).__name__
        return {
            "screen_type_open": screen_type_open,
            "body_markdown": body_markdown,
            "screen_type_after_escape": screen_type_after_escape,
        }


def test_docs_table_drill_in() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_docs_drill_in(pipe))
    assert probe["screen_type_open"] == "DocFileModal"
    assert "docs/alpha.md" in probe["body_markdown"]
    assert "Alpha fixture body." in probe["body_markdown"]
    assert probe["screen_type_after_escape"] != "DocFileModal"


async def _probe_docs_reopen_after_change(pipeline_dir: Path) -> dict:
    """Open docs/alpha.md, dismiss, mutate the file on disk, reopen — proves no stale cache (DOCTAB-03)."""
    with tempfile.TemporaryDirectory() as tmp:
        dash_copy = Path(tmp) / "dashboard"
        shutil.copytree(DASH_FIXTURES, dash_copy)
        app = _build_app(pipeline_dir, manage=False, refresh=0.1, repo_root=dash_copy)
        async with app.run_test(size=(120, 40)) as pilot:
            await _settle(pilot, lambda: app.query_one("#docs-table", DataTable).row_count > 0)
            table = app.query_one("#docs-table", DataTable)
            table.focus()
            idx = table.get_row_index("docs/alpha.md")
            table.move_cursor(row=idx)
            await pilot.press("enter")
            await pilot.pause()
            first_markdown = app.screen.query_one("#doc-modal-body", Markdown)._markdown
            await pilot.press("escape")
            await pilot.pause()

            (dash_copy / "docs" / "alpha.md").write_text(
                "# Alpha Fixture Doc\n\nUPDATED alpha fixture body after on-disk change.\n",
                encoding="utf-8",
            )

            table = app.query_one("#docs-table", DataTable)
            table.focus()
            idx = table.get_row_index("docs/alpha.md")
            table.move_cursor(row=idx)
            await pilot.press("enter")
            await pilot.pause()
            second_markdown = app.screen.query_one("#doc-modal-body", Markdown)._markdown
            await pilot.press("escape")
            await pilot.pause()
            return {"first_markdown": first_markdown, "second_markdown": second_markdown}


def test_docs_reopen_shows_updated_content() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_docs_reopen_after_change(pipe))
    assert "UPDATED alpha fixture body after on-disk change." not in probe["first_markdown"]
    assert "UPDATED alpha fixture body after on-disk change." in probe["second_markdown"]


async def _probe_docs_empty_state(pipeline_dir: Path, empty_repo_root: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1, repo_root=empty_repo_root)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(
            pilot,
            lambda: str(app.query_one("#docs-placeholder", Static).render()).strip() != "",
        )
        placeholder_text = str(app.query_one("#docs-placeholder", Static).render()).strip()
        row_count = app.query_one("#docs-table", DataTable).row_count
        return {"placeholder_text": placeholder_text, "row_count": row_count}


def test_docs_empty_state_shows_placeholder() -> None:
    with _temp_pipeline() as pipe:
        with tempfile.TemporaryDirectory() as tmp:
            probe = asyncio.run(_probe_docs_empty_state(pipe, Path(tmp)))
    assert probe["placeholder_text"] == "(no docs found)"
    assert probe["row_count"] == 0


# --- VIEW-08: DAG stage strip renders tokens, highlights an active run, colors gates ------------

# A well-formed fixture run with a truthy current_step and both gates recorded (composition dumped
# from the real model). This test file lives under tests/, which the grep-guard does NOT scan, so it
# may name the gate verdict WORD it expects the strip to render.
_DAG_RUN_ID = "20260601T120000-del"
_DAG_RUN_STEP = "gmj-cv-generator"


async def _probe_dag_strip(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill the #dag-placeholder panel, then probe text + style spans."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle until the threaded poll marshals snapshot()["stages"] back into the strip.
        await _settle(pilot, lambda: str(app.query_one("#dag-placeholder", Static).render()).strip() != "")
        panel = app.query_one("#dag-placeholder", Static)
        rendered = str(panel.render())
        # Static.update(out) stores the ORIGINAL Rich Text in the name-mangled __content attribute
        # (textual 6.1 has no public `.renderable`); read it to inspect the applied style spans. The
        # suite already reads private internals (e.g. app._bindings.key_to_bindings) by convention.
        renderable = getattr(panel, "_Static__content", None)
        dag = app._model.snapshot()["stages"]["dag"]
        # Collect the non-empty style spans off the Rich Text (proves color was applied inline).
        spans = getattr(renderable, "spans", [])
        nonempty_styles = [str(sp.style) for sp in spans if sp.style]
        return {
            "rendered": rendered,
            "is_text": isinstance(renderable, Text),
            "dag": dag,
            "nonempty_style_count": len(nonempty_styles),
        }


def test_dag_strip_renders_and_highlights() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_dag_strip(pipe))
        assert "Traceback" not in buf.getvalue(), f"DAG strip probe leaked a traceback: {buf.getvalue()}"

    rendered = probe["rendered"]
    assert rendered.strip(), f"the DAG strip must render non-empty text: {rendered!r}"

    # VIEW-08: every config-read dag token appears in the static strip row.
    assert probe["dag"], "the fixture dag must carry at least one stage token"
    for token in probe["dag"]:
        assert token in rendered, f"the DAG strip must render the dag token {token!r}: {rendered!r}"

    # VIEW-08: a known active run's line carries its run_id + highlighted current_step.
    assert _DAG_RUN_ID in rendered, f"the DAG strip must show the active run_id {_DAG_RUN_ID!r}: {rendered!r}"
    assert _DAG_RUN_STEP in rendered, (
        f"the DAG strip must show the active run's current_step {_DAG_RUN_STEP!r}: {rendered!r}"
    )

    # VIEW-08: the Gate A/B labels and a pass verdict appear on that run's line.
    assert "A:" in rendered and "B:" in rendered, f"the DAG strip must label the Gate A/B verdicts: {rendered!r}"
    assert "pass" in rendered, f"the DAG strip must render the projected gate verdict word: {rendered!r}"

    # VIEW-08: coloring is applied inline via theme vars — the renderable is a Rich Text carrying at
    # least one non-empty style span (the accent current_step / the gate-pass verdict / the separators).
    assert probe["is_text"], "the #dag-placeholder renderable must be a Rich Text (colored spans, not plain text)"
    assert probe["nonempty_style_count"] >= 1, (
        f"the DAG strip must carry at least one non-empty style span (projection-colored): "
        f"found {probe['nonempty_style_count']}"
    )


# --- VIEW-09: run drill-in modal — enter opens it, resume printed-not-run, escape pops it --------

# The known-good fixture run has a full, well-formed run_detail payload (status delivered, both gates
# pass, an offer hash, a resume command string). These substrings were dumped from the live model;
# this test file lives under tests/, which the grep-guard does NOT scan, so it may name them freely.
_DRILL_RUN_ID = "20260601T120000-del"
_DRILL_OFFER_HASH_SUBSTR = "aaaa0000"                       # prefix of offer_spec_hash
_DRILL_ARTIFACT = "gate_gmj-fit-evaluator_cv_1.json"        # a run-dir artifact/attempt filename
_DRILL_RESUME_SUBSTR = "run_id=20260601T120000-del"          # inside the resume command string only


async def _probe_drill_in_modal(pipeline_dir: Path) -> dict:
    """Launch read-only, cursor to a known run, enter→modal, read the frozen body, escape→pop."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle until the threaded poll seeds the runs table (add_row keyed by run_id).
        await _settle(pilot, lambda: app.query_one("#runs", DataTable).row_count > 0)
        table = app.query_one("#runs", DataTable)
        table.focus()
        # Position the row cursor on the known-good run — with the table focused, enter is consumed by
        # the DataTable and surfaces as RowSelected (an App-level enter binding would be swallowed).
        idx = table.get_row_index(_DRILL_RUN_ID)
        table.move_cursor(row=idx)
        await pilot.pause()

        stack_before = len(app.screen_stack)
        await pilot.press("enter")
        await pilot.pause()
        stack_open = len(app.screen_stack)
        top_name = type(app.screen).__name__
        # The frozen modal body (namespaced #modal-body id, distinct from every base-screen id).
        body = str(app.screen.query_one("#modal-body", Static).render())

        # A poll tick WHILE the modal is on top must keep the base panels queryable with zero errors
        # (Pitfall 3 — distinct ids mean the poll's query_one never raises TooManyMatches).
        await pilot.pause()
        await pilot.pause()
        base_counters = str(app.query_one("#counters", Static).render())

        # escape pops the modal back to the base screen (built-in Screen.action_dismiss).
        await pilot.press("escape")
        await pilot.pause()
        stack_closed = len(app.screen_stack)
        return {
            "stack_before": stack_before,
            "stack_open": stack_open,
            "top_name": top_name,
            "body": body,
            "base_counters": base_counters,
            "stack_closed": stack_closed,
        }


def test_drill_in_modal_open_and_resume_printed_not_run() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_drill_in_modal(pipe))
        # Poll-underneath non-interference: no traceback while the modal was open across poll ticks.
        assert "Traceback" not in buf.getvalue(), f"drill-in modal leaked a traceback: {buf.getvalue()}"

    # VIEW-09: enter on the focused, cursor-positioned runs row PUSHES the modal (screen_stack 1→2).
    assert probe["stack_before"] == 1, f"the base screen must be the only screen before enter: {probe['stack_before']}"
    assert probe["stack_open"] == 2, (
        f"enter on the focused runs row must push RunDetailModal (screen_stack 1→2): {probe['stack_open']}"
    )
    assert probe["top_name"] == "RunDetailModal", f"the top screen must be RunDetailModal: {probe['top_name']!r}"

    # VIEW-09: the frozen run_detail payload is rendered — run_id, offer hash, an artifact/attempt
    # filename, and (proving the resume string is DISPLAYED) the resume command's run_id= substring.
    body = probe["body"]
    assert _DRILL_RUN_ID in body, f"the modal body must show the run_id: {body!r}"
    assert _DRILL_OFFER_HASH_SUBSTR in body, f"the modal body must show the offer hash: {body!r}"
    assert _DRILL_ARTIFACT in body, f"the modal body must show an artifact/attempt filename: {body!r}"
    assert _DRILL_RESUME_SUBSTR in body, (
        f"the modal body must DISPLAY the resume command verbatim (present, not executed): {body!r}"
    )
    # The proof that the resume command is NEVER EXECUTED is the standing AST invariant
    # test_view_has_no_write_or_subprocess_api (no subprocess/write API exists anywhere in the view
    # module) combined with this assertion that the command string is merely PRESENT in the modal body.

    # Pitfall 3: the poll kept updating the base panels underneath the modal with zero errors.
    assert probe["base_counters"].strip(), (
        f"the base counters must stay populated by the poll while the modal is open: {probe['base_counters']!r}"
    )
    assert "runs" in probe["base_counters"], f"the base panel must stay snapshot-queryable under the modal: {probe['base_counters']!r}"

    # VIEW-09: escape pops the modal back to the base screen (screen_stack 2→1).
    assert probe["stack_closed"] == 1, f"escape must pop the modal back to the base screen (2→1): {probe['stack_closed']}"


# --- VIEW-10: found-vacancies rows + batch delivered/total rollup render from the projection ------

# Known fixture facts (dumped from the live model over tests/fixtures/dashboard + tests/fixtures/
# pipeline): two frozen offers — Backend Engineer / TestCorp / senior / 4000-6000 USD / 3 must-haves,
# and Frontend Developer / WidgetWorks / middle / null salary / 2 must-haves — plus one batch
# batch-20260601T120000 with delivered=3 / total=6. This test file lives under tests/, which the
# Phase-20 grep-guard does NOT scan, so it may name the batch status/rollup values freely.
_VAC_TITLE = "Backend Engineer"
_VAC_COMPANY = "TestCorp"
_VAC_SENIORITY = "senior"
_VAC_MUST_HAVES = 3
_BATCH_ID = "batch-20260601T120000"
_BATCH_ROLLUP = "3/6"


async def _probe_vacancies_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill vacancies table + batch footer, return rendered state."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#vacancies", DataTable).row_count == 2)
        table = app.query_one("#vacancies", DataTable)
        batches = str(app.query_one("#vac-batches", Static).render())
        rows = []
        for rk in table.rows:
            rows.append(
                " ".join(
                    str(table.get_cell(rk, col))
                    for _, col in (
                        ("title", "title"),
                        ("company", "company"),
                        ("seniority", "seniority"),
                        ("salary", "salary"),
                        ("mh", "mh"),
                    )
                )
            )
        return {"row_count": table.row_count, "rows_text": "\n".join(rows), "batches": batches}


async def _probe_empty_vacancies_panel() -> dict:
    """Launch over an empty pipeline + repo_root with no offers → expect empty-state copy."""
    with tempfile.TemporaryDirectory() as tmp:
        empty_pipe = Path(tmp) / "pipeline"
        empty_root = Path(tmp) / "root"
        empty_pipe.mkdir()
        empty_root.mkdir()
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(empty_pipe), repo_root=empty_root)
        app = gmj_dashboard.GmjDashboard(model, manage=False, refresh=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            table = app.query_one("#vacancies", DataTable)
            batches = str(app.query_one("#vac-batches", Static).render())
            return {"row_count": table.row_count, "batches": batches}


def test_vacancies_and_batch_rollup_render() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            vac = asyncio.run(_probe_vacancies_panel(pipe))
            empty = asyncio.run(_probe_empty_vacancies_panel())
        assert "Traceback" not in buf.getvalue(), f"vacancies probe leaked a traceback: {buf.getvalue()}"

    vac_text = vac["rows_text"] + "\n" + vac["batches"]
    empty_text = empty["batches"]
    assert vac["row_count"] == 2, f"two frozen offers must appear as table rows: {vac['row_count']}"
    assert vac_text.strip(), f"the vacancies panel must render non-empty text: {vac_text!r}"
    for field in (_VAC_TITLE, _VAC_COMPANY, _VAC_SENIORITY):
        assert field in vac_text, f"the vacancies panel must show the offer field {field!r}: {vac_text!r}"
    assert re.search(rf"\b{_VAC_MUST_HAVES}\b", vac_text), (
        f"the vacancies panel must show the must-have count {_VAC_MUST_HAVES}: {vac_text!r}"
    )
    for token in ("4000", "6000", "USD"):
        assert token in vac_text, f"the vacancies panel must show the salary token {token!r}: {vac_text!r}"
    assert _BATCH_ID in vac_text, f"the vacancies panel must show the batch id {_BATCH_ID!r}: {vac_text!r}"
    assert _BATCH_ROLLUP in vac_text, (
        f"the vacancies panel must show the batch delivered/total rollup {_BATCH_ROLLUP!r}: {vac_text!r}"
    )
    # CONC-04: the per-batch line must also show the 5-token by_offer_status breakdown, additively,
    # alongside the unchanged aggregate segment above -- including zero-count tokens (never omitted).
    # Fixture facts (per Plan 35-03's worked example over batch-20260601T120000): offer 0's runs
    # (delivered, delivered, waiting) worst-case to the "waiting" bucket; offer 1's runs
    # (gate_exhausted, in_flight, delivered) worst-case to the "gate_exhausted" bucket.
    for present_token in ("waiting:1", "gate_exhausted:1"):
        assert present_token in vac_text, (
            f"the vacancies panel must show the by_offer_status token {present_token!r}: {vac_text!r}"
        )
    for zero_token in ("error:0", "delivered:0", "in_flight:0"):
        assert zero_token in vac_text, (
            f"the vacancies panel must show the zero-count by_offer_status token {zero_token!r} "
            f"(zero counts are never omitted): {vac_text!r}"
        )
    assert empty["row_count"] == 0, f"empty offers must render zero table rows: {empty['row_count']}"
    assert "No frozen offers" in empty_text, f"the empty vacancies panel must show 'No frozen offers': {empty_text!r}"
    assert "No batches" in empty_text, f"the empty vacancies panel must show 'No batches': {empty_text!r}"


_VAC_ALPHA_HASH = "aaaa1111"
_VAC_MUST_HAVE_ITEM = "PostgreSQL"


async def _probe_vacancies_filter(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the FULL projected count before typing the filter, so the "narrows to subset"
        # and "clearing restores" assertions stay meaningful.
        await _settle(pilot, lambda: app.query_one("#vacancies", DataTable).row_count == 2)
        table = app.query_one("#vacancies", DataTable)
        full_count = table.row_count
        filt = app.query_one("#vac-filter", Input)
        filt.value = "Backend"
        await pilot.pause()
        narrowed = table.row_count
        filt.value = ""
        await pilot.pause()
        restored = table.row_count
        return {"full": full_count, "narrowed": narrowed, "restored": restored}


def test_vacancies_filter_narrows_table() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_vacancies_filter(pipe))
    assert probe["full"] == 2, f"fixture must expose two vacancy rows before filter: {probe['full']}"
    assert probe["narrowed"] == 1, f"filter 'Backend' must keep one row: {probe['narrowed']}"
    assert probe["restored"] == 2, f"clearing the filter must restore both rows: {probe['restored']}"


async def _probe_vacancy_drill_in(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#vacancies", DataTable).row_count > 0)
        table = app.query_one("#vacancies", DataTable)
        table.focus()
        idx = table.get_row_index(_VAC_ALPHA_HASH)
        table.move_cursor(row=idx)
        await pilot.pause()
        stack_before = len(app.screen_stack)
        await pilot.press("enter")
        await pilot.pause()
        stack_open = len(app.screen_stack)
        top_name = type(app.screen).__name__
        body = str(app.screen.query_one("#vac-modal-body", Static).render())
        await pilot.pause()
        await pilot.pause()
        base_counters = str(app.query_one("#counters", Static).render())
        await pilot.press("escape")
        await pilot.pause()
        stack_closed = len(app.screen_stack)
        return {
            "stack_before": stack_before,
            "stack_open": stack_open,
            "top_name": top_name,
            "body": body,
            "base_counters": base_counters,
            "stack_closed": stack_closed,
        }


def test_vacancy_drill_in_modal_open() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_vacancy_drill_in(pipe))
        assert "Traceback" not in buf.getvalue(), buf.getvalue()
    assert probe["stack_before"] == 1
    assert probe["stack_open"] == 2
    assert probe["top_name"] == "VacancyDetailModal"
    assert _VAC_TITLE in probe["body"]
    assert _VAC_MUST_HAVE_ITEM in probe["body"]
    assert probe["base_counters"].strip()
    assert probe["stack_closed"] == 1


# --- TEST-03 (HON-03): a live resume child flips the run-status cell to the in-flight overlay ------

# Deterministic — asserts DIRECTLY on the pure ``_table_status`` `Text` return (`.plain` + `.style`),
# never on a rendered Pilot frame. The overlay branch fires purely off an in-memory
# ``_launched_runs[rid]`` entry whose child reads as alive (a ``_FakeProc`` has NO ``returncode``
# attribute, so ``getattr(proc, "returncode", None) is None`` → True). No disk write, no timing,
# no ``_settle`` — mutating only ``app._launched_runs`` inside a throwaway ``_temp_pipeline()``
# (T-29-06: run state is never touched on disk).
_INFLIGHT_RUN_ID = "20260601T120000-del"
_INFLIGHT_PROJECTED = "delivered"


async def _probe_inflight_overlay(pipeline_dir: Path) -> dict:
    """Build the app, snapshot ``_table_status`` with NO live child, then seed one and re-snapshot."""
    app = _build_app(pipeline_dir, manage=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        rid = _INFLIGHT_RUN_ID
        # No live child in _launched_runs → the cell shows the projected status VERBATIM.
        normal = app._table_status(rid, _INFLIGHT_PROJECTED)
        # A live resume child (no returncode → alive) sits under this run_id → the cell flips.
        app._launched_runs[rid] = _FakeProc()
        inflight = app._table_status(rid, _INFLIGHT_PROJECTED)
        return {
            "normal_plain": normal.plain,
            "normal_style": str(normal.style),
            "inflight_plain": inflight.plain,
            "inflight_style": str(inflight.style),
            "token": app._inflight_status_token(),
        }


def test_resume_shows_inflight_overlay() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_inflight_overlay(pipe))
        assert "Traceback" not in buf.getvalue(), f"in-flight overlay probe leaked a traceback: {buf.getvalue()}"

    # No live child → the projected status is returned verbatim (no overlay).
    assert probe["normal_plain"] == _INFLIGHT_PROJECTED, (
        f"with no live child the cell must show the projected status verbatim: {probe['normal_plain']!r}"
    )
    # A live resume child flips the cell to the distinct in-flight token ("running").
    assert probe["token"] == "running", f"the in-flight token must be 'running': {probe['token']!r}"
    assert probe["inflight_plain"] == probe["token"] == "running", (
        f"a live resume child must flip the cell to the in-flight token: {probe['inflight_plain']!r}"
    )
    # The overlay applies a DISTINCT style (in-flight color != frozen-status color).
    assert probe["inflight_style"] != probe["normal_style"], (
        f"the in-flight overlay must apply a distinct style vs the frozen status: "
        f"{probe['inflight_style']!r} == {probe['normal_style']!r}"
    )


# --- VIEW-11: built-in command palette opens + filter Input narrows the runs table ---------------

# A distinguishing filter substring: "del" matches the -del run by run_id AND the three delivered runs
# by status ("delivered"), a strict subset (3) of the 7 fixture runs — so it proves the view-only
# predicate narrows over already-projected run_id/status VALUES. This test file lives under tests/,
# which the Phase-20 grep-guard does NOT scan, so it may name the status word freely.
_FILTER_SUBSTR = "del"
_FILTER_CURSOR_RUN = "20260601T120000-del"  # a surviving run to park the cursor on (proves stability)


async def _probe_command_palette() -> tuple[bool, str]:
    """Launch read-only and open the built-in command palette with ctrl+p; report the top-screen type."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=False, refresh=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("ctrl+p")
            await pilot.pause()
            from textual.command import CommandPalette

            return isinstance(app.screen, CommandPalette), type(app.screen).__name__


def test_command_palette_opens() -> None:
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        is_palette, top_name = asyncio.run(_probe_command_palette())
    assert "Traceback" not in buf.getvalue(), f"command palette open leaked a traceback: {buf.getvalue()}"
    # VIEW-11: the built-in palette (ENABLE_COMMAND_PALETTE stays default True) opens on ctrl+p.
    assert is_palette, f"ctrl+p must open the built-in CommandPalette; top screen was {top_name!r}"


async def _probe_filter_narrows() -> dict:
    """Launch read-only, seed the table, drive the #filter Input, and probe narrowing + stability."""
    from textual.widgets import Input

    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=False, refresh=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            # Settle on the FULL projected run set (via _apply_runs) BEFORE parking the cursor and
            # typing, so the "strict subset" and "cursor stays" assertions remain meaningful.
            await _settle(
                pilot,
                lambda: app.query_one("#runs", DataTable).row_count
                == len(app._model.snapshot()["runs"]),
            )
            table = app.query_one("#runs", DataTable)
            full_count = table.row_count
            status_by_id = {r["run_id"]: r["status"] for r in (app._last_snap or {}).get("runs", [])}

            # Park the cursor on a surviving run so a clear()+refill would visibly snap it back to row 0.
            table.move_cursor(row=table.get_row_index(_FILTER_CURSOR_RUN))
            cursor_before = table.cursor_row

            # Drive the real filter Input (focus + type) — the persistent predicate narrows the table.
            inp = app.query_one("#filter", Input)
            inp.focus()
            await pilot.pause()
            for ch in _FILTER_SUBSTR:
                await pilot.press(ch)
            await pilot.pause()
            filtered_count = table.row_count
            filtered_ids = [str(k.value) for k in table.rows]
            cursor_after = table.cursor_row

            # A poll tick must NOT resurrect the filtered-out rows (Pitfall 4 — persistent predicate).
            await pilot.pause()
            await pilot.pause()
            after_poll_count = table.row_count
            after_poll_ids = [str(k.value) for k in table.rows]

            # Clearing the filter restores the full projected row set.
            inp.value = ""
            await pilot.pause()
            restored_count = table.row_count

            return {
                "full_count": full_count,
                "filtered_count": filtered_count,
                "filtered_ids": filtered_ids,
                "status_by_id": status_by_id,
                "cursor_before": cursor_before,
                "cursor_after": cursor_after,
                "after_poll_count": after_poll_count,
                "after_poll_ids": after_poll_ids,
                "restored_count": restored_count,
            }


def test_filter_narrows_runs_table() -> None:
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        probe = asyncio.run(_probe_filter_narrows())
    assert "Traceback" not in buf.getvalue(), f"filter probe leaked a traceback: {buf.getvalue()}"

    # VIEW-11: the filter narrows the runs table to a STRICT subset of the projected rows.
    assert probe["full_count"] >= 2, f"the fixture corpus must yield multiple run rows: {probe['full_count']}"
    assert 0 < probe["filtered_count"] < probe["full_count"], (
        f"the filter must narrow the runs table to a strict subset: "
        f"{probe['filtered_count']} of {probe['full_count']}"
    )

    # VIEW-11: EVERY surviving row matches the substring over its projected run_id OR status (the exact
    # view-only predicate — no new data source), proving the narrowing is by projection value.
    for rid in probe["filtered_ids"]:
        status = str(probe["status_by_id"].get(rid, ""))
        assert _FILTER_SUBSTR in rid.lower() or _FILTER_SUBSTR in status.lower(), (
            f"surviving row {rid!r} (status {status!r}) must match the filter {_FILTER_SUBSTR!r}"
        )

    # VIEW-11 / Pitfall 4: a poll tick does NOT resurrect filtered-out rows (persistent predicate).
    assert probe["after_poll_count"] == probe["filtered_count"], (
        f"a poll tick must not resurrect filtered-out rows: {probe['filtered_count']} -> {probe['after_poll_count']}"
    )
    assert set(probe["after_poll_ids"]) == set(probe["filtered_ids"]), (
        "the surviving row set must be identical after a poll tick (no resurrection)"
    )

    # VIEW-11: the cursor stays on its surviving run (targeted remove/add diff, not clear()+refill) —
    # it must NOT snap back to row 0 the way a rebuild would.
    assert probe["cursor_after"] != 0, (
        "the cursor must stay on its surviving run, not snap to row 0 (proving a targeted diff, not clear+refill)"
    )

    # VIEW-11: clearing the filter restores the full projected row set.
    assert probe["restored_count"] == probe["full_count"], (
        f"clearing the filter must restore every projected row: "
        f"{probe['restored_count']} vs {probe['full_count']}"
    )


# --- VIEW-15: commands panel lists mode-aware key/action rows --------------------------------------

async def _probe_commands_panel(pipeline_dir: Path, *, manage: bool) -> str:
    """Launch (read-only or --manage), let on_mount seed the static commands panel, read its text."""
    app = _build_app(pipeline_dir, manage=manage, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        return str(app.query_one("#commands", Static).render())


def test_commands_panel_mode_aware() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            ro = asyncio.run(_probe_commands_panel(pipe, manage=False))
            mg = asyncio.run(_probe_commands_panel(pipe, manage=True))
        assert "Traceback" not in buf.getvalue(), f"commands panel leaked a traceback: {buf.getvalue()}"

    # VIEW-15: both modes list key/action rows — the always-present read-only keys plus the _MANAGE_KEYS.
    for text in (ro, mg):
        assert text.strip(), f"the commands panel must render non-empty rows: {text!r}"
        assert "q" in text and "quit" in text, f"the commands panel must list the read-only quit key: {text!r}"
        assert "enter" in text and "drill-in" in text, f"the commands panel must list the drill-in key: {text!r}"
        assert "Run" in text, f"the commands panel must list a mutating _MANAGE_KEYS action row: {text!r}"

    # VIEW-15: a mutating key row's mode column DIFFERS between read-only and --manage. Read-only marks
    # the manage keys as Phase-24-deferred; under --manage they carry the active (--manage) mode.
    assert "Phase 24" in ro, f"read-only mode must annotate the manage keys as Phase-24-deferred: {ro!r}"
    assert "Phase 24" not in mg, f"--manage mode must NOT annotate the manage keys as deferred: {mg!r}"

    # HON-03: the commands panel carries the frozen-vs-live legend in plain, grep-guard-safe words —
    # a marked run = a live in-flight child this session; an unmarked run = frozen on-disk status from
    # the last poll. The legend is mode-independent (informational in both modes).
    for text in (ro, mg):
        assert "in-flight" in text, (
            f"the commands panel must name the live in-flight marker in the legend: {text!r}"
        )
        assert "frozen" in text, (
            f"the commands panel must name the frozen on-disk status in the legend: {text!r}"
        )
        assert "last poll" in text, (
            f"the legend must attribute the frozen status to the last poll: {text!r}"
        )


# --- VIEW-16: debug/internals panel renders the selected run's run_detail on selection --------------

# The enriched Gate A fail fixture carries a full run_detail payload (offer hash cccc0000…, retry
# counts, current_step). This test file lives under tests/, which the grep-guard does NOT scan, so it
# may name the current_step value the panel renders from the payload.
_DEBUG_RUN_ID = "20260603T120000-fail"
_DEBUG_OFFER_HASH_SUBSTR = "cccc0000"      # prefix of offer_spec_hash
_DEBUG_STEP_VALUE = "gmj-truth-verifier"    # current_step payload value (rendered as data, not a literal)


async def _probe_debug_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, read the empty state, cursor to a known run, enter, read #debug internals."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Two+ ticks let the poll paint the empty-state #debug before any selection.
        await pilot.pause()
        await pilot.pause()
        empty = str(app.query_one("#debug", Static).render())

        table = app.query_one("#runs", DataTable)
        table.focus()
        idx = table.get_row_index(_DEBUG_RUN_ID)
        table.move_cursor(row=idx)
        await pilot.pause()
        await pilot.press("enter")   # RowSelected → _apply_debug sets the panel BEFORE the drill-in modal
        await pilot.pause()

        # #debug is a unique base-screen id — reachable via App.query_one even under the drill-in modal.
        selected = str(app.query_one("#debug", Static).render())
        return {"empty": empty, "selected": selected}


def test_debug_panel_on_selection() -> None:
    with _temp_idle_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_debug_panel(pipe))
        assert "Traceback" not in buf.getvalue(), f"debug panel leaked a traceback: {buf.getvalue()}"

    # VIEW-16: the empty state renders before any row is selected.
    assert "Select a run for internals" in probe["empty"], (
        f"the debug panel must show the empty-state copy before selection: {probe['empty']!r}"
    )

    # VIEW-16: after enter on the known run, the panel renders that run's run_detail internals — the
    # run_id, the offer-hash substring, and a retry/current-step field (proving live internals).
    sel = probe["selected"]
    assert _DEBUG_RUN_ID in sel, f"the debug panel must show the selected run_id: {sel!r}"
    assert _DEBUG_OFFER_HASH_SUBSTR in sel, f"the debug panel must show the offer hash: {sel!r}"
    assert _DEBUG_STEP_VALUE in sel, f"the debug panel must show the current_step internal: {sel!r}"
    assert "retries" in sel or "retry" in sel, f"the debug panel must show a retry field: {sel!r}"


# --- VIEW-12: errors panel renders failed runs' Gate A/Gate B failure detail, red-forward -----------

# The enriched fail fixtures: 20260603T120000-fail carries a Gate A fail with offending_claims
# (numeric_invention / scope_inflation), 20260602T120000-run-ws a Gate B fail with missing_ids
# ["mh-2","mh-3"]. This test file lives under tests/, which the grep-guard does NOT scan, so it may
# name the failed run id + the rule/missing-id values the panel renders from the projection.
_ERR_RUN_ID = "20260603T120000-fail"
_ERR_GATE_A_RULE = "numeric_invention"     # a Gate A offending_claims rule_violated value
_ERR_GATE_B_MISSING = "mh-2"                # a Gate B missing must-have id


async def _probe_errors_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill #errors, then probe text + applied style spans."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the real seeding (IN-02): the failure detail is marshalled off-thread into #errors —
        # a fixed pause count races the ~0.1s poll worker. _settle blocks and fails loudly if it never fills.
        await _settle(pilot, lambda: str(app.query_one("#errors", Static).render()).strip() != "")
        panel = app.query_one("#errors", Static)
        rendered = str(panel.render())
        # Static.update(out) stores the ORIGINAL Rich Text in the name-mangled __content attribute
        # (textual 6.1 has no public `.renderable`); read it to inspect the applied red style spans —
        # the same private-internals convention the DAG-strip test uses.
        renderable = getattr(panel, "_Static__content", None)
        spans = getattr(renderable, "spans", [])
        nonempty_styles = [str(sp.style) for sp in spans if sp.style]
        return {
            "rendered": rendered,
            "is_text": isinstance(renderable, Text),
            "nonempty_style_count": len(nonempty_styles),
        }


async def _probe_empty_errors_panel() -> str:
    """Launch over an empty pipeline → expect the `No failures` empty-state copy."""
    with tempfile.TemporaryDirectory() as tmp:
        empty_pipe = Path(tmp) / "pipeline"
        empty_root = Path(tmp) / "root"
        empty_pipe.mkdir()
        empty_root.mkdir()
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(empty_pipe), repo_root=empty_root)
        app = gmj_dashboard.GmjDashboard(model, manage=False, refresh=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return str(app.query_one("#errors", Static).render())


def test_errors_panel_renders() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_errors_panel(pipe))
            empty_text = asyncio.run(_probe_empty_errors_panel())
        assert "Traceback" not in buf.getvalue(), f"errors panel leaked a traceback: {buf.getvalue()}"

    rendered = probe["rendered"]
    assert rendered.strip(), f"the errors panel must render non-empty text: {rendered!r}"

    # VIEW-12: the failed run_id, a Gate A offending-claim detail, and a Gate B missing must-have id.
    assert _ERR_RUN_ID in rendered, f"the errors panel must show the failed run_id: {rendered!r}"
    assert _ERR_GATE_A_RULE in rendered, (
        f"the errors panel must show a Gate A offending-claim detail: {rendered!r}"
    )
    assert _ERR_GATE_B_MISSING in rendered, (
        f"the errors panel must show a Gate B missing must-have id: {rendered!r}"
    )

    # VIEW-12: coloring is applied inline via theme vars — the renderable is a Rich Text carrying at
    # least one non-empty style span (the red-forward failure markers / gate-verdict colours).
    assert probe["is_text"], "the #errors renderable must be a Rich Text (red spans, not plain text)"
    assert probe["nonempty_style_count"] >= 1, (
        f"the errors panel must carry at least one non-empty style span (red-forward): "
        f"found {probe['nonempty_style_count']}"
    )

    # VIEW-12: the empty pipeline degrades to the UI-SPEC `No failures` copy, never a blank or a crash.
    assert "No failures" in empty_text, f"the empty errors panel must show 'No failures': {empty_text!r}"


# --- VIEW-13: activity feed renders a newest-first, colour-coded event timeline -------------------

# The fixtures span three days: 20260603T120000-fail (newest), 20260602T120000-run-ws, and
# 20260601T120000-del (oldest). activity() is newest-first, so the -fail run's events precede the
# -del run's terminal line. This test file lives under tests/, which the Phase-20 grep-guard does NOT
# scan, so it may freely name the status/verdict words the feed renders from the projection VALUES.
_ACT_NEWER_RUN = "20260603T120000-fail"
_ACT_OLDER_RUN = "20260601T120000-del"


async def _probe_activity_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill #activity, then probe text + applied event-colour spans."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the real seeding (IN-02): the event timeline is marshalled off-thread into #activity —
        # a fixed pause count races the ~0.1s poll worker. _settle blocks and fails loudly if it never fills.
        await _settle(pilot, lambda: str(app.query_one("#activity", Static).render()).strip() != "")
        panel = app.query_one("#activity", Static)
        rendered = str(panel.render())
        # Static.update(out) stores the ORIGINAL Rich Text in the name-mangled __content attribute
        # (textual 6.1 has no public `.renderable`); read it for the plain text + applied event spans —
        # the same private-internals convention the DAG-strip / errors tests use.
        renderable = getattr(panel, "_Static__content", None)
        content_plain = renderable.plain if isinstance(renderable, Text) else rendered
        spans = getattr(renderable, "spans", [])
        nonempty_styles = [str(sp.style) for sp in spans if sp.style]
        return {
            "rendered": rendered,
            "content_plain": content_plain,
            "is_text": isinstance(renderable, Text),
            "nonempty_style_count": len(nonempty_styles),
        }


async def _probe_empty_activity_panel() -> str:
    """Launch over an empty pipeline → expect the `No activity yet` empty-state copy."""
    with tempfile.TemporaryDirectory() as tmp:
        empty_pipe = Path(tmp) / "pipeline"
        empty_root = Path(tmp) / "root"
        empty_pipe.mkdir()
        empty_root.mkdir()
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(empty_pipe), repo_root=empty_root)
        app = gmj_dashboard.GmjDashboard(model, manage=False, refresh=0.1)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return str(app.query_one("#activity", Static).render())


def test_activity_panel_renders() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_activity_panel(pipe))
            empty_text = asyncio.run(_probe_empty_activity_panel())
        assert "Traceback" not in buf.getvalue(), f"activity panel leaked a traceback: {buf.getvalue()}"

    content = probe["content_plain"]
    assert content.strip(), f"the activity feed must render non-empty text: {content!r}"

    # VIEW-13: at least one event line includes a known run_id ...
    assert _ACT_NEWER_RUN in content, f"the activity feed must show a known run_id: {content!r}"
    # ... and a verdict/status word (a delivered terminal status or a gate pass/fail verdict), rendered
    # from the projection VALUE (never a .py literal).
    assert re.search(r"\b(delivered|pass|fail)\b", content), (
        f"the activity feed must show an event verdict/status word: {content!r}"
    )

    # VIEW-13: newest-first — the newer run's events precede the older run's in the feed.
    assert _ACT_OLDER_RUN in content, f"the activity feed must also show an older run: {content!r}"
    assert content.index(_ACT_NEWER_RUN) < content.index(_ACT_OLDER_RUN), (
        f"the activity feed must be newest-first (newer run before older): {content!r}"
    )

    # VIEW-13: colour is applied inline via theme vars — a Rich Text with >=1 non-empty event span
    # (event-started / event-pass / event-fail / status-*), colour always paired with the readable label.
    assert probe["is_text"], "the #activity renderable must be a Rich Text (event-coloured spans, not plain text)"
    assert probe["nonempty_style_count"] >= 1, (
        f"the activity feed must carry at least one non-empty event-colour span: "
        f"found {probe['nonempty_style_count']}"
    )

    # VIEW-13: an empty pipeline degrades to the `No activity yet` empty state, never a blank or a crash.
    assert "No activity yet" in empty_text, f"the empty activity panel must show 'No activity yet': {empty_text!r}"


async def _probe_diag_tabs_panel(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        tabs = app.query_one("#diag-tabs-panel", TabbedContent)
        errors_text = str(app.query_one("#errors", Static).render())
        tabs.active = "pane-activity"
        await pilot.pause()
        activity_text = str(app.query_one("#activity", Static).render())
        tabs.active = "pane-debug"
        await pilot.pause()
        debug_text = str(app.query_one("#debug", Static).render())
        return {
            "panel_type": type(tabs).__name__,
            "initial_active": tabs.active,
            "errors_nonempty": bool(errors_text.strip()),
            "activity_nonempty": bool(activity_text.strip()),
            "debug_text": debug_text,
            "tab_labels": [t.label_text for t in app.query("#diag-tabs-panel Tab")],
        }


def test_diag_tabs_panel_switch() -> None:
    with _temp_idle_pipeline() as pipe:
        probe = asyncio.run(_probe_diag_tabs_panel(pipe))
    assert probe["panel_type"] == "TabbedContent"
    assert probe["tab_labels"] == [
        "errors",
        "debug",
        "activity (events)",
        "commands",
        "metrics",
        "pipeline stages",
        "throughput / gates",
        "docs",
    ]
    assert probe["activity_nonempty"], f"activity tab must show content: {probe!r}"
    assert "Select a run for internals" in probe["debug_text"]


async def _probe_diag_tab_focus_escape(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        tabs = app.query_one("#diag-tabs-panel", TabbedContent)
        tab_bar = app.query_one("#diag-tabs-panel ContentTabs")
        tab_bar.focus()
        await pilot.pause()
        assert tab_bar.has_focus
        await pilot.press("tab")
        await pilot.pause()
        escaped = not tab_bar.has_focus
        # Arrow keys still switch panes while the tab bar holds focus.
        tab_bar.focus()
        await pilot.pause()
        assert tabs.active == "pane-errors"
        await pilot.press("right")
        await pilot.pause()
        after_right = tabs.active
        return {"escaped": escaped, "after_right": after_right}


def test_diag_tab_bar_allows_tab_focus_escape() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_diag_tab_focus_escape(pipe))
    assert probe["escaped"], f"Tab must leave the diagnostics tab bar: {probe!r}"
    assert probe["after_right"] == "pane-debug", f"←/→ must switch panes: {probe!r}"


# --- VIEW-14: extended charts — multi-row block throughput graph + Gate A/B bars + per-status trend -

async def _probe_charts_panel(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill #charts, then probe plain text + applied colour spans."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: str(app.query_one("#charts", Static).render()).strip() != "")
        panel = app.query_one("#charts", Static)
        rendered = str(panel.render())
        # Static.update(out) stores the ORIGINAL Rich Text in the name-mangled __content attribute
        # (textual 6.1 has no public `.renderable`); read it for the plain text + applied colour spans.
        renderable = getattr(panel, "_Static__content", None)
        content_plain = renderable.plain if isinstance(renderable, Text) else rendered
        spans = getattr(renderable, "spans", [])
        nonempty_styles = [str(sp.style) for sp in spans if sp.style]
        # The metrics projection the charts render from (throughput series + per-status trend keys).
        metrics = app._model.snapshot()["metrics"]
        return {
            "content_plain": content_plain,
            "is_text": isinstance(renderable, Text),
            "nonempty_style_count": len(nonempty_styles),
            "throughput": metrics.get("throughput") or [],
            "throughput_by_status": metrics.get("throughput_by_status") or {},
        }


def test_charts_panel_renders() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_charts_panel(pipe))
        assert "Traceback" not in buf.getvalue(), f"charts panel leaked a traceback: {buf.getvalue()}"

    content = probe["content_plain"]
    assert content.strip(), f"the charts panel must render non-empty text: {content!r}"

    # VIEW-14: the BIG throughput graph is a hand-rolled MULTI-ROW block matrix, NOT a single-row
    # Sparkline. _block_graph over the same series must yield >1 row (contain a newline), and that
    # multi-row block must appear verbatim in the rendered panel.
    block = gmj_dashboard._block_graph(probe["throughput"])
    assert "\n" in block, (
        f"the throughput block graph must be multi-row (contain a newline), not a single-row Sparkline: {block!r}"
    )
    assert block in content, (
        f"the multi-row block throughput graph must appear in the charts panel: block={block!r} content={content!r}"
    )

    # VIEW-14: the Gate A/B pass-fail bar chart carries the numeric pass/fail counts + a gate label.
    assert "Gate A" in content and "Gate B" in content, f"the charts panel must label the Gate A/B bars: {content!r}"
    assert re.search(r"\d+\s*pass\s*/\s*\d+\s*fail", content), (
        f"the Gate A/B bar chart must show the numeric pass/fail counts: {content!r}"
    )

    # VIEW-14: a per-status trend appears for at least one projected status VALUE (fed from
    # throughput_by_status). Every trend status key must be present in the rendered panel.
    assert probe["throughput_by_status"], "the fixture corpus must yield at least one per-status trend series"
    for status in probe["throughput_by_status"]:
        assert status in content, f"the charts panel must render a per-status trend for {status!r}: {content!r}"

    # VIEW-14: colour is applied inline via theme vars — a Rich Text carrying >=1 non-empty colour span
    # (the green pass / red fail bar runs and the per-status trend colours).
    assert probe["is_text"], "the #charts renderable must be a Rich Text (coloured bar/trend spans, not plain text)"
    assert probe["nonempty_style_count"] >= 1, (
        f"the charts panel must carry at least one non-empty colour span: found {probe['nonempty_style_count']}"
    )


# --- MANAGE-01/02/03: --manage binds real actions; r/R launch via the seam, fire-and-forget --------

# A known fixture run to park the #runs cursor on for the resume launch (present in the corpus).
_MANAGE_RUN_ID = "20260601T120000-del"


async def _probe_manage_binds_and_launch(pipeline_dir: Path) -> dict:
    """Under --manage: read the binding action names, then drive r/R with a fake launcher + collectors."""
    app = _build_app(pipeline_dir, manage=True)
    rec = _RecordingLauncher()
    out: dict = {}
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        # (a) each mutating key binds to its REAL action name (run/resume/batch/mode/cap), not noop.
        k2b = app._bindings.key_to_bindings
        out["actions"] = {
            k: (k2b[k][0].action if k in k2b and k2b[k] else None) for k in _MUTATING_KEYS
        }
        # (b) inject the fake launcher + deterministic collectors; focus the table so the letter keys
        #     reach the App binding (the filter Input would otherwise consume them).
        app._launcher = rec
        app._prompt_offer = lambda: _aval("https://work.ua/jobs/1/")
        app._selected_run_id = lambda: _MANAGE_RUN_ID
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()

        await pilot.press("r")
        await pilot.pause()
        out["argv_run"] = rec.argv
        out["kwargs_run"] = dict(rec.kwargs)

        await pilot.press("R")
        await pilot.pause()
        out["argv_resume"] = rec.argv

        out["calls"] = rec.calls
        out["wait_calls"] = rec.proc.wait_calls
        out["communicate_calls"] = rec.proc.communicate_calls
        out["children"] = len(app._children)
    return out


def test_manage_binds_real_actions() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_manage_binds_and_launch(pipe))
        assert "Traceback" not in buf.getvalue(), f"--manage launch leaked a traceback: {buf.getvalue()}"

    # MANAGE-01: every mutating key binds to its REAL action name, NOT the inert noop.
    for key, expected in _MANAGE_ACTIONS.items():
        got = probe["actions"].get(key)
        assert got == expected, f"key {key!r} must bind to action {expected!r} under --manage, got {got!r}"
        assert got != "noop", f"key {key!r} must NOT bind to the inert noop under --manage"

    # MANAGE-02: `r` awaited the injected launcher with the exact autonomous argv + start_new_session.
    argv_run = probe["argv_run"]
    assert argv_run[:3] == ("claude", "--dangerously-skip-permissions", "-p"), (
        f"the launched argv must be claude … -p …: {argv_run!r}"
    )
    assert "mode=autonomous" in argv_run[-1], f"a fresh run must force autonomous: {argv_run[-1]!r}"
    assert "run_id=" not in argv_run[-1], f"a fresh run must not carry a run_id: {argv_run[-1]!r}"
    assert probe["kwargs_run"].get("start_new_session") is True, "the child must be detached (start_new_session=True)"

    # HON-02: a --manage `r` launch under --pipeline-dir <dir> carries the operator dir in BOTH carriers —
    # the readable prompt token AND the authoritative child env (built from an os.environ COPY, so PATH
    # survives). _build_app sets pipeline_dir=str(pipe); no real claude spawns (recording launcher).
    assert f"pipeline-dir={pipe}" in argv_run[-1], f"prompt must carry the operator dir: {argv_run[-1]!r}"
    env_run = probe["kwargs_run"].get("env") or {}
    assert env_run.get("GMJ_PIPELINE_DIR") == str(pipe), f"child env must carry the operator dir: {env_run!r}"
    assert "PATH" in env_run, "env must be a COPY of os.environ (child keeps PATH — no bare dict)"

    # MANAGE-03: `R` embedded the selected run_id in the resume prompt.
    argv_resume = probe["argv_resume"]
    assert f"run_id={_MANAGE_RUN_ID}" in argv_resume[-1], f"resume must embed run_id=<id>: {argv_resume[-1]!r}"
    assert "mode=autonomous" in argv_resume[-1], f"resume must also force autonomous: {argv_resume[-1]!r}"

    # Fire-and-forget: both keys launched (2 calls), children held; the UI action never blocks on
    # completion. A background watcher may call .wait() to end fast-poll — that is not a UI freeze.
    assert probe["calls"] == 2, f"r and R must each launch exactly once: {probe['calls']}"
    assert probe["children"] == 2, f"each launched proc must be held in self._children: {probe['children']}"
    assert probe["communicate_calls"] == 0, "the launched proc's .communicate() must never be called"


# --- MANAGE-05: m toggles execution_mode + c sets retry_cap, over a temp config (comments survive) --

async def _drive_config_edits(pipeline_dir: Path, config_path: Path) -> dict:
    """Under --manage: drive `m` (mode toggle) then `c` (retry_cap set) over a temp config copy."""
    app = _build_app(pipeline_dir, manage=True, config_path=config_path)
    notes: list = []
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        app.notify = lambda message, **kw: notes.append((str(message), kw.get("severity")))
        app._prompt_cap = lambda: _aval(7)
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
    return {"notes": notes, "text": config_path.read_text(encoding="utf-8")}


def test_manage_config_edit() -> None:
    with _temp_pipeline() as pipe, tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "pipeline.config.yaml"
        cfg.write_text(_MANAGE_TEST_CONFIG, encoding="utf-8")
        seed = cfg.read_text(encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_drive_config_edits(pipe, cfg))
        assert "Traceback" not in buf.getvalue(), f"config edit leaked a traceback: {buf.getvalue()}"

    text = probe["text"]
    # MANAGE-05: the seed mode (human_in_the_loop) flipped to autonomous on `m`.
    assert "execution_mode: human_in_the_loop" in seed, "the seed config must start human_in_the_loop"
    assert "execution_mode: autonomous" in text, f"`m` must flip execution_mode in the file: {text!r}"
    # `c` set retry_cap to the injected value; the FREEZE CONTRACT comment block survives both edits.
    assert re.search(r"retry_cap:\s*7\b", text), f"`c` must set retry_cap to the injected value: {text!r}"
    assert "# FREEZE CONTRACT" in text, "the freeze-contract comment block must survive the config edits"

    # The confirmation notices carry the exact UI-SPEC copy (never silent).
    msgs = [m for m, _sev in probe["notes"]]
    assert any(m == "✓ default_mode → autonomous (existing runs unchanged)" for m in msgs), (
        f"missing mode notice: {msgs}"
    )
    assert any(m == "✓ retry_cap → 7" for m in msgs), f"missing cap notice: {msgs}"


# --- MANAGE prompt-modal deadlock guard: the REAL _ask/_PromptModal path must stay interactive under a
# --- keypress. A prompt action that ``await``s its pushed modal INLINE on the message pump deadlocks —
# --- the modal never receives keystrokes/escape (the exact symptom a human hit in UAT Step 3). Every
# --- collector-override test above deliberately bypasses this path, so THIS is the regression guard for
# --- the ``@work`` fix (the prompt actions must run as workers, off the pump).

async def _drive_real_prompt_modal(pipeline_dir: Path, config_path: Path) -> dict:
    """Press `c` with NO `_prompt_cap` override so the real `_PromptModal` opens; type + submit it."""
    app = _build_app(pipeline_dir, manage=True, config_path=config_path)
    out: dict = {}
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        # Focus the table so `c` reaches the App binding (the filter Input would otherwise consume it).
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()
        await pilot.press("c")            # REAL dispatch — the deadlock path (no collector override)
        await pilot.pause()
        out["modal_open"] = type(app.screen_stack[-1]).__name__ == "_PromptModal"
        out["focused_input"] = getattr(app.focused, "id", None)
        await pilot.press("4")
        await pilot.press("2")
        await pilot.pause()
        out["typed"] = app.screen.query_one("#modal-prompt-input", Input).value
        await pilot.press("enter")        # submit → resolve → dismiss (pump must be free)
        await pilot.pause()
        out["closed_after_submit"] = len(app.screen_stack) == 1
    return out


def test_manage_prompt_modal_is_interactive_under_keypress() -> None:
    with _temp_pipeline() as pipe, tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "pipeline.config.yaml"
        shutil.copy(CONFIG_SRC, cfg)
        # A re-introduced deadlock HANGS rather than fails — bound the run so it surfaces as a clean
        # test failure (never a wedged suite).
        out = asyncio.run(asyncio.wait_for(_drive_real_prompt_modal(pipe, cfg), timeout=20))
        text = cfg.read_text(encoding="utf-8")

    assert out["modal_open"], "pressing `c` must open the real _PromptModal (no collector override)"
    assert out["focused_input"] == "modal-prompt-input", "the modal Input must receive focus"
    assert out["typed"] == "42", f"the modal Input must accept typed keys (deadlock guard): {out['typed']!r}"
    assert out["closed_after_submit"], "Enter must submit + dismiss the modal (message pump not blocked)"
    assert re.search(r"retry_cap:\s*42\b", text), f"the submitted value must reach the config: {text!r}"


# --- SAFE-02: first m/c write to the real repo-default config is blocked behind a confirm gate ------
# The gate is an INJECTABLE seam (``_confirm_manage_write``) so the Pilot test never opens a real modal:
# it forces ``_editing_repo_default`` True over a TEMP config copy (never the real repo file) and swaps
# the confirm seam for a counting coroutine. A cancel (seam → False) must leave the config byte-unchanged;
# a confirm (seam → True) writes once and, crucially, a SECOND mutating key does NOT re-invoke the seam
# (confirm-once-per-session) yet still writes.

_SAFE02_SEED = """\
# FREEZE CONTRACT: at run start, gmj_state_write.py copies these values into state.json.
execution_mode: human_in_the_loop
retry_cap: 4
"""


async def _drive_confirm_gate(config_path: Path, *, confirm: bool, presses: int) -> dict:
    """Force the SAFE-02 gate ON over a temp config; press `m` ``presses`` times through a counting seam."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=True, config_path=config_path)
        calls = {"confirm": 0}
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app._editing_repo_default = lambda: True          # force gate ON over the temp copy
            app.notify = lambda message, **kw: None

            async def _c() -> bool:
                calls["confirm"] += 1
                return confirm

            app._confirm_manage_write = _c
            app.query_one("#runs", DataTable).focus()
            await pilot.pause()
            for _ in range(presses):
                await pilot.press("m")
                await pilot.pause()
        return {"confirm_calls": calls["confirm"], "text": config_path.read_text(encoding="utf-8")}


def test_manage_confirm_gate_blocks_first_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # (a) cancel (seam → False) leaves the config byte-unchanged (no write).
        cancel_cfg = Path(tmp) / "cancel.yaml"
        cancel_cfg.write_text(_SAFE02_SEED, encoding="utf-8")
        seed = cancel_cfg.read_text(encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            cancelled = asyncio.run(_drive_confirm_gate(cancel_cfg, confirm=False, presses=1))
        assert "Traceback" not in buf.getvalue(), f"confirm-cancel leaked a traceback: {buf.getvalue()}"
        assert cancelled["confirm_calls"] == 1, (
            f"pressing `m` on the repo-default must invoke the confirm seam once: {cancelled['confirm_calls']}"
        )
        assert cancelled["text"] == seed, (
            f"a cancelled confirm must leave the config byte-unchanged (no write): {cancelled['text']!r}"
        )
        assert "execution_mode: human_in_the_loop" in cancelled["text"], "cancel must not flip execution_mode"

        # (b) confirm (seam → True): first `m` writes, second `m` does NOT re-prompt yet still writes.
        ok_cfg = Path(tmp) / "ok.yaml"
        ok_cfg.write_text(_SAFE02_SEED, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            confirmed = asyncio.run(_drive_confirm_gate(ok_cfg, confirm=True, presses=2))
        assert "Traceback" not in buf.getvalue(), f"confirm-proceed leaked a traceback: {buf.getvalue()}"
        # Confirm-once-per-session: two mutating presses, exactly ONE confirm-seam invocation.
        assert confirmed["confirm_calls"] == 1, (
            f"after the first acknowledgement subsequent writes must NOT re-prompt (confirm-once): "
            f"{confirmed['confirm_calls']}"
        )
        # Both presses wrote: `m` toggles execution_mode, so two toggles land back on human_in_the_loop —
        # the SECOND write is what proves the write proceeds without a second confirm.
        assert "execution_mode: human_in_the_loop" in confirmed["text"], (
            f"two confirmed toggles must land back on human_in_the_loop (both writes proceeded): {confirmed['text']!r}"
        )
        assert "# FREEZE CONTRACT" in confirmed["text"], "the freeze-contract comment block must survive"


# --- SAFE-02 (WR-01): a second manage keypress WHILE the confirm modal is open must NOT stack a second
# --- worker + second write. The bare ``@work`` was non-exclusive, so a second ``m`` fell through and
# --- spawned a competing worker that re-entered the guard (still un-confirmed) and double-wrote. The
# --- fix makes ``action_mode``/``action_cap`` ``@work(exclusive=True, group="manage")`` so the second
# --- press CANCELS the pending worker. The existing gate test cannot see this: its injected confirm
# --- seam resolves synchronously, so worker A fully latches before worker B is ever spawned. Here the
# --- seam BLOCKS on an Event, holding the "modal" open across the second keypress — the real path.


async def _drive_concurrent_confirm(config_path: Path) -> dict:
    """Force the SAFE-02 gate ON; press `m` twice WHILE the confirm seam is blocked open on an Event."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=True, config_path=config_path)
        gate = asyncio.Event()
        calls = {"entered": 0, "resolved": 0}
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app._editing_repo_default = lambda: True          # force gate ON over the temp copy
            app.notify = lambda message, **kw: None

            async def _c() -> bool:
                calls["entered"] += 1
                await gate.wait()                              # hold the "modal" open across press #2
                calls["resolved"] += 1                         # only a NON-cancelled worker reaches here
                return True

            app._confirm_manage_write = _c
            app.query_one("#runs", DataTable).focus()
            await pilot.pause()
            await pilot.press("m")                             # worker A: enters _c, blocks on the gate
            await pilot.pause()
            await pilot.press("m")                             # worker B: exclusive → cancels worker A
            await pilot.pause()
            gate.set()                                         # release: only the surviving worker writes
            await pilot.pause()
            await pilot.pause()
        return {**calls, "text": config_path.read_text(encoding="utf-8")}


def test_manage_confirm_gate_no_double_write_under_concurrent_keypress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "concurrent.yaml"
        cfg.write_text(_SAFE02_SEED, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_drive_concurrent_confirm(cfg))
        assert "Traceback" not in buf.getvalue(), (
            f"the concurrent-confirm path leaked a traceback (worker cancellation must be clean): {buf.getvalue()}"
        )
    # Exactly ONE worker survived the second keypress, so exactly ONE write completed. A non-exclusive
    # ``@work`` would let BOTH workers resolve and write, toggling execution_mode twice back to
    # human_in_the_loop (a silent double-write). One toggle lands on autonomous.
    assert probe["resolved"] == 1, (
        f"only one confirm worker may complete a write under concurrent keypresses (exclusive group); "
        f"resolved={probe['resolved']} (2 ⇒ the second press stacked a competing worker + double-wrote)"
    )
    assert "execution_mode: autonomous" in probe["text"], (
        f"a single confirmed toggle must land on autonomous — a double-write would flip it back to "
        f"human_in_the_loop: {probe['text']!r}"
    )
    assert "# FREEZE CONTRACT" in probe["text"], "the freeze-contract comment block must survive"


# --- SAFE-02 (WR-02): the confirm-once latch must be set only AFTER a SUCCESSFUL write. The buggy
# --- guard latched ``_manage_confirmed`` on acknowledgement BEFORE the write, so a failed first write
# --- permanently disabled the prompt — every later write proceeded unacknowledged even though none had
# --- ever succeeded. Here the first ``actions.toggle_execution_mode`` raises ValueError; the SECOND
# --- keypress must therefore RE-PROMPT (confirm seam invoked twice), and only the second write lands.


async def _drive_failed_then_reprompt(config_path: Path) -> dict:
    """Force the gate ON; make the first write RAISE, then prove the next keypress re-prompts + writes."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=True, config_path=config_path)
        calls = {"confirm": 0}
        import gmj_dashboard_actions as actions

        real_toggle = actions.toggle_execution_mode
        state = {"fail_first": True}

        def _flaky_toggle(path):
            if state["fail_first"]:
                state["fail_first"] = False
                raise ValueError("simulated first-write failure")
            return real_toggle(path)

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app._editing_repo_default = lambda: True          # force gate ON over the temp copy
            app.notify = lambda message, **kw: None

            async def _c() -> bool:
                calls["confirm"] += 1
                return True

            app._confirm_manage_write = _c
            actions.toggle_execution_mode = _flaky_toggle     # first call raises, second succeeds
            try:
                app.query_one("#runs", DataTable).focus()
                await pilot.pause()
                await pilot.press("m")                         # confirm #1 → write RAISES → no latch
                await pilot.pause()
                await pilot.press("m")                         # must RE-PROMPT (confirm #2) → write OK
                await pilot.pause()
            finally:
                actions.toggle_execution_mode = real_toggle
        return {"confirm": calls["confirm"], "text": config_path.read_text(encoding="utf-8")}


def test_manage_confirm_latch_survives_failed_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "flaky.yaml"
        cfg.write_text(_SAFE02_SEED, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_drive_failed_then_reprompt(cfg))
        assert "Traceback" not in buf.getvalue(), f"failed-write reprompt leaked a traceback: {buf.getvalue()}"
    # WR-02: a failed first write must NOT consume the session's single prompt — the second keypress
    # re-prompts. The buggy latch-on-ack would leave confirm==1 (prompt permanently disabled).
    assert probe["confirm"] == 2, (
        f"a FAILED first write must leave the confirm prompt armed (re-prompt on the next attempt); "
        f"confirm={probe['confirm']} (1 ⇒ the latch was set before the write and the prompt was lost)"
    )
    # The second (successful) write toggled execution_mode exactly once → autonomous.
    assert "execution_mode: autonomous" in probe["text"], (
        f"the successful second write must flip execution_mode to autonomous: {probe['text']!r}"
    )
    assert "# FREEZE CONTRACT" in probe["text"], "the freeze-contract comment block must survive"


# --- SAFE-02 (a): a persistent repo-default warning banner shows at launch under --manage -----------
# Seeded ONCE in _seed_widgets() (never per-poll → no flicker, Pitfall 3), guarded by
# ``self._manage and self._editing_repo_default()``. It names the resolved real config path so the
# operator is warned before any mutating key can act; the read-only board (no --manage) shows nothing.


async def _drive_banner(config_path: Path, *, manage: bool, force_repo_default: bool) -> str:
    """Launch (manage / read-only), optionally force the repo-default detection, read the banner text."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=manage, config_path=config_path)
        if force_repo_default:
            app._editing_repo_default = lambda: True
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return str(app.query_one("#config-warning", Static).render())


def test_manage_repo_default_banner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "pipeline.config.yaml"
        cfg.write_text(_SAFE02_SEED, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            manage_banner = asyncio.run(_drive_banner(cfg, manage=True, force_repo_default=True))
            readonly_banner = asyncio.run(_drive_banner(cfg, manage=False, force_repo_default=True))
            other_config_banner = asyncio.run(_drive_banner(cfg, manage=True, force_repo_default=False))
        assert "Traceback" not in buf.getvalue(), f"banner probe leaked a traceback: {buf.getvalue()}"

    # Under --manage + repo-default: the banner is non-empty AND names the resolved config path.
    assert manage_banner.strip(), f"the repo-default banner must render non-empty under --manage: {manage_banner!r}"
    assert str(cfg.resolve()) in manage_banner, (
        f"the banner must name the resolved config path: {manage_banner!r}"
    )
    # Read-only board (no --manage): no banner at all.
    assert not readonly_banner.strip(), (
        f"the read-only board must show no repo-default banner: {readonly_banner!r}"
    )
    # Under --manage but NOT the repo-default (a temp/other config): no banner.
    assert not other_config_banner.strip(), (
        f"a non-repo-default config must show no banner even under --manage: {other_config_banner!r}"
    )


# --- MANAGE-04 (plan-checker W3): b drives run_batch with the board's pipeline_dir + success notice --

def test_manage_batch_action() -> None:
    import gmj_dashboard_actions as actions

    recorded: dict = {}

    class _Completed:
        returncode = 0
        stderr = ""

    def _fake_run_batch(shortlist, select, *, pipeline_dir, **kw):
        recorded["shortlist"] = shortlist
        recorded["select"] = select
        recorded["pipeline_dir"] = pipeline_dir
        return _Completed()

    async def _drive_batch(pipeline_dir: Path) -> list:
        app = _build_app(pipeline_dir, manage=True)
        notes: list = []
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.notify = lambda message, **kw: notes.append((str(message), kw.get("severity")))
            app._prompt_batch = lambda: _aval(("shortlist.json", "1,3"))
            app.query_one("#runs", DataTable).focus()
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
        return notes

    orig = actions.run_batch
    actions.run_batch = _fake_run_batch  # patch the module attr the lazy import resolves (no real subprocess)
    try:
        with _temp_pipeline() as pipe:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                notes = asyncio.run(_drive_batch(pipe))
            assert "Traceback" not in buf.getvalue(), f"batch action leaked a traceback: {buf.getvalue()}"
            expected_pipeline_dir = str(pipe)
    finally:
        actions.run_batch = orig

    # MANAGE-04: `b` called run_batch with the collected (shortlist, select) and the board's pipeline_dir (W2).
    assert recorded.get("shortlist") == "shortlist.json", f"run_batch shortlist not threaded: {recorded}"
    assert recorded.get("select") == "1,3", f"run_batch select not threaded: {recorded}"
    assert recorded.get("pipeline_dir") == expected_pipeline_dir, (
        f"run_batch must receive the board's own pipeline_dir (W2): {recorded.get('pipeline_dir')!r} "
        f"vs {expected_pipeline_dir!r}"
    )
    msgs = [m for m, _sev in notes]
    assert any(m == "▸ batch manifest written" for m in msgs), f"missing batch success notice: {msgs}"


# --- MANAGE-02/03: a failed launch posts a VISIBLE error-severity notice (never silent) -------------

async def _drive_launch_failure(pipeline_dir: Path) -> list:
    """Inject a launcher raising FileNotFoundError; drive `r` and capture the posted notifications."""
    app = _build_app(pipeline_dir, manage=True)
    notes: list = []

    async def _boom(*argv, **kwargs):
        raise FileNotFoundError("claude not on PATH")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        app._launcher = _boom
        app._prompt_offer = lambda: _aval("https://work.ua/jobs/1/")
        app.notify = lambda message, **kw: notes.append((str(message), kw.get("severity")))
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
    return notes


def test_launch_failure_notice() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            notes = asyncio.run(_drive_launch_failure(pipe))
        # A failed launch must NOT leak a traceback — it is converted to a UI notice.
        assert "Traceback" not in buf.getvalue(), f"a failed launch must not leak a traceback: {buf.getvalue()}"

    # MANAGE-02/03: exactly one error-severity notice, carrying the UI-SPEC launch-error copy.
    assert notes, "a failed launch must post a visible notice (never silent)"
    error_notes = [(m, sev) for m, sev in notes if sev == "error"]
    assert error_notes, f"a failed launch must post an ERROR-severity notice: {notes}"
    assert any(m.startswith("⚠ launch failed:") for m, _sev in error_notes), (
        f"the launch-error notice must use the UI-SPEC copy '⚠ launch failed: …': {error_notes}"
    )


# --- VIEW-27: live heartbeat + feature launch tracking -----------------------------------------

async def _probe_heartbeat_on_kick(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        hb = app.query_one("#heartbeat", Static)
        app._kick_live_refresh(5.0, expand_activity=False)
        await pilot.pause()
        await pilot.pause()
        return {"display": hb.display, "text": str(hb.render())}


def test_heartbeat_strip_shows_during_live_refresh() -> None:
    with _temp_idle_pipeline() as pipe:
        probe = asyncio.run(_probe_heartbeat_on_kick(pipe))
    assert probe["display"], f"heartbeat must be visible during live refresh: {probe!r}"
    low = probe["text"].lower()
    assert "syncing" in low or "launch" in low or "→" in probe["text"] or "resume" in low, (
        f"heartbeat must name the active task: {probe['text']!r}"
    )


async def _probe_feature_launch_live(pipeline_dir: Path) -> dict:
    app = _build_app(pipeline_dir, manage=True, refresh=0.1, repo_root=REPO_ROOT)
    rec = _RecordingLauncher()
    app._launcher = rec
    feature = app._model.feature_detail("command:gmj-pipeline-run")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._launch_feature(feature, {"offer": "https://example.test/job", "mode": "autonomous"})
        for _ in range(8):
            await pilot.pause()
        hb = app.query_one("#heartbeat", Static)
        return {
            "launcher_calls": rec.calls,
            "pending": len(app._pending_launches),
            "fast_poll": app._fast_poll is not None,
            "heartbeat": str(hb.render()),
            "heartbeat_visible": hb.display,
        }


def test_feature_launch_enables_live_refresh() -> None:
    with _temp_pipeline() as pipe:
        probe = asyncio.run(_probe_feature_launch_live(pipe))
    assert probe["launcher_calls"] == 1, f"feature launch must invoke launcher once: {probe!r}"
    assert probe["fast_poll"] or probe["heartbeat_visible"], (
        f"feature launch must enable fast poll / heartbeat: {probe!r}"
    )


async def _probe_reload_pipeline_heartbeat() -> dict:
    """Simulate reload: fresh app over fixture pipeline with in-flight runs on disk."""
    app = _build_app(FIXTURES, manage=False, refresh=0.1, repo_root=REPO_ROOT)
    async with app.run_test(size=(120, 40)) as pilot:
        # Settle on the real seeding (poll marshalled the on-disk active-pipeline state back) — a fixed
        # pause triple races the poll worker under CPU contention (the 29-01 render-settle flake class).
        await _settle(pilot, lambda: app._disk_pipeline_active)
        hb = app.query_one("#heartbeat", Static)
        return {
            "disk_active": app._disk_pipeline_active,
            "heartbeat_visible": hb.display,
            "heartbeat_text": str(hb.render()),
            "fast_poll": app._fast_poll is not None,
            "debug_run_id": app._debug_run_id,
        }


def test_heartbeat_on_reload_when_pipeline_active_on_disk() -> None:
    probe = asyncio.run(_probe_reload_pipeline_heartbeat())
    assert probe["disk_active"], f"fixture pipeline must be active on disk: {probe!r}"
    assert probe["heartbeat_visible"], f"heartbeat must show after reload: {probe!r}"
    assert probe["debug_run_id"], f"an in-flight run should be auto-selected for debug: {probe!r}"
    text = probe["heartbeat_text"]
    assert "●" in text, f"heartbeat must show task marker: {text!r}"
    assert "░" in text or "█" in text, f"heartbeat must show full-width bar: {text!r}"
    assert "→" in text or "batch" in text or "syncing" in text.lower(), (
        f"heartbeat must name an in-flight task: {text!r}"
    )
    assert "updating runs" not in text.lower()


async def _probe_startup_focus(pipeline_dir: Path) -> str | None:
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        for _ in range(4):
            await pilot.pause()
        focused = app.focused
        return getattr(focused, "id", None) if focused is not None else None


def test_startup_has_no_default_focus() -> None:
    with _temp_pipeline() as pipe:
        focused_id = asyncio.run(_probe_startup_focus(pipe))
    assert focused_id is None, f"no widget should be focused at startup, got {focused_id!r}"


# --- RELOAD-01/02 (Plan 28-03): view wires the launch sidecar into launch/watch/heartbeat ----------

_LAUNCHES_GLOB = "launches/*.json"


def _launches_of(pipeline_dir: Path) -> list[Path]:
    """All launch sidecars currently on disk under a pipeline dir (empty when none/absent)."""
    return sorted((Path(pipeline_dir) / "launches").glob("*.json"))


def test_launch_sidecar_kind_derives_from_slash() -> None:
    """The sidecar kind is derived from the feature SLASH (collective/interview/template) — NOT
    feature['kind'] (command/agent/skill/flow). Pure helper, no pilot render (deterministic)."""
    with _temp_pipeline() as pipe:
        app = _build_app(pipe, manage=True)
        assert app._launch_sidecar_kind({"slash": "/gmj-interview"}) == "interview"
        assert app._launch_sidecar_kind({"slash": "/gmj-template"}) == "template"
        assert app._launch_sidecar_kind({"slash": "/gmj-collective"}) == "collective"
        # The default + writer-clamp backstop: any other slash (or none) maps to collective.
        assert app._launch_sidecar_kind({"slash": "/gmj-pipeline-run"}) == "collective"
        assert app._launch_sidecar_kind({}) == "collective"


async def _drive_feature_launch(pipeline_dir: Path, feature: dict, *, manage: bool) -> None:
    """Drive ``_launch_feature`` for a feature under a running pilot; the child ``wait()`` BLOCKS so the
    sidecar is inspected while the launch is still live (no reap-on-exit race)."""
    app = _build_app(pipeline_dir, manage=manage, refresh=0.1, repo_root=REPO_ROOT)
    rec = _RecordingLauncher()
    rec.proc = _BlockingProc()  # the launched child never exits → _watch_launch does not reap
    app._launcher = rec
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._launch_feature(feature, {"args": "https://example.test/job"})
        for _ in range(10):
            await pilot.pause()


def test_launch_feature_writes_sidecar_under_manage() -> None:
    """Under --manage, driving a FeatureModal Run writes exactly one launch sidecar with the
    slash-derived kind (RELOAD-01 wiring). The view delegates the write to the actions module."""
    feature = {"kind": "command", "slash": "/gmj-template", "name": "gmj-template"}
    with _temp_idle_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            asyncio.run(_drive_feature_launch(pipe, feature, manage=True))
        assert "Traceback" not in buf.getvalue(), f"feature launch leaked a traceback: {buf.getvalue()}"
        sidecars = _launches_of(pipe)
        assert len(sidecars) == 1, f"a --manage feature launch must write exactly one sidecar: {sidecars}"
        payload = json.loads(sidecars[0].read_text(encoding="utf-8"))
        assert payload.get("kind") == "template", (
            f"the sidecar kind must be derived from the /gmj-template slash: {payload!r}"
        )
        assert payload.get("label") == "gmj-template", f"the sidecar must carry the feature label: {payload!r}"


def test_launch_feature_readonly_writes_no_sidecar() -> None:
    """Without --manage the same action writes NO sidecar — the read-only board never mutates disk."""
    feature = {"kind": "command", "slash": "/gmj-collective", "name": "gmj-collective"}
    with _temp_idle_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            asyncio.run(_drive_feature_launch(pipe, feature, manage=False))
        assert "Traceback" not in buf.getvalue(), f"read-only launch leaked a traceback: {buf.getvalue()}"
        assert _launches_of(pipe) == [], "a read-only feature launch must write NO sidecar"


async def _drive_watch_reap(pipeline_dir: Path, launch_id: str) -> bool:
    """Under a running pilot, seed a live sidecar then run ``_watch_launch`` to clean exit; return whether
    the sidecar still exists afterward (it must be reaped via the actions module)."""
    app = _build_app(pipeline_dir, manage=True, refresh=0.1, repo_root=REPO_ROOT)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await app._watch_launch(_FakeProc(), launch_id=launch_id)
        return (Path(pipeline_dir) / "launches" / f"{launch_id}.json").exists()


def test_watch_launch_reaps_sidecar_on_exit() -> None:
    """On a clean child exit ``_watch_launch`` reaps the sidecar through the actions module — the file
    is gone and the view itself never unlinks (the reap is delegated)."""
    with _temp_idle_pipeline() as pipe:
        lid = actions.write_launch_sidecar(
            str(pipe), kind="collective", label="gmj-collective", pid=os.getpid(), cmd="/gmj-collective"
        )
        assert _launches_of(pipe), "the seeded sidecar must exist before the watch reaps it"
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            still_there = asyncio.run(_drive_watch_reap(pipe, lid))
        assert "Traceback" not in buf.getvalue(), f"_watch_launch leaked a traceback: {buf.getvalue()}"
        assert not still_there, "a clean child exit must reap the launch sidecar"
        assert _launches_of(pipe) == [], "no sidecar should remain after the reap"


def test_heartbeat_recovers_launch_after_reload() -> None:
    """After reload (in-memory tracking empty, disk pipeline active), the heartbeat strip lists one item
    per recovered live launch (label + kind) — parity with recovered runs/batches (RELOAD-02)."""
    with _temp_idle_pipeline() as pipe:
        app = _build_app(pipe, manage=False)
        # Simulate the post-reload state the model produces: in-memory branch empty, disk branch active.
        app._disk_pipeline_active = True
        app._pipeline_activity = {
            "active_run_ids": [],
            "active_batch_ids": [],
            "active_launches": [{"launch_id": "L1", "kind": "collective", "label": "gmj-collective"}],
        }
        items = app._heartbeat_task_items()
        assert "gmj-collective (collective)" in items, (
            f"a recovered live launch must surface on the heartbeat strip with label+kind: {items!r}"
        )


def test_heartbeat_recovered_launch_label_without_kind() -> None:
    """A recovered launch with no kind falls back to a bare label (never an empty ``()`` suffix)."""
    with _temp_idle_pipeline() as pipe:
        app = _build_app(pipe, manage=False)
        app._disk_pipeline_active = True
        app._pipeline_activity = {"active_launches": [{"label": "gmj-collective", "kind": ""}]}
        assert app._heartbeat_task_items() == ["gmj-collective"], (
            "a kind-less recovered launch must render as a bare label"
        )


def test_live_launch_not_double_counted() -> None:
    """A live-session launch (in-memory branch non-empty) is listed ONCE — the disk branch fills in only
    when the in-memory branch is empty (the in-memory-wins dedup runs/batches already use)."""
    with _temp_idle_pipeline() as pipe:
        app = _build_app(pipe, manage=True)
        proc = _FakeProc()  # no returncode attr => treated as in-flight
        app._pending_launches = [proc]
        app._launch_labels[id(proc)] = "gmj-collective"
        # Disk ALSO reports the same launch as active (as it would while the child lives).
        app._disk_pipeline_active = True
        app._pipeline_activity = {
            "active_launches": [{"launch_id": "L1", "kind": "collective", "label": "gmj-collective"}],
        }
        items = app._heartbeat_task_items()
        occurrences = sum(1 for it in items if "gmj-collective" in it)
        assert occurrences == 1, f"a live launch must be listed exactly once, not double-counted: {items!r}"


# --- TEST-02: the REAL two-step batch modal, Escape-cancelled, launches NOTHING -------------------
# `test_manage_batch_action` (above) overrides `app._prompt_batch = lambda: _aval(...)` and so NEVER
# opens the real `_PromptModal`s — it proves threading, not the modal path. THIS test presses `b` with
# NO override, drives the REAL `action_batch (@work) → _prompt_batch → _ask → _PromptModal` chain under
# keypress, cancels step 2 with Escape, and proves (a) both steps are real `_PromptModal`s, (b) Escape
# pops cleanly back to the base screen, and (c) `actions.run_batch` is invoked exactly 0 times. The
# coroutine is bounded by `asyncio.wait_for(..., timeout=20)` — `action_batch` is `@work`, so a lost
# decorator would DEADLOCK (awaiting the pushed modal inline on the pump) and HANG the suite; the
# timeout converts that into a clean failure (RESEARCH Pitfall 4).


async def _drive_batch_modal_escape_cancel(pipeline_dir: Path) -> dict:
    """Press `b` (real path), advance past step 1, Escape-cancel step 2; report the modal chain state."""
    app = _build_app(pipeline_dir, manage=True)
    out: dict = {}
    async with app.run_test(size=(120, 40)) as pilot:
        await _settle(pilot, lambda: app.query_one("#runs", DataTable).row_count > 0)
        # Focus the table so `b` reaches the App binding (a filter Input would otherwise consume it).
        app.query_one("#runs", DataTable).focus()
        await pilot.pause()
        await pilot.press("b")            # REAL dispatch — NO `_prompt_batch` override (the whole point)
        await pilot.pause()
        # Step 1: the shortlist-path prompt is a real _PromptModal.
        out["step1_modal"] = type(app.screen_stack[-1]).__name__
        # Seed a non-empty selection into the REAL Input so step 1 does not itself cancel, then submit.
        # We set `.value` rather than pressing each char: per-key `pilot.press` each awaits `wait_for_idle`,
        # and a preceding manage test's `_kick_live_refresh` fast-poll leaves the process just busy enough
        # that a long char-by-char sequence never reaches idle and deadlocks (a cross-test Textual timing
        # fragility, NOT a product bug). Setting the value + pressing `enter` exercises the SAME real
        # submit path (`on_input_submitted → _resolve → future → _ask returns → step 2 opens`) count-free.
        app.screen.query_one("#modal-prompt-input", Input).value = "shortlist.json"
        await pilot.press("enter")        # submit step 1 → resolves → step 2 (_ask) opens
        await pilot.pause()
        out["step2_modal"] = type(app.screen_stack[-1]).__name__
        await pilot.press("escape")       # CANCEL step 2 → _prompt_batch returns None → no run_batch
        await pilot.pause()
        await pilot.pause()
        out["stack_after_cancel"] = len(app.screen_stack)
    return out


def test_manage_batch_modal_two_step_escape_cancel() -> None:
    calls = {"run_batch": 0}

    class _Completed:
        returncode = 0
        stderr = ""

    def _spy_run_batch(*args, **kwargs):
        calls["run_batch"] += 1
        return _Completed()

    orig = actions.run_batch
    actions.run_batch = _spy_run_batch  # patch the module attr the lazy import resolves (no subprocess)
    try:
        with _temp_pipeline() as pipe:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                # A re-introduced deadlock HANGS rather than fails — bound the run so a lost `@work`
                # surfaces as a clean failure, never a wedged suite (RESEARCH Pitfall 4).
                out = asyncio.run(
                    asyncio.wait_for(_drive_batch_modal_escape_cancel(pipe), timeout=20)
                )
            assert "Traceback" not in buf.getvalue(), (
                f"the batch modal cancel path leaked a traceback: {buf.getvalue()}"
            )
    finally:
        actions.run_batch = orig

    # Both steps of the REAL two-step chain opened a genuine _PromptModal (no collector override).
    assert out["step1_modal"] == "_PromptModal", (
        f"pressing `b` must open the real step-1 _PromptModal: {out['step1_modal']!r}"
    )
    assert out["step2_modal"] == "_PromptModal", (
        f"submitting step 1 must open the real step-2 _PromptModal: {out['step2_modal']!r}"
    )
    # Escape on step 2 popped cleanly back to the single base screen (no wedged/leaked modal).
    assert out["stack_after_cancel"] == 1, (
        f"Escape on step 2 must pop back to the base screen (stack==1): {out['stack_after_cancel']}"
    )
    # The load-bearing safety assertion: a cancelled batch launches NOTHING.
    assert calls["run_batch"] == 0, (
        f"a cancelled batch must never call run_batch (launched nothing): {calls['run_batch']}"
    )


# --- TEST-01: the fixed grid keeps every panel visible at its min height under a LONG candidate -----
# Regression guard for the FIND-09/FIND-14 layout starvation: before the Session-5 fixed grid
# (`grid-rows: auto auto auto 17 17 12`, `min-height: 3`), a realistically long `config/candidate.yaml`
# could starve the lower panels to zero height. This feeds a generated 400-word-summary / 120-item
# expertise candidate via a tempdir `repo_root` (the real `config/*.yaml` copied alongside so the
# sources/pipeline/fit/prefs counters + config-table still resolve) and asserts the four panels stay
# `display=True` with `size.height >= 3`. The `#candidate` widget was REMOVED in the Session-5 grid, so
# it is deliberately NOT asserted. Geometry is read only AFTER the grid settles (Pitfall 5: pre-layout
# height is 0). Every fixture write lands in the tempdir — never a real repo config file.


def test_layout_panels_visible_under_long_candidate() -> None:
    with _temp_pipeline() as pipe, tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        (root / "config").mkdir(parents=True)
        # Copy the real config yamls so the sources/pipeline/fit/prefs panels + counters resolve …
        for p in (REPO_ROOT / "config").glob("*.yaml"):
            shutil.copy2(p, root / "config" / p.name)
        # … then OVERWRITE candidate.yaml with a realistically long profile (RESEARCH Pattern 4).
        long_cand = [
            "name: Test Candidate",
            "title: Senior Engineer",
            "summary: " + ("word " * 400),
            "expertise:",
        ]
        long_cand += [f"  - skill {i} with a longish descriptive clause" for i in range(120)]
        (root / "config" / "candidate.yaml").write_text("\n".join(long_cand), encoding="utf-8")

        _panels = ("#runs", "#vacancies", "#features-table", "#config-table")

        async def _probe() -> dict:
            app = _build_app(pipe, manage=False, refresh=0.1, repo_root=root)
            async with app.run_test(size=(120, 40)) as pilot:
                # Settle on the REAL seeding + layout condition (WR-01): the fixture-guaranteed run rows
                # are marshalled off-thread AND every asserted panel has a computed (non-zero) height, so
                # `_settle` actually blocks on wall-clock and fails loudly if layout never settles — the
                # always-true `row_count >= 0` predicate did neither (Pitfall 5 — pre-layout height reads 0).
                await _settle(
                    pilot,
                    lambda: app.query_one("#runs", DataTable).row_count > 0
                    and all(app.query_one(wid).size.height > 0 for wid in _panels),
                    tries=20,
                )
                for _ in range(3):
                    await pilot.pause()
                return {
                    wid: (app.query_one(wid).size.height, app.query_one(wid).display)
                    for wid in _panels
                }

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            geom = asyncio.run(_probe())
        assert "Traceback" not in buf.getvalue(), (
            f"the long-candidate layout probe leaked a traceback: {buf.getvalue()}"
        )

    for wid, (height, display) in geom.items():
        assert display is True, f"{wid} must stay visible under a long candidate: {geom}"
        assert height >= 3, f"{wid} must keep its min height (>=3) under a long candidate: {geom}"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
