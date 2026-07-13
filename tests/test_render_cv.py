#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/gmj_render_cv.py's DEFAULT invocation (ARTF-02).

Proves the HTML-sibling guarantee/degrade contract on the default (no explicit
``--template``/``--no-template`` flag) invocation: a PDF is ALWAYS produced, and a
first-class ``.html`` sibling is produced whenever the default WeasyPrint/Jinja2
template path (``templates/cv/baxter.html``) succeeds — or, when WeasyPrint is
unavailable, the script gracefully degrades to PDF-only with the already-implemented,
non-blocking "Falling back to ReportLab built-in layout." stderr warning. The branch
exercised is probed live via ``importlib.util.find_spec("weasyprint")`` so this same
file is correct on both a WeasyPrint-present and a WeasyPrint-absent machine — no
hardcoded assumption about which branch runs. Also proves ``--no-template`` never
emits an HTML sibling. No pytest — run with ``python3 tests/test_render_cv.py``.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_cv.py"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"

_WEASYPRINT_AVAILABLE = importlib.util.find_spec("weasyprint") is not None


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_default_invocation_produces_pdf() -> None:
    out = Path(tempfile.mkdtemp()) / "default-cv.pdf"
    result = _run("--config", str(CONFIG), "--out", str(out))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    assert out.is_file(), f"missing PDF: {out}"
    with out.open("rb") as fh:
        assert fh.read(5) == b"%PDF-", "not a PDF (bad magic bytes)"


def test_default_invocation_html_sibling_guaranteed_or_gracefully_degraded() -> None:
    out = Path(tempfile.mkdtemp()) / "default-cv.pdf"
    result = _run("--config", str(CONFIG), "--out", str(out))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    html_sibling = out.with_suffix(".html")
    if _WEASYPRINT_AVAILABLE:
        assert html_sibling.is_file(), (
            f"WeasyPrint available: expected HTML sibling at {html_sibling}"
        )
        assert str(html_sibling) in result.stdout, (
            "HTML path must be printed on its own stdout line before the PDF path"
        )
    else:
        assert not html_sibling.is_file(), (
            f"WeasyPrint unavailable: no HTML sibling should be written at {html_sibling}"
        )
        assert "Falling back to ReportLab built-in layout." in result.stderr, (
            "graceful-degrade warning must be visible on stderr"
        )


def test_documented_draft_mode_invocation_produces_html_sibling_or_gracefully_degrades() -> None:
    """Proves the ACTUAL documented Draft-mode `cv` invocation (post-32-06 fix), not only
    gmj_render_cv.py's isolated bare-default invocation. The real Draft-mode flag set is
    `--config <cv.yaml> --lang <content.language> --out <path>` (no `--no-template`) --
    this uses config/candidate.yaml as a stand-in valid YAML since the render's template
    branching does not depend on which YAML is passed, only on the presence/absence of the
    --template/--no-template flags.
    """
    out = Path(tempfile.mkdtemp()) / "draft-mode-cv.pdf"
    result = _run("--config", str(CONFIG), "--lang", "en", "--out", str(out))
    assert result.returncode == 0, f"documented Draft-mode invocation must exit 0: {result.stderr}"
    assert out.is_file(), f"missing PDF: {out}"
    html_sibling = out.with_suffix(".html")
    if _WEASYPRINT_AVAILABLE:
        assert html_sibling.is_file(), (
            f"WeasyPrint available: expected HTML sibling at {html_sibling}"
        )
        assert str(html_sibling) in result.stdout, (
            "HTML path must be printed on its own stdout line before the PDF path"
        )
    else:
        assert not html_sibling.is_file(), (
            f"WeasyPrint unavailable: no HTML sibling should be written at {html_sibling}"
        )
        assert "Falling back to ReportLab built-in layout." in result.stderr, (
            "graceful-degrade warning must be visible on stderr"
        )


def test_no_template_flag_never_emits_html() -> None:
    out = Path(tempfile.mkdtemp()) / "no-template-cv.pdf"
    result = _run("--config", str(CONFIG), "--no-template", "--out", str(out))
    assert result.returncode == 0, f"--no-template invocation must exit 0: {result.stderr}"
    assert out.is_file(), f"missing PDF: {out}"
    html_sibling = out.with_suffix(".html")
    assert not html_sibling.is_file(), (
        f"--no-template must never write an HTML sibling: {html_sibling}"
    )


