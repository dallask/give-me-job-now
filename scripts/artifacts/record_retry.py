#!/usr/bin/env python3
"""Record a per-(offer-slug, artifact_type) retry counter into the pipeline state (COMPOSE-02).

Minimal executed writer that records ``retry_counts[offer_slug][artifact_type] = N`` onto
``.pipeline/state.json``. The composer is invoked once per artifact type and each type gets
its OWN retry counter, so the count becomes a resumable, executed fact — never an agent claim
(T-04-07). Existing state keys (``current_step``, ``completed_steps``, ``gate_results``,
``offer_spec_path``/``offer_spec_hash``) are preserved on update; the file is created when
absent (read-modify-preserve, cloned from ``state_write.py``).

Cap ENFORCEMENT + cap-exhaustion honest-stop are explicitly DEFERRED to Phase 7 (hub not yet
rewired). This code adds NO cap check, ceiling, or refusal — it only records the count that
Phase 7 will later read to enforce the retry cap.

CLI: ``record_retry.py --state <path> --offer-slug <s> --artifact-type <cv|cover_letter|
interview_prep> (--count N | --increment)`` exits 0 after printing the written path; invalid
existing JSON goes to stderr, exit 1 (no traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ARTIFACT_TYPES = ["cv", "cover_letter", "interview_prep"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a per-(offer,type) retry counter into the pipeline state file."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument("--offer-slug", required=True, help="Offer slug (JSON key only)")
    parser.add_argument(
        "--artifact-type",
        required=True,
        choices=ARTIFACT_TYPES,
        help="Artifact type (constrained to the enum; becomes a JSON key only).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--count", type=int, help="Set the counter to this absolute value.")
    mode.add_argument(
        "--increment",
        action="store_true",
        help="Read the current counter (or 0) and add 1.",
    )
    args = parser.parse_args()

    state_path = args.state.expanduser()

    if state_path.is_file():
        try:
            state: dict = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Invalid state JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(state, dict):
            print("State file must contain a JSON object.", file=sys.stderr)
            return 1
    else:
        state = {}

    offer_slug = args.offer_slug
    artifact_type = args.artifact_type

    if args.increment:
        current = int(
            state.get("retry_counts", {}).get(offer_slug, {}).get(artifact_type, 0)
        )
        new_count = current + 1
    else:
        new_count = args.count

    # Record WITHOUT dropping any existing state keys.
    state.setdefault("retry_counts", {}).setdefault(offer_slug, {})
    state["retry_counts"][offer_slug][artifact_type] = new_count

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(state_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
