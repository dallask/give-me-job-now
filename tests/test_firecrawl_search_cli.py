#!/usr/bin/env python3
"""CLI-level tests for scripts/offers/gmj_firecrawl_search.py (SEARCH-06/SEARCH-08).

Runnable as a plain assertion script (no pytest dependency), mirroring
tests/test_sources_scope_guard.py's self-registering module-collected test_* convention.

Proves, with ZERO live network calls (every Firecrawl SDK call is mocked/monkeypatched):
- an unset FIRECRAWL_API_KEY (no env var, no .env file) exits non-zero with a stderr message
  naming FIRECRAWL_API_KEY, and NEVER constructs a firecrawl.Firecrawl client (Pitfall 1 —
  this is an invocation-count assertion, not an API-behavior assertion);
- argparse's own required-arg validation rejects --mode scrape without --url and
  --mode search without --query;
- a monkeypatched Firecrawl.search() round-trips through main()'s JSON serialization to stdout;
- a monkeypatched Firecrawl.scrape() is called with formats=[{"type": "json", "schema": <loaded
  schema>}] (schema-guided extraction, not a bare string/prompt-only call) and its .json is
  printed to stdout.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "offers" / "gmj_firecrawl_search.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "firecrawl_extract_schema.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "offers"))

try:
    import firecrawl  # noqa: F401

    _FIRECRAWL_INSTALLED = True
except ImportError:
    _FIRECRAWL_INSTALLED = False


class SkipTest(Exception):
    """Raised to mark a test as skipped (not failed) — see main()'s runner."""


def _require_firecrawl() -> None:
    if not _FIRECRAWL_INSTALLED:
        raise SkipTest(
            "firecrawl-py not installed (pip install -r scripts/offers/requirements.txt)"
        )


def _fresh_module():
    """Import (or re-import) gmj_firecrawl_search as a fresh module object."""
    if "gmj_firecrawl_search" in sys.modules:
        return importlib.reload(sys.modules["gmj_firecrawl_search"])
    return importlib.import_module("gmj_firecrawl_search")


def test_unset_api_key_exits_nonzero_and_never_constructs_client() -> None:
    _require_firecrawl()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "search", "--query", "FPV Engineer Kyiv"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={"PATH": "/usr/bin:/bin", "FIRECRAWL_API_KEY": ""},
    )
    assert result.returncode != 0, f"expected non-zero exit, got {result.returncode}"
    assert "FIRECRAWL_API_KEY" in result.stderr, f"stderr missing FIRECRAWL_API_KEY: {result.stderr!r}"

    # Invocation-count assertion (Pitfall 1): mock Firecrawl and prove it is never called
    # when the key is unset, in-process (not just via subprocess exit code).
    mod = _fresh_module()
    with mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": ""}, clear=False):
        with mock.patch("firecrawl.Firecrawl") as mock_firecrawl_cls:
            argv_backup = sys.argv
            sys.argv = ["gmj_firecrawl_search.py", "--mode", "search", "--query", "x"]
            try:
                rc = mod.main()
            finally:
                sys.argv = argv_backup
            assert rc == 1
            mock_firecrawl_cls.assert_not_called()


def test_scrape_without_url_and_search_without_query_exit_nonzero() -> None:
    result_scrape = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "scrape"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result_scrape.returncode != 0

    result_search = subprocess.run(
        [sys.executable, str(SCRIPT), "--mode", "search"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result_search.returncode != 0


def test_search_mode_writes_valid_json_with_web_key() -> None:
    _require_firecrawl()
    mod = _fresh_module()

    fake_web_hit = SimpleNamespace(
        url="https://www.work.ua/jobs/1234567/",
        title="FPV Engineer",
        description="A great role.",
    )
    fake_search_data = SimpleNamespace(web=[fake_web_hit])

    mock_client = mock.MagicMock()
    mock_client.search.return_value = fake_search_data

    argv_backup = sys.argv
    sys.argv = ["gmj_firecrawl_search.py", "--mode", "search", "--query", "FPV Engineer Kyiv"]
    try:
        with mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "fc-test-key"}, clear=False):
            with mock.patch("firecrawl.Firecrawl", return_value=mock_client):
                import io

                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = mod.main()
                out = buf.getvalue()
    finally:
        sys.argv = argv_backup

    assert rc == 0
    payload = json.loads(out)
    assert "web" in payload
    assert payload["web"][0]["url"] == "https://www.work.ua/jobs/1234567/"
    assert payload["web"][0]["title"] == "FPV Engineer"


def test_scrape_mode_uses_schema_guided_formats_and_writes_json() -> None:
    _require_firecrawl()
    mod = _fresh_module()

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fake_doc = SimpleNamespace(json={"title": "FPV Engineer", "company": "Acme"})

    mock_client = mock.MagicMock()
    mock_client.scrape.return_value = fake_doc

    argv_backup = sys.argv
    sys.argv = [
        "gmj_firecrawl_search.py",
        "--mode",
        "scrape",
        "--url",
        "https://example.com/job/1",
    ]
    try:
        with mock.patch.dict("os.environ", {"FIRECRAWL_API_KEY": "fc-test-key"}, clear=False):
            with mock.patch("firecrawl.Firecrawl", return_value=mock_client):
                import io

                buf = io.StringIO()
                with mock.patch("sys.stdout", buf):
                    rc = mod.main()
                out = buf.getvalue()
    finally:
        sys.argv = argv_backup

    assert rc == 0
    payload = json.loads(out)
    assert payload == {"title": "FPV Engineer", "company": "Acme"}

    mock_client.scrape.assert_called_once()
    _, kwargs = mock_client.scrape.call_args
    assert kwargs.get("formats") == [{"type": "json", "schema": schema}]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    skipped = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except SkipTest as exc:
            skipped += 1
            print(f"SKIP {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed ({skipped} skipped)", file=sys.stderr)
        return 1
    suffix = f" ({skipped} skipped)" if skipped else ""
    print(f"all {len(tests) - skipped} tests passed{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