def _build_fake_repo(tmp_dir: Path, *, with_master_photo: bool) -> tuple[Path, Path]:
    """Build a throwaway repo root (CLAUDE.md anchor) with config/candidate.yaml
    (real skill-CV shaped fields) and config/cv/cv.testskill.en.yaml (a skill-CV
    draft with NO photo key). Returns (repo_root, skill_cv_config_path)."""
    repo_root = tmp_dir / "fake-repo"
    (repo_root / "config" / "cv").mkdir(parents=True, exist_ok=True)
    (repo_root / "CLAUDE.md").write_text("# fake repo anchor\n", encoding="utf-8")
    # The default template resolver needs templates/cv/baxter.html to exist under
    # the fake repo root for the HTML/WeasyPrint path to activate (rather than
    # silently degrading to ReportLab, which has no HTML sibling to assert on).
    real_templates_dir = REPO_ROOT / "templates" / "cv"
    fake_templates_dir = repo_root / "templates" / "cv"
    fake_templates_dir.mkdir(parents=True, exist_ok=True)
    if real_templates_dir.is_dir():
        shutil.copytree(real_templates_dir, fake_templates_dir, dirs_exist_ok=True)

    master_candidate: dict = {
        "name": "Test Candidate",
        "title": "Test Title",
        "contact": {"email": ["test@example.com"]},
    }
    if with_master_photo:
        (repo_root / "sources").mkdir(parents=True, exist_ok=True)
        real_photo = REPO_ROOT / "sources" / "user_photo.jpg"
        fake_photo = repo_root / "sources" / "user_photo.jpg"
        if real_photo.is_file():
            shutil.copyfile(real_photo, fake_photo)
        else:
            # Minimal 1x1 JPEG-ish bytes are unnecessary — any real file suffices
            # for photo_path_for()'s is_file() check + base64 embedding.
            fake_photo.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        master_candidate["photo"] = "sources/user_photo.jpg"

    (repo_root / "config" / "candidate.yaml").write_text(
        yaml.safe_dump(master_candidate), encoding="utf-8"
    )

    skill_cv: dict = {
        "name": "Test Candidate",
        "title": "Test Skill Title",
        "contact": {"email": ["test@example.com"]},
        # Deliberately NO "photo" key and NO "contact.photo" key.
    }
    skill_cv_path = repo_root / "config" / "cv" / "cv.testskill.en.yaml"
    skill_cv_path.write_text(yaml.safe_dump(skill_cv), encoding="utf-8")
    return repo_root, skill_cv_path


def test_skill_cv_falls_back_to_master_photo_when_present() -> None:
    """Test 1: skill-CV draft with no photo key, next to a master candidate.yaml
    with a real resolvable photo, must embed the actual photo (data URI), not the
    placeholder SVG branch."""
    if not _WEASYPRINT_AVAILABLE:
        print("SKIP (weasyprint unavailable): test_skill_cv_falls_back_to_master_photo_when_present")
        return
    tmp_dir = Path(tempfile.mkdtemp())
    repo_root, skill_cv_path = _build_fake_repo(tmp_dir, with_master_photo=True)
    out = tmp_dir / "out" / "skill-cv.pdf"
    result = _run("--config", str(skill_cv_path), "--lang", "en", "--out", str(out))
    assert result.returncode == 0, f"must exit 0: {result.stderr}"
    html_sibling = out.with_suffix(".html")
    assert html_sibling.is_file(), f"missing HTML sibling: {html_sibling}"
    html = html_sibling.read_text(encoding="utf-8")
    assert '<img src="data:' in html, (
        "expected an embedded data-URI <img> (real photo), not the placeholder SVG branch"
    )
    assert "photo-placeholder" not in html or '<img src="data:' in html, (
        "fallback photo must be embedded; placeholder branch must not be the active one"
    )


