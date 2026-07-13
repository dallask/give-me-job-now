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

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_testplan_gen as g  # noqa: E402  (module under test)
import gmj_testplan_signals as sig  # noqa: E402  (Phase 4 signal-table data module)

INVESTIGATE_SIGNAL_TABLE = (
    REPO_ROOT
    / ".planning"
    / "workstreams"
    / "investigate"
    / "phases"
    / "02-evaluation-criteria-grounding"
    / "02-EVALUATION-CRITERIA.md"
)

_MECHANICAL_LITERAL = "None — fully mechanical"

# The exact 10 flow-number -> slug join key, per 04-RESEARCH.md's "FLOW_MANIFEST Join Key
# (confirmed)" table -- used only to locate each slug's source row in the raw investigate
# table text below, never to re-derive/duplicate the transcribed cell content itself.
_SLUG_TO_FLOW_NUM = {
    "initial-configuration": 1,
    "pipeline-run-hitl": 2,
    "pipeline-run-autonomous": 3,
    "multi-offer-batch": 4,
    "firecrawl-search": 5,
    "cv-template": 6,
    "scheduled-runs": 7,
    "resume-flow": 8,
    "operator-monitoring": 9,
    "cleanup-wizard": 10,
}

# Slugs whose row shares the _GATE_AB_JUDGMENT_CAVEAT constant (by reference in the source
# table's own prose -- "Same ... as Flow 2" / "Inherits Flow 3's ... caveat by reference").
_GATED_SLUGS = {"pipeline-run-hitl", "pipeline-run-autonomous", "multi-offer-batch", "scheduled-runs"}

# The 4 genuinely mechanical slugs (D-04) -- NOT scheduled-runs (Pitfall 2).
_MECHANICAL_SLUGS = {"firecrawl-search", "resume-flow", "operator-monitoring", "cleanup-wizard"}


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


# --------------------------------------------------------------------------- Phase 3 Review Fix (CR-01/CR-02/CR-03) regression tests

# Shaped like the real .claude/commands/gmj-template.md: a fenced ```bash``` command inside
# one heading section, THEN a separate, later, unrelated heading with multi-line bulleted
# content -- this is the exact shape that let CR-01's prose-leak bug reach production
# (cv-template.md/initial-configuration.md) with zero test failures, since every prior
# fixture only ever had at most one heading section of bulleted content after a captured
# code-block line.
_FIXTURE_CROSS_SECTION_LEAK = """\
# /gmj-fixture-flow — a synthetic fixture command doc

---
allowed-tools: Bash(*)
description: A synthetic fixture flow for extractor testing (REQ-01).
---

## Steps section

Run the lint gate:

```bash
python3 scripts/gmj_fixture_lint.py --template templates/cv/<slug>.html
```

## Unrelated later section

Operator messages (machine-truthful; never claim pixel-perfect):

- **Success (match reached):** "Template `{slug}` matched the design (diff-ratio {r} ≤ 0.10)
  in {n} iteration(s) — saved to `templates/cv/{slug}.html}`."
- **Error (lint fail):** "Template rejected: it contains literal sample-profile
  text ({flagged tokens}). All content must bind via `{{ candidate.* }}`."
"""


