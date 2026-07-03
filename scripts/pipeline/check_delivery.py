#!/usr/bin/env python3
"""Gated delivery precondition — Gate A ∧ Gate B recorded pass (GUARD-03).

An artifact is ``deliverable`` ONLY when BOTH recorded gate verdicts pass:
``gate_results['truth-verifier'] == 'pass'`` (Gate A) AND
``gate_results['fit-evaluator'] == 'pass'`` (Gate B) — the exact gate-node names
from ``config/pipeline.dag.yaml``. Any missing/failed verdict, or absent
``gate_results``, is blocked.

This is an INDEPENDENT backstop that refuses delivery regardless of any loop
state: even a loop bug cannot ship a failed draft (Pitfall 2 defense-in-depth,
T-07-13). Control flow mirrors ``scripts/offers/check_offer.py`` (read → boolean
→ exit 0/1). All error paths go to stderr with no traceback.

CLI: ``check_delivery.py --state <path>`` prints ``deliverable`` + exit 0, or a
structured ``blocked: <which gate missing/failed>`` to stderr + exit 1 (also on
missing file / invalid JSON / non-dict state).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Exact gate-node names from config/pipeline.dag.yaml (Gate A ∧ Gate B).
REQUIRED_GATES = ["truth-verifier", "fit-evaluator"]


def blocked_reason(gate_results: dict) -> str | None:
    """Return a naming reason for the first non-passing gate, or None if all pass."""
    problems = []
    for gate in REQUIRED_GATES:
        verdict = gate_results.get(gate)
        if verdict != "pass":
            problems.append(f"{gate}={verdict if verdict is not None else 'missing'}")
    if problems:
        return "blocked: " + ", ".join(problems)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refuse delivery unless Gate A ∧ Gate B recorded a pass."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
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

    gate_results = state.get("gate_results")
    if not isinstance(gate_results, dict):
        gate_results = {}

    reason = blocked_reason(gate_results)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 1

    print("deliverable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
