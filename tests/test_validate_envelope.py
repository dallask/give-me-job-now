#!/usr/bin/env python3
"""Behavior tests for the executed envelope validator (ARCH-04, GUARD-01).

Runnable as a plain assertion script (no pytest dependency). Proves that:
- each schemas/samples/<kind>.valid.json validates clean and exits 0,
- each schemas/samples/<kind>.invalid.json is rejected with a structured
  field-path error on stderr and a non-zero exit,
- --stdin mode works (Plan 05's SubagentStop hook depends on it),
- an unknown/unsupported --kind is rejected (path-traversal mitigation),
- the cross-file $ref resolves via referencing.Registry with no
  DeprecationWarning (run this file under `-W error::DeprecationWarning`
  to turn the deprecated RefResolver path into a hard failure).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
SAMPLES = SCHEMA_DIR / "samples"
VALIDATOR = REPO_ROOT / "scripts" / "contracts" / "gmj_validate_envelope.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
import gmj_validate_envelope as validate_envelope  # noqa: E402

KINDS = ("offer_spec", "artifact_draft", "gate_result")


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_valid_fixtures_exit_zero() -> None:
    for kind in KINDS:
        result = _run(["--file", str(SAMPLES / f"{kind}.valid.json")])
        assert result.returncode == 0, (kind, result.returncode, result.stderr)


def test_gate_bc_samples_validate() -> None:
    # Phase 06 Gate B/C content variants share the gate_result envelope but are
    # not named <kind>.valid.json, so assert them explicitly.
    for name in ("gate_result.gateb.valid.json", "gate_result.gatec.valid.json"):
        result = _run(["--file", str(SAMPLES / name)])
        assert result.returncode == 0, (name, result.returncode, result.stderr)


def test_invalid_fixtures_exit_nonzero_with_field_path() -> None:
    for kind in KINDS:
        result = _run(["--file", str(SAMPLES / f"{kind}.invalid.json")])
        assert result.returncode != 0, (kind, result.returncode)
        # Structured "<path>: <message>" — not a bare boolean.
        assert ": " in result.stderr, (kind, result.stderr)


def test_invalid_offer_spec_names_status_path() -> None:
    result = _run(["--file", str(SAMPLES / "offer_spec.invalid.json")])
    assert result.returncode != 0
    # The malformed enum value is at the `status` field.
    assert "status" in result.stderr, result.stderr


def test_stdin_mode_valid() -> None:
    payload = (SAMPLES / "offer_spec.valid.json").read_text(encoding="utf-8")
    result = _run(["--stdin"], stdin=payload)
    assert result.returncode == 0, result.stderr


def test_stdin_mode_invalid() -> None:
    payload = (SAMPLES / "gate_result.invalid.json").read_text(encoding="utf-8")
    result = _run(["--stdin"], stdin=payload)
    assert result.returncode != 0
    assert ": " in result.stderr, result.stderr


def test_unknown_kind_rejected() -> None:
    result = _run(
        ["--file", str(SAMPLES / "offer_spec.valid.json"), "--kind", "../etc/passwd"]
    )
    assert result.returncode != 0
    assert result.stderr.strip() != ""


def test_kind_override_mismatch_fails() -> None:
    # A real offer_spec envelope validated as artifact_draft must fail the
    # `kind` const, proving --kind actually drives schema selection.
    result = _run(
        ["--file", str(SAMPLES / "offer_spec.valid.json"), "--kind", "artifact_draft"]
    )
    assert result.returncode != 0
    assert "kind" in result.stderr, result.stderr


def test_validate_helper_clean_for_valid() -> None:
    # In-process call — under -W error::DeprecationWarning this asserts the
    # Registry path (never RefResolver) is used for cross-file $ref.
    envelope = json.loads((SAMPLES / "offer_spec.valid.json").read_text("utf-8"))
    errors = validate_envelope.validate(envelope, "offer_spec", SCHEMA_DIR)
    assert errors == [], errors


def test_validate_helper_returns_field_path_errors() -> None:
    envelope = json.loads((SAMPLES / "offer_spec.invalid.json").read_text("utf-8"))
    errors = validate_envelope.validate(envelope, "offer_spec", SCHEMA_DIR)
    assert errors, "expected at least one error"
    assert any(e.startswith("status:") for e in errors), errors


def test_resolve_kind_rejects_unknown() -> None:
    try:
        validate_envelope.resolve_kind(None, {"kind": "evil_kind"})
    except ValueError:
        return
    raise AssertionError("resolve_kind should reject an unknown kind")


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
