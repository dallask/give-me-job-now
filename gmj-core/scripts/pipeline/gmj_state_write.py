#!/usr/bin/env python3
"""Record frozen run facts into the pipeline state file (INTAKE-02, EXEC-01, GUARD-03).

Two coexisting write operations, both using the same read-modify-preserve idiom so no
existing state key is ever dropped and ``.pipeline/state.json`` is created when absent:

1. Offer-spec recording (INTAKE-02): stamps ``offer_spec_path`` + ``offer_spec_hash``
   (recorded only when BOTH are supplied). This code never computes the hash — it only
   records the value produced by the executed ``gmj_freeze_offer.py`` (T-02-09).

2. Run-config freeze (EXEC-01, GUARD-03): when ``--run-id`` is supplied, copies
   ``execution_mode`` + ``retry_cap`` from ``config/pipeline.config.yaml`` (with optional
   CLI overrides) into the run-scoped state, plus the sanitized ``run_id``. Downstream
   control decisions read this FROZEN copy, never the config file mid-run (Pattern 1,
   T-07-03). The config is loaded via ``yaml.safe_load`` (never ``yaml.load``) with an
   ``isinstance(dict)`` guard; ``retry_cap`` must be an int excluding bool (T-07-02). The
   ``run_id`` is sanitized to ``^[A-Za-z0-9._-]+$`` — "/" and ".." are rejected before it
   can become a run-dir path component (V12 path-traversal, T-07-01).

``gmj_route.py`` stays a pure ``(state, dag) -> decision`` function and gains NO config logic.
All error paths print a structured stderr message and return 1 — never a traceback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

_EXECUTION_MODES = ("human_in_the_loop", "autonomous")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _freeze_run_config(state: dict, args: argparse.Namespace) -> int:
    """Freeze execution_mode + retry_cap + run_id into ``state`` in place.

    Returns 0 on success, 1 (after a structured stderr message) on any validation error.
    """
    # Sanitize run_id before it can become a run-dir path component (T-07-01, V12).
    run_id = args.run_id
    if ".." in run_id or "/" in run_id or "\\" in run_id or not _RUN_ID_RE.match(run_id):
        print(
            "Invalid --run-id: must match ^[A-Za-z0-9._-]+$ (no '/', '\\', or '..').",
            file=sys.stderr,
        )
        return 1

    config_path = args.config.expanduser()
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"Invalid pipeline config YAML: {exc}", file=sys.stderr)
        return 1
    if not isinstance(cfg, dict):
        print("Pipeline config YAML must parse to a mapping.", file=sys.stderr)
        return 1

    # execution_mode: CLI override wins over the config value.
    execution_mode = args.execution_mode or cfg.get("execution_mode")
    if execution_mode not in _EXECUTION_MODES:
        print(
            f"execution_mode must be one of {_EXECUTION_MODES}; got {execution_mode!r}.",
            file=sys.stderr,
        )
        return 1

    # retry_cap: CLI override wins; int excluding bool (bool is an int subclass, T-07-02).
    retry_cap = args.retry_cap if args.retry_cap is not None else cfg.get("retry_cap")
    if not isinstance(retry_cap, int) or isinstance(retry_cap, bool):
        print("retry_cap must be an integer (not a bool).", file=sys.stderr)
        return 1
    if retry_cap < 0:
        print("retry_cap must be non-negative.", file=sys.stderr)
        return 1

    # Read-modify-preserve: set frozen keys, keep every sibling key.
    state["execution_mode"] = execution_mode
    state["retry_cap"] = retry_cap
    state.setdefault("run_id", run_id)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record frozen offer-spec and/or run-config facts into the pipeline state file."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument(
        "--offer-spec-path", default=None, help="Path to the frozen offer-spec.json"
    )
    parser.add_argument(
        "--offer-spec-hash", default=None, help="offer_spec_hash from gmj_freeze_offer.py"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/pipeline.config.yaml"),
        help="Path to pipeline.config.yaml (frozen at run start).",
    )
    parser.add_argument(
        "--execution-mode",
        choices=_EXECUTION_MODES,
        default=None,
        help="Optional CLI override for execution_mode (wins over the config value).",
    )
    parser.add_argument(
        "--retry-cap",
        type=int,
        default=None,
        help="Optional CLI override for retry_cap (wins over the config value).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run identifier; presence triggers the run-config freeze. Sanitized charset.",
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

    # Run-config freeze (EXEC-01, GUARD-03): triggered by --run-id.
    if args.run_id is not None:
        rc = _freeze_run_config(state, args)
        if rc != 0:
            return rc

    # Offer-spec recording (INTAKE-02): only when BOTH fields are supplied.
    if args.offer_spec_path is not None and args.offer_spec_hash is not None:
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
