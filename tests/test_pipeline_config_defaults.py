#!/usr/bin/env python3
"""Regression guard for config/pipeline.config.yaml safe defaults (SAFE-01, Plan 26-01).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_pipeline_config_defaults.py``. Mirrors the idiom of
``tests/test_gmj_dashboard_actions.py``: module-level ``REPO_ROOT``, the ``sys.path.insert``
import seam, a ``main()`` that runs every ``test_*`` and returns 1 on any failure, and the
never-a-traceback discipline (a stray crash can never masquerade as a pass).

This file exists to make the FIND-08 accidental commit — which flipped the repo-default config
to ``execution_mode: autonomous`` / ``retry_cap: 4`` — un-revertible-by-accident: if either
value drifts back to the unsafe default, this guard exits 1. It reads the two knobs via the same
``actions.read_config_values`` seam the ``--manage`` action layer and the existing mutator tests
use, so the guard and the runtime read the file identically. The file lands in the
``tests/test_*.py`` phase-gate glob automatically (no ledger registration required).
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = REPO_ROOT / "scripts" / "dashboard"
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"

sys.path.insert(0, str(DASH_DIR))
import gmj_dashboard_actions as actions  # noqa: E402


# ── SAFE-01: the repo-default config must read the safe defaults ───────────────────────────────────

def test_repo_default_is_safe_default() -> None:
    mode, cap = actions.read_config_values(DEFAULT_CONFIG)
    assert mode == "human_in_the_loop", (
        f"repo-default execution_mode must be human_in_the_loop (FIND-08 drift returned?), got {mode!r}"
    )
    assert cap == 2, f"repo-default retry_cap must be 2 (FIND-08 drift returned?), got {cap!r}"


def test_comment_and_value_agree() -> None:
    text = DEFAULT_CONFIG.read_text(encoding="utf-8")
    assert "# FREEZE CONTRACT" in text, "the FREEZE-CONTRACT comment block must survive"
    assert "Default human_in_the_loop" in text, (
        "the comment must document the human_in_the_loop safe default so comment/value agree"
    )
    assert "execution_mode: human_in_the_loop" in text, "the execution_mode value line must read the safe default"
    assert "retry_cap: 2" in text, "the retry_cap value line must read the safe default"


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
