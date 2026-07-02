#!/usr/bin/env python3
"""All-states determinism test for the deterministic pipeline router (ARCH-06).

Runnable as a plain assertion script (no pytest dependency). Proves that every
node in config/pipeline.dag.yaml resolves to exactly one deterministic decision
and that the committed sample fixture routes to fit-evaluator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG_PATH = REPO_ROOT / "config" / "pipeline.dag.yaml"
SAMPLE_STATE_PATH = REPO_ROOT / "schemas" / "samples" / "state.sample.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import route  # noqa: E402


def _load_dag() -> dict:
    return yaml.safe_load(DAG_PATH.read_text(encoding="utf-8")) or {}


def test_non_gate_follows_next() -> None:
    dag = _load_dag()
    state = {"current_step": "offer-scout", "completed_steps": [], "gate_results": {}}
    assert route.next_step(state, dag) == {"next_step": "artifact-composer"}


def test_gate_pass_takes_on_pass_edge() -> None:
    dag = _load_dag()
    state = {
        "current_step": "truth-verifier",
        "completed_steps": [],
        "gate_results": {"truth-verifier": "pass"},
    }
    assert route.next_step(state, dag) == {"next_step": "fit-evaluator"}


def test_gate_fail_takes_on_fail_edge() -> None:
    dag = _load_dag()
    state = {
        "current_step": "fit-evaluator",
        "completed_steps": [],
        "gate_results": {"fit-evaluator": "fail"},
    }
    assert route.next_step(state, dag) == {"next_step": "artifact-composer"}


def test_terminal_node_signals_done() -> None:
    dag = _load_dag()
    state = {"current_step": "cv-generator", "completed_steps": [], "gate_results": {}}
    assert route.next_step(state, dag) == {"status": "done"}


def test_sample_fixture_routes_to_fit_evaluator() -> None:
    dag = _load_dag()
    state = json.loads(SAMPLE_STATE_PATH.read_text(encoding="utf-8"))
    assert route.next_step(state, dag) == {"next_step": "fit-evaluator"}


def test_every_dag_node_resolves() -> None:
    dag = _load_dag()
    for node, spec in dag["steps"].items():
        gate_results = {node: "pass"} if spec.get("gate") else {}
        state = {"current_step": node, "completed_steps": [], "gate_results": gate_results}
        decision = route.next_step(state, dag)
        assert isinstance(decision, dict) and len(decision) == 1, (node, decision)
        assert ("next_step" in decision) or (decision.get("status") == "done"), (node, decision)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
