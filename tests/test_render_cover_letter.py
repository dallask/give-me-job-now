#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/render_cover_letter.py (E2E-02).

Proves an approved cover_letter draft renders to a REAL PDF via ReportLab:
magic bytes ``%PDF-`` + ``pypdf`` page count >= 1. PDF validity is asserted
STRUCTURALLY, never by byte-hash — ReportLab embeds CreationDate/ModDate so
the bytes are not reproducible across runs (Pitfall 5, T-08-07). Also proves
the Cyrillic (``--lang ua``) path does not crash and that a malformed draft
degrades to exit 1 with no traceback. No pytest — run with
``python3 tests/test_render_cover_letter.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "render_cover_letter.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cover_letter.draft.sample.json"


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


def test_english_render_valid_pdf() -> None:
    out = Path(tempfile.mkdtemp()) / "cover-en.pdf"
    result = _run("--file", str(FIXTURE), "--out", str(out))
    assert result.returncode == 0, f"english render must exit 0: {result.stderr}"
    assert_valid_pdf(out)


def test_cyrillic_lang_does_not_crash() -> None:
    out = Path(tempfile.mkdtemp()) / "cover-ua.pdf"
    result = _run("--file", str(FIXTURE), "--out", str(out), "--lang", "ua")
    assert result.returncode == 0, f"--lang ua must not crash: {result.stderr}"
    assert_valid_pdf(out)


def test_malformed_draft_degrades_exit_1() -> None:
    bad = Path(tempfile.mkdtemp()) / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    out = Path(tempfile.mkdtemp()) / "cover-bad.pdf"
    result = _run("--file", str(bad), "--out", str(out))
    assert result.returncode == 1, "malformed draft must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on malformed draft"


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
