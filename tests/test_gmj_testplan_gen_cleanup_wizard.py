#!/usr/bin/env python3
"""Drift guard for the committed docs/test-plans/cleanup-wizard.md (TPGEN-03/TPGEN-04).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_testplan_gen_cleanup_wizard.py``. Mirrors
``tests/test_gmj_cleanup_wizard.py``'s and ``tests/test_gmj_testplan_gen.py``'s shape: a
``main()`` that runs every ``test_*`` function, catches and reports any uncaught exception
as FAIL, and exits 1 on any failure / 0 if all pass, printing which specific field/assertion
failed rather than a bare ``AssertionError``.

This is the mechanically-checkable proof Phase 2's proof-of-concept claim ("static
templating alone produced a spec-conformant plan") rests on: it proves the *committed*
``docs/test-plans/cleanup-wizard.md`` is exactly what today's ``extract()``/``render()``
pipeline produces from the real ``.claude/commands/gmj-cleanup-wizard.md`` -- never a
hand-edited or stale copy that has silently diverged from the generator (T-02-08).

This is a scoped, single-flow precursor to Phase 5's ``tests/test_testplans_current.py``
drift-detection gate (TPGEN-09/10, out of this phase's scope) -- it proves today's committed
file matches today's generator, not that it will stay in sync forever; the general-purpose
drift gate across all 10 flows is Phase 5's own deliverable.

HARD CONSTRAINT: this file only reads from the real repo (the committed
``docs/test-plans/cleanup-wizard.md`` and ``.claude/commands/gmj-cleanup-wizard.md``); it
never writes anywhere under the real repo tree.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_testplan_gen as g  # noqa: E402  (module under test)

_COMMAND_FILE = REPO_ROOT / ".claude" / "commands" / "gmj-cleanup-wizard.md"
_COMMITTED_FILE = REPO_ROOT / "docs" / "test-plans" / "cleanup-wizard.md"

# The generator was invoked from the repo root with this exact relative path (per the
# real CLI command in 02-03-PLAN.md's <action>), which becomes the IR's `source_file` and
# is embedded verbatim in the rendered Expected/provenance-note text. extract() must be
# called with this same relative form here so the byte-identity comparison below is a true
# apples-to-apples check against what actually produced the committed file -- an absolute
# path would produce a different (still-correct, but non-identical) `source_file` string.
_COMMAND_FILE_RELATIVE = Path(".claude") / "commands" / "gmj-cleanup-wizard.md"


def _committed_text() -> str:
    assert _COMMITTED_FILE.is_file(), (
        f"committed test-plan file missing: {_COMMITTED_FILE} -- run "
        f"`python3 scripts/gmj_testplan_gen.py --command-file {_COMMAND_FILE} "
        f"--output {_COMMITTED_FILE}` and commit the result"
    )
    return _COMMITTED_FILE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- Test 1: byte-identity

def test_committed_file_is_byte_identical_to_fresh_generator_run() -> None:
    """render(extract(cleanup-wizard.md)) in-process == the committed file's content, exactly.

    extract() is called with the same repo-root-relative path the real CLI invocation used
    (see 02-03-PLAN.md's <action>), via a cwd context manager, so the IR's `source_file`
    field -- embedded verbatim in the Expected/provenance-note text -- matches exactly what
    produced the committed file, not merely an equivalent absolute-path variant.
    """
    committed = _committed_text()

    original_cwd = Path.cwd()
    try:
        os.chdir(REPO_ROOT)
        fresh = g.render(g.extract(_COMMAND_FILE_RELATIVE))
    finally:
        os.chdir(original_cwd)

    assert fresh == committed, (
        "committed docs/test-plans/cleanup-wizard.md has drifted from a fresh in-process "
        "extract()+render() run against .claude/commands/gmj-cleanup-wizard.md -- the file "
        "was likely hand-edited after generation (T-02-08); re-run "
        f"`python3 scripts/gmj_testplan_gen.py --command-file {_COMMAND_FILE} "
        f"--output {_COMMITTED_FILE}` and re-commit, never hand-edit the generated file "
        f"directly.\n--- fresh (expected) ---\n{fresh}\n--- committed (actual) ---\n{committed}"
    )


# --------------------------------------------------------------------------- Test 2: field spec + Proves substance

def test_committed_file_has_all_six_fields_and_real_proves_substance() -> None:
    """The committed file carries all six Field Spec markers, plus a substantive OPS-01 Proves line.

    Never just checks the bare **Proves:** marker string is present -- a
    generic/placeholder **Proves:** line would otherwise pass a bare-marker-presence check
    undetected (T-02-12); this asserts the literal OPS-01 token appears immediately after
    the marker, followed by non-empty, non-bare-ID prose.
    """
    committed = _committed_text()

    for field in ("**Proves:**", "**Why human:**", "**Steps", "**Expected:**", "**PASS criteria"):
        assert field in committed, (
            f"committed docs/test-plans/cleanup-wizard.md missing required Field Spec "
            f"marker: {field!r}"
        )

    assert "Generated" in committed or "generated" in committed, (
        "committed docs/test-plans/cleanup-wizard.md missing the closing "
        "generation-provenance note (must state the file was generated, not hand-authored)"
    )

    proves_match = re.search(r"\*\*Proves:\*\*\s+OPS-01\s+\S", committed)
    assert proves_match, (
        "committed docs/test-plans/cleanup-wizard.md's **Proves:** line must name the real "
        "OPS-01 requirement ID immediately after the marker, followed by concrete prose -- "
        "a bare marker-presence check would silently miss a placeholder/generic Proves "
        f"line; searched pattern r'\\*\\*Proves:\\*\\*\\s+OPS-01\\s+\\S' against:\n{committed}"
    )

    proves_line_start = committed.find("**Proves:**")
    proves_line_end = committed.find("\n", proves_line_start)
    proves_line = committed[proves_line_start : proves_line_end if proves_line_end != -1 else None]
    after_id = proves_line.split("OPS-01", 1)[1].strip(" —-")
    assert after_id, (
        f"**Proves:** line must have non-empty, non-placeholder prose after OPS-01, "
        f"got line: {proves_line!r}"
    )


# --------------------------------------------------------------------------- Test 3: non-executability spot checks

def test_committed_file_has_no_bypass_phrasing_or_scripted_check_as_criterion() -> None:
    """The committed file never instructs a bypass flag or reduces PASS-criteria to a bare script check.

    Mirrors tests/test_gmj_testplan_gen.py Task 2 Test 7's assertion, applied here to the
    real committed file rather than a synthetic fixture -- makes Task 1's manual
    Non-Executability Criterion 4 verification pass mechanically repeatable on every future
    test run, not a one-time confirmation that could silently bit-rot (T-02-09).
    """
    committed = _committed_text()
    lowered = committed.lower()

    for forbidden in ("--yes", "--force", "-y", "--no-confirm"):
        assert forbidden not in lowered, (
            f"committed docs/test-plans/cleanup-wizard.md must never contain a raw "
            f"bypass-flag instruction: {forbidden!r}"
        )

    assert "run assert_pass" not in lowered, (
        "committed docs/test-plans/cleanup-wizard.md must never phrase a PASS-criteria "
        "field as a bare scripted-check invocation (e.g. 'run assert_pass.py')"
    )

    # A PASS-criteria bullet that reduces the entire judgment to "the script exited 0" (with
    # no human-applied inspection of real output) would defeat the manual-only shape.
    pass_criteria_start = committed.find("**PASS criteria")
    assert pass_criteria_start != -1, (
        "committed docs/test-plans/cleanup-wizard.md missing a **PASS criteria** section "
        "to spot-check"
    )
    pass_criteria_block = committed[pass_criteria_start:].lower()
    assert "human operator" in pass_criteria_block or "human" in pass_criteria_block, (
        "committed docs/test-plans/cleanup-wizard.md's PASS-criteria field must be "
        "human-applied (naming a human operator reading real output), not delegated "
        "wholesale to a script's exit code alone"
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
