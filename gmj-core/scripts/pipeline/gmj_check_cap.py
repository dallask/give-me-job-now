#!/usr/bin/env python3
"""Honest hard-stop at the FROZEN retry cap (EXEC-03).

Reads the per-(offer-slug, artifact_type) retry counter recorded by
``gmj_record_retry.py`` and compares it to the FROZEN ``state.retry_cap``:

- below cap — ``retry_count < retry_cap``: print ``continue`` to stdout, exit 0,
- at/over cap — ``retry_count >= retry_cap``: print a distinct EXHAUSTED report
  ``{"status":"exhausted","artifact":<type>,"reason":<reason>}`` to stdout and
  exit nonzero (the hub maps this to a HARD STOP report).

There is NO "deliver best-effort" / ship-last-attempt branch anywhere: cap
exhaustion is a repudiation-proof stop, not a downgrade (Pitfall 2, T-07-12).
The cap is the FROZEN state value — this guard never re-reads
``config/pipeline.config.yaml`` mid-run (Pattern 1, T-07-14); a bool or missing
cap is rejected. Control flow mirrors ``scripts/offers/gmj_check_offer.py``
(``.is_file()`` guard → ``json.loads`` try/except → ``isinstance`` guard →
compute → distinct stdout token + exit code).

CLI: ``gmj_check_cap.py --state <path> --offer-slug <s> --artifact-type
<cv|cover_letter|interview_prep> [--reason <str>]`` exits 0 (continue) or nonzero
(exhausted / missing file / invalid JSON / malformed cap); all errors go to
stderr with no traceback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ARTIFACT_TYPES = ["cv", "cover_letter", "interview_prep"]
DEFAULT_REASON = "retry cap reached"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Honest hard-stop at the frozen retry cap (never ship-last-attempt)."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument("--offer-slug", required=True, help="Offer slug (JSON key only)")
    parser.add_argument(
        "--artifact-type",
        required=True,
        choices=ARTIFACT_TYPES,
        help="Artifact type (constrained to the enum; a JSON key only).",
    )
    parser.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        help="Failing reason carried into the exhausted report (last gate summary).",
    )
    args = parser.parse_args()

    state_path = args.state.expanduser()
    if not state_path.is_file():
        print(f"Not a file: {state_path}", file=sys.stderr)
        return 1

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid state JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(state, dict):
        print("State file must contain a JSON object.", file=sys.stderr)
        return 1

    offer_slug = args.offer_slug
    artifact_type = args.artifact_type

    # Cap is the FROZEN state value — never re-read from config (Pattern 1).
    cap = state.get("retry_cap")
    if not isinstance(cap, int) or isinstance(cap, bool):
        print(
            "Malformed state: 'retry_cap' must be a frozen integer.",
            file=sys.stderr,
        )
        return 1

    # Missing counter is treated as 0 (no attempt recorded yet).
    current = int(state.get("retry_counts", {}).get(offer_slug, {}).get(artifact_type, 0))

    if current < cap:
        print("continue")
        return 0

    # At/over cap — distinct EXHAUSTED report. NO deliver/best-effort branch.
    print(
        json.dumps(
            {"status": "exhausted", "artifact": artifact_type, "reason": args.reason}
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
