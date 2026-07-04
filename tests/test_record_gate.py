#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_record_gate.py (GUARD-03).

Proves the gate-verdict recorder does BOTH jobs atomically so the audit log and the
routing state can never disagree (Pattern 5, threat T-07-09):

  1. The emitted gate_result envelope is written verbatim as an artifact under the run
     dir (``gate_<node>_<type>_<attempt>.json``).
  2. ``state.gate_results[<node>]`` is set to the envelope's ``content.verdict`` so
     gmj_route.py can branch (Wiring Fact 1 — gmj_route.py RAISES on a gate node with no recorded
     verdict).

Also proves the Gate-B ``{gate_b, gate_c}`` wrapper is normalized to the inner gate_b
envelope before recording (Wiring Fact 2, threat T-07-10) — Gate C never touches
gate_results — that pre-existing sibling state keys survive (T-07-09), that a traversal
run-dir is rejected (T-07-08), and that malformed gate stdout degrades to exit 1
(T-07-11). No pytest — run with ``python3 tests/test_record_gate.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_record_gate.py"
DAG_PATH = REPO_ROOT / "config" / "pipeline.dag.yaml"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_route as route  # noqa: E402  drives the Wiring Fact 1 no-raise regression case

# Sentinel pre-existing keys that MUST survive a gate-verdict update.
SEED_STATE = {
    "current_step": "truth-verifier",
    "retry_counts": {"acme": {"cv": 1}},
    "offer_spec_hash": "deadbeef",
}

# A bare Gate-A gate_result envelope, exactly as gmj_check_truth.py emits it to stdout.
GATE_A_ENVELOPE = {
    "schema_version": "1.0",
    "kind": "gate_result",
    "content": {"gate": "A", "verdict": "pass", "offending_claims": []},
}

# gmj_score_fit.py's {gate_b, gate_c} wrapper stdout — the wrapper is what record_gate normalizes.
GATE_B_WRAPPER = {
    "gate_b": {
        "schema_version": "1.0",
        "kind": "gate_result",
        "content": {
            "gate": "B",
            "verdict": "fail",
            "coverage": {"covered_ids": [], "missing_ids": ["mh-0"], "score": 0.0},
            "why": {"coverage": "0/1", "missing_must_haves": [{"id": "mh-0", "text": "x"}]},
        },
    },
    "gate_c": {
        "schema_version": "1.0",
        "kind": "gate_result",
        "content": {"gate": "C", "advisory": True, "polish": {"clarity": 4}},
    },
}


def _run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _seed_state() -> Path:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text(json.dumps(SEED_STATE) + "\n", encoding="utf-8")
    return tmp


def _run_dir() -> Path:
    return Path(tempfile.mkdtemp()) / "runs" / "run-123"


def _write_result(payload: dict) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "gate.stdout.json"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    return tmp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_gate_a_bare_envelope_recorded_as_artifact_and_state() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    result_path = _write_result(GATE_A_ENVELOPE)
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", str(result_path),
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
    )
    assert r.returncode == 0, f"gmj_record_gate.py failed: {r.stderr}"

    artifact = run_dir / "gate_truth-verifier_cv_0.json"
    assert artifact.is_file(), f"artifact not written under run dir: {artifact}"
    written = _load(artifact)
    assert written["content"]["gate"] == "A", f"artifact gate letter wrong: {written!r}"

    state = _load(state_path)
    assert state["gate_results"]["truth-verifier"] == "pass", (
        f"gate_results[truth-verifier] not set to verdict: {state.get('gate_results')!r}"
    )


