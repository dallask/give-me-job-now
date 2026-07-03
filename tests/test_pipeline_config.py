#!/usr/bin/env python3
"""Plain-python3 tests for the run-config freeze path in state_write.py (EXEC-01, GUARD-03).

Proves that scripts/pipeline/state_write.py freezes execution_mode + retry_cap + run_id
from config/pipeline.config.yaml into run-scoped state at run start, while:

- preserving pre-existing sibling state keys (current_step / gate_results /
  offer_spec_hash) — the T-04-07 key-preservation idiom,
- letting a --execution-mode CLI override win over the config value,
- rejecting a bool retry_cap (bool is an int subclass — must be excluded), exit 1,
- rejecting a non-mapping top-level config, exit 1, no traceback (T-07-02),
- rejecting a run_id containing "/" or ".." (V12 path-traversal, T-07-01), exit 1.

No pytest — run with ``python3 tests/test_pipeline_config.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "state_write.py"

# Sentinel pre-existing keys that MUST survive a run-config freeze.
SEED_STATE = {
    "current_step": "intake",
    "gate_results": {"A": "pass"},
    "offer_spec_hash": "deadbeef",
}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _seed_state() -> Path:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text(json.dumps(SEED_STATE) + "\n", encoding="utf-8")
    return tmp


def _write_config(text: str) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "pipeline.config.yaml"
    tmp.write_text(text, encoding="utf-8")
    return tmp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_GOOD_CONFIG = "execution_mode: human_in_the_loop\nretry_cap: 2\n"


def test_freezes_mode_cap_run_id_preserving_siblings() -> None:
    state = _seed_state()
    cfg = _write_config(_GOOD_CONFIG)
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "demo1")
    assert result.returncode == 0, result.stderr
    data = _load(state)
    assert data["execution_mode"] == "human_in_the_loop"
    assert data["retry_cap"] == 2
    assert data["run_id"] == "demo1"
    # Sibling keys survive untouched.
    for key, val in SEED_STATE.items():
        assert data[key] == val, f"{key} must be preserved on freeze"


def test_cli_execution_mode_override_wins() -> None:
    state = _seed_state()
    cfg = _write_config(_GOOD_CONFIG)
    result = _run(
        "--state", str(state), "--config", str(cfg),
        "--run-id", "demo2", "--execution-mode", "autonomous",
    )
    assert result.returncode == 0, result.stderr
    assert _load(state)["execution_mode"] == "autonomous"


def test_cli_retry_cap_override_wins() -> None:
    state = _seed_state()
    cfg = _write_config(_GOOD_CONFIG)
    result = _run(
        "--state", str(state), "--config", str(cfg),
        "--run-id", "demo3", "--retry-cap", "5",
    )
    assert result.returncode == 0, result.stderr
    assert _load(state)["retry_cap"] == 5


def test_bool_retry_cap_rejected() -> None:
    state = _seed_state()
    cfg = _write_config("execution_mode: autonomous\nretry_cap: true\n")
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "demo4")
    assert result.returncode == 1, "bool retry_cap must be rejected"
    assert result.stderr.strip() != "", "error must go to stderr"
    assert "Traceback" not in result.stderr, "must not dump a traceback"


def test_non_mapping_config_rejected() -> None:
    state = _seed_state()
    cfg = _write_config("- just\n- a\n- list\n")
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "demo5")
    assert result.returncode == 1, "non-mapping config must be rejected"
    assert result.stderr.strip() != "", "error must go to stderr"
    assert "Traceback" not in result.stderr, "must not dump a traceback"


def test_run_id_slash_rejected() -> None:
    state = _seed_state()
    cfg = _write_config(_GOOD_CONFIG)
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "a/b")
    assert result.returncode == 1, "run_id with '/' must be rejected"
    assert result.stderr.strip() != "", "error must go to stderr"
    assert "Traceback" not in result.stderr, "must not dump a traceback"


def test_run_id_dotdot_rejected() -> None:
    state = _seed_state()
    cfg = _write_config(_GOOD_CONFIG)
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "..")
    assert result.returncode == 1, "run_id containing '..' must be rejected"
    assert result.stderr.strip() != "", "error must go to stderr"
    assert "Traceback" not in result.stderr, "must not dump a traceback"


def test_bad_execution_mode_in_config_rejected() -> None:
    state = _seed_state()
    cfg = _write_config("execution_mode: sideways\nretry_cap: 2\n")
    result = _run("--state", str(state), "--config", str(cfg), "--run-id", "demo6")
    assert result.returncode == 1, "invalid execution_mode enum must be rejected"
    assert "Traceback" not in result.stderr, "must not dump a traceback"


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