def test_extract_behaviors_never_leaks_later_unrelated_section_onto_code_block_command() -> None:
    """CR-01 regression: a fenced code-block command must never absorb a LATER, unrelated
    heading section's bulleted/indented continuation lines.

    Reproduces the exact real-world shape that shipped corrupted content in
    docs/test-plans/cv-template.md and docs/test-plans/initial-configuration.md: a captured
    code-block command in one section, followed by a separate later heading whose bulleted
    list items happen to look like continuation lines (indented, non-bullet-prefixed
    wrapped text). None of the pre-existing fixtures placed a second, later, unrelated
    section after a captured code-block line, so this cross-section leak path was
    structurally never exercised before this test.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_CROSS_SECTION_LEAK)
        ir = g.extract(fixture, risk_tier="read-only")

        behaviors = ir.get("behaviors") or []
        command_behaviors = [b for b in behaviors if b.strip().startswith("python3 ")]
        assert command_behaviors, (
            f"sanity check: the real code-block command must still be extracted, "
            f"got behaviors: {behaviors!r}"
        )
        for cmd in command_behaviors:
            for forbidden in ("saved to", "matched the design", "diff-ratio", "flagged tokens", "candidate.*"):
                assert forbidden not in cmd, (
                    f"_extract_behaviors() must never fold a LATER, unrelated heading "
                    f"section's bulleted content onto an earlier captured code-block "
                    f"command (CR-01 regression) -- found forbidden fragment {forbidden!r} "
                    f"glued onto captured command: {cmd!r}"
                )
        assert command_behaviors[0].strip() == (
            "python3 scripts/gmj_fixture_lint.py --template templates/cv/<slug>.html"
        ), (
            f"the captured command must be exactly the fenced code-block line, with "
            f"nothing appended from a later section, got: {command_behaviors[0]!r}"
        )


# Shaped like the real .claude/commands/gmj-pipeline-run.md's "## CLI-only invocation"
# block: a bare `claude ...` REPL-entry line followed by exactly one `/gmj-...` follow-up
# line typed inside the session -- CR-02's bug dropped the follow-up line entirely because
# it didn't start with python3/claude/bash.
_FIXTURE_CLI_ONLY_INVOCATION = """\
# /gmj-fixture-pipeline — a synthetic fixture command doc

---
allowed-tools: Bash(*)
description: A synthetic fixture flow for extractor testing (REQ-01).
---

## CLI-only invocation

```bash
claude --dangerously-skip-permissions
# then, in the session:
/gmj-fixture-pipeline   # then state your mode / offer / run_id
```
"""


def test_render_steps_block_keeps_slash_command_follow_up_after_claude_repl_entry() -> None:
    """CR-02 regression: a `claude ...` REPL-entry line's `/gmj-...` follow-up command must
    survive into the rendered Steps block, not be silently dropped.

    Reproduces the exact real-world shape that shipped
    docs/test-plans/pipeline-run-hitl.md, pipeline-run-autonomous.md, multi-offer-batch.md,
    and resume-flow.md with ONLY a bare `claude --dangerously-skip-permissions` step and no
    mention anywhere of the actual slash command a human must type next.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-pipeline.md", _FIXTURE_CLI_ONLY_INVOCATION)
        ir = g.extract(fixture, risk_tier="read-only")
        text = g.render(ir)

        # Scope the assertion to the fenced code block(s) inside the Steps section, not the
        # whole document -- the flow's title/source-file-path/provenance note all legitimately
        # contain the substring "/gmj-fixture-pipeline" (as part of a filesystem path), so a
        # whole-document substring check would false-pass even when the Steps block itself
        # silently dropped the slash-command follow-up line (the actual CR-02 bug).
        steps_start = text.find("**Steps")
        steps_end = text.find("**Expected:**")
        assert steps_start != -1 and steps_end != -1, f"could not locate Steps/Expected markers in:\n{text}"
        steps_block = text[steps_start:steps_end]
        code_blocks = "\n".join(re.findall(r"```bash\n(.*?)\n```", steps_block, flags=re.DOTALL))

        assert "claude --dangerously-skip-permissions" in code_blocks, (
            f"rendered Steps fenced code block(s) must still contain the claude REPL-entry "
            f"line, got:\n{code_blocks!r}"
        )
        assert re.search(r"^\s*(?:\d+\.\s*)?/gmj-fixture-pipeline\b", code_blocks, flags=re.MULTILINE), (
            f"CR-02 regression: rendered Steps fenced code block(s) must contain the "
            f"/gmj-fixture-pipeline follow-up command typed inside the REPL session, not "
            f"silently drop it, got code block(s):\n{code_blocks!r}\nfull Steps block:\n{steps_block}"
        )


