#!/usr/bin/env python3
"""Integration tests for the gmj-firecrawl-scope-guard PreToolUse hook (SEARCH-07).

Runnable as a plain assertion script (no pytest dependency). Feeds fixture stdin
payloads to ``.claude/hooks/gmj-firecrawl-scope-guard.sh`` as a subprocess and proves
the EXECUTED hook — not an agent self-report — enforces ``config/sources.yaml``
scope on every Bash-invoked ``scripts/offers/gmj_firecrawl_search.py`` call:

- an in-scope ``--url`` (host under ``config/sources.yaml`` sites) is allowed (exit 0),
- an out-of-scope ``--url`` (host not in the allow-list) is blocked (exit 2) — this is
  SEARCH-07's mandatory negative test,
- a Bash command NOT invoking ``gmj_firecrawl_search.py`` is an early pass-through
  (exit 0, no log entry written) — the hook never interferes with unrelated Bash usage,
- a search-mode ``--query`` that explicitly pins an off-allow-list domain via a
  ``site:`` token is blocked (exit 2), mirroring the existing WebSearch behavior.

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
HOOK = REPO_ROOT / ".claude" / "hooks" / "gmj-firecrawl-scope-guard.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCES_YAML = REPO_ROOT / "config" / "sources.yaml"

IN_SCOPE = FIXTURES / "firecrawl_bash_in_scope.json"
OUT_OF_SCOPE = FIXTURES / "firecrawl_bash_out_of_scope.json"
NON_FIRECRAWL = FIXTURES / "firecrawl_bash_non_firecrawl.json"

# Query-mode off-list domain pin — a minor variant of the search-mode shape, inlined
# here rather than as a fifth fixture file (plan's stated discretion).
QUERY_OFFLIST_PIN = (
    '{"tool_name": "Bash", "tool_input": {"command": '
    '"python3 scripts/offers/gmj_firecrawl_search.py --mode search '
    '--query \\"FPV Engineer site:evil-untrusted-board.example.com\\""}}'
)

# A command whose text merely MENTIONS the script's filename in prose (e.g. a git
# commit message describing a change to it) without invoking it. Regression fixture
# for a real bug found during Phase 48 execution: the hook's original filename-
# substring `case` match fired on this shape and blocked an unrelated `git commit`.
MENTION_ONLY_NOT_INVOCATION = (
    '{"tool_name": "Bash", "tool_input": {"command": '
    '"git commit -m \\"fix: regenerate payload manifest for gmj_firecrawl_search.py\\""}}'
)

# A command that references the script's PATH as an argument to another command
# (git add, cat, an editor) — not an invocation. Second regression fixture: an
# earlier fix attempt matched any path-qualified mention of the filename, which
# still falsely fired on `git add gmj-core/scripts/offers/gmj_firecrawl_search.py`.
PATH_REFERENCE_NOT_INVOCATION = (
    '{"tool_name": "Bash", "tool_input": {"command": '
    '"git add gmj-core/scripts/offers/gmj_firecrawl_search.py"}}'
)

# A real invocation with an interpreter FLAG between python3 and the script path,
# targeting an off-allow-list host. Third regression fixture, this one for a
# fail-OPEN bug (not fail-closed like the two above) found by code review: the
# prior regex required the script path immediately after python3/python with a
# single whitespace run, so `python3 -u ...gmj_firecrawl_search.py --url <evil>`
# slipped past the second early pass-through entirely (exit 0, no log, no scope
# check) even though it is a genuine, malicious-target invocation.
INTERPRETER_FLAG_BYPASS_OFFLIST = (
    '{"tool_name": "Bash", "tool_input": {"command": '
    '"python3 -u scripts/offers/gmj_firecrawl_search.py --mode scrape '
    '--url https://evil-untrusted-board.example.com/job/1"}}'
)

# A real invocation with a VALUE-TAKING interpreter flag (the flag and its value are
# two separate tokens, e.g. `-X utf8`) between python3 and the script path, targeting
# an off-allow-list host. Fourth regression fixture, for a second fail-OPEN bug found
# by code review after the -u fix: the boolean-flags-only regex from that fix matched
# `-u`/`-B`/`-O` (single tokens) but not `-X utf8`/`-W ignore` (flag + separate value
# token), so this shape still slipped past the second early pass-through entirely.
INTERPRETER_VALUE_FLAG_BYPASS_OFFLIST = (
    '{"tool_name": "Bash", "tool_input": {"command": '
    '"python3 -X utf8 scripts/offers/gmj_firecrawl_search.py --mode scrape '
    '--url https://evil-untrusted-board.example.com/job/1"}}'
)


def _run_in_dir(stdin_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the hook in an isolated CLAUDE_PROJECT_DIR seeded with config/sources.yaml.

    Returns (result, tmp_dir) so callers can reach the firecrawl-scope.log under
    ``tmp_dir/.claude/logs/``. No credentials.yaml is needed for this hook.
    """
    tmp = Path(tempfile.mkdtemp(prefix="firecrawl-scope-guard-"))
    (tmp / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(SOURCES_YAML, tmp / "config" / "sources.yaml")
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
    return result, tmp / ".claude" / "logs" / "firecrawl-scope.log"


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


def test_in_scope_firecrawl_bash_allowed() -> None:
    result, log = _run(_read_payload(IN_SCOPE))
    assert result.returncode == 0, (
        f"in-scope Firecrawl Bash --url call must be allowed (exit 0); "
        f"got {result.returncode}\nstderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "ALLOWED" in log.read_text(encoding="utf-8")


def test_out_of_scope_firecrawl_bash_blocked() -> None:
    result, log = _run(_read_payload(OUT_OF_SCOPE))
    assert result.returncode == 2, (
        f"out-of-scope Firecrawl Bash --url call must be blocked (exit 2); "
        f"got {result.returncode}\nstderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "BLOCK" in log.read_text(encoding="utf-8")


def test_non_firecrawl_bash_passthrough() -> None:
    result, tmp = _run_in_dir(_read_payload(NON_FIRECRAWL))
    assert result.returncode == 0, (
        f"a Bash command NOT invoking gmj_firecrawl_search.py must pass through "
        f"(exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    log_path = tmp / ".claude" / "logs" / "firecrawl-scope.log"
    # True pass-through: either the log file is absent, or (if created by mkdir -p
    # elsewhere) it has no content written for this call — never a silent-allow entry.
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        assert text == "", (
            f"unrelated Bash command must write NO log entry (true pass-through, "
            f"not silent-allow); got:\n{text}"
        )


def test_filename_mention_without_invocation_passes_through() -> None:
    result, tmp = _run_in_dir(MENTION_ONLY_NOT_INVOCATION)
    assert result.returncode == 0, (
        "a command that only MENTIONS gmj_firecrawl_search.py in text (e.g. a git "
        "commit message) — without invoking it via python3/a path-qualified call — "
        f"must pass through (exit 0); got {result.returncode}\nstderr: {result.stderr}"
    )
    log_path = tmp / ".claude" / "logs" / "firecrawl-scope.log"
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        assert text == "", (
            f"a filename mention with no invocation must write NO log entry "
            f"(true pass-through); got:\n{text}"
        )


def test_path_reference_without_invocation_passes_through() -> None:
    result, tmp = _run_in_dir(PATH_REFERENCE_NOT_INVOCATION)
    assert result.returncode == 0, (
        "a command that references the script's path as an argument to another "
        "command (e.g. `git add <path>`) — without a python3/python interpreter "
        f"invocation — must pass through (exit 0); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    log_path = tmp / ".claude" / "logs" / "firecrawl-scope.log"
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        assert text == "", (
            f"a path reference with no invocation must write NO log entry "
            f"(true pass-through); got:\n{text}"
        )


def test_interpreter_flag_invocation_still_scoped() -> None:
    result, log = _run(INTERPRETER_FLAG_BYPASS_OFFLIST)
    assert result.returncode == 2, (
        "an off-allow-list Firecrawl invocation with an interpreter flag "
        "(e.g. `python3 -u ...gmj_firecrawl_search.py --url <evil>`) must still "
        f"be blocked (exit 2), not silently pass through; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "BLOCK" in log.read_text(encoding="utf-8")


def test_interpreter_value_flag_invocation_still_scoped() -> None:
    result, log = _run(INTERPRETER_VALUE_FLAG_BYPASS_OFFLIST)
    assert result.returncode == 2, (
        "an off-allow-list Firecrawl invocation with a value-taking interpreter flag "
        "(e.g. `python3 -X utf8 ...gmj_firecrawl_search.py --url <evil>`) must still "
        f"be blocked (exit 2), not silently pass through; got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    _assert_read_logged_before_decision(log)
    assert "BLOCK" in log.read_text(encoding="utf-8")


def test_query_mode_offlist_domain_pin_blocked() -> None:
    result, tmp = _run_in_dir(QUERY_OFFLIST_PIN)
    assert result.returncode == 2, (
        f"a --query explicitly pinning an off-allow-list domain via site: must be "
        f"blocked (exit 2); got {result.returncode}\nstderr: {result.stderr}"
    )
    log_path = tmp / ".claude" / "logs" / "firecrawl-scope.log"
    _assert_read_logged_before_decision(log_path)
    assert "BLOCK" in log_path.read_text(encoding="utf-8")


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
