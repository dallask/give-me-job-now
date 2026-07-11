#!/usr/bin/env python3
"""Plain-python3 regression tests for the preferences.schema.json `cv:` block (TMPL-01).

Proves both the happy path and the fail-closed path for the self-contained `$defs.cv`
entry added to schemas/preferences.schema.json: the REAL config/preferences.yaml
validates clean, a well-formed synthetic `cv:` block validates clean, an unknown
`mode` enum value is rejected, and an unknown `cv:` sub-key is rejected
(additionalProperties:false enforced, closing Pitfall 1's regression risk per
RESEARCH.md's "Wave 0 Gaps" list). No pytest — run with
``python3 tests/test_preferences_cv_schema.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "schemas" / "preferences.schema.json"
PREFERENCES = REPO_ROOT / "config" / "preferences.yaml"

# scripts/-tree import idiom (matches test_gmj_batch.py's sys.path.insert convention).
sys.path.insert(0, str(REPO_ROOT / "scripts" / "preferences"))
from gmj_validate_preferences import shape_errors  # noqa: E402


def test_real_preferences_yaml_passes_shape_validation() -> None:
    prefs = yaml.safe_load(PREFERENCES.read_text(encoding="utf-8"))
    errors = shape_errors(prefs, SCHEMA)
    assert errors == [], (
        f"expected zero shape errors for the real config/preferences.yaml, got: {errors}"
    )


def test_cv_block_validates_with_real_shape() -> None:
    sample = {
        "cv": {
            "templates": ["baxter.html", "default.html"],
            "default": "baxter.html",
            "mode": "default",
        }
    }
    errors = shape_errors(sample, SCHEMA)
    assert errors == [], (
        f"expected zero shape errors for a well-formed cv: block, got: {errors}"
    )


def test_cv_mode_enum_rejects_unknown_value() -> None:
    sample = {"cv": {"mode": "bogus"}}
    errors = shape_errors(sample, SCHEMA)
    assert errors, "expected at least one shape error for cv.mode: 'bogus' (enum violation)"
    assert any("cv" in err or "mode" in err for err in errors), (
        f"expected an error mentioning 'cv' or 'mode', got: {errors}"
    )


def test_cv_block_rejects_unknown_key() -> None:
    sample = {"cv": {"bogus_key": 1}}
    errors = shape_errors(sample, SCHEMA)
    assert errors, (
        "expected at least one shape error for an unknown cv: sub-key "
        "(additionalProperties:false on the self-contained $defs.cv object)"
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
