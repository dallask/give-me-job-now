#!/usr/bin/env python3
"""Honest hard-stop at the FROZEN retry cap (EXEC-03, PIPE-07/PIPE-08).

Reads the per-(offer-slug, artifact_type) retry counter recorded by
``gmj_record_retry.py`` and compares it to the FROZEN ``state.retry_cap``:

- below cap — ``retry_count < retry_cap``: print ``continue`` to stdout, exit 0,
- AT cap, first time (``retry_count == retry_cap`` and the caller has not
  already passed ``--raised`` for this offer/type) — print a distinct
  ``propose_raise`` report ``{"status":"propose_raise","artifact":<type>,
  "current_cap":<int>,"proposed_cap":<int>,"reason":<reason>}`` to stdout and
  exit **2**. The hub then either prompts for human approval
  (human-in-the-loop) or auto-applies + logs the raise (autonomous), re-invokes
  this script with ``--raised`` for the SAME offer/type going forward in this
  retry sequence, and retries the SAME recompose→Gate A/B path — a raised-cap
  recompose is NOT exempt from Gate A/B (T-41-07).
- at/over cap otherwise (``current > cap``, OR ``current == cap`` and
  ``--raised`` was passed) — print the final, distinct EXHAUSTED report
  ``{"status":"exhausted","artifact":<type>,"reason":<reason>,
  "failure_class":<"narrow"|"systemic">}`` to stdout and exit **1** (the hub
  maps this to a HARD STOP report).

**3-way exit code contract:** ``0`` = continue, ``1`` = exhausted (final hard
stop), ``2`` = propose_raise (bounded, fires at most once per offer/type per
retry sequence — CONTEXT.md's "ONE bounded cap raise" decision). The
"has this offer/type already used its one raise" state is tracked OUTSIDE this
script by the caller (``--raised``).

**Atomic cap-write (PIPEFIX-01, the ONLY state-mutating code path in this
file):** an optional ``--new-cap <int>`` argument atomically persists a raised
``retry_cap`` into ``state.json`` BEFORE the normal read-only 3-way verdict
logic below runs (against the just-written, post-bump state). This closes the
gap where a ``propose_raise`` (exit 2) response was followed by a ``--raised``
re-invocation without ``state.retry_cap`` ever actually being bumped, which
previously produced a false EXHAUSTED verdict on the SAME stale cap value. The
new value is validated with the same isinstance-int-excluding-bool guard used
for the read-path ``retry_cap`` check, and rejected if negative; on any
validation failure nothing is written (structured stderr message, exit 1, no
traceback). This mutation is triggered EXCLUSIVELY by the explicit ``--new-cap``
flag — it is never a side effect of the read-only verdict logic, and a single
invocation may both bump the cap and immediately return a verdict, or the flag
may be its own standalone invocation (the orchestrator prescribes: bump first
via a dedicated ``--new-cap`` call, THEN a separate ``--raised`` call).

There is NO "deliver best-effort" / ship-last-attempt branch anywhere: cap
exhaustion is a repudiation-proof stop, not a downgrade (Pitfall 2, T-07-12).
The cap is the FROZEN state value — this guard never re-reads
``config/pipeline.config.yaml`` mid-run (Pattern 1, T-07-14); a bool or missing
cap is rejected. Control flow mirrors ``scripts/offers/gmj_check_offer.py``
(``.is_file()`` guard → ``json.loads`` try/except → ``isinstance`` guard →
compute → distinct stdout token + exit code).

CLI: ``gmj_check_cap.py --state <path> --offer-slug <s> --artifact-type
<cv|cover_letter|interview_prep> [--reason <str>] [--raised] [--new-cap <int>]``
exits 0 (continue), 2 (propose_raise), or 1 (exhausted / missing file / invalid
JSON / malformed cap / malformed or negative ``--new-cap``); all errors go to
stderr with no traceback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ARTIFACT_TYPES = ["cv", "cover_letter", "interview_prep"]
DEFAULT_REASON = "retry cap reached"

# Fixed +1 increment for the ONE bounded cap raise (CONTEXT.md decision) —
# never config-driven, never operator-adjustable at raise time (T-41-07).
RAISE_INCREMENT = 1

# Simple, documented, necessarily-approximate heuristic (PIPE-07): a reason
# string is classified "narrow" when it looks like it names ONE specific
# failing claim (a claim-index pattern like "claims[3]"/"claim 3", or the
# literal phrase "single claim"/"single-claim"); anything else — empty
# reason, wording implying MULTIPLE claims, or generic/unspecific text — is
# classified "systemic".
_NARROW_KEYWORDS = ("single claim", "single-claim")
# Digit-index citation patterns like "claims[3]" or "claim 3" also imply a
# single, specific failing claim.
_NARROW_INDEX_RE = re.compile(r"claims?\s*[\[\(]?\s*\d+")


def _classify_failure(reason: str) -> str:
    """Classify a cap-exhaustion ``reason`` string as narrow vs systemic.

    Heuristic (approximate, documented — see module docstring): a reason is
    "narrow" when it names exactly one specific failing claim (a claim-index
    pattern such as "claims[3]"/"claim 3", or the literal phrase "single
    claim"). Anything else — empty/missing reason, or wording implying
    multiple/unclear failing claims (e.g. "multiple claims") — is "systemic".
    This is a best-effort signal for the operator, not a precise count.
    """
    if not reason:
        return "systemic"
    lowered = reason.lower()
    if any(keyword in lowered for keyword in _NARROW_KEYWORDS):
        return "narrow"
    if _NARROW_INDEX_RE.search(lowered) and "multiple" not in lowered:
        return "narrow"
    return "systemic"


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
        help="Failing reason carried into the exhausted/propose_raise report (last gate summary).",
    )
    parser.add_argument(
        "--raised",
        action="store_true",
        default=False,
        help=(
            "This offer/type has ALREADY had its one bounded raise proposed/applied "
            "for this retry sequence (caller-tracked; see module docstring)."
        ),
    )
    parser.add_argument(
        "--new-cap",
        type=int,
        default=None,
        help=(
            "Atomically bump state.json's retry_cap to this value BEFORE the normal "
            "verdict logic runs (PIPEFIX-01; see module docstring). Orthogonal to "
            "--raised — both may be passed in one invocation, or --new-cap may be its "
            "own standalone call preceding a separate --raised re-invocation."
        ),
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

    # Atomic cap-write (PIPEFIX-01) — the ONLY state-mutating code path in this
    # script, triggered exclusively by the explicit --new-cap flag. Applied
    # BEFORE the read-only verdict logic below, so a single invocation (or a
    # standalone --new-cap-only invocation) can bump the cap and have the
    # subsequent verdict logic (this call or a later --raised re-invocation)
    # see the already-bumped value.
    if args.new_cap is not None:
        existing_cap = state.get("retry_cap")
        if not isinstance(existing_cap, int) or isinstance(existing_cap, bool):
            print(
                "Malformed state: 'retry_cap' must be a frozen integer "
                "(required before --new-cap can bump it).",
                file=sys.stderr,
            )
            return 1
        if isinstance(args.new_cap, bool) or args.new_cap < 0:
            print("--new-cap must be a non-negative integer.", file=sys.stderr)
            return 1
        # Read-modify-preserve: set retry_cap, keep every sibling key
        # (including retry_counts) — mirrors gmj_state_write.py's own idiom.
        state["retry_cap"] = args.new_cap
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

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

    if current == cap and not args.raised:
        # FIRST time this exact count reaches cap — propose the ONE bounded
        # +1 raise instead of the final report (exit 2, distinct from both 0
        # and 1 so callers can branch on exit code alone without JSON-parsing
        # in a shell context).
        print(
            json.dumps(
                {
                    "status": "propose_raise",
                    "artifact": artifact_type,
                    "current_cap": cap,
                    "proposed_cap": cap + RAISE_INCREMENT,
                    "reason": args.reason,
                }
            )
        )
        return 2

    # current > cap, OR current == cap and already raised — final, distinct
    # EXHAUSTED report. NO deliver/best-effort branch.
    print(
        json.dumps(
            {
                "status": "exhausted",
                "artifact": artifact_type,
                "reason": args.reason,
                "failure_class": _classify_failure(args.reason),
            }
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
