#!/usr/bin/env python3
"""Record the frozen offer-spec path + hash into the pipeline state file (INTAKE-02).

Minimal executed writer that stamps ``offer_spec_path`` and ``offer_spec_hash`` onto
``.pipeline/state.json``. The hub reads these to invoke ``check_offer.py`` before each
spoke dispatch; ``route.py`` stays a pure ``(state, dag) -> decision`` function and gains
NO hash logic (D-04 / RESEARCH Open Q1). Existing state keys (``current_step``,
``completed_steps``, ``gate_results``) are preserved on update; the file is created when
absent. This code never computes the hash — it only records the value produced by the
executed ``freeze_offer.py`` (the hash is never agent-asserted, T-02-09).

CLI: ``state_write.py --state <path> --offer-spec-path <p> --offer-spec-hash <h>`` exits 0
after printing the written path; invalid existing JSON goes to stderr, exit 1 (no traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record the frozen offer-spec path + hash into the pipeline state file."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument(
        "--offer-spec-path", required=True, help="Path to the frozen offer-spec.json"
    )
    parser.add_argument(
        "--offer-spec-hash", required=True, help="offer_spec_hash from freeze_offer.py"
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

    # Record the offer fields WITHOUT dropping any existing state keys.
    state["offer_spec_path"] = args.offer_spec_path
    state["offer_spec_hash"] = args.offer_spec_hash

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(state_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
