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
import os
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


# --- VIEW-12: failures() builder surfaces Gate A/Gate B failure detail -------

def test_failures_builder_gate_a_and_b() -> None:
    # Projection-equality style over the enriched fail fixtures: the fail run surfaces a Gate A
    # reason with a populated offending_claims list; run-ws surfaces a Gate B reason with the
    # missing_ids/missing_must_haves detail; a delivered run yields no entry.
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    snap = _snapshot(model)  # never-a-traceback discipline
    errors = snap["errors"]
    assert isinstance(errors, list), f"snapshot()['errors'] must be a list: {type(errors)}"
    # snapshot()['errors'] mirrors the direct builder call.
    assert errors == model.failures(), "snapshot()['errors'] must equal failures()"
    by_run = {e["run_id"]: e for e in errors}

    # Gate A: the enriched fail run carries a non-empty offending_claims list with the right rules.
    fail = by_run.get("20260603T120000-fail")
    assert fail is not None, "the Gate A fail run must appear in failures()"
    assert fail["gate_a"] == "fail", f"row gate_a must be the projected fail VALUE: {fail}"
    a_reasons = [r for r in fail["reasons"] if r["gate"] == "A"]
    assert a_reasons, f"the fail run must carry a Gate A reason: {fail['reasons']}"
    claims = a_reasons[0]["offending_claims"]
    assert isinstance(claims, list) and claims, f"offending_claims must be non-empty: {claims}"
    assert {c["rule_violated"] for c in claims} == {"numeric_invention", "scope_inflation"}, claims

    # Gate B: run-ws carries the missing_ids + missing_must_haves detail.
    ws = by_run.get("20260602T120000-run-ws")
    assert ws is not None, "the Gate B fail run (run-ws) must appear in failures()"
    b_reasons = [r for r in ws["reasons"] if r["gate"] == "B"]
    assert b_reasons, f"run-ws must carry a Gate B reason: {ws['reasons']}"
    assert b_reasons[0]["missing_ids"] == ["mh-2", "mh-3"], b_reasons[0]["missing_ids"]
    assert {m["id"] for m in b_reasons[0]["missing_must_haves"]} == {"mh-2", "mh-3"}, b_reasons[0]

    # A delivered/pass run contributes NO failures entry.
    assert "20260601T120000-del" not in by_run, "a delivered (both-pass) run must not appear in failures()"


def test_throughput_by_status() -> None:
    # metrics["throughput_by_status"] is a dict keyed by projected status VALUE, each a day-count
    # list of ints. Keys are a subset of by_status; the grand total equals the global throughput sum
    # (both exclude the single no-timestamp run).
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    metrics = _snapshot(model)["metrics"]
    tbs = metrics["throughput_by_status"]
    assert isinstance(tbs, dict), f"throughput_by_status must be a dict: {type(tbs)}"
    by_status = metrics["by_status"]
    assert set(tbs) <= set(by_status), f"keys must be data-derived from by_status: {set(tbs)} vs {set(by_status)}"
    for status, series in tbs.items():
        assert isinstance(series, list) and all(isinstance(x, int) for x in series), (
            f"throughput_by_status[{status!r}] must be a list of ints: {series!r}"
        )
    # Grand total consistent with the global throughput (both drop e2e-notime — the one no-ts run).
    total = sum(sum(series) for series in tbs.values())
    assert total == sum(metrics["throughput"]) == 6, f"per-status day totals must reconcile: {tbs!r}"
    # delivered has one no-timestamp member (e2e) → its timestamped sum is by_status - 1.
    assert sum(tbs.get("delivered", [])) == by_status["delivered"] - 1, tbs.get("delivered")


# --- VIEW-13: activity() builder — newest-first started/gate/terminal union ---

