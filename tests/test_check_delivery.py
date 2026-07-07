#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_check_delivery.py (GUARD-03).

Proves delivery is a gated state transition: an artifact is ``deliverable``
(exit 0) ONLY when BOTH recorded gate verdicts are present and pass —
``gate_results['gmj-truth-verifier']=='pass'`` (Gate A) AND
``gate_results['gmj-fit-evaluator']=='pass'`` (Gate B). Any missing/failed verdict,
or absent ``gate_results``, is blocked (exit 1) with a naming reason. This is an
INDEPENDENT backstop: even a loop bug cannot ship a failed draft (T-07-13). No
pytest — run with ``python3 tests/test_check_delivery.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_delivery.py"
PIPELINE_RUN = REPO_ROOT / "scripts" / "pipeline" / "gmj_pipeline_run.py"
STATE_WRITE = REPO_ROOT / "scripts" / "pipeline" / "gmj_state_write.py"
RECORD_GATE = REPO_ROOT / "scripts" / "pipeline" / "gmj_record_gate.py"
PIPELINE_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess:
    """Generalized ``_run`` parametrized over the invoked script path."""
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _write_gate_result(tmp_dir: Path, verdict: str) -> Path:
    """Write a ``{"content": {"verdict": verdict}}`` gate-stdout JSON to a temp file."""
    result_path = tmp_dir / f"gate-result-{uuid.uuid4().hex}.json"
    result_path.write_text(
        json.dumps({"content": {"verdict": verdict}}) + "\n", encoding="utf-8"
    )
    return result_path


def _seed_state(state: dict) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text(json.dumps(state) + "\n", encoding="utf-8")
    return tmp


