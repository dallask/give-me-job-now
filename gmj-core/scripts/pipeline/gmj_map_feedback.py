#!/usr/bin/env python3
"""Pure ``gate_result`` -> ``gate_feedback`` projection (GUARD-04).

Structured-only feedback is the anti-drift contract that keeps a bounded composer
retry from re-introducing unbounded context. When Gate A (truth) or Gate B
(target-fit) FAILs, the hub loops the composer with a STRUCTURED-ONLY
``{gate, missing_must_haves, fabricated_claims}`` payload — never raw evaluator
prose, transcripts, or the gate's own stdout blob. A *pure projection* means the
model never re-summarizes a gate: the reason sentence for each fabricated claim is
a deterministic ``RULE_REASON`` enum->sentence lookup, never model text (A2).

The emitted shape is the frozen ``tests/fixtures/gate_feedback.sample.json`` shape
(consumed here, never edited). Both branches emit BOTH keys (one empty) — the
fixture is the kitchen-sink shape:

    Gate A: offending_claims[] {claim_index, rule_violated, offending_span}
              -> fabricated_claims[] {claims_index, source_span, reason}
              (claim_index SINGULAR -> claims_index PLURAL — the fixture spelling;
               offending_span -> source_span; rule_violated -> reason via RULE_REASON)
    Gate B: why.missing_must_haves[] {id, text}
              -> missing_must_haves[] (plain string array — the .text values only)

This is a PURE dict->dict projection with no state I/O — modeled on
``check_truth.build_gate_a_result`` / ``score_fit.build_gate_b_result``. It reads a
normalized ``gate_result`` envelope from ``--file`` (using its ``.content``),
dispatches on ``content.gate``, and prints the projection as JSON to stdout.
Malformed/oversized input degrades to structured stderr + exit 1 with no traceback
(threat T-07-07).

CLI: ``gmj_map_feedback.py --file <gate_result.json>``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Deterministic enum -> human-readable sentence lookup. This is NOT model prose (A2):
# the four gate_result rule enums map to fixed sentences; an unknown rule falls back
# to the bare enum token so the projection never invents text.
RULE_REASON = {
    "unresolved_span": "source_span does not resolve in candidate.yaml",
    "numeric_invention": "numeric value absent from the cited candidate.yaml span",
    "scope_inflation": "claim inflates the scope of the cited candidate.yaml span",
    "cross_entry_merge": "claim merges facts from multiple candidate.yaml entries",
}


def map_gate_a(content: dict) -> dict:
    """Project a Gate-A ``gate_result`` content-doc into the frozen feedback shape.

    ``offending_claims[]`` {claim_index, rule_violated, offending_span} becomes
    ``fabricated_claims[]`` {claims_index (PLURAL — fixture spelling, NOT a typo to
    "fix"), source_span, reason} where ``reason`` is the deterministic RULE_REASON
    sentence (falling back to the bare enum on an unknown rule). ``missing_must_haves``
    is empty for Gate A — both keys are always emitted (the kitchen-sink shape).
    """
    return {
        "gate": "A",
        "missing_must_haves": [],
        "fabricated_claims": [
            {
                "claims_index": claim.get("claim_index"),
                "source_span": claim.get("offending_span"),
                "reason": RULE_REASON.get(
                    claim.get("rule_violated"), claim.get("rule_violated")
                ),
            }
            for claim in content.get("offending_claims", [])
        ],
    }


def map_gate_b(content: dict) -> dict:
    """Project a Gate-B ``gate_result`` content-doc into the frozen feedback shape.

    ``why.missing_must_haves[]`` {id, text} becomes ``missing_must_haves[]`` — a plain
    string array of the ``.text`` values only (id is dropped; the composer needs the
    human-readable must-have, not the stable index ID). ``fabricated_claims`` is empty
    for Gate B — both keys are always emitted (the kitchen-sink shape).
    """
    why = content.get("why", {})
    if not isinstance(why, dict):
        why = {}
    return {
        "gate": "B",
        "missing_must_haves": [
            mh.get("text")
            for mh in why.get("missing_must_haves", [])
            if isinstance(mh, dict)
        ],
        "fabricated_claims": [],
    }


def map_feedback(content: dict) -> dict:
    """Dispatch on ``content.gate`` and project into the frozen feedback shape.

    Only Gate A and Gate B failures loop the composer (Gate C is advisory and never
    gates), so those are the only two variants projected here.
    """
    gate = content.get("gate")
    if gate == "A":
        return map_gate_a(content)
    if gate == "B":
        return map_gate_b(content)
    raise ValueError(f"unsupported gate {gate!r}; expected 'A' or 'B'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pure gate_result -> gate_feedback projection: emit ONLY "
        "{gate, missing_must_haves, fabricated_claims} for a composer retry (GUARD-04)."
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="gate_result envelope JSON (reads content).",
    )
    args = parser.parse_args()

    gate_path = args.file.expanduser().resolve()
    if not gate_path.is_file():
        print(f"Not a file: {gate_path}", file=sys.stderr)
        return 1

    try:
        envelope = json.loads(gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(envelope, dict):
        print("gate_result must be a JSON object.", file=sys.stderr)
        return 1
    if "content" not in envelope or not isinstance(envelope["content"], dict):
        print("Malformed gate_result: missing object 'content'.", file=sys.stderr)
        return 1

    try:
        feedback = map_feedback(envelope["content"])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(feedback, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
