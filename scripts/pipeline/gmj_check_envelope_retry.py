#!/usr/bin/env python3
"""Deterministic, bounded envelope-violation retry counter (GUIDE-01 gap closure).

Tracks how many times the hub has retried the SAME ``Task(<spoke>)`` dispatch after a
``gmj-collective-handoff-contract.sh`` HOOK_ERROR (a missing/malformed ``agent_result_v1``
envelope — see ``.claude/skills/gmj-agent-output-contract/SKILL.md``). This is a DIFFERENT,
narrower concern than the Gate A/B content retry cap owned by ``gmj_check_cap.py`` /
``gmj_record_retry.py`` — the two retry concepts stay in separate counters/scripts and never
share or observe each other's state.

State is a small, session-scoped JSON counter file, NOT a new key inside
``<root>/runs/<run_id>/state.json`` (this script never touches the frozen run-state schema or
``gmj_route.py``'s DAG-node assumptions). The hub persists it at
``<root>/runs/<run_id>/envelope_retries.json`` (same ``<root>`` resolution convention documented
in ``gmj-orchestrator.md``'s ``init_run`` section: the ``pipeline-dir=<dir>`` prompt arg if
present, else the ``GMJ_PIPELINE_DIR`` environment variable, else ``.pipeline``), keyed by a
caller-supplied ``--dispatch-id`` string. The hub MUST pass the exact same run-scoped step
identifier it already uses for ``gmj_route.py``'s ``next_step`` / DAG-node name as
``--dispatch-id`` — e.g. ``gmj-artifact-composer``, or a per-artifact-type variant such as
``gmj-artifact-composer-cv`` when the hub needs to distinguish concurrent per-type dispatches of
the same spoke within one run. One JSON object: ``{"<dispatch-id>": <int count>, ...}``,
read-modify-write, created if absent (mirrors ``gmj_record_retry.py``'s read-modify-preserve
idiom).

Two CLI modes:

- ``--increment`` — increments the named dispatch-id's counter (0 if absent) and prints the new
  count to stdout. Exit **0 always** (pure recording, no verdict — mirrors
  ``gmj_record_retry.py``'s division of labor: recording and verdict are separate calls).
- check-only (no ``--increment``) — reads the current count (0 if absent/missing key) and
  returns the verdict: count ``== 0`` (no prior retry yet for this dispatch) -> print
  ``first_attempt``, exit 0; count ``== 1`` (exactly one retry already recorded) -> print
  ``retry_exhausted``, exit 1 (the hub must hard-stop, never retry a second time).

There is NO raise-the-cap path here (unlike ``gmj_check_cap.py``'s ``propose_raise``) — the
envelope-violation retry budget is a fixed, non-negotiable ONE retry per dispatch (uniform
hardening, not per-agent negotiation, per D-03's precedent), keeping this script genuinely small.

Malformed/non-dict JSON in the state file, or a missing ``--dispatch-id``, exits 1 with a clear
stderr message (no traceback) — mirrors ``gmj_record_retry.py``'s existing error-handling idiom
exactly.

CLI: ``gmj_check_envelope_retry.py --state <root>/runs/<run_id>/envelope_retries.json
--dispatch-id <str> [--increment]``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_state(state_path: Path) -> dict:
    if not state_path.is_file():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid state JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(state, dict):
        print("State file must contain a JSON object.", file=sys.stderr)
        raise SystemExit(1)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic, bounded (exactly one retry) envelope-violation retry counter "
            "for a single Task(<spoke>) dispatch — separate from the Gate A/B content "
            "retry cap."
        )
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to envelope_retries.json")
    parser.add_argument(
        "--dispatch-id",
        required=True,
        help=(
            "The exact next_step/DAG-node string just dispatched (e.g. 'gmj-artifact-composer', "
            "or a per-artifact-type variant like 'gmj-artifact-composer-cv'). JSON key only."
        ),
    )
    parser.add_argument(
        "--increment",
        action="store_true",
        default=False,
        help="Record one more retry for this dispatch-id (pure recording, always exit 0).",
    )
    args = parser.parse_args()

    if not args.dispatch_id:
        print("Missing --dispatch-id.", file=sys.stderr)
        return 1

    state_path = args.state.expanduser()

    try:
        state = _load_state(state_path)
    except SystemExit as exc:
        return int(exc.code or 1)

    dispatch_id = args.dispatch_id

    if args.increment:
        current = int(state.get(dispatch_id, 0))
        new_count = current + 1
        state[dispatch_id] = new_count
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(new_count)
        return 0

    # Check-only mode: consult the verdict, never mutate.
    current = int(state.get(dispatch_id, 0))
    if current == 0:
        print("first_attempt")
        return 0
    print("retry_exhausted")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
