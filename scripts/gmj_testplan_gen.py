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

import gmj_testplan_signals as _signals

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

    Continuation-folding is scoped to the current ``##``/``###`` heading section, mirroring
    ``_extract_flags()``'s own ``in_flag_section`` reset on every heading: crossing into a new
    section clears the "fold onto the last-captured behavior" eligibility, so a later,
    unrelated section's bulleted/indented prose can never get silently glued onto a behavior
    captured under a previous heading (or inside a previous fenced code block).
    """
    behaviors: list[str] = []
    lines = body.splitlines()
    in_code_block = False
    # Tracks which heading section the most recently captured behavior belongs to, so
    # continuation-folding never crosses a heading boundary (see docstring above).
    current_section = 0
    last_behavior_section: int | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            heading_match = re.match(r"^#{1,6}\s+(.*)$", line)
            if heading_match:
                current_section += 1
                continue
        if in_code_block and stripped:
            if not stripped.startswith("#"):
                behaviors.append(stripped)
                last_behavior_section = current_section
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
            last_behavior_section = current_section
            continue
        # Continuation line: indented (part of the same list item), non-blank, not itself a
        # new bullet/heading/numbered-item, AND in the same heading section as the most
        # recently captured behavior — fold it onto that behavior, mirroring
        # _extract_flags()'s continuation handling. The section-match guard is what stops a
        # later, unrelated section's continuation-looking lines from leaking onto a behavior
        # captured under an earlier heading (or fenced code block).
        if (
            behaviors
            and not in_code_block
            and last_behavior_section == current_section
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


def extract(
    command_file: Path,
    risk_tier: str,
    requirement_id_override: str | None = None,
    flow_slug_override: str | None = None,
    signal_table: dict | None = None,
) -> dict:
    """Parse ``command_file`` (a ``.claude/commands/*.md`` file) into an in-memory dict IR.

    Reads the frontmatter (``---``-fenced, YAML) and body, pulling out: ``flow_name``/
    ``slug`` (derived from the filename, unless overridden — see ``flow_slug_override``
    below), the frontmatter ``description``, a ``flags`` list (name + purpose, scanned from
    Usage/Flags-style sections), a ``behaviors`` list (real commands/interaction steps
    scanned from body prose/code blocks), a ``requirement_id``, and a ``no_bypass_flag``
    boolean fact when the body states one explicitly. Returns a plain dict (D-02's
    YAML-shaped IR) — never writes anything to disk (D-03: in-memory only).

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

    ``flow_slug_override``, when truthy, is used verbatim as both ``ir["flow_name"]`` and
    ``ir["slug"]`` instead of ``command_file.stem`` — required whenever more than one
    FLOW_MANIFEST row shares the same ``command_file`` (e.g. the pipeline-run-hitl/
    pipeline-run-autonomous pair both sourcing ``gmj-pipeline-run.md``, per Decision 1),
    so each generated document's own title/body text names its own distinct flow instead of
    both rows rendering byte-identical "gmj-pipeline-run" prose that gives a reader no way
    to tell which risk-tier/mode a given file actually documents. When falsy/omitted, the
    existing ``command_file.stem`` derivation is preserved unchanged (single-invocation CLI
    mode never needed this distinction, since one command file always maps to one output).

    ``signal_table``, when truthy, is a 4-key dict (``pass_signal``/``fail_signal``/
    ``signal_source``/``semantic_caveat``) threaded verbatim into ``ir["signal_table"]`` --
    a pure pass-through, never re-derived or re-validated by this function (the caller, e.g.
    ``_run_all_mode()`` looking up ``gmj_testplan_signals.SIGNAL_TABLE_BY_SLUG`` by ``slug``,
    owns that verbatim-transcription guarantee). Optional and falsy-by-default: when omitted,
    the IR carries no ``signal_table`` key at all (mirrors the existing ``no_bypass_flag``
    optional-key convention), so single-invocation ``--command-file`` mode's existing call
    sites remain unaffected and ``render()`` falls back to its pre-Phase-4 generic PASS-criteria
    bullet for such IRs.

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

    slug = flow_slug_override or command_file.stem
    description = str(frontmatter.get("description") or "")
    flags = _extract_flags(body)
    behaviors = _extract_behaviors(body)
    if requirement_id_override:
        requirement_id = requirement_id_override
    else:
        requirement_id = _extract_requirement_id(frontmatter, body, command_file)
    no_bypass_flag = _extract_no_bypass_flag(body)

    # Cite a portable, repo-relative source path when command_file resolves inside
    # REPO_ROOT (the FLOW_MANIFEST rows always do, since they're built as
    # REPO_ROOT / ".claude" / "commands" / ...), so generated docs never leak the
    # invoking checkout's absolute filesystem path (e.g. a throwaway git-worktree
    # directory that won't exist once the worktree is removed). A command_file
    # supplied outside REPO_ROOT (not a FLOW_MANIFEST case today, but --command-file
    # accepts any path per this module's own "generic by design" docstring) falls
    # back to the resolved absolute path unchanged.
    try:
        source_file = str(command_file.resolve().relative_to(REPO_ROOT))
    except ValueError:
        source_file = str(command_file)

    ir: dict = {
        "flow_name": slug,
        "slug": slug,
        "description": description,
        "flags": flags,
        "behaviors": behaviors,
        "requirement_id": requirement_id,
        "source_file": source_file,
        "risk_tier": risk_tier,
    }
    if no_bypass_flag:
        ir["no_bypass_flag"] = True
    if signal_table:
        ir["signal_table"] = signal_table
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


# Matches a slash-command follow-up line typed inside a live Claude Code session after
# `claude ...` has already put the operator at the REPL (e.g. `/gmj-pipeline-run`,
# `/gmj-batch --resume`, `/gmj-runs run inspect <id>`) — these lines never start with
# python3/claude/bash but are still real, runnable-as-typed commands per
# docs/TESTPLAN-FORMAT-SPEC.md's Steps field requirement (CR-02).
_SLASH_COMMAND_RE = re.compile(r"^/gmj-[\w-]+\b")


def _render_steps_block(ir: dict) -> list[str]:
    """Build the Steps section lines for one generated test case, per the Deterministic Backstop Convention."""
    lines: list[str] = []
    behaviors = ir.get("behaviors") or ir.get("steps") or []
    real_commands = [
        b for b in behaviors
        if b.strip().startswith(("python3 ", "claude ", "bash ")) or _SLASH_COMMAND_RE.match(b.strip())
    ]

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

    # A `claude ...` REPL-entry line followed by exactly one slash-command follow-up line
    # (its primary invocation) is a genuine 2-step sequence: enter the REPL, then type the
    # command (CR-02). Any FURTHER slash-command lines beyond that first follow-up (e.g.
    # `/gmj-batch --resume`, `/gmj-runs run inspect <id>`) are documented alternative
    # subcommands/modes, not additional sequential steps -- keep only the primary follow-up
    # so the rendered Steps block stays a genuine ordered sequence, never a bundle of
    # independent alternatives (CR-03's Non-Executability Criterion 2).
    claude_lines = [c for c in real_commands if c.strip().startswith("claude ")]
    slash_lines = [c for c in real_commands if _SLASH_COMMAND_RE.match(c.strip())]
    if claude_lines and slash_lines and len(slash_lines) > 1:
        real_commands = [c for c in real_commands if c not in slash_lines[1:]]

    # Independent, mutually-exclusive script-invocation alternatives (e.g. the same script
    # run with vs. without `--manage`) are not a sequence either -- surface each as its own
    # sub-block with an explicit "run ONE of the following" note between the judgment
    # points, rather than numbering them together inside one fenced block (CR-03). Compare
    # only the invocation itself (strip any trailing `# ...` inline comment first, then
    # split off the first `--flag`), so a same-script/different-flag pair like
    # `gmj_dashboard.py            # read-only ...` vs `gmj_dashboard.py --manage   # ...`
    # is correctly recognized as sharing one base command.
    def _base_command(c: str) -> str:
        no_comment = re.split(r"\s+#", c.strip(), maxsplit=1)[0].strip()
        return re.split(r"\s+--", no_comment, maxsplit=1)[0].strip()

    is_alternatives = (
        len(real_commands) > 1
        and not claude_lines
        and len({_base_command(c) for c in real_commands}) == 1
    )

    if real_commands:
        lines.append("**Steps (live):**")
        if is_alternatives:
            lines.append(
                "Run ONE of the following, not both — these are independent, "
                "mutually-exclusive entry points. Inspect the output before proceeding."
            )
            for i, cmd in enumerate(real_commands, start=1):
                lines.append("")
                lines.append(f"Option {i}:")
                lines.append("```bash")
                lines.append(cmd)
                lines.append("```")
        elif len(real_commands) > 1:
            lines.append("```bash")
            for i, cmd in enumerate(real_commands, start=1):
                lines.append(f"{i}. {cmd}")
            lines.append("```")
        else:
            lines.append("```bash")
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


def _escape_table_cell(value: str) -> str:
    """Escape a literal pipe `|` inside a Markdown table cell so it can never break the table."""
    return value.replace("|", "\\|")


def _render_signal_table_block(ir: dict) -> list[str]:
    """Build the PASS-criteria block: a 4-column signal table from ir['signal_table'] (D-03).

    Reads ``ir.get("signal_table")``: when truthy, renders a Markdown table (Pass Signal /
    Fail Signal / Signal Source / Semantic Caveat) from its 4 verbatim-transcribed cell
    values. When falsy (absent or None -- e.g. a single-invocation ``--command-file`` IR with
    no manifest-driven signal-table lookup), falls back unchanged to the pre-Phase-4 generic
    PASS-criteria bullet -- an explicit, tested, documented degraded-mode fallback, never a
    raise (see 04-RESEARCH.md's asymmetric fail-closed/graceful-fallback design: ``--all``
    mode's mandatory-signal-table enforcement is Plan 02's concern, out of this helper's
    scope).
    """
    lines: list[str] = []
    lines.append("**PASS criteria:**")
    signal_table = ir.get("signal_table")
    if signal_table:
        lines.append("")
        lines.append("| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |")
        lines.append("|---|---|---|---|")
        pass_signal = _escape_table_cell(str(signal_table.get("pass_signal", "")))
        fail_signal = _escape_table_cell(str(signal_table.get("fail_signal", "")))
        signal_source = _escape_table_cell(str(signal_table.get("signal_source", "")))
        semantic_caveat = _escape_table_cell(str(signal_table.get("semantic_caveat", "")))
        lines.append(f"| {pass_signal} | {fail_signal} | {signal_source} | {semantic_caveat} |")
    else:
        requirement_id = ir.get("requirement_id")
        lines.append(
            f"- A human operator confirms the observed output/state matches {requirement_id}'s "
            "documented behavior above by reading the real output, not by delegating to a "
            "script's exit code alone."
        )
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

    The **PASS criteria:** block is built by ``_render_signal_table_block(ir)``: a 4-column
    Markdown table (Pass Signal / Fail Signal / Signal Source / Semantic Caveat) when
    ``ir.get("signal_table")`` is truthy, falling back to the pre-Phase-4 generic bullet
    otherwise (D-03; see that helper's own docstring for the fallback rationale).

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
    lines.extend(_render_signal_table_block(ir))
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


# --------------------------------------------------------------------------- FLOW_MANIFEST
#
# The 10-row flow -> command-file -> risk_tier -> requirement_id_override manifest driving
# main()'s --all mode (Plan 02). Resolves the 3 open design questions RESEARCH.md flagged as
# blockers (03-RESEARCH.md "Open Questions"), each recorded here as the binding decision and
# rationale — not just in the plan file — per RESEARCH.md's own framing that this must not be
# "silently picked without stating why".
#
# Decision 1 (flows 2+3, RESEARCH.md Open Question 1): TPGEN-06's success criterion 2 literally
# requires "all 10 flows have a generated file" and no CONTEXT.md exists to confirm a narrower
# reading interactively (RESEARCH.md's own recommendation flagged this as needing explicit
# confirmation, which this planning session cannot obtain without a human present) — so this
# resolves via the literal-compliant option: generate TWO output files from the single shared
# source `.claude/commands/gmj-pipeline-run.md`, one per manifest row, each tagged at its own
# accurate tier rather than collapsing to worst-case-only. Row A: slug="pipeline-run-hitl",
# risk_tier="local-safe" (flow 2's true tier — the default human-in-the-loop mode, human approves
# after each gate pass). Row B: slug="pipeline-run-autonomous", risk_tier="live-cost" (flow 3's
# true tier — real LLM/API spend end to end, no human pause to abort). Both rows source the same
# command_file; extract()'s own body-scan finds EXEC-07 (the "## CLI-only invocation (EXEC-07)"
# heading) for both — accurate for both modes since EXEC-07 covers the shared CLI-invocation
# capability itself, not a mode-specific claim, so no requirement_id_override is needed for
# either row. Both rows DO set flow_slug_override (their own manifest slug), since without it
# extract()'s default command_file.stem derivation ("gmj-pipeline-run") would make both rows'
# generated title/body text byte-identical except for the warning block -- a reader could not
# tell pipeline-run-hitl.md and pipeline-run-autonomous.md apart from their body prose alone
# (Plan 03's own real-run discovery; see 03-03-SUMMARY.md deviations). This preserves both
# flows' asymmetric risk profile (Pitfall 2's own warning against flattening it into one tier)
# and satisfies TPGEN-06's literal "all 10 flows" wording without requiring an unconfirmable
# interpretive narrowing.
#
# Decision 2 (flow 5, RESEARCH.md Open Question 2): source
# `.claude/commands/gmj-pipeline/scout.md` (the nearest real doc; RESEARCH.md's option (c)), with
# requirement_id_override="GUIDE-04" — a real, verifiable requirement ID from
# .planning/REQUIREMENTS.md covering exactly this flow's behavior (missing firecrawl-py
# dependency surfaces a clear upfront hint before dispatch). Tier: live-cost (per the investigate
# inventory, still fully scoped by config/sources.yaml's board/geo/language allow-list — a
# transport-only switch, but live network/LLM spend nonetheless). Output file:
# docs/test-plans/firecrawl-search.md.
#
# Decision 3 (flow 7, RESEARCH.md Open Question 3): hand-construct the IR dict for this one flow,
# bypassing extract()'s frontmatter-parsing path entirely (RESEARCH.md's recommended option — no
# second parsing code path added to extract() for a single one-off source shape). Source doc:
# docs/RUNBOOK.md (named as source_file in the hand-built IR, even though it's not parsed by
# extract()). requirement_id_override is NOT applicable here since no extract() call happens at
# all — the hand-built IR's requirement_id field is set directly to "OPS-02", the real ID cited
# verbatim in scripts/ops/gmj_cron_run.sh's own header comment (lines 4-5). Tier: live-cost
# (drives the autonomous flow, unattended, repeatedly, per the investigate inventory's own D-14
# reasoning). Output file: docs/test-plans/scheduled-runs.md.
#
# Do NOT include gmj-collective.md or any gmj-pipeline/{freeze,compose,verify,evaluate,generate}.md
# sub-step file as its own manifest row (RESEARCH.md Pitfall 1: these are internal pipeline steps,
# not top-level flows in the 10-flow inventory).
FLOW_MANIFEST: list[dict] = [
    {
        "slug": "initial-configuration",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-interview.md",
        "risk_tier": "local-safe",
        "requirement_id_override": None,
    },
    {
        # Decision 1, Row A (flow 2 — HITL mode). flow_slug_override is required here:
        # both this row and the next share command_file (gmj-pipeline-run.md), so without
        # an override extract()'s default command_file.stem-derived flow_name/slug
        # ("gmj-pipeline-run") would make both rows' generated title/body text byte-
        # identical except for the warning block, defeating the point of two separate
        # per-tier files (see extract()'s flow_slug_override docstring).
        "slug": "pipeline-run-hitl",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-pipeline-run.md",
        "risk_tier": "local-safe",
        "requirement_id_override": None,
        "flow_slug_override": "pipeline-run-hitl",
    },
    {
        # Decision 1, Row B (flow 3 — autonomous mode, same source file as above).
        "slug": "pipeline-run-autonomous",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-pipeline-run.md",
        "risk_tier": "live-cost",
        "requirement_id_override": None,
        "flow_slug_override": "pipeline-run-autonomous",
    },
    {
        "slug": "multi-offer-batch",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-batch.md",
        "risk_tier": "live-cost",
        "requirement_id_override": None,
    },
    {
        # Decision 2 (flow 5 — Firecrawl): sourced from scout.md, GUIDE-04 override.
        "slug": "firecrawl-search",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-pipeline" / "scout.md",
        "risk_tier": "live-cost",
        "requirement_id_override": "GUIDE-04",
    },
    {
        "slug": "cv-template",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-template.md",
        "risk_tier": "local-safe",
        "requirement_id_override": None,
    },
    {
        # Decision 3 (flow 7 — scheduled/unattended runs): hand-built IR, no command_file,
        # bypasses extract() entirely; render() consumes this dict directly.
        "slug": "scheduled-runs",
        "command_file": None,
        "risk_tier": "live-cost",
        "requirement_id_override": None,
        "hand_built_ir": {
            "flow_name": "scheduled-runs",
            "slug": "scheduled-runs",
            "description": (
                "Run the autonomous pipeline (/gmj-batch mode=autonomous) unattended on a "
                "recurring OS-native schedule (cron or launchd) via "
                "scripts/ops/gmj_cron_run.sh, with a non-blocking overlap guard."
            ),
            "flags": [],
            "behaviors": [
                "bash scripts/ops/gmj_cron_run.sh",
                "launchctl load ~/Library/LaunchAgents/com.gmj.cron-run.plist",
            ],
            "requirement_id": "OPS-02",
            "source_file": "docs/RUNBOOK.md",
            "risk_tier": "live-cost",
            "signal_table": _signals.SIGNAL_TABLE_BY_SLUG["scheduled-runs"],
        },
    },
    {
        "slug": "resume-flow",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-runs.md",
        "risk_tier": "read-only",
        "requirement_id_override": None,
    },
    {
        "slug": "operator-monitoring",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-dashboard.md",
        "risk_tier": "local-safe",
        "requirement_id_override": None,
    },
    {
        "slug": "cleanup-wizard",
        "command_file": REPO_ROOT / ".claude" / "commands" / "gmj-cleanup-wizard.md",
        "risk_tier": "destructive-if-confirmed",
        "requirement_id_override": None,
    },
]


# --------------------------------------------------------------------------- CLI

DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "test-plans"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic extractor+renderer: turn a .claude/commands/*.md file into a "
            "docs/TESTPLAN-FORMAT-SPEC.md-conformant Markdown test-plan file. Supports EITHER "
            "a single-invocation mode (--command-file/--output/--risk-tier) OR a manifest-"
            "driven multi-flow mode (--all[/--output-dir]) generating one file per "
            "FLOW_MANIFEST row."
        )
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--command-file", type=Path,
        help="Path to the .claude/commands/*.md file to extract from (single-invocation mode).",
    )
    mode_group.add_argument("--all",
        action="store_true",
        help="Manifest-driven mode: generate one test-plan file per FLOW_MANIFEST row.",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Markdown test-plan output path (single-invocation mode only; overwritten each run).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory the --all mode writes its generated files into (default: "
            "docs/test-plans/), one file per FLOW_MANIFEST row named '<slug>.md'."
        ),
    )
    parser.add_argument("--risk-tier",
        choices=sorted(_VALID_RISK_TIERS),
        help="Risk tier for the single-invocation --command-file/--output path (required with that mode).",
    )
    parser.add_argument(
        "--requirement-id-override",
        help="Optional requirement-ID override for the single-invocation --command-file/--output path.",
    )
    args = parser.parse_args(argv)

    if args.all:
        # --output/--risk-tier/--requirement-id-override are single-invocation-mode-only
        # flags; _run_all_mode() never reads them (each FLOW_MANIFEST row carries its own
        # risk_tier/requirement_id_override, and --output-dir is the --all-mode output
        # knob). Fail closed and name every ignored flag rather than silently discarding a
        # value the user believed would narrow/override the manifest (WR-02).
        ignored = []
        if args.output:
            ignored.append(f"--output={args.output}")
        if args.risk_tier:
            ignored.append(f"--risk-tier={args.risk_tier}")
        if args.requirement_id_override:
            ignored.append(f"--requirement-id-override={args.requirement_id_override}")
        if ignored:
            print(
                "FAIL: --all does not accept " + ", ".join(ignored) + " -- these flags only "
                "apply to single-invocation (--command-file) mode and would be silently "
                "ignored; --all's per-row risk_tier/requirement_id_override come from "
                "FLOW_MANIFEST, and its output location is --output-dir.",
                file=sys.stderr,
            )
            return 1
        return _run_all_mode(args.output_dir)

    if not args.output:
        print("FAIL: --output is required with --command-file", file=sys.stderr)
        return 1
    if not args.risk_tier:
        print("FAIL: --risk-tier is required with --command-file", file=sys.stderr)
        return 1

    try:
        ir = extract(
            args.command_file,
            risk_tier=args.risk_tier,
            requirement_id_override=args.requirement_id_override,
        )
        text = render(ir)
    except Exception as exc:  # noqa: BLE001  fail-closed: never write a degraded output
        # Include type(exc).__name__ so an unexpected TypeError/AttributeError (likely a
        # real bug) is visually distinguishable in CI/stderr output from an expected,
        # documented ValueError/FileNotFoundError extraction failure (WR-03).
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    write_testplan(text, args.output)
    print(f"wrote {args.output}")
    return 0


def _run_all_mode(output_dir: Path) -> int:
    """Manifest-driven multi-flow generation: one file per FLOW_MANIFEST row, per-row fail-closed.

    Each row's extract/render/write sequence is wrapped in its own try/except so one bad row
    (e.g. a future command-file edit that breaks frontmatter parsing) cannot silently suppress
    or abort another row's correctly-generated output. Flow 7's row (the one carrying a
    'hand_built_ir' key, per Decision 3) skips extract() entirely and calls render() directly on
    the pre-built IR dict.
    """
    failed_slugs: list[str] = []
    for row in FLOW_MANIFEST:
        slug = row["slug"]
        try:
            hand_built_ir = row.get("hand_built_ir")
            if hand_built_ir:
                ir = hand_built_ir
            else:
                ir = extract(
                    row["command_file"],
                    risk_tier=row["risk_tier"],
                    requirement_id_override=row.get("requirement_id_override"),
                    flow_slug_override=row.get("flow_slug_override"),
                    signal_table=_signals.SIGNAL_TABLE_BY_SLUG.get(row["slug"]),
                )
            text = render(ir)
            write_testplan(text, output_dir / f"{slug}.md")
        except Exception as exc:  # noqa: BLE001  per-row fail-closed: never abort the whole batch
            # Include type(exc).__name__ so an unexpected TypeError/AttributeError (likely a
            # real bug in a future manifest/extractor edit) is visually distinguishable in
            # CI/stderr output from an expected, documented ValueError/FileNotFoundError
            # extraction failure (WR-03). The "FAIL: {slug}:" prefix is preserved verbatim
            # for existing stderr-matching test/tooling contracts.
            print(f"FAIL: {slug}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failed_slugs.append(slug)
            continue

    if failed_slugs:
        print(
            f"FAIL: {len(failed_slugs)}/{len(FLOW_MANIFEST)} flows failed: {failed_slugs}",
            file=sys.stderr,
        )
        return 1

    print(f"wrote {len(FLOW_MANIFEST)} test plans to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