# Shaped like the real .claude/commands/gmj-dashboard.md: two independent,
# mutually-exclusive invocations of the SAME script (default vs. `--manage`) -- CR-03's bug
# bundled both into one numbered fenced code block with no judgment point between them,
# violating the spec's "no single-block copy-paste-and-run-all" Non-Executability Criterion.
_FIXTURE_INDEPENDENT_ALTERNATIVES = """\
# /gmj-fixture-dashboard — a synthetic fixture command doc

---
allowed-tools: Bash(*)
description: A synthetic fixture flow for extractor testing (REQ-01).
---

## Invocation

```bash
python3 scripts/fixture/gmj_fixture_dashboard.py            # read-only (default)
python3 scripts/fixture/gmj_fixture_dashboard.py --manage   # opt into the action layer
```
"""


def test_render_steps_block_splits_independent_alternatives_into_separate_blocks() -> None:
    """CR-03 regression: independent, mutually-exclusive command alternatives must never be
    bundled into a single uninterrupted fenced code block.

    Reproduces the exact real-world shape that shipped docs/test-plans/operator-monitoring.md
    with two mutually-exclusive gmj_dashboard.py invocations numbered 1./2. inside one
    ```bash``` block -- exactly the "Pitfall 1: auto-execution drift" pattern
    docs/TESTPLAN-FORMAT-SPEC.md's Non-Executability Acceptance Criterion 2 forbids.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-dashboard.md", _FIXTURE_INDEPENDENT_ALTERNATIVES)
        ir = g.extract(fixture, risk_tier="read-only")
        text = g.render(ir)

        # Both invocations must still be present somewhere in the rendered output...
        assert "gmj_fixture_dashboard.py" in text and "--manage" in text, (
            f"both independent alternatives must still appear in the rendered output, "
            f"got:\n{text}"
        )
        # ...but never inside the SAME fenced code block together (no single-block
        # copy-paste-and-run-all of two independent, mutually-exclusive entry points).
        code_blocks = re.findall(r"```bash\n(.*?)\n```", text, flags=re.DOTALL)
        for block in code_blocks:
            command_lines = [ln for ln in block.splitlines() if ln.strip()]
            assert len(command_lines) <= 1, (
                f"CR-03 regression: no single fenced code block may contain more than one "
                f"command when the underlying behaviors are independent, mutually-exclusive "
                f"alternatives rather than a genuine ordered sequence -- found a block with "
                f"{len(command_lines)} command lines: {command_lines!r}\nfull output:\n{text}"
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


# --------------------------------------------------------------------------- Phase 3 Task 2: main() --all mode

def test_main_all_mode_generates_one_file_per_manifest_row() -> None:
    """main(["--all", "--output-dir", tmp]) exits 0 and writes one .md file per FLOW_MANIFEST row."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "test-plans"
        exit_code = g.main(["--all", "--output-dir", str(output_dir)])

        assert exit_code == 0, f"main(['--all', ...]) must exit 0, got {exit_code}"
        written = sorted(p.name for p in output_dir.glob("*.md"))
        expected = sorted(f"{row['slug']}.md" for row in g.FLOW_MANIFEST)
        assert written == expected, (
            f"main(['--all', ...]) must write exactly one .md file per FLOW_MANIFEST row "
            f"(by slug), got {written}, expected {expected}"
        )
        assert len(written) == len(g.FLOW_MANIFEST) == 10, (
            f"expected exactly 10 files written, got {len(written)}"
        )


