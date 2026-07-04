#!/usr/bin/env python3
"""Render candidate YAML to PDF using ReportLab. Optional Jinja2 HTML template via WeasyPrint if installed."""

from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from xml.sax.saxutils import escape

# Import the single-owner candidate.yaml field-name registry (SCHEMA-06) so this
# consumer never re-declares key literals that could drift from the schema owner.
# Same import idiom as scripts/cv/gmj_draft_to_cv_yaml.py (scripts/artifacts on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "artifacts"))
from gmj_schema_fields import CONTACT, WEBSITE_GROUPS  # noqa: E402  (both must be USED, not just imported)

LANGS = ("en", "ua", "ru")
DEFAULT_LANG = "en"

_FONT_DIRS = [
    str(Path(__file__).parent / "fonts"),
    "/usr/share/fonts/truetype/dejavu",
    "/usr/local/share/fonts",
]


def _register_unicode_font() -> tuple[str, str]:
    """Register DejaVu Sans TTF for Cyrillic support. Returns (regular_name, bold_name)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for d in _FONT_DIRS:
        regular = Path(d) / "DejaVuSans.ttf"
        bold = Path(d) / "DejaVuSans-Bold.ttf"
        if regular.is_file():
            pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
            if bold.is_file():
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
                return "DejaVuSans", "DejaVuSans-Bold"
            return "DejaVuSans", "DejaVuSans"
    return "Helvetica", "Helvetica-Bold"


def _load_labels(repo_root: Path, lang: str) -> dict:
    path = repo_root / "config" / "i18n" / "labels.yaml"
    if not path.is_file():
        return {}
    all_labels: dict = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return all_labels.get(lang) or all_labels.get(DEFAULT_LANG) or {}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _is_skill_cv(config_path: Path) -> bool:
    """True when config is a skill-specific file under config/cv/."""
    return config_path.resolve().parent.name == "cv"


def lang_from_config_path(config_path: Path, explicit_lang: str | None) -> str:
    """Return lang: explicit arg wins; otherwise infer from filename suffix (cv.fpv.ua.yaml → ua)."""
    if explicit_lang is not None:
        return explicit_lang
    stem = config_path.stem         # e.g. "cv.fpv.ua"
    last = stem.rsplit(".", 1)[-1]  # "ua"
    return last if last in LANGS else DEFAULT_LANG


def load_candidate(config_path: Path, lang: str = DEFAULT_LANG) -> dict:
    base: dict = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(base, dict):
        raise ValueError("Config root must be a mapping")
    # Skill-specific cv/ files are standalone — no overlay merging needed.
    # Overlay merging only applies to the master candidate.yaml.
    if _is_skill_cv(config_path) or lang == DEFAULT_LANG:
        return base
    overlay_path = config_path.parent / f"candidate.{lang}.yaml"
    if not overlay_path.is_file():
        return base
    overlay = yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    return _deep_merge(base, overlay)


def slug(s: str) -> str:
    x = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return x or "cv"


def repo_root_from_config(config_path: Path) -> Path:
    """Walk up from config file looking for CLAUDE.md or .claude/ as repo root anchor."""
    p = config_path.resolve().parent
    while p != p.parent:
        if (p / "CLAUDE.md").is_file() or (p / ".claude").is_dir():
            return p
        p = p.parent
    # fallback: assume config is one level below repo root
    return config_path.resolve().parent.parent


def photo_raw(candidate: dict) -> str | None:
    raw = candidate.get("photo")
    if raw:
        return str(raw).strip() or None
    contact = candidate.get("contact")
    if isinstance(contact, dict) and contact.get("photo"):
        return str(contact["photo"]).strip() or None
    return None


def photo_path_for(candidate: dict, repo_root: Path) -> Path | None:
    raw = photo_raw(candidate)
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    else:
        path = path.resolve()
    return path if path.is_file() else None


def candidate_for_template(candidate: dict, repo_root: Path) -> dict:
    """Copy candidate dict; drop invalid photo paths so HTML img does not break."""
    out = dict(candidate)
    if photo_raw(out) and not photo_path_for(out, repo_root):
        out.pop("photo", None)
        c = out.get("contact")
        if isinstance(c, dict) and "photo" in c:
            c2 = dict(c)
            c2.pop("photo", None)
            out["contact"] = c2
    return out


def _photo_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def candidate_with_embedded_photo(candidate: dict, repo_root: Path) -> dict:
    """Return candidate dict with photo replaced by a base64 data URI for standalone HTML."""
    out = candidate_for_template(candidate, repo_root)
    photo_path = photo_path_for(out, repo_root)
    if not photo_path:
        return out
    data_uri = _photo_data_uri(photo_path)
    if out.get("photo"):
        out["photo"] = data_uri
    c = out.get("contact")
    if isinstance(c, dict) and c.get("photo"):
        out["contact"] = {**c, "photo": data_uri}
    return out


def _contact_lines(contact: dict) -> list[str]:
    """Build contact strings by SHAPE — never by string-formatting a bare container.

    Consumes the nested v2.0 ``contact`` schema (email is a list, ``website`` is a mapping
    of ``personal``/``company``/``portfolio`` URL lists plus a ``media`` label→url dict, and
    ``messengers`` is a label→handle dict). Every access is guarded with ``or []`` / ``or {}``
    and every appended line is a plain string, so no ``[`` or ``{`` container-repr can ever
    leak into the rendered PDF (SCHEMA-02). Group names come from the ``WEBSITE_GROUPS``
    registry (SCHEMA-06) rather than being re-declared here.
    """
    # Field names come from the CONTACT registry (SCHEMA-06) — never re-declared as
    # bare literals here, so a rename of the schema owner cannot silently drift.
    phone_key, email_key, address_key, website_key, messengers_key = CONTACT
    lines: list[str] = []
    if not isinstance(contact, dict):
        return lines
    if contact.get(phone_key):
        lines.append(f"Phone: {contact[phone_key]}")
    emails = contact.get(email_key) or []
    if emails:
        if isinstance(emails, (list, tuple)):
            joined = ", ".join(str(e) for e in emails)
        else:
            joined = str(emails)
        if joined:
            lines.append(f"Email: {joined}")
    if contact.get(address_key):
        lines.append(str(contact[address_key]))
    web = contact.get(website_key) or {}
    if isinstance(web, dict):
        # URL-list groups (every WEBSITE_GROUPS entry except the "media" label→url dict).
        for group in WEBSITE_GROUPS:
            if group == "media":
                continue
            for url in web.get(group) or []:
                if url:
                    lines.append(str(url))
        media = web.get("media")
        media = media if isinstance(media, dict) else {}
        for label, url in media.items():
            if url:
                lines.append(f"{str(label).capitalize()}: {url}")
    messengers = contact.get(messengers_key)
    messengers = messengers if isinstance(messengers, dict) else {}
    for label, handle in messengers.items():
        if handle:
            lines.append(f"{str(label).capitalize()}: {handle}")
    return lines


def render_reportlab(candidate: dict, out_path: Path, *, repo_root: Path, labels: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font_regular, font_bold = _register_unicode_font()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="CVTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=18,
        leading=22,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        name="CVSubtitle",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        name="CVH2",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#111111"),
    )
    body_style = ParagraphStyle(
        name="CVBody",
        parent=styles["Normal"],
        fontName=font_regular,
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

    def lbl(key: str, default: str = "") -> str:
        return labels.get(key) or default

    name = candidate.get("name") or "Candidate"
    title = candidate.get("title") or ""
    summary = candidate.get("summary") or ""

    photo_path = photo_path_for(candidate, repo_root)
    contact = candidate.get("contact") or {}
    contact_bits = _contact_lines(contact)
    contact_html = "<br/>".join(escape(b) for b in contact_bits)

    left_cell: list = [
        Paragraph(escape(name), title_style),
    ]
    if title:
        left_cell.append(Paragraph(escape(title), subtitle_style))
    if contact_html:
        left_cell.append(Paragraph(contact_html.replace("\n", "<br/>"), body_style))

    if photo_path:
        img = RLImage(str(photo_path), width=28 * mm, height=28 * mm, mask="auto")
        header = Table(
            [[left_cell, img]],
            colWidths=[doc.width - 34 * mm, 30 * mm],
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(header)
    else:
        story.extend(left_cell)

    if summary:
        story.append(Paragraph(f"<b>{escape(lbl('summary', 'Summary'))}</b>", h2_style))
        story.append(Paragraph(summary.replace("&", "&amp;"), body_style))

    tech = candidate.get("expertise") or []
    if tech:
        story.append(Paragraph(f"<b>{escape(lbl('expertise', 'Technical expertise'))}</b>", h2_style))
        for block in tech:
            if not isinstance(block, dict):
                continue
            rt = block.get("resume_title") or "Skills"
            skills = block.get("skills") or []
            story.append(Paragraph(f"<b>{escape(str(rt))}</b>", body_style))
            if isinstance(skills, list):
                story.append(Paragraph(", ".join(str(s) for s in skills).replace("&", "&amp;"), body_style))
            story.append(Spacer(1, 4))

    skills_flat = candidate.get("skills") or []
    if isinstance(skills_flat, list) and skills_flat:
        story.append(Paragraph(f"<b>{escape(lbl('core_skills', 'Core skills'))}</b>", h2_style))
        story.append(Paragraph(", ".join(str(s) for s in skills_flat).replace("&", "&amp;"), body_style))

    langs = candidate.get("languages") or []
    if langs:
        story.append(Paragraph(f"<b>{escape(lbl('languages', 'Languages'))}</b>", h2_style))
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
        story.append(Paragraph(f"<b>{escape(lbl('experience', 'Experience'))}</b>", h2_style))
        for job in exp:
            if not isinstance(job, dict):
                continue
            header_text = f"{job.get('position','')} — {job.get('company','')}"
            meta = " | ".join(x for x in (job.get("location"), job.get("duration")) if x)
            story.append(Paragraph(f"<b>{header_text}</b>".replace("&", "&amp;"), body_style))
            if meta:
                story.append(Paragraph(meta.replace("&", "&amp;"), subtitle_style))
            # role_progression is a schema-declared experience field (EXPERIENCE_FIELDS)
            # that the HTML template renders (enhancv-inspired.html); render it here too
            # so the default ReportLab path does not silently drop real CV content.
            role_progression = job.get("role_progression")
            if role_progression:
                story.append(Paragraph(str(role_progression).replace("&", "&amp;"), subtitle_style))
            desc = job.get("company_description")
            if desc:
                story.append(Paragraph(str(desc).replace("&", "&amp;"), body_style))
            for ach in job.get("achievements") or []:
                story.append(Paragraph(f"• {str(ach)}".replace("&", "&amp;"), body_style))
            story.append(Spacer(1, 6))

    edu = candidate.get("education") or []
    if edu:
        story.append(Paragraph(f"<b>{escape(lbl('education', 'Education'))}</b>", h2_style))
        for row in edu:
            if isinstance(row, dict):
                line = " — ".join(
                    x for x in (row.get("program"), row.get("institution"), row.get("duration")) if x
                )
                story.append(Paragraph(line.replace("&", "&amp;"), body_style))

    projects = candidate.get("independent_projects") or []
    if isinstance(projects, list) and projects:
        story.append(Paragraph(f"<b>{escape(lbl('independent_projects', 'Independent projects'))}</b>", h2_style))
        for p in projects:
            if isinstance(p, dict):
                story.append(
                    Paragraph(str(p.get("name") or p.get("title") or p).replace("&", "&amp;"), body_style)
                )
            else:
                story.append(Paragraph(str(p).replace("&", "&amp;"), body_style))

    certs = candidate.get("certifications") or []
    if isinstance(certs, list) and certs:
        story.append(Paragraph(f"<b>{escape(lbl('certifications', 'Courses &amp; certifications'))}</b>", h2_style))
        for block in certs:
            if not isinstance(block, dict):
                continue
            issuer = escape(str(block.get("issuer") or ""))
            year = block.get("year")
            head = f"{issuer} ({year})" if year else issuer
            story.append(Paragraph(f"<b>{head}</b>", body_style))
            for line in block.get("credentials") or []:
                story.append(Paragraph(f"• {escape(str(line))}", body_style))
            story.append(Spacer(1, 4))

    key_ach = candidate.get("key_achievements") or []
    if isinstance(key_ach, list) and key_ach:
        story.append(Paragraph(f"<b>{escape(lbl('key_achievements', 'Key achievements'))}</b>", h2_style))
        for item in key_ach:
            if isinstance(item, dict):
                t = escape(str(item.get("title") or ""))
                d = escape(str(item.get("description") or ""))
                story.append(Paragraph(f"• <b>{t}</b> — {d}", body_style))
            else:
                story.append(Paragraph(f"• {escape(str(item))}", body_style))

    doc.build(story)


def _prepend_dyld_fallback_for_weasyprint() -> None:
    """Help WeasyPrint find Homebrew Pango on macOS when launching from GUIs/IDEs."""
    if platform.system() != "Darwin":
        return
    for lib in ("/opt/homebrew/lib", "/usr/local/lib"):
        if os.path.isdir(lib):
            cur = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            parts = [p for p in cur.split(os.pathsep) if p]
            if lib not in parts:
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = lib + (os.pathsep + cur if cur else "")
            break


def render_weasyprint_html(
    candidate: dict,
    template_path: Path,
    out_path: Path,
    *,
    repo_root: Path,
    html_out_path: Path | None = None,
    labels: dict,
    lang: str,
) -> None:
    _prepend_dyld_fallback_for_weasyprint()
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from weasyprint import HTML

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    tpl = env.get_template(template_path.name)
    br = repo_root.resolve()
    base_uri = br.as_uri()
    if not base_uri.endswith("/"):
        base_uri += "/"
    html_str = tpl.render(candidate=candidate, now=datetime.now(timezone.utc),
                          labels=labels, lang=lang)
    if html_out_path is not None:
        html_out_path.write_text(html_str, encoding="utf-8")
    HTML(string=html_str, base_url=base_uri).write_pdf(str(out_path))


def _prune_old_outputs(new_pdf: Path, out_dir: Path, keep: int) -> None:
    """Delete all but the newest `keep` PDFs (and paired .html) per (stem_prefix, lang) group."""
    import re
    ts_pattern = re.compile(r"-\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}$")
    stem = new_pdf.stem  # e.g. "cv.fpv.ua-2026-05-04_08:30:21" or "yevhen-kyvhyla-ua-..."
    prefix = ts_pattern.sub("", stem)  # strip timestamp → "cv.fpv.ua" or "yevhen-kyvhyla-ua"
    if not prefix:
        return
    peers = sorted(
        [p for p in out_dir.glob(f"{prefix}-*.pdf") if p != new_pdf],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    to_delete = peers[keep - 1:]  # keep (keep-1) existing + the new one = keep total
    for old in to_delete:
        try:
            old.unlink(missing_ok=True)
            sibling_html = old.with_suffix(".html")
            if sibling_html.is_file():
                sibling_html.unlink(missing_ok=True)
        except OSError:
            pass


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
    parser.add_argument(
        "--lang",
        default=None,
        choices=list(LANGS),
        help="Output language for section labels (auto-detected from filename when omitted)",
    )
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    lang = lang_from_config_path(config_path, args.lang)
    candidate = load_candidate(config_path, lang)
    repo_root = repo_root_from_config(config_path)
    labels = _load_labels(repo_root, lang)

    date_part = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S")
    if _is_skill_cv(config_path):
        # cv.fpv.ua.yaml → output name "cv.fpv.ua-<timestamp>.pdf" (lang already in stem)
        default_name = config_path.stem
        lang_suffix = ""
    else:
        default_name = slug(str(candidate.get("name") or "candidate"))
        lang_suffix = f"-{lang}" if lang != DEFAULT_LANG else ""
    out_path = args.out
    if not out_path:
        out_dir = (repo_root / "output" / "cv").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{default_name}{lang_suffix}-{date_part}.pdf"
    else:
        out_path = out_path.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    use_html = args.template and not args.no_template
    if use_html:
        tpl = args.template.expanduser().resolve()
        if not tpl.is_file():
            print(f"Template not found: {tpl}", file=sys.stderr)
            return 1
        html_out_path = out_path.with_suffix(".html")
        try:
            cand = candidate_with_embedded_photo(candidate, repo_root)
            render_weasyprint_html(cand, tpl, out_path, repo_root=repo_root,
                                   html_out_path=html_out_path, labels=labels, lang=lang)
        except ImportError:
            print(
                "WeasyPrint/Jinja2 HTML path requires: pip install weasyprint\n"
                "Falling back to ReportLab built-in layout.",
                file=sys.stderr,
            )
            render_reportlab(candidate, out_path, repo_root=repo_root, labels=labels)
            html_out_path = None
        if html_out_path is not None:
            print(str(html_out_path))
    else:
        render_reportlab(candidate, out_path, repo_root=repo_root, labels=labels)

    print(str(out_path))

    if not args.out:
        keep = int(os.environ.get("CV_KEEP_LAST", "5"))
        _prune_old_outputs(out_path, out_path.parent, keep=keep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
