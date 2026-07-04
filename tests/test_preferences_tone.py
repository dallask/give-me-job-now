#!/usr/bin/env python3
"""Tests for the optional cover_letter_tone preferences field (ARTIFACT-02, config half).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_preferences_tone.py``. Proves the EXECUTED validator
(scripts/preferences/validate_preferences.py) both:

- ACCEPTS a preferences.yaml carrying an optional ``cover_letter_tone`` string (exit 0), and
- still FAILS CLOSED on an unknown/misspelled top-level key (root
  ``additionalProperties:false``) after the schema gained the new property — a misspelled
  ``cover_letter_tones:`` (plural) must be REJECTED, not silently dropped.

Also re-asserts the committed config/preferences.yaml conforms against the real
config/sources.yaml, so adding the schema property did not regress the shipped config.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "preferences" / "validate_preferences.py"


def _write(tmp: Path, name: str, data) -> Path:
    """yaml-dump a dict to a temp file and return its path."""
    p = tmp / name
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def _run(prefs: Path, sources: Path) -> subprocess.CompletedProcess:
    """Subprocess-run the validator with --file and --sources, capturing text output."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--file", str(prefs), "--sources", str(sources)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _sources(tmp: Path) -> Path:
    return _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua", "en"]},
    )


def test_cover_letter_tone_string_accepted() -> None:
    """A valid ``cover_letter_tone`` string must validate (exit 0)."""
    tmp = Path(tempfile.mkdtemp(prefix="pref-tone-ok-"))
    sources = _sources(tmp)
    prefs = _write(tmp, "preferences.yaml", {"cover_letter_tone": "warm, direct"})
    r = _run(prefs, sources)
    assert r.returncode == 0, (
        "a valid cover_letter_tone string must pass (exit 0); "
        f"got {r.returncode}\nstderr: {r.stderr}"
    )


def test_misspelled_tone_key_fails_closed() -> None:
    """A misspelled top-level key (``cover_letter_tones`` plural) must be REJECTED.

    Proves root ``additionalProperties:false`` still fails closed AFTER the schema gained
    the ``cover_letter_tone`` property — a typo must not slip past the subset validator.
    """
    tmp = Path(tempfile.mkdtemp(prefix="pref-tone-typo-"))
    sources = _sources(tmp)
    prefs = _write(tmp, "preferences.yaml", {"cover_letter_tones": "warm, direct"})
    r = _run(prefs, sources)
    assert r.returncode == 1, (
        "misspelled 'cover_letter_tones' key must FAIL closed (root additionalProperties:false); "
        f"got {r.returncode}\nstdout: {r.stdout}"
    )
    assert "SHAPE-ERROR" in r.stderr, f"must report a shape error; stderr:\n{r.stderr}"
    assert "OK" not in r.stdout, f"must NOT print the success sentinel; stdout:\n{r.stdout}"


def test_committed_preferences_conforms() -> None:
    """The committed config/preferences.yaml must still conform (no regression)."""
    r = _run(REPO_ROOT / "config" / "preferences.yaml", REPO_ROOT / "config" / "sources.yaml")
    assert r.returncode == 0, (
        "the committed config/preferences.yaml must conform against the real "
        f"config/sources.yaml (exit 0); got {r.returncode}\nstderr: {r.stderr}"
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
