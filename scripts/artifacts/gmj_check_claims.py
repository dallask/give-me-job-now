#!/usr/bin/env python3
"""Executed provenance gate for a composed artifact draft (COMPOSE-03).

Proves two things about a stored ``<type>.draft.json`` (a content-doc
``{schema_version, kind, content:{...}}``, NOT a full agent_result_v1 envelope):

1. ``draft["content"]`` conforms to ``artifact_draft.schema.json#/$defs/artifact_content``
   (the sub-schema ONLY — the file carries no ``status``/``schema`` envelope fields, so
   applying the full envelope schema is Pitfall 2 / threat T-04-11).
2. Every ``claim.source_span`` resolves into ``candidate.yaml`` via the shared, executed
   ``yaml_path.resolve_path`` walker — never an LLM self-report (threat T-04-10). A
   fabricated or out-of-range span surfaces as an unresolved span, reported + exit 1.

Malformed/oversized input is guarded (``is_file``/``json.JSONDecodeError``/``isinstance``)
into structured stderr + exit 1 with no traceback (threat T-04-12). The schema ``$ref``
into the shared base resolves through a local-only registry (threat T-04-13). This CLI
does NOT read the offer-spec; the language-equality check (COMPOSE-05) lives in the test.

CLI: ``gmj_check_claims.py --file <draft.json> --candidate <candidate.yaml> [--schema-dir DIR]``
exits 0 (``OK``) when the draft is well-formed and every span resolves, else 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/artifacts/ -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from gmj_validate_envelope import build_registry  # noqa: E402  reuse the local schema registry

sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from gmj_yaml_path import resolve_path  # noqa: E402  promoted shared source-span resolver

DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"
ARTIFACT_DRAFT_SCHEMA = "artifact_draft.schema.json"


def check(draft: dict, candidate: dict, schema_dir: Path) -> list[str]:
    """Validate a draft content-doc + resolve every claim span into *candidate*.

    Returns a list of structured error strings (empty when the draft is well-formed
    and every ``source_span`` resolves). Validates ``draft["content"]`` against the
    ``artifact_content`` sub-schema ONLY (never the full envelope), then walks each
    claim's ``source_span`` with the shared resolver — an unresolvable span is an
    error, proving provenance by execution rather than self-report.
    """
    schema = json.loads((schema_dir / ARTIFACT_DRAFT_SCHEMA).read_text(encoding="utf-8"))
    subschema = schema["$defs"]["artifact_content"]
    registry = build_registry(schema_dir)
    validator = Draft202012Validator(subschema, registry=registry)
    content = draft.get("content", {})
    errors = [
        f"schema: {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(content), key=lambda e: list(e.path))
    ]

    for i, claim in enumerate(content.get("claims", [])):
        span = claim.get("source_span", "") if isinstance(claim, dict) else ""
        try:
            resolve_path(candidate, span)
        except (KeyError, IndexError, TypeError) as exc:
            errors.append(f"claims[{i}].source_span {span!r} does not resolve: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a draft content-doc + resolve every claim source_span."
    )
    parser.add_argument(
        "--file", type=Path, required=True, help="Draft JSON content-doc to check."
    )
    parser.add_argument(
        "--candidate", type=Path, required=True, help="candidate.yaml the spans resolve into."
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="Directory of *.schema.json files (defaults to the repo schemas/ dir).",
    )
    args = parser.parse_args()

    draft_path = args.file.expanduser().resolve()
    if not draft_path.is_file():
        print(f"Not a file: {draft_path}", file=sys.stderr)
        return 1
    candidate_path = args.candidate.expanduser().resolve()
    if not candidate_path.is_file():
        print(f"Not a file: {candidate_path}", file=sys.stderr)
        return 1

    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(draft, dict):
        print("Draft must be a JSON object.", file=sys.stderr)
        return 1
    if "content" not in draft:
        print("Malformed draft: missing 'content'.", file=sys.stderr)
        return 1

    candidate = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        print("Candidate YAML must parse to a JSON object.", file=sys.stderr)
        return 1

    schema_dir = args.schema_dir.expanduser().resolve()
    errors = check(draft, candidate, schema_dir)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
