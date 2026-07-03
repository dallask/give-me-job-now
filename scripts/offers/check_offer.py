#!/usr/bin/env python3
"""Re-check a frozen offer-spec for tampering by recompute-and-compare (INTAKE-02, INTAKE-03).

Loads a frozen offer-spec document, recomputes ``canonical_hash(content)`` by
REUSING Phase 2's audited hasher, and compares it to the stored
``offer_spec_hash``. Immutability is enforced by this recompute (RESEARCH
Pattern 4), NOT by filesystem permissions:

- fresh — recomputed hash matches the stored one: print ``OK``, exit 0,
- stale — they differ (a ``content`` field was hand-edited without recomputing
  the hash): print ``STALE: <path>`` to stderr, exit 1.

Because ``captured_at`` and ``offer_spec_hash`` are siblings OUTSIDE ``content``
(the freeze layout), editing capture time never moves the recomputed hash and so
never trips staleness (Pitfall 1). This is a content-integrity fingerprint, not
a MAC — it detects careless staleness, not a motivated editor who also recomputes
the hash (T-03-integrity, accepted for a single-user local CLI).

The hub runs this before EACH downstream spoke dispatch; ``route.py`` stays a pure
DAG traversal and is NOT modified to gate on the hash (D-04 / Pitfall 4).

CLI: ``check_offer.py --file <path>`` exits 0 (fresh) or 1 (stale / missing file /
invalid JSON / malformed doc); all errors go to stderr with no traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/offers/ -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from hash_artifact import canonical_hash  # noqa: E402  reuse the audited canonical form


def is_stale(doc: dict) -> bool:
    """True when the recomputed content hash no longer matches the stored anchor."""
    return canonical_hash(doc["content"]) != doc.get("offer_spec_hash")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-check a frozen offer-spec for tampering (recompute + compare)."
    )
    parser.add_argument(
        "--file", type=Path, required=True, help="Path to the frozen offer-spec JSON."
    )
    args = parser.parse_args()

    path = args.file.expanduser().resolve()
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        return 1

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(doc, dict):
        print("Frozen offer-spec must be a JSON object.", file=sys.stderr)
        return 1
    if "content" not in doc or "offer_spec_hash" not in doc:
        print(
            "Malformed frozen offer-spec: missing 'content' or 'offer_spec_hash'.",
            file=sys.stderr,
        )
        return 1

    if is_stale(doc):
        print(f"STALE: {path}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
