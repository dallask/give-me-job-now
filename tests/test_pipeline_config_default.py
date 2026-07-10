#!/usr/bin/env python3
"""Regression guard proving scripts/ops/gmj_cron_run.sh never writes config/pipeline.config.yaml (OPS-04).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_pipeline_config_default.py``. Mirrors the idiom of
``tests/test_gmj_cron_run.py`` (a real two-process/subprocess proof against the actual wrapper
script, a PATH-shadowed fake ``claude`` stub, module-level ``REPO_ROOT``/``WRAPPER`` constants,
and a ``main()`` that runs every ``test_*`` and returns 1 on any failure).

NOTE: this file is deliberately narrower than, and does NOT duplicate,
``tests/test_pipeline_config_defaults.py`` (plural) — that file is the canonical guard for the
repo-default *value* (``execution_mode: human_in_the_loop`` / ``retry_cap: 2``) and is left
completely unmodified here. This file's only job is the NEW claim: that invoking the cron
wrapper never writes to the real, tracked ``config/pipeline.config.yaml`` file at all — proven
empirically via an mtime + sha256 content-hash comparison across a real wrapper invocation, not
inferred from the wrapper's source alone.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = REPO_ROOT / "scripts" / "dashboard"
WRAPPER = REPO_ROOT / "scripts" / "ops" / "gmj_cron_run.sh"
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"

sys.path.insert(0, str(DASH_DIR))
import gmj_dashboard_actions as actions  # noqa: E402


def _write_fake_claude(bin_dir: Path) -> None:
    """Write a PATH-shadowed fake ``claude`` executable: exits 0 immediately, no output.

    Used so the wrapper's ``os.execvp("claude", ...)`` resolves to this stub instead of a real
    Claude Code CLI invocation — zero network/LLM dependency, fast and deterministic.
    """
    stub = bin_dir / "claude"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n")
    stub.chmod(0o755)


def _run_wrapper(lock_path: Path, *, fake_claude_dir: Path) -> subprocess.CompletedProcess:
    """Invoke the REAL scripts/ops/gmj_cron_run.sh against a PATH-shadowed fake claude stub."""
    import os

    env = {**os.environ, "PATH": f"{fake_claude_dir}:{os.environ.get('PATH', '')}"}
    args = ["bash", str(WRAPPER), "--lock-path", str(lock_path)]
    return subprocess.run(args, capture_output=True, text=True, env=env)


def _snapshot(path: Path) -> tuple[float, str]:
    """Return (mtime, sha256 hex digest) for ``path``."""
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return stat.st_mtime, digest


# ── OPS-04: the cron wrapper must never write the real tracked config file ─────────────────────

def test_cron_wrapper_never_writes_pipeline_config() -> None:
    before_mtime, before_hash = _snapshot(DEFAULT_CONFIG)

    with tempfile.TemporaryDirectory() as bin_dir_s, tempfile.TemporaryDirectory() as lock_dir_s:
        bin_dir = Path(bin_dir_s)
        lock_path = Path(lock_dir_s) / "cron.lock"
        _write_fake_claude(bin_dir)

        proc = _run_wrapper(lock_path, fake_claude_dir=bin_dir)
        assert proc.returncode == 0, (
            f"wrapper invocation against the fake claude stub must exit 0, got {proc.returncode}; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
        assert "Traceback" not in proc.stderr, proc.stderr

    after_mtime, after_hash = _snapshot(DEFAULT_CONFIG)

    assert before_mtime == after_mtime, (
        f"config/pipeline.config.yaml mtime changed across a cron-wrapper invocation: "
        f"before={before_mtime!r} after={after_mtime!r} (before_hash={before_hash} after_hash={after_hash})"
    )
    assert before_hash == after_hash, (
        f"config/pipeline.config.yaml content hash changed across a cron-wrapper invocation: "
        f"before_hash={before_hash} after_hash={after_hash}"
    )


def test_wrapper_forwards_autonomous_as_override_not_default_edit() -> None:
    """Value-level cross-check: execution_mode reads human_in_the_loop before AND after one full
    wrapper invocation — i.e. the wrapper's ``mode=autonomous`` prompt argument is a per-invocation
    CLI override, never a rewrite of the tracked default. Complements (does not duplicate)
    tests/test_pipeline_config_defaults.py's static, invocation-independent assertion of the same
    committed value.
    """
    mode_before, _ = actions.read_config_values(DEFAULT_CONFIG)
    assert mode_before == "human_in_the_loop", (
        f"repo-default execution_mode must be human_in_the_loop before invoking the wrapper, got {mode_before!r}"
    )

    with tempfile.TemporaryDirectory() as bin_dir_s, tempfile.TemporaryDirectory() as lock_dir_s:
        bin_dir = Path(bin_dir_s)
        lock_path = Path(lock_dir_s) / "cron.lock"
        _write_fake_claude(bin_dir)

        proc = _run_wrapper(lock_path, fake_claude_dir=bin_dir)
        assert proc.returncode == 0, (
            f"wrapper invocation against the fake claude stub must exit 0, got {proc.returncode}; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

    mode_after, _ = actions.read_config_values(DEFAULT_CONFIG)
    assert mode_after == "human_in_the_loop", (
        f"execution_mode must still be human_in_the_loop after one full wrapper invocation "
        f"(autonomous must stay a per-invocation override, never a baked-in default edit), got {mode_after!r}"
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
