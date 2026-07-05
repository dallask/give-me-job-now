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
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from rich.text import Text

from textual.widgets import DataTable, Sparkline, Static

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline"
DASH_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "dashboard"
DASHBOARD_PY = REPO_ROOT / "scripts" / "dashboard" / "gmj_dashboard.py"

# Import the App + the model via the same sys.path idiom the model test uses.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dashboard"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_dashboard  # noqa: E402
import gmj_dashboard_model  # noqa: E402

# Keys that must NEVER be bound without --manage (VIEW-01) and MUST be bound with it (VIEW-07).
_MUTATING_KEYS = ("r", "R", "b", "m", "c")


@contextmanager
def _temp_pipeline():
    """Yield a Path to a throwaway COPY of tests/fixtures/pipeline/ (bug-proofs the committed corpus)."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "pipeline"
        shutil.copytree(FIXTURES, dst)
        yield dst


def _build_app(pipeline_dir: Path, *, manage: bool = False, refresh: float = 1.5) -> "gmj_dashboard.GmjDashboard":
    """Construct the App around a pre-built model reading the temp pipeline + dashboard fixtures."""
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(pipeline_dir), repo_root=DASH_FIXTURES)
    return gmj_dashboard.GmjDashboard(model, manage=manage, refresh=refresh)


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

def test_readonly_no_mutating_bindings() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            bound = asyncio.run(_bound_keys(pipe, manage=False))
        assert "Traceback" not in buf.getvalue(), f"read-only launch leaked a traceback: {buf.getvalue()}"
    for key in _MUTATING_KEYS:
        assert key not in bound, f"mutating key {key!r} must NOT be bound in read-only mode: {sorted(bound)}"
    assert "q" in bound, "the read-only quit key must be bound in read-only mode"


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
    app = _build_app(pipeline_dir, manage=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
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
    for label in ("runs", "offers", "mode", "cap"):
        assert label in counters_text, f"counters must carry the {label!r} label: {counters_text!r}"
    # The delivered headline number appears (rendered from by_status.items(), not a .py literal).
    assert re.search(r"delivered\s+\d+", counters_text), (
        f"counters must show a numeric delivered count from by_status: {counters_text!r}"
    )
    # The hardcoded ASCII banner rendered non-empty.
    assert banner_text.strip(), f"banner must render non-empty ASCII art: {banner_text!r}"


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


# --- SAFETY-02: AST proof the view has no write / subprocess API --------------

def test_view_has_no_write_or_subprocess_api() -> None:
    tree = ast.parse(DASHBOARD_PY.read_text(encoding="utf-8"), filename=str(DASHBOARD_PY))

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
                    offenders.append(f"open(mode={arg.value!r})")
            for kw in node.keywords:
                if (
                    kw.arg == "mode"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                    and kw.value.value in write_modes
                ):
                    offenders.append(f"open(mode={kw.value.value!r})")
        # (b) a banned write/subprocess attribute call: x.write_text(...), os.replace(...),
        #     os.remove(...), os.system(...), os.exec*/os.spawn*(...).
        if isinstance(node, ast.Attribute):
            if node.attr in banned_attrs:
                offenders.append(f".{node.attr}")
            if node.attr.startswith(exec_prefixes) and node.attr not in ("execute",):
                offenders.append(f".{node.attr}")
        # (c) a subprocess / os.system reference anywhere (import or attribute base).
        if isinstance(node, ast.Name) and node.id in banned_module_names:
            offenders.append(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in banned_module_names:
            offenders.append(f"{node.value.id}.{node.attr}")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = {a.name for a in node.names}
            if mod in banned_module_names or names & banned_module_names:
                offenders.append(f"import {mod or ','.join(sorted(names))}")

    assert not offenders, f"the view must expose NO write/subprocess API (SAFETY-02): {offenders}"


# --- VIEW-03 (+ strengthened VIEW-04): live runs table rows, status labels, stability -----------

# A well-formed fixture run with a clear projected status (composition documented in
# tests/test_gmj_dashboard_model.py). This test file lives under tests/, which the Phase-20 grep-guard
# does NOT scan, so it may freely name the status WORD it expects the status cell to render.
_KNOWN_RUN_ID = "20260601T120000-del"


async def _probe_runs_table(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll seed the table, then probe rows / status cell / cursor stability."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Two+ ticks let the threaded poll seed every run row via _apply_runs (add_row keyed by run_id).
        await pilot.pause()
        await pilot.pause()
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
        # Two+ ticks let the threaded poll marshal snapshot()["metrics"] back into the panel.
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
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


# --- VIEW-06: read-only candidate + configuration panels ---------------------

async def _probe_candidate_config(pipeline_dir: Path) -> dict:
    """Launch read-only, let the poll fill the candidate + config panels, then read their text."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        cand_text = str(app.query_one("#candidate", Static).render())
        cfg_text = str(app.query_one("#config", Static).render())
        return {"cand_text": cand_text, "cfg_text": cfg_text}


