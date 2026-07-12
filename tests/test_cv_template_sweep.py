#!/usr/bin/env python3
"""Standing parametrized regression sweep over every templates/cv/*.html (PIPE-09, PIPE-11).

Mirrors tests/test_schema_migration.py's ``_run()``/``_pdf_text()`` subprocess+pypdf
helper pattern and the "iterate + collect offenders + one final assert" idiom from
tests/test_gmj_template_lint.py's ``test_real_templates_have_no_legacy_schema_bindings``
(this repo's plain-python3 harness convention has no pytest ``@pytest.mark.parametrize``).

Four behaviors proven empirically (real render + real text/image extraction, never by
reading template source and trusting an ``{% if %}`` guard exists):

  * ``test_photo_renders_across_every_html_template`` — every one of the 9 real
    templates/cv/*.html files, rendered against config/candidate.yaml (which configures
    ``photo: sources/user_photo.jpg``), produces an ``.html`` sibling containing a
    non-empty ``<img src="...">`` (the embedded base64 data URI) — proving the photo
    actually reached the rendered output (PIPE-09).
  * ``test_photo_renders_via_reportlab_backend`` — ``--no-template`` (ReportLab) produces
    a PDF whose page(s) carry at least one embedded image XObject (``page.images``),
    proving ``photo_path_for()`` + the ``RLImage`` embed path actually rasterizes an
    image, not just that the code path exists (PIPE-09).
  * ``test_no_leak_across_all_9_templates`` — every one of the 9 templates, rendered and
    pypdf-extracted, contains neither ``"['"`` nor ``"{'"`` anywhere in the extracted
    text — the PIPE-02 "everywhere" sweep, broader than test_schema_migration.py's
    single-default-template check (RESEARCH.md Common Pitfall 3).
  * ``test_education_languages_certifications_present_where_template_supports_them`` —
    for the templates whose own HTML source declares a VISIBLE certifications heading
    (``labels.certifications`` or a literal ``>Certifications<`` — baxter.html and
    default.html per this plan's Task 1 fix, plus any other template using the same
    labels key; several other templates bind ``candidate.certifications`` data under a
    "Courses" heading via ``labels.courses`` instead and are correctly out of scope —
    detected by reading each template file's source at test time, not a hardcoded
    assumption), the rendered PDF text contains the Education/Languages/Certifications
    section labels (case-normalized, since some templates render section headings as
    uppercase glyphs via ``text-transform: uppercase`` — pypdf extracts the literal
    drawn glyph shapes, not the DOM source casing).

No pytest — run with ``python3 tests/test_cv_template_sweep.py`` (also pytest-collectible
since every function is named ``test_*`` and takes no arguments).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_cv.py"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"
MALFORMED_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cv.malformed.sample.yaml"
TEMPLATES_DIR = REPO_ROOT / "templates" / "cv"
TEMPLATES = sorted(TEMPLATES_DIR.glob("*.html"))


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _pdf_text(pdf: Path) -> str:
    """Concatenate extracted text across every page of a rendered PDF."""
    return "".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)


def test_photo_renders_across_every_html_template() -> None:
    assert len(TEMPLATES) == 9, (
        f"expected 9 real templates/cv/*.html files, found {len(TEMPLATES)} "
        f"({[t.name for t in TEMPLATES]}) — a template was added/removed without "
        f"updating this sweep's expectations"
    )
    offenders: list[str] = []
    for template in TEMPLATES:
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(CONFIG), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        html_out = out.with_suffix(".html")
        if not html_out.is_file():
            offenders.append(f"{template.name}: no .html sibling produced at {html_out}")
            continue
        html_text = html_out.read_text(encoding="utf-8")
        # Non-empty <img src="..."> — the base64 data URI from candidate_with_embedded_photo().
        if '<img src=""' in html_text or "<img src=''" in html_text:
            offenders.append(f"{template.name}: <img src=\"\"> is empty — photo did not reach rendered output")
            continue
        if "<img" not in html_text or 'src="data:' not in html_text:
            offenders.append(f"{template.name}: no <img src=\"data:...\"> embedded photo found in rendered HTML")
    assert not offenders, "photo missing from rendered HTML output:\n" + "\n".join(offenders)


def test_photo_renders_via_reportlab_backend() -> None:
    out = Path(tempfile.mkdtemp()) / "reportlab.pdf"
    result = _run("--config", str(CONFIG), "--no-template", "--out", str(out))
    assert result.returncode == 0, f"--no-template render must exit 0: {result.stderr}"
    reader = PdfReader(str(out))
    has_image = any(list(page.images) for page in reader.pages)
    assert has_image, (
        "ReportLab (--no-template) render produced no embedded image XObject on any page — "
        "photo_path_for()/RLImage embed path did not actually rasterize an image"
    )


def test_no_leak_across_all_9_templates() -> None:
    assert len(TEMPLATES) == 9, f"expected 9 templates, found {len(TEMPLATES)}"
    offenders: list[str] = []
    for template in TEMPLATES:
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(CONFIG), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        text = _pdf_text(out)
        if "['" in text:
            offenders.append(f"{template.name}: list container-repr (\"['\") leaked into rendered text")
        if "{'" in text:
            offenders.append(f"{template.name}: dict container-repr (\"{{'\") leaked into rendered text")
    assert not offenders, "container-repr leak found:\n" + "\n".join(offenders)


def test_education_languages_certifications_present_where_template_supports_them() -> None:
    offenders: list[str] = []
    checked_any = False
    for template in TEMPLATES:
        html_src = template.read_text(encoding="utf-8")
        # Detect a VISIBLE certifications heading, not just the `candidate.certifications`
        # data-binding (several templates render that data under a "Courses" heading via
        # labels.courses instead — out of scope for this label-presence check).
        has_visible_heading = (
            "labels.certifications" in html_src or ">Certifications<" in html_src
        )
        if not has_visible_heading:
            continue  # this template does not declare a visible certifications heading — not in scope
        checked_any = True
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(CONFIG), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        text_lower = _pdf_text(out).lower()
        for label in ("education", "languages", "certifications"):
            if label not in text_lower:
                offenders.append(f"{template.name}: {label!r} section label missing from extracted PDF text")
    assert checked_any, "no template declared a certifications block — sweep found nothing to check"
    assert not offenders, "section presence check failed:\n" + "\n".join(offenders)


def test_no_repeated_skills_literal_across_all_9_templates_and_reportlab() -> None:
    """D-06 #1 (TMPL-03): the literal 'Skills' fallback must never fire, across all 9
    templates plus the ReportLab (--no-template) path, when fed a draft whose expertise
    blocks entirely lack a resume_title key (the confirmed real-world defect shape)."""
    assert len(TEMPLATES) == 9, f"expected 9 templates, found {len(TEMPLATES)}"
    offenders: list[str] = []
    for template in TEMPLATES:
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(MALFORMED_FIXTURE), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        text = _pdf_text(out)
        if "Skills" in text:
            offenders.append(f"{template.name}: literal 'Skills' fallback leaked into rendered text")
    out = Path(tempfile.mkdtemp()) / "reportlab.pdf"
    result = _run("--config", str(MALFORMED_FIXTURE), "--no-template", "--out", str(out))
    if result.returncode != 0:
        offenders.append(f"--no-template (ReportLab): render exited {result.returncode}: {result.stderr}")
    else:
        text = _pdf_text(out)
        if "Skills" in text:
            offenders.append("--no-template (ReportLab): literal 'Skills' fallback leaked into rendered text")
    assert not offenders, "literal 'Skills' fallback found:\n" + "\n".join(offenders)


def test_languages_section_shows_real_values_when_data_present() -> None:
    """D-06 #2 (TMPL-04): when candidate.yaml has well-formed languages data, every
    actual language value must appear in the rendered output — proving Languages shows
    REAL values, not just "no visible garbage". Matching is case-insensitive since some
    templates render section content in uppercase via CSS text-transform (pypdf extracts
    the literal drawn glyph shapes, not the DOM source casing — same quirk documented in
    test_education_languages_certifications_present_where_template_supports_them).
    Templates whose own HTML source has no `languages` binding at all (e.g. anthony.html,
    confirmed via 03-RESEARCH.md) are out of scope for this check, detected at test time."""
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    languages = raw.get("languages") or []
    assert languages, "config/candidate.yaml has no languages data — nothing to verify"
    expected_values = [entry["language"] for entry in languages if isinstance(entry, dict) and entry.get("language")]
    assert expected_values, "config/candidate.yaml's languages entries have no 'language' values to check"
    expected_lower = [v.lower() for v in expected_values]

    assert len(TEMPLATES) == 9, f"expected 9 templates, found {len(TEMPLATES)}"
    offenders: list[str] = []
    checked_any = False
    for template in TEMPLATES:
        html_src = template.read_text(encoding="utf-8")
        if "languages" not in html_src:
            continue  # this template declares no languages binding at all — not in scope
        checked_any = True
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(CONFIG), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        text_lower = _pdf_text(out).lower()
        for value, value_lower in zip(expected_values, expected_lower):
            if value_lower not in text_lower:
                offenders.append(f"{template.name}: language value {value!r} missing from rendered text")
    assert checked_any, "no template declared a languages binding — sweep found nothing to check"
    out = Path(tempfile.mkdtemp()) / "reportlab.pdf"
    result = _run("--config", str(CONFIG), "--no-template", "--out", str(out))
    if result.returncode != 0:
        offenders.append(f"--no-template (ReportLab): render exited {result.returncode}: {result.stderr}")
    else:
        text_lower = _pdf_text(out).lower()
        for value, value_lower in zip(expected_values, expected_lower):
            if value_lower not in text_lower:
                offenders.append(f"--no-template (ReportLab): language value {value!r} missing from rendered text")
    assert not offenders, "Languages section missing real values:\n" + "\n".join(offenders)


def test_no_lone_dash_line_in_experience_or_languages_with_malformed_data() -> None:
    """D-06 #3 (TMPL-05, plus TMPL-04's char-by-char/prose defect shape): no rendered
    line may consist of nothing but a lone dash glyph, across all 9 templates plus the
    ReportLab (--no-template) path, when fed the malformed fixture (missing
    position/company, and languages emitted as a bare prose string)."""
    assert len(TEMPLATES) == 9, f"expected 9 templates, found {len(TEMPLATES)}"
    lone_dash_glyphs = {"-", "—"}  # "-" and "—"
    offenders: list[str] = []
    for template in TEMPLATES:
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(MALFORMED_FIXTURE), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        text = _pdf_text(out)
        for line in text.splitlines():
            if line.strip() in lone_dash_glyphs:
                offenders.append(f"{template.name}: lone dash glyph line found: {line!r}")
    out = Path(tempfile.mkdtemp()) / "reportlab.pdf"
    result = _run("--config", str(MALFORMED_FIXTURE), "--no-template", "--out", str(out))
    if result.returncode != 0:
        offenders.append(f"--no-template (ReportLab): render exited {result.returncode}: {result.stderr}")
    else:
        text = _pdf_text(out)
        for line in text.splitlines():
            if line.strip() in lone_dash_glyphs:
                offenders.append(f"--no-template (ReportLab): lone dash glyph line found: {line!r}")
    assert not offenders, "lone dash glyph line found:\n" + "\n".join(offenders)


def test_no_language_row_explosion_with_malformed_data() -> None:
    """Closes 03-VERIFICATION.md's gaps[1] / 03-REVIEW.md's WR-03: locks the TMPL-04
    languages-row-explosion defect (03-VERIFICATION.md's gaps[0] / CR-01) with a real
    regression assertion, not just a "no visible garbage" check.

    ``MALFORMED_FIXTURE``'s ``languages`` field is a single 74-character bare prose
    string (see tests/fixtures/cv.malformed.sample.yaml). Before 03-06-PLAN.md's
    ``languages_rows()`` shape-guard + 03-07-PLAN.md's 8 template call-site fixes, every
    template's ``{% for row in candidate.languages %}`` iterated that string
    character-by-character, exploding into 74 empty language-row elements per template
    (confirmed via this task's manual RED-step run against a scratch-reverted guard,
    documented in this plan's SUMMARY.md). Post-fix, ``languages_rows()`` returns ``[]``
    for a non-list input, so the row count must be 0 (comfortably under the bound below).

    Row-count signal is read from each template's rendered ``.html`` sibling (a
    markup-structure property), not from extracted PDF text, per each template's actual
    per-row CSS class marker (RESEARCH.md/PATTERNS.md document these differ per file —
    no single universal marker string exists across all 9 templates):

      * ``class="lang-entry"`` — mark-smith-navy.html, emerald.html
      * ``class="lang-item"`` — baxter.html, enhancv.html
      * plain ``<li>`` (whole-file count; each of these templates' Languages section is
        the file's ONLY ``<li>``-emitting loop over ``candidate.languages``, and the
        outer ``{% if candidate.languages | languages_rows %}`` guard removes the entire
        ``<ul>...</ul>`` block — including its heading — when the guarded list is empty,
        so a small bound is safe without narrowing to a specific block) —
        enhancv-left.html, enhancv-inspired.html, gmj-baseline.html, default.html

    A generous bound of <= 5 is used (0 is the correct post-fix value; 5 comfortably
    allows a few legitimate rows while failing hard on anything proportional to the
    74-character malformed input — RESEARCH.md confirms 74 rows is the actual pre-fix
    explosion count for the class-marker-based templates, and 76 total <li> elements for
    the <ul>-based templates in the RED-step confirmation, both far above this bound).
    """
    assert len(TEMPLATES) == 9, f"expected 9 templates, found {len(TEMPLATES)}"
    row_marker_by_template = {
        "mark-smith-navy.html": 'class="lang-entry"',
        "emerald.html": 'class="lang-entry"',
        "baxter.html": 'class="lang-item"',
        "enhancv.html": 'class="lang-item"',
        "enhancv-left.html": "<li",
        "enhancv-inspired.html": "<li",
        "gmj-baseline.html": "<li",
        "default.html": "<li",
    }
    max_rows = 5
    offenders: list[str] = []
    checked_any = False
    for template in TEMPLATES:
        marker = row_marker_by_template.get(template.name)
        if marker is None:
            continue  # anthony.html — no languages section, correctly out of scope
        checked_any = True
        out = Path(tempfile.mkdtemp()) / f"{template.stem}.pdf"
        result = _run("--config", str(MALFORMED_FIXTURE), "--template", str(template), "--out", str(out))
        if result.returncode != 0:
            offenders.append(f"{template.name}: render exited {result.returncode}: {result.stderr}")
            continue
        html_out = out.with_suffix(".html")
        if not html_out.is_file():
            offenders.append(f"{template.name}: no .html sibling produced at {html_out}")
            continue
        html_text = html_out.read_text(encoding="utf-8")
        row_count = html_text.count(marker)
        if row_count > max_rows:
            offenders.append(
                f"{template.name}: {row_count} language-row-shaped elements ({marker!r}) "
                f"found (bound is <= {max_rows}) — likely a bare-string languages "
                f"character-explosion regression"
            )
    assert checked_any, "no template had a known row marker — sweep found nothing to check"

    # ReportLab (--no-template) path: mirrors 03-06-PLAN.md's fix — the "Languages"
    # heading itself must be entirely absent (not merely "no rows under it"), since the
    # heading is gated on the guarded list being non-empty.
    out = Path(tempfile.mkdtemp()) / "reportlab.pdf"
    result = _run("--config", str(MALFORMED_FIXTURE), "--no-template", "--out", str(out))
    if result.returncode != 0:
        offenders.append(f"--no-template (ReportLab): render exited {result.returncode}: {result.stderr}")
    else:
        text = _pdf_text(out)
        if "Languages" in text:
            offenders.append(
                "--no-template (ReportLab): 'Languages' heading present despite malformed "
                "(bare-string) languages input — heading must be gated on languages_rows()"
            )
    assert not offenders, "language-row-explosion regression found:\n" + "\n".join(offenders)


def test_certifications_bullet_uses_self_correcting_pseudo_element() -> None:
    """02-UAT.md gap 5: baxter.html's Certifications bullet must use the same
    self-correcting ::before pseudo-element pattern already proven for
    .job-bullets li::before, not the shared .entry-bullet fixed-margin-top nudge
    (which does not reliably center against Certifications' variable-length/
    wrapping title text). Education's own .entry-bullet markup must be untouched —
    this is a Certifications-only scoped fix per 02-UAT.md's root-cause diagnosis."""
    baxter = TEMPLATES_DIR / "baxter.html"
    src = baxter.read_text(encoding="utf-8")
    start = src.index("<!-- CERTIFICATIONS -->")
    # Find this block's matching {% endfor %} (the one closing the certifications loop,
    # i.e. the next endfor after the for-loop that immediately follows the comment).
    loop_start = src.index("{% for cert in candidate.certifications %}", start)
    end = src.index("{% endfor %}", loop_start) + len("{% endfor %}")
    cert_block = src[start:end]
    assert 'class="entry-bullet"' not in cert_block, (
        "Certifications markup still references the shared fixed-nudge .entry-bullet "
        "span — the self-correcting ::before replacement was not actually wired in"
    )
    assert "cert-entry-title" in cert_block, (
        "Certifications markup does not reference a new self-correcting bullet class"
    )
    # The new class's ::before rule must be defined in the <style> block (not just
    # referenced in markup) — grep the stylesheet region specifically.
    style_start = src.index("<style")
    style_end = src.index("</style>")
    style_block = src[style_start:style_end]
    assert ".cert-entry-title::before" in style_block, (
        "No ::before rule defined for the new Certifications bullet class in <style>"
    )
    # Education's own entry-bullet/entry-name-row markup must remain untouched.
    edu_start = src.index("<!-- EDUCATION -->")
    edu_end = src.index("<!-- LANGUAGES -->")
    edu_block = src[edu_start:edu_end]
    assert 'class="entry-bullet"' in edu_block, (
        "Education's own entry-bullet markup was unexpectedly removed/changed"
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