def test_main_all_mode_reports_each_row_failure_individually() -> None:
    """A single bad manifest row's failure is reported without aborting the other 9 rows.

    Verified at the loop-body level directly (not via a full main() subprocess run), by
    temporarily monkeypatching g.FLOW_MANIFEST with a manifest-shaped list where one row's
    command_file points at a nonexistent path -- this deterministically exercises the
    per-row try/except without depending on any real command file's content.
    """
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "test-plans"
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        bad_manifest = [
            {
                "slug": "bad-row",
                "command_file": Path(tmp) / "gmj-does-not-exist.md",
                "risk_tier": "read-only",
                "requirement_id_override": None,
            },
            {
                "slug": "good-row",
                "command_file": fixture,
                "risk_tier": "read-only",
                "requirement_id_override": None,
            },
        ]

        original_manifest = g.FLOW_MANIFEST
        try:
            g.FLOW_MANIFEST = bad_manifest
            import io
            captured_stderr = io.StringIO()
            original_stderr = sys.stderr
            sys.stderr = captured_stderr
            try:
                exit_code = g.main(["--all", "--output-dir", str(output_dir)])
            finally:
                sys.stderr = original_stderr
        finally:
            g.FLOW_MANIFEST = original_manifest

        stderr_text = captured_stderr.getvalue()
        assert exit_code == 1, (
            f"main(['--all', ...]) must exit 1 when any row fails, got {exit_code}"
        )
        assert "FAIL: bad-row" in stderr_text, (
            f"main(['--all', ...]) must print a FAIL:-prefixed message naming the failing "
            f"row's slug, got stderr: {stderr_text!r}"
        )
        good_output = output_dir / "good-row.md"
        assert good_output.is_file(), (
            f"main(['--all', ...]) must still write the other (good) rows' output files "
            f"even when one row fails -- per-row fail-closed, not whole-batch fail-closed, "
            f"but found no {good_output}"
        )
        bad_output = output_dir / "bad-row.md"
        assert not bad_output.is_file(), (
            f"main(['--all', ...]) must not write an output file for the failing row, but "
            f"found {bad_output}"
        )


def test_main_single_invocation_mode_unchanged() -> None:
    """The pre-existing --command-file/--output single-invocation CLI contract still works,
    now requiring the new --risk-tier flag (extract()'s risk_tier became required in Plan 01).
    """
    with tempfile.TemporaryDirectory() as tmp:
        command_file = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        output_path = Path(tmp) / "out" / "fixture-flow.md"

        exit_code = g.main([
            "--command-file", str(command_file),
            "--output", str(output_path),
            "--risk-tier", "read-only",
        ])

        assert exit_code == 0, (
            f"main() with --command-file/--output/--risk-tier must exit 0, got {exit_code}"
        )
        assert output_path.is_file(), (
            f"main() single-invocation mode must write the output file, but {output_path} "
            f"does not exist"
        )
        text = output_path.read_text(encoding="utf-8")
        assert "REQ-01" in text, (
            f"single-invocation output must contain the fixture's REQ-01 requirement ID, "
            f"got:\n{text}"
        )


# --------------------------------------------------------------------------- Plan 03 Task 1: real-repo rollout

def test_all_ten_flow_plans_exist_on_disk() -> None:
    """Real-repo-state assertion (not a tempdir fixture): every FLOW_MANIFEST row has a
    generated docs/test-plans/<slug>.md file on disk, and live-cost/destructive-if-confirmed
    rows' files carry the structural warning block while read-only/local-safe rows' files do
    not -- the real-file equivalent of the synthetic-IR render() warning-block tests, proving
    the end-to-end --all pipeline (not just the unit-level render() function) produces the
    structurally-distinct warning behavior TPGEN-06 requires.

    Uses len(g.FLOW_MANIFEST) rather than a hard-coded 10 so this stays correct if the
    manifest count is ever legitimately revised (RESEARCH.md Validation Architecture Wave 0
    gap #2: "no test currently asserts file count").
    """
    output_dir = REPO_ROOT / "docs" / "test-plans"
    on_disk = {p.name for p in output_dir.glob("*.md")}
    expected = {f"{row['slug']}.md" for row in g.FLOW_MANIFEST}

    assert on_disk == expected, (
        f"docs/test-plans/*.md must contain exactly one file per FLOW_MANIFEST row, "
        f"got {sorted(on_disk)}, expected {sorted(expected)}"
    )
    assert len(on_disk) == len(g.FLOW_MANIFEST), (
        f"expected exactly len(FLOW_MANIFEST)={len(g.FLOW_MANIFEST)} files on disk, "
        f"got {len(on_disk)}"
    )

    warn_tiers = {"live-cost", "destructive-if-confirmed"}
    for row in g.FLOW_MANIFEST:
        plan_path = output_dir / f"{row['slug']}.md"
        text = plan_path.read_text(encoding="utf-8")
        has_warning = "⚠️" in text
        if row["risk_tier"] in warn_tiers:
            assert has_warning, (
                f"{plan_path} is tagged risk_tier={row['risk_tier']!r} (a warn-worthy tier) "
                f"but its generated text contains no ⚠️ warning block"
            )
        else:
            assert not has_warning, (
                f"{plan_path} is tagged risk_tier={row['risk_tier']!r} (not a warn-worthy "
                f"tier) but its generated text unexpectedly contains a ⚠️ warning block"
            )


