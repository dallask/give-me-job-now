#!/usr/bin/env python3
"""Doc-lint for .claude/commands/gmj-runs.md (ERGO-02, ERGO-03, ERGO-04 persona invariants).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_runs_persona.py``. This is a DOC-LINT: it loads the persona
markdown as TEXT and asserts the load-bearing clauses are present, each with a specific
sentinel so a deleted clause fails loudly. It is NOT an LLM green-gate — it never runs the
persona or judges output quality; it only proves the persona *states* the invariants that
keep the inspector safe:

- frontmatter grants ``Bash(*)`` but does NOT grant the orchestration (Task) tool — the
  INVERSION of test_gmj_batch_persona.py, which asserts ``Task(*)`` is present (T-16-07),
- names the CLI ``gmj_runs.py`` and its four subcommands + the ``--json`` flag (ERGO-02),
- states it is read-only and never executes a resume (ERGO-04 / T-16-08),
- surfaces both resume commands ``/gmj-pipeline-run`` and ``/gmj-batch --resume`` (ERGO-03).

Discipline: every assertion carries a message naming the missing sentinel, so a removed
clause fails with a readable reason (not a bare AssertionError).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA = REPO_ROOT / ".claude" / "commands" / "gmj-runs.md"


def _persona_text() -> str:
    if not PERSONA.is_file():
        raise AssertionError(f"persona not found: {PERSONA}")
    return PERSONA.read_text(encoding="utf-8")


def _frontmatter(text: str) -> str:
    """Return the frontmatter slice (between the first two ``---`` fences)."""
    parts = text.split("---")
    assert len(parts) >= 3, "persona must have a frontmatter block delimited by two '---' fences"
    return parts[1]


def test_frontmatter_grants_bash_not_task() -> None:
    t = _persona_text()
    fm = _frontmatter(t)
    assert "Bash(*)" in fm, "frontmatter allowed-tools must grant Bash(*) (shells to the CLI)"
    # INVERSION of gmj-batch: the read-only inspector must NOT hold the orchestration tool.
    assert "Task(" not in fm, (
        "frontmatter must NOT grant the orchestration (Task) tool — /gmj-runs is a "
        "read-only inspector, not a hub (T-16-07)"
    )


def test_names_the_cli_and_subcommands() -> None:
    t = _persona_text()
    for sentinel in (
        "gmj_runs.py",
        "runs list",
        "run inspect",
        "batches list",
        "batch inspect",
        "--json",
    ):
        assert sentinel in t, f"persona must name the CLI surface {sentinel!r} (ERGO-02)"


def test_states_read_only_and_never_executes_resume() -> None:
    t = _persona_text()
    assert "read-only" in t, "persona must state it is read-only (ERGO-04)"
    assert "never" in t and "resume" in t, (
        "persona must state it never executes a resume (ERGO-04 / T-16-08)"
    )


def test_surfaces_both_resume_commands() -> None:
    t = _persona_text()
    assert "/gmj-pipeline-run" in t, "persona must surface the run resume command /gmj-pipeline-run (ERGO-03)"
    assert "/gmj-batch --resume" in t, (
        "persona must surface the batch resume command /gmj-batch --resume (ERGO-03)"
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