def test_activity_builder_order() -> None:
    # The activity feed is a newest-first (ts, seq)-descending union: each run contributes a started
    # event (seq -1), one gate event per gate envelope carrying a verdict, and a terminal event
    # (seq 10**6) whose status is the projected row VALUE. Gate C advisory (no verdict) is skipped.
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    snap = _snapshot(model)
    acts = snap["activity"]
    assert isinstance(acts, list), f"snapshot()['activity'] must be a list: {type(acts)}"
    assert acts == model.activity(), "snapshot()['activity'] must equal activity()"

    # Newest-first: (ts, seq) is non-increasing across the list.
    keys = [(e["ts"], e["seq"]) for e in acts]
    assert keys == sorted(keys, reverse=True), f"activity() must be (ts, seq)-descending: {keys}"

    # Every gate event carries a real verdict (no-verdict envelopes never produce a gate event).
    for e in acts:
        if e["kind"] == "gate":
            assert e["verdict"] is not None, f"a gate event must carry a verdict: {e}"

    # The enriched fail run contributes started + >=1 gate + terminal, terminal status = projection.
    fe = [e for e in acts if e["run_id"] == "20260603T120000-fail"]
    kinds = [e["kind"] for e in fe]
    assert "started" in kinds, f"fail run must have a started event: {kinds}"
    assert kinds.count("gate") >= 1, f"fail run must have >=1 gate event: {kinds}"
    terminals = [e for e in fe if e["kind"] == "terminal"]
    assert len(terminals) == 1, f"fail run must have exactly one terminal event: {kinds}"
    state = json.loads((FIXTURES / "runs" / "20260603T120000-fail" / "state.json").read_text())
    assert terminals[0]["status"] == gmj_runs.project_status(state), (
        "terminal status must equal the IMPORTED projection, never a re-derived literal"
    )

    # Truncation to limit.
    assert len(model.activity(limit=2)) <= 2, "activity(limit) must truncate to the limit"


def test_activity_skips_gate_c_advisory() -> None:
    # A Gate C advisory envelope has NO verdict key → it must contribute no gate event, while a
    # sibling verdict-bearing envelope does. Seeded in a tempdir (no committed fixture perturbed).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        runs_dir = tmp_path / "runs"
        run_id = "20260703T120000-adv"
        d = runs_dir / run_id
        d.mkdir(parents=True)
        (d / "state.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "pass"},
                    "retry_cap": 2,
                }
            ),
            encoding="utf-8",
        )
        (d / "gate_gmj-fit-evaluator_cv_0.json").write_text(
            json.dumps({"kind": "gate_result", "schema_version": "1.0",
                        "content": {"gate": "B", "verdict": "pass"}}),
            encoding="utf-8",
        )
        (d / "gate_c_gmj-fit-evaluator_cv_0.json").write_text(
            json.dumps({"kind": "gate_result", "schema_version": "1.0",
                        "content": {"gate": "C", "advisory": True,
                                    "polish": {"clarity": 4, "concision": 4, "formatting": 4,
                                               "quantified_impact": 4, "natural_keywords": 4}}}),
            encoding="utf-8",
        )
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(tmp_path), repo_root=REPO_ROOT)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            acts = model.activity()
        assert "Traceback" not in buf.getvalue(), "activity() must never leak a traceback"
        gate_events = [e for e in acts if e["run_id"] == run_id and e["kind"] == "gate"]
        assert len(gate_events) == 1, f"only the verdict-bearing envelope yields a gate event: {gate_events}"
        assert all(e["gate"] != "C" for e in gate_events), "a Gate C advisory must produce no gate event"


# --- MODEL-05: thin readers over a deterministic fixture repo_root -----------

DASH_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "dashboard"


def _thin_model() -> "gmj_dashboard_model.DashboardModel":
    # pipeline_dir left at the (absent) default so runs/batches are empty — this model exercises the
    # thin readers, which read from repo_root (the deterministic dashboard fixture corpus).
    return gmj_dashboard_model.DashboardModel(pipeline_dir=str(DASH_FIXTURES / "nopipeline"), repo_root=DASH_FIXTURES)


