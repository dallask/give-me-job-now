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
import subprocess
import sys
import tempfile
from pathlib import Path

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
