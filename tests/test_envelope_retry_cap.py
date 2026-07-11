#!/usr/bin/env python3
"""Tests for scripts/pipeline/gmj_check_envelope_retry.py (GUIDE-01 gap closure).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_envelope_retry_cap.py``. Proves the bounded, deterministic
envelope-violation retry counter/cap script's contract, structurally separate from the Gate A/B
content retry cap (``gmj_check_cap.py`` / ``gmj_record_retry.py``):

- a fresh dispatch-id with no prior increment reports ``first_attempt`` / exit 0,
- one ``--increment`` call followed by a check reports ``retry_exhausted`` / exit 1 (bounded to
  exactly one retry),
- two DIFFERENT dispatch-ids in the SAME state file are tracked independently,
- a malformed (non-JSON, or JSON-but-not-a-dict) state file exits 1 with a clear stderr message,
  never a traceback.

Discipline (mirrors ``tests/test_merge_shortlists.py``): assert the exit code AND the specific
stdout/stderr sentinel so an unrelated crash's nonzero exit never masquerades as a pass.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_envelope_retry.py"


def _cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_fresh_dispatch_id_is_first_attempt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "envelope_retries.json"
        result = _cli(["--state", str(state), "--dispatch-id", "gmj-offer-scout"])
        assert result.returncode == 0, f"fresh dispatch-id must exit 0: {result.stderr}"
        assert result.stdout.strip() == "first_attempt", (
            f"fresh dispatch-id must report 'first_attempt': {result.stdout!r}"
        )


def test_one_retry_then_exhausted() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "envelope_retries.json"
        dispatch_id = "gmj-artifact-composer-cv"

        inc = _cli(["--state", str(state), "--dispatch-id", dispatch_id, "--increment"])
        assert inc.returncode == 0, f"--increment must always exit 0: {inc.stderr}"
        assert inc.stdout.strip() == "1", f"first increment must print new count 1: {inc.stdout!r}"

        check = _cli(["--state", str(state), "--dispatch-id", dispatch_id])
        assert check.returncode == 1, (
            f"count==1 (one retry already recorded) must exit 1 (hard-stop): {check.stdout}"
        )
        assert check.stdout.strip() == "retry_exhausted", (
            f"count==1 must report 'retry_exhausted': {check.stdout!r}"
        )


def test_independent_dispatch_ids_tracked_separately() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "envelope_retries.json"
        a = "gmj-truth-verifier"
        b = "gmj-fit-evaluator"

        inc_a = _cli(["--state", str(state), "--dispatch-id", a, "--increment"])
        assert inc_a.returncode == 0, f"increment of {a} must exit 0: {inc_a.stderr}"

        # b has NOT been incremented -- must still report first_attempt / exit 0.
        check_b = _cli(["--state", str(state), "--dispatch-id", b])
        assert check_b.returncode == 0, (
            f"incrementing '{a}' must not affect '{b}': {check_b.stdout}"
        )
        assert check_b.stdout.strip() == "first_attempt", (
            f"'{b}' must remain first_attempt after only '{a}' was incremented: {check_b.stdout!r}"
        )

        # a IS now exhausted.
        check_a = _cli(["--state", str(state), "--dispatch-id", a])
        assert check_a.returncode == 1, f"'{a}' must now be retry_exhausted: {check_a.stdout}"
        assert check_a.stdout.strip() == "retry_exhausted", (
            f"'{a}' must report retry_exhausted: {check_a.stdout!r}"
        )


def test_malformed_state_file_fails_loud_no_traceback() -> None:
    # Non-JSON content.
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "envelope_retries.json"
        state.write_text("not json at all {{{", encoding="utf-8")
        result = _cli(["--state", str(state), "--dispatch-id", "gmj-cv-generator"])
        assert result.returncode == 1, f"non-JSON state must exit 1: {result.stdout}"
        assert "Invalid state JSON" in result.stderr, (
            f"stderr must clearly name the invalid JSON, not a traceback: {result.stderr}"
        )
        assert "Traceback" not in result.stderr, (
            f"error must not surface a raw traceback: {result.stderr}"
        )

    # Valid JSON but not a dict (a bare list).
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "envelope_retries.json"
        state.write_text("[1, 2, 3]", encoding="utf-8")
        result = _cli(["--state", str(state), "--dispatch-id", "gmj-cv-generator"])
        assert result.returncode == 1, f"non-dict JSON state must exit 1: {result.stdout}"
        assert "must contain a JSON object" in result.stderr, (
            f"stderr must clearly name the non-dict shape, not a traceback: {result.stderr}"
        )
        assert "Traceback" not in result.stderr, (
            f"error must not surface a raw traceback: {result.stderr}"
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