def test_gate_b_wrapper_normalized_to_inner_envelope() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    result_path = _write_result(GATE_B_WRAPPER)
    r = _run(
        "--state", str(state_path),
        "--node", "fit-evaluator",
        "--result", str(result_path),
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "1",
    )
    assert r.returncode == 0, f"gmj_record_gate.py failed: {r.stderr}"

    artifact = run_dir / "gate_fit-evaluator_cv_1.json"
    assert artifact.is_file(), f"artifact not written: {artifact}"
    written = _load(artifact)
    # The stored artifact is the INNER gate_b envelope, NOT the {gate_b, gate_c} wrapper.
    assert written["content"]["gate"] == "B", f"wrapper not normalized: {written!r}"
    assert "gate_b" not in written, "wrapper leaked into the stored artifact"
    assert "gate_c" not in written, "gate_c leaked into the stored artifact"

    state = _load(state_path)
    assert state["gate_results"]["fit-evaluator"] == "fail", (
        f"gate_results[fit-evaluator] wrong: {state.get('gate_results')!r}"
    )
    # Gate C must NEVER enter gate_results (FIT-05, threat T-07-10).
    assert "gate_c" not in state["gate_results"], "gate_c leaked into gate_results"
    assert "C" not in state["gate_results"], "Gate C letter leaked into gate_results"


def test_sibling_state_keys_survive() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    result_path = _write_result(GATE_A_ENVELOPE)
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", str(result_path),
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
    )
    assert r.returncode == 0, f"gmj_record_gate.py failed: {r.stderr}"
    state = _load(state_path)
    assert state["current_step"] == "truth-verifier", "current_step clobbered"
    assert state["retry_counts"] == {"acme": {"cv": 1}}, "retry_counts clobbered"
    assert state["offer_spec_hash"] == "deadbeef", "offer_spec_hash clobbered"


def test_stdin_result_supported() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", "-",
        "--run-dir", str(run_dir),
        "--artifact-type", "cover_letter",
        "--attempt", "2",
        stdin=json.dumps(GATE_A_ENVELOPE),
    )
    assert r.returncode == 0, f"gmj_record_gate.py failed on stdin: {r.stderr}"
    assert (run_dir / "gate_truth-verifier_cover_letter_2.json").is_file()


def test_traversal_run_dir_rejected() -> None:
    state_path = _seed_state()
    result_path = _write_result(GATE_A_ENVELOPE)
    bad_run_dir = Path(tempfile.mkdtemp()) / "runs" / ".." / "escape"
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", str(result_path),
        "--run-dir", str(bad_run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
    )
    assert r.returncode == 1, "traversal run-dir must be rejected (exit 1)"


def test_malformed_result_rejected() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", "-",
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
        stdin="{not json",
    )
    assert r.returncode == 1, "malformed gate stdout must exit 1"


def test_missing_verdict_rejected() -> None:
    state_path = _seed_state()
    run_dir = _run_dir()
    no_verdict = {"schema_version": "1.0", "kind": "gate_result", "content": {"gate": "A"}}
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", "-",
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
        stdin=json.dumps(no_verdict),
    )
    assert r.returncode == 1, "missing content.verdict must exit 1"


def test_route_does_not_raise_on_produced_state() -> None:
    """Wiring Fact 1 regression: the recorded verdict lets gmj_route.py branch, not raise."""
    state_path = _seed_state()
    run_dir = _run_dir()
    result_path = _write_result(GATE_A_ENVELOPE)
    r = _run(
        "--state", str(state_path),
        "--node", "truth-verifier",
        "--result", str(result_path),
        "--run-dir", str(run_dir),
        "--artifact-type", "cv",
        "--attempt", "0",
    )
    assert r.returncode == 0, f"gmj_record_gate.py failed: {r.stderr}"

    state = _load(state_path)
    state["current_step"] = "truth-verifier"  # route reads gate_results[current_step]
    dag = yaml.safe_load(DAG_PATH.read_text(encoding="utf-8")) or {}
    # Must NOT raise "gate node ... has no recorded verdict" — that is the whole point.
    decision = route.next_step(state, dag)
    assert decision == {"next_step": "fit-evaluator"}, (
        f"pass verdict should route to on_pass edge, got {decision!r}"
    )


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
