#!/usr/bin/env python3
"""Prove SEARCH-05's "zero Firecrawl calls when unset" branch-point contract (Plan 48-03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_offer_scout_firecrawl_opt_in.py``. Mirrors the no-pytest-dependency
convention already used by ``tests/test_sources_scope_guard.py`` and
``tests/test_validate_preferences.py``.

This is a pure STATIC-INSPECTION test suite over the committed config and agent-definition
source text — it never imports/invokes ``firecrawl``/``dotenv`` and never attempts a live or
mocked network call. RESEARCH.md Pitfall 1 explicitly warns that an API-behavior assertion
(e.g. "no exception was raised with an unset key") is NOT a valid proof of SEARCH-05, because
firecrawl-py's SDK silently falls back to a keyless free tier rather than refusing outright.
The only valid proof is that the CODE PATH is never reached by inspection of the committed
contract: the shipped default has ``search_provider`` unset, and ``gmj-offer-scout.md``
documents that an absent/non-firecrawl value keeps the original WebSearch/WebFetch call sites
textually unchanged.

Asserted invariants:
- the REAL committed ``config/preferences.yaml`` has no live ``search_provider`` key (Test 1),
- ``gmj-offer-scout.md`` documents the unset-key default path as the unchanged original
  WebSearch/WebFetch behavior (Test 2),
- every ``gmj_firecrawl_search.py`` reference in ``gmj-offer-scout.md`` sits within the
  opt-in ``search_provider`` conditional branch, never unconditionally (Test 3),
- Plan 03's schema edit didn't break the existing ``gmj_validate_preferences.py`` pre-write
  guard against the real committed preferences file (Test 4, regression guard).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PREFERENCES_YAML = REPO_ROOT / "config" / "preferences.yaml"
OFFER_SCOUT_MD = REPO_ROOT / ".claude" / "agents" / "gmj-offer-scout.md"
VALIDATOR = REPO_ROOT / "scripts" / "preferences" / "gmj_validate_preferences.py"

# Proximity window (lines) within which every gmj_firecrawl_search.py mention must find a
# search_provider mention — proves the script is never referenced unconditionally outside
# the opt-in branch (Test 3).
PROXIMITY_LINES = 8


def _preferences_data() -> dict:
    return yaml.safe_load(PREFERENCES_YAML.read_text(encoding="utf-8")) or {}


def _offer_scout_text() -> str:
    return OFFER_SCOUT_MD.read_text(encoding="utf-8")


def test_default_preferences_yaml_has_no_live_search_provider_key() -> None:
    data = _preferences_data()
    assert "search_provider" not in data or data.get("search_provider") is None, (
        "the REAL committed config/preferences.yaml must ship with search_provider genuinely "
        f"unset (default/inert state per SEARCH-05); found: {data.get('search_provider')!r}"
    )


def test_offer_scout_md_documents_unset_key_as_unchanged_default_path() -> None:
    text = _offer_scout_text()
    assert "search_provider" in text, (
        "gmj-offer-scout.md must document the search_provider branch point"
    )
    assert "WebSearch" in text and "WebFetch" in text, (
        "gmj-offer-scout.md must still reference the original WebSearch/WebFetch call sites"
    )
    # The branch paragraph must establish that absent/non-firecrawl keeps the ORIGINAL
    # WebSearch/WebFetch path unchanged — look for the paragraph containing both
    # "search_provider" and "absent" (or "unchanged") together with "WebSearch".
    paragraphs = re.split(r"\n\s*\n", text)
    branch_paragraphs = [
        p for p in paragraphs
        if "search_provider" in p and ("absent" in p or "unchanged" in p) and "WebSearch" in p
    ]
    assert branch_paragraphs, (
        "expected a paragraph documenting that an absent/non-firecrawl search_provider value "
        "keeps the WebSearch/WebFetch path unchanged (the default, SEARCH-05); none found"
    )


def test_firecrawl_script_never_referenced_outside_conditional_branch() -> None:
    lines = _offer_scout_text().splitlines()
    firecrawl_lines = [i for i, line in enumerate(lines) if "gmj_firecrawl_search.py" in line]
    assert firecrawl_lines, "expected at least one gmj_firecrawl_search.py reference"

    search_provider_lines = [i for i, line in enumerate(lines) if "search_provider" in line]
    assert search_provider_lines, "expected at least one search_provider reference"

    for fc_idx in firecrawl_lines:
        nearest = min(abs(fc_idx - sp_idx) for sp_idx in search_provider_lines)
        assert nearest <= PROXIMITY_LINES, (
            f"gmj_firecrawl_search.py reference at line {fc_idx + 1} is not within "
            f"{PROXIMITY_LINES} lines of any search_provider mention (nearest={nearest}) — "
            "the script must never be invoked unconditionally outside the opt-in branch"
        )


def test_schema_validates_committed_preferences_file() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--file", str(PREFERENCES_YAML)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        "gmj_validate_preferences.py must still exit 0 against the real committed "
        f"config/preferences.yaml after Plan 03's schema edit; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
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
