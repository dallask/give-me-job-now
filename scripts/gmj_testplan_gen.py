#!/usr/bin/env python3
"""Deterministic extractor+renderer CLI producing test-plan Markdown from a command doc.

This tool reads one ``.claude/commands/*.md`` file (frontmatter + body) and produces a
``docs/TESTPLAN-FORMAT-SPEC.md``-conformant Markdown test-plan file. It is a two-stage
pipeline mirroring ``scripts/gmj_cleanup_report.py``'s deterministic-script shape: an
``extract()`` step parses the command file into an in-memory, YAML-shaped intermediate
representation (IR) — a plain ``dict`` — and a separate ``render()`` step consumes that IR
to produce the final Markdown string. Nothing is written to disk until
``write_testplan()`` is called from ``main()``, and that is the ONLY filesystem-write call
in the whole module (mirrors ``write_report()``'s zero-mutation-outside-output-file
discipline in ``gmj_cleanup_report.py``).

**Generic by design (D-07/D-08/D-09).** ``--command-file`` accepts any
``.claude/commands/*.md`` path — there is no cleanup-wizard-specific hardcoding anywhere in
``extract()``, ``render()``, or ``main()``'s argument parsing. Cleanup-wizard
(``.claude/commands/gmj-cleanup-wizard.md``) is simply the first real invocation target
(Phase 2 proof-of-concept); the same script targets any other flow's command file
unchanged once Phase 3 scales rollout to the remaining flows.

**Safety guarantee.** Zero mutation outside the user-supplied ``--output`` path. A missing
or unparsable ``--command-file`` (missing file, malformed frontmatter fence, no citable
requirement-ID token) fails closed — ``main()`` prints a ``FAIL:``-prefixed message to
stderr and returns 1 without ever calling ``write_testplan()`` — never silently degrading
to an empty/placeholder test plan.

CLI: ``python3 scripts/gmj_testplan_gen.py --command-file
.claude/commands/gmj-cleanup-wizard.md --output docs/test-plans/cleanup-wizard.md``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root

# Matches the parenthetical requirement-ID citation convention this repo's command docs
# use, e.g. "(OPS-01)" in a description: line, or "**OPS-01**"/"satisfies OPS-01" in body
# prose. Requirement IDs are an uppercase-letter-and-hyphen prefix followed by digits
# (e.g. OPS-01, INTAKE-01, TPGEN-03) -- never matches a bare lowercase word.
REQUIREMENT_ID_RE = re.compile(r"\b([A-Z][A-Z-]*-\d+)\b")

# Section headings whose body text is scanned for documented CLI flags.
_FLAG_SECTION_HEADINGS = ("flags", "usage")

# The 4 frozen risk-tier names, reused verbatim from the `investigate` milestone's own
# taxonomy (never re-derived here) -- see
# .planning/workstreams/investigate/phases/01-flow-inventory-approach-comparison/01-FLOW-INVENTORY-AND-COMPARISON.md.
_VALID_RISK_TIERS = {"read-only", "local-safe", "live-cost", "destructive-if-confirmed"}

# A single documented flag line looks like: "- **`--repo-root <path>`** — testability-only. ..."
# or "- `--foo`: some purpose." Capture the flag token and the rest of the line as purpose.
# The purpose group (and its leading separator) is optional -- a terse `` - `--dry-run` ``
# bullet with no trailing dash/colon/em-dash description still matches (purpose=None),
# rather than silently dropping the flag from the extracted list entirely.
_FLAG_LINE_RE = re.compile(
    r"^-\s*\*{0,2}`(?P<flag>--[\w-]+(?:\s+<[\w-]+>)?)`\*{0,2}\s*(?:[—:-]\s*(?P<purpose>.+))?$"
)


def _split_frontmatter(text: str, command_file: Path) -> tuple[dict, str]:
    """Split ``text`` into (frontmatter dict, body str); raise ValueError if malformed.

    The command-file convention (mirroring every existing ``.claude/commands/*.md`` file,
    e.g. ``gmj-cleanup-wizard.md``) is a leading ``#``-level title line, THEN the
    ``---``-fenced frontmatter block, THEN the body — the fence is not required to be the
    file's very first line. This scans for the opening ``---`` fence on its own line
    anywhere in the file, so a leading title (or blank lines) before the fence is expected,
    not an error; a file with no ``---`` fence anywhere still raises ValueError.
    """
    lines = text.splitlines()
    opening_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            opening_idx = i
            break
    if opening_idx is None:
        raise ValueError(
            f"{command_file}: missing '---'-fenced frontmatter block "
            "(no '---' fence found anywhere in the file)"
        )
    closing_idx = None
    for i in range(opening_idx + 1, len(lines)):
        if lines[i].strip() == "---":
            closing_idx = i
            break
    if closing_idx is None:
        raise ValueError(f"{command_file}: frontmatter fence never closes ('---' not found)")
    fm_text = "\n".join(lines[opening_idx + 1 : closing_idx])
    body = "\n".join(lines[closing_idx + 1 :])
    data = yaml.safe_load(fm_text)
    if not isinstance(data, dict):
        raise ValueError(f"{command_file}: frontmatter block must parse to a YAML mapping")
    return data, body


def _extract_flags(body: str) -> list[dict[str, str]]:
    """Scan body for '## Usage'/'## Flags'-style sections and pull documented flag lines.

    A documented flag's purpose text may soft-wrap across multiple Markdown source lines
    within the same list item (a continuation line is indented and does not itself start a
    new `-`/`*` bullet or heading) — those continuation lines are folded into the same
    flag's ``purpose`` string so the extracted text is never silently truncated mid-sentence
    at the source file's line-wrap point.
    """
    flags: list[dict[str, str]] = []
    lines = body.splitlines()
    in_flag_section = False
    for line in lines:
        heading_match = re.match(r"^#{1,6}\s+(.*)$", line)
        if heading_match:
            heading_text = heading_match.group(1).strip().lower()
            in_flag_section = any(h in heading_text for h in _FLAG_SECTION_HEADINGS)
            continue
        if not in_flag_section:
            continue
        stripped = line.strip()
        flag_match = _FLAG_LINE_RE.match(stripped)
        if flag_match:
            purpose = flag_match.group("purpose")
            flags.append(
                {
                    "name": flag_match.group("flag").split()[0],
                    "purpose": purpose.strip() if purpose else "",
                }
            )
            continue
        # Continuation line: indented (part of the same list item), non-blank, and not
        # itself a new bullet/heading — fold it onto the most recently captured flag.
        if flags and line.strip() and line[:1] in (" ", "\t") and not stripped.startswith(("-", "*", "#")):
            flags[-1]["purpose"] = (flags[-1]["purpose"] + " " + stripped).strip()
    return flags


def _extract_behaviors(body: str) -> list[str]:
    """Scan body for real, concrete described behaviors/steps (Claude's Discretion heuristic).

    Pulls numbered-list items from an "## Interaction flow"/"## What to do"-style section,
    plus any fenced ```bash code block lines found anywhere in the body — these are the
    concrete, real commands/interaction-sequence facts render() needs. Never returns a
    placeholder; an empty list means the caller must decide if that is acceptable (extract()
    only raises for the mandatory requirement_id, not for behaviors, since behaviors are
    Claude's Discretion per 02-CONTEXT.md).

    A numbered list item's text may soft-wrap across multiple Markdown source lines, mirroring
    ``_extract_flags()``'s continuation-folding: those continuation lines are folded onto the
    same behavior string so the extracted text is never silently truncated mid-sentence at the
    source file's line-wrap point. Both leading and trailing ``**`` bold markers are stripped
    from the captured text.
    """
    behaviors: list[str] = []
    lines = body.splitlines()
    in_code_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block and stripped:
            if not stripped.startswith("#"):
                behaviors.append(stripped)
            continue
        numbered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered_match:
            # Strip a leading bold-title marker pair, e.g. "**Checkbox selection.**  A ..."
            # -> "Checkbox selection.  A ..." — the closing "**" typically lands right after
            # the short bold title, not at the end of the (possibly still-wrapping) line, so
            # this cannot be anchored with a trailing "$" the way the numbering prefix can.
            text = numbered_match.group(1).strip()
            text = re.sub(r"^\*\*(.+?)\*\*", r"\1", text, count=1)
            behaviors.append(text.strip())
            continue
        # Continuation line: indented (part of the same list item), non-blank, and not
        # itself a new bullet/heading/numbered-item — fold it onto the most recently
        # captured behavior, mirroring _extract_flags()'s continuation handling.
        if (
            behaviors
            and not in_code_block
            and line.strip()
            and line[:1] in (" ", "\t")
            and not stripped.startswith(("-", "*", "#", "```"))
            and not re.match(r"^\d+\.\s", stripped)
        ):
            behaviors[-1] = (behaviors[-1] + " " + stripped).strip()
    return behaviors


def _extract_requirement_id(frontmatter: dict, body: str, command_file: Path) -> str:
    """Find a real requirement-ID token in the frontmatter description or body; else raise.

    Scans the frontmatter's ``description`` field first (the canonical citation site per
    D-04/Plan 01), then the body. Raises ValueError naming the file if no token is found
    anywhere — per docs/TESTPLAN-FORMAT-SPEC.md's Proves field mandate, a command file with
    no citable requirement ID cannot produce a spec-conformant **Proves:** line, so this is
    a real, fail-closed extraction error, never a silently-degraded IR field.
    """
    description = str(frontmatter.get("description") or "")
    match = REQUIREMENT_ID_RE.search(description)
    if match:
        return match.group(1)
    match = REQUIREMENT_ID_RE.search(body)
    if match:
        return match.group(1)
    raise ValueError(
        f"{command_file}: no requirement-ID token (e.g. OPS-01, INTAKE-01) found in "
        "frontmatter description or body — cannot produce a spec-conformant Proves field"
    )


def _extract_no_bypass_flag(body: str) -> bool:
    """True if the body explicitly states no confirm-bypass flag exists (cleanup-wizard-style).

    Requires a near-adjacency match between "no", "bypass", and "flag" (within ~40 chars of
    each other, same sentence) rather than mere whole-body word co-occurrence — a body that
    merely mentions "bypass" and "flag" near unrelated "no" tokens elsewhere (e.g. "no way to
    bypass validation, but does support a --flag for other purposes") must not false-positive.
    """
    lowered = body.lower()
    if "no bypass flag" in lowered:
        return True
    # Tight adjacency: "no" must be followed, within a handful of tokens (tolerating
    # Markdown punctuation like "**"/backticks between words), directly by "bypass flag" as
    # a unit — this rejects wide-window whole-sentence co-occurrence false positives such as
    # "no way to bypass validation, but does support a --flag for other purposes" or
    # "no automatic bypass exists; the flag --dry-run is separate", where "bypass" and
    # "flag" are not actually asserting the non-existence of a bypass flag together.
    return bool(re.search(r"\bno\b[\W_]*(?:\S+[\W_]+){0,4}bypass\W*flag\b", lowered))


def _validate_risk_tier(risk_tier: str, command_file: Path) -> str:
    """Fail-closed validation of ``risk_tier`` against the 4 frozen tier names.

    Mirrors ``_extract_requirement_id``'s raise-with-filename-context style exactly: any
    value not in ``_VALID_RISK_TIERS`` (typo, omission, or invented tier name) raises
    ``ValueError`` naming both the offending file and the invalid value — never silently
    defaulting to ``read-only``/no-warning.
    """
    if risk_tier not in _VALID_RISK_TIERS:
        raise ValueError(
            f"{command_file}: risk_tier {risk_tier!r} is not one of the 4 frozen tiers "
            f"{sorted(_VALID_RISK_TIERS)}"
        )
    return risk_tier


def extract(command_file: Path, risk_tier: str, requirement_id_override: str | None = None) -> dict:
    """Parse ``command_file`` (a ``.claude/commands/*.md`` file) into an in-memory dict IR.

    Reads the frontmatter (``---``-fenced, YAML) and body, pulling out: ``flow_name``/
    ``slug`` (derived from the filename), the frontmatter ``description``, a ``flags`` list
    (name + purpose, scanned from Usage/Flags-style sections), a ``behaviors`` list (real
    commands/interaction steps scanned from body prose/code blocks), a ``requirement_id``,
    and a ``no_bypass_flag`` boolean fact when the body states one explicitly. Returns a
    plain dict (D-02's YAML-shaped IR) — never writes anything to disk (D-03: in-memory
    only).

    ``risk_tier`` is required and validated fail-closed against the 4 frozen tier names
    (``_VALID_RISK_TIERS``) via ``_validate_risk_tier`` — an unrecognized value raises
    ``ValueError`` immediately, before any other extraction work. Every IR this function
    returns carries a validated ``risk_tier`` key (always present, unlike the optional
    ``no_bypass_flag`` key).

    ``requirement_id_override``, when truthy, is used verbatim as ``ir["requirement_id"]``
    instead of calling ``_extract_requirement_id()`` — this bypasses the fail-closed raise
    for command files that carry no citable requirement-ID token of their own. The override
    is trusted human-supplied input (per the security threat model: it is a planning-time
    discipline that the override cites a real requirement, not a code-level check) and is
    never re-validated against a real requirements doc by this function. When
    ``requirement_id_override`` is falsy/omitted, the existing fail-closed
    ``_extract_requirement_id()`` behavior is preserved unchanged.

    Raises ``FileNotFoundError`` if ``command_file`` does not exist; raises ``ValueError``
    if ``risk_tier`` is not one of the 4 frozen tiers, if the frontmatter fence is
    missing/malformed, the fenced block does not parse to a YAML mapping, or (absent an
    override) no requirement-ID token is found anywhere in the file.
    """
    if not command_file.is_file():
        raise FileNotFoundError(f"command file not found: {command_file}")

    _validate_risk_tier(risk_tier, command_file)

    text = command_file.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, command_file)

    slug = command_file.stem
    description = str(frontmatter.get("description") or "")
    flags = _extract_flags(body)
    behaviors = _extract_behaviors(body)
    if requirement_id_override:
        requirement_id = requirement_id_override
    else:
        requirement_id = _extract_requirement_id(frontmatter, body, command_file)
    no_bypass_flag = _extract_no_bypass_flag(body)

    ir: dict = {
        "flow_name": slug,
        "slug": slug,
        "description": description,
        "flags": flags,
        "behaviors": behaviors,
        "requirement_id": requirement_id,
        "source_file": str(command_file),
        "risk_tier": risk_tier,
    }
    if no_bypass_flag:
        ir["no_bypass_flag"] = True
    return ir


# --------------------------------------------------------------------------- render()

# Warning body text for the 2 warn-worthy risk tiers, keyed by exact tier name. Only
# "live-cost" and "destructive-if-confirmed" get entries -- "read-only"/"local-safe" are
# deliberately absent so `.get(risk_tier)` returning None for those two IS the omission
# mechanism (no explicit if/else branch needed to skip them). Each tier's prose names its
# own real blast radius; never a generic sentence shared across tiers.
_TIER_WARNINGS: dict[str, str] = {
    "live-cost": (
        "**live-cost**: Running this flow's live steps incurs real LLM/API spend and makes "
        "real external network calls. There is no human pause to abort mid-run in "
        "autonomous mode. Confirm cost expectations before running the live steps."
    ),
    "destructive-if-confirmed": (
        "**destructive-if-confirmed**: This flow can permanently delete real local data if "
        "a human confirms the deletion prompt. Run only against a disposable fixture "
        "directory, never a real working copy with data you need, unless deletion is the "
        "intended outcome."
    ),
}


def _capability_sentence(ir: dict) -> str:
    """Build a concrete, non-generic capability sentence from the IR's behavior/flag data.

    Mirrors docs/HUMAN-TESTING-PLAN.md's own `**Proves:** OPS-01 — ...` pattern: names what
    the test actually demonstrates, drawn from real extracted facts, never generic filler.
    """
    parts: list[str] = []
    description = str(ir.get("description") or "").strip()
    if description:
        # Strip a parenthetical requirement-ID citation wherever it occurs in the
        # description, not just at the very end -- render() already prepends the
        # requirement_id via "**Proves:** {requirement_id} — ...", so a mid-sentence
        # citation (the frontmatter description-field fallback explicitly scans for, per
        # this module's own docstring) must not survive into the capability sentence and
        # duplicate the ID.
        description = re.sub(r"\s*\([A-Z][A-Z-]*-\d+\)\.?", "", description).strip(". ").strip()
        if description:
            parts.append(description)
    if ir.get("no_bypass_flag"):
        parts.append("with no confirm-bypass flag anywhere in its CLI")
    if not parts:
        parts.append(f"the {ir.get('flow_name') or ir.get('slug') or 'flow'} behaves as documented")
    return "; ".join(parts) + "."


def _render_steps_block(ir: dict) -> list[str]:
    """Build the Steps section lines for one generated test case, per the Deterministic Backstop Convention."""
    lines: list[str] = []
    behaviors = ir.get("behaviors") or ir.get("steps") or []
    real_commands = [b for b in behaviors if b.strip().startswith(("python3 ", "claude ", "bash "))]

    # A bare `claude ...` REPL-entry line with no script/tool argument (e.g.
    # `claude --dangerously-skip-permissions`) documents an *alternative* way to reach a
    # live TTY session, not a distinct sequential step — many command docs show it beside
    # the flow's own script invocation as "either way requires a live TTY", not "run both in
    # order". Drop it whenever a real script-invocation command (one naming a `.py`/`.sh`
    # file) is present alongside it, so Non-Executability Criterion 2 (no uninterrupted
    # multi-command copy-paste-run-all block) isn't violated by bundling two independent
    # entry points into one numbered sequence.
    script_commands = [c for c in real_commands if re.search(r"\.(py|sh)\b", c)]
    if script_commands and len(script_commands) != len(real_commands):
        real_commands = script_commands

    if real_commands:
        lines.append("**Steps (live):**")
        lines.append("```bash")
        if len(real_commands) > 1:
            for i, cmd in enumerate(real_commands, start=1):
                lines.append(f"{i}. {cmd}")
        else:
            lines.append(real_commands[0])
        lines.append("```")
        lines.append("")
        lines.append("**Steps (deterministic backstop):**")
        lines.append("No deterministic backstop exists for this step.")
    else:
        lines.append("**Steps:**")
        lines.append("```bash")
        source = ir.get("source_file") or "the command file"
        lines.append(f"# See {source} for the exact invocation.")
        lines.append("```")
    return lines


def render(ir: dict) -> str:
    """Consume the extract()-produced IR to build spec-conformant Markdown.

    Produces, in order: (1) title + one-line purpose; (2) setup/precondition checklist
    (explicit "no preconditions" statement if the IR carries none); (3) one per-test
    Markdown block with all six required fields in the mandated order (ID heading,
    **Proves:**, **Why human:**, **Steps** [live/deterministic-backstop sub-labels where a
    backstop applies], **Expected:**, **PASS criteria:**); (4) a closing
    generation-provenance note naming the IR's source_file and this module as the
    generation source (no schema file named, per D-06).

    Raises ValueError if ``ir['requirement_id']`` is missing/empty — render() must fail
    closed rather than emit a **Proves:** line with no ID or a placeholder, independent of
    extract()'s own fail-closed guarantee (render() may be called directly with a hand-built
    or future non-command-file-sourced IR).
    """
    requirement_id = ir.get("requirement_id")
    if not requirement_id:
        raise ValueError(
            "render() requires a non-empty ir['requirement_id'] to build a spec-conformant "
            "**Proves:** line — refusing to emit a placeholder/blank Proves field"
        )

    flow_name = ir.get("flow_name") or ir.get("slug") or "flow"
    source_file = ir.get("source_file") or "an unnamed command file"

    lines: list[str] = []

    # (1) Title + one-line purpose.
    lines.append(f"# Test Plan — {flow_name}")
    lines.append("")

    # Tier-aware structural warning block -- present only for live-cost/
    # destructive-if-confirmed tiers (an omitted _TIER_WARNINGS entry for
    # read-only/local-safe IS the omission mechanism; render() stays tolerant of any of
    # the 4 valid tier strings and never raises on tier value here -- validation belongs
    # in extract()/_validate_risk_tier).
    warning = _TIER_WARNINGS.get(ir.get("risk_tier"))
    if warning:
        lines.append(f"> ⚠️ {warning}")
        lines.append("")

    lines.append(f"This file verifies the `{flow_name}` flow for a human operator running it directly.")
    lines.append("")

    # (2) Setup / precondition checklist.
    lines.append("## Setup & Preconditions")
    lines.append("")
    flags = ir.get("flags") or []
    if flags:
        for flag in flags:
            name = flag.get("name", "")
            purpose = flag.get("purpose", "")
            lines.append(f"- `{name}` — {purpose}" if purpose else f"- `{name}`")
    else:
        lines.append(
            "No preconditions — this flow has no setup requirements beyond the repo's "
            "standard `pip install` step."
        )
    lines.append("")

    # (3) Per-test block.
    lines.append(f"## Test 1 — {flow_name}")
    lines.append("")
    lines.append(f"**Proves:** {requirement_id} — {_capability_sentence(ir)}")
    lines.append("")
    lines.append(
        "**Why human:** this flow's behavior is grounded in real command output that "
        "requires human judgment or a live environment this plain-python3 harness cannot "
        "exercise on its own."
    )
    lines.append("")
    lines.extend(_render_steps_block(ir))
    lines.append("")
    lines.append(
        f"**Expected:** running the steps above against `{source_file}`'s documented "
        "behavior produces the outcome described in that file's own frontmatter/body — "
        "inspect stdout/stderr and any named output paths for the concrete result."
    )
    lines.append("")
    lines.append("**PASS criteria:**")
    lines.append(
        f"- A human operator confirms the observed output/state matches {requirement_id}'s "
        "documented behavior above by reading the real output, not by delegating to a "
        "script's exit code alone."
    )
    lines.append("")

    # (4) Closing generation-provenance note.
    lines.append("---")
    lines.append("")
    lines.append(
        f"_Generated from `{source_file}` by `scripts/gmj_testplan_gen.py`. This file is "
        "not an executable artifact — it is prose a human reads and acts on manually._"
    )

    return "\n".join(lines) + "\n"


def write_testplan(text: str, output_path: Path) -> None:
    """The single filesystem-write call in this module — overwrite output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic extractor+renderer: turn a .claude/commands/*.md file into a "
            "docs/TESTPLAN-FORMAT-SPEC.md-conformant Markdown test-plan file."
        )
    )
    parser.add_argument(
        "--command-file", type=Path, required=True,
        help="Path to the .claude/commands/*.md file to extract from (any flow's command doc).",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="Markdown test-plan output path (overwritten each run).",
    )
    args = parser.parse_args(argv)

    try:
        ir = extract(args.command_file)
        text = render(ir)
    except Exception as exc:  # noqa: BLE001  fail-closed: never write a degraded output
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    write_testplan(text, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
