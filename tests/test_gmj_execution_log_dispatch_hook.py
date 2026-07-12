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
- Task 2 (Tests 6-9): bounds and auto-fires ``gmj_self_reflect.py`` against a small
  recent-file staging window (not the full unbounded log history), never passes ``--apply``,
  and never blocks even if the analyzer subprocess is unreachable/crashing.
- WR-03 regression tests: STATE.md discovery precedence between the top-level file and
  per-workstream candidates, keyed on most-recent mtime (CR-01 fix), not a hardcoded
  top-level-always-wins order.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-execution-log-dispatch.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution-logs"

STATE_EXECUTING = FIXTURES / "dispatch_state_executing.md"
STATE_MISSING_FRONTMATTER = FIXTURES / "dispatch_state_missing_frontmatter.md"
STATE_STALE_COMPLETE = FIXTURES / "dispatch_state_stale_complete.md"
NORMAL_RUN_JSONL = FIXTURES / "normal-run.jsonl"

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
    # WR-02 regression: --plan must stay null (this hook has no short plan-number
    # identifier source); the descriptive current_phase_name label is carried
    # separately as phase_name, not overloaded into plan.
    assert entry.get("plan") is None, f"plan must stay null (WR-02); got {entry}"
    assert entry.get("phase_name"), f"phase_name must be derived from fixture STATE.md; got {entry}"
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


# --------------------------------------------------- WR-03: discovery precedence tests


def _touch_older(path: Path, *, seconds_older_than: Path) -> None:
    """Set path's mtime to be strictly older than seconds_older_than's mtime."""
    reference_mtime = seconds_older_than.stat().st_mtime
    older_mtime = reference_mtime - 3600
    os.utime(path, (older_mtime, older_mtime))


def _touch_newer(path: Path, *, seconds_newer_than: Path) -> None:
    """Set path's mtime to be strictly newer than seconds_newer_than's mtime."""
    reference_mtime = seconds_newer_than.stat().st_mtime
    newer_mtime = reference_mtime + 3600
    os.utime(path, (newer_mtime, newer_mtime))


def test_workstream_state_md_used_when_no_top_level_state() -> None:
    """Fallback path: workstream STATE.md is discovered when no top-level STATE.md exists."""
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    ws_dir = tmp / ".planning" / "workstreams" / "testplan-gen"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws_state = ws_dir / "STATE.md"
    shutil.copy(STATE_EXECUTING, ws_state)
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block; got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_gsd_workflow_entries(tmp)
    assert len(entries) == 1, f"expected exactly one gsd-workflow JSONL entry; got {entries}"
    assert entries[0]["outcome"] == "pass", (
        f"outcome must be derived from the workstream STATE.md's executing status; got {entries[0]}"
    )


def test_active_workstream_state_preferred_over_stale_top_level_state() -> None:
    """Regression test for CR-01: an actively-executing workstream's STATE.md must not
    be shadowed by a stale/completed top-level STATE.md, regardless of the hardcoded
    top-level-first precedence CR-01 removed. Selection is by most-recent mtime."""
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_STALE_COMPLETE)
    top_level_state = tmp / ".planning" / "STATE.md"

    ws_dir = tmp / ".planning" / "workstreams" / "active-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws_state = ws_dir / "STATE.md"
    shutil.copy(STATE_EXECUTING, ws_state)

    # Force the workstream STATE.md to have a strictly newer mtime than the stale
    # top-level one, independent of filesystem copy-timing granularity.
    _touch_newer(ws_state, seconds_newer_than=top_level_state)

    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block; got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_gsd_workflow_entries(tmp)
    assert len(entries) == 1, f"expected exactly one gsd-workflow JSONL entry; got {entries}"
    assert entries[0]["outcome"] == "pass", (
        "must reflect the actively-executing workstream, not the stale top-level "
        f"STATE.md (outcome would be 'checkpoint' if the stale file won); got {entries[0]}"
    )


def test_stale_top_level_state_preferred_when_newer_than_workstream_state() -> None:
    """Inverse of the CR-01 regression: when the top-level STATE.md is genuinely the
    most-recently-modified candidate, it must still win (mtime-based selection, not an
    unconditional workstream-first flip)."""
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    ws_dir = tmp / ".planning" / "workstreams" / "active-ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws_state = ws_dir / "STATE.md"
    shutil.copy(STATE_EXECUTING, ws_state)

    _seed_state(tmp, STATE_STALE_COMPLETE)
    top_level_state = tmp / ".planning" / "STATE.md"

    # Force the top-level STATE.md to have a strictly newer mtime than the workstream one.
    _touch_newer(top_level_state, seconds_newer_than=ws_state)

    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block; got {result.returncode}\nstderr: {result.stderr}"
    )
    entries = _parsed_gsd_workflow_entries(tmp)
    assert len(entries) == 1, f"expected exactly one gsd-workflow JSONL entry; got {entries}"
    assert entries[0]["outcome"] == "checkpoint", (
        "must reflect the newer top-level STATE.md (status: 'Awaiting next milestone' maps "
        f"to outcome=checkpoint), not the older workstream STATE.md; got {entries[0]}"
    )