def test_candidate_and_config_panels() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            probe = asyncio.run(_probe_candidate_config(pipe))
        assert "Traceback" not in buf.getvalue(), f"candidate/config probe leaked a traceback: {buf.getvalue()}"

    # VIEW-06: the candidate panel shows the fixture candidate's whitelisted top-fields verbatim.
    cand = probe["cand_text"]
    assert cand.strip(), f"the candidate panel must render non-empty text: {cand!r}"
    assert "Test Candidate" in cand, f"the candidate panel must show the fixture name: {cand!r}"
    assert "Senior Test Engineer" in cand, f"the candidate panel must show the fixture title: {cand!r}"

    # VIEW-06: the config panel shows the governing knobs (execution_mode + retry_cap) verbatim.
    cfg = probe["cfg_text"]
    assert cfg.strip(), f"the config panel must render non-empty text: {cfg!r}"
    assert "autonomous" in cfg, f"the config panel must show the fixture execution_mode: {cfg!r}"
    assert re.search(r"retry_cap\s+5", cfg), f"the config panel must show the fixture retry_cap: {cfg!r}"


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
        # Two+ ticks let the threaded poll marshal snapshot()["stages"] back into the strip.
        await pilot.pause()
        await pilot.pause()
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
        # Two+ ticks let the threaded poll seed the runs table (add_row keyed by run_id).
        await pilot.pause()
        await pilot.pause()
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


async def _probe_vacancies_panel(pipeline_dir: Path) -> str:
    """Launch read-only, let the poll fill the #vac-placeholder panel, then read its rendered text."""
    app = _build_app(pipeline_dir, manage=False, refresh=0.1)
    async with app.run_test(size=(120, 40)) as pilot:
        # Two+ ticks let the threaded poll marshal snapshot()["vacancies"]/["batches"] into the panel.
        await pilot.pause()
        await pilot.pause()
        return str(app.query_one("#vac-placeholder", Static).render())


async def _probe_empty_vacancies_panel() -> str:
    """Launch over an empty pipeline + a repo_root with no offers → expect the empty-state copy."""
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
            return str(app.query_one("#vac-placeholder", Static).render())


def test_vacancies_and_batch_rollup_render() -> None:
    with _temp_pipeline() as pipe:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            vac_text = asyncio.run(_probe_vacancies_panel(pipe))
            empty_text = asyncio.run(_probe_empty_vacancies_panel())
        assert "Traceback" not in buf.getvalue(), f"vacancies probe leaked a traceback: {buf.getvalue()}"

    # VIEW-10: a known frozen offer's fields render verbatim (title · company · seniority · #must-haves).
    assert vac_text.strip(), f"the vacancies panel must render non-empty text: {vac_text!r}"
    for field in (_VAC_TITLE, _VAC_COMPANY, _VAC_SENIORITY):
        assert field in vac_text, f"the vacancies panel must show the offer field {field!r}: {vac_text!r}"
    assert re.search(rf"mh\s+{_VAC_MUST_HAVES}\b", vac_text), (
        f"the vacancies panel must show the must-have count 'mh {_VAC_MUST_HAVES}': {vac_text!r}"
    )

    # VIEW-10: the priced offer's salary appears (min/max + currency), rendered from salary_range.
    for token in ("4000", "6000", "USD"):
        assert token in vac_text, f"the vacancies panel must show the salary token {token!r}: {vac_text!r}"

    # VIEW-10: the batch rollup line shows the batch_id and its delivered/total from snapshot()["batches"].
    assert _BATCH_ID in vac_text, f"the vacancies panel must show the batch id {_BATCH_ID!r}: {vac_text!r}"
    assert _BATCH_ROLLUP in vac_text, (
        f"the vacancies panel must show the batch delivered/total rollup {_BATCH_ROLLUP!r}: {vac_text!r}"
    )

    # VIEW-10 empty states: no offers / no batches degrade to the UI-SPEC copy, never a blank or a crash.
    assert "No frozen offers" in empty_text, f"the empty vacancies panel must show 'No frozen offers': {empty_text!r}"
    assert "No batches" in empty_text, f"the empty vacancies panel must show 'No batches': {empty_text!r}"


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
            # Two+ ticks let the threaded poll seed every run row via _apply_runs.
            await pilot.pause()
            await pilot.pause()
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
    with _temp_pipeline() as pipe:
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
