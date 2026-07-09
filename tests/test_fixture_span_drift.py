#!/usr/bin/env python3
"""Fixture-drift guard for Gate A's Wave-0 truth fixtures (Plan 41-01).

PIPE-06 investigation conclusion: no viable deterministic wrong-span detector
found. ``gmj_yaml_path.resolve_path`` is a structural-only walker (dict-key/
list-index resolution via a strict grammar, no text-similarity signal by
design — see its own docstring). Building a second, separate heuristic (e.g.
proper-noun/company-name overlap between ``claim.text`` and the resolved
span) to catch non-numeric wrong-span citations was considered per
``gmj-truth-rubric``'s R1 vocabulary-swap / R2 scope-inflation boundary, but
R1 explicitly sanctions same-fact rewording with no textual overlap
requirement (e.g. "Backend engineer" from "Sample Backend Engineer" swaps the
qualifier entirely) and R3's own worked example legitimizes word-fraction
restatements that share no digit token with the span. Any keyword/overlap
heuristic strict enough to catch a mis-citation would also flag these
legitimate, rubric-sanctioned reframes as false positives — and a false
Gate-A block on a truthful claim is judged worse than the current gap (see
this plan's threat register, T-41-02, disposition "accept"). Documented
no-go: no code shipped for a non-numeric wrong-span detector.

This file instead ships the concrete, always-valuable half of PIPE-06's
scope: a standing regression guard that makes ANY future ``candidate.yaml``
edit which silently invalidates a fixture's ``source_span`` (reordering,
inserting, or removing ``key_achievements``/``professional_experience``
entries) fail loudly and immediately, rather than surfacing later as a
mysterious Gate-A regression in the real test suite. It reuses (never
re-declares) the exact resolver and numeric-token regex ``gmj_check_truth.py``
uses in production, so this guard tracks the real gate byte-for-byte.

Runnable as a plain assertion script (no pytest), matching the repo
convention of ``python3 tests/test_*.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CANDIDATE = REPO_ROOT / "config" / "candidate.yaml"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from gmj_yaml_path import resolve_path  # noqa: E402  the single-owner span resolver
from gmj_check_truth import NUMERIC_TOKEN  # noqa: E402  reuse, never re-declare the regex

REAL_FIXTURES = [
    FIXTURES / "artifacts" / "quantified.real.draft.json",
    FIXTURES / "cover_letter.toned.draft.json",
    FIXTURES / "interview_prep.rich.draft.json",
]
INVENTED_FIXTURE = FIXTURES / "artifacts" / "quantified.invented.draft.json"

# Spans that are not achievement-array entries (e.g. "summary", "position")
# carry no per-index drift risk from a candidate.yaml reordering and are out
# of scope for this guard, per the plan's own Test 1 spec.
ACHIEVEMENT_SPAN_PREFIXES = ("professional_experience[", "key_achievements[")


def _load_claims(fixture_path: Path) -> list[dict]:
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    return doc["content"]["claims"]


def _load_candidate() -> dict:
    candidate = yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))
    assert isinstance(candidate, dict), "candidate.yaml must parse to a mapping"
    return candidate


def test_all_real_fixture_spans_resolve_and_contain_claim_digits() -> None:
    """Every achievement-array span in the three GOOD fixtures must still resolve
    and every numeric token in its claim text must still be a substring of the
    resolved span — the exact ``_numeric_invention`` check gmj_check_truth.py
    runs in production, executed here pre-emptively as a standing guard.
    """
    candidate = _load_candidate()
    checked = 0
    for fixture_path in REAL_FIXTURES:
        for claim in _load_claims(fixture_path):
            span = claim.get("source_span", "")
            if not span.startswith(ACHIEVEMENT_SPAN_PREFIXES):
                continue
            try:
                resolved = resolve_path(candidate, span)
            except (KeyError, IndexError, TypeError) as exc:
                raise AssertionError(
                    f"{fixture_path.name}: source_span {span!r} no longer resolves "
                    f"against candidate.yaml ({exc}) — candidate.yaml drifted out from "
                    "under this fixture"
                ) from exc
            resolved_str = str(resolved)
            text = claim.get("text", "")
            for token in NUMERIC_TOKEN.findall(text):
                core = token.rstrip("%")
                if core and core not in resolved_str:
                    raise AssertionError(
                        f"{fixture_path.name}: claim {claim['text']!r} cites digit "
                        f"{token!r} which is no longer present in resolved span "
                        f"{span!r} ({resolved_str!r}) — candidate.yaml drifted"
                    )
            checked += 1
    assert checked > 0, "expected at least one achievement-array span to check"


def test_invented_fixture_span_resolves_but_lacks_digit() -> None:
    """Pin the negative fixture's own correctness independent of the gate script:
    claims[1].source_span must resolve (in-range) but must NOT contain "40" —
    the exact contrast that makes the fixture assert numeric_invention rather
    than unresolved_span.
    """
    candidate = _load_candidate()
    claims = _load_claims(INVENTED_FIXTURE)
    claim = claims[1]
    span = claim["source_span"]
    assert span == "professional_experience[1].achievements[1]", (
        f"expected the pinned invented-number span, got {span!r} — update this test "
        "if the fixture was intentionally retargeted"
    )
    resolved = resolve_path(candidate, span)  # must not raise (in-range)
    resolved_str = str(resolved)
    assert "40" not in resolved_str, (
        f"the invented-number negative fixture's span {span!r} now contains '40' "
        f"({resolved_str!r}) — a candidate.yaml edit coincidentally introduced the "
        "digit into this achievement, invalidating the negative test case"
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