def test_vacancies_thin_reader() -> None:
    snap = _snapshot(_thin_model())
    vac = snap["vacancies"]
    # Two *.offer-spec.json files (glob-ordered); the *.draft.json decoy is NOT included.
    assert len(vac) == 2, f"vacancies must glob only *.offer-spec.json (2 specs, decoy excluded): {vac}"
    by_hash = {v["offer_spec_hash"]: v for v in vac}
    alpha = by_hash["aaaa1111"]
    assert alpha["title"] == "Backend Engineer"
    assert alpha["company"] == "TestCorp"
    assert alpha["location"] == "Testville"
    assert alpha["seniority"] == "senior"
    assert alpha["salary_range"] == {"min": 4000, "max": 6000, "currency": "USD"}
    assert alpha["n_must_haves"] == 3, "n_must_haves is len(content.must_haves)"
    beta = by_hash["bbbb2222"]
    assert beta["salary_range"] is None, "a null salary_range is displayed verbatim"
    assert beta["n_must_haves"] == 2
    # counters.offers mirrors the vacancies count.
    assert snap["counters"]["offers"] == 2


def test_offer_detail_reader() -> None:
    model = _thin_model()
    detail = model.offer_detail("aaaa1111")
    assert detail["title"] == "Backend Engineer"
    assert detail["company"] == "TestCorp"
    assert detail["must_haves"] == ["Python", "PostgreSQL", "REST APIs"]
    assert detail["spec_basename"] == "alpha-backend-engineer.offer-spec.json"
    assert model.offer_detail("missing-hash") == {}


def test_candidate_thin_reader_top_fields_only() -> None:
    cand = _thin_model()._candidate()
    assert cand["name"] == "Test Candidate"
    assert cand["title"] == "Senior Test Engineer"
    assert cand["summary"].startswith("A concise fixture summary")
    assert cand["contact"] == {"email": "candidate@example.test", "phone": "+10000000000"}
    # expertise_top is the first N of the expertise list (a truncation, not the whole list).
    assert isinstance(cand["expertise_top"], list)
    assert cand["expertise_top"][0] == "Python"
    assert "Extra Skill Nine" not in cand["expertise_top"], "expertise_top must truncate the list"
    # The thin reader must NEVER surface non-whitelisted fields (e.g. key_achievements).
    assert "key_achievements" not in cand


def test_config_thin_reader_and_dag_from_disk() -> None:
    snap = _snapshot(_thin_model())
    cfg = snap["config"]
    assert cfg["boards"] == ["https://board-one.test/", "https://board-two.test/"], cfg["boards"]
    assert cfg["cities"] == ["Testville"]
    assert cfg["languages"] == ["en"]
    assert cfg["execution_mode"] == "autonomous"
    assert cfg["retry_cap"] == 5
    assert cfg["fit_thresholds"]["coverage_threshold"] == 0.7
    assert cfg["preferences"]["salary"]["min"] == 3000
    # stages.dag is the ordered `steps` keys READ from config/pipeline.dag.yaml (never hardcoded).
    assert snap["stages"]["dag"] == ["node-alpha", "node-beta", "node-gamma"], snap["stages"]["dag"]
    # counters mirror the config knobs.
    assert snap["counters"]["mode"] == "autonomous"
    assert snap["counters"]["retry_cap"] == 5


def test_config_yaml_files_and_file_text() -> None:
    model = _thin_model()
    snap = _snapshot(model)
    files = snap["config_files"]
    assert "config/pipeline.config.yaml" in files, files
    assert "config/sources.yaml" in files, files
    assert all(path.startswith("config/") and path.endswith(".yaml") for path in files)
    payload = model.config_file_text("config/pipeline.config.yaml")
    assert payload.get("path") == "config/pipeline.config.yaml"
    assert "execution_mode: autonomous" in (payload.get("text") or "")
    assert model.config_file_text("../config/pipeline.config.yaml").get("error")
    assert model.config_file_text("config/missing.yaml").get("error")


