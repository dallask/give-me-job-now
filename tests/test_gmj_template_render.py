#!/usr/bin/env python3
"""Plain-python3 render gate for templates/cv/gmj-baseline.html (TEMPLATE-01/05/06).

Proves the canonical branded baseline template is production-safe on the three axes the
13-UI-SPEC print contract makes load-bearing:

  * ``test_by_name_render_en`` — render the template BY NAME (``--template
    templates/cv/gmj-baseline.html``) and assert a real ``%PDF-`` with >= 1 page. This is
    the TEMPLATE-06 by-name-render guarantee: a stored slug under ``templates/cv/`` is a
    first-class renderable option with no per-template wiring.
  * ``test_cyrillic_glyphs_ua`` / ``test_cyrillic_glyphs_ru`` — render ``--lang ua`` / ``ru``
    and assert the extracted PDF text carries Cyrillic glyphs ABOVE a fixed threshold. A
    high count can only come from DejaVu actually resolving (via the template's explicit
    repo-relative ``@font-face`` + the render base_url); a fallback font would drop the
    Cyrillic and collapse the count (TEMPLATE-05 portable-Cyrillic contract).
  * ``test_longer_than_sample_no_overflow`` — render the longer-than-sample Ukrainian CV
    (``config/candidate.yaml`` + ``--lang ua`` merges the longer ``candidate.ua.yaml``
    overlay) and assert it reflows across multiple pages with NO render error, and that
    every top-level schema section that has data still renders its heading (no silent
    section drop from an over-fit layout). This is the TEMPLATE-05 reflow-not-clip guard.

PDF validity is asserted STRUCTURALLY (``%PDF-`` magic + ``pypdf`` page count), never by
byte-hash — WeasyPrint embeds timestamps so the bytes are not reproducible across runs.
Section-heading probes use casefold matching because the template ``text-transform:
uppercase`` bakes uppercase glyphs into the PDF text layer.

No pytest — run with ``python3 tests/test_gmj_template_render.py``.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "render_cv.py"
TEMPLATE = REPO_ROOT / "templates" / "cv" / "gmj-baseline.html"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"
UA_OVERLAY = REPO_ROOT / "config" / "candidate.ua.yaml"
LABELS = REPO_ROOT / "config" / "i18n" / "labels.yaml"

# Cyrillic Unicode block (U+0400–U+04FF) + supplement; a healthy ua/ru render is deep into
# the thousands, so a threshold of 100 cleanly separates "DejaVu resolved" from a
# labels-only or fallback-font degradation.
_CYRILLIC = re.compile(r"[Ѐ-ӿԀ-ԯ]")
_CYRILLIC_MIN = 100


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def assert_valid_pdf(path: Path) -> None:
    """Structural PDF-validity assertion — never byte-hash (timestamps vary)."""
    assert path.is_file(), f"missing PDF: {path}"
    with path.open("rb") as fh:
        assert fh.read(5) == b"%PDF-", "not a PDF (bad magic bytes)"
    assert len(PdfReader(str(path)).pages) >= 1, "PDF has no pages"


def _pdf_text(pdf: Path) -> str:
    """Concatenate extracted text across every page of a rendered PDF."""
    return "".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)


def _cyrillic_count(text: str) -> int:
    return len(_CYRILLIC.findall(text))


def _labels(lang: str) -> dict:
    data = yaml.safe_load(LABELS.read_text(encoding="utf-8")) or {}
    return data.get(lang) or {}


def test_by_name_render_en() -> None:
    out = Path(tempfile.mkdtemp()) / "gmj-en.pdf"
    result = _run("--config", str(CONFIG), "--template", str(TEMPLATE), "--out", str(out))
    assert result.returncode == 0, f"by-name en render must exit 0: {result.stderr}"
    assert "Traceback" not in result.stderr, f"no traceback expected: {result.stderr}"
    assert_valid_pdf(out)


def test_cyrillic_glyphs_ua() -> None:
    out = Path(tempfile.mkdtemp()) / "gmj-ua.pdf"
    result = _run("--config", str(CONFIG), "--lang", "ua", "--template", str(TEMPLATE), "--out", str(out))
    assert result.returncode == 0, f"ua render must exit 0: {result.stderr}"
    assert_valid_pdf(out)
    text = _pdf_text(out)
    count = _cyrillic_count(text)
    assert count > _CYRILLIC_MIN, (
        f"ua render carries only {count} Cyrillic glyphs (<= {_CYRILLIC_MIN}) — DejaVu did "
        f"not resolve via @font-face; Cyrillic is being dropped to a fallback font"
    )


def test_cyrillic_glyphs_ru() -> None:
    out = Path(tempfile.mkdtemp()) / "gmj-ru.pdf"
    result = _run("--config", str(CONFIG), "--lang", "ru", "--template", str(TEMPLATE), "--out", str(out))
    assert result.returncode == 0, f"ru render must exit 0: {result.stderr}"
    assert_valid_pdf(out)
    count = _cyrillic_count(_pdf_text(out))
    assert count > _CYRILLIC_MIN, (
        f"ru render carries only {count} Cyrillic glyphs (<= {_CYRILLIC_MIN}) — DejaVu did "
        f"not resolve via @font-face"
    )


def _emoji_codepoints(text: str) -> list[str]:
    """Code points DejaVu Sans has NO glyph for — emoji / pictographs / dingbats.

    DejaVu ships zero glyphs across these ranges, so any such code point in the PDF text
    layer can only rasterize via a per-machine system emoji font (Apple Color Emoji, Noto
    Color Emoji, or tofu on a bare CI box). Emitting one reintroduces exactly the fontconfig
    nondeterminism the template's @font-face doctrine exists to kill.
    """
    ranges = (
        (0x2600, 0x27BF),    # Misc symbols + Dingbats (⚡ ❤ ⭐-adjacent, ✨ ✅)
        (0x2B00, 0x2BFF),    # Misc symbols and arrows (⭐ U+2B50)
        (0x1F000, 0x1FAFF),  # Emoji, pictographs, supplemental symbols (💡 🤖 🏆 🚀 …)
        (0xFE00, 0xFE0F),    # Variation selectors (emoji-presentation VS16)
    )
    return sorted({c for c in text if any(lo <= ord(c) <= hi for lo, hi in ranges)})


def test_achievements_icons_emit_no_emoji_codepoints() -> None:
    """Determinism guard (TEMPLATE-05): an achievements CV must emit ZERO emoji code points.

    The live ``config/candidate.yaml`` seeds ``key_achievements[].icon`` with real emoji
    (🤖 ✨ 🏆 ⚡ 📈 🚀 ✅). DejaVu — the only @font-face-pinned family — has no glyph for any of
    them, so if the template routed a raw emoji into the layout it would fall back to a
    host-specific system emoji font and the rasterized sidebar (hence the visual-diff ratio)
    would become machine-dependent, silently breaking the ≤0.10 compare==ship bar across
    machines. The template renders a repo-local inline SVG star marker instead, so no emoji
    code point must reach the PDF text/layout layer — while the achievement CONTENT is still
    rendered.
    """
    # Guard the guard: the sample data must actually contain emoji, else this test is hollow.
    base = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    achievements = base.get("key_achievements") or []
    seeded_icons = [a.get("icon") for a in achievements if a.get("icon")]
    seeded_emoji = [ic for ic in seeded_icons if _emoji_codepoints(ic)]
    assert seeded_emoji, (
        "fixture drift: config/candidate.yaml key_achievements no longer carry emoji icons — "
        "this determinism test can no longer prove the emoji are dropped from the layout"
    )

    out = Path(tempfile.mkdtemp()) / "gmj-ach.pdf"
    result = _run("--config", str(CONFIG), "--template", str(TEMPLATE), "--out", str(out))
    assert result.returncode == 0, f"achievements render must exit 0: {result.stderr}"
    assert_valid_pdf(out)

    text = _pdf_text(out)
    leaked = _emoji_codepoints(text)
    assert not leaked, (
        f"rendered PDF emits emoji/pictograph code points {[hex(ord(c)) for c in leaked]} "
        f"which DejaVu cannot render — they fall back to a per-machine system emoji font, "
        f"reintroducing cross-machine nondeterminism into the visual diff"
    )

    # Content must survive the icon substitution: the achievement titles still render.
    folded = re.sub(r"\s+", "", text).casefold()
    for item in achievements:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        assert re.sub(r"\s+", "", title).casefold() in folded, (
            f"achievement {title!r} is absent from the rendered PDF — dropping the emoji "
            f"icon must not drop the achievement content"
        )


def test_longer_than_sample_no_overflow() -> None:
    # candidate.yaml + --lang ua deep-merges the longer-than-sample Ukrainian overlay
    # (config/candidate.ua.yaml) over the English base — the longest CV variant. It must
    # reflow across pages, never clip, and never silently drop a populated section.
    out = Path(tempfile.mkdtemp()) / "gmj-ua-long.pdf"
    result = _run("--config", str(CONFIG), "--lang", "ua", "--template", str(TEMPLATE), "--out", str(out))
    assert result.returncode == 0, f"longer-than-sample ua render must exit 0: {result.stderr}"
    assert "Traceback" not in result.stderr, f"no render error expected: {result.stderr}"
    assert_valid_pdf(out)

    reader = PdfReader(str(out))
    # Multi-page reflow is the actual invariant this test exists to prove: the
    # longer-than-sample merged ua CV must spill onto a SECOND page rather than clip
    # content into a single over-fit page. A `>= 1` assertion is vacuous here (already
    # guaranteed by assert_valid_pdf), so a silent single-page clip would pass. Require
    # the real property.
    assert len(reader.pages) >= 2, (
        f"longest CV must reflow onto a second page, not clip — got "
        f"{len(reader.pages)} page(s)"
    )

    def _norm(s: str) -> str:
        # Whitespace-insensitive + case-insensitive: section titles are
        # text-transform:uppercase in the PDF text layer AND the narrow sidebar wraps
        # multi-word headings across a newline (КЛЮЧОВІ\nДОСЯГНЕННЯ), so collapse all
        # whitespace before comparing.
        return re.sub(r"\s+", "", s).casefold()

    text = _pdf_text(out)
    folded = _norm(text)

    # Every top-level schema section that has data in the merged ua candidate MUST render
    # its heading — proving no over-fit layout silently dropped a section.
    base = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    overlay = yaml.safe_load(UA_OVERLAY.read_text(encoding="utf-8")) or {}
    merged = {**base, **overlay}
    lab = _labels("ua")

    # (top-level key -> label key used by the template heading for that section)
    section_label = {
        "summary": "summary",
        "professional_experience": "experience",
        "education": "education",
        "independent_projects": "projects",
        "languages": "languages",
        "key_achievements": "key_achievements",
        "expertise": "expertise",
        "certifications": "courses",
    }
    for top_key, label_key in section_label.items():
        if not merged.get(top_key):
            continue
        heading = lab.get(label_key)
        assert heading, f"labels.ua missing {label_key!r} — cannot verify section render"
        assert _norm(heading) in folded, (
            f"section {top_key!r} has data but its heading {heading!r} is absent from the "
            f"rendered PDF — the longer-than-sample layout dropped/clipped a section"
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
