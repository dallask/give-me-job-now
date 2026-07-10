#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_check_render_quality.py (QA-02/QA-03).

Proves all three QA-02 defect-detection paths fire independently (missing sections,
clipped content, empty/overlapping regions), the QA-01/QA-03 advisory exit-0-always
contract, traceback-free rejection of a corrupt PDF / missing path, a real
``gmj_render_cv.py --no-template``-rendered PDF fixture in both ``en`` and ``ua``
(Cyrillic round-trip), and a regression guard proving ``gmj_check_delivery.py`` was
never wired to this script's result (QA-01: this check stays advisory-only).

QA-01 (the written hard-vs-advisory decision) and QA-04 (the local ``file://``
Playwright smoke test) are both satisfied by ``51-CONTEXT.md`` itself, not by this
test file — see that document's Detection Mechanism section for the QA-04 finding.

No pytest — run with ``python3 tests/test_check_render_quality.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_render_quality.py"
RENDER_SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_cv.py"
DELIVERY_SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_delivery.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
from gmj_check_render_quality import (  # noqa: E402
    find_clipped_content,
    find_empty_and_overlapping,
    find_missing_sections,
)

import fitz  # noqa: E402  PyMuPDF — used to build synthetic geometry fixtures

# gmj_render_cv.py's repo_root_from_config() walks UP from the config path looking for
# CLAUDE.md/.claude/ to locate config/i18n/labels.yaml; a fixture config living outside the
# repo tree would silently fall back to English labels regardless of --lang (a real, separate
# renderer behavior, not a QA-script bug). Fixture tempdirs must therefore live INSIDE the
# repo tree -- output/cv/ is the existing gitignored-contents convention (see .gitignore).
_FIXTURE_ROOT = REPO_ROOT / "output" / "cv"


def _mkfixturedir() -> Path:
    _FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=str(_FIXTURE_ROOT)))


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


# Minimal fixture exercising the renderer's real section-emitting branches.
# certifications / independent_projects are deliberately OMITTED: their absence is a
# legitimate "candidate has no such section" case, not a defect.
_FIXTURE_CANDIDATE = {
    "name": "Test Candidate",
    "title": "Software Engineer",
    "summary": "A short professional summary for QA fixture purposes.",
    "expertise": [
        {"resume_title": "Core Skills", "skills": ["Python", "Testing", "PDF rendering"]},
    ],
    "languages": [
        {"language": "English", "proficiency": "Fluent"},
    ],
    "professional_experience": [
        {
            "company": "Acme Corp",
            "position": "Engineer",
            "location": "Remote",
            "duration": "2020-2024",
            "achievements": ["Shipped a thing", "Fixed a bug"],
        },
    ],
    "education": [
        {"program": "BSc Computer Science", "institution": "Test University", "duration": "2016-2020"},
    ],
}

_FIXTURE_CANDIDATE_UA = {
    **_FIXTURE_CANDIDATE,
    "name": "Тестовий Кандидат",
    "summary": "Короткий професійний підсумок для фікстури QA.",
}