def test_pipeline_activity_detects_in_flight_work() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    pa = model.pipeline_activity()
    assert pa["active"], f"fixture corpus must include in-flight pipeline work: {pa}"
    assert pa["active_run_ids"], f"expected active run ids: {pa}"
    snap = _snapshot(model)
    assert snap["pipeline_activity"]["active"]


def test_missing_files_degrade_without_raising() -> None:
    # A repo_root with NO config/ and NO sources/offers/ must degrade to {}/[] — never raise.
    with tempfile.TemporaryDirectory() as tmp:
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(Path(tmp) / "nopipeline"), repo_root=Path(tmp))
        snap = _snapshot(model)
        assert snap["vacancies"] == [], "a missing offers dir degrades to []"
        assert snap["features"] == [], "a missing .claude catalog degrades features to []"
        assert snap["config"]["boards"] == [], "a missing sources.yaml degrades boards to []"
        assert snap["config_files"] == [], "a missing config/ dir degrades config_files to []"
        assert snap["stages"]["dag"] == [], "a missing pipeline.dag.yaml degrades dag to []"
        json.dumps(snap)  # still JSON-serializable


# --- MODEL-01 finalize: nine-key shape + JSON-serializable ---------------------

def test_snapshot_nine_key_shape_and_json_serializable() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=DASH_FIXTURES)
    snap = _snapshot(model)
    assert set(snap) >= {
        "counters", "metrics", "stages", "runs", "batches",
        "vacancies", "features", "config", "config_files", "run_detail",
        "pipeline_activity",
    }, f"snapshot() must carry all panel keys: {sorted(snap)}"
    assert set(snap["stages"]) >= {"dag", "active"}, "stages must carry dag + active"
    json.dumps(snap)  # the whole nine-key dict is plain dicts/lists/str/int only


# --- MODEL-01: run_detail on-demand accessor (valid + unsafe) ------------------

def test_run_detail_valid_id() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    detail = model.run_detail("20260601T120000-del")
    assert detail.get("kind") == "run_inspect", f"run_detail must return the run_inspect payload: {detail}"
    assert detail["run_id"] == "20260601T120000-del"
    # status is the IMPORTED projection, never re-derived.
    state = json.loads((FIXTURES / "runs" / "20260601T120000-del" / "state.json").read_text())
    assert detail["status"] == gmj_runs.project_status(state)
    for key in ("offer_spec_path", "offer_spec_hash", "retry_cap", "retry_counts",
                "current_step", "artifacts", "attempts", "resume_command"):
        assert key in detail, f"run_detail must carry the {key!r} field"
    # snapshot()'s run_detail stays {} — the accessor is on-demand (not per-poll).
    assert _snapshot(model)["run_detail"] == {}


def test_run_detail_unsafe_or_absent_returns_empty() -> None:
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        assert model.run_detail("../../etc/passwd") == {}, "an unsafe run_id must return {}"
        assert model.run_detail("does-not-exist") == {}, "an absent run_id must return {}"
    assert "Traceback" not in buf.getvalue(), "run_detail must never leak a traceback"


# --- MODEL-01: read-only invariant (bytes + st_mtime_ns unchanged) ------------

def test_read_only_invariant_state_unchanged() -> None:
    sp = FIXTURES / "runs" / "20260601T120000-del" / "state.json"
    before_bytes = sp.read_bytes()
    before_mtime = sp.stat().st_mtime_ns
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    _snapshot(model)
    model.run_detail("20260601T120000-del")  # the drill-in path is read-only too
    assert sp.read_bytes() == before_bytes, "snapshot()/run_detail must not alter state.json bytes"
    assert sp.stat().st_mtime_ns == before_mtime, "snapshot()/run_detail must not touch state.json mtime"


