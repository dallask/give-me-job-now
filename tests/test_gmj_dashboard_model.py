#!/usr/bin/env python3
"""Tests for scripts/dashboard/gmj_dashboard_model.py (MODEL-01/02/03 + SAFETY-03, Plan 20-01 core).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_dashboard_model.py``. This is the deterministic regression net that gates
the safety-critical core of the headless read model. It proves the model NEVER re-derives status
and NEVER blanks a live row on a torn read.

Plan-01 core subset (Plan 02 extends this same file with metrics + thin-reader tests):

- **Shape skeleton (MODEL-01):** ``snapshot()`` returns a plain dict whose top level carries at
  least ``counters``/``runs``/``batches``/``stages``; ``runs``/``batches`` are lists, ``counters``
  is a dict; the whole thing is ``json.dumps``-able.
- **Projection-equality (MODEL-02 / SAFETY-03):** for every WELL-FORMED run fixture (state.json
  parses to a dict), the matching ``snapshot()`` runs-row ``status`` equals
  ``gmj_runs.project_status(state)`` byte-for-byte. ``project_status`` is IMPORTED, never a
  re-derived literal. The torn/invalid ``20260606T120000-bad`` fixture is EXCLUDED here — it is
  uncallable by ``project_status`` and is special-cased in the 4a degrade check below.
- **Grep-guard (SAFETY-03):** an AST-scoped walk over ``scripts/dashboard/*.py`` proves NONE of the
  four re-derived projection statuses (delivered/failed/pending/running), NEITHER gate-node literal
  (gmj-truth-verifier/gmj-fit-evaluator), nor a ``>= retry_cap`` compare appears AS A CODE STRING
  LITERAL / comparison. The ``unknown`` degrade sentinel is DELIBERATELY EXCLUDED from the
  forbidden set — the model legitimately emits it and ``project_status`` never returns it. The
  guard inspects ``ast.Constant`` string values (NOT a raw whole-file substring count), so prose /
  docstrings / comments never false-positive. (This test file itself legitimately contains the
  forbidden tokens; the guard only scans ``scripts/dashboard/``, never ``tests/``.)
- **Torn-read last-good (MODEL-03):** a truncated / empty ``state.json`` on a previously-good run
  serves the cached last-good row across the next poll, never the degrade sentinel; a valid change
  then refreshes the row.
- **Two degrade classes, labelled distinctly:**
  - **4a DEGRADE-CLASS-A** — the committed ``20260606T120000-bad`` fixture holds truncated
    (invalid) JSON; ``project_status`` is uncallable, so its expected status is SPECIAL-CASED to
    the ``unknown`` degrade sentinel (asserted directly, with no last-good present).
  - **4b DEGRADE-CLASS-B** — a runtime tempfile state.json holding a valid-JSON-but-non-dict value
    (a list) degrades to the ``unknown`` row IMMEDIATELY (a valid non-object won't fix itself).

Discipline (mirrors test_gmj_runs.py): every check asserts a specific field AND that no
``Traceback`` leaked to stderr while the model ran (the never-a-traceback contract) — an unrelated
crash can never masquerade as a pass.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline"
DASHBOARD_DIR = REPO_ROOT / "scripts" / "dashboard"

# Import the model under test and the canonical projection via the same sys.path.insert idiom
# tests/test_gmj_runs.py uses (scripts/dashboard for the model, scripts/pipeline for the
# projection). project_status is imported for the equality assertion — NEVER re-derived here.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "dashboard"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_dashboard_model  # noqa: E402
import gmj_runs  # noqa: E402

# Forbidden re-derived projection/gate literals for the grep-guard. NOTE: "unknown" is INTENTIONALLY
# ABSENT — it is the degrade sentinel the model legitimately emits (project_status never returns it,
# and gmj_runs.py writes the literal with no importable sentinel to reuse). This supersedes the
# 20-RESEARCH.md § Validation Architecture list which still names unknown; it matches ROADMAP
# success-criterion 3 (delivered / gmj-truth-verifier / the retry-cap >= compare only).
_FORBIDDEN_STRINGS = frozenset(
    {
        "delivered",
        "failed",
        "pending",
        "running",
        "gmj-truth-verifier",
        "gmj-fit-evaluator",
    }
)


def _snapshot(model: "gmj_dashboard_model.DashboardModel") -> dict:
    """Call snapshot() with stderr captured, asserting the never-a-traceback contract."""
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        snap = model.snapshot()
    assert "Traceback" not in buf.getvalue(), f"snapshot() leaked a traceback: {buf.getvalue()}"
    return snap


def _rows_by_id(snap: dict) -> dict:
    return {r["run_id"]: r for r in snap["runs"]}


# --- MODEL-01: snapshot() shape skeleton -------------------------------------

def test_snapshot_shape_skeleton() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    snap = _snapshot(model)
    assert isinstance(snap, dict), f"snapshot() must return a plain dict: {type(snap)}"
    for key in ("counters", "runs", "batches", "stages"):
        assert key in snap, f"snapshot() must carry the {key!r} panel key: {sorted(snap)}"
    assert isinstance(snap["counters"], dict), "counters must be a dict"
    assert isinstance(snap["runs"], list), "runs must be a list"
    assert isinstance(snap["batches"], list), "batches must be a list"
    # JSON-serializable (MODEL-01): plain dicts/lists/str/int only, no widgets.
    json.dumps(snap)


# --- MODEL-02 / SAFETY-03: projection-equality over the well-formed subset ----

def test_projection_equality_wellformed_subset() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    snap = _snapshot(model)
    rows = _rows_by_id(snap)
    checked = 0
    runs_dir = FIXTURES / "runs"
    for run_dir in sorted(runs_dir.iterdir()):
        sp = run_dir / "state.json"
        if not sp.is_file():
            continue  # strayonly: skipped, never listed
        try:
            state = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError:
            continue  # the torn 20260606T120000-bad fixture — special-cased in 4a, not here
        if not isinstance(state, dict):
            continue
        # The status MUST equal the imported projection verbatim — never a re-derived expected.
        expected = gmj_runs.project_status(state)
        got = rows.get(run_dir.name, {}).get("status")
        assert got == expected, (
            f"{run_dir.name}: snapshot status {got!r} must EQUAL "
            f"gmj_runs.project_status(state)={expected!r} verbatim"
        )
        checked += 1
    assert checked >= 5, f"equality must cover the well-formed corpus, checked only {checked}"


# --- SAFETY-03: AST-scoped string-literal grep-guard --------------------------

def test_grep_guard_no_rederived_literals() -> None:
    sources = sorted(DASHBOARD_DIR.glob("*.py"))
    assert sources, f"the dashboard package must have at least one .py file: {DASHBOARD_DIR}"
    bad_strings: list[str] = []
    bad_compares: list[str] = []
    for src in sources:
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        for node in ast.walk(tree):
            # (a) re-derived status / gate-node string literals (AST-scoped, NOT a raw substring
            #     count — prose/docstrings/comments never false-positive because they are not
            #     ast.Constant *string* values used as code literals).
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in _FORBIDDEN_STRINGS:
                    bad_strings.append(f"{src.name}: {node.value!r}")
            # (b) a retry-cap `>=` comparison (the failed-status re-derivation).
            if isinstance(node, ast.Compare) and any(isinstance(op, ast.GtE) for op in node.ops):
                names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                attrs = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
                if "retry_cap" in (names | attrs):
                    bad_compares.append(f"{src.name}: {ast.dump(node)}")
    assert not bad_strings, f"re-derived status/gate literals found in scripts/dashboard/: {bad_strings}"
    assert not bad_compares, f"retry-cap >= compare found in scripts/dashboard/: {bad_compares}"


# --- MODEL-03: torn read serves last-good, never blanks the row ---------------

def _seed_run(runs_dir: Path, run_id: str, state: dict) -> Path:
    d = runs_dir / run_id
    d.mkdir(parents=True, exist_ok=True)
    sp = d / "state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    return sp


def test_torn_read_serves_last_good() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        run_id = "20260701T120000-torn"
        good = {
            "run_id": run_id,
            "current_step": "gmj-cv-generator",
            "execution_mode": "autonomous",
            "gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "pass"},
            "retry_cap": 2,
        }
        sp = _seed_run(runs_dir, run_id, good)
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(tmp_path), repo_root=REPO_ROOT)

        # Poll 1: populate the last-good cache.
        snap1 = _snapshot(model)
        good_status = _rows_by_id(snap1)[run_id]["status"]
        assert good_status == gmj_runs.project_status(good), "seed row must project verbatim"

        # Sub-case (i): a truncated fragment (writer mid-flight) → serve last-good, NOT unknown.
        sp.write_text('{"run_id": "x", "gate_resu', encoding="utf-8")
        snap2 = _snapshot(model)
        assert _rows_by_id(snap2)[run_id]["status"] == good_status, (
            "a truncated state.json must serve the last-good status, never blank to unknown"
        )

        # Sub-case (ii): an empty (zero-byte truncate window) file → still last-good.
        sp.write_text("", encoding="utf-8")
        snap3 = _snapshot(model)
        assert _rows_by_id(snap3)[run_id]["status"] == good_status, (
            "an empty state.json must serve the last-good status, never blank to unknown"
        )

        # Restore valid-but-CHANGED JSON → the row refreshes (last-good is superseded).
        changed = dict(good)
        changed["gate_results"] = {"gmj-truth-verifier": "fail"}
        sp.write_text(json.dumps(changed), encoding="utf-8")
        snap4 = _snapshot(model)
        assert _rows_by_id(snap4)[run_id]["status"] == gmj_runs.project_status(changed), (
            "valid changed JSON must refresh the row to the newly-projected status"
        )


# --- MODEL-03 / 4a: DEGRADE-CLASS-A — committed torn fixture, no last-good -----

def test_degrade_class_a_committed_torn_fixture_unknown() -> None:
    # The committed 20260606T120000-bad fixture holds truncated (invalid) JSON. project_status is
    # UNCALLABLE on it, so its expected status is SPECIAL-CASED to the 'unknown' degrade sentinel,
    # asserted directly (NOT derived via project_status). This is the same class as a torn read
    # whose retry budget is spent with no last-good entry.
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    snap = _snapshot(model)
    rows = _rows_by_id(snap)
    assert rows.get("20260606T120000-bad", {}).get("status") == "unknown", (
        "a torn/unparseable state.json with no last-good must degrade to the 'unknown' sentinel"
    )
    # ...and one bad row never aborts the table (healthy rows still list).
    assert rows.get("20260601T120000-del", {}).get("status") == "delivered", (
        "the delivered row must still list beside the degraded row"
    )
    assert "strayonly" not in rows, "the no-state.json dir must be skipped, not listed"


# --- MODEL-03 / 4b: DEGRADE-CLASS-B — runtime non-dict → immediate unknown -----

def test_degrade_class_b_nondict_immediate_unknown() -> None:
    # A valid-JSON-but-non-dict state.json (a list) is GENUINELY malformed — it degrades to the
    # 'unknown' row IMMEDIATELY (no retry; a valid non-object won't fix itself), with no last-good
    # needed to prove the path. Distinct from 4a (which is torn/unparseable, not non-dict).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        run_id = "20260702T120000-nondict"
        d = runs_dir / run_id
        d.mkdir(parents=True)
        (d / "state.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(tmp_path), repo_root=REPO_ROOT)
        snap = _snapshot(model)
        assert _rows_by_id(snap).get(run_id, {}).get("status") == "unknown", (
            "a valid-JSON-but-non-dict state.json must degrade immediately to 'unknown'"
        )


# --- MODEL-04: domain metric aggregation over the known-count pipeline corpus -

# The pipeline fixture corpus (tests/fixtures/pipeline/runs) has a KNOWN composition:
#   del      -> delivered (both gates pass)                       gate_a=pass gate_b=pass
#   run-ws   -> running  (fit fail, cv retry 2 < cap 3)           gate_a=pass gate_b=fail  retries+2
#   fail     -> failed   (truth fail, cv retry 2 >= cap 2)        gate_a=fail gate_b=—     retries+2
#   pend     -> pending  (empty gate_results, seeded)             gate_a=—    gate_b=—
#   bad      -> unknown  (committed torn/unparseable state.json)  gate_a=—    gate_b=—     (no metric input)
#   legacy   -> delivered (both gates pass)                       gate_a=pass gate_b=pass  retries+1
#   e2e      -> delivered (both gates pass, NO timestamp)         gate_a=pass gate_b=pass
#   strayonly-> skipped (no state.json)
# by_status {delivered:3, running:1, failed:1, pending:1, unknown:1}; gate_a {pass:4,fail:1};
# gate_b {pass:3,fail:1}; retries_used 5; retry_cap sum 14 -> cap_space 9; throughput 6 buckets of 1
# (e2e-notime excluded — no \d{8}T\d{6} substring).


def test_metrics_by_status_buckets() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    metrics = _snapshot(model)["metrics"]
    assert metrics["by_status"] == {
        "delivered": 3,
        "running": 1,
        "failed": 1,
        "pending": 1,
        "unknown": 1,
    }, f"by_status buckets must be a data-derived Counter over projected statuses: {metrics['by_status']}"


def test_metrics_gate_a_b_tallies() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    metrics = _snapshot(model)["metrics"]
    # An absent verdict ("—") counts as NEITHER pass nor fail (never counted as fail).
    assert metrics["gate_a"] == {"pass": 4, "fail": 1}, metrics["gate_a"]
    assert metrics["gate_b"] == {"pass": 3, "fail": 1}, metrics["gate_b"]


def test_metrics_retries_used_and_cap_space() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    metrics = _snapshot(model)["metrics"]
    # Sum of innermost int retry counters (bool excluded): run-ws 2 + fail 2 + legacy 1 = 5.
    assert metrics["retries_used"] == 5, metrics["retries_used"]
    # SUM-vs-SUM headroom (not a per-run >= retry_cap compare): sum(retry_cap)=14 minus retries_used 5.
    assert metrics["cap_space"] == 9, metrics["cap_space"]


def test_metrics_throughput_excludes_no_timestamp_runs() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    metrics = _snapshot(model)["metrics"]
    tp = metrics["throughput"]
    assert isinstance(tp, list) and all(isinstance(x, int) for x in tp), f"throughput must be a list of ints: {tp!r}"
    # 7 listed rows minus the single no-timestamp run (e2e-notime) = 6 timestamped runs, one per day.
    assert sum(tp) == 6, f"throughput must count only timestamped runs: {tp!r} (sum {sum(tp)})"
    assert len(tp) == 6, f"the six distinct-day buckets must each appear: {tp!r}"


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
