#!/usr/bin/env python3
"""Contract for scripts/gmj_testplan_gen.py (TPGEN-03/TPGEN-04, TPGEN-05/TPGEN-06).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_testplan_gen.py``. Mirrors
``tests/test_gmj_cleanup_wizard.py``'s shape: a ``main()`` that runs every ``test_*``
function, catches and reports any uncaught exception as FAIL, and exits 1 on any failure /
0 if all pass.

Task 1 tests (1-4) cover ``extract()``: parsing a real ``.claude/commands/*.md`` file's
frontmatter/body into an in-memory dict IR, including the mandatory ``requirement_id``
field, and failing closed on a missing file, malformed frontmatter, or absent
requirement-ID token.

Task 2 tests (5-9) cover ``render()``/``write_testplan()``/``main()``: spec-conformant
Markdown output (all six per-test fields in order, document scaffolding,
non-executability-compliant phrasing), the render()-side fail-closed guard on a missing/
empty requirement_id, and the CLI's extract->render->write wiring with fail-closed error
handling.

Phase 3 Task 1 tests cover ``extract()``'s new ``risk_tier`` (required, fail-closed
validated against the 4 frozen tiers) and ``requirement_id_override`` (optional bypass of
the missing-requirement-ID raise) parameters.

Phase 3 Task 2 tests cover ``render()``'s new tier-aware structural warning block: present
(and positionally correct) for ``live-cost``/``destructive-if-confirmed`` tiers, fully
omitted for ``read-only``/``local-safe`` tiers.

HARD CONSTRAINT: synthetic fixtures live under their own ``tempfile.TemporaryDirectory()``
context manager. This file mutates nothing under the real repo's ``docs/`` or ``output/``
directories outside a tempdir.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_testplan_gen as g  # noqa: E402  (module under test)


# --------------------------------------------------------------------------- fixtures

_FIXTURE_COMMAND_DOC = """\
# /gmj-fixture-flow — a synthetic fixture command doc

---
allowed-tools: Bash(*)
description: A synthetic fixture flow for extractor testing (REQ-01).
---

## What to do

This is a synthetic fixture flow, satisfying **REQ-01** in its body too.

## Flags

- **`--repo-root <path>`** — testability-only. Re-anchors the flow at a different root.
- **`--dry-run`** — preview mode, makes no changes.

## Interaction flow

There is **no** bypass flag anywhere in this CLI — the confirm prompt can never be skipped.

1. **First step.** Do the first thing.
2. **Second step.** Do the second thing.

```bash
python3 scripts/gmj_fixture_flow.py --repo-root <path>
```
"""

_FIXTURE_NO_FRONTMATTER = """\
# /gmj-fixture-flow — no frontmatter here

Just a body, no frontmatter fence at all.
"""

_FIXTURE_NO_REQUIREMENT_ID = """\
---
allowed-tools: Bash(*)
description: A fixture flow citing no requirement ID at all.
---

## What to do

Nothing to cite here.
"""


def _write_fixture(tmp: str, name: str, content: str) -> Path:
    path = Path(tmp) / name
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- Task 1: extract()

def test_extract_returns_ir_with_expected_fields() -> None:
    """extract() on a valid fixture returns a dict IR with all required fields populated."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        ir = g.extract(fixture, risk_tier="read-only")

        assert isinstance(ir, dict), f"extract() must return a dict, got {type(ir)}"
        assert ir.get("flow_name") or ir.get("slug"), (
            f"IR must carry a flow_name or slug string, got: {ir}"
        )
        assert ir.get("description"), f"IR must carry the frontmatter description, got: {ir}"
        assert isinstance(ir.get("flags"), list) and ir["flags"], (
            f"IR must carry a non-empty flags list capturing each documented CLI flag, got: {ir.get('flags')!r}"
        )
        flag_names = {f.get("name") for f in ir["flags"]}
        assert "--repo-root" in flag_names, (
            f"IR flags list must capture --repo-root with its purpose, got names: {flag_names}"
        )
        behaviors = ir.get("behaviors") or ir.get("steps")
        assert behaviors, (
            f"IR must carry a non-empty behaviors/steps list with at least one real command, got: {behaviors!r}"
        )
        assert ir.get("requirement_id") == "REQ-01", (
            f"IR must carry the exact REQ-01 token extracted from the fixture's description "
            f"line, got: {ir.get('requirement_id')!r}"
        )