# --- RELOAD-02: read-only launches() liveness filter (never deletes) ----------

# A pid that is guaranteed NOT to exist (above the OS pid_max on Linux/macOS) — deterministic
# "dead" without the pid-reuse flakiness of a reaped child.
_IMPOSSIBLE_PID = 2**31 - 1


def _seed_launch(launches_dir: Path, launch_id: str, payload: dict) -> Path:
    """Seed a launches/ sidecar exactly as the actions writer would (the test may write freely)."""
    launches_dir.mkdir(parents=True, exist_ok=True)
    p = launches_dir / f"{launch_id}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_is_pid_alive_edge_cases() -> None:
    # _is_pid_alive rejects pid<=0 / None / bool / non-int BEFORE probing (never signal a process
    # group), treats an impossible pid as dead, and reports this live process as alive. Never raises.
    model = gmj_dashboard_model.DashboardModel(pipeline_dir=str(FIXTURES), repo_root=REPO_ROOT)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        for bad in (0, -1, None, True, False, "x", 3.5, [1]):
            assert model._is_pid_alive(bad) is False, f"pid {bad!r} must be rejected as not-alive"
        assert model._is_pid_alive(_IMPOSSIBLE_PID) is False, "an impossible pid must be dead"
        assert model._is_pid_alive(os.getpid()) is True, "this live process pid must be alive"
    assert "Traceback" not in buf.getvalue(), "_is_pid_alive must never leak a traceback"


def test_launches_liveness_filter_and_never_deletes() -> None:
    # _launches() over a live + dead sidecar returns ONLY the live one, each row carrying the
    # {launch_id,kind,label,pid,launched_at} fields; the dead sidecar file is STILL on disk after.
    with tempfile.TemporaryDirectory() as tmp:
        launches_dir = Path(tmp) / "launches"
        _seed_launch(launches_dir, "20260707T120000-aaa", {
            "launch_id": "20260707T120000-aaa", "kind": "collective", "label": "gmj-collective",
            "pid": os.getpid(), "launched_at": "2026-07-07T12:00:00Z", "cmd": "claude -p ...",
        })
        dead = _seed_launch(launches_dir, "20260707T120001-bbb", {
            "launch_id": "20260707T120001-bbb", "kind": "interview", "label": "gmj-interview",
            "pid": _IMPOSSIBLE_PID, "launched_at": "2026-07-07T12:00:01Z", "cmd": "claude -p ...",
        })
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=tmp, repo_root=REPO_ROOT)
        rows = model._launches()
        ids = {r["launch_id"] for r in rows}
        assert ids == {"20260707T120000-aaa"}, f"only the live-pid launch must survive: {ids}"
        row = rows[0]
        assert set(row) == {"launch_id", "kind", "label", "pid", "launched_at"}, row
        assert row["kind"] == "collective" and row["label"] == "gmj-collective", row
        # The model NEVER deletes — the dead sidecar file is still on disk.
        assert dead.is_file(), "the read model must not delete a dead-pid sidecar"


def test_launches_skips_torn_or_nondict_sidecar() -> None:
    # A torn (truncated) sidecar and a valid-JSON-but-non-dict sidecar are both SKIPPED (never a
    # degrade row, never a raise); snapshot() leaks no traceback (never-a-traceback contract).
    with tempfile.TemporaryDirectory() as tmp:
        launches_dir = Path(tmp) / "launches"
        launches_dir.mkdir(parents=True)
        (launches_dir / "20260707T120002-torn.json").write_text('{"pid": 1, "kin', encoding="utf-8")
        (launches_dir / "20260707T120003-list.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        model = gmj_dashboard_model.DashboardModel(pipeline_dir=tmp, repo_root=REPO_ROOT)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rows = model._launches()
        assert rows == [], "torn / non-dict sidecars must be skipped, not degrade-rowed"
        assert "Traceback" not in buf.getvalue(), "_launches() must never leak a traceback"


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