# --------------------------------------------------------------------------- Task 2 tests


def _seed_bounded_window_logs(tmp: Path) -> Path:
    """Seed today's tool-calls-<date>.jsonl with normal-run.jsonl content."""
    log_dir = tmp / ".planning" / "execution-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = log_dir / f"tool-calls-{today}.jsonl"
    shutil.copy(NORMAL_RUN_JSONL, dest)
    return log_dir


def test_auto_fire_invokes_self_reflect_and_writes_report() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_EXECUTING)
    _seed_bounded_window_logs(tmp)
    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block; got {result.returncode}\nstderr: {result.stderr}"
    )
    report_path = tmp / "output" / "analysis" / "self-reflect-report.md"
    assert report_path.is_file(), f"expected a self-reflect-report.md written at {report_path}"
    text = report_path.read_text(encoding="utf-8")
    assert text.strip(), f"report must be non-empty; got: {text!r}"
    assert "STATUS:" in text, f"report must contain the STATUS: footer line; got: {text!r}"


def test_auto_fire_window_is_bounded_not_full_history() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_EXECUTING)
    log_dir = tmp / ".planning" / "execution-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 5 distinct old dates (5+ days apart), each with a distinguishing marker command,
    # plus today's file seeded from normal-run.jsonl.
    now = datetime.now(timezone.utc)
    old_marker = "OLD_DATE_MARKER_COMMAND_should_not_appear_in_bounded_window"
    for i in range(1, 6):
        old_date = (now - timedelta(days=5 * i)).strftime("%Y-%m-%d")
        old_file = log_dir / f"tool-calls-{old_date}.jsonl"
        old_entry = {
            "ts": f"{old_date}T00:00:00.000Z",
            "source": "tool-call",
            "event": "PreToolUse",
            "tool_name": "Bash",
            "outcome": "observed",
            "artifacts": [],
            "command": old_marker,
        }
        old_file.write_text(json.dumps(old_entry) + "\n", encoding="utf-8")

    today = now.strftime("%Y-%m-%d")
    today_file = log_dir / f"tool-calls-{today}.jsonl"
    shutil.copy(NORMAL_RUN_JSONL, today_file)

    result = _run_in_dir(STOP_STDIN_JSON, tmp)
    assert result.returncode == 0, (
        f"hook must never block; got {result.returncode}\nstderr: {result.stderr}"
    )

    report_path = tmp / "output" / "analysis" / "self-reflect-report.md"
    assert report_path.is_file(), f"expected a self-reflect-report.md written at {report_path}"
    text = report_path.read_text(encoding="utf-8")
    assert old_marker not in text, (
        f"bounded window must NOT include 5-day-old-and-older files; found marker in report: {text!r}"
    )

    # Confirm the live log directory itself was never mutated (copy, not move).
    live_files = sorted(log_dir.glob("tool-calls-*.jsonl"))
    assert len(live_files) == 6, f"live log dir must retain all 6 original files; got {live_files}"


def test_auto_fire_never_blocks_on_crashing_analyzer() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dispatch-hook-"))
    _seed_state(tmp, STATE_EXECUTING)
    _seed_bounded_window_logs(tmp)

    # Point PATH at a directory containing only `sh` (symlinked from its real
    # location) and no `python3` at all, so the analyzer invocation itself cannot
    # even launch — while subprocess.run(["sh", ...]) can still resolve `sh`.
    sh_real = shutil.which("sh")
    assert sh_real, "test environment must have a resolvable `sh` on PATH"
    broken_path_dir = Path(tempfile.mkdtemp(prefix="broken-path-"))
    os.symlink(sh_real, broken_path_dir / "sh")
    result = _run_in_dir(
        STOP_STDIN_JSON,
        tmp,
        extra_env={"PATH": str(broken_path_dir)},
    )
    assert result.returncode == 0, (
        f"hook must never block even with a broken python3 PATH; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )


def test_auto_fire_never_passes_apply_flag() -> None:
    hook_source = HOOK.read_text(encoding="utf-8")
    # Static assertion: --apply must never appear anywhere in this hook's source,
    # belt-and-braces against ever accidentally triggering a fix-apply path.
    assert "--apply" not in hook_source, (
        "gmj-execution-log-dispatch.sh must never pass --apply to gmj_self_reflect.py "
        "(D-07 never-auto-apply constraint)"
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