# --------------------------------------------------------------------------- Phase 4 Task 1: signal-table data module

def _read_investigate_source_rows() -> dict[int, list[str]]:
    """Parse 02-EVALUATION-CRITERIA.md's Signal Reference table at test time (never hand-copied).

    Returns {flow_number: [flow_cell, pass_signal, fail_signal, signal_source, semantic_caveat]},
    read directly from the raw file text every call -- this is the ONLY place this test file
    reads the source table's cell content, so a future edit to the source table is picked up
    automatically rather than checked against a second, potentially-stale hand-copied fixture.
    """
    text = INVESTIGATE_SIGNAL_TABLE.read_text(encoding="utf-8")
    rows: dict[int, list[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*(\d+)\.", line)
        if not match:
            continue
        # Split on unescaped pipes only (a cell may contain an escaped `\|`), then drop the
        # leading/trailing empty strings produced by the row's own boundary `|` characters.
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)]
        cells = cells[1:-1] if len(cells) >= 2 and cells[0] == "" and cells[-1] == "" else cells
        rows[int(match.group(1))] = cells
    return rows


def test_signal_table_by_slug_has_all_ten_manifest_slugs() -> None:
    """SIGNAL_TABLE_BY_SLUG's key set is exactly FLOW_MANIFEST's slug set (not a duplicate list)."""
    manifest_slugs = {row["slug"] for row in g.FLOW_MANIFEST}
    assert set(sig.SIGNAL_TABLE_BY_SLUG.keys()) == manifest_slugs, (
        f"SIGNAL_TABLE_BY_SLUG's keys {sorted(sig.SIGNAL_TABLE_BY_SLUG.keys())} must exactly "
        f"match FLOW_MANIFEST's slugs {sorted(manifest_slugs)}"
    )
    assert len(sig.SIGNAL_TABLE_BY_SLUG) == 10, (
        f"expected exactly 10 entries, got {len(sig.SIGNAL_TABLE_BY_SLUG)}"
    )


def test_exactly_four_flows_are_fully_mechanical() -> None:
    """Exactly firecrawl-search/resume-flow/operator-monitoring/cleanup-wizard are fully mechanical.

    scheduled-runs (flow 7) must NOT carry the literal -- Pitfall 2 regression guard.
    """
    for slug in _MECHANICAL_SLUGS:
        assert sig.SIGNAL_TABLE_BY_SLUG[slug]["semantic_caveat"] == _MECHANICAL_LITERAL, (
            f"{slug!r} must have semantic_caveat == {_MECHANICAL_LITERAL!r} (D-04), got: "
            f"{sig.SIGNAL_TABLE_BY_SLUG[slug]['semantic_caveat']!r}"
        )
    all_mechanical = {
        slug for slug, row in sig.SIGNAL_TABLE_BY_SLUG.items()
        if row["semantic_caveat"] == _MECHANICAL_LITERAL
    }
    assert all_mechanical == _MECHANICAL_SLUGS, (
        f"expected exactly {sorted(_MECHANICAL_SLUGS)} to be fully mechanical, got "
        f"{sorted(all_mechanical)}"
    )
    assert sig.SIGNAL_TABLE_BY_SLUG["scheduled-runs"]["semantic_caveat"] != _MECHANICAL_LITERAL, (
        "Pitfall 2 regression: scheduled-runs (flow 7) must NOT be rendered as "
        "'None — fully mechanical' -- it inherits the shared Gate A/B caveat by reference"
    )


