#!/usr/bin/env python3
"""RED contract for STRUCT-03 — CLAUDE.md carries only the current gmj- roster.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_claude_md_current.py``. This IS a real gate in the
``tests/test_*.py`` glob. It is the machine-checkable acceptance contract that plan 18-04
(the CLAUDE.md refresh) must turn GREEN, run against BOTH ``CLAUDE.md`` and
``.claude/CLAUDE.md``. It is EXPECTED to FAIL now (RED): both files still present the
superseded legacy-13-agent roster as the CURRENT roster and neither points at the
``rules/`` index.

STALE_TOKENS is the single source of truth for the grep gate — the superseded non-gmj
Component-Responsibilities roster (18-PATTERNS lines 218-223). Plan 18-04 consults THIS
list rather than embedding the tokens in its own action body.

Grep discipline (mirrors tests/test_rebrand_acceptance.py grep-0 style; threat T-18-06 —
avoid a false-negative that lets a stale token slip through): a token occurrence is
counted as a CURRENT-roster reference UNLESS the line is a comment (``<!--``) / blockquote
(``>``) line, or sits inside an explicitly-marked historical/superseded block (a heading
or line carrying a ``historical`` / ``superseded`` marker, or an HTML-comment-delimited
block). A bare current mention fails; each failure names the token + file + line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CLAUDE_FILES = (
    REPO_ROOT / "CLAUDE.md",
    REPO_ROOT / ".claude" / "CLAUDE.md",
)

# Single source of truth: the superseded legacy-13-agent-roster names to drop (the non-gmj
# Component-Responsibilities rows, 18-PATTERNS lines 218-223). NOT the retained gmj- roster.
STALE_TOKENS = (
    "vacancy-router",
    "job-market-researcher",
    "vacancy-scraper",
    "candidate-translator",
    "cv-composer",
    "cv-template-creator",
    "cv-reviewer",
    "cv-enhancer",
    "cv-deliverable-gate",
)

# Positive-presence anchors every refreshed file must retain.
HUB_NAME = "gmj-orchestrator"
ARCH_POINTER = "ARCHITECTURE.md"
RULES_POINTER = "rules/"

_HEADING = re.compile(r"^#{1,6}\s")


def _has_marker(text: str) -> bool:
    low = text.lower()
    return "historical" in low or "superseded" in low


def _current_sites(text: str, token: str) -> list[int]:
    """Line numbers where ``token`` appears as a CURRENT reference (exclusions applied).

    Excluded (NOT counted): blockquote (``>``) / HTML-comment (``<!--``) lines, any line
    inside a heading-section whose heading is marked historical/superseded, any line inside
    an HTML-comment-delimited ``historical``/``superseded`` block, and any line self-marked
    with a historical/superseded word.
    """
    pattern = re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")
    sites: list[int] = []
    section_historical = False
    in_hist_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # HTML-comment marker lines toggle an explicit historical block (and are not counted).
        if stripped.startswith("<!--") and _has_marker(stripped):
            if "end" in stripped.lower() or "/" in stripped:
                in_hist_block = False
            else:
                in_hist_block = True
            continue
        # A heading resets the section's historical disposition based on its own text.
        if _HEADING.match(line):
            section_historical = _has_marker(line)
        # Exclusions: comment/quote line, marked block/section, or a self-marked line.
        if stripped.startswith(">") or stripped.startswith("<!--"):
            continue
        if in_hist_block or section_historical or _has_marker(line):
            continue
        if pattern.search(line):
            sites.append(i)
    return sites


def test_no_stale_roster_tokens_presented_as_current() -> None:
    """Each STALE_TOKEN appears 0 times as a current-roster reference in both files."""
    violations: list[str] = []
    for path in CLAUDE_FILES:
        assert path.is_file(), f"CLAUDE file missing: {path.relative_to(REPO_ROOT)}"
        text = path.read_text(encoding="utf-8")
        for token in STALE_TOKENS:
            sites = _current_sites(text, token)
            if sites:
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"{rel}: '{token}' as current on line(s) {sites[:10]}")
    assert not violations, (
        "legacy roster token(s) still presented as current "
        f"({len(violations)}): " + " | ".join(violations)
    )


def test_files_name_gmj_hub_and_architecture_pointer() -> None:
    """Both files positively name the gmj- hub and point at docs/ARCHITECTURE.md."""
    for path in CLAUDE_FILES:
        assert path.is_file(), f"CLAUDE file missing: {path.relative_to(REPO_ROOT)}"
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        assert HUB_NAME in text, f"{rel}: missing gmj- hub name '{HUB_NAME}'"
        assert ARCH_POINTER in text, (
            f"{rel}: missing roster source-of-truth pointer to docs/ARCHITECTURE.md"
        )


def test_files_reference_rules_index() -> None:
    """Both files reference the rules index (STRUCT-03 pointer — a `rules/` mention)."""
    for path in CLAUDE_FILES:
        assert path.is_file(), f"CLAUDE file missing: {path.relative_to(REPO_ROOT)}"
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        assert RULES_POINTER in text, f"{rel}: missing rules-index pointer ('{RULES_POINTER}')"


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