def test_extract_real_cleanup_wizard_command_file() -> None:
    """extract() against the real gmj-cleanup-wizard.md sources OPS-01 and --repo-root."""
    real_path = REPO_ROOT / ".claude" / "commands" / "gmj-cleanup-wizard.md"
    ir = g.extract(real_path, risk_tier="destructive-if-confirmed")

    flag_names = {f.get("name") for f in ir.get("flags", [])}
    assert "--repo-root" in flag_names, (
        f"extract() against the real cleanup-wizard command file must capture --repo-root "
        f"in its flags list, got names: {flag_names}"
    )
    assert ir.get("no_bypass_flag") is True, (
        f"extract() must reflect the explicit 'no bypass flag' statement from the real "
        f"command file as a structured fact (e.g. no_bypass_flag: true), got IR: {ir}"
    )
    assert ir.get("requirement_id") == "OPS-01", (
        f"extract() against the real cleanup-wizard command file must source "
        f"requirement_id=OPS-01 (Plan 01's citation), got: {ir.get('requirement_id')!r}"
    )


def test_extract_nonexistent_file_raises() -> None:
    """extract() with a path to a nonexistent file raises (fail-closed), never an empty IR."""
    missing = REPO_ROOT / ".claude" / "commands" / "gmj-does-not-exist-fixture.md"
    assert not missing.exists(), f"test fixture assumption broken: {missing} unexpectedly exists"

    raised = False
    try:
        g.extract(missing, risk_tier="read-only")
    except (FileNotFoundError, OSError) as exc:
        raised = True
        assert str(missing) in str(exc) or missing.name in str(exc), (
            f"extract() must name the missing file path in its error, got: {exc}"
        )
    assert raised, "extract() must raise (FileNotFoundError or equivalent) on a missing file"


def test_extract_missing_frontmatter_raises() -> None:
    """extract() on a file missing the '---'-fenced frontmatter block raises ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-no-frontmatter.md", _FIXTURE_NO_FRONTMATTER)

        raised = False
        try:
            g.extract(fixture, risk_tier="read-only")
        except ValueError as exc:
            raised = True
            assert str(fixture) in str(exc) or fixture.name in str(exc), (
                f"extract() must name the offending file in its ValueError, got: {exc}"
            )
        assert raised, (
            "extract() must raise ValueError when the frontmatter fence is missing, "
            "not silently treat the whole file as body content"
        )


def test_extract_behaviors_never_picks_up_prose_outside_numbered_lists_and_code_blocks() -> None:
    """_extract_behaviors()/extract() must never pick up plain-prose sentences.

    This is a structural guarantee (not an accident of the current narrow scanner): prose
    sentences that live outside a numbered list item and outside a fenced code block --
    including ones that happen to contain bypass-flag tokens like ``--yes``/``--force`` --
    must never end up in the IR's ``behaviors`` list. This is what actually keeps
    ``test_render_no_bypass_phrasing_and_human_applied_pass_criteria``'s "never leaks"
    assertion true; that render-level test alone is a weak proxy (WR-02) because it only
    proves today's fixture happens not to trigger a leak, not that leakage is structurally
    impossible.
    """
    prose_fixture = """\
# /gmj-fixture-flow — a synthetic fixture command doc

---
allowed-tools: Bash(*)
description: A synthetic fixture flow for extractor testing (REQ-01).
---

## What to do

This is a synthetic fixture flow, satisfying **REQ-01** in its body too.

## Interaction flow

There is **no** `--yes`/`--force`/`-y`/`--no-confirm` bypass flag anywhere in this CLI --
the confirm prompt can never be skipped non-interactively.

1. **First step.** Do the first thing.

