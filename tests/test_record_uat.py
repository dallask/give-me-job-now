#!/usr/bin/env python3
"""Deterministic tests for scripts/testing/gmj_record_uat.py (plain python3, no pytest).

All writes are scoped to a mkdtemp() dir via --results-file/--state-file, so the real
.planning/STATE.md and UAT-RESULTS.md are never touched.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "testing" / "gmj_record_uat.py"

STATE_STUB = """# Project State

## Deferred Verification

| Phase | State | Item | Resume |
|-------|-------|------|--------|
| 08 | e2e03 | live real-offer run | run /gmj-pipeline-run |

## Session Continuity

Last session: today
"""


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


def test_list_seeds_all_pending() -> None:
    with tempfile.TemporaryDirectory() as d:
        r = _run("--list", "--results-file", f"{d}/UAT.md", "--state-file", f"{d}/STATE.md", cwd=REPO_ROOT)
        assert r.returncode == 0, r.stderr
        # all 11 registry ids appear, all pending, gating verdict "not yet accepted"
        assert r.stdout.count("pending") >= 11, r.stdout
        assert "not yet accepted" in r.stdout


def test_record_pass_writes_ledger_and_state_marker() -> None:
    with tempfile.TemporaryDirectory() as d:
        results = Path(d) / "UAT-RESULTS.md"
        state = Path(d) / "STATE.md"
        state.write_text(STATE_STUB, encoding="utf-8")
        r = _run("--id", "UAT-05", "--result", "pass", "--notes", "eval_truth 1.0",
                 "--date", "2026-07-04", "--results-file", str(results), "--state-file", str(state),
                 cwd=REPO_ROOT)
        assert r.returncode == 0, r.stderr
        led = results.read_text(encoding="utf-8")
        assert "| UAT-05 |" in led and "PASS" in led and "eval_truth 1.0" in led and "2026-07-04" in led
        # state marker inserted under the heading, one gating item still failing → not accepted
        st = state.read_text(encoding="utf-8")
        assert "> **UAT acceptance:**" in st
        assert "UAT-05 PASS" in st and "E2E-03 pending" in st
        assert "not yet accepted" in st
        # heading + marker adjacency preserved; original table row untouched
        assert "## Deferred Verification" in st and "| 08 | e2e03 |" in st


def test_marker_is_idempotent_not_duplicated() -> None:
    with tempfile.TemporaryDirectory() as d:
        results = Path(d) / "UAT-RESULTS.md"
        state = Path(d) / "STATE.md"
        state.write_text(STATE_STUB, encoding="utf-8")
        for res in ("pass", "fail", "pass"):
            _run("--id", "UAT-05", "--result", res, "--date", "2026-07-04",
                 "--results-file", str(results), "--state-file", str(state), cwd=REPO_ROOT)
        st = state.read_text(encoding="utf-8")
        assert st.count("> **UAT acceptance:**") == 1, "marker must be replaced, never duplicated"


def test_both_gating_pass_marks_accepted() -> None:
    with tempfile.TemporaryDirectory() as d:
        results = Path(d) / "UAT-RESULTS.md"
        state = Path(d) / "STATE.md"
        state.write_text(STATE_STUB, encoding="utf-8")
        _run("--id", "UAT-05", "--result", "pass", "--date", "2026-07-04",
             "--results-file", str(results), "--state-file", str(state), cwd=REPO_ROOT)
        _run("--id", "E2E-03", "--result", "pass", "--date", "2026-07-04",
             "--results-file", str(results), "--state-file", str(state), cwd=REPO_ROOT)
        st = state.read_text(encoding="utf-8")
        led = results.read_text(encoding="utf-8")
        assert "behavioral acceptance: ACCEPTED" in st, st
        assert "behavioral acceptance: ACCEPTED" in led, led


def test_unknown_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as d:
        r = _run("--id", "UAT-99", "--result", "pass",
                 "--results-file", f"{d}/UAT.md", "--state-file", f"{d}/STATE.md", cwd=REPO_ROOT)
        assert r.returncode == 1
        assert "must be one of" in r.stderr


def test_reload_roundtrip_preserves_prior_results() -> None:
    with tempfile.TemporaryDirectory() as d:
        results = Path(d) / "UAT-RESULTS.md"
        state = Path(d) / "STATE.md"
        state.write_text(STATE_STUB, encoding="utf-8")
        _run("--id", "UAT-02", "--result", "pass", "--notes", "hook fired", "--date", "2026-07-04",
             "--results-file", str(results), "--state-file", str(state), cwd=REPO_ROOT)
        # recording a DIFFERENT id must not wipe the first
        _run("--id", "UAT-06", "--result", "blocked", "--date", "2026-07-04",
             "--results-file", str(results), "--state-file", str(state), cwd=REPO_ROOT)
        led = results.read_text(encoding="utf-8")
        assert "| UAT-02 | " in led and "hook fired" in led
        assert "| UAT-06 |" in led and "BLOCKED" in led


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
