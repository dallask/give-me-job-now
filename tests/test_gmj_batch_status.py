#!/usr/bin/env python3
"""Tests for the ``gmj_batch.py status`` subcommand (FANOUT-02).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_batch_status.py``. Proves the EXECUTED deterministic
``status`` subcommand — never hub-authored prose — guarantees:

- ``status`` prints one line per offer in the manifest, covering every selected offer, not
  just ``offer_index=0`` (FANOUT-02, the literal "silently drops an offer" regression this
  phase closes),
- each printed offer line names all three artifact types (cv, cover_letter, interview_prep)
  with their REAL per-type status — delivered, gate-failed, or waiting — never a single
  collapsed pass/fail for the whole offer,
- ``status`` and ``resume`` never disagree about which runs are delivered, because both reuse
  the identical label-AND-gate predicate (``label == "delivered" and blocked_reason(...) is
  None``) rather than ``status`` re-deriving its own check (Pitfall 1 / CR-01 regression
  class),
- the EXISTING ``resume`` subcommand (unmodified by this plan) already reports non-empty
  output naming every incomplete offer — the literal backstop signal Plan 02 wires into the
  doc edits.

Discipline (test_gmj_batch.py:21-23): every test asserts the exit code AND a specific
field/sentinel, and asserts ``"Traceback" not in result.stderr`` so an unrelated crash's
nonzero exit never masquerades as a pass.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BATCH = REPO_ROOT / "scripts" / "pipeline" / "gmj_batch.py"

# Reuse test_gmj_batch.py's own CLI/init/mark/resume/set_gates/run_ids/load_manifest helpers
# verbatim rather than re-deriving them — mirrors this test suite's own precedent of a
# sys.path insert + local import for in-repo module reuse (test_gmj_batch.py:42-45).
sys.path.insert(0, str(REPO_ROOT / "tests"))
import test_gmj_batch as tb  # noqa: E402


def _status(
    cwd: Path, *, batch_id: str = "b1", pipeline_dir: str = ".pipeline"
):
    """CLI-exercise helper for the new ``status`` subcommand, mirroring tb._resume's shape."""
    return tb._cli(
        ["status", "--batch", batch_id, "--pipeline-dir", pipeline_dir], cwd
    )


def _write_3offer_shortlist(cwd: Path) -> Path:
    """Write a 3-entry inline shortlist fixture (the shared 2-entry fixture is too small).

    Field shape matches tests/fixtures/batch/shortlist.thin-and-rich.json's existing entries
    (board/canonical_key/company/language/location/mode/salary/score/seniority/title/
    trace.source_url [+ optional must_haves/trace.excerpt for a non-thin entry) — never the
    stale pending/failed status vocabulary from schemas/samples/batch_manifest.sample.json.
    """
    shortlist = {
        "kind": "offer_shortlist",
        "schema_version": "1.0",
        "shortlist": [
            {
                "board": "https://www.work.ua/",
                "canonical_key": "ibwt-senior-backend-developer-php-laravel-kyiv",
                "company": "IBWT",
                "language": "ua",
                "location": "Kyiv",
                "mode": "hybrid",
                "salary": 4000,
                "score": 1.6666666666666665,
                "seniority": "senior",
                "title": "Senior Backend Developer (PHP / Laravel)",
                "trace": {"source_url": "https://www.work.ua/jobs/7890/"},
            },
            {
                "board": "https://robota.ua/",
                "canonical_key": "softpeak-lead-backend-php-engineer-laravel-kyiv",
                "company": "SoftPeak",
                "language": "ua",
                "location": "Kyiv",
                "mode": "remote",
                "must_haves": [
                    "5+ years commercial PHP",
                    "Production Laravel experience",
                ],
                "salary": 4500,
                "score": 1.6666666666666665,
                "seniority": "lead",
                "title": "Lead Backend PHP Engineer (Laravel)",
                "trace": {
                    "excerpt": "Шукаємо Lead Backend PHP інженера з комерційним досвідом Laravel",
                    "source_url": "https://robota.ua/company/softpeak/vacancy/325215",
                },
            },
            {
                "board": "https://www.work.ua/",
                "canonical_key": "acme-mid-backend-developer-php-kyiv",
                "company": "Acme",
                "language": "ua",
                "location": "Kyiv",
                "mode": "remote",
                "must_haves": ["3+ years commercial PHP"],
                "salary": 3500,
                "score": 1.5,
                "seniority": "mid",
                "title": "Mid Backend Developer (PHP)",
                "trace": {
                    "excerpt": "Шукаємо Mid Backend PHP розробника",
                    "source_url": "https://www.work.ua/jobs/1234/",
                },
            },
        ],
    }
    fixture_path = cwd / "shortlist-3offer.json"
    fixture_path.write_text(json.dumps(shortlist), encoding="utf-8")
    return fixture_path


