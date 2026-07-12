#!/usr/bin/env python3
"""Integration tests for the gmj-execution-log-dispatch Stop-event hook (06-06,
REFLECT-01/REFLECT-03/REFLECT-05 — closes Gap 1/D-01 dispatch and Gap 2/D-05 auto-fire).

Runnable as a plain assertion script (no pytest dependency). Feeds fixture Stop stdin
payloads to ``.claude/hooks/gmj-execution-log-dispatch.sh`` as a subprocess and proves the
EXECUTED hook — not an agent self-report:

- Task 1 (Tests 1-5): derives phase/plan/outcome from a fixture STATE.md and shells out to
  ``gmj_execution_log_writer.py``, writing a ``gsd-workflow``-tagged JSONL entry with
  ``point: "execute:post"``, and NEVER returns a blocking exit code under any input
  (missing STATE.md, malformed frontmatter).

The hook runs with ``CLAUDE_PROJECT_DIR`` pointed at an isolated temp dir, so assertions
never touch the real repo's ``.planning/`` or ``output/`` trees.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-execution-log-dispatch.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution-logs"

STATE_EXECUTING = FIXTURES / "dispatch_state_executing.md"
STATE_MISSING_FRONTMATTER = FIXTURES / "dispatch_state_missing_frontmatter.md"

STOP_STDIN_JSON = json.dumps({"hook_event_name": "Stop"})


def _run_in_dir(
    stdin_text: str,
    tmp: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook in an isolated CLAUDE_PROJECT_DIR temp dir."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp)}
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["sh", str(HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=60,
    )
    return result


def _seed_state(tmp: Path, fixture: Path) -> None:
    planning_dir = tmp / ".planning"
    planning_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture, planning_dir / "STATE.md")


def _gsd_workflow_log_files(tmp: Path) -> list[Path]:
    log_dir = tmp / ".planning" / "execution-logs"
    if not log_dir.is_dir():
        return []
    return sorted(log_dir.glob("gsd-workflow-*.jsonl"))


def _parsed_gsd_workflow_entries(tmp: Path) -> list[dict]:
    entries: list[dict] = []
    for log_file in _gsd_workflow_log_files(tmp):
        text = log_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))  # must be valid JSON — no try/except here
    return entries


# --------------------------------------------------------------------------- Task 1 tests


def test_stop_event_writes_gsd_workflow_entry() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_EXECUTING)
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_gsd_workflow_entries(tmp)
    assert len(entries) == 1, f"expected exactly one gsd-workflow JSONL entry; got {entries}"
    entry = entries[0]
    assert entry["source"] == "gsd-workflow", f"entry must be source=gsd-workflow; got {entry}"
    assert entry.get("phase"), f"phase must be derived from fixture STATE.md; got {entry}"
    assert entry.get("plan") is not None, f"plan must be derived (non-null); got {entry}"
    assert entry["outcome"] in ("pass", "fail", "halt", "checkpoint"), (
        f"outcome must be in the 4-word vocabulary; got {entry}"
    )
    assert entry["outcome"] == "pass", f"status: executing must map to outcome=pass; got {entry}"


def test_missing_state_md_never_blocks() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    # No STATE.md seeded at all.
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block on missing STATE.md; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "Traceback" not in result.stderr, f"hook must never crash-trace; stderr: {result.stderr}"
    entries = _parsed_gsd_workflow_entries(tmp)
    # Either an entry with phase/plan both null and outcome checkpoint, or nothing at all.
    if entries:
        assert len(entries) == 1, f"expected at most one entry; got {entries}"
        entry = entries[0]
        assert entry.get("phase") is None, f"phase must be null when STATE.md is absent; got {entry}"
        assert entry.get("plan") is None, f"plan must be null when STATE.md is absent; got {entry}"
        assert entry.get("outcome") == "checkpoint", f"outcome must be checkpoint; got {entry}"


def test_malformed_state_md_frontmatter_never_blocks() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_MISSING_FRONTMATTER)
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block on malformed STATE.md; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "Traceback" not in result.stderr, f"hook must never crash-trace; stderr: {result.stderr}"
    # Any line written must be valid JSON — re-parse every line (this raises if invalid).
    entries = _parsed_gsd_workflow_entries(tmp)
    for entry in entries:
        assert isinstance(entry, dict), f"every written line must be a valid JSON object; got {entry}"


def test_writer_invocation_uses_execute_post_point() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_EXECUTING)
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, f"hook must never block; got {result.returncode}"
    entries = _parsed_gsd_workflow_entries(tmp)
    assert len(entries) == 1, f"expected exactly one entry; got {entries}"
    assert entries[0]["point"] == "execute:post", (
        f"point must be the literal best-effort approximation 'execute:post'; got {entries[0]}"
    )


def test_hook_never_returns_blocking_exit_code() -> None:
    for fixture in (STATE_EXECUTING, STATE_MISSING_FRONTMATTER, None):
        tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
        if fixture is not None:
            _seed_state(tmp, fixture)
        result = _run_in_dir(STOP_STDIN_JSON, tmp)
        assert result.returncode == 0, (
            f"hook must never return a blocking exit code for fixture={fixture}; "
            f"got {result.returncode}\nstderr: {result.stderr}"
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
