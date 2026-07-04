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

# Fixed base dir: the repo's schemas/ directory (this file lives at
# scripts/contracts/gmj_validate_envelope.py, so repo root is two parents up).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"


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

    An explicit `--kind` wins; otherwise the envelope's own `kind` field is used.
    The result must be in the constrained KNOWN_KINDS allowlist.
    """
    kind = explicit_kind if explicit_kind is not None else envelope.get("kind")
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
    except json.JSONDecodeError as exc:
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