def _render_fixture(candidate: dict, out_pdf: Path, lang: str = "en") -> None:
    """Write ``candidate`` to a tempfile and render it via the real ship path."""
    fixture_yaml = out_pdf.parent / f"fixture-{lang}.yaml"
    fixture_yaml.write_text(yaml.safe_dump(candidate, allow_unicode=True), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable, str(RENDER_SCRIPT),
            "--config", str(fixture_yaml),
            "--no-template",
            "--lang", lang,
            "--out", str(out_pdf),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"fixture render failed: {result.stderr}"
    assert out_pdf.is_file(), f"fixture render produced no PDF: {out_pdf}"


def test_missing_section_detected_when_label_absent_from_pdf_text() -> None:
    # Part A: CLI, real render, zero false positives on the happy-path fixture.
    tmpdir = _mkfixturedir()
    fixture_yaml = tmpdir / "fixture.yaml"
    fixture_yaml.write_text(yaml.safe_dump(_FIXTURE_CANDIDATE), encoding="utf-8")
    out_pdf = tmpdir / "fixture.pdf"
    _render_fixture(_FIXTURE_CANDIDATE, out_pdf, lang="en")

    result = _run("--pdf", str(out_pdf), "--candidate-yaml", str(fixture_yaml), "--lang", "en")
    assert result.returncode == 0, f"QA script must exit 0: {result.stderr}"
    lines = result.stdout.splitlines()
    assert lines[0] == "defects: 0", f"expected no false positives, got: {result.stdout}"
    assert "missing_section" not in result.stdout

    # Part B: unit-level, genuine miss — call find_missing_sections() directly.
    candidate = {"professional_experience": [{"company": "X"}]}
    labels = {"experience": "Experience"}
    defects = find_missing_sections(candidate, labels, rendered_text="this text has no such heading")
    assert len(defects) == 1, defects
    assert defects[0]["type"] == "missing_section"
    assert defects[0]["key"] == "professional_experience"


def test_clipped_content_detected_via_bbox_vs_cropbox() -> None:
    tmpdir = _mkfixturedir()
    pdf_path = tmpdir / "clip.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        # Safe span well inside the cropbox.
        page.insert_text((20, 20), "safe text")
        # Span positioned so its glyphs extend past the page's right/bottom edge --
        # PyMuPDF drops glyphs placed entirely off-page from the content stream, so the
        # origin must sit near the edge (not far off-page) for a genuinely out-of-bounds
        # span bbox to appear in get_text("dict").
        page.insert_text((195, 195), "overflowing content well past the edge", fontsize=24)
        doc.save(str(pdf_path))
    finally:
        doc.close()

    doc = fitz.open(str(pdf_path))
    try:
        defects = find_clipped_content(doc, tolerance=3.0)
        assert any(d["type"] == "clipped_content" for d in defects), defects
    finally:
        doc.close()

    # Safe-only document: no clipped_content defect.
    pdf_path_safe = tmpdir / "safe.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 20), "safe text only")
        doc.save(str(pdf_path_safe))
    finally:
        doc.close()

    doc = fitz.open(str(pdf_path_safe))
    try:
        defects = find_clipped_content(doc, tolerance=3.0)
        assert defects == [], defects
    finally:
        doc.close()


def test_empty_page_and_overlapping_regions_detected() -> None:
    tmpdir = _mkfixturedir()

    # Empty page: a document with a page holding no text at all.
    pdf_empty = tmpdir / "empty.pdf"
    doc = fitz.open()
    try:
        doc.new_page(width=200, height=200)
        doc.save(str(pdf_empty))
    finally:
        doc.close()

    doc = fitz.open(str(pdf_empty))
    try:
        defects = find_empty_and_overlapping(doc, tolerance=3.0)
        assert any(d["type"] == "empty_page" for d in defects), defects
    finally:
        doc.close()

    # Overlapping blocks: PyMuPDF's own text-extraction layout analysis coalesces two
    # same-page insertions into a SINGLE block whenever they visually overlap (verified
    # empirically), so overlapping block-level geometry can never be reproduced through a
    # real insert_text()/insert_textbox() PDF fixture. Exercise the geometry logic directly
    # against a minimal fake fitz.Document-shaped object instead (get_text("dict") is the
    # only fitz.Page API find_empty_and_overlapping() calls).
    class _FakePage:
        def __init__(self, blocks: list[dict]) -> None:
            self._blocks = blocks

        def get_text(self, _mode: str) -> dict:
            return {"blocks": self._blocks}

    class _FakeDoc:
        def __init__(self, pages: list[_FakePage]) -> None:
            self._pages = pages
            self.page_count = len(pages)

        def __getitem__(self, index: int) -> _FakePage:
            return self._pages[index]

    def _fake_block(bbox: tuple[float, float, float, float], text: str) -> dict:
        return {"bbox": bbox, "lines": [{"spans": [{"bbox": bbox, "text": text}]}]}

    overlap_doc = _FakeDoc(
        [
            _FakePage(
                [
                    _fake_block((20.0, 20.0, 100.0, 60.0), "block one text here"),
                    _fake_block((30.0, 25.0, 110.0, 65.0), "block two text here"),
                ]
            )
        ]
    )
    defects = find_empty_and_overlapping(overlap_doc, tolerance=3.0)
    overlap_defects = [d for d in defects if d["type"] == "overlapping_regions"]
    assert overlap_defects, defects

    # Non-overlapping blocks: two far-apart insertions -> no overlap defect.
    pdf_clean = tmpdir / "clean.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=400, height=400)
        page.insert_text((20, 20), "top left block")
        page.insert_text((20, 350), "bottom left block")
        doc.save(str(pdf_clean))
    finally:
        doc.close()

    doc = fitz.open(str(pdf_clean))
    try:
        defects = find_empty_and_overlapping(doc, tolerance=3.0)
        overlap_defects = [d for d in defects if d["type"] == "overlapping_regions"]
        assert overlap_defects == [], defects
    finally:
        doc.close()


def test_missing_sections_fires_independently_of_clipping_pitfall_1() -> None:
    """RESEARCH.md Pitfall 1 regression lock: a missing_section defect must fire even
    when the geometry-based checks (clipping/empty/overlap) report completely clean —
    mirroring Phase 41's actual bug (content simply absent from the text layer, zero
    out-of-bounds spans)."""
    tmpdir = _mkfixturedir()
    pdf_clean = tmpdir / "clean_geometry.pdf"
    doc = fitz.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 20), "Just a summary, nothing else.")
        doc.save(str(pdf_clean))
    finally:
        doc.close()

    doc = fitz.open(str(pdf_clean))
    try:
        clip_defects = find_clipped_content(doc, tolerance=3.0)
        geom_defects = find_empty_and_overlapping(doc, tolerance=3.0)
        full_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()

    assert clip_defects == [], clip_defects
    assert geom_defects == [], geom_defects

    candidate = {"education": [{"program": "BSc"}]}
    labels = {"education": "Education"}
    missing_defects = find_missing_sections(candidate, labels, rendered_text=full_text)
    assert len(missing_defects) == 1, missing_defects
    assert missing_defects[0]["type"] == "missing_section"