def test_gated_flows_share_identical_gate_ab_caveat_substring() -> None:
    """The full _GATE_AB_JUDGMENT_CAVEAT text appears verbatim in all 4 gated flows' caveat cells."""
    for slug in _GATED_SLUGS:
        assert sig._GATE_AB_JUDGMENT_CAVEAT in sig.SIGNAL_TABLE_BY_SLUG[slug]["semantic_caveat"], (
            f"{slug!r}'s semantic_caveat must contain the full _GATE_AB_JUDGMENT_CAVEAT text "
            f"verbatim as a substring (one source of truth, not independently-typed near-"
            f"duplicates), got: {sig.SIGNAL_TABLE_BY_SLUG[slug]['semantic_caveat']!r}"
        )


def test_signal_table_matches_investigate_source() -> None:
    """Every transcribed cell traces verbatim to 02-EVALUATION-CRITERIA.md's raw table text.

    pass_signal/fail_signal/signal_source are always an exact match against the source row's
    corresponding cell. semantic_caveat is checked per-case: the 4 mechanical slugs must equal
    the D-04 literal; the 4 gated slugs' OWN row-specific trailing clause (the shared constant's
    reference has already been asserted separately by
    test_gated_flows_share_identical_gate_ab_caveat_substring) must be a substring of the
    source row's caveat cell; all other (ungated, non-mechanical) slugs must match the source
    row's caveat cell exactly.
    """
    source_rows = _read_investigate_source_rows()

    for slug, flow_num in _SLUG_TO_FLOW_NUM.items():
        row = sig.SIGNAL_TABLE_BY_SLUG[slug]
        source_cells = source_rows[flow_num]
        assert len(source_cells) == 5, (
            f"expected 5 cells for flow {flow_num} ({slug!r}), got {len(source_cells)}: {source_cells}"
        )
        _flow, src_pass, src_fail, src_source, src_caveat = source_cells

        assert row["pass_signal"] == src_pass, (
            f"{slug!r}'s pass_signal must be verbatim-identical to the source table's flow "
            f"{flow_num} Pass Signal cell -- got:\n{row['pass_signal']!r}\nexpected:\n{src_pass!r}"
        )
        assert row["fail_signal"] == src_fail, (
            f"{slug!r}'s fail_signal must be verbatim-identical to the source table's flow "
            f"{flow_num} Fail Signal cell -- got:\n{row['fail_signal']!r}\nexpected:\n{src_fail!r}"
        )
        assert row["signal_source"] == src_source, (
            f"{slug!r}'s signal_source must be verbatim-identical to the source table's flow "
            f"{flow_num} Signal Source cell -- got:\n{row['signal_source']!r}\nexpected:\n{src_source!r}"
        )

        if slug in _MECHANICAL_SLUGS:
            assert row["semantic_caveat"] == _MECHANICAL_LITERAL, (
                f"{slug!r}'s semantic_caveat must equal the D-04 literal {_MECHANICAL_LITERAL!r}, "
                f"got: {row['semantic_caveat']!r}"
            )
        elif slug in _GATED_SLUGS and slug != "pipeline-run-hitl":
            # Flow 2 (pipeline-run-hitl) IS the canonical text -- checked via the exact-match
            # branch below. Flows 3/4/7 append their own row-specific trailing clause to the
            # shared constant; that trailing clause must itself be a verbatim substring of the
            # source row's own (short, "Same as Flow 2 —") caveat cell.
            addendum = row["semantic_caveat"].replace(sig._GATE_AB_JUDGMENT_CAVEAT, "", 1).strip()
            assert addendum, (
                f"{slug!r}'s semantic_caveat must carry its own row-specific trailing clause "
                f"beyond the shared constant, got: {row['semantic_caveat']!r}"
            )
            assert addendum in src_caveat, (
                f"{slug!r}'s own trailing clause must be an exact substring of the source "
                f"table's flow {flow_num} Semantic Caveat cell -- got addendum:\n{addendum!r}\n"
                f"source cell:\n{src_caveat!r}"
            )
        else:
            assert row["semantic_caveat"] == src_caveat, (
                f"{slug!r}'s semantic_caveat must be verbatim-identical to the source table's "
                f"flow {flow_num} Semantic Caveat cell -- got:\n{row['semantic_caveat']!r}\n"
                f"expected:\n{src_caveat!r}"
            )


