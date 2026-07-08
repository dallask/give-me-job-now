#!/usr/bin/env python3
"""EXPERIMENTAL / UNSUPPORTED FOR AUTONOMOUS RUNS UNTIL PARITY IS VERIFIED.

This module is experimental/unsupported for autonomous runs until parity is verified
against the working Claude Code CLI path — see scripts/runtime/HOOK-PARITY.md for the
PreToolUse/SubagentStop parity status this label depends on.

Dispatches ONE spoke through claude-agent-sdk's query(), which itself spawns the same
`claude` CLI binary as a fresh subprocess per call. This is an alternate Python-orchestrated
harness around the existing CLI, never an independent inference engine — the CLI remains a
hard prerequisite (SDK-01/RESEARCH.md Pitfall 1). The returned envelope is re-validated
through the existing, unmodified scripts/contracts/gmj_validate_envelope.py before being
treated as trustworthy (SDK-02, RESEARCH.md Pattern 3).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/runtime/ -> repo root

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from gmj_validate_envelope import resolve_kind, validate as validate_against_kind_schema  # noqa: E402

# claude-agent-sdk is an OPTIONAL, isolated dependency (scripts/runtime/requirements.txt
# only) — guard the import so nothing under scripts/contracts or the default CLI path ever
# needs it installed (mirrors gmj_render_cv.py's WeasyPrint ImportError-guard convention).
# ResultMessage is imported alongside the others so the structured_output-carrying message
# can be identified with a real isinstance() check rather than string-matching the class
# name (a subclass, a differently-namespaced ResultMessage, or an SDK refactor would
# silently stop matching a type(message).__name__ comparison).
try:
    from claude_agent_sdk import query, ClaudeAgentOptions, HookMatcher, ResultMessage
except ImportError:
    query = None
    ClaudeAgentOptions = None
    HookMatcher = None
    ResultMessage = None

# Flat (no $ref/$defs) JSON-schema hint passed to output_format — a generation-time
# constraint only (RESEARCH.md Pitfall 2). kind/schema_version are included so a
# schema-conformant structured_output can also pass the real, kind-dispatched
# validate_envelope() check below; without them every response would be correctly
# rejected by the same trust boundary the SubagentStop hook enforces in production.
SPOKE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "schema": {"type": "string", "const": "agent_result_v1"},
        "kind": {
            "type": "string",
            "enum": ["offer_spec", "artifact_draft", "gate_result"],
        },
        "schema_version": {"type": "string", "const": "1.0"},
        "agent": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["success", "fail", "gap_report_ready", "handoff"],
        },
        "artifacts": {"type": "array", "items": {"type": "object"}},
        "notes": {"type": "string"},
    },
    "required": ["schema", "kind", "schema_version", "agent", "status", "notes"],
}


def _project_layout_root(repo_root: Path) -> tuple[Path, Path]:
    """Return (agents_dir, hooks_dir), supporting both the source tree (.claude/*)
    and the flat gmj-core/ payload layout (agents/, hooks/).

    This module ships in two locations: the source tree, where spoke definitions
    and hooks live under `.claude/agents` / `.claude/hooks`, and the standalone
    `gmj-core/` install payload (see `gmj-core/gmj-file-manifest.json`), whose
    layout is flat (`gmj-core/agents/`, `gmj-core/hooks/`, no `.claude/` prefix).
    Detecting the layout at call time keeps a single source file correct in both
    trees without needing per-tree forks.
    """
    if (repo_root / ".claude" / "agents").is_dir():
        return repo_root / ".claude" / "agents", repo_root / ".claude" / "hooks"
    return repo_root / "agents", repo_root / "hooks"


def load_spoke_system_prompt(spoke: str) -> str:
    """Read `<agents_dir>/<spoke>.md`'s body (frontmatter stripped) as the system prompt."""
    agents_dir, _ = _project_layout_root(REPO_ROOT)
    path = agents_dir / f"{spoke}.md"
    if not path.is_file():
        raise FileNotFoundError(f"No spoke definition for {spoke!r} at {path}")
    text = path.read_text(encoding="utf-8")
    # The file begins with a "---"-delimited YAML frontmatter block; splitting on "---"
    # with maxsplit=2 and taking the third element yields the remaining markdown body.
    parts = text.split("---", 2)
    body = parts[2] if len(parts) == 3 else text
    return body.strip()


def validate_envelope(structured_output: dict) -> list[str]:
    """Re-validate structured_output through the UNMODIFIED deterministic validator.

    output_format is a generation-time constraint, not proof (RESEARCH.md Pitfall 2 /
    Pattern 3) — this call is the actual trust boundary, identical to the dispatch
    .claude/hooks/gmj-validate-envelope.sh / gmj_validate_envelope.py --stdin exercise
    in production. Never a parallel, more-permissive check invented for this prototype.
    """
    try:
        kind = resolve_kind(None, structured_output)
    except ValueError as exc:
        return [str(exc)]
    return validate_against_kind_schema(structured_output, kind, REPO_ROOT / "schemas")


def _hook_deny_reason(proc: subprocess.CompletedProcess) -> str:
    """Extract the human-readable "reason" from a hook's stdout JSON blob.

    The underlying .sh scripts print a JSON object ({"decision":"block","reason":"..."})
    to stdout and a separate human-readable line to stderr. Prefer the parsed "reason"
    field; fall back to raw stdout/stderr only if the stdout cannot be parsed as the
    expected shape.
    """
    reason = proc.stdout or proc.stderr
    try:
        parsed = json.loads(proc.stdout)
        if isinstance(parsed, dict) and "reason" in parsed:
            reason = parsed["reason"]
    except (json.JSONDecodeError, TypeError):
        pass
    return reason


async def pretooluse_scope_guard(
    input_data, tool_use_id, context, *, project_dir: Path = REPO_ROOT
) -> dict:
    """Shell out to the UNMODIFIED gmj-sources-scope-guard.sh (RESEARCH.md Pattern 2).

    The keyword-only `project_dir` default preserves real production behavior — an
    SDK-registered HookMatcher always calls this with exactly 3 positional args — while
    letting tests inject an isolated tempdir, mirroring tests/test_sources_scope_guard.py's
    isolation convention so no test invocation writes into the real repo's own
    .claude/logs/sources-scope.log.
    """
    payload = {
        "tool_name": input_data.get("tool_name", ""),
        "tool_input": input_data.get("tool_input", {}),
    }
    _, hooks_dir = _project_layout_root(REPO_ROOT)
    hook_path = hooks_dir / "gmj-sources-scope-guard.sh"
    proc = subprocess.run(
        [str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)},
    )
    if proc.returncode == 2:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": _hook_deny_reason(proc),
            }
        }
    return {}


async def subagentstop_envelope_guard(input_data, tool_use_id, context) -> dict:
    """Shell out to the UNMODIFIED gmj-validate-envelope.sh (RESEARCH.md Pattern 2).

    Field names are identical on both sides per RESEARCH.md's live-confirmed mapping —
    no translation needed for transcript_path/agent_id.
    """
    payload = {
        "transcript_path": input_data.get("transcript_path", ""),
        "agent_id": input_data.get("agent_id", ""),
    }
    _, hooks_dir = _project_layout_root(REPO_ROOT)
    hook_path = hooks_dir / "gmj-validate-envelope.sh"
    proc = subprocess.run(
        [str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    if proc.returncode == 2:
        return {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "permissionDecision": "deny",
                "permissionDecisionReason": _hook_deny_reason(proc),
            }
        }
    return {}


async def run_spoke(spoke: str, bounded_input: str) -> dict:
    """Dispatch ONE spoke through claude_agent_sdk.query() and return a validated envelope.

    Never returns structured_output without first passing it through validate_envelope() —
    the deterministic re-check remains the real trust boundary (RESEARCH.md Pattern 3).
    """
    if query is None or ClaudeAgentOptions is None or HookMatcher is None:
        raise RuntimeError(
            "claude-agent-sdk is not installed. Run: pip install -r scripts/runtime/requirements.txt"
        )

    options = ClaudeAgentOptions(
        max_turns=1,
        permission_mode="default",
        system_prompt=load_spoke_system_prompt(spoke),
        output_format={"type": "json_schema", "schema": SPOKE_OUTPUT_SCHEMA},
        hooks={
            "PreToolUse": [HookMatcher(matcher=None, hooks=[pretooluse_scope_guard])],
            "SubagentStop": [HookMatcher(matcher=None, hooks=[subagentstop_envelope_guard])],
        },
    )

    structured = None
    async for message in query(prompt=bounded_input, options=options):
        if ResultMessage is not None and isinstance(message, ResultMessage):
            structured = message.structured_output

    if structured is None:
        raise RuntimeError(f"{spoke}: no structured_output captured from the SDK run")

    errors = validate_envelope(structured)
    if errors:
        raise RuntimeError(f"{spoke}: envelope failed validation: {'; '.join(errors)}")

    return structured


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dispatch one spoke via claude-agent-sdk (EXPERIMENTAL)."
    )
    parser.add_argument("--spoke", required=True, help="Agent name, e.g. gmj-offer-scout.")
    parser.add_argument("--input", type=Path, required=True, help="Bounded JSON/text input file.")
    args = parser.parse_args()

    try:
        bounded_input = args.input.read_text(encoding="utf-8")
        result = asyncio.run(run_spoke(args.spoke, bounded_input))
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
