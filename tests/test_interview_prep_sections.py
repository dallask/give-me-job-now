#!/usr/bin/env python3
"""Plain-python3 tests for section-grouping in scripts/cv/gmj_render_interview_prep.py (ARTIFACT-01).

Proves the renderer groups an approved interview_prep draft's claims by the required
``claim.section`` field under ``## <Section Title>`` markdown headers, in
first-appearance order, dropping no claim, and still degrades to exit 1 with no
traceback on a malformed draft. No pytest — run with
``python3 tests/test_interview_prep_sections.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_interview_prep.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "interview_prep.rich.draft.json"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _render_fixture() -> str:
    out = Path(tempfile.mkdtemp()) / "rich.md"
    result = _run("--file", str(FIXTURE), "--out", str(out))
    assert result.returncode == 0, f"rich render must exit 0: {result.stderr}"
    return out.read_text(encoding="utf-8")


def test_four_section_headers_in_first_appearance_order() -> None:
    md = _render_fixture()
    headers = [ln[3:].strip() for ln in md.splitlines() if ln.startswith("## ")]
    expected = ["Likely Questions", "Star Stories", "Talking Points", "Questions To Ask"]
    assert headers == expected, f"headers/order wrong: {headers} != {expected}"


def test_no_claim_dropped() -> None:
    md = _render_fixture()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    claim_count = len(fixture["content"]["claims"])
    bullets = [ln for ln in md.splitlines() if ln.startswith("- ")]
    assert len(bullets) == claim_count, (
        f"bullet count {len(bullets)} != claim count {claim_count} (a claim was dropped)"
    )


def test_two_star_stories_with_distinct_spans() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    stars = [c for c in fixture["content"]["claims"] if c.get("section") == "star_stories"]
    assert len(stars) >= 2, f"need >=2 star_stories claims, got {len(stars)}"
    spans = {c["source_span"] for c in stars}
    assert len(spans) == len(stars), f"star_stories spans must be distinct: {spans}"


def test_malformed_draft_degrades_exit_1() -> None:
    bad = Path(tempfile.mkdtemp()) / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    out = Path(tempfile.mkdtemp()) / "bad.md"
    result = _run("--file", str(bad), "--out", str(out))
    assert result.returncode == 1, "malformed draft must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on malformed draft"


def test_whitespace_only_text_claim_rejected_not_silently_dropped() -> None:
    """A whitespace-only ``text`` claim must be rejected up front, consistently.

    A claim like ``"   "`` would pass a bare truthiness gate but render to
    nothing after the strip — a silent drop that contradicts the "dropping no
    claim" guarantee. The loader now filters on stripped text, so a draft whose
    only claim is whitespace-only degrades to exit 1 (no usable claims) with a
    diagnostic and no traceback, per the malformed-draft contract.
    """
    draft = Path(tempfile.mkdtemp()) / "ws.json"
    draft.write_text(
        json.dumps({"content": {"claims": [{"text": "   ", "section": "notes"}]}}),
        encoding="utf-8",
    )
    out = Path(tempfile.mkdtemp()) / "ws.md"
    result = _run("--file", str(draft), "--out", str(out))
    assert result.returncode == 1, "whitespace-only-text claim must degrade to exit 1"
    assert "Traceback" not in result.stderr, "no traceback on whitespace-only claim"
    assert not out.exists(), "no markdown should be written when no claim is usable"


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
