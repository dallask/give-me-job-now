#!/usr/bin/env python3
"""Plain-python3 tests for scripts/publish/gmj_check_milestone_releases.py (REL-05/REL-06).

Proves the script's own strict exit-0/1 contract against a simulated gap (SC3), and
surfaces (never asserts) any REAL gap found against this repo's actual MILESTONES.md /
milestone-releases.yaml files, via warnings.warn() — the only mechanism proven (this
phase's empirical CI-flag probe, see 03-RESEARCH.md) to survive this repo's real
`pytest tests/ -q -p no:cacheprovider -n auto` invocation without -s/-v (D-03).

Deliberate first: this file is the first in tests/ to `import warnings` — every other
file in tests/ (85 files, verified via grep) imports neither `pytest` nor `warnings`,
since the advisory-only surfacing mechanism D-03 requires has no prior repo analog.
Everything else in this file (module docstring style, `_run()` subprocess helper,
tempfile-only fixture isolation, self-running `main()` harness) is copied from this
repo's existing convention.

No pytest import — run with ``python3 tests/test_milestone_releases_coverage.py``,
same self-running-harness convention as every other file in tests/.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "publish" / "gmj_check_milestone_releases.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_milestone_releases_coverage_advisory() -> None:
    """Advisory-only (D-03): surfaces any real gap via a warning, never fails the build.

    Runs the REAL script (no --milestones/--releases override, so it reads the actual
    .planning/MILESTONES.md + scripts/publish/milestone-releases.yaml). Never asserts on
    the subprocess's return code — this is the advisory-only layer per D-03.
    """
    result = _run()
    assert "Traceback" not in result.stderr, result.stderr
    if result.returncode != 0:
        warnings.warn(
            f"gmj_check_milestone_releases.py detected a gap (exit {result.returncode}): "
            f"{result.stdout.strip()} {result.stderr.strip()}".strip()
        )
    # No assert on result.returncode here — advisory-only per D-03.


def test_script_exits_nonzero_on_simulated_gap() -> None:
    """SC3: prove detection actually works — simulate an un-backfilled milestone.

    Builds a tempfile.TemporaryDirectory()-backed fixture pair (never touching the real,
    tracked .planning/MILESTONES.md or scripts/publish/milestone-releases.yaml) and
    invokes the script with explicit --milestones/--releases pointing at the temp files.
    This test DOES assert — it proves the script's own strict SC1 contract, not the
    advisory layer.
    """
    with tempfile.TemporaryDirectory() as tmp_dir_s:
        tmp_dir = Path(tmp_dir_s)
        milestones_md = tmp_dir / "MILESTONES.md"
        milestones_md.write_text(
            "# Milestones\n\n"
            "## v10.0 Simulated Un-backfilled Milestone (Shipped: 2026-07-12)\n\n"
            "**Phases completed:** 1 phases, 1 plans, 1 tasks\n\n---\n",
            encoding="utf-8",
        )
        releases_yaml = tmp_dir / "milestone-releases.yaml"
        releases_yaml.write_text("releases: []\n", encoding="utf-8")

        result = _run(
            "--milestones", str(milestones_md),
            "--releases", str(releases_yaml),
        )
        assert result.returncode == 1, (
            f"expected exit 1 on a simulated gap, got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "v10.0.0" in result.stdout or "v10.0.0" in result.stderr, (
            f"expected v10.0.0 named in output, got stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "Traceback" not in result.stderr, result.stderr


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