# --------------------------------------------------------------------------- Phase 4 Task 2: signal_table IR threading + render()

_SYNTHETIC_SIGNAL_TABLE = {
    "pass_signal": "p",
    "fail_signal": "f",
    "signal_source": "s",
    "semantic_caveat": "c",
}


def test_extract_signal_table_field_threads_through_ir() -> None:
    """extract(..., signal_table=...) returns an IR whose ir['signal_table'] equals the input unchanged."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        ir = g.extract(fixture, risk_tier="read-only", signal_table=_SYNTHETIC_SIGNAL_TABLE)

        assert ir.get("signal_table") == _SYNTHETIC_SIGNAL_TABLE, (
            f"extract(signal_table=...) must thread the 4-key dict through the IR unchanged "
            f"(pass-through, no re-derivation), got: {ir.get('signal_table')!r}"
        )


def test_extract_signal_table_omitted_by_default() -> None:
    """extract() with no signal_table argument produces an IR with no truthy signal_table key."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = _write_fixture(tmp, "gmj-fixture-flow.md", _FIXTURE_COMMAND_DOC)
        ir = g.extract(fixture, risk_tier="read-only")

        assert not ir.get("signal_table"), (
            f"extract() called with no signal_table argument must not force a truthy "
            f"signal_table key onto the IR (optional parameter, single-invocation "
            f"--command-file mode's existing call sites remain unaffected), got: "
            f"{ir.get('signal_table')!r}"
        )


def test_render_signal_table_produces_four_column_markdown_table() -> None:
    """render() on an IR carrying signal_table produces a 4-column Markdown table under PASS criteria."""
    ir = _synthetic_ir()
    ir["signal_table"] = _SYNTHETIC_SIGNAL_TABLE
    text = g.render(ir)

    assert "| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |" in text, (
        f"render() must emit the 4-column table header when ir['signal_table'] is present, "
        f"got:\n{text}"
    )
    for value in _SYNTHETIC_SIGNAL_TABLE.values():
        assert value in text, f"render() output must contain the signal_table cell value {value!r}, got:\n{text}"
    assert "A human operator confirms the observed output/state matches" not in text, (
        f"render() must replace the OLD generic PASS-criteria bullet when signal_table is "
        f"present, got:\n{text}"
    )


def test_render_falls_back_to_generic_bullet_when_signal_table_absent() -> None:
    """render() on an IR with no signal_table key falls back to the pre-Phase-4 generic bullet."""
    ir = _synthetic_ir()
    assert "signal_table" not in ir, "sanity check: _synthetic_ir() must not carry signal_table by default"
    text = g.render(ir)

    assert "A human operator confirms the observed output/state matches" in text, (
        f"render() must fall back to the pre-Phase-4 generic PASS-criteria bullet when "
        f"ir.get('signal_table') is absent (documented single-invocation-mode degraded-mode "
        f"fallback), got:\n{text}"
    )
    assert "| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |" not in text, (
        f"render() must not emit an empty/broken table when signal_table is absent, got:\n{text}"
    )

    ir_none = _synthetic_ir()
    ir_none["signal_table"] = None
    text_none = g.render(ir_none)
    assert "A human operator confirms the observed output/state matches" in text_none, (
        f"render() must also fall back to the generic bullet when signal_table is explicitly "
        f"None, got:\n{text_none}"
    )


def test_render_none_fully_mechanical_literal_reads_naturally() -> None:
    """render() renders the D-04 'None — fully mechanical' literal exactly inside the caveat cell."""
    ir = _synthetic_ir()
    ir["signal_table"] = {
        "pass_signal": "p",
        "fail_signal": "f",
        "signal_source": "s",
        "semantic_caveat": "None — fully mechanical",
    }
    text = g.render(ir)

    assert "None — fully mechanical" in text, (
        f"render() must render the exact D-04 literal string inside the Semantic Caveat "
        f"table cell, got:\n{text}"
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
