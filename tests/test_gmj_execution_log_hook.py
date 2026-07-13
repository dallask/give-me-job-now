#!/usr/bin/env python3
"""Integration tests for the gmj-execution-log PostToolUse/PreToolUse/SubagentStop
hook (REFLECT-01, REFLECT-02, REFLECT-05).

Runnable as a plain assertion script (no pytest dependency). Feeds fixture stdin
payloads to ``.claude/hooks/gmj-execution-log.sh`` as a subprocess and proves the
EXECUTED hook — not an agent self-report:

- writes exactly one structured JSONL entry per matched tool-call event to
  ``.planning/execution-logs/tool-calls-<date>.jsonl`` (REFLECT-01),
- records the touched file path in a non-empty ``artifacts`` array for Write/Edit
  PostToolUse events (REFLECT-02),
- NEVER returns a blocking exit code (2) under any input, including malformed or
  empty stdin, and never raises the calling tool call's own exit code (REFLECT-05).

The hook runs with ``CLAUDE_PROJECT_DIR`` pointed at an isolated temp dir, so
assertions never touch the real repo's ``.planning/execution-logs/`` directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-execution-log.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution-logs"

PRETOOLUSE_BASH = FIXTURES / "pretooluse_bash.json"
PRETOOLUSE_READ = FIXTURES / "pretooluse_read.json"
POSTTOOLUSE_WRITE = FIXTURES / "posttooluse_write.json"
POSTTOOLUSE_EDIT = FIXTURES / "posttooluse_edit.json"
SUBAGENTSTOP_NO_TRANSCRIPT = FIXTURES / "subagentstop_no_transcript.json"
MALFORMED_EMPTY = FIXTURES / "malformed_empty.json"


def _run_in_dir(stdin_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the hook in an isolated CLAUDE_PROJECT_DIR temp dir.

    Returns (result, tmp_dir) so callers can reach the JSONL log file(s) under
    ``tmp_dir / ".planning" / "execution-logs"``.
    """
    tmp = Path(tempfile.mkdtemp(prefix="execution-log-hook-"))
    result = subprocess.run(
        ["sh", str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp)},
    )
    return result, tmp


