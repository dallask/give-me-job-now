#!/usr/bin/env python3
"""Deterministic pipeline router (ARCH-06).

Reads a declarative DAG (config/pipeline.dag.yaml) and a resumable state file,
then emits the next pipeline step as a single JSON object to stdout. Pure
`(state, dag) -> decision` code: no Task call, no LLM, no subprocess, no network.
Gate nodes branch on a recorded verdict in state.gate_results, never on model
reasoning.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def next_step(state: dict, dag: dict) -> dict:
    """Resolve the next pipeline step from state + DAG.

    Returns exactly one of:
      {"next_step": <node>}  — advance to the named node
      {"status": "done"}     — terminal node reached (next: null)

    Raises ValueError on a missing/unknown current step or a gate node without a
    recorded verdict — the caller maps these to exit code 1.
    """
    steps = dag.get("steps") or {}
    current = state.get("current_step")
    if current is None:
        raise ValueError("state has no 'current_step'")
    if current not in steps:
        raise ValueError(f"unknown step: {current!r}")

    node = steps[current] or {}

    if node.get("gate"):
        verdict = (state.get("gate_results") or {}).get(current)
        if verdict is None:
            raise ValueError(f"gate node {current!r} has no recorded verdict in gate_results")
        target = node.get("on_pass") if verdict == "pass" else node.get("on_fail")
        if target is None:
            raise ValueError(f"gate node {current!r} missing on_pass/on_fail edge")
        return {"next_step": target}

    nxt = node.get("next")
    if nxt is None:
        return {"status": "done"}
    return {"next_step": nxt}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit the next pipeline step as JSON from a fixed DAG + state file."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument("--dag", type=Path, required=True, help="Path to pipeline.dag.yaml")
    args = parser.parse_args()

    dag_path = args.dag.expanduser()
    state_path = args.state.expanduser()

    if not dag_path.is_file():
        print(f"DAG not found: {dag_path}", file=sys.stderr)
        return 1
    if not state_path.is_file():
        print(f"State not found: {state_path}", file=sys.stderr)
        return 1

    dag: dict = yaml.safe_load(dag_path.read_text(encoding="utf-8")) or {}
    try:
        state: dict = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid state JSON: {exc}", file=sys.stderr)
        return 1

    try:
        decision = next_step(state, dag)
    except ValueError as exc:
        print(f"Routing error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(decision, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