def _parse_status(stdout: str) -> list[dict]:
    """Parse status stdout into [{offer_index, canonical_key, cv, cover_letter,
    interview_prep}, ...]."""
    rows: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = dict(tok.split("=", 1) for tok in line.split() if "=" in tok)
        if "offer_index" not in fields:
            continue
        rows.append(
            {
                "offer_index": int(fields["offer_index"]),
                "canonical_key": fields.get("canonical_key", ""),
                "cv": fields.get("cv"),
                "cover_letter": fields.get("cover_letter"),
                "interview_prep": fields.get("interview_prep"),
            }
        )
    return rows


def test_status_reports_all_offers_not_just_first() -> None:
    """FANOUT-02's literal regression check: status must NOT silently drop offers 1/2."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        shortlist = _write_3offer_shortlist(cwd)
        r = tb._init(cwd, "all", shortlist=shortlist)
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        rids = tb._run_ids(tb._load_manifest(cwd))

        # offer 0's cv run: delivered label + passing gates -> genuinely delivered.
        tb._set_gates(cwd, rids[(0, "cv")], truth="pass", fit="pass")
        assert tb._mark(cwd, rids[(0, "cv")], "delivered").returncode == 0

        # offers 1 and 2 are left fully untouched (init-seeded "waiting" default).

        r = _status(cwd)
        assert r.returncode == 0, f"status must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        rows = _parse_status(r.stdout)
        idxs = sorted(row["offer_index"] for row in rows)
        assert idxs == [0, 1, 2], (
            f"status must print exactly one line per offer (0, 1, 2) — an implementation that "
            f"only emits offer_index=0 must fail this assertion: {r.stdout!r}"
        )


def test_status_distinguishes_delivered_from_gated_from_waiting() -> None:
    """Each offer's line must reflect its OWN real per-type status — never a collapsed
    single pass/fail for the whole offer."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        shortlist = _write_3offer_shortlist(cwd)
        r = tb._init(cwd, "all", shortlist=shortlist)
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        rids = tb._run_ids(tb._load_manifest(cwd))

        # offer 0: cv run genuinely delivered (label 'delivered' + both gates pass).
        tb._set_gates(cwd, rids[(0, "cv")], truth="pass", fit="pass")
        assert tb._mark(cwd, rids[(0, "cv")], "delivered").returncode == 0

        # offer 1: cv run has a recorded gate FAIL, label left at the init-seeded default
        # (mirrors test_gmj_batch.py's test_resume_delivered_label_but_gate_failed_is_not_delivered
        # gate-stamping pattern, without forging a 'delivered' label here).
        tb._set_gates(cwd, rids[(1, "cv")], truth="pass", fit="fail")

        # offer 2: fully untouched -> every artifact type stays "waiting".

        r = _status(cwd)
        assert r.returncode == 0, f"status must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        rows = {row["offer_index"]: row for row in _parse_status(r.stdout)}

        assert rows[0]["cv"] == "delivered", (
            f"offer 0's cv run (delivered label + passing gates) must report delivered: {rows[0]}"
        )
        assert rows[1]["cv"] != "delivered", (
            f"offer 1's cv run (gate FAIL, label not 'delivered') must NOT report delivered: "
            f"{rows[1]}"
        )
        assert rows[2]["cv"] == "waiting", (
            f"offer 2's untouched cv run must report waiting: {rows[2]}"
        )
        assert rows[2]["cover_letter"] == "waiting", (
            f"offer 2's untouched cover_letter run must report waiting: {rows[2]}"
        )
        assert rows[2]["interview_prep"] == "waiting", (
            f"offer 2's untouched interview_prep run must report waiting: {rows[2]}"
        )
        # offer 0's OTHER artifact types (never touched) must stay waiting too — proving the
        # per-type resolution is independent, not a single collapsed offer-level verdict.
        assert rows[0]["cover_letter"] == "waiting", (
            f"offer 0's untouched cover_letter run must independently report waiting "
            f"(not inherit cv's delivered status): {rows[0]}"
        )


