#!/usr/bin/env python3
"""Render an approved cover_letter artifact_draft to a PDF via ReportLab.

Thin sibling of gmj_render_cv.py: imports ONLY the shared Cyrillic font setup
(_register_unicode_font) and never touches the CV layout renderer / the CV
path (T-08-05, Pitfall 4). One Paragraph per ordered claim.text; every claim
text is XML-escaped before it reaches ReportLab's mini-markup parser
(injection mitigation T-08-06). PDFs are written under output/cv/ — no manual
PDF authoring.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
from gmj_render_cv import _register_unicode_font  # noqa: E402  (share font setup only)

LANGS = ("en", "ua", "ru")


def render_cover_letter(paragraphs: list[str], out_path: Path) -> None:
    """Build a simple A4 PDF: one escaped Paragraph per cover-letter paragraph."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    font_regular, _ = _register_unicode_font()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CoverLetterBody",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=11,
        leading=15,
    )
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )
    story: list = []
    for p in paragraphs:
        # escape() is the XML/markup-injection mitigation (gmj_render_cv.py:17 pattern).
        story.append(Paragraph(escape(p), body))
        story.append(Spacer(1, 8))
    doc.build(story)


def repo_root_from_here() -> Path:
    """Walk up from this script looking for CLAUDE.md or .claude/ as repo root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").is_file() or (p / ".claude").is_dir():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent


def _paragraphs_from_draft(draft_path: Path) -> list[str] | None:
    """Load an approved cover_letter draft; return ordered claim texts, or None on error."""
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read cover_letter draft {draft_path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"Draft root must be a mapping: {draft_path}", file=sys.stderr)
        return None
    content = data.get("content")
    claims = content.get("claims") if isinstance(content, dict) else None
    if not isinstance(claims, list) or not claims:
        print(f"Draft has no content.claims: {draft_path}", file=sys.stderr)
        return None
    paragraphs = [
        str(c.get("text")).strip()
        for c in claims
        if isinstance(c, dict) and c.get("text")
    ]
    if not paragraphs:
        print(f"Draft claims contain no text: {draft_path}", file=sys.stderr)
        return None
    return paragraphs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render an approved cover_letter draft to a PDF (ReportLab)."
    )
    parser.add_argument(
        "--file", "--draft", dest="file", type=Path, required=True,
        help="Path to approved cover_letter artifact_draft JSON",
    )
    parser.add_argument("--out", type=Path, help="Output PDF path")
    parser.add_argument(
        "--lang", default=None, choices=list(LANGS),
        help="Output language (bundled DejaVu fonts cover ua/ru Cyrillic)",
    )
    args = parser.parse_args()

    draft_path = args.file.expanduser().resolve()
    paragraphs = _paragraphs_from_draft(draft_path)
    if paragraphs is None:
        return 1

    out_path = args.out
    if not out_path:
        repo_root = repo_root_from_here()
        out_dir = (repo_root / "output" / "cv").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S")
        out_path = out_dir / f"cover-letter-{date_part}.pdf"
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        render_cover_letter(paragraphs, out_path)
    except Exception as exc:  # noqa: BLE001 — degrade without traceback
        print(f"Cover-letter render failed: {exc}", file=sys.stderr)
        return 1

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
