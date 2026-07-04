#!/usr/bin/env python3
"""Doc-lint for Phase 14 artifact-depth guidance (ARTIFACT-01/02/03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_artifact_depth_docs.py``. This is a DOC-LINT: it loads the composer
agent and the two rubric skills as TEXT and asserts the load-bearing depth-guidance clauses
are present, each behind a specific sentinel so a deleted clause fails loudly. It is NOT an
LLM green-gate — it never runs the composer or judges richness quality (that is deferred to
Phase 15). It only proves the guidance *states* the invariants:

- gmj-artifact-composer.md names the four interview-prep sections
  (``likely_questions`` / ``star_stories`` / ``talking_points`` / ``questions_to_ask``),
- the cover-letter tone hint is a hub-passed PARAM and the composer must NOT read the
  preferences file (COMPOSE-01 two-input DATA contract),
- gmj-artifact-composer.md carries quantified span-cite framing guidance,
- truth-rubric has the new quantified worked example (references ``professional_experience``),
- fit-rubric states quantified framing lifts Gate C (``advisory``), not Gate B,
- the removed pre-migration expertise key is ABSENT from the composer examples
  (negative sentinel).

Discipline: every assertion carries a message naming the missing sentinel, so a removed
clause fails with a readable reason (not a bare AssertionError).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSER = REPO_ROOT / ".claude" / "agents" / "gmj-artifact-composer.md"
TRUTH_RUBRIC = REPO_ROOT / ".claude" / "skills" / "truth-rubric" / "SKILL.md"
FIT_RUBRIC = REPO_ROOT / ".claude" / "skills" / "fit-rubric" / "SKILL.md"

# Pre-migration flat-schema key that must never re-enter the composer examples.
PRE_MIGRATION_KEY = "technical" + "_expertise"  # split to keep the token out of grep noise


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"file not found: {path}")
    return path.read_text(encoding="utf-8")


def test_composer_names_four_sections() -> None:
    t = _read(COMPOSER)
    for section in ("likely_questions", "star_stories", "talking_points", "questions_to_ask"):
        assert section in t, (
            f"gmj-artifact-composer.md must name the interview-prep section {section!r} (ARTIFACT-01)"
        )


def test_composer_star_stories_single_span_claims() -> None:
    t = _read(COMPOSER)
    assert "MULTIPLE claims" in t, (
        "composer must state STAR stories are emitted as MULTIPLE claims, each with its own span "
        "(no cross-entry merge, truth-rubric R4)"
    )


def test_composer_tone_hint_is_hub_param() -> None:
    t = _read(COMPOSER)
    assert "hub-passed" in t, (
        "composer must state the cover-letter tone hint arrives as a hub-passed param (ARTIFACT-02)"
    )
    assert "param, never a file" in t, (
        "composer must state the tone hint is a param, never a file (COMPOSE-01)"
    )


def test_composer_forbids_reading_preferences_file() -> None:
    t = _read(COMPOSER)
    assert "config/preferences.yaml" in t, (
        "composer must reference config/preferences.yaml to forbid reading it (COMPOSE-01)"
    )
    assert "must **NOT** read" in t or "must NOT read" in t, (
        "composer must state it must NOT read the preferences file (two-input DATA contract)"
    )


def test_composer_quantified_span_cite() -> None:
    t = _read(COMPOSER)
    assert "Never invent, estimate,\n  or round-up" in t or "Never invent, estimate, or round-up" in t, (
        "composer must forbid inventing/estimating/rounding-up a metric (ARTIFACT-03)"
    )
    assert "source_span" in t, "composer must retain source_span span-cite guidance (ARTIFACT-03)"


def test_truth_rubric_has_quantified_example() -> None:
    t = _read(TRUTH_RUBRIC)
    assert "professional_experience" in t, (
        "truth-rubric R3 must carry the new quantified worked example on a professional_experience span"
    )
    assert "numeric_invention" in t, (
        "truth-rubric quantified example must name the numeric_invention FAIL"
    )


def test_fit_rubric_quantified_lifts_gate_c_advisory() -> None:
    t = _read(FIT_RUBRIC)
    assert "advisory" in t.lower(), "fit-rubric must state Gate C quantified_impact is advisory"
    assert "quantified" in t.lower(), "fit-rubric must discuss quantified framing"
    assert "quantified_impact" in t, (
        "fit-rubric must state quantified framing lifts the Gate C quantified_impact dimension, not Gate B"
    )


def test_no_pre_migration_key_in_composer() -> None:
    t = _read(COMPOSER)
    # Negative sentinel: the removed pre-migration expertise key must be absent.
    assert PRE_MIGRATION_KEY not in t, (
        f"pre-migration schema key {PRE_MIGRATION_KEY!r} must NOT appear in gmj-artifact-composer.md examples "
        "(use nested-schema spans only, T-14-09)"
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
