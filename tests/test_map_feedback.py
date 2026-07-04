#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_map_feedback.py (GUARD-04).

Proves the gate_result -> gate_feedback projection emits EXACTLY the frozen
tests/fixtures/gate_feedback.sample.json field names — the PLURAL claims_index,
source_span, and a deterministic reason sentence for Gate A; a plain string array
for Gate B — with NO extra keys, no gate stdout blob, no transcript, no prose field
other than the per-item reason / must-have strings (Pitfall 3, threat T-07-04). The
Gate A output is validated against BOTH the fixture's key set AND the derived
schemas/gate_feedback.schema.json via a LOCAL registry (never a URL fetch, T-07-06).
No pytest — run with ``python3 tests/test_map_feedback.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_map_feedback.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_feedback.sample.json"
SCHEMA_DIR = REPO_ROOT / "schemas"
GATE_FEEDBACK_SCHEMA = SCHEMA_DIR / "gate_feedback.schema.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from gmj_validate_envelope import build_registry  # noqa: E402  local-only schema registry

FEEDBACK_KEYS = {"gate", "missing_must_haves", "fabricated_claims"}

# Deterministic RULE_REASON sentences expected in the projection (mirror of the
# gmj_map_feedback.py lookup — asserted here so a drift to model prose fails the test).
EXPECTED_REASON = {
    "unresolved_span": "source_span does not resolve in candidate.yaml",
    "numeric_invention": "numeric value absent from the cited candidate.yaml span",
    "scope_inflation": "claim inflates the scope of the cited candidate.yaml span",
    "cross_entry_merge": "claim merges facts from multiple candidate.yaml entries",
}

# Gate A gate_result envelope (matches gate_result.schema.json#/$defs/gate_a_content).
GATE_A_INPUT = {
    "schema_version": "1.0",
    "kind": "gate_result",
    "content": {
        "gate": "A",
        "verdict": "fail",
        "offending_claims": [
            {
                "claim_index": 3,
                "rule_violated": "unresolved_span",
                "offending_span": "professional_experience[0].achievements[9]",
            },
            {
                "claim_index": 7,
                "rule_violated": "scope_inflation",
                "offending_span": "certifications[2].credentials[0]",
            },
        ],
    },
}

# Gate B gate_result envelope (matches gate_result.schema.json#/$defs/gate_b_content).
GATE_B_INPUT = {
    "schema_version": "1.0",
    "kind": "gate_result",
    "content": {
        "gate": "B",
        "verdict": "fail",
        "coverage": {"covered_ids": [], "missing_ids": ["mh-0", "mh-1"], "score": 0.0},
        "why": {
            "coverage": "0/2",
            "missing_must_haves": [
                {"id": "mh-0", "text": "Django and Django REST Framework"},
                {"id": "mh-1", "text": "PostgreSQL query optimization"},
            ],
        },
    },
}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _project(envelope: dict) -> dict:
    """Write *envelope* to a tempfile, run gmj_map_feedback.py --file, parse stdout."""
    tmp = Path(tempfile.mkdtemp()) / "gate_result.json"
    tmp.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    result = _run("--file", str(tmp))
    assert result.returncode == 0, f"gmj_map_feedback.py failed: {result.stderr}"
    return json.loads(result.stdout)


def test_gate_a_exact_fixture_field_names() -> None:
    out = _project(GATE_A_INPUT)
    # EXACTLY the three fixture keys — no extra keys, no prose blob (Pitfall 3).
    assert set(out.keys()) == FEEDBACK_KEYS, f"unexpected keys: {set(out.keys())!r}"
    assert out["gate"] == "A"
    assert out["missing_must_haves"] == [], "Gate A must-haves must be empty"
    items = out["fabricated_claims"]
    assert len(items) == 2, f"expected 2 fabricated_claims, got {len(items)}"
    for item in items:
        # PLURAL claims_index + source_span + reason ONLY — the fixture item shape.
        assert set(item.keys()) == {"claims_index", "source_span", "reason"}, (
            f"fabricated_claim item has wrong keys: {set(item.keys())!r}"
        )
        assert "claim_index" not in item, "singular claim_index must be renamed (plural)"
        assert "offending_span" not in item, "offending_span must be renamed to source_span"
        assert "rule_violated" not in item, "rule_violated must be renamed to reason"
    # Rename values carried through faithfully.
    assert items[0]["claims_index"] == 3
    assert items[0]["source_span"] == "professional_experience[0].achievements[9]"
    assert items[1]["claims_index"] == 7
    assert items[1]["source_span"] == "certifications[2].credentials[0]"


def test_gate_a_deterministic_reason_sentences() -> None:
    out = _project(GATE_A_INPUT)
    reasons = [c["reason"] for c in out["fabricated_claims"]]
    assert reasons[0] == EXPECTED_REASON["unresolved_span"], reasons[0]
    assert reasons[1] == EXPECTED_REASON["scope_inflation"], reasons[1]


def test_gate_b_plain_string_array() -> None:
    out = _project(GATE_B_INPUT)
    assert set(out.keys()) == FEEDBACK_KEYS, f"unexpected keys: {set(out.keys())!r}"
    assert out["gate"] == "B"
    assert out["fabricated_claims"] == [], "Gate B fabricated_claims must be empty"
    mh = out["missing_must_haves"]
    # Plain string array of the .text values only — never {id, text} objects.
    assert mh == [
        "Django and Django REST Framework",
        "PostgreSQL query optimization",
    ], f"missing_must_haves not a plain .text string array: {mh!r}"
    assert all(isinstance(x, str) for x in mh), "missing_must_haves must be strings"


def test_gate_a_matches_fixture_key_set() -> None:
    out = _project(GATE_A_INPUT)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(out.keys()) == set(fixture.keys()), "top-level key set diverges from fixture"
    out_item_keys = set(out["fabricated_claims"][0].keys())
    fixture_item_keys = set(fixture["fabricated_claims"][0].keys())
    assert out_item_keys == fixture_item_keys, (
        f"fabricated_claim item keys {out_item_keys!r} != fixture {fixture_item_keys!r}"
    )


def test_output_validates_against_derived_schema() -> None:
    schema = json.loads(GATE_FEEDBACK_SCHEMA.read_text(encoding="utf-8"))
    registry = build_registry(SCHEMA_DIR)  # local registry, never a URL fetch (T-07-06)
    validator = Draft202012Validator(schema, registry=registry)
    for label, envelope in (("A", GATE_A_INPUT), ("B", GATE_B_INPUT)):
        out = _project(envelope)
        errors = sorted(validator.iter_errors(out), key=lambda e: list(e.path))
        assert not errors, f"Gate {label} output fails schema: {[e.message for e in errors]}"


def test_unsupported_gate_rejected() -> None:
    bad = {"schema_version": "1.0", "kind": "gate_result", "content": {"gate": "C"}}
    tmp = Path(tempfile.mkdtemp()) / "gate_c.json"
    tmp.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    result = _run("--file", str(tmp))
    assert result.returncode != 0, "an unsupported gate must exit non-zero"


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
