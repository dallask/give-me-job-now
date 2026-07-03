#!/usr/bin/env python3
"""Freeze a fielded offer draft into an immutable offer-spec.json (INTAKE-01, INTAKE-03).

Reads a fielded offer draft (a ``content`` object, or an object with a ``content``
key) from ``--file`` or ``--stdin``, validates it against
``schemas/offer_spec.schema.json#/$defs/offer_content``, computes
``offer_spec_hash = canonical_hash(content)`` by REUSING Phase 2's audited hasher,
and writes ``sources/offers/<slug>.offer-spec.json`` with ``content`` plus
``captured_at`` and ``offer_spec_hash`` as siblings OUTSIDE ``content``.

Design (RESEARCH Pattern 1/3, Pitfall 1): nesting the hashed fields in ``content``
while keeping ``captured_at`` a sibling excludes capture time from the fingerprint
BY CONSTRUCTION — so ``canonical_hash`` is reused unchanged and no ``VOLATILE_FIELDS``
edit is needed. The hash is produced only by this executed code, never agent-asserted
(T-03-hash). The ``<slug>`` is sanitized to ``[a-z0-9-]`` and the file is written only
under ``sources/offers/`` (T-03-path).

CLI: ``freeze_offer.py (--file <path> | --stdin) [--captured-at <iso8601>]`` exits 0
after printing the written path; validation/JSON/IO errors go to stderr, exit 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/offers/ -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from hash_artifact import canonical_hash  # noqa: E402  reuse the audited canonical form
from validate_envelope import build_registry  # noqa: E402  reuse the local schema registry

DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"
OFFER_SPEC_SCHEMA = "offer_spec.schema.json"
# cwd-relative so the freeze target is predictable from repo root and isolatable in tests.
OUTPUT_SUBDIR = Path("sources") / "offers"


def freeze(content: dict, captured_at: str) -> dict:
    """Wrap *content* into the immutable frozen offer-spec document.

    ``captured_at`` and ``offer_spec_hash`` are siblings OUTSIDE ``content`` so the
    hash covers the offer body only and stays stable across capture time.
    """
    return {
        "schema_version": "1.0",
        "kind": "offer_spec",
        "content": content,
        "captured_at": captured_at,
        "offer_spec_hash": canonical_hash(content),
    }


def validate_content(content: dict, schema_dir: Path | None = None) -> list[str]:
    """Validate *content* against ``offer_spec.schema.json#/$defs/offer_content``.

    Returns a list of structured ``<field/path>: <message>`` error strings (empty
    when the content conforms). Validates the ``content`` subschema ONLY — the frozen
    doc is not an agent envelope, so the full envelope schema (with ``status``) must
    never be applied (Pitfall 3).
    """
    schema_dir = (schema_dir or DEFAULT_SCHEMA_DIR).expanduser().resolve()
    schema = json.loads((schema_dir / OFFER_SPEC_SCHEMA).read_text(encoding="utf-8"))
    subschema = schema["$defs"]["offer_content"]
    registry = build_registry(schema_dir)
    validator = Draft202012Validator(subschema, registry=registry)
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(content), key=lambda e: list(e.path))
    ]


def slugify(company: str, title: str) -> str:
    """Derive a filesystem-safe ``[a-z0-9-]`` slug from company + title (T-03-path)."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{company}-{title}".lower()).strip("-")
    return slug or "offer"


def _extract_content(draft: dict) -> dict:
    """Accept either a bare content object or an object with a ``content`` key."""
    inner = draft.get("content")
    return inner if isinstance(inner, dict) else draft


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze a fielded offer draft into an immutable offer-spec.json."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Fielded offer draft JSON file.")
    source.add_argument("--stdin", action="store_true", help="Read the fielded draft from stdin.")
    parser.add_argument(
        "--captured-at",
        default=None,
        help="ISO-8601 capture time (defaults to the current UTC time).",
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
        draft = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(draft, dict):
        print("Offer draft must be a JSON object.", file=sys.stderr)
        return 1

    content = _extract_content(draft)

    errors = validate_content(content)
    if errors:
        for error in errors:
            print(f"content invalid: {error}", file=sys.stderr)
        return 1

    captured_at = args.captured_at or (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    frozen = freeze(content, captured_at)

    out_dir = OUTPUT_SUBDIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(str(content.get("company", "")), str(content.get("title", "")))
    out_path = out_dir / f"{slug}.offer-spec.json"
    # Defence in depth: the sanitized slug can never escape, but assert containment.
    if out_dir not in out_path.resolve().parents:
        print(f"Refusing to write outside {out_dir}: {out_path}", file=sys.stderr)
        return 1

    out_path.write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
