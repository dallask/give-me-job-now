#!/usr/bin/env python3
"""Hard-gate harness for the Phase 9 candidate.yaml schema migration (SCHEMA-02/03/06).

This is the mechanical gate that makes the whole migration verifiable. Built FIRST,
before any consumer rename (research Pattern 1), so it can be re-run after every
consumer edit to catch Direction-B failures (a green gate over a hollow PDF) the moment
they appear.

Three checks:
  * ``test_no_container_repr_and_nonempty`` — render en/ua/ru and assert each PDF is
    non-empty and leaks no list/dict container-repr (``['`` / ``{'``) into contact or
    certification text (SCHEMA-02); the en render must contain the first expertise skill
    string, proving the expertise section rendered.
  * ``test_span_round_trip`` — a real new-key span resolves; a fabricated span raises
    (SCHEMA-03), reusing the single grammar owner ``yaml_path.resolve_path`` (never a
    second parser — threat T-09-01).
  * ``test_schema_fields_single_owner`` — the renderer imports ``schema_fields`` (SCHEMA-06).

Deterministic only: span resolution is machine-checkable; the LLM Gate-A verdict is
judgment and is NOT asserted here (repo discipline).

No pytest — run with ``python3 tests/test_schema_migration.py``. This harness is EXPECTED
to be RED at the end of plan 09-01 because ``render_cv.py`` still reads ``technical_expertise``
and does not yet import ``schema_fields``; later plans (09-02+) turn it green.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "render_cv.py"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"
ARTIFACTS_DIR = REPO_ROOT / "scripts" / "artifacts"


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


def test_no_container_repr_and_nonempty() -> None:
    for lang in ("en", "ua", "ru"):
        out = Path(tempfile.mkdtemp()) / f"cv-{lang}.pdf"
        result = _run("--config", str(CONFIG), "--lang", lang, "--out", str(out))
        assert result.returncode == 0, f"render --lang {lang} must exit 0: {result.stderr}"
        text = _pdf_text(out)
        assert "['" not in text, f"list container-repr leaked into {lang} render"
        assert "{'" not in text, f"dict container-repr leaked into {lang} render"
        assert len(text) > 200, f"{lang} render is trivially short ({len(text)} chars) — hollow PDF"
        if lang == "en":
            assert "Generative AI application" in text, "expertise section did not render in en"


def test_span_round_trip() -> None:
    sys.path.insert(0, str(ARTIFACTS_DIR))
    from yaml_path import resolve_path

    candidate = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert resolve_path(candidate, "expertise[0].skills[0]"), "real new-key span must resolve to a truthy value"
    try:
        resolve_path(candidate, "expertise[99].skills[0]")
    except (KeyError, IndexError, TypeError):
        pass
    else:
        raise AssertionError("fabricated span expertise[99].skills[0] must raise, not resolve")


def test_schema_fields_single_owner() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert "from schema_fields import" in src, "render_cv.py must import the schema_fields registry (SCHEMA-06)"


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
