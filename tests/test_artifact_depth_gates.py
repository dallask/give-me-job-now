#!/usr/bin/env python3
"""Gates-green integration test for the Phase-14 richer artifacts (Plan 14-05).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. This proves the EXISTING Gate A + Gate B mechanisms stay
green on the depth-phase fixtures — no new gate is added, no gate flag is changed:

- Gate A on the rich interview-prep fixture: ``gmj_check_claims.py`` exit 0 AND
  ``gmj_check_truth.py`` exit 0 (every span resolves, every number in-span).
- Gate A on the toned cover-letter fixture: ``gmj_check_claims.py`` exit 0 AND
  ``gmj_check_truth.py`` exit 0 (offer-register tone is phrasing only — still span-traced).
- Gate B on the rich interview-prep fixture: ``gmj_score_fit.py`` exit 0 against the committed
  ``offer.python-mid.sample.json`` with the plan's coverage_map + ``fit_thresholds.yaml``.

Every gate is invoked with NO mode/bypass flag — the gates block identically in all modes.
Assertions carry stderr in the failure message. Only stdlib is used here (the gates
themselves pull in PyYAML + jsonschema).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

CHECK_CLAIMS = REPO_ROOT / "scripts" / "artifacts" / "gmj_check_claims.py"
CHECK_TRUTH = REPO_ROOT / "scripts" / "artifacts" / "gmj_check_truth.py"
SCORE_FIT = REPO_ROOT / "scripts" / "artifacts" / "gmj_score_fit.py"

CANDIDATE = REPO_ROOT / "config" / "candidate.yaml"
THRESHOLDS = REPO_ROOT / "config" / "fit_thresholds.yaml"

RICH_INTERVIEW = FIXTURES / "interview_prep.rich.draft.json"
TONED_COVER = FIXTURES / "cover_letter.toned.draft.json"
OFFER = FIXTURES / "fit" / "offer.python-mid.sample.json"
RICH_COVERAGE_MAP = FIXTURES / "interview_prep.rich.coverage_map.json"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _fail_msg(label: str, result: subprocess.CompletedProcess) -> str:
    return (
        f"{label}: expected exit 0, got {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


def _gate_a_clean(draft: Path, label: str) -> None:
    """Both Gate-A pre-gates must exit 0 on *draft* (span-clean + no numeric invention)."""
    claims = _run(str(CHECK_CLAIMS), "--file", str(draft), "--candidate", str(CANDIDATE))
    assert claims.returncode == 0, _fail_msg(f"{label} check_claims", claims)
    truth = _run(str(CHECK_TRUTH), "--file", str(draft), "--candidate", str(CANDIDATE))
    assert truth.returncode == 0, _fail_msg(f"{label} check_truth", truth)


def test_rich_interview_prep_passes_gate_a() -> None:
    _gate_a_clean(RICH_INTERVIEW, "rich interview_prep")


def test_toned_cover_letter_passes_gate_a() -> None:
    _gate_a_clean(TONED_COVER, "toned cover_letter")


def test_rich_interview_prep_passes_gate_b() -> None:
    result = _run(
        str(SCORE_FIT),
        "--file",
        str(RICH_INTERVIEW),
        "--offer",
        str(OFFER),
        "--coverage-map",
        str(RICH_COVERAGE_MAP),
        "--thresholds",
        str(THRESHOLDS),
    )
    assert result.returncode == 0, _fail_msg("rich interview_prep score_fit", result)


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
