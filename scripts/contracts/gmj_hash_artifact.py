#!/usr/bin/env python3
"""Compute content-integrity fingerprints (offer_spec_hash / claims_hash) — ARCH-05.

The hash is a **content-integrity fingerprint, not a MAC/authentication token**:
its guarantee is that it is computed by this executed code over a documented
field subset, never asserted by an agent (T-02-09).

Fixed canonical form (repo-wide, do not vary per producer):
    json.dumps(subset, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
then UTF-8 encoded and SHA-256 hashed. ``ensure_ascii=False`` is load-bearing and
matches ``scripts/cv/gmj_extract.py`` so Cyrillic (ua/ru) content never diverges by
encoding; ``sort_keys=True`` makes key order irrelevant; the compact separators
strip incidental whitespace (T-02-10).

Documented hashed subset per kind (projection runs BEFORE canonicalization so
volatile fields never move the hash — Pitfall 5):
- ``offer_spec``: the artifact payload MINUS the frozen ``VOLATILE_FIELDS``
  denylist (per-run identifiers, timestamps, and the hash anchors themselves).
  Stable offer-spec content fields added in later phases are covered
  automatically; volatile envelope fields are always excluded.
- ``claims``: the extracted claim set — the ``claims`` collection when present,
  else the payload minus ``VOLATILE_FIELDS``.

CLI: ``gmj_hash_artifact.py --kind {offer_spec,claims} (--file <path> | --stdin)``
prints a 64-char lowercase hex SHA-256 and exits 0; errors go to stderr, exit 1.
``--kind`` is constrained to the known set and ``--file`` is guarded with
``.is_file()`` (path/kind-traversal mitigation, T-02-11).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

KINDS = ("offer_spec", "claims")

# Frozen denylist of volatile envelope fields excluded from every content hash:
# per-run identifiers, timestamps, and the hash anchors themselves. Documented
# and stable so the hashed coverage is auditable.
VOLATILE_FIELDS = frozenset(
    {
        "pipeline_run_id",
        "offer_spec_hash",
        "claims_hash",
        "timestamp",
        "created_at",
        "updated_at",
        "generated_at",
    }
)


def canonical_hash(payload: dict) -> str:
    """Return the SHA-256 hex digest of the canonical JSON of *payload*."""
    canon = json.dumps(
        payload,
        sort_keys=True,  # order-independent
        ensure_ascii=False,  # UTF-8 raw — load-bearing for Cyrillic ua/ru content
        separators=(",", ":"),  # compact, no incidental whitespace
    ).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def project_subset(payload: dict, kind: str) -> dict:
    """Project *payload* to the documented hashed subset for *kind*.

    Runs BEFORE canonicalization so volatile out-of-subset fields never affect
    the resulting hash.
    """
    if kind == "claims" and "claims" in payload:
        return {"claims": payload["claims"]}
    return {k: v for k, v in payload.items() if k not in VOLATILE_FIELDS}


def hash_artifact(payload: dict, kind: str) -> str:
    """Compute the content-integrity hash for *payload* of *kind*."""
    return canonical_hash(project_subset(payload, kind))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute canonical-JSON SHA-256 over a documented artifact subset."
    )
    parser.add_argument("--kind", required=True, choices=KINDS, help="Artifact kind to hash")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Artifact JSON file to hash")
    source.add_argument("--stdin", action="store_true", help="Read artifact JSON from stdin")
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
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(payload, dict):
        print("Artifact payload must be a JSON object", file=sys.stderr)
        return 1

    print(hash_artifact(payload, args.kind))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
