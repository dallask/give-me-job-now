#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_pipeline_run.py (ARTF-03).

Proves the single-offer `--artifact-types` narrowing flag is validated against the exact 3-item
enum (cv, cover_letter, interview_prep) BEFORE any state write or Task dispatch, naming every
invalid token individually alongside the valid set, and that exactly one distinct, safe-charset
run_id is derived per requested artifact type (`<run_id>-cv`/`-cl`/`-ip`) — never fewer or more
than requested. No pytest — run with ``python3 tests/test_gmj_pipeline_run.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_pipeline_run.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_default_derives_all_three_in_canonical_order() -> None:
    result = _run("--run-id", "iso-123")
    assert result.returncode == 0, f"default (no --artifact-types) must succeed: {result.stderr}"
    lines = result.stdout.strip("\n").split("\n")
    assert lines == ["cv=iso-123-cv", "cover_letter=iso-123-cl", "interview_prep=iso-123-ip"], (
        f"unexpected stdout: {result.stdout!r}"
    )


def test_narrowed_subset_excludes_unrequested_type() -> None:
    result = _run("--run-id", "iso-123", "--artifact-types", "cv,cover_letter")
    assert result.returncode == 0, f"narrowed selection must succeed: {result.stderr}"
    lines = result.stdout.strip("\n").split("\n")
    assert lines == ["cv=iso-123-cv", "cover_letter=iso-123-cl"], f"unexpected stdout: {result.stdout!r}"
    assert "interview_prep" not in result.stdout, "unrequested type must be absent"


def test_invalid_type_hard_fails_before_any_output() -> None:
    result = _run("--run-id", "demo", "--artifact-types", "cv,typo")
    assert result.returncode == 1, "an invalid type token must hard-fail"
    assert result.stdout == "", f"stdout must be empty on failure: {result.stdout!r}"
    assert "typo" in result.stderr, f"stderr must name the invalid token: {result.stderr!r}"
    for valid_key in ("cv", "cover_letter", "interview_prep"):
        assert valid_key in result.stderr, f"stderr must name the valid set: {result.stderr!r}"
    assert "Traceback" not in result.stderr, result.stderr


def test_empty_artifact_types_hard_fails() -> None:
    result = _run("--run-id", "demo", "--artifact-types", " , ,")
    assert result.returncode == 1, "an all-comma/whitespace value must resolve to zero types"
    assert result.stdout == "", f"stdout must be empty on failure: {result.stdout!r}"
    assert "no types" in result.stderr.lower(), f"stderr must state no types resolved: {result.stderr!r}"
    assert "Traceback" not in result.stderr, result.stderr


def test_unsafe_run_id_rejected() -> None:
    result = _run("--run-id", "../evil")
    assert result.returncode == 1, "an unsafe run_id must be rejected"
    assert result.stdout == "", f"stdout must be empty on failure: {result.stdout!r}"
    assert "Traceback" not in result.stderr, result.stderr


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
