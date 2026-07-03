#!/usr/bin/env python3
"""Emit an approved interview_prep artifact_draft as an ordered markdown document.

Trivial deterministic markdown/text writer — NO ReportLab, no PDF. Reads the
approved interview_prep draft and writes its ordered claim.text values as
markdown lines. Mirrors the argparse/degrade/entry skeleton of
render_cover_letter.py so cv-generator can invoke it the same way.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LANGS = ("en", "ua", "ru")


def render_interview_prep(lines: list[str], out_path: Path) -> None:
    """Write ordered interview-prep lines as a markdown document."""
    body = "\n".join(f"- {line}" for line in lines)
    out_path.write_text(f"# Interview Prep\n\n{body}\n", encoding="utf-8")


def repo_root_from_here() -> Path:
    """Walk up from this script looking for CLAUDE.md or .claude/ as repo root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").is_file() or (p / ".claude").is_dir():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent


def _lines_from_draft(draft_path: Path) -> list[str] | None:
    """Load an approved interview_prep draft; return ordered claim texts, or None on error."""
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read interview_prep draft {draft_path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"Draft root must be a mapping: {draft_path}", file=sys.stderr)
        return None
    content = data.get("content")
    claims = content.get("claims") if isinstance(content, dict) else None
    if not isinstance(claims, list) or not claims:
        print(f"Draft has no content.claims: {draft_path}", file=sys.stderr)
        return None
    lines = [
        str(c.get("text")).strip()
        for c in claims
        if isinstance(c, dict) and c.get("text")
    ]
    if not lines:
        print(f"Draft claims contain no text: {draft_path}", file=sys.stderr)
        return None
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit an approved interview_prep draft as a markdown document."
    )
    parser.add_argument(
        "--file", "--draft", dest="file", type=Path, required=True,
        help="Path to approved interview_prep artifact_draft JSON",
    )
    parser.add_argument("--out", type=Path, help="Output markdown path")
    parser.add_argument(
        "--lang", default=None, choices=list(LANGS),
        help="Output language (informational; markdown is language-agnostic)",
    )
    args = parser.parse_args()

    draft_path = args.file.expanduser().resolve()
    lines = _lines_from_draft(draft_path)
    if lines is None:
        return 1

    out_path = args.out
    if not out_path:
        repo_root = repo_root_from_here()
        out_dir = (repo_root / "output").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S")
        out_path = out_dir / f"interview-prep-{date_part}.md"
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        render_interview_prep(lines, out_path)
    except OSError as exc:  # degrade without traceback
        print(f"Interview-prep write failed: {exc}", file=sys.stderr)
        return 1

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