def test_status_and_resume_agree_on_delivered_predicate() -> None:
    """status and resume must never disagree about which runs are delivered (D-06)."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        shortlist = _write_3offer_shortlist(cwd)
        r = tb._init(cwd, "all", shortlist=shortlist)
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        rids = tb._run_ids(tb._load_manifest(cwd))

        # Same seeded state as the distinguishing test above.
        tb._set_gates(cwd, rids[(0, "cv")], truth="pass", fit="pass")
        assert tb._mark(cwd, rids[(0, "cv")], "delivered").returncode == 0
        tb._set_gates(cwd, rids[(1, "cv")], truth="pass", fit="fail")
        # offer 2 fully untouched.

        status_r = _status(cwd)
        assert status_r.returncode == 0, f"status must exit 0: {status_r.stderr}"
        assert "Traceback" not in status_r.stderr, status_r.stderr
        resume_r = tb._resume(cwd)
        assert resume_r.returncode == 0, f"resume must exit 0: {resume_r.stderr}"
        assert "Traceback" not in resume_r.stderr, resume_r.stderr

        # Build the (offer_index, artifact_type) -> delivered? map from status output.
        status_rows = _parse_status(status_r.stdout)
        status_delivered: set[tuple[int, str]] = set()
        status_all: set[tuple[int, str]] = set()
        for row in status_rows:
            for artifact_type in ("cv", "cover_letter", "interview_prep"):
                key = (row["offer_index"], artifact_type)
                status_all.add(key)
                if row[artifact_type] == "delivered":
                    status_delivered.add(key)

        # Build the (offer_index, artifact_type) set resume considers non-delivered.
        resume_rows = tb._parse_resume(resume_r.stdout)
        resume_non_delivered = {
            (row["offer_index"], row["artifact_type"]) for row in resume_rows
        }

        # Every run is exactly one of: reported delivered by status, or listed by resume as
        # non-delivered — never both, never neither (mutually exclusive and jointly exhaustive
        # over all 9 runs: 3 offers x 3 artifact types).
        assert len(status_all) == 9, f"expected 9 total runs (3 offers x 3 types): {status_all}"
        status_non_delivered = status_all - status_delivered
        assert status_non_delivered == resume_non_delivered, (
            "status's non-delivered set must exactly match resume's reported set — "
            f"status non-delivered: {status_non_delivered}, resume: {resume_non_delivered}"
        )
        assert status_delivered.isdisjoint(resume_non_delivered), (
            "a run status reports delivered must never also appear in resume's non-delivered "
            f"output: overlap={status_delivered & resume_non_delivered}"
        )


def test_resume_nonempty_when_offers_incomplete() -> None:
    """The literal backstop signal Plan 02 wires in: resume must be non-empty and name every
    incomplete offer. This is the EXISTING resume subcommand (unmodified by this plan) —
    this test only adds an explicit 3-offer assertion alongside test_gmj_batch.py's existing
    2-offer coverage."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        shortlist = _write_3offer_shortlist(cwd)
        r = tb._init(cwd, "all", shortlist=shortlist)
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        rids = tb._run_ids(tb._load_manifest(cwd))

        # offer 0 fully delivered: all 3 artifact types delivered + passing gates.
        for artifact_type in ("cv", "cover_letter", "interview_prep"):
            tb._set_gates(cwd, rids[(0, artifact_type)], truth="pass", fit="pass")
            assert tb._mark(cwd, rids[(0, artifact_type)], "delivered").returncode == 0

        # offers 1 and 2 left fully "waiting" (incomplete).

        r = tb._resume(cwd)
        assert r.returncode == 0, f"resume must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        assert r.stdout.strip(), "resume's stdout must be non-empty while offers 1/2 are incomplete"
        rows = tb._parse_resume(r.stdout)
        offer_idxs = {row["offer_index"] for row in rows}
        assert 1 in offer_idxs, f"resume must name offer_index=1 as incomplete: {r.stdout!r}"
        assert 2 in offer_idxs, f"resume must name offer_index=2 as incomplete: {r.stdout!r}"
        assert 0 not in offer_idxs, (
            f"offer 0 is fully delivered and must NOT appear in resume's output: {r.stdout!r}"
        )


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