def _read_payload(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _log_files(tmp: Path) -> list[Path]:
    log_dir = tmp / ".planning" / "execution-logs"
    if not log_dir.is_dir():
        return []
    return sorted(log_dir.glob("tool-calls-*.jsonl"))


def _parsed_entries(tmp: Path) -> list[dict]:
    """Parse every JSONL line across all log files in tmp as a list of dicts."""
    entries: list[dict] = []
    for log_file in _log_files(tmp):
        text = log_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def test_bash_call_writes_jsonl_entry() -> None:
    result, tmp = _run_in_dir(_read_payload(PRETOOLUSE_BASH))
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    log_files = _log_files(tmp)
    assert log_files, f"expected a tool-calls-<date>.jsonl file under {tmp}, none written"
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["source"] == "tool-call", f"entry must be tagged source=tool-call; got {entry}"
    assert entry["event"] == "PreToolUse", f"entry must record the hook event name; got {entry}"
    assert entry["tool_name"] == "Bash", f"entry must record tool_name=Bash; got {entry}"
    assert entry["outcome"] == "observed", f"observability entry outcome must be 'observed'; got {entry}"
    assert "ts" in entry and entry["ts"], f"entry must include an ISO8601 ts field; got {entry}"


def test_read_call_records_artifact_path() -> None:
    # REFLECT-06: proves a Read tool-call payload (the exact fixture shape a real
    # Claude Code session sends) produces a correctly-shaped JSONL entry via the
    # real hook script - tool_name Read, event PreToolUse, source tool-call, and a
    # non-empty artifacts array containing the fixture's file_path value. This is
    # the same shape REFLECT-02 already requires for Write/Edit entries, now proven
    # for Read too.
    result, tmp = _run_in_dir(_read_payload(PRETOOLUSE_READ))
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["source"] == "tool-call", f"entry must be tagged source=tool-call; got {entry}"
    assert entry["event"] == "PreToolUse", f"entry must record the hook event name; got {entry}"
    assert entry["tool_name"] == "Read", f"entry must record tool_name=Read; got {entry}"
    assert isinstance(entry.get("artifacts"), list) and entry["artifacts"], (
        f"artifacts must be a non-empty array (REFLECT-02 shape, now proven for Read); got {entry}"
    )
    assert "config/candidate.yaml" in entry["artifacts"], (
        f"artifacts must contain the fixture's file_path value; got {entry}"
    )


def test_write_call_records_artifact_path() -> None:
    result, tmp = _run_in_dir(_read_payload(POSTTOOLUSE_WRITE))
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["tool_name"] == "Write", f"entry must record tool_name=Write; got {entry}"
    assert "artifacts" in entry, f"entry must have an artifacts field; got {entry}"
    assert isinstance(entry["artifacts"], list) and entry["artifacts"], (
        f"artifacts must be a non-empty array (REFLECT-02); got {entry}"
    )
    assert "output/analysis/self-reflect-report.md" in entry["artifacts"], (
        f"artifacts must contain the touched file path; got {entry}"
    )


def test_edit_call_records_artifact_path() -> None:
    result, tmp = _run_in_dir(_read_payload(POSTTOOLUSE_EDIT))
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["tool_name"] == "Edit", f"entry must record tool_name=Edit; got {entry}"
    assert isinstance(entry.get("artifacts"), list) and entry["artifacts"], (
        f"artifacts must be a non-empty array (REFLECT-02); got {entry}"
    )
    assert "scripts/gmj_self_reflect.py" in entry["artifacts"], (
        f"artifacts must contain the touched file path; got {entry}"
    )


def test_subagent_stop_records_transcript_path() -> None:
    result, tmp = _run_in_dir(_read_payload(SUBAGENTSTOP_NO_TRANSCRIPT))
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["source"] == "tool-call", f"entry must be tagged source=tool-call; got {entry}"
    assert entry["event"] == "SubagentStop", f"entry must record event=SubagentStop; got {entry}"
    assert entry.get("agent_id") == "agent-does-not-exist-12345", (
        f"entry must record the agent_id field; got {entry}"
    )
    assert entry.get("transcript_path") == "/nonexistent/path/to/transcript.jsonl", (
        f"entry must record the transcript_path field (path only, never content); got {entry}"
    )


def test_malformed_stdin_never_blocks() -> None:
    # A single stray newline byte is not valid JSON — the hook must degrade
    # gracefully (best-effort partial entry or nothing written) but NEVER exit 2
    # and NEVER raise an uncaught shell error.
    result, _tmp = _run_in_dir(_read_payload(MALFORMED_EMPTY))
    assert result.returncode == 0, (
        f"malformed stdin must never block (exit 0, never 2); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )


def test_empty_stdin_never_blocks() -> None:
    result, _tmp = _run_in_dir("")
    assert result.returncode == 0, (
        f"empty stdin must never block (exit 0, never 2); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )


def test_unhandled_tool_still_observed() -> None:
    # A PreToolUse payload for a tool this hook does not specifically special-case
    # (e.g. Read) still produces a minimal JSONL entry — every matched tool call is
    # observed, not just the specially-handled ones (Bash/Write/Edit/SubagentStop).
    payload = json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/some-file.txt"},
        }
    )
    result, tmp = _run_in_dir(payload)
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_entries(tmp)
    assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
    entry = entries[0]
    assert entry["tool_name"] == "Read", f"entry must record tool_name=Read; got {entry}"
    assert entry["source"] == "tool-call", f"entry must be tagged source=tool-call; got {entry}"
    assert entry["event"] == "PreToolUse", f"entry must record the hook event name; got {entry}"
    assert "ts" in entry and entry["ts"], f"entry must include a ts field; got {entry}"


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
