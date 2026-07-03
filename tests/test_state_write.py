#!/usr/bin/env python3
"""Behavior tests for the pipeline state writer (INTAKE-02).

Runnable as a plain assertion script (no pytest dependency). Proves that
``scripts/pipeline/state_write.py`` records ``offer_spec_path`` + ``offer_spec_hash``
into ``.pipeline/state.json`` while:

- preserving existing state keys (current_step / completed_steps / gate_results) on
  update — seeded from the committed state.sample.json,
- creating the file (and parent dir) with the two offer fields when it is absent,
- exiting 1 cleanly (stderr, no traceback) on invalid existing JSON,
- leaving ``route.py`` importable and unchanged (no hash-gating leaked in).

The writer never computes the hash — it only records the value produced by the
executed ``freeze_offer.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRITER = REPO_ROOT / "scripts" / "pipeline" / "state_write.py"
SAMPLE_STATE = REPO_ROOT / "schemas" / "samples" / "state.sample.json"

_HASH = "a" * 64
_OFFER_PATH = "sources/offers/acme-senior-python.offer-spec.json"


def _run(state: Path, offer_path: str = _OFFER_PATH, offer_hash: str = _HASH):
    return subprocess.run(
        [
            sys.executable,
            str(WRITER),
            "--state",
            str(state),
            "--offer-spec-path",
            offer_path,
            "--offer-spec-hash",
            offer_hash,
        ],
        capture_output=True,
        text=True,
    )


def test_creates_file_when_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / ".pipeline" / "state.json"
        result = _run(state)
        assert result.returncode == 0, result.stderr
        assert state.is_file(), "state file must be created when absent"
        data = json.loads(state.read_text(encoding="utf-8"))
        assert data["offer_spec_path"] == _OFFER_PATH
        assert data["offer_spec_hash"] == _HASH


def test_preserves_existing_keys_on_update() -> None:
    seed = json.loads(SAMPLE_STATE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state.json"
        state.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
        result = _run(state)
        assert result.returncode == 0, result.stderr
        data = json.loads(state.read_text(encoding="utf-8"))
        # Prior keys survive untouched.
        for key in ("current_step", "completed_steps", "gate_results"):
            assert data[key] == seed[key], f"{key} must be preserved on update"
        # Offer fields are recorded.
        assert data["offer_spec_path"] == _OFFER_PATH
        assert data["offer_spec_hash"] == _HASH


def test_overwrites_offer_fields_on_rerun() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state.json"
        assert _run(state, "old/path.json", "b" * 64).returncode == 0
        assert _run(state).returncode == 0
        data = json.loads(state.read_text(encoding="utf-8"))
        assert data["offer_spec_path"] == _OFFER_PATH
        assert data["offer_spec_hash"] == _HASH


def test_invalid_json_exits_one_cleanly() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state.json"
        state.write_text("{ not valid json", encoding="utf-8")
        result = _run(state)
        assert result.returncode == 1, "invalid existing JSON must exit 1"
        assert result.stderr.strip() != "", "error must go to stderr"
        assert "Traceback" not in result.stderr, "must not dump a traceback"


def test_route_py_unchanged_and_importable() -> None:
    # route.py must remain a pure router: importable and free of any offer-spec hash logic.
    route_src = (REPO_ROOT / "scripts" / "pipeline" / "route.py").read_text(encoding="utf-8")
    assert "offer_spec_hash" not in route_src, "route.py must not gain hash logic (D-04)"
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
    import route  # noqa: F401  import must succeed


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
