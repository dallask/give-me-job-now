#!/usr/bin/env python3
"""Unit + correlation integration tests for scripts/gmj_execution_log_writer.py
(D-01/D-03, REFLECT-01, REFLECT-03).

Runnable as a plain assertion script (no pytest dependency), mirroring
``tests/test_gmj_execution_log_hook.py``'s subprocess-driven shape from Plan 02.

Proves:
- A valid ``--point``/``--outcome`` invocation appends exactly one well-formed
  JSONL entry to ``.planning/execution-logs/gsd-workflow-<date>.jsonl`` with all
  required fields (ts, source=gsd-workflow, point, phase, plan, wave, outcome).
- An invalid ``--outcome`` value exits non-zero with a stderr message (CLI usage
  error — fail loud, distinct from a runtime/environment failure).
- An unwritable log-dir (a file where a directory is expected) degrades to exit 0
  with a stderr warning rather than crashing (D-09).
- Task 2: both ``tool-calls-<date>.jsonl`` (Plan 02's hook) and
  ``gsd-workflow-<date>.jsonl`` (this writer) coexist in one directory, every line
  across both files has both a ``ts`` and a ``source`` field, and glob-read-and-
  sort-by-``ts`` produces one coherent chronological stream across both sources.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRITER = REPO_ROOT / "scripts" / "gmj_execution_log_writer.py"
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-execution-log.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution-logs"

GSD_WORKFLOW_FIXTURE = FIXTURES / "gsd_workflow_execute_post.json"
PRETOOLUSE_BASH = FIXTURES / "pretooluse_bash.json"


def _run_writer(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRITER), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else str(REPO_ROOT),
    )


def _log_files(log_dir: Path, pattern: str) -> list[Path]:
    if not log_dir.is_dir():
        return []
    return sorted(log_dir.glob(pattern))


def _parsed_entries(log_dir: Path, pattern: str) -> list[dict]:
    entries: list[dict] = []
    for log_file in _log_files(log_dir, pattern):
        text = log_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def test_valid_invocation_writes_wellformed_jsonl_entry() -> None:
    fixture = json.loads(GSD_WORKFLOW_FIXTURE.read_text(encoding="utf-8"))
    cli_args = fixture["cli_args"]
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            [
                "--point", cli_args["point"],
                "--phase", cli_args["phase"],
                "--plan", cli_args["plan"],
                "--wave", cli_args["wave"],
                "--outcome", cli_args["outcome"],
                "--log-dir", str(log_dir),
            ]
        )
        assert result.returncode == 0, (
            f"valid invocation must exit 0; got {result.returncode}\nstderr: {result.stderr}"
        )
        entries = _parsed_entries(log_dir, "gsd-workflow-*.jsonl")
        assert len(entries) == 1, f"expected exactly one JSONL entry; got {len(entries)}: {entries}"
        entry = entries[0]
        expected = fixture["expected_entry_fields"]
        for key, value in expected.items():
            assert entry.get(key) == value, (
                f"entry field {key!r} mismatch: expected {value!r}, got {entry.get(key)!r} "
                f"(full entry: {entry})"
            )
        assert "ts" in entry and entry["ts"], f"entry must include a ts field; got {entry}"


def test_nullable_plan_wave_for_ship_post() -> None:
    # ship:post has no plan/wave context — must be nullable, not a hard requirement.
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            ["--point", "ship:post", "--outcome", "pass", "--log-dir", str(log_dir)]
        )
        assert result.returncode == 0, (
            f"ship:post with no phase/plan/wave must still succeed; got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        entries = _parsed_entries(log_dir, "gsd-workflow-*.jsonl")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["point"] == "ship:post"
        assert entry["phase"] is None
        assert entry["plan"] is None
        assert entry["wave"] is None


def test_invalid_outcome_exits_nonzero_with_stderr_message() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            ["--point", "execute:post", "--outcome", "not-a-real-outcome", "--log-dir", str(log_dir)]
        )
        assert result.returncode != 0, (
            f"invalid --outcome must exit non-zero (CLI usage error); got {result.returncode}"
        )
        assert result.stderr.strip(), "invalid --outcome must print a clear stderr message"
        assert not _log_files(log_dir, "gsd-workflow-*.jsonl"), (
            "invalid --outcome must not write any log entry"
        )


def test_invalid_point_exits_nonzero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            ["--point", "not-a-real-point", "--outcome", "pass", "--log-dir", str(log_dir)]
        )
        assert result.returncode != 0, (
            f"invalid --point must exit non-zero (CLI usage error); got {result.returncode}"
        )


def test_unwritable_log_dir_degrades_to_exit_zero_with_warning() -> None:
    # A file where a directory is expected: mkdir(parents=True, exist_ok=True) will
    # raise FileExistsError/NotADirectoryError under the hood -- must degrade
    # gracefully (D-09), never crash or exit non-zero.
    with tempfile.TemporaryDirectory() as tmp:
        blocking_file = Path(tmp) / "not-a-directory"
        blocking_file.write_text("i am a file, not a directory\n", encoding="utf-8")
        result = _run_writer(
            ["--point", "execute:post", "--outcome", "pass", "--log-dir", str(blocking_file)]
        )
        assert result.returncode == 0, (
            f"unwritable log-dir must degrade to exit 0 (D-09), never crash; "
            f"got {result.returncode}\nstderr: {result.stderr}"
        )
        assert result.stderr.strip(), (
            "unwritable log-dir must print a stderr warning even though it exits 0"
        )


def test_malformed_extra_json_is_ignored_not_fatal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            [
                "--point", "execute:post",
                "--outcome", "pass",
                "--log-dir", str(log_dir),
                "--extra-json", "{not valid json",
            ]
        )
        assert result.returncode == 0, (
            f"malformed --extra-json must not be fatal (T-06-03-02); got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        entries = _parsed_entries(log_dir, "gsd-workflow-*.jsonl")
        assert len(entries) == 1
        # No stray "not valid json"-derived key should have leaked into the entry.
        assert set(entries[0].keys()) >= {"ts", "source", "point", "outcome"}


def test_valid_extra_json_is_merged_into_entry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "execution-logs"
        result = _run_writer(
            [
                "--point", "execute:post",
                "--outcome", "pass",
                "--log-dir", str(log_dir),
                "--extra-json", json.dumps({"artifacts": ["scripts/gmj_execution_log_writer.py"]}),
            ]
        )
        assert result.returncode == 0
        entries = _parsed_entries(log_dir, "gsd-workflow-*.jsonl")
        assert len(entries) == 1
        assert entries[0].get("artifacts") == ["scripts/gmj_execution_log_writer.py"]


def test_dual_source_logs_coexist_and_correlate_by_ts() -> None:
    """Task 2: prove correlatable dual-source log output end-to-end.

    Within one isolated temp .planning/execution-logs/ dir, invoke both Plan 02's
    hook (tool-calls-<date>.jsonl) and this plan's writer (gsd-workflow-<date>.jsonl),
    then assert both files exist side by side, every line across both has both a
    `ts` and a `source` field with value "tool-call" or "gsd-workflow", and sorting
    all lines from both files by `ts` produces one coherent chronological stream.
    """
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        log_dir = project_dir / ".planning" / "execution-logs"

        # Invoke Plan 02's hook (writes tool-calls-<date>.jsonl under
        # CLAUDE_PROJECT_DIR/.planning/execution-logs/).
        hook_result = subprocess.run(
            ["sh", str(HOOK)],
            input=PRETOOLUSE_BASH.read_text(encoding="utf-8"),
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)},
        )
        assert hook_result.returncode == 0, (
            f"Plan 02's hook must not block; got {hook_result.returncode}\n"
            f"stderr: {hook_result.stderr}"
        )

        # Invoke this plan's writer against the SAME log_dir.
        writer_result = _run_writer(
            [
                "--point", "execute:post",
                "--phase", "6",
                "--plan", "03",
                "--wave", "2",
                "--outcome", "pass",
                "--log-dir", str(log_dir),
            ]
        )
        assert writer_result.returncode == 0, (
            f"writer must succeed; got {writer_result.returncode}\nstderr: {writer_result.stderr}"
        )

        tool_call_files = _log_files(log_dir, "tool-calls-*.jsonl")
        gsd_workflow_files = _log_files(log_dir, "gsd-workflow-*.jsonl")
        assert tool_call_files, f"expected a tool-calls-<date>.jsonl file under {log_dir}"
        assert gsd_workflow_files, f"expected a gsd-workflow-<date>.jsonl file under {log_dir}"

        all_entries: list[dict] = []
        all_entries.extend(_parsed_entries(log_dir, "tool-calls-*.jsonl"))
        all_entries.extend(_parsed_entries(log_dir, "gsd-workflow-*.jsonl"))
        assert len(all_entries) == 2, f"expected exactly 2 entries total; got {len(all_entries)}"

        sources_seen = set()
        for entry in all_entries:
            assert "ts" in entry and entry["ts"], f"every entry must have a ts field; got {entry}"
            assert entry.get("source") in ("tool-call", "gsd-workflow"), (
                f"every entry's source must be tool-call or gsd-workflow; got {entry}"
            )
            sources_seen.add(entry["source"])
        assert sources_seen == {"tool-call", "gsd-workflow"}, (
            f"expected both sources represented; got {sources_seen}"
        )

        # Glob-read-and-sort-by-ts produces one coherent chronological interleaving
        # (proof of D-03's interpretation, not merely independent-file existence).
        sorted_entries = sorted(all_entries, key=lambda e: e["ts"])
        assert len(sorted_entries) == len(all_entries), "sort must not drop any entry"
        # Sorting is stable and total: every entry has a comparable ISO8601 ts.
        timestamps = [e["ts"] for e in sorted_entries]
        assert timestamps == sorted(timestamps), "ts-sorted order must be monotonic"


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
