#!/usr/bin/env python3
"""Tests for scripts/pipeline/gmj_runs.py (ERGO-01, ERGO-02, ERGO-04 + resume + traversal).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_runs.py``. This is the deterministic regression net that gates the
Plan-01 read-only inspector CLI. It proves the EXECUTED projection (not an LLM) guarantees:

- status derivation over the heterogeneous fixture corpus — delivered/running/failed/pending
  plus the ``unknown`` degrade (one malformed state.json) and the no-state.json skip (ERGO-01),
- the ``delivered`` label is PARITY-checked against the canonical, imported
  ``check_delivery.blocked_reason`` (never a re-implemented predicate) so the inspector can
  never diverge from the real Gate A ∧ Gate B gate (T-16-06),
- newest-first ordering by the ``\\d{8}T\\d{6}`` id-timestamp key with the no-timestamp run last
  (ERGO-02),
- ``--json`` is byte-identical across ``PYTHONHASHSEED`` 0 vs 1 (ERGO-02 determinism),
- the READ-ONLY invariant: every fixture ``state.json`` byte content AND ``st_mtime_ns`` is
  UNCHANGED after ``runs list`` + ``run inspect`` — the load-bearing ERGO-04 proof (T-16-05),
- ``run inspect`` surfaces gate verdicts, run-dir artifacts (both gate-log conventions), a
  non-empty attempt history, the RELATIVE ``offer_spec_path`` verbatim, and a PRINTED (never
  executed) resume command; ``batch inspect`` prints ``/gmj-batch --resume <id>`` (ERGO-03),
- a ``../evil`` run_id is rejected (exit 1) with no read outside the runs dir (T-16-01),
- an absent ``batches/`` dir yields an empty exit-0 result.

Discipline (test_gmj_batch.py): every test asserts the exit code AND a specific field/sentinel,
and asserts ``"Traceback" not in result.stderr`` so an unrelated crash's nonzero exit never
masquerades as a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS = REPO_ROOT / "scripts" / "pipeline" / "gmj_runs.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline"

# Import the canonical Gate A ∧ Gate B predicate for the delivered-parity assertion — compare
# the CLI label against blocked_reason itself, NEVER a re-derived predicate (T-16-06).
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import check_delivery  # noqa: E402


def _cli(
    args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNS), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _runs_list_json(env: dict[str, str] | None = None) -> dict:
    r = _cli(["runs", "list", "--pipeline-dir", str(FIXTURES), "--json"], env=env)
    assert r.returncode == 0, f"runs list must exit 0: {r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    return json.loads(r.stdout)


def _inspect_json(run_id: str) -> tuple[subprocess.CompletedProcess[str], dict | None]:
    r = _cli(["run", "inspect", run_id, "--pipeline-dir", str(FIXTURES), "--json"])
    payload = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    return r, payload


# --- ERGO-01: status derivation (+ degrade + skip) ---------------------------

def test_runs_list_status_derivation() -> None:
    doc = _runs_list_json()
    status = {r["run_id"]: r["status"] for r in doc["runs"]}
    expected = {
        "20260601T120000-del": "delivered",
        "20260602T120000-run-ws": "running",
        "20260603T120000-fail": "failed",
        "20260604T120000-pend": "pending",
        "20260606T120000-bad": "unknown",
        "cl-20260605T120000-legacy": "delivered",
        "e2e-notime": "delivered",
    }
    for run_id, want in expected.items():
        assert status.get(run_id) == want, (
            f"{run_id} must derive status {want!r}, got {status.get(run_id)!r}"
        )
    assert "strayonly" not in status, "the no-state.json dir must be skipped, not listed"


# --- ERGO-01/T-16-06: delivered parity with the imported canonical predicate --

def test_delivered_parity_with_check_delivery() -> None:
    doc = _runs_list_json()
    cli_status = {r["run_id"]: r["status"] for r in doc["runs"]}
    checked = 0
    runs_dir = FIXTURES / "runs"
    for run_dir in sorted(runs_dir.iterdir()):
        sp = run_dir / "state.json"
        if not sp.is_file():
            continue
        try:
            state = json.loads(sp.read_text(encoding="utf-8"))
        except ValueError:
            continue  # the malformed 'bad' fixture — projects to unknown, not parity-testable
        if not isinstance(state, dict):
            continue
        gate_results = state.get("gate_results")
        if not isinstance(gate_results, dict):
            gate_results = {}
        expected_delivered = check_delivery.blocked_reason(gate_results) is None
        got_delivered = cli_status.get(run_dir.name) == "delivered"
        assert got_delivered == expected_delivered, (
            f"{run_dir.name}: CLI delivered={got_delivered} must agree with "
            f"blocked_reason(...) is None = {expected_delivered}"
        )
        checked += 1
    assert checked >= 5, f"parity must cover the parseable corpus, checked only {checked}"


# --- ERGO-02: newest-first ordering, no-timestamp run last -------------------

def test_newest_first_ordering() -> None:
    doc = _runs_list_json()
    order = [r["run_id"] for r in doc["runs"]]
    ts_keys = [r["ts"] for r in doc["runs"]]
    # Descending by the ts key; the placeholder '—' (no timestamp) sorts to the end.
    real_ts = [t for t in ts_keys if t != "—"]
    assert real_ts == sorted(real_ts, reverse=True), (
        f"timestamps must be descending (newest-first): {ts_keys}"
    )
    assert order[-1] == "e2e-notime", (
        f"the no-timestamp run must be LAST: {order}"
    )


# --- ERGO-01: degrade — one bad run does not blank the table -----------------

def test_degrade_one_bad_run_still_lists_others() -> None:
    doc = _runs_list_json()
    status = {r["run_id"]: r["status"] for r in doc["runs"]}
    assert status.get("20260606T120000-bad") == "unknown", (
        "the malformed state.json must degrade to an 'unknown' row"
    )
    # ...while the healthy rows still list (one bad run never aborts the table).
    assert status.get("20260601T120000-del") == "delivered", "delivered row must still list"
    assert status.get("20260604T120000-pend") == "pending", "pending row must still list"
    assert len(doc["runs"]) >= 7, f"the bad run must not blank the table: {status}"
    # the no-state.json dir is skipped (not an 'unknown' row, simply absent)
    assert "strayonly" not in status, "the no-state.json dir must be skipped"


# --- ERGO-02: --json byte-determinism across PYTHONHASHSEED ------------------

def test_json_byte_determinism() -> None:
    r0 = _cli(
        ["runs", "list", "--pipeline-dir", str(FIXTURES), "--json"],
        env={"PYTHONHASHSEED": "0"},
    )
    r1 = _cli(
        ["runs", "list", "--pipeline-dir", str(FIXTURES), "--json"],
        env={"PYTHONHASHSEED": "1"},
    )
    assert r0.returncode == 0 and r1.returncode == 0, f"{r0.stderr}\n{r1.stderr}"
    assert "Traceback" not in r0.stderr and "Traceback" not in r1.stderr
    assert r0.stdout.encode("utf-8") == r1.stdout.encode("utf-8"), (
        "runs list --json must be byte-identical across PYTHONHASHSEED 0 and 1"
    )


# --- ERGO-04/T-16-05: READ-ONLY invariant (bytes + st_mtime_ns) --------------

def test_read_only_invariant() -> None:
    runs_dir = FIXTURES / "runs"
    # Snapshot every state.json's bytes AND st_mtime_ns before touching the CLI.
    before: dict[Path, tuple[bytes, int]] = {}
    for sp in sorted(runs_dir.glob("*/state.json")):
        st = sp.stat()
        before[sp] = (sp.read_bytes(), st.st_mtime_ns)
    assert before, "the fixture corpus must contain state.json files to snapshot"

    # Also snapshot the FULL recursive path listing of the whole pipeline fixture dir so a stray
    # NEW file/dir (temp/rename artifact) is caught — not just mutations of known files (WR-02).
    tree_before = {p.relative_to(FIXTURES) for p in FIXTURES.rglob("*")}

    # Exercise ALL FOUR subcommands inside the snapshot window (batch inspect opens run
    # state.json files and is the command most likely to touch multiple run dirs — ERGO-04).
    for cmd in (
        ["runs", "list", "--pipeline-dir", str(FIXTURES)],
        ["run", "inspect", "20260601T120000-del", "--pipeline-dir", str(FIXTURES)],
        ["batches", "list", "--pipeline-dir", str(FIXTURES)],
        ["batch", "inspect", "batch-20260601T120000", "--pipeline-dir", str(FIXTURES)],
    ):
        r = _cli(cmd)
        assert r.returncode == 0, f"{' '.join(cmd)} must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr

    for sp, (raw, mtime_ns) in before.items():
        st = sp.stat()
        assert sp.read_bytes() == raw, f"state.json bytes changed (write!): {sp}"
        assert st.st_mtime_ns == mtime_ns, f"state.json st_mtime_ns changed (write!): {sp}"

    tree_after = {p.relative_to(FIXTURES) for p in FIXTURES.rglob("*")}
    assert tree_after == tree_before, (
        "the pipeline dir listing changed — a file/dir was added or removed (write!): "
        f"added={sorted(str(p) for p in tree_after - tree_before)} "
        f"removed={sorted(str(p) for p in tree_before - tree_after)}"
    )


# --- ERGO-03: inspect verdicts / artifacts / attempts ------------------------

def test_inspect_verdicts_artifacts_attempts() -> None:
    r, payload = _inspect_json("20260601T120000-del")
    assert r.returncode == 0, f"inspect must exit 0: {r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    assert payload is not None
    assert payload["gate_a"] == "pass" and payload["gate_b"] == "pass", (
        f"delivered run must surface both gates pass: {payload}"
    )
    # gate-log filenames present among artifacts; attempts non-empty (both gate logs)
    for fn in ("gate_fit-evaluator_cv_1.json", "gate_truth-verifier_cv_1.json"):
        assert fn in payload["artifacts"], f"artifact {fn} must be listed: {payload['artifacts']}"
        assert fn in payload["attempts"], f"attempt {fn} must be listed: {payload['attempts']}"
    assert payload["attempts"], "attempts must be non-empty for a run with gate logs"

    # legacy run: surfaces the legacy gateA/gateB logs and the RELATIVE offer_spec_path verbatim.
    r2, legacy = _inspect_json("cl-20260605T120000-legacy")
    assert r2.returncode == 0, f"legacy inspect must exit 0: {r2.stderr}"
    assert "Traceback" not in r2.stderr, r2.stderr
    assert legacy is not None
    for fn in ("cover_letter.gateA.json", "cover_letter.gateB.json"):
        assert fn in legacy["attempts"], f"legacy attempt {fn} must be listed: {legacy['attempts']}"
    assert legacy["offer_spec_path"] == "sources/offers/beta-cover-letter.offer-spec.json", (
        f"the relative offer_spec_path must be surfaced verbatim (unresolved): {legacy}"
    )


# --- ERGO-03: resume command PRINTED (never executed) ------------------------

def test_resume_command_printed_not_executed() -> None:
    _, payload = _inspect_json("20260601T120000-del")
    assert payload is not None
    assert "/pipeline-run" in payload["resume_command"], (
        f"run resume_command must contain /pipeline-run: {payload['resume_command']}"
    )
    assert "20260601T120000-del" in payload["resume_command"], (
        f"run resume_command must name the run_id: {payload['resume_command']}"
    )

    r = _cli(
        ["batch", "inspect", "batch-20260601T120000", "--pipeline-dir", str(FIXTURES), "--json"]
    )
    assert r.returncode == 0, f"batch inspect must exit 0: {r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr
    batch = json.loads(r.stdout)
    assert batch["resume_command"] == "/gmj-batch --resume batch-20260601T120000", (
        f"batch resume_command must be the exact /gmj-batch --resume line: {batch['resume_command']}"
    )


# --- T-16-01: path traversal rejected ----------------------------------------

def test_path_traversal_rejected() -> None:
    r = _cli(["run", "inspect", "../evil", "--pipeline-dir", str(FIXTURES)])
    assert r.returncode == 1, f"'../evil' run_id must exit 1: {r.stdout}"
    assert "unsafe" in r.stderr.lower(), f"stderr must name the unsafe id: {r.stderr}"
    assert "Traceback" not in r.stderr, r.stderr


# --- tolerance: an absent batches/ dir is an empty exit-0 result -------------

def test_absent_batches_dir_is_empty() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = _cli(["batches", "list", "--pipeline-dir", tmp, "--json"])
        assert r.returncode == 0, f"absent batches/ must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        doc = json.loads(r.stdout)
        assert doc.get("batches") == [], f"absent batches/ must yield an empty list: {doc}"


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
