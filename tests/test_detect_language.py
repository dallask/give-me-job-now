#!/usr/bin/env python3
"""Plain-python3 tests for scripts/offers/gmj_detect_language.py (PIPE-10).

Proves the deterministic ua/ru/en offer-language detector: Cyrillic-ratio +
UA/RU-stopword heuristic classifies clearly-Ukrainian and clearly-Russian samples
correctly, plain-Latin English text is detected as en, and every inconclusive case
(below the named Cyrillic-ratio threshold, empty/missing text) degrades to en rather
than crashing or exiting nonzero — detection never "fails" for ordinary input
(RESEARCH.md Pattern 2). No pytest — run with ``python3 tests/test_detect_language.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "offers" / "gmj_detect_language.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "offers"))
from gmj_detect_language import (  # noqa: E402
    CYRILLIC_RATIO_THRESHOLD,
    detect_language,
)


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_ukrainian_heavy_text_detected_as_ua() -> None:
    text = (
        "Ми шукаємо досвідченого розробника, який також вміє працювати в команді. "
        "Будь ласка, надішліть резюме — цей вакансія відкрита зараз."
    )
    assert detect_language(text) == "ua", detect_language(text)


def test_russian_heavy_text_detected_as_ru() -> None:
    text = (
        "Мы ищем опытного разработчика, который также умеет работать в команде. "
        "Пожалуйста, отправьте резюме — этот вакансия открыта сейчас, очень срочно."
    )
    assert detect_language(text) == "ru", detect_language(text)


def test_english_text_detected_as_en() -> None:
    text = "Hello there, we are looking for a senior engineer to join our team."
    assert detect_language(text) == "en", detect_language(text)


def test_inconclusive_defaults_to_en() -> None:
    # Deliberately construct a sample whose Cyrillic-character ratio is below the
    # detector's own named threshold constant (imported directly, not hardcoded, so
    # this test stays correct if the constant is later tuned).
    cyrillic_chars = "б"  # a single Cyrillic character
    latin_padding = "a" * 200  # plenty of Latin alphabetic characters
    text = f"{cyrillic_chars} {latin_padding}"

    # Sanity-check our construction actually sits below the threshold.
    alpha_count = len(cyrillic_chars) + len(latin_padding)
    ratio = len(cyrillic_chars) / alpha_count
    assert ratio < CYRILLIC_RATIO_THRESHOLD, (
        f"test construction bug: ratio {ratio} not below threshold "
        f"{CYRILLIC_RATIO_THRESHOLD}"
    )

    assert detect_language(text) == "en", detect_language(text)


def test_empty_or_missing_text_defaults_to_en() -> None:
    assert detect_language("") == "en"
    assert detect_language("   \n\t  ") == "en"


def test_cli_reads_file_and_stdin() -> None:
    # --stdin
    result = _run("--stdin", stdin="Hello there, we are looking for a senior engineer")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "en", result.stdout

    # --file
    tmp_dir = Path(REPO_ROOT) / "tests" / "fixtures"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / "_tmp_detect_language_sample.txt"
    tmp_file.write_text(
        "Ми шукаємо досвідченого розробника, який також вміє працювати в команді. "
        "Будь ласка, надішліть резюме — цей вакансія відкрита зараз.",
        encoding="utf-8",
    )
    try:
        result = _run("--file", str(tmp_file))
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ua", result.stdout
    finally:
        tmp_file.unlink(missing_ok=True)

    # Every ordinary invocation exits 0 — detection never "fails".
    result = _run("--stdin", stdin="")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "en", result.stdout


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
