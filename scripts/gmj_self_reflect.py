#!/usr/bin/env python3
"""Read-only, report-ONLY execution-log findings analyzer (REFLECT-03/REFLECT-04).

This tool reads every ``*.jsonl`` file under ``.planning/execution-logs/`` — both the
``source: "tool-call"`` stream (``tool-calls-<date>.jsonl``, Plan 02) and the
``source: "gsd-workflow"`` stream (``gsd-workflow-<date>.jsonl``, Plan 03), tolerating
either glob matching zero files — plus ``SubagentStop``-sourced transcript excerpts, and
classifies the combined, chronologically-sorted event stream into named recurring
behavioral-pattern findings, each with a proposed concrete fix. It is NOT a raw log dump:
``render_report`` renders one Markdown section per named pattern (pattern name, occurrence
count, proposed fix, bounded evidence references), never a flat per-tool-call count table.

There is NO fix-application code path in this file at all (D-07): a fix is only applied
by a separate ``/gsd-self-reflect --apply`` follow-up flow, never by this script. The
safety guarantee is the ABSENCE of any mutation code path outside ``write_report()``
(mirroring ``scripts/gmj_cleanup_report.py``'s existing precedent), not a flag or
environment toggle. Passing ``--apply`` directly to this script always fails loudly
(belt-and-braces D-07 boundary enforcement) rather than silently doing nothing.

CLI (mirrors ``scripts/gmj_cleanup_report.py``): ``python3 scripts/gmj_self_reflect.py
[--log-dir .planning/execution-logs] [--output output/analysis/self-reflect-report.md]``;
writes the Markdown report and prints its path. A malformed/partial JSONL line (from a
crashed writer, or a truncated concurrent-write) is skipped, never crashes the analyzer —
this is the analyzer's own fail-open posture (T-06-04-01), distinct from
``gmj_cleanup_report.py``'s fail-closed manifest-loading posture, since a missing log
directory here just means "nothing observed yet," not a misconfiguration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_LOG_DIR = REPO_ROOT / ".planning" / "execution-logs"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "analysis" / "self-reflect-report.md"

BAR = "=" * 74

# Bounded evidence list per finding — keeps the report readable even when a pattern
# recurs dozens of times (RESEARCH.md Pitfall 3: avoid the raw-log-dump failure mode).
MAX_EVIDENCE_PER_FINDING = 8

# Minimum occurrence count required for the generic fallback signature to fire, so it
# does not over-eagerly compete with the two named patterns on borderline data.
GENERIC_PATTERN_MIN_OCCURRENCES = 3


# --------------------------------------------------------------------------- transcript reading

def _read_final_assistant_message(transcript_path: Path) -> str:
    """Extract the CURRENT subagent's FINAL assistant message text from a transcript.

    Extends ``.claude/hooks/gmj-validate-envelope.sh``'s final-assistant-message
    extraction technique (lines 63-104) into a reusable Python helper, per
    RESEARCH.md's Don't-Hand-Roll guidance (reuse, do not write a second independent
    transcript parser). Wrapped in a broad ``try/except`` — any read/parse failure
    (missing file, permission error, malformed JSONL) returns an empty string rather
    than raising, since a transcript is optional context, never required (T-06-04-01/02
    defensive parsing: never crash on adversarial or absent input).
    """
    try:
        if not transcript_path or not Path(transcript_path).is_file():
            return ""
        messages: list[str] = []
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", obj) if isinstance(obj, dict) else {}
                if isinstance(msg, dict) and msg.get("role") not in (None, "assistant"):
                    continue
                content = msg.get("content") if isinstance(msg, dict) else None
                if content is None and isinstance(obj, dict):
                    content = obj.get("content")
                parts: list[str] = []
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
                if parts:
                    messages.append("\n".join(parts))
        return messages[-1] if messages else ""
    except Exception:  # noqa: BLE001  defensive: a transcript read never crashes the analyzer
        return ""


# --------------------------------------------------------------------------- log loading

def _load_entries(log_dir: Path) -> tuple[list[dict], int]:
    """Read every ``tool-calls-*.jsonl`` and ``gsd-workflow-*.jsonl`` file under log_dir.

    Returns (entries, skipped_malformed_lines). Entries are sorted by ``ts`` across
    both source streams (Plan 03's correlatable-stream proof). Either glob matching
    zero files is tolerated — returns an empty list, not an error (this plan does not
    assume Plan 03's gsd-workflow dispatch point is wired; T-06-03-04 / T-06-04-01).
    Each SubagentStop-sourced entry (one carrying a ``transcript_path`` but no inline
    content) is enriched in-place with a ``_transcript_excerpt`` field for pattern
    matching, via ``_read_final_assistant_message`` — a best-effort addition that never
    raises.
    """
    entries: list[dict] = []
    skipped_malformed_lines = 0

    if not log_dir.is_dir():
        return entries, skipped_malformed_lines

    files = sorted(log_dir.glob("tool-calls-*.jsonl")) + sorted(log_dir.glob("gsd-workflow-*.jsonl"))
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                skipped_malformed_lines += 1
                continue
            if not isinstance(entry, dict):
                skipped_malformed_lines += 1
                continue
            transcript_path = entry.get("transcript_path")
            if transcript_path:
                entry["_transcript_excerpt"] = _read_final_assistant_message(Path(transcript_path))
            entries.append(entry)

    entries.sort(key=lambda e: str(e.get("ts", "")))
    return entries, skipped_malformed_lines


def _searchable_text(entry: dict) -> str:
    """Concatenate every text-shaped field on an entry that a signature might match against."""
    parts: list[str] = []
    for key in ("command", "event", "tool_name", "outcome", "point", "_transcript_excerpt"):
        value = entry.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


# --------------------------------------------------------------------------- pattern signatures

def _sig_worktree_base_drift(entry: dict) -> bool:
    """Worktree base-drift shaped signature: diverged/non-fast-forward/merge-conflict text."""
    text = _searchable_text(entry).lower()
    needles = (
        "base has diverged",
        "non-fast-forward",
        "merge conflict",
        "conflicting files",
        "cannot fast-forward",
        "worktree base",
    )
    return any(n in text for n in needles)


def _sig_pycache_hook_log_pollution(entry: dict) -> bool:
    """pycache/hook-log self-inflicted test-gate-failure shaped signature."""
    text = _searchable_text(entry).lower()
    needles = (
        "__pycache__",
        "hook-log",
        "validate-envelope.log",
        "blocked-commands.log",
    )
    return any(n in text for n in needles)


def _sig_repeated_identical_error(entries: list[dict]) -> list[dict]:
    """Generic fallback: 3+ entries sharing a near-identical error-shaped field value.

    Not a per-entry predicate like the two named signatures — this groups entries by a
    normalized error-shaped field (command) and returns the group's members if it
    recurs >= GENERIC_PATTERN_MIN_OCCURRENCES times and looks error-shaped (contains
    "error"/"fail"/"exception"), so the analyzer is extensible to future patterns
    without a new hardcoded predicate for every case.
    """
    buckets: dict[str, list[dict]] = {}
    for entry in entries:
        text = _searchable_text(entry).lower()
        if not any(marker in text for marker in ("error", "fail", "exception", "traceback")):
            continue
        command = entry.get("command")
        key = str(command).strip() if isinstance(command, str) and command else None
        if not key:
            continue
        buckets.setdefault(key, []).append(entry)
    for members in buckets.values():
        if len(members) >= GENERIC_PATTERN_MIN_OCCURRENCES:
            return members
    return []


# Pattern-signature registry: a list of dicts, NOT a giant if/elif chain, so adding a
# new pattern is a new registry entry, never a new branch in classify()'s control flow.
PATTERN_REGISTRY = [
    {
        "pattern_id": "worktree-base-drift",
        "heading": "Worktree base drift",
        "description": (
            "A concurrent sibling-workstream commit landed mid-dispatch, causing the "
            "worktree's base to diverge from its expected parent (non-fast-forward / "
            "merge-conflict-shaped signals)."
        ),
        "min_occurrences": 3,
        "signature_predicate": _sig_worktree_base_drift,
        "proposed_fix": (
            "Before dispatching a wave of parallel worktree agents, snapshot and pin the "
            "expected base commit SHA per agent, and have each agent assert its actual "
            "base against the pinned SHA before its first commit (fail fast with a clear "
            "diagnostic instead of a raw git error). Consider serializing merges back to "
            "the integration branch through a single rebase-and-retry step rather than "
            "relying on each worktree agent to detect drift independently."
        ),
    },
    {
        "pattern_id": "pycache-hook-log-pollution",
        "heading": "pycache / hook-log self-inflicted test-gate pollution",
        "description": (
            "The test gate itself creates __pycache__ artifacts, or a concurrently-"
            "running hook mutates a hook-log file mid-test-run, and the resulting "
            "filesystem noise is then mis-diagnosed as a genuine test failure, requiring "
            "manual root-causing from raw command output."
        ),
        "min_occurrences": 2,
        "signature_predicate": _sig_pycache_hook_log_pollution,
        "proposed_fix": (
            "Add __pycache__ and .claude/logs/*.log to the test runner's ignored-paths "
            "list (or run tests with PYTHONDONTWRITEBYTECODE=1) so gate output never "
            "conflates self-inflicted filesystem noise with a genuine assertion failure; "
            "additionally, have the test harness diff only the files each test itself "
            "wrote, not the whole working tree, to avoid concurrent-hook-log mutations "
            "being misattributed to the test under gate."
        ),
    },
]


def _evidence_line(entry: dict) -> str:
    ts = entry.get("ts", "?")
    tool = entry.get("tool_name") or entry.get("point") or entry.get("event") or "?"
    detail = entry.get("command") or entry.get("_transcript_excerpt") or entry.get("outcome") or ""
    detail = detail.strip().splitlines()[0][:160] if isinstance(detail, str) and detail else ""
    return f"{ts} [{tool}] {detail}".strip()


def _repeated_identical_error_finding(entries: list[dict]) -> dict | None:
    members = _sig_repeated_identical_error(entries)
    if not members:
        return None
    sample_command = members[0].get("command", "")
    return {
        "pattern": "repeated-identical-error",
        "heading": "Repeated identical error",
        "occurrences": len(members),
        "proposed_fix": (
            f"The same error-shaped command recurred {len(members)} times "
            f"({sample_command!r} truncated for display). Investigate whether this "
            "command should be retried with backoff, guarded by a precondition check, "
            "or replaced with a more robust equivalent."
        ),
        "evidence": [_evidence_line(e) for e in members[:MAX_EVIDENCE_PER_FINDING]],
    }


# --------------------------------------------------------------------------- classification

def _classify_entries(entries: list[dict]) -> list[dict]:
    """Shared classification core, operating on an already-loaded entry list.

    Used by both ``classify()`` (disk-driven) and direct-import unit tests (in-memory
    fixture lists), per PATTERNS.md's recommended test shape for this file.
    """
    findings: list[dict] = []

    for pattern in PATTERN_REGISTRY:
        matches = [e for e in entries if pattern["signature_predicate"](e)]
        if len(matches) >= pattern["min_occurrences"]:
            findings.append(
                {
                    "pattern": pattern["pattern_id"],
                    "heading": pattern["heading"],
                    "occurrences": len(matches),
                    "proposed_fix": pattern["proposed_fix"],
                    "evidence": [_evidence_line(e) for e in matches[:MAX_EVIDENCE_PER_FINDING]],
                }
            )

    named_pattern_ids = {p["pattern_id"] for p in PATTERN_REGISTRY}
    already_matched_ids = {
        id(e) for pat in PATTERN_REGISTRY for e in entries if pat["signature_predicate"](e)
    }
    remaining_entries = [e for e in entries if id(e) not in already_matched_ids]
    generic = _repeated_identical_error_finding(remaining_entries)
    if generic and generic["pattern"] not in named_pattern_ids:
        findings.append(generic)

    return findings


def classify(log_dir: Path) -> list[dict]:
    """Read execution logs under ``log_dir`` and return named recurring-pattern findings.

    Returns a list of finding dicts, each with at least ``pattern``, ``heading``,
    ``occurrences``, ``proposed_fix``, and ``evidence`` (a bounded list of evidence
    line-references). Tolerates either JSONL glob matching zero files (returns an
    empty findings list, not an error) and skips any line that fails ``json.loads``
    (tracked internally via a skipped-line counter, never raised).

    A "normal run" — a handful of unrelated tool calls with no repeated error-shaped
    content — returns an empty or near-empty findings list; the analyzer does not
    over-fire false positives on ordinary activity.
    """
    entries, _skipped = _load_entries(log_dir)
    return _classify_entries(entries)


def classify_from_entries(entries: list[dict]) -> list[dict]:
    """Same classification logic as ``classify()``, but against an in-memory entry list.

    Exposed for direct unit testing of the pattern-signature registry without needing
    to write fixture files to disk first (PATTERNS.md's recommended shape for this
    test file: call ``classify()``/``render_report()`` as direct Python function
    imports rather than via subprocess).
    """
    return _classify_entries(entries)


# --------------------------------------------------------------------------- rendering

def render_report(findings: list[dict]) -> str:
    """Build the Markdown self-reflection findings report as a single string.

    Renders one Markdown section per named pattern finding (pattern name, occurrence
    count, proposed fix, bounded evidence list) — NOT a flat per-tool-call count
    table (RESEARCH.md Pitfall 3's "raw log dump" anti-pattern). Always ends with the
    D-06/D-07 STATUS/ACTION/SAFETY footer.
    """
    lines: list[str] = []
    lines.append("# GSD Self-Reflection Findings Report")
    lines.append("")
    lines.append(
        "This report analyzes structured execution logs (`.planning/execution-logs/"
        "*.jsonl`) and names recurring behavioral patterns with a proposed concrete "
        "fix for each — not a raw count of tool calls."
    )
    lines.append("")

    if not findings:
        lines.append("## No recurring patterns found")
        lines.append("")
        lines.append(
            "No named recurring-pattern findings were detected in the analyzed logs."
        )
        lines.append("")
    else:
        for finding in findings:
            lines.append(f"## {finding['heading']} (`{finding['pattern']}`)")
            lines.append("")
            lines.append(f"**Occurrences:** {finding['occurrences']}")
            lines.append("")
            lines.append(f"**Proposed fix:** {finding['proposed_fix']}")
            lines.append("")
            if finding.get("evidence"):
                lines.append("**Evidence:**")
                lines.append("")
                for ref in finding["evidence"]:
                    lines.append(f"- {ref}")
                lines.append("")

    lines.append(BAR)
    lines.append("STATUS: findings only — no fix was applied.")
    lines.append(
        "ACTION: run `/gsd-self-reflect --apply` to apply one proposed fix, atomically "
        "committed. This is a separate, later, human-gated step."
    )
    lines.append("SAFETY: this tool has no fix-application code path at all (D-07).")
    lines.append(BAR)

    return "\n".join(lines) + "\n"


def write_report(text: str, output_path: Path) -> None:
    """The single filesystem-write call in this module — overwrite output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report-only execution-log findings analyzer (no fix-application branch "
            "exists in this script)."
        )
    )
    parser.add_argument(
        "--log-dir", type=Path, default=DEFAULT_LOG_DIR,
        help="Directory containing tool-calls-*.jsonl / gsd-workflow-*.jsonl "
        "(default: .planning/execution-logs/).",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Markdown report output path (overwritten each run).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Not implemented here — fails loudly (D-07 boundary). Use the "
        "/gsd-self-reflect --apply follow-up flow instead.",
    )
    args = parser.parse_args(argv)

    if args.apply:
        print(
            "FAIL: --apply is not implemented in the report generator; use the "
            "/gsd-self-reflect --apply follow-up flow.",
            file=sys.stderr,
        )
        return 1

    findings = classify(args.log_dir)
    text = render_report(findings)
    write_report(text, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
