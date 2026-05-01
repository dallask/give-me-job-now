#!/usr/bin/env python3
"""Render candidate YAML to PDF using ReportLab. Optional Jinja2 HTML template via WeasyPrint if installed."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_candidate(config_path: Path) -> dict:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    return raw


def slug(s: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return x or "cv"


def render_reportlab(candidate: dict, out_path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="CVTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        name="CVSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        name="CVH2",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#111111"),
    )
    body_style = ParagraphStyle(
        name="CVBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
    )
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    story: list = []

    name = candidate.get("name") or "Candidate"
    title = candidate.get("title") or ""
    summary = candidate.get("summary") or ""

    story.append(Paragraph(name.replace("&", "&amp;"), title_style))
    if title:
        story.append(Paragraph(title.replace("&", "&amp;"), subtitle_style))
    if summary:
        story.append(Paragraph("<b>Summary</b>", h2_style))
        story.append(Paragraph(summary.replace("&", "&amp;"), body_style))

    contact = candidate.get("contact") or {}
    if isinstance(contact, dict) and contact:
        story.append(Paragraph("<b>Contact</b>", h2_style))
        lines = []
        for k in ("email", "phone", "address", "website", "github", "linkedin"):
            v = contact.get(k)
            if v:
                lines.append(f"{k.capitalize()}: {v}")
        story.append(Paragraph("<br/>".join(lines).replace("&", "&amp;"), body_style))

    tech = candidate.get("technical_expertise") or []
    if tech:
        story.append(Paragraph("<b>Technical expertise</b>", h2_style))
        for block in tech:
            if not isinstance(block, dict):
                continue
            rt = block.get("resume_title") or "Skills"
            skills = block.get("skills") or []
            story.append(Paragraph(f"<b>{rt}</b>", body_style))
            if isinstance(skills, list):
                story.append(Paragraph(", ".join(str(s) for s in skills).replace("&", "&amp;"), body_style))
            story.append(Spacer(1, 4))

    skills_flat = candidate.get("skills") or []
    if isinstance(skills_flat, list) and skills_flat:
        story.append(Paragraph("<b>Core skills</b>", h2_style))
        story.append(Paragraph(", ".join(str(s) for s in skills_flat).replace("&", "&amp;"), body_style))

    langs = candidate.get("languages") or []
    if langs:
        story.append(Paragraph("<b>Languages</b>", h2_style))
        for row in langs:
            if isinstance(row, dict):
                story.append(
                    Paragraph(
                        f"• {row.get('language','')}: {row.get('proficiency','')}".replace("&", "&amp;"),
                        body_style,
                    )
                )

    exp = candidate.get("professional_experience") or []
    if exp:
        story.append(Paragraph("<b>Experience</b>", h2_style))
        for job in exp:
            if not isinstance(job, dict):
                continue
            header = f"{job.get('position','')} — {job.get('company','')}"
            meta = " | ".join(x for x in (job.get("location"), job.get("duration")) if x)
            story.append(Paragraph(f"<b>{header}</b>".replace("&", "&amp;"), body_style))
            if meta:
                story.append(Paragraph(meta.replace("&", "&amp;"), subtitle_style))
            desc = job.get("company_description")
            if desc:
                story.append(Paragraph(str(desc).replace("&", "&amp;"), body_style))
            for ach in job.get("achievements") or []:
                story.append(Paragraph(f"• {str(ach)}".replace("&", "&amp;"), body_style))
            story.append(Spacer(1, 6))

    edu = candidate.get("education") or []
    if edu:
        story.append(Paragraph("<b>Education</b>", h2_style))
        for row in edu:
            if isinstance(row, dict):
                line = " — ".join(
                    x for x in (row.get("program"), row.get("institution"), row.get("duration")) if x
                )
                story.append(Paragraph(line.replace("&", "&amp;"), body_style))

    projects = candidate.get("independent_projects") or []
    if isinstance(projects, list) and projects:
        story.append(Paragraph("<b>Independent projects</b>", h2_style))
        for p in projects:
            if isinstance(p, dict):
                story.append(
                    Paragraph(str(p.get("name") or p.get("title") or p).replace("&", "&amp;"), body_style)
                )
            else:
                story.append(Paragraph(str(p).replace("&", "&amp;"), body_style))

    doc.build(story)


def render_weasyprint_html(candidate: dict, template_path: Path, out_path: Path) -> None:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from weasyprint import HTML

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template(template_path.name)
    html_str = tpl.render(candidate=candidate, now=datetime.now(timezone.utc))
    HTML(string=html_str, base_url=str(template_path.parent)).write_pdf(str(out_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render config/candidate.yaml to PDF.")
    parser.add_argument("--config", type=Path, required=True, help="Path to candidate YAML")
    parser.add_argument("--out", type=Path, help="Output PDF path")
    parser.add_argument(
        "--template",
        type=Path,
        help="Optional Jinja2 HTML template (requires weasyprint)",
    )
    parser.add_argument(
        "--no-template",
        action="store_true",
        help="Force built-in ReportLab layout (default when --template omitted)",
    )
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    candidate = load_candidate(config_path)

    default_name = slug(str(candidate.get("name") or "candidate"))
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = args.out
    if not out_path:
        repo_root = config_path.parent.parent
        out_dir = repo_root / "output" / "cv"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{default_name}-{date_part}.pdf"
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    use_html = args.template and not args.no_template
    if use_html:
        tpl = args.template.expanduser().resolve()
        if not tpl.is_file():
            print(f"Template not found: {tpl}", file=sys.stderr)
            return 1
        try:
            render_weasyprint_html(candidate, tpl, out_path)
        except ImportError:
            print(
                "WeasyPrint/Jinja2 HTML path requires: pip install weasyprint\n"
                "Falling back to ReportLab built-in layout.",
                file=sys.stderr,
            )
            render_reportlab(candidate, out_path)
    else:
        render_reportlab(candidate, out_path)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