def test_successful_run_always_exits_0_regardless_of_defect_count() -> None:
    tmpdir = _mkfixturedir()
    fixture_yaml = tmpdir / "fixture.yaml"
    fixture_yaml.write_text(yaml.safe_dump(_FIXTURE_CANDIDATE), encoding="utf-8")
    out_pdf = tmpdir / "fixture.pdf"
    _render_fixture(_FIXTURE_CANDIDATE, out_pdf, lang="en")

    # Engineer a candidate YAML that will report at least one missing_section defect:
    # add a certifications entry the real render (from the ORIGINAL fixture) never emitted.
    engineered_yaml = tmpdir / "engineered.yaml"
    engineered_candidate = dict(_FIXTURE_CANDIDATE)
    engineered_candidate["certifications"] = [{"issuer": "Nonexistent Cert Body", "year": 2099}]
    engineered_yaml.write_text(yaml.safe_dump(engineered_candidate), encoding="utf-8")

    result = _run("--pdf", str(out_pdf), "--candidate-yaml", str(engineered_yaml), "--lang", "en")
    assert result.returncode == 0, f"advisory check must always exit 0: {result.stderr}"
    lines = result.stdout.splitlines()
    assert lines[0].startswith("defects: "), result.stdout
    count = int(lines[0].split(":", 1)[1].strip())
    assert count >= 1, f"expected at least one defect, got: {result.stdout}"


def test_corrupt_pdf_rejected_no_traceback() -> None:
    tmpdir = _mkfixturedir()
    bad_pdf = tmpdir / "corrupt.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4\ncorrupt garbage not a real pdf")

    candidate_yaml = REPO_ROOT / "config" / "candidate.yaml"
    result = _run("--pdf", str(bad_pdf), "--candidate-yaml", str(candidate_yaml), "--lang", "en")
    assert result.returncode == 1, result.stdout
    assert result.stderr.strip(), "expected a stderr message"
    assert "Traceback" not in result.stderr, result.stderr


def test_missing_pdf_path_rejected_no_traceback() -> None:
    tmpdir = _mkfixturedir()
    missing_pdf = tmpdir / "nonexistent.pdf"
    candidate_yaml = REPO_ROOT / "config" / "candidate.yaml"

    result = _run("--pdf", str(missing_pdf), "--candidate-yaml", str(candidate_yaml), "--lang", "en")
    assert result.returncode == 1, result.stdout
    assert "Not a file:" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr


def test_cyrillic_lang_labels_detected_pitfall_3() -> None:
    tmpdir = _mkfixturedir()
    fixture_yaml = tmpdir / "fixture_ua.yaml"
    fixture_yaml.write_text(yaml.safe_dump(_FIXTURE_CANDIDATE_UA, allow_unicode=True), encoding="utf-8")
    out_pdf = tmpdir / "fixture_ua.pdf"
    _render_fixture(_FIXTURE_CANDIDATE_UA, out_pdf, lang="ua")

    result = _run("--pdf", str(out_pdf), "--candidate-yaml", str(fixture_yaml), "--lang", "ua")
    assert result.returncode == 0, f"QA script must exit 0: {result.stderr}"
    lines = result.stdout.splitlines()
    assert lines[0] == "defects: 0", (
        f"expected no false-positive missing_section for Cyrillic labels, got: {result.stdout}"
    )


def test_gmj_check_delivery_untouched_regression() -> None:
    """QA-01 regression guard: gmj_check_delivery.py must never reference this new
    script's module name — the QA pass stays advisory-only, never a wired hard gate."""
    source = DELIVERY_SCRIPT.read_text(encoding="utf-8")
    assert "gmj_check_render_quality" not in source, (
        "gmj_check_delivery.py must not reference gmj_check_render_quality (QA-01 advisory-only)"
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
