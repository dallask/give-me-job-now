#!/usr/bin/env python3
"""Unit tests for scripts/gmj_self_reflect_apply.py (D-07 apply-flow guardrails).

Runnable as a plain assertion script (no pytest dependency). Exercises the CLI via
subprocess against isolated temp directories (never the real repo's
``.planning/config.json``), per this repo's established test convention
(``tests/test_gmj_execution_log_writer.py``'s subprocess-driven shape).

Covers:
- Missing report: exits non-zero, never auto-generates the report as a side effect.
- Unknown ``--finding``: exits non-zero with a "not found in report" message.
- A valid, mechanically-applicable finding (``pycache-hook-log-pollution``) applies its
  one registered fix and is idempotent-safe on a second run (already-applied, exit 0).
- A prose-only / non-mechanical finding (``worktree-base-drift``) correctly refuses
  rather than fabricating an apply.
- This script never creates a git commit itself (commit ownership stays at the command
  layer per the plan's division of responsibility).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gmj_self_reflect_apply.py"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name} {detail}")


SAMPLE_REPORT = """# GSD Self-Reflection Findings Report

This report analyzes structured execution logs and names recurring behavioral patterns.

## pycache / hook-log self-inflicted test-gate pollution (`pycache-hook-log-pollution`)

**Occurrences:** 2

