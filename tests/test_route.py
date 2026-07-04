#!/usr/bin/env python3
"""All-states determinism test for the deterministic pipeline router (ARCH-06).

Runnable as a plain assertion script (no pytest dependency). Proves that every
node in config/pipeline.dag.yaml resolves to exactly one deterministic decision
and that the committed sample fixture routes to fit-evaluator.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG_PATH = REPO_ROOT / "config" / "pipeline.dag.yaml"
SAMPLE_STATE_PATH = REPO_ROOT / "schemas" / "samples" / "state.sample.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_route as route  # noqa: E402


def _load_dag() -> dict:
    return yaml.safe_load(DAG_PATH.read_text(encoding="utf-8")) or {}


def _write_run_scoped_state(run_id: str, state: dict) -> Path:
    """Persist a run-scoped .pipeline/runs/<run_id>/state.json under a mkdtemp root.

    Mirrors how a resumed run loads its saved state from disk (EXEC-06). Returns the path
    to the written state.json; the caller loads it back with json.loads to prove resume is a
    pure function of the persisted payload — no config read, no new routing logic.
    """
    root = Path(tempfile.mkdtemp())
    run_dir = root / ".pipeline" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "state.json"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return state_path


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


def test_resume_from_run_scoped_state_gate_pass() -> None:
    # EXEC-06: a run resumed from a persisted .pipeline/runs/<run_id>/state.json — carrying
    # run_id, execution_mode, retry_cap, a mid-pipeline gate current_step, and the gate's
    # recorded verdict — must resolve to the correct next DAG node. Resume is a pure function
    # of the saved run-scoped state: no config read, no routing logic change.
    dag = _load_dag()
    state_path = _write_run_scoped_state(
        "run-20260703-abc123",
        {
            "run_id": "run-20260703-abc123",
            "execution_mode": "autonomous",
            "retry_cap": 2,
            "current_step": "truth-verifier",
            "completed_steps": ["offer-scout", "artifact-composer"],
            "gate_results": {"truth-verifier": "pass"},
        },
    )
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        assert route.next_step(loaded, dag) == {"next_step": "fit-evaluator"}, (
            "a passed truth-verifier resumed from run-scoped state must advance to fit-evaluator"
        )
    finally:
        shutil.rmtree(state_path.parents[3], ignore_errors=True)


def test_resume_from_run_scoped_state_gate_fail() -> None:
    # Same persisted-state resume, gate verdict "fail" → loops back to artifact-composer.
    dag = _load_dag()
    state_path = _write_run_scoped_state(
        "run-20260703-def456",
        {
            "run_id": "run-20260703-def456",
            "execution_mode": "human_in_the_loop",
            "retry_cap": 2,
            "current_step": "truth-verifier",
            "completed_steps": ["offer-scout", "artifact-composer"],
            "gate_results": {"truth-verifier": "fail"},
        },
    )
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        assert route.next_step(loaded, dag) == {"next_step": "artifact-composer"}, (
            "a failed truth-verifier resumed from run-scoped state must loop back to "
            "artifact-composer"
        )
    finally:
        shutil.rmtree(state_path.parents[3], ignore_errors=True)


def test_resume_from_run_scoped_state_non_gate_node() -> None:
    # A mid-pipeline NON-gate node resumed from run-scoped state advances to its `next` node.
    dag = _load_dag()
    state_path = _write_run_scoped_state(
        "run-20260703-ghi789",
        {
            "run_id": "run-20260703-ghi789",
            "execution_mode": "autonomous",
            "retry_cap": 2,
            "current_step": "offer-scout",
            "completed_steps": [],
            "gate_results": {},
        },
    )
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        assert route.next_step(loaded, dag) == {"next_step": "artifact-composer"}, (
            "a non-gate node resumed from run-scoped state must advance to its next node"
        )
    finally:
        shutil.rmtree(state_path.parents[3], ignore_errors=True)


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
