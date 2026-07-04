#!/usr/bin/env python3
"""Tests for scripts/preferences/gmj_validate_preferences.py (INTERVIEW-06 / INTERVIEW-03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_validate_preferences.py``. Proves the EXECUTED validator, not a
persona self-report, enforces the ``config/preferences.yaml`` ⊆ ``config/sources.yaml``
scope invariant and fails CLOSED:

- an in-scope preferences.yaml exits 0,
- an out-of-scope scope-axis item (city / site / language absent from sources.yaml)
  exits non-zero AND names the offending item,
- a missing / unparsable sources.yaml exits non-zero (fail CLOSED, never fail-open),
- a bare host in preferences matches a full-URL board in sources.yaml after
  normalization (no false-negative),
- the validator never writes sources.yaml (content + mtime unchanged after a run),
- the committed config/preferences.yaml conforms against the real config/sources.yaml.

Written BEFORE the validator exists, so first run is expected to FAIL (RED).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "preferences" / "gmj_validate_preferences.py"


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


def test_in_scope_passes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-in-scope-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua", "en"]},
    )
    prefs = _write(
        tmp,
        "preferences.yaml",
        {"scope": {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]}},
    )
    r = _run(prefs, sources)
    assert r.returncode == 0, (
        f"in-scope prefs must pass (exit 0); got {r.returncode}\nstderr: {r.stderr}"
    )


def test_out_of_scope_city_fails_closed_and_lists() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-oos-city-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    prefs = _write(tmp, "preferences.yaml", {"scope": {"cities": ["Berlin"]}})
    r = _run(prefs, sources)
    assert r.returncode != 0, "out-of-scope city must FAIL closed"
    assert "Berlin" in r.stderr, f"must LIST the offending city; stderr:\n{r.stderr}"


def test_out_of_scope_site_fails_closed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-oos-site-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    prefs = _write(tmp, "preferences.yaml", {"scope": {"sites": ["https://evil.example/"]}})
    r = _run(prefs, sources)
    assert r.returncode != 0, "out-of-scope site must FAIL closed"
    assert "evil.example" in r.stderr, f"must LIST the offending site; stderr:\n{r.stderr}"


def test_out_of_scope_language_fails_closed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-oos-lang-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    prefs = _write(tmp, "preferences.yaml", {"scope": {"languages": ["fr"]}})
    r = _run(prefs, sources)
    assert r.returncode != 0, "out-of-scope language must FAIL closed"
    assert "fr" in r.stderr, f"must LIST the offending language; stderr:\n{r.stderr}"


def test_missing_sources_fails_closed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-missing-src-"))
    prefs = _write(tmp, "preferences.yaml", {"scope": {"cities": ["Kyiv"]}})
    r = _run(prefs, tmp / "does-not-exist.yaml")
    assert r.returncode != 0, (
        "missing sources.yaml must FAIL closed (never fail-open on a scope gate)"
    )
    # A nonzero exit alone is satisfiable by an unrelated crash (argparse/import/traceback);
    # assert the specific fail-closed reason path AND the absence of the success sentinel.
    assert "FAIL-CLOSED" in r.stderr, (
        f"must hit the fail-closed reason path (not an unrelated crash); stderr:\n{r.stderr}"
    )
    assert "OK" not in r.stdout, f"must NOT print the success sentinel; stdout:\n{r.stdout}"


def test_misspelled_scope_key_rejected() -> None:
    """A typo'd top-level key (`scopes:`) must be REJECTED by shape validation.

    Without root ``additionalProperties:false`` an unknown key like ``scopes:`` slips past
    the schema and ``_scope()`` reads nothing, so ``subset_offenders`` finds no offender and
    the validator prints ``OK`` — silently dropping the operator's intended narrowing (here
    an out-of-scope Berlin). The root guard must turn this into a shape error.
    """
    tmp = Path(tempfile.mkdtemp(prefix="pref-typo-scope-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    prefs = _write(tmp, "preferences.yaml", {"scopes": {"cities": ["Berlin"]}})
    r = _run(prefs, sources)
    assert r.returncode != 0, (
        "misspelled top-level 'scopes' key must FAIL (root additionalProperties:false), "
        f"not silently drop the subset gate; stdout:\n{r.stdout}"
    )
    assert "SHAPE-ERROR" in r.stderr, f"must report a shape error; stderr:\n{r.stderr}"
    assert "OK" not in r.stdout, f"must NOT print the success sentinel; stdout:\n{r.stdout}"


def test_url_vs_host_normalization_true_positive() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-norm-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    # sources lists the full URL; prefs lists the bare host — must still match.
    prefs = _write(tmp, "preferences.yaml", {"scope": {"sites": ["work.ua"]}})
    r = _run(prefs, sources)
    assert r.returncode == 0, (
        "bare host must match full-URL board after normalization (no false-negative); "
        f"got {r.returncode}\nstderr: {r.stderr}"
    )


def test_validator_never_writes_sources() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pref-readonly-"))
    sources = _write(
        tmp,
        "sources.yaml",
        {"sites": ["https://www.work.ua/"], "cities": ["Kyiv"], "languages": ["ua"]},
    )
    prefs = _write(tmp, "preferences.yaml", {"scope": {"cities": ["Berlin"]}})  # triggers a fail path
    before_bytes = sources.read_bytes()
    before_mtime = sources.stat().st_mtime_ns
    _run(prefs, sources)
    assert sources.read_bytes() == before_bytes, "validator must NOT modify sources.yaml content"
    assert sources.stat().st_mtime_ns == before_mtime, "validator must NOT touch sources.yaml mtime"


def test_committed_preferences_conforms() -> None:
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