def test_both_gates_pass_deliverable() -> None:
    state_path = _seed_state(
        {"gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 0, f"A∧B pass must be deliverable: {result.stderr}"
    assert result.stdout.strip() == "deliverable", result.stdout


def test_fit_fail_blocked_naming_fit() -> None:
    state_path = _seed_state(
        {"gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "fail"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "B fail must block"
    assert "gmj-fit-evaluator" in result.stderr, (
        f"blocked reason must name the failing gate: {result.stderr!r}"
    )
    assert result.stdout.strip() != "deliverable", "must not signal deliverable"


def test_truth_missing_blocked_naming_truth() -> None:
    state_path = _seed_state(
        {"gate_results": {"gmj-fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "A missing must block"
    assert "gmj-truth-verifier" in result.stderr, (
        f"blocked reason must name the missing gate: {result.stderr!r}"
    )


def test_truth_fail_blocked() -> None:
    state_path = _seed_state(
        {"gate_results": {"gmj-truth-verifier": "fail", "gmj-fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "A fail must block"
    assert "gmj-truth-verifier" in result.stderr, result.stderr


def test_both_missing_blocked() -> None:
    state_path = _seed_state(
        {"gate_results": {"gmj-truth-verifier": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "B missing must block"
    assert "gmj-fit-evaluator" in result.stderr, result.stderr


def test_gate_results_absent_blocked() -> None:
    state_path = _seed_state({"current_step": "compose"})
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "absent gate_results must block"
    assert result.stdout.strip() != "deliverable"
    assert result.stderr.strip(), "must report a blocked reason"


def test_invalid_state_json_rejected() -> None:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text("{not valid json", encoding="utf-8")
    result = _run("--state", str(tmp))
    assert result.returncode == 1, "invalid JSON must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on malformed state"


def test_non_dict_state_rejected() -> None:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text("[1, 2, 3]", encoding="utf-8")
    result = _run("--state", str(tmp))
    assert result.returncode == 1, "non-dict state must exit 1"
    assert "Traceback" not in result.stderr


def test_missing_state_file_rejected() -> None:
    result = _run("--state", "/nonexistent/state.json")
    assert result.returncode == 1, "missing state file must exit 1"
    assert "Traceback" not in result.stderr


def test_independent_state_files_no_cross_type_clobber() -> None:
    """Two per-artifact-type ``state.json`` files derived by ``gmj_pipeline_run.py`` must
    NEVER share a gate verdict — the ARTF-01/ARTF-04 regression guard 32-RESEARCH.md's Wave 0
    flags as missing.

    Derives run_ids for ``cv``/``cover_letter`` from one base run_id, seeds each its OWN
    state.json, records BOTH gates as "pass" on the cv file and ONLY Gate A on the
    cover_letter file, then independently checks delivery on each — proving the cv file's
    fully-recorded pass never leaks into the cover_letter file.
    """
    base_run_id = f"iso-test-{uuid.uuid4().hex[:8]}"
    derive = _run_script(
        PIPELINE_RUN, "--run-id", base_run_id, "--artifact-types", "cv,cover_letter"
    )
    assert derive.returncode == 0, f"pipeline_run derivation must succeed: {derive.stderr}"
    derived: dict[str, str] = {}
    for line in derive.stdout.strip().splitlines():
        key, _, run_id = line.partition("=")
        derived[key] = run_id
    assert set(derived) == {"cv", "cover_letter"}, derived

    tmp_root = Path(tempfile.mkdtemp())
    state_paths: dict[str, Path] = {}
    run_dirs: dict[str, Path] = {}
    for artifact_type, run_id in derived.items():
        run_dir = tmp_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        state_path = run_dir / "state.json"
        write = _run_script(
            STATE_WRITE,
            "--state", str(state_path),
            "--run-id", run_id,
            "--config", str(PIPELINE_CONFIG),
            "--execution-mode", "human_in_the_loop",
            "--retry-cap", "2",
        )
        assert write.returncode == 0, (
            f"state seed for {artifact_type} must succeed: {write.stderr}"
        )
        state_paths[artifact_type] = state_path
        run_dirs[artifact_type] = run_dir

    # cv: BOTH gates recorded pass on its own state file.
    cv_run_dir = run_dirs["cv"]
    for node in ("gmj-truth-verifier", "gmj-fit-evaluator"):
        result_path = _write_gate_result(cv_run_dir, "pass")
        record = _run_script(
            RECORD_GATE,
            "--state", str(state_paths["cv"]),
            "--node", node,
            "--result", str(result_path),
            "--run-dir", str(cv_run_dir),
            "--artifact-type", "cv",
            "--attempt", "1",
        )
        assert record.returncode == 0, f"recording {node} on cv must succeed: {record.stderr}"

    # cover_letter: ONLY Gate A recorded pass; Gate B deliberately left unrecorded on THIS file.
    cl_run_dir = run_dirs["cover_letter"]
    cl_result_path = _write_gate_result(cl_run_dir, "pass")
    record_cl = _run_script(
        RECORD_GATE,
        "--state", str(state_paths["cover_letter"]),
        "--node", "gmj-truth-verifier",
        "--result", str(cl_result_path),
        "--run-dir", str(cl_run_dir),
        "--artifact-type", "cover_letter",
        "--attempt", "1",
    )
    assert record_cl.returncode == 0, (
        f"recording gmj-truth-verifier on cover_letter must succeed: {record_cl.stderr}"
    )

    # cv's own state.json: both gates pass -> deliverable.
    cv_check = _run("--state", str(state_paths["cv"]))
    assert cv_check.returncode == 0, f"cv state must be deliverable: {cv_check.stderr}"
    assert cv_check.stdout.strip() == "deliverable", cv_check.stdout

    # cover_letter's own state.json: Gate B missing -> blocked, naming gmj-fit-evaluator.
    cl_check = _run("--state", str(state_paths["cover_letter"]))
    assert cl_check.returncode == 1, "cover_letter state missing Gate B must block"
    assert "gmj-fit-evaluator" in cl_check.stderr, cl_check.stderr

    # Load-bearing: cover_letter's own gate_results has NO gmj-fit-evaluator key at all --
    # proving cv's fully-recorded pass never leaked into cover_letter's own file.
    cl_state = json.loads(state_paths["cover_letter"].read_text(encoding="utf-8"))
    assert cl_state.get("gate_results", {}).get("gmj-fit-evaluator") is None, cl_state


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
