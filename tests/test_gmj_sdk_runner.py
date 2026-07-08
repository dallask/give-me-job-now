#!/usr/bin/env python3
"""Behavior tests for scripts/runtime/gmj_sdk_runner.py (SDK-02/SDK-03).

Runnable as a plain assertion script (no pytest dependency), mirroring
tests/test_validate_envelope.py's structure. Proves the adapter's hook shell-out,
envelope re-validation, and dispatch orchestration all work correctly WITHOUT requiring
the real claude-agent-sdk to be installed or making any live/paid API call — this
environment has claude-agent-sdk confirmed absent (test 10 exercises that real path).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "runtime" / "gmj_sdk_runner.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "runtime"))
import gmj_sdk_runner  # noqa: E402


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(RUNNER), *args], capture_output=True, text=True)


def _isolated_scope_project_dir() -> Path:
    """Mirror tests/test_sources_scope_guard.py::_run_in_dir()'s isolation convention.

    Never write into or read the real repo's .claude/logs/ during these tests.
    """
    tmp = Path(tempfile.mkdtemp(prefix="sdk-runner-scope-guard-"))
    (tmp / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "config" / "sources.yaml", tmp / "config" / "sources.yaml")
    return tmp


def test_requirements_txt_isolated_and_minimal() -> None:
    content = (REPO_ROOT / "scripts" / "runtime" / "requirements.txt").read_text(encoding="utf-8")
    assert "claude-agent-sdk" in content
    assert "jsonschema" not in content


def test_experimental_label_in_entry_script() -> None:
    text = gmj_sdk_runner.__file__ and Path(gmj_sdk_runner.__file__).read_text(encoding="utf-8")
    assert "experimental/unsupported for autonomous runs until parity is verified" in text.lower()


def test_pretooluse_scope_guard_denies_offscope_host() -> None:
    tmp = _isolated_scope_project_dir()
    result = asyncio.run(
        gmj_sdk_runner.pretooluse_scope_guard(
            {"tool_name": "WebFetch", "tool_input": {"url": "https://evil.example.com/"}},
            "tool-1",
            None,
            project_dir=tmp,
        )
    )
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny", result


def test_pretooluse_scope_guard_allows_in_scope_host() -> None:
    tmp = _isolated_scope_project_dir()
    result = asyncio.run(
        gmj_sdk_runner.pretooluse_scope_guard(
            {"tool_name": "WebFetch", "tool_input": {"url": "https://www.work.ua/jobs"}},
            "tool-1",
            None,
            project_dir=tmp,
        )
    )
    assert result == {}, result


def test_pretooluse_scope_guard_passthrough_non_web_tool() -> None:
    tmp = _isolated_scope_project_dir()
    result = asyncio.run(
        gmj_sdk_runner.pretooluse_scope_guard(
            {"tool_name": "Read", "tool_input": {}},
            "tool-1",
            None,
            project_dir=tmp,
        )
    )
    assert result == {}, result


def test_validate_envelope_accepts_conformant_dict() -> None:
    envelope = {
        "schema": "agent_result_v1",
        "kind": "gate_result",
        "schema_version": "1.0",
        "status": "success",
        "agent": "smoke-spoke",
        "notes": "ok",
        "artifacts": [],
    }
    assert gmj_sdk_runner.validate_envelope(envelope) == []


def test_validate_envelope_rejects_malformed_dict() -> None:
    # (a) conformant except an invalid status enum value.
    bad_status = {
        "schema": "agent_result_v1",
        "kind": "gate_result",
        "schema_version": "1.0",
        "status": "bogus",
        "agent": "smoke-spoke",
        "notes": "ok",
        "artifacts": [],
    }
    errors = gmj_sdk_runner.validate_envelope(bad_status)
    assert errors, "expected validate_envelope to reject an invalid status enum"
    assert any("status" in e for e in errors), errors

    # (b) a bare shared-base dict with NO kind/schema_version at all — the exact shape a
    # hand-rolled bare-base check would wrongly accept; must be rejected here.
    no_kind = {
        "schema": "agent_result_v1",
        "status": "success",
        "agent": "x",
        "notes": "ok",
        "artifacts": [],
    }
    errors2 = gmj_sdk_runner.validate_envelope(no_kind)
    assert errors2, "expected validate_envelope to reject a dict with no kind"
    assert any("kind" in e for e in errors2), errors2


def test_run_spoke_dispatches_and_returns_validated_envelope() -> None:
    envelope = {
        "schema": "agent_result_v1",
        "kind": "gate_result",
        "schema_version": "1.0",
        "status": "success",
        "agent": "smoke-spoke",
        "notes": "ok",
        "artifacts": [],
    }

    class ResultMessage:
        def __init__(self, structured_output: dict) -> None:
            self.structured_output = structured_output

    class FakeOptions:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeHookMatcher:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    async def fake_query(*, prompt, options):
        yield ResultMessage(envelope)

    orig_query = gmj_sdk_runner.query
    orig_options = gmj_sdk_runner.ClaudeAgentOptions
    orig_matcher = gmj_sdk_runner.HookMatcher
    try:
        gmj_sdk_runner.query = fake_query
        gmj_sdk_runner.ClaudeAgentOptions = FakeOptions
        gmj_sdk_runner.HookMatcher = FakeHookMatcher
        result = asyncio.run(
            gmj_sdk_runner.run_spoke("gmj-candidate-configurator", '{"ping": "pong"}')
        )
        assert result == envelope, result
    finally:
        gmj_sdk_runner.query = orig_query
        gmj_sdk_runner.ClaudeAgentOptions = orig_options
        gmj_sdk_runner.HookMatcher = orig_matcher


def test_run_spoke_raises_actionable_error_when_sdk_unavailable() -> None:
    orig_query = gmj_sdk_runner.query
    try:
        gmj_sdk_runner.query = None
        try:
            asyncio.run(gmj_sdk_runner.run_spoke("gmj-candidate-configurator", "{}"))
        except RuntimeError as exc:
            message = str(exc)
            assert "pip install" in message, message
            assert "scripts/runtime/requirements.txt" in message, message
        else:
            raise AssertionError("expected RuntimeError when query is None")
    finally:
        gmj_sdk_runner.query = orig_query


def test_cli_subprocess_reports_actionable_error_when_sdk_not_installed() -> None:
    # claude-agent-sdk is confirmed absent from this environment's Python — this test
    # genuinely exercises the not-installed path against the real, unpatched subprocess.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write("{}")
        input_path = fh.name
    try:
        result = _run(["--spoke", "gmj-candidate-configurator", "--input", input_path])
        assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
        assert "Traceback" not in result.stderr, result.stderr
        assert "pip install" in result.stderr, result.stderr
    finally:
        os.unlink(input_path)


def test_default_cli_path_untouched() -> None:
    files = sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))
    files += [
        REPO_ROOT / ".claude" / "commands" / "gmj-collective.md",
        REPO_ROOT / ".claude" / "commands" / "gmj-pipeline-run.md",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "scripts/runtime" not in text, path
        assert "claude_agent_sdk" not in text, path
        assert "claude-agent-sdk" not in text, path


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