**Proposed fix:** Add __pycache__ and .claude/logs/*.log to the test runner's ignored-paths
list (or run tests with PYTHONDONTWRITEBYTECODE=1) so gate output never conflates
self-inflicted filesystem noise with a genuine assertion failure.

**Evidence:**

- 2026-07-12T07:20:03.400Z [Bash] test-gate failure: pycache recreated mid-run
- 2026-07-12T07:45:12.900Z [Bash] test-gate failure: hook-log mutated mid-test-run

## Worktree base drift (`worktree-base-drift`)

**Occurrences:** 3

**Proposed fix:** Before dispatching a wave of parallel worktree agents, snapshot and pin
the expected base commit SHA per agent, and have each agent assert its actual base against
the pinned SHA before its first commit.

**Evidence:**

- 2026-07-12T07:10:00.000Z [Bash] base has diverged from origin
- 2026-07-12T07:11:00.000Z [Bash] non-fast-forward push rejected
- 2026-07-12T07:12:00.000Z [SubagentStop] merge conflict detected during rebase

==========================================================================
STATUS: findings only — no fix was applied.
ACTION: run `/gsd-self-reflect --apply` to apply one proposed fix, atomically committed.
SAFETY: this tool has no fix-application code path at all (D-07).
==========================================================================
"""


def _make_workdir() -> Path:
    """Build an isolated temp repo-like dir with a report + a minimal config.json."""
    tmp = Path(tempfile.mkdtemp(prefix="gmj-self-reflect-apply-"))
    (tmp / "output" / "analysis").mkdir(parents=True, exist_ok=True)
    (tmp / "output" / "analysis" / "self-reflect-report.md").write_text(
        SAMPLE_REPORT, encoding="utf-8"
    )
    (tmp / ".planning").mkdir(parents=True, exist_ok=True)
    config = {
        "workflow": {
            "test_command": (
                'source .venv/bin/activate 2>/dev/null; FAIL=0; for t in tests/test_*.py; '
                'do python3 "$t" >/tmp/gsd_test_out_$$ 2>&1 && echo "PASS $t" || '
                '{ echo "FAIL $t"; FAIL=1; cat /tmp/gsd_test_out_$$; }; '
                'rm -f /tmp/gsd_test_out_$$; done; exit $FAIL'
            )
        }
    }
    (tmp / ".planning" / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return tmp


def run_apply(workdir: Path, *extra_args: str) -> subprocess.CompletedProcess:
    report_path = workdir / "output" / "analysis" / "self-reflect-report.md"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--report",
        str(report_path),
        "--repo-root",
        str(workdir),
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def test_missing_report_exits_nonzero_without_generating_it() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gmj-self-reflect-apply-missing-"))
    report_path = tmp / "output" / "analysis" / "self-reflect-report.md"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--report",
            str(report_path),
            "--repo-root",
            str(tmp),
            "--finding",
            "pycache-hook-log-pollution",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    check(
        "missing report exits non-zero",
        result.returncode != 0,
        f"(got {result.returncode}, stderr={result.stderr!r})",
    )
    check(
        "missing report never auto-generated as a side effect",
        not report_path.exists(),
    )
    check(
        "missing report stderr directs user to /gsd-self-reflect",
        "gsd-self-reflect" in result.stderr,
        f"(stderr={result.stderr!r})",
    )


def test_unknown_finding_exits_nonzero() -> None:
    workdir = _make_workdir()
    result = run_apply(workdir, "--finding", "totally-unknown-pattern-id")
    check(
        "unknown --finding exits non-zero",
        result.returncode != 0,
        f"(got {result.returncode})",
    )
    check(
        "unknown --finding stderr mentions 'not found'",
        "not found" in result.stderr.lower(),
        f"(stderr={result.stderr!r})",
    )


def test_valid_mechanical_finding_applies_and_is_idempotent() -> None:
    workdir = _make_workdir()
    config_path = workdir / ".planning" / "config.json"

    result1 = run_apply(workdir, "--finding", "pycache-hook-log-pollution")
    check(
        "valid mechanical finding exits zero",
        result1.returncode == 0,
        f"(got {result1.returncode}, stderr={result1.stderr!r})",
    )
    try:
        payload1 = json.loads(result1.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload1 = {}
    check(
        "valid mechanical finding prints structured applied JSON",
        payload1.get("status") == "applied",
        f"(stdout={result1.stdout!r})",
    )
    check(
        "applied JSON names the finding id",
        payload1.get("finding") == "pycache-hook-log-pollution",
    )
    check(
        "applied JSON lists files_changed",
        isinstance(payload1.get("files_changed"), list) and len(payload1["files_changed"]) >= 1,
    )

    updated_config = json.loads(config_path.read_text(encoding="utf-8"))
    check(
        "PYTHONDONTWRITEBYTECODE=1 present in test_command after apply",
        "PYTHONDONTWRITEBYTECODE=1" in updated_config["workflow"]["test_command"],
    )

    # Re-run: idempotent-safe, exit 0, "already applied" — never double-applies.
    result2 = run_apply(workdir, "--finding", "pycache-hook-log-pollution")
    check(
        "re-run of already-applied finding exits zero",
        result2.returncode == 0,
        f"(got {result2.returncode}, stderr={result2.stderr!r})",
    )
    try:
        payload2 = json.loads(result2.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        payload2 = {}
    check(
        "re-run reports already_applied status",
        payload2.get("status") == "already_applied",
        f"(stdout={result2.stdout!r})",
    )

    reconfirmed = json.loads(config_path.read_text(encoding="utf-8"))
    check(
        "re-run does not double-insert the env var",
        reconfirmed["workflow"]["test_command"].count("PYTHONDONTWRITEBYTECODE=1") == 1,
    )


def test_prose_only_finding_refuses_rather_than_fabricating() -> None:
    workdir = _make_workdir()
    result = run_apply(workdir, "--finding", "worktree-base-drift")
    check(
        "prose-only finding exits non-zero",
        result.returncode != 0,
        f"(got {result.returncode})",
    )
    check(
        "prose-only finding stderr explains manual judgment is required",
        "manual" in result.stderr.lower() or "judgment" in result.stderr.lower(),
        f"(stderr={result.stderr!r})",
    )


def test_script_never_creates_a_git_commit_itself() -> None:
    """The apply script must not shell out to `git commit`/`git add` — commit
    ownership stays at the command layer (.claude/commands/gsd-self-reflect.md),
    per the plan. Checks for actual invocation call-sites (subprocess/os.system
    calls referencing "git commit"/"git add"), not prose mentions in comments or
    docstrings describing this design constraint."""
    source = SCRIPT.read_text(encoding="utf-8")
    check(
        "script has no subprocess/os.system call invoking git commit",
        not re.search(r"(subprocess\.\w+|os\.system)\([^)]*git commit", source),
    )
    check(
        "script has no subprocess/os.system call invoking git add",
        not re.search(r"(subprocess\.\w+|os\.system)\([^)]*git add", source),
    )
    check(
        "script imports no subprocess module at all (no shell-out capability)",
        "import subprocess" not in source and "os.system" not in source,
    )


def main() -> int:
    test_missing_report_exits_nonzero_without_generating_it()
    test_unknown_finding_exits_nonzero()
    test_valid_mechanical_finding_applies_and_is_idempotent()
    test_prose_only_finding_refuses_rather_than_fabricating()
    test_script_never_creates_a_git_commit_itself()

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
