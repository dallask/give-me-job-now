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

# A single documented flag line looks like: "- **`--repo-root <path>`** — testability-only. ..."
# or "- `--foo`: some purpose." Capture the flag token and the rest of the line as purpose.
_FLAG_LINE_RE = re.compile(
    r"^-\s*\*{0,2}`(?P<flag>--[\w-]+(?:\s+<[\w-]+>)?)`\*{0,2}\s*[—:-]\s*(?P<purpose>.+)$"
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
    """Scan body for '## Usage'/'## Flags'-style sections and pull documented flag lines."""
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
        flag_match = _FLAG_LINE_RE.match(line.strip())
        if flag_match:
            flags.append(
                {
                    "name": flag_match.group("flag").split()[0],
                    "purpose": flag_match.group("purpose").strip(),
                }
            )
    return flags


def _extract_behaviors(body: str) -> list[str]:
    """Scan body for real, concrete described behaviors/steps (Claude's Discretion heuristic).

    Pulls numbered-list items from an "## Interaction flow"/"## What to do"-style section,
    plus any fenced ```bash code block lines found anywhere in the body — these are the
    concrete, real commands/interaction-sequence facts render() needs. Never returns a
    placeholder; an empty list means the caller must decide if that is acceptable (extract()
    only raises for the mandatory requirement_id, not for behaviors, since behaviors are
    Claude's Discretion per 02-CONTEXT.md).
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
            behaviors.append(stripped)
            continue
        numbered_match = re.match(r"^\d+\.\s+\*{0,2}(.+)$", stripped)
        if numbered_match:
            behaviors.append(numbered_match.group(1).strip())
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
    """True if the body explicitly states no confirm-bypass flag exists (cleanup-wizard-style)."""
    lowered = body.lower()
    return "no bypass flag" in lowered or (
        "no" in lowered and "bypass" in lowered and "flag" in lowered
    )


def extract(command_file: Path) -> dict:
    """Parse ``command_file`` (a ``.claude/commands/*.md`` file) into an in-memory dict IR.

    Reads the frontmatter (``---``-fenced, YAML) and body, pulling out: ``flow_name``/
    ``slug`` (derived from the filename), the frontmatter ``description``, a ``flags`` list
    (name + purpose, scanned from Usage/Flags-style sections), a ``behaviors`` list (real
    commands/interaction steps scanned from body prose/code blocks), a ``requirement_id``
    (mandatory — raises if absent), and a ``no_bypass_flag`` boolean fact when the body
    states one explicitly. Returns a plain dict (D-02's YAML-shaped IR) — never writes
    anything to disk (D-03: in-memory only).

    Raises ``FileNotFoundError`` if ``command_file`` does not exist; raises ``ValueError``
    if the frontmatter fence is missing/malformed, the fenced block does not parse to a
    YAML mapping, or no requirement-ID token is found anywhere in the file.
    """
    if not command_file.is_file():
        raise FileNotFoundError(f"command file not found: {command_file}")

    text = command_file.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, command_file)

    slug = command_file.stem
    description = str(frontmatter.get("description") or "")
    flags = _extract_flags(body)
    behaviors = _extract_behaviors(body)
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
    }
    if no_bypass_flag:
        ir["no_bypass_flag"] = True
    return ir


# --------------------------------------------------------------------------- CLI (Task 2)

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
