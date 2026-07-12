#!/usr/bin/env python3
"""Single-fix, explicit-consent applier for self-reflect-report.md findings (D-07).

This script is deliberately separate from ``scripts/gmj_self_reflect.py`` (the
report-only analyzer): the analyzer classifies and proposes fixes but never applies
one; this script applies exactly ONE named fix per invocation, and never generates
the report itself. This hard separation is D-07's non-bypassable guarantee — a fix
is only ever applied on an explicit, later, human-gated ``/gsd-self-reflect --apply``
follow-up, mirroring ``$HOME/.claude/gsd-core/workflows/code-review-fix.md``'s
``check_review_exists`` -> ``check_review_status`` -> apply shape exactly.

Threat-model note (T-06-05-01): ``--finding <pattern-id>`` must match one of this
script's own registered, pre-authored fix functions (``FIX_REGISTRY`` below) — it
never executes instructions parsed FROM the report's prose. The report is only used
to confirm the named finding was actually surfaced by the analyzer (a safety check,
not a source of executable instructions).

This script does NOT create a git commit itself (T-06-05-04): commit ownership stays
at the calling command layer (``.claude/commands/gsd-self-reflect.md``), which reads
this script's structured stdout JSON to decide what to stage and commit, exactly
once per applied fix.

CLI:
    python3 scripts/gmj_self_reflect_apply.py \\
        --report output/analysis/self-reflect-report.md \\
        --finding <pattern-id> \\
        [--repo-root <path>]

Exit codes:
    0 — either a fix was applied (``status: applied``) or was already present
        (``status: already_applied``); both print a structured one-line JSON result.
    1 — the report is missing, the finding id is unknown, the finding exists but has
        no mechanical apply available (prose-only, requires human judgment), or the
        fix function itself failed. Every non-zero exit prints a clear stderr
        message; this script never silently no-ops.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_REPORT = REPO_ROOT / "output" / "analysis" / "self-reflect-report.md"

# Matches render_report()'s exact heading shape in scripts/gmj_self_reflect.py:
#   "## {heading} (`{pattern_id}`)"
FINDING_HEADING_RE = re.compile(r"^##\s+.+\(`([^`]+)`\)\s*$", re.MULTILINE)

PYTHONDONTWRITEBYTECODE_MARKER = "PYTHONDONTWRITEBYTECODE=1"


# --------------------------------------------------------------------------- report parsing


def _parse_report_finding_ids(report_text: str) -> set[str]:
    """Return the set of pattern-ids this report actually names, via heading match.

    Reuses a simple heading-match parse (per the plan's own instruction: "reuse a
    simple heading-match parse, not a new Markdown AST dependency"), mirroring
    ``check_review_status``'s frontmatter-regex approach in
    ``code-review-fix.md`` adapted to this report's Markdown heading shape instead
    of YAML frontmatter.
    """
    return set(FINDING_HEADING_RE.findall(report_text))


# --------------------------------------------------------------------------- fix functions
#
# Each fix function is a scoped, single-purpose file-edit — never a generic
# patch-applier (per the plan's explicit instruction). A fix function returns a
# dict describing what changed on success, or raises ValueError with a message
# safe to print to stderr on failure. Idempotency (returning ``already_applied``
# instead of double-applying) is the fix function's own responsibility, checked
# before making any edit.


def _fix_pycache_hook_log_pollution(repo_root: Path) -> dict:
    """Add PYTHONDONTWRITEBYTECODE=1 to workflow.test_command in .planning/config.json.

    This is the mechanical half of scripts/gmj_self_reflect.py's own proposed fix
    text for this pattern ("...or run tests with PYTHONDONTWRITEBYTECODE=1..."):
    a config-toggle edit, not a prose recommendation. Idempotent: if the marker is
    already present in test_command, this is a no-op that reports already_applied.
    """
    config_path = repo_root / ".planning" / "config.json"
    if not config_path.is_file():
        raise ValueError(
            f"Cannot apply pycache-hook-log-pollution fix: {config_path} not found."
        )

    try:
        config_text = config_path.read_text(encoding="utf-8")
        config = json.loads(config_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot parse {config_path}: {exc}") from exc

    workflow = config.get("workflow")
    if not isinstance(workflow, dict) or "test_command" not in workflow:
        raise ValueError(
            f"Cannot apply pycache-hook-log-pollution fix: {config_path} has no "
            "workflow.test_command field to prepend the env var to."
        )

    test_command = workflow["test_command"]
    if not isinstance(test_command, str):
        raise ValueError(
            "Cannot apply pycache-hook-log-pollution fix: workflow.test_command is "
            "not a string."
        )

    if PYTHONDONTWRITEBYTECODE_MARKER in test_command:
        return {"already_applied": True, "files_changed": []}

    workflow["test_command"] = f"export {PYTHONDONTWRITEBYTECODE_MARKER}; {test_command}"
    new_text = json.dumps(config, indent=2) + "\n"
    config_path.write_text(new_text, encoding="utf-8")
    return {"already_applied": False, "files_changed": [str(config_path)]}


# Fix registry: pattern-id -> {mechanical: bool, fn: callable|None, refusal_reason}.
# A pattern-id absent from this registry, or present with mechanical=False, always
# refuses rather than fabricating an apply (per the plan's explicit instruction not
# to route around genuinely prose-only recommendations).
FIX_REGISTRY: dict[str, dict] = {
    "pycache-hook-log-pollution": {
        "mechanical": True,
        "fn": _fix_pycache_hook_log_pollution,
    },
    "worktree-base-drift": {
        "mechanical": False,
        "refusal_reason": (
            "This finding's proposed fix requires manual judgment; no mechanical "
            "apply is available."
        ),
    },
    "repeated-identical-error": {
        "mechanical": False,
        "refusal_reason": (
            "This finding's proposed fix requires manual judgment; no mechanical "
            "apply is available."
        ),
    },
}


# --------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply exactly ONE named finding's mechanical fix from a prior "
            "self-reflect-report.md. Never auto-generates the report; never "
            "batch-applies; never commits (the calling command layer commits)."
        )
    )
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT,
        help="Path to the prior self-reflect-report.md (must already exist).",
    )
    parser.add_argument(
        "--finding", required=True,
        help="The pattern-id of the single finding to apply (must appear in --report).",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="Repo root to resolve fix-target files against (default: this script's "
        "own repo root; override for isolated/test invocations).",
    )
    args = parser.parse_args(argv)

    if not args.report.is_file():
        print(
            f"FAIL: no report found at {args.report}. Run /gsd-self-reflect first "
            "to generate it — this script never auto-generates the report.",
            file=sys.stderr,
        )
        return 1

    report_text = args.report.read_text(encoding="utf-8")
    finding_ids_in_report = _parse_report_finding_ids(report_text)

    if args.finding not in finding_ids_in_report:
        print(
            f"FAIL: finding '{args.finding}' not found in report {args.report}. "
            f"Findings present in this report: {sorted(finding_ids_in_report) or '(none)'}.",
            file=sys.stderr,
        )
        return 1

    registry_entry = FIX_REGISTRY.get(args.finding)
    if registry_entry is None or not registry_entry.get("mechanical"):
        reason = (
            registry_entry.get("refusal_reason")
            if registry_entry
            else "This finding's proposed fix requires manual judgment; no mechanical "
            "apply is available."
        )
        print(f"FAIL: {reason}", file=sys.stderr)
        return 1

    try:
        result = registry_entry["fn"](args.repo_root)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if result.get("already_applied"):
        print(
            json.dumps(
                {
                    "status": "already_applied",
                    "finding": args.finding,
                    "files_changed": [],
                }
            )
        )
        return 0

    print(
        json.dumps(
            {
                "status": "applied",
                "finding": args.finding,
                "files_changed": result.get("files_changed", []),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