```bash
python3 scripts/gmj_fixture_flow.py --repo-root <path>
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", prose_fixture)
        ir = g.extract(fixture, risk_tier="read-only")

        behaviors = ir.get("behaviors") or []
        joined = " ".join(behaviors).lower()
        for forbidden in ("--yes", "--force", "-y", "--no-confirm"):
            assert forbidden not in joined, (
                f"_extract_behaviors() must never pick up a bare-prose sentence outside a "
                f"numbered list item or code block -- found forbidden token {forbidden!r} "
                f"in extracted behaviors: {behaviors!r}"
            )
        assert any("first step" in b.lower() for b in behaviors), (
            f"sanity check: the real numbered-list item must still be extracted, "
            f"got behaviors: {behaviors!r}"
        )


# --------------------------------------------------------------------------- Phase 3 Task 1: risk_tier / requirement_id_override

def test_extract_risk_tier_field_present() -> None:
    """extract(fixture, risk_tier=...) round-trips all 4 frozen tier values into the IR unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        for tier in ("read-only", "local-safe", "live-cost", "destructive-if-confirmed"):
            ir = g.extract(fixture, risk_tier=tier)
            assert ir["risk_tier"] == tier, (
                f"extract(risk_tier={tier!r}) must produce ir['risk_tier'] == {tier!r}, "
                f"got: {ir.get('risk_tier')!r}"
            )


def test_extract_invalid_risk_tier_raises() -> None:
    """extract() with a risk_tier not in the frozen 4-tier set raises ValueError naming file + value."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)

        raised = False
        try:
            g.extract(fixture, risk_tier="critical")
        except ValueError as exc:
            raised = True
            message = str(exc)
            assert str(fixture) in message or fixture.name in message, (
                f"extract() must name the offending file in its risk_tier ValueError, got: {exc}"
            )
            assert "critical" in message, (
                f"extract() must name the invalid risk_tier value in its ValueError, got: {exc}"
            )
        assert raised, (
            "extract() must raise ValueError when risk_tier is not one of the 4 frozen tiers"
        )


def test_extract_requirement_id_override_bypasses_missing_id() -> None:
    """requirement_id_override bypasses the missing-requirement-ID raise, using the override verbatim."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-no-req-id.md", _FIXTURE_NO_REQUIREMENT_ID)
        ir = g.extract(fixture, risk_tier="read-only", requirement_id_override="OPS-02")

        assert ir["requirement_id"] == "OPS-02", (
            f"extract() with requirement_id_override='OPS-02' against a fixture with no "
            f"citable requirement-ID token must produce ir['requirement_id'] == 'OPS-02' "
            f"exactly (the override value verbatim), got: {ir.get('requirement_id')!r}"
        )


def test_extract_no_override_still_raises_on_missing_id() -> None:
    """Without an override, extract() still raises ValueError on a fixture with no requirement ID."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-no-req-id.md", _FIXTURE_NO_REQUIREMENT_ID)

        raised = False
        try:
            g.extract(fixture, risk_tier="read-only")
        except ValueError:
            raised = True
        assert raised, (
            "extract() without requirement_id_override must still raise ValueError on a "
            "fixture with no citable requirement-ID token -- the override is opt-in, never "
            "a silent default that weakens the existing fail-closed guarantee"
        )


# --------------------------------------------------------------------------- Task 2: render()

def _synthetic_ir(requirement_id: str = "REQ-01") -> dict:
    return {
        "flow_name": "fixture-flow",
        "slug": "fixture-flow",
        "description": "A synthetic fixture flow for render() testing.",
        "flags": [{"name": "--repo-root", "purpose": "Re-anchors the flow at a different root."}],
        "behaviors": ["python3 scripts/gmj_fixture_flow.py --repo-root <path>"],
        "requirement_id": requirement_id,
        "source_file": ".claude/commands/gmj-fixture-flow.md",
    }


def test_render_produces_six_fields_in_order_with_real_proves_content() -> None:
    """render() on a synthetic IR produces all six per-test fields, Proves carrying the real ID."""
    ir = _synthetic_ir()
    text = g.render(ir)

    markers = ["**Proves:**", "**Why human:**", "**Steps", "**Expected:**", "**PASS criteria:**"]
    positions = []
    for marker in markers:
        idx = text.find(marker)
        assert idx != -1, f"render() output missing required field marker: {marker}\n---\n{text}"
        positions.append(idx)
    assert positions == sorted(positions), (
        f"render() output fields must appear in order {markers}, got positions {positions}"
    )
    # An ID heading (## or ###) must exist before Proves.
    id_heading_idx = text.find("#")
    assert 0 <= id_heading_idx < positions[0], (
        "render() output must contain an ID heading before the **Proves:** marker"
    )

    proves_line_start = positions[0]
    proves_line_end = text.find("\n", proves_line_start)
    proves_line = text[proves_line_start:proves_line_end if proves_line_end != -1 else None]
    assert "REQ-01" in proves_line, (
        f"**Proves:** line must contain the literal token REQ-01 immediately after the "
        f"marker, got line: {proves_line!r}"
    )
    after_id = proves_line.split("REQ-01", 1)[1].strip(" —-")
    assert after_id, (
        f"**Proves:** line must have non-empty, non-placeholder prose after the "
        f"requirement ID, got line: {proves_line!r}"
    )
    assert proves_line.strip() != f"**Proves:** {ir['requirement_id']}", (
        f"**Proves:** line must not be a bare ID with nothing after it, got: {proves_line!r}"
    )
    assert "this test works" not in text.lower(), (
        "render() must never emit generic filler like 'this test works' with no real ID"
    )


def test_render_document_scaffolding_present() -> None:
    """render() output has a title heading, setup/precondition section, and provenance note."""
    ir = _synthetic_ir()
    text = g.render(ir)

    lines = text.splitlines()
    title_lines = [ln for ln in lines if ln.startswith("# ")]
    assert title_lines, f"render() output must contain a #-level title heading, got:\n{text}"

    lowered = text.lower()
    assert "precondition" in lowered or "setup" in lowered, (
        "render() output must contain a setup/precondition section"
    )
    assert "generated" in lowered and "gmj_testplan_gen.py" in text, (
        "render() output must close with a note stating the file was generated (not "
        "hand-authored) naming scripts/gmj_testplan_gen.py as the generation source"
    )


def test_render_no_bypass_phrasing_and_human_applied_pass_criteria() -> None:
    """render() output never contains bypass-flag phrasing or scripted-check-as-criterion phrasing.

    Also asserts render() raises on a missing/empty requirement_id IR — render() must not
    silently paper over an IR that violates the fail-closed contract.
    """
    ir = _synthetic_ir()
    text = g.render(ir)

    lowered = text.lower()
    for forbidden in ("--yes", "--force", "-y", "--no-confirm"):
        assert forbidden not in lowered, (
            f"render() output must never contain a raw bypass instruction: {forbidden!r}"
        )
    assert "run assert_pass" not in lowered, (
        "render() output must never phrase PASS-criteria as a bare scripted-check invocation"
    )

    for bad_ir in (_synthetic_ir(requirement_id=""), {k: v for k, v in _synthetic_ir().items() if k != "requirement_id"}):
        raised = False
        try:
            g.render(bad_ir)
        except ValueError:
            raised = True
        assert raised, (
            f"render() must raise ValueError when requirement_id is missing/empty, "
            f"IR: {bad_ir}"
        )


# --------------------------------------------------------------------------- Phase 3 Task 2: tier-aware warning block

def test_render_warning_block_for_live_cost_tier() -> None:
    """render() on a live-cost IR positions a '> ⚠️' warning between the title and purpose lines."""
    ir = _synthetic_ir()
    ir["risk_tier"] = "live-cost"
    text = g.render(ir)

    title_idx = text.find("# Test Plan")
    warn_idx = text.find("> ⚠️")
    purpose_idx = text.find("This file verifies")
    assert title_idx != -1 and warn_idx != -1 and purpose_idx != -1, (
        f"render() output missing title/warning/purpose markers, got:\n{text}"
    )
    assert title_idx < warn_idx < purpose_idx, (
        f"render() must position the '> ⚠️' warning strictly between the title and purpose "
        f"lines, got indices title={title_idx}, warn={warn_idx}, purpose={purpose_idx}"
    )
    assert "live-cost" in text, "warning text must name the live-cost tier"
    lowered = text.lower()
    assert "spend" in lowered or "network" in lowered or "api" in lowered, (
        f"live-cost warning text must name the real blast radius (LLM/API spend or network "
        f"calls), not a generic templated sentence, got:\n{text}"
    )


def test_render_warning_block_for_destructive_tier() -> None:
    """render() on a destructive-if-confirmed IR positions a distinct '> ⚠️' warning, worded differently from live-cost."""
    ir = _synthetic_ir()
    ir["risk_tier"] = "destructive-if-confirmed"
    text = g.render(ir)

    title_idx = text.find("# Test Plan")
    warn_idx = text.find("> ⚠️")
    purpose_idx = text.find("This file verifies")
    assert title_idx < warn_idx < purpose_idx, (
        f"render() must position the '> ⚠️' warning strictly between the title and purpose "
        f"lines, got indices title={title_idx}, warn={warn_idx}, purpose={purpose_idx}"
    )
    assert "destructive-if-confirmed" in text, "warning text must name the destructive tier"
    lowered = text.lower()
    assert "delet" in lowered, (
        f"destructive-if-confirmed warning text must name the real blast radius (local-data "
        f"deletion), got:\n{text}"
    )

    live_cost_ir = _synthetic_ir()
    live_cost_ir["risk_tier"] = "live-cost"
    live_cost_text = g.render(live_cost_ir)
    live_cost_warn_line = live_cost_text.split("> ⚠️", 1)[1].split("\n", 1)[0]
    destructive_warn_line = text.split("> ⚠️", 1)[1].split("\n", 1)[0]
    assert live_cost_warn_line != destructive_warn_line, (
        "live-cost and destructive-if-confirmed warning text must be distinct wording, "
        "never a copy-pasted generic sentence shared across tiers"
    )


def test_render_no_warning_block_for_read_only_tier() -> None:
    """render() on a read-only IR emits zero '⚠️' occurrences -- full omission."""
    ir = _synthetic_ir()
    ir["risk_tier"] = "read-only"
    text = g.render(ir)

    assert "⚠️" not in text, (
        f"render() must fully omit the warning block for read-only tier (zero '⚠️' "
        f"occurrences), got:\n{text}"
    )


def test_render_no_warning_block_for_local_safe_tier() -> None:
    """render() on a local-safe IR emits zero '⚠️' occurrences -- full omission."""
    ir = _synthetic_ir()
    ir["risk_tier"] = "local-safe"
    text = g.render(ir)

    assert "⚠️" not in text, (
        f"render() must fully omit the warning block for local-safe tier (zero '⚠️' "
        f"occurrences), got:\n{text}"
    )


def test_main_wires_extract_render_write() -> None:
    """render(extract(path, risk_tier=...)) wiring works directly (main()'s own --risk-tier
    CLI wiring is Plan 02's concern, not this plan's -- see 03-01-PLAN.md verification
    section). main() itself, unmodified in this plan, now fails closed (TypeError from
    extract()'s new required risk_tier parameter) rather than succeeding -- this is expected
    and acceptable at the end of this plan.
    """
    with tempfile.TemporaryDirectory() as tmp:
        command_file = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        output_path = Path(tmp) / "out" / "fixture-flow.md"

        exit_code = g.main(["--command-file", str(command_file), "--output", str(output_path)])

        assert exit_code == 1, (
            f"main() is not updated to pass risk_tier= in this plan (Plan 02's concern) -- "
            f"it must fail closed (exit 1) rather than silently succeed, got {exit_code}"
        )
        assert not output_path.is_file(), (
            f"main()'s fail-closed path must not write the output file, but found {output_path}"
        )

        direct_text = g.render(g.extract(command_file, risk_tier="read-only"))
        assert direct_text, "render(extract(path, risk_tier=...)) direct wiring must still work"


def test_main_missing_command_file_fails_closed() -> None:
    """main(), given a nonexistent --command-file, exits 1, prints FAIL: to stderr, writes nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        missing_command_file = Path(tmp) / "gmj-does-not-exist.md"
        output_path = Path(tmp) / "out" / "should-not-exist.md"

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "gmj_testplan_gen.py"),
                "--command-file", str(missing_command_file),
                "--output", str(output_path),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, (
            f"main() must exit 1 on a missing --command-file, got {result.returncode}. "
            f"stderr: {result.stderr}"
        )
        assert "FAIL:" in result.stderr, (
            f"main() must print a FAIL:-prefixed message to stderr, got stderr: {result.stderr!r}"
        )
        assert not output_path.exists(), (
            f"main() must not create the --output file at all on a fail-closed error "
            f"(zero mutation on error), but found: {output_path}"
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
