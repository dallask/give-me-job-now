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


def _bare_agent_result_v1_envelope() -> dict:
    """A minimal, schema-conforming bare agent_result_v1 envelope with NO
    `kind` field — the exact shape every collective spoke emits per
    .claude/skills/gmj-agent-output-contract/SKILL.md's canonical schema."""
    return {
        "schema": "agent_result_v1",
        "schema_version": "1.0",
        "agent": "gmj-truth-verifier",
        "pipeline_run_id": "run-2026-07-12-001",
        "status": "success",
        "artifacts": [
            {"type": "file", "path": "/abs/output/analysis/gate-a-verdict.json"}
        ],
        "acceptance_criteria_met": ["crit-truth-verified"],
        "acceptance_criteria_failed": [],
        "next_action": "none",
        "handoff_target": None,
        "notes": "All claims re-grounded against config/candidate.yaml; 0 fabrications found.",
    }


def test_bare_agent_result_v1_envelope_no_kind_field_validates() -> None:
    # Reproduces the exact "unknown kind None" BLOCK scenario from
    # validate-envelope.log (04-UAT.md gap-closure test 1), now fixed.
    envelope = _bare_agent_result_v1_envelope()
    assert "kind" not in envelope
    payload = json.dumps(envelope)
    result = _run(["--stdin"], stdin=payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK: agent_result_v1", result.stdout


def test_explicit_kind_agent_result_v1_field_validates() -> None:
    # Reproduces the second observed BLOCK variant: an envelope that adds a
    # redundant "kind": "agent_result_v1" field (unknown kind 'agent_result_v1').
    envelope = _bare_agent_result_v1_envelope()
    envelope["kind"] = "agent_result_v1"
    payload = json.dumps(envelope)
    result = _run(["--stdin"], stdin=payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK: agent_result_v1", result.stdout


def test_bare_agent_result_v1_still_rejects_genuine_violation() -> None:
    # A bare envelope missing a required field (status) must still fail loud
    # with a structured <field/path>: <message> stderr line — the fix does
    # not loosen genuine-violation detection.
    envelope = _bare_agent_result_v1_envelope()
    del envelope["status"]
    payload = json.dumps(envelope)
    result = _run(["--stdin"], stdin=payload)
    assert result.returncode != 0
    assert ": " in result.stderr, result.stderr
    assert "status" in result.stderr, result.stderr


def test_three_wrapper_kinds_still_resolve_unchanged() -> None:
    # resolve_kind() itself still returns the correct wrapper kind for an
    # envelope that DOES carry one of the 3 wrapper `kind` values — proving
    # the new bare-envelope branch is additive, never a replacement.
    for kind in KINDS:
        envelope = json.loads(
            (SAMPLES / f"{kind}.valid.json").read_text(encoding="utf-8")
        )
        assert envelope.get("kind") == kind
        resolved = validate_envelope.resolve_kind(None, envelope)
        assert resolved == kind, (kind, resolved)


def test_agent_result_v1_sample_fixture_validates_via_file_mode() -> None:
    # Proves the fixture-file fixture works through --file mode too (Task 1's
    # tests above already covered --stdin), matching this file's existing
    # dual-entry-point test discipline (test_stdin_mode_valid alongside
    # test_valid_fixtures_exit_zero's --file coverage for the 3 wrapper kinds).
    result = _run(["--file", str(SAMPLES / "agent_result_v1.valid.json")])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK: agent_result_v1", result.stdout


def _artifact_draft_with_notes(notes_raw_fragment: str) -> str:
    """Return a raw artifact_draft envelope JSON string with `notes` set to a raw
    (already-JSON-quoted) fragment, so the caller controls exactly what backslash
    sequence lands inside the string literal — reproducing the real failure class
    from validate-envelope.log (a bare backslash inside the `notes` free-text field
    breaking json.loads() before schema validation ever runs)."""
    template = (SAMPLES / "artifact_draft.valid.json").read_text(encoding="utf-8")
    envelope = json.loads(template)
    envelope["notes"] = "placeholder"
    raw = json.dumps(envelope)
    # Splice the raw fragment in place of the placeholder's JSON string body,
    # so the bare backslash is not escaped by json.dumps first.
    return raw.replace('"placeholder"', f'"{notes_raw_fragment}"')


def test_repair_pass_fixes_bare_backslash_in_notes() -> None:
    # Reproduces the exact "Invalid \escape" class from validate-envelope.log: a
    # Windows-style path fragment in `notes` with an unescaped backslash before a
    # non-escape character (\U is not a legal JSON escape).
    raw = _artifact_draft_with_notes(r"See output at C:\Users\report.pdf")
    # Sanity: this raw string is genuinely invalid JSON before repair.
    try:
        json.loads(raw)
        raise AssertionError("fixture must be invalid JSON before repair")
    except json.JSONDecodeError:
        pass
    result = _run(["--stdin", "--kind", "artifact_draft"], stdin=raw)
    assert result.returncode == 0, result.stderr


def test_repair_pass_does_not_mask_unrecoverable_syntax_error() -> None:
    # A truncated/missing closing brace is unrelated to backslash escaping and
    # must NOT be silently swallowed by the repair pass.
    template = (SAMPLES / "artifact_draft.valid.json").read_text(encoding="utf-8")
    truncated = template.rstrip()[:-1]  # drop the final closing brace
    result = _run(["--stdin", "--kind", "artifact_draft"], stdin=truncated)
    assert result.returncode != 0
    assert "Invalid JSON:" in result.stderr, result.stderr


def test_repair_pass_is_noop_on_already_valid_envelopes() -> None:
    for kind in KINDS:
        payload = (SAMPLES / f"{kind}.valid.json").read_text(encoding="utf-8")
        result = _run(["--stdin", "--kind", kind], stdin=payload)
        assert result.returncode == 0, (kind, result.stderr)


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