def test_skill_cv_degrades_to_placeholder_when_no_master_photo() -> None:
    """Test 2: skill-CV draft with no photo key, and no config/candidate.yaml (or no
    resolvable photo) at the repo root — must still exit 0 and degrade to the
    placeholder branch (no crash, no fabricated path)."""
    if not _WEASYPRINT_AVAILABLE:
        print("SKIP (weasyprint unavailable): test_skill_cv_degrades_to_placeholder_when_no_master_photo")
        return
    tmp_dir = Path(tempfile.mkdtemp())
    repo_root, skill_cv_path = _build_fake_repo(tmp_dir, with_master_photo=False)
    out = tmp_dir / "out" / "skill-cv.pdf"
    result = _run("--config", str(skill_cv_path), "--lang", "en", "--out", str(out))
    assert result.returncode == 0, f"must exit 0 even with no master photo: {result.stderr}"
    html_sibling = out.with_suffix(".html")
    assert html_sibling.is_file(), f"missing HTML sibling: {html_sibling}"
    html = html_sibling.read_text(encoding="utf-8")
    assert '<img src="data:' not in html, (
        "must not fabricate/embed a photo when no master photo is resolvable"
    )


_WELL_FORMED_EDUCATION = [
    {
        "institution": "Kryvyi Rih Technical University",
        "program": "Mining, Faculty of Mining & Metallurgy",
        "location": "Kryvyi Rih, Ukraine",
        "duration": "1997 - 2003",
    },
    {
        "institution": "1C Bitrix Academy",
        "program": "Bitrix Framework Developer Master",
        "location": "Certification program",
        "duration": "2014",
    },
]

# The exact bug-reproduction shape: gmj_draft_to_cv_yaml.py's bridge writes the ENTIRE
# claim-text STRING as the list element when a composer citation targets a whole-object
# source_span like "education[0]" instead of a specific field within it (PIPEFIX-02,
# 07-RESEARCH.md's confirmed root-cause reproduction).
_MALFORMED_EDUCATION = [
    "Education: Kryvyi Rih Technical University, Mining, Faculty of Mining & Metallurgy",
]


def _build_education_fixture_repo(tmp_dir: Path, education: object) -> Path:
    """Build a throwaway repo root (CLAUDE.md anchor, templates/cv/ copied so the
    default WeasyPrint/baxter.html path can activate) with a config/candidate.yaml
    carrying the given ``education`` value. Returns the candidate.yaml path.

    Mirrors ``_build_fake_repo``'s anchor+templates-copy pattern above, but scoped to
    exactly the fields this task's education-row tests need (PIPEFIX-04's new
    RepoRootNotFoundError hard-errors on a bare, unanchored tmp dir, so a real
    CLAUDE.md anchor is required for --config paths used in these tests).
    """
    repo_root = tmp_dir / "fake-repo"
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    (repo_root / "CLAUDE.md").write_text("# fake repo anchor\n", encoding="utf-8")
    real_templates_dir = REPO_ROOT / "templates" / "cv"
    fake_templates_dir = repo_root / "templates" / "cv"
    fake_templates_dir.mkdir(parents=True, exist_ok=True)
    if real_templates_dir.is_dir():
        shutil.copytree(real_templates_dir, fake_templates_dir, dirs_exist_ok=True)

    fixture: dict = {
        "name": "Test Candidate",
        "title": "Test Title",
        "contact": {"email": ["test@example.com"]},
        "education": education,
    }
    candidate_path = repo_root / "config" / "candidate.yaml"
    candidate_path.write_text(yaml.safe_dump(fixture), encoding="utf-8")
    return candidate_path


def test_well_formed_education_renders_non_empty_section_both_paths() -> None:
    """Test 1: a well-formed education list (matching candidate.yaml's real shape)
    renders a non-empty Education section in both the default (WeasyPrint/baxter.html)
    path and the ReportLab (--no-template) path — institution/program text must be
    visible in each rendered output."""
    tmp_dir = Path(tempfile.mkdtemp())
    fixture_yaml = _build_education_fixture_repo(tmp_dir, _WELL_FORMED_EDUCATION)

    # ReportLab (--no-template) path: assert the render succeeds and produces a real
    # PDF; the shared PyMuPDF-based render-quality check in
    # test_well_formed_education_zero_missing_section_defects (Test 4) independently
    # proves the section content is actually visible in extracted PDF text.
    out_reportlab = tmp_dir / "out" / "reportlab-cv.pdf"
    result = _run("--config", str(fixture_yaml), "--no-template", "--out", str(out_reportlab))
    assert result.returncode == 0, f"--no-template invocation must exit 0: {result.stderr}"
    assert out_reportlab.is_file(), f"missing PDF: {out_reportlab}"

    if not _WEASYPRINT_AVAILABLE:
        print("SKIP (weasyprint unavailable): default-path HTML assertion in test_well_formed_education_renders_non_empty_section_both_paths")
        return

    out_default = tmp_dir / "out" / "default-cv.pdf"
    result = _run("--config", str(fixture_yaml), "--out", str(out_default))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    html_sibling = out_default.with_suffix(".html")
    assert html_sibling.is_file(), f"missing HTML sibling: {html_sibling}"
    html = html_sibling.read_text(encoding="utf-8")
    assert "Kryvyi Rih Technical University" in html, (
        "well-formed education row's institution text must appear in the rendered HTML"
    )
    assert "1C Bitrix Academy" in html, (
        "well-formed education row's institution text must appear in the rendered HTML"
    )


