#!/usr/bin/env python3
"""Plain-python3 tests for scripts/artifacts/gmj_record_retry.py (COMPOSE-02).

Proves the per-(offer,type) retry counter is recorded by executed code, that pre-existing
state keys survive the update (T-04-07), that per-type recording is isolated, and that an
off-enum artifact_type is rejected at the CLI boundary (T-04-08). No pytest — run with
``python3 tests/test_record_retry.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "artifacts" / "gmj_record_retry.py"

# Sentinel pre-existing keys that MUST survive a counter update.
SEED_STATE = {
    "current_step": "compose",
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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_records_counter_preserving_existing_keys() -> None:
    state_path = _seed_state()
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--count", "1",
    )
    assert result.returncode == 0, f"gmj_record_retry.py failed: {result.stderr}"
    state = _load(state_path)
    assert state["retry_counts"]["acme"]["cv"] == 1, (
        f"counter not recorded: {state.get('retry_counts')!r}"
    )
    assert state["current_step"] == "compose", "current_step clobbered"
    assert state["gate_results"] == {"A": "pass"}, "gate_results clobbered"
    assert state["offer_spec_hash"] == "deadbeef", "offer_spec_hash clobbered"


def test_increment_and_per_type_isolation() -> None:
    state_path = _seed_state()
    for _ in range(2):
        r = _run(
            "--state", str(state_path),
            "--offer-slug", "acme",
            "--artifact-type", "cv",
            "--increment",
        )
        assert r.returncode == 0, f"increment cv failed: {r.stderr}"
    r = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cover_letter",
        "--increment",
    )
    assert r.returncode == 0, f"increment cover_letter failed: {r.stderr}"
    state = _load(state_path)
    assert state["retry_counts"]["acme"]["cv"] == 2, (
        f"cv counter wrong: {state['retry_counts']['acme']!r}"
    )
    assert state["retry_counts"]["acme"]["cover_letter"] == 1, (
        f"per-type isolation broken: {state['retry_counts']['acme']!r}"
    )


def test_invalid_artifact_type_rejected() -> None:
    state_path = _seed_state()
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "resume",
        "--count", "1",
    )
    assert result.returncode != 0, (
        "off-enum artifact_type must be rejected by argparse choices"
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
