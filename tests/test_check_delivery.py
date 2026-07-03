#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/check_delivery.py (GUARD-03).

Proves delivery is a gated state transition: an artifact is ``deliverable``
(exit 0) ONLY when BOTH recorded gate verdicts are present and pass —
``gate_results['truth-verifier']=='pass'`` (Gate A) AND
``gate_results['fit-evaluator']=='pass'`` (Gate B). Any missing/failed verdict,
or absent ``gate_results``, is blocked (exit 1) with a naming reason. This is an
INDEPENDENT backstop: even a loop bug cannot ship a failed draft (T-07-13). No
pytest — run with ``python3 tests/test_check_delivery.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "check_delivery.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _seed_state(state: dict) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text(json.dumps(state) + "\n", encoding="utf-8")
    return tmp


def test_both_gates_pass_deliverable() -> None:
    state_path = _seed_state(
        {"gate_results": {"truth-verifier": "pass", "fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 0, f"A∧B pass must be deliverable: {result.stderr}"
    assert result.stdout.strip() == "deliverable", result.stdout


def test_fit_fail_blocked_naming_fit() -> None:
    state_path = _seed_state(
        {"gate_results": {"truth-verifier": "pass", "fit-evaluator": "fail"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "B fail must block"
    assert "fit-evaluator" in result.stderr, (
        f"blocked reason must name the failing gate: {result.stderr!r}"
    )
    assert result.stdout.strip() != "deliverable", "must not signal deliverable"


def test_truth_missing_blocked_naming_truth() -> None:
    state_path = _seed_state(
        {"gate_results": {"fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "A missing must block"
    assert "truth-verifier" in result.stderr, (
        f"blocked reason must name the missing gate: {result.stderr!r}"
    )


def test_truth_fail_blocked() -> None:
    state_path = _seed_state(
        {"gate_results": {"truth-verifier": "fail", "fit-evaluator": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "A fail must block"
    assert "truth-verifier" in result.stderr, result.stderr


def test_both_missing_blocked() -> None:
    state_path = _seed_state(
        {"gate_results": {"truth-verifier": "pass"}}
    )
    result = _run("--state", str(state_path))
    assert result.returncode == 1, "B missing must block"
    assert "fit-evaluator" in result.stderr, result.stderr


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
