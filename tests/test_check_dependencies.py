#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_check_dependencies.py (GUIDE-04).

Proves the advisory optional-dependency presence probe fires only for configured
features (search_provider: firecrawl), always checks the CV HTML-render path
unconditionally, and stays advisory-only (always exits 0).

No pytest — run with ``python3 tests/test_check_dependencies.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_dependencies.py"
REAL_PREFERENCES = REPO_ROOT / "config" / "preferences.yaml"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_real_config_default_provider_reports_cv_only() -> None:
    result = _run("--preferences", str(REAL_PREFERENCES))
    assert result.returncode == 0, result.stderr
    assert "firecrawl-py" not in result.stdout
    assert "CV HTML template rendering" in result.stdout


def test_synthetic_config_firecrawl_configured_reports_finding() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "preferences.yaml"
        path.write_text("search_provider: firecrawl\n", encoding="utf-8")
        result = _run("--preferences", str(path))
        assert result.returncode == 0, result.stderr
        assert "firecrawl-py" in result.stdout


def test_synthetic_config_no_provider_key_omits_firecrawl_finding() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "preferences.yaml"
        path.write_text("salary:\n  min: 1000\n", encoding="utf-8")
        result = _run("--preferences", str(path))
        assert result.returncode == 0, result.stderr
        assert "firecrawl-py" not in result.stdout


def test_missing_preferences_file_exits_one_no_traceback() -> None:
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "does_not_exist.yaml"
        result = _run("--preferences", str(missing))
        assert result.returncode == 1
        assert result.stderr.strip() != ""
        assert "Traceback" not in result.stderr


def test_invalid_yaml_exits_one_no_traceback() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "broken.yaml"
        path.write_text("{ this is not: valid: yaml", encoding="utf-8")
        result = _run("--preferences", str(path))
        assert result.returncode == 1
        assert result.stderr.strip() != ""
        assert "Traceback" not in result.stderr


def test_advisory_contract_always_exits_zero() -> None:
    for preferences_path in (REAL_PREFERENCES,):
        result = _run("--preferences", str(preferences_path))
        assert result.returncode == 0, result.stderr
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "preferences.yaml"
        path.write_text("search_provider: firecrawl\n", encoding="utf-8")
        result = _run("--preferences", str(path))
        assert result.returncode == 0, result.stderr


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
