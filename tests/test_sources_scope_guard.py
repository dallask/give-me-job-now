#!/usr/bin/env python3
"""Integration tests for the gmj-sources-scope-guard PreToolUse hook (INTAKE-05 / SC2).

Runnable as a plain assertion script (no pytest dependency). Feeds fixture stdin
payloads to ``.claude/hooks/gmj-sources-scope-guard.sh`` as a subprocess and proves the
EXECUTED hook — not an agent self-report — enforces ``config/sources.yaml`` scope:

- an in-scope WebFetch (host under ``config/sources.yaml`` sites) is allowed (exit 0),
- an out-of-scope WebFetch (host not in the allow-list) is blocked (exit 2),
- a non-web tool (``Read``) is an early pass-through (exit 0, no block),
- on every WebSearch/WebFetch the ``sources.yaml`` read is logged BEFORE the
  allow/block decision — the log line is the demonstrable SC2 audit record.

The hook runs with ``CLAUDE_PROJECT_DIR`` pointed at an isolated temp dir (its own
copy of ``config/sources.yaml`` + its own log path), so assertions never touch the
real repo log.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-sources-scope-guard.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCES_YAML = REPO_ROOT / "config" / "sources.yaml"
CREDENTIALS_YAML = REPO_ROOT / "config" / "credentials.yaml"

IN_SCOPE = FIXTURES / "websearch_in_scope.json"
OUT_OF_SCOPE = FIXTURES / "websearch_out_of_scope.json"
CRED_IN_SCOPE = FIXTURES / "credential_in_scope.json"
CRED_OFF_LIST = FIXTURES / "credential_off_list.json"


def _run_in_dir(stdin_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the hook in an isolated CLAUDE_PROJECT_DIR seeded with both allow-lists.

    Returns (result, tmp_dir) so callers can reach either the sources-scope.log or
    the separate credential-intake.log under ``tmp_dir/.claude/logs/``.
    """
    tmp = Path(tempfile.mkdtemp(prefix="scope-guard-"))
    (tmp / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(SOURCES_YAML, tmp / "config" / "sources.yaml")
    if CREDENTIALS_YAML.is_file():
        shutil.copy(CREDENTIALS_YAML, tmp / "config" / "credentials.yaml")
    result = subprocess.run(
        ["sh", str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp)},
    )
    return result, tmp


def _run(stdin_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the hook in an isolated CLAUDE_PROJECT_DIR; return (result, log_path)."""
    result, tmp = _run_in_dir(stdin_text)
    return result, tmp / ".claude" / "logs" / "sources-scope.log"


def _read_payload(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_read_logged_before_decision(log_path: Path) -> None:
    assert log_path.is_file(), f"expected log at {log_path}, none written"
    text = log_path.read_text(encoding="utf-8")
    assert "READ" in text, f"log must record the sources.yaml read; got:\n{text}"
    assert "sources.yaml" in text, f"log READ line must name sources.yaml; got:\n{text}"
    # The read must be logged before the allow/block decision (SC2 demonstrability).
    read_idx = text.index("READ")
    decision_idx = min(
        (text.index(tok) for tok in ("ALLOWED", "BLOCK") if tok in text),
        default=-1,
    )
    assert decision_idx != -1, f"log must record a decision (ALLOWED/BLOCK); got:\n{text}"
    assert read_idx < decision_idx, (
        f"the sources.yaml READ must be logged BEFORE the decision; got:\n{text}"
    )


def test_in_scope_webfetch_allowed() -> None:
    result, log = _run(_read_payload(IN_SCOPE))
    assert result.returncode == 0, (
        f"in-scope WebFetch must be allowed (exit 0); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "ALLOWED" in log.read_text(encoding="utf-8")


def test_out_of_scope_webfetch_blocked() -> None:
    result, log = _run(_read_payload(OUT_OF_SCOPE))
    assert result.returncode == 2, (
        f"out-of-scope WebFetch must be blocked (exit 2); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "BLOCK" in log.read_text(encoding="utf-8")


def test_non_web_tool_passthrough() -> None:
    payload = '{"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}}'
    result, _log = _run(payload)
    assert result.returncode == 0, (
        f"non-web tool must pass through (exit 0); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )


def test_read_line_present_on_every_web_invocation() -> None:
    # Both an allowed and a blocked invocation must emit the demonstrable read line.
    _, allow_log = _run(_read_payload(IN_SCOPE))
    _, block_log = _run(_read_payload(OUT_OF_SCOPE))
    for log in (allow_log, block_log):
        _assert_read_logged_before_decision(log)


def test_credential_host_allowed() -> None:
    # A host on the SEPARATE config/credentials.yaml credential_sites list is
    # fetch-allowed (exit 0) and recorded in the DISTINCT credential-intake.log
    # (INGEST-02 demonstrable audit record), not in sources-scope.log.
    result, tmp = _run_in_dir(_read_payload(CRED_IN_SCOPE))
    assert result.returncode == 0, (
        f"credential-list WebFetch must be allowed (exit 0); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    cred_log = tmp / ".claude" / "logs" / "credential-intake.log"
    assert cred_log.is_file(), f"expected credential log at {cred_log}, none written"
    text = cred_log.read_text(encoding="utf-8")
    assert "ALLOWED" in text and "credential-allow-list" in text, (
        f"credential log must record an ALLOWED credential line; got:\n{text}"
    )
    assert "credly.com" in text, f"credential log must name the fetched host; got:\n{text}"


def test_offlist_still_blocked() -> None:
    # Regression: a host on NEITHER sources.yaml nor credentials.yaml is refused.
    result, _tmp = _run_in_dir(_read_payload(CRED_OFF_LIST))
    assert result.returncode == 2, (
        f"a host on neither allow-list must be blocked (exit 2); got {result.returncode}\n"
        f"stderr: {result.stderr}"
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
