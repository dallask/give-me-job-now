#!/usr/bin/env python3
"""Validate an agent_result_v1 envelope against its per-kind JSON Schema.

Dispatches on the envelope's `kind` (or an explicit `--kind` override), loads the
matching `schemas/<kind>.schema.json`, and resolves the shared-base `$ref` through
a `referencing.Registry` populated only with local repo schema files (never the
deprecated `RefResolver`, never network retrieval). Errors are reported as
structured `<field/path>: <message>` lines on stderr (GUARD-01). A conforming
envelope exits 0; a malformed one exits 1. Consumed as a CLI/module by Plan 05's
SubagentStop hook via `--stdin`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# Constrained allowlist — resolving a schema path from anything outside this set
# is refused, so `--kind` can never traverse out of the schemas/ base dir.
KNOWN_KINDS = ("offer_spec", "artifact_draft", "gate_result")

# The bare agent_result_v1 handoff envelope every collective spoke emits as its
# final message — legitimately carries NO `kind` field at all (only the 3
# wrapper kinds above add a `kind` const on top of this shared base). Kept
# deliberately separate from KNOWN_KINDS/`--kind`'s argparse `choices=`: a bare
# envelope has no `kind` field to override, so `--kind agent_result_v1` stays
# unreachable via the CLI flag (see resolve_kind()) — only an absent or
# explicit-but-redundant `kind` field on the envelope itself resolves here, no
# new CLI-driven path-traversal surface is introduced. Closes the previously
# PRE-EXISTING, DEFERRED decision D-01 (see 04-RESEARCH.md and 04-UAT.md's
# gap-closure diagnosis for test 1 —
# .planning/workstreams/r8-1/phases/04-contract-schema-reliability/04-07-PLAN.md):
# a genuinely valid, schema-conforming agent_result_v1 handoff envelope was
# logging a spurious `BLOCK: unknown kind None/'agent_result_v1'` because this
# 4th resolvable kind was never dispatched to its own already-existing
# schemas/agent_result_v1.schema.json file.
BARE_ENVELOPE_KIND = "agent_result_v1"

# Fixed base dir: the repo's schemas/ directory (this file lives at
# scripts/contracts/gmj_validate_envelope.py, so repo root is two parents up).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"

# JSON's own legal single-character escapes (RFC 8259 sec. 7) — anything else
# following a backslash inside a JSON string literal is a syntax error.
_LEGAL_JSON_ESCAPES = frozenset('"\\/bfnrtu')


def _repair_common_escape_errors(raw: str) -> str:
    """Escape bare backslashes inside JSON string literals so one common,
    recoverable authoring mistake does not hard-fail json.loads() before schema
    validation ever runs (04-05 gap closure; see
    .planning/workstreams/r8-1/phases/04-contract-schema-reliability/04-05-PLAN.md
    and the ~8 recurring `BLOCK: Invalid JSON: Invalid \\escape: line 6 column
    174` occurrences recorded in .claude/logs/validate-envelope.log from a single
    gmj-artifact-composer dispatch retried repeatedly).

    NARROWLY SCOPED: this targets exactly one failure class — a bare `\\` inside
    a JSON string value that is NOT followed by one of JSON's legal escape
    characters (`"`, `\\`, `/`, `b`, `f`, `n`, `r`, `t`, `u`). It doubles that
    bare backslash to `\\\\` so it parses as a literal backslash character,
    mirroring the real-world cause: a free-text field (e.g. `notes`) containing
    a Windows path, regex fragment, or LaTeX-style escape that the emitting
    agent did not double-escape for JSON.

    Every OTHER JSON syntax error class (unbalanced braces, unterminated
    strings, trailing commas, etc.) is left completely untouched by this
    function — those must continue to raise json.JSONDecodeError exactly as
    before this change, via the unmodified `raw` string reaching json.loads()
    unrepaired when this repair does not apply. Do not expand this function's
    scope without updating this comment and the plan it cites.
    """
    out: list[str] = []
    in_string = False
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue
        # Inside a string literal.
        if ch == "\\":
            nxt = raw[i + 1] if i + 1 < n else ""
            if nxt in _LEGAL_JSON_ESCAPES:
                # Already a legal escape sequence — copy both chars verbatim.
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            # Bare backslash not followed by a legal escape char — double it.
            out.append("\\\\")
            i += 1
            continue
        if ch == '"':
            in_string = False
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def build_registry(schema_dir: Path) -> Registry:
    """Build a Registry from every local schemas/*.schema.json, keyed on its $id.

    Local files only — no network/remote retrieval is enabled, so cross-file
    `$ref` (into the shared agent_result_v1 base) resolves without SSRF risk.
    """
    resources = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def resolve_kind(explicit_kind: str | None, envelope: dict) -> str:
    """Return the validated kind to dispatch on, or raise ValueError.

    An explicit `--kind` wins and MUST be one of the constrained KNOWN_KINDS
    allowlist (unchanged behavior — `--kind` can never resolve to
    BARE_ENVELOPE_KIND, since a bare envelope has no `kind` field to override).

    Otherwise, the envelope's own `kind` field is used: if it is absent
    (`None`) or exactly `"agent_result_v1"` (a redundant-but-valid self-label
    some emitters add), this resolves to BARE_ENVELOPE_KIND, validated
    directly against schemas/agent_result_v1.schema.json. Any other value
    must still be one of the 3 wrapper KNOWN_KINDS, or this raises ValueError
    exactly as before — this branch is strictly additive, never a replacement
    for the existing wrapper-kind dispatch.
    """
    if explicit_kind is not None:
        if explicit_kind not in KNOWN_KINDS:
            raise ValueError(
                f"unknown kind {explicit_kind!r}; expected one of {', '.join(KNOWN_KINDS)}"
            )
        return explicit_kind

    kind = envelope.get("kind")
    if kind is None or kind == BARE_ENVELOPE_KIND:
        return BARE_ENVELOPE_KIND
    if kind not in KNOWN_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; expected one of {', '.join(KNOWN_KINDS)}"
        )
    return kind


def validate(envelope: dict, kind: str, schema_dir: Path) -> list[str]:
    """Validate `envelope` against `schemas/<kind>.schema.json`.

    Returns a list of structured `<field/path>: <message>` error strings (empty
    when the envelope conforms). Uses Draft202012Validator with a Registry-backed
    cross-file `$ref` — never the deprecated RefResolver.
    """
    schema = json.loads((schema_dir / f"{kind}.schema.json").read_text(encoding="utf-8"))
    registry = build_registry(schema_dir)
    validator = Draft202012Validator(schema, registry=registry)
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(envelope), key=lambda e: list(e.path))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an agent_result_v1 envelope against its per-kind schema."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Envelope JSON file to validate.")
    source.add_argument(
        "--stdin", action="store_true", help="Read one envelope JSON from stdin."
    )
    parser.add_argument(
        "--kind",
        choices=KNOWN_KINDS,
        default=None,
        help="Override the envelope's own kind (constrained to the known set).",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="Directory of *.schema.json files (defaults to the repo schemas/ dir).",
    )
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    else:
        path = args.file.expanduser().resolve()
        if not path.is_file():
            print(f"Not a file: {path}", file=sys.stderr)
            return 1
        raw = path.read_text(encoding="utf-8")

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        # Bare-backslash escape errors are the single most common recoverable
        # failure class observed in practice (see _repair_common_escape_errors'
        # docstring) — retry once against a narrowly-repaired copy before
        # failing loud. Any other syntax error class re-raises unchanged.
        repaired = _repair_common_escape_errors(raw)
        try:
            envelope = json.loads(repaired)
        except json.JSONDecodeError as exc:
            # Report against whichever parse attempt is closer to the true
            # remaining problem: if the repair changed nothing, the original
            # error is exact; if it changed something but still failed, the
            # repaired-string error is closer to the true remaining problem.
            print(f"Invalid JSON: {exc}", file=sys.stderr)
            return 1
    if not isinstance(envelope, dict):
        print("Envelope must be a JSON object.", file=sys.stderr)
        return 1

    try:
        kind = resolve_kind(args.kind, envelope)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    schema_dir = args.schema_dir.expanduser().resolve()
    errors = validate(envelope, kind, schema_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(f"OK: {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