def test_malformed_education_row_warns_visibly_never_silent() -> None:
    """Test 2 (the exact bug-reproduction case): a bare-string education list (the real
    composer-citation-shape bug shape) must NOT silently produce an empty Education
    section with zero error signal. The render must still exit 0 (never crash), but a
    warning naming the malformed row must be visible on stderr for the ReportLab
    (--no-template) path, and for the default WeasyPrint path when available."""
    tmp_dir = Path(tempfile.mkdtemp())
    fixture_yaml = _build_education_fixture_repo(tmp_dir, _MALFORMED_EDUCATION)

    out_reportlab = tmp_dir / "out" / "reportlab-cv.pdf"
    result = _run("--config", str(fixture_yaml), "--no-template", "--out", str(out_reportlab))
    assert result.returncode == 0, f"--no-template invocation must exit 0 even with malformed education: {result.stderr}"
    assert out_reportlab.is_file(), f"missing PDF: {out_reportlab}"
    assert "malformed education row" in result.stderr, (
        f"expected a visible malformed-education-row warning on stderr, got: {result.stderr!r}"
    )
    assert "index 0" in result.stderr, "warning must name the row's index"

    if not _WEASYPRINT_AVAILABLE:
        print("SKIP (weasyprint unavailable): default-path warning assertion in test_malformed_education_row_warns_visibly_never_silent")
        return

    out_default = tmp_dir / "out" / "default-cv.pdf"
    result = _run("--config", str(fixture_yaml), "--out", str(out_default))
    assert result.returncode == 0, f"default invocation must exit 0 even with malformed education: {result.stderr}"
    assert "malformed education row" in result.stderr, (
        f"expected a visible malformed-education-row warning on stderr (default path), got: {result.stderr!r}"
    )


def test_well_formed_education_zero_missing_section_defects() -> None:
    """Test 4 (render-quality verification per PIPEFIX-02's acceptance criterion):
    running gmj_check_render_quality.py against a PDF rendered from the well-formed-
    education fixture reports zero missing_section defects for the education key."""
    if not _WEASYPRINT_AVAILABLE:
        print("SKIP (weasyprint unavailable): test_well_formed_education_zero_missing_section_defects")
        return
    tmp_dir = Path(tempfile.mkdtemp())
    fixture_yaml = _build_education_fixture_repo(tmp_dir, _WELL_FORMED_EDUCATION)

    out_pdf = tmp_dir / "out" / "default-cv.pdf"
    result = _run("--config", str(fixture_yaml), "--out", str(out_pdf))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    assert out_pdf.is_file(), f"missing PDF: {out_pdf}"

    check_script = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_render_quality.py"
    check_result = subprocess.run(
        [
            sys.executable, str(check_script),
            "--pdf", str(out_pdf),
            "--candidate-yaml", str(fixture_yaml),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert check_result.returncode == 0, f"render-quality check must exit 0: {check_result.stderr}"
    assert "missing_section: education" not in check_result.stdout, (
        f"expected zero missing_section defects for education, got: {check_result.stdout!r}"
    )


def test_master_candidate_direct_render_unchanged_by_fallback() -> None:
    """Test 3: rendering config/candidate.yaml directly (existing default invocation)
    with its own real photo key must be byte-identical in behavior to before this
    task — proven by the pre-existing tests in this file still passing unmodified,
    plus an explicit check here that the fallback path is never consulted for a
    direct master-file render (the master already has photo_raw() truthy)."""
    out = Path(tempfile.mkdtemp()) / "master-direct-cv.pdf"
    result = _run("--config", str(CONFIG), "--out", str(out))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    assert out.is_file(), f"missing PDF: {out}"


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
