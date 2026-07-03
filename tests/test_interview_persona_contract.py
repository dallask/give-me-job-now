#!/usr/bin/env python3
"""Doc-lint over the /gmj-interview persona (mechanical INTERVIEW-04/05).

Runnable as a plain assertion script (no pytest dependency), mirroring the
``main()`` collector convention of ``tests/test_sources_scope_guard.py``. These
cases assert the *mechanical* invariants of ``.claude/commands/gmj-interview.md``
— the tool restriction and the four hard rules encoded in its prose — so the
live conversational behavior can stay UAT (repo discipline: never a boolean LLM
green-gate).

Asserted invariants:
- the frontmatter OMITS ``Task`` and ``Edit`` and GRANTS ``AskUserQuestion`` /
  ``Read`` / ``Write`` / ``Bash`` (standalone persona, not the hub),
- the body states it NEVER writes ``candidate.yaml`` and routes profile facts to
  ``candidate-configurator``,
- it emits the ``candidate_findings_v1`` / ``candidate_findings.json`` contract,
- it reads the profile + coverage manifest before questioning,
- it advises when ``sources/candidate`` is empty,
- it runs the ``validate_preferences.py`` pre-write guard,
- it hands off (no ``Task(`` spawn) via ``/job-collective``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CMD = REPO_ROOT / ".claude" / "commands" / "gmj-interview.md"


def _text() -> str:
    return CMD.read_text(encoding="utf-8")


def _frontmatter() -> str:
    """Return the ``---``-fenced frontmatter block (the second split segment)."""
    parts = _text().split("---")
    assert len(parts) >= 3, f"{CMD} must have a ---fenced frontmatter block"
    return parts[1]


def test_persona_file_exists() -> None:
    assert CMD.is_file(), f"persona not found at {CMD}"


def test_persona_omits_task_and_edit() -> None:
    fm = _frontmatter()
    assert "Task" not in fm, "frontmatter must OMIT Task (standalone persona, not the hub)"
    assert "Edit" not in fm, "frontmatter must OMIT Edit (never writes candidate.yaml)"
    assert "AskUserQuestion" in fm, "frontmatter must grant AskUserQuestion"


def test_persona_grants_needed_tools() -> None:
    fm = _frontmatter()
    for tool in ("Read", "Write", "Bash"):
        assert tool in fm, f"frontmatter must grant {tool}"


def test_persona_write_scoped_excludes_candidate_yaml() -> None:
    """Write/Bash grants must be SCOPED, never unrestricted.

    A top-level persona structurally holds Write, so containment cannot rely on prose
    alone: the frontmatter must scope Write to the declared surface
    (``config/preferences.yaml`` + ``sources/analysis/*``) and must NOT grant a path that
    reaches the master profile. An unrestricted ``Bash(*)`` is equally disqualifying — a
    stray shell can open ``config/candidate.yaml`` for writing.
    """
    fm = _frontmatter()
    assert "Write(*)" not in fm, (
        "frontmatter must NOT grant unrestricted Write(*) — scope it to "
        "Write(config/preferences.yaml) + Write(sources/analysis/*)"
    )
    assert "Bash(*)" not in fm, (
        "frontmatter must NOT grant unrestricted Bash(*) — an unscoped shell can write "
        "config/candidate.yaml; scope Bash to the validate_preferences.py invocation"
    )
    assert "Write(config/preferences.yaml)" in fm, (
        "frontmatter must scope Write to config/preferences.yaml"
    )
    assert "Write(sources/analysis/*)" in fm, (
        "frontmatter must scope Write to sources/analysis/*"
    )
    # No granted Write path may resolve to the master profile or its language overlays.
    assert "Write(config/candidate.yaml)" not in fm, "must never grant Write to candidate.yaml"
    assert "Write(config/candidate." not in fm, (
        "must never grant Write to a config/candidate.* overlay"
    )


def test_persona_declares_never_writes_candidate_profile() -> None:
    """Prose must explicitly forbid writing the master profile AND its language overlays."""
    src = _text()
    lowered = src.lower()
    assert "never" in lowered and "config/candidate.yaml" in src, (
        "must declare it NEVER writes config/candidate.yaml (single source of truth)"
    )
    assert "config/candidate.*.yaml" in src, (
        "must explicitly name the config/candidate.*.yaml language overlays it never writes"
    )


def test_persona_states_write_routing() -> None:
    src = _text()
    assert "candidate-configurator" in src, "must route profile facts to candidate-configurator"
    assert "never" in src.lower() and "candidate.yaml" in src, (
        "must state it never writes candidate.yaml (source of truth)"
    )


def test_persona_emits_findings_contract() -> None:
    src = _text()
    assert "candidate_findings_v1" in src, "must emit the candidate_findings_v1 schema"
    assert "candidate_findings.json" in src, "must name the candidate_findings.json artifact"


def test_persona_reads_inputs_first() -> None:
    src = _text()
    assert "candidate_coverage_manifest.json" in src, "must read the coverage manifest first"
    assert "config/candidate.yaml" in src, "must read config/candidate.yaml first"


def test_persona_has_empty_sources_advisory() -> None:
    src = _text()
    assert "sources/candidate" in src, "must reference the sources/candidate intake dir"
    assert "advise" in src.lower() or "add source" in src.lower(), (
        "must advise adding source docs when sources/candidate is empty"
    )


def test_persona_runs_validator_guard() -> None:
    src = _text()
    assert "validate_preferences.py" in src, "must run validate_preferences.py as a pre-write guard"


def test_persona_no_task_spawn() -> None:
    src = _text()
    assert "Task(" not in src, "persona must not contain a Task( spawn (holds no delegation tool)"
    handoff = "/job-collective" in src or "hand off" in src.lower() or "handoff" in src.lower()
    assert handoff, "persona must state a handoff cue (/job-collective or hand off/handoff)"


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
