#!/usr/bin/env python3
"""Tests for scripts/pipeline/gmj_pipeline_paths.py (HON-01, Plan 27-01).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_pipeline_dir.py``. Mirrors the idiom of
``tests/test_gmj_dashboard_actions.py``: module-level ``REPO_ROOT``, the
``sys.path.insert`` import seam, a ``main()`` that runs every ``test_*`` and returns 1 on
any failure, and the never-a-traceback discipline (a stray crash can never masquerade as a
pass).

Requirement coverage:
- HON-01 ``test_env_wins_over_default`` / ``test_explicit_wins_over_env`` /
         ``test_fallback_is_dot_pipeline`` — asserts the single-sourced resolve order
         explicit > GMJ_PIPELINE_DIR env > ".pipeline".

Each test mutates ``os.environ`` inside a try/finally that restores it, so the global env
is never left dirty for a following test.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_pipeline_paths as p  # noqa: E402


def test_env_wins_over_default() -> None:
    os.environ["GMJ_PIPELINE_DIR"] = "/tmp/board-x"
    try:
        assert p.resolve_pipeline_dir() == "/tmp/board-x"
    finally:
        del os.environ["GMJ_PIPELINE_DIR"]


def test_explicit_wins_over_env() -> None:
    os.environ["GMJ_PIPELINE_DIR"] = "/tmp/board-x"
    try:
        assert p.resolve_pipeline_dir("/tmp/explicit") == "/tmp/explicit"
    finally:
        del os.environ["GMJ_PIPELINE_DIR"]


def test_fallback_is_dot_pipeline() -> None:
    os.environ.pop("GMJ_PIPELINE_DIR", None)
    assert p.resolve_pipeline_dir() == ".pipeline"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                test()
            assert "Traceback" not in buf.getvalue(), f"{test.__name__} leaked a traceback: {buf.getvalue()}"
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
