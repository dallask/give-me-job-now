#!/usr/bin/env python3
"""Behavior tests for the advisory offer-liveness checker (GUIDE-03).

Runnable as a plain assertion script (no pytest dependency), mirroring
``tests/test_check_offer.py``. Proves ``scripts/offers/gmj_check_offer_liveness.py``
computes the documented liveness verdict from caller-supplied signals only, and
that it is advisory-only (always exits 0 on a successful run).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "offers" / "gmj_check_offer_liveness.py"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
    )


def test_live_status_reports_live_true() -> None:
    result = _cli("--http-status", "200")
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)
    assert verdict["live"] is True
    assert verdict["reasons"] == []


def test_dead_status_reports_live_false() -> None:
    result = _cli("--http-status", "404")
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)
    assert verdict["live"] is False
    assert any(r.startswith("http_status_404") for r in verdict["reasons"])


def test_missing_status_reports_unreachable() -> None:
    result = _cli()
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)
    assert verdict["live"] is False
    assert "unreachable" in verdict["reasons"]


def test_stale_by_age_overrides_live_status() -> None:
    ninety_one_days_ago = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat().replace(
        "+00:00", "Z"
    )
    result = _cli(
        "--http-status", "200", "--discovered-at", ninety_one_days_ago, "--max-age-days", "90"
    )
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)
    assert verdict["live"] is False
    assert "stale_by_age" in verdict["reasons"]


def test_age_check_skipped_without_max_age_days() -> None:
    ancient = "2000-01-01T00:00:00Z"
    result = _cli("--http-status", "200", "--discovered-at", ancient)
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout)
    assert verdict["live"] is True


def test_advisory_contract_always_exits_zero() -> None:
    for args in (
        ("--http-status", "200"),
        ("--http-status", "404"),
        (),
        ("--http-status", "200", "--discovered-at", "2000-01-01T00:00:00Z", "--max-age-days", "1"),
    ):
        result = _cli(*args)
        assert result.returncode == 0, f"args={args} stderr={result.stderr}"


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
