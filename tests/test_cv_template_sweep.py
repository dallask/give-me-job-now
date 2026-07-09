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

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_cv.py"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"
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
