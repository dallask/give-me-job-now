#!/usr/bin/env python3
"""ARTIFACT-03 quantified-framing truth invariant (Plan 14-03).

Pins the deterministic Gate-A behavior that makes "surface real numbers, never
invent/estimate/round-up" machine-enforced BEFORE the composer guidance (Plan 04) teaches
it. No new gate, no new script: this reuses the EXISTING ``gmj_check_truth.py``
``numeric_invention`` heuristic verbatim via a subprocess, and asserts the PASS/FAIL pair:

- a claim foregrounding a REAL metric whose digit is in the cited span PASSES (exit 0),
- a claim asserting an invented number absent from the cited span FAILS as
  ``numeric_invention`` (exit 1).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. Only stdlib is used; ``gmj_check_truth.py`` carries its own deps.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK = REPO_ROOT / "scripts" / "artifacts" / "gmj_check_truth.py"
CANDIDATE = REPO_ROOT / "config" / "candidate.yaml"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "artifacts"

REAL = FIXTURES / "quantified.real.draft.json"
INVENTED = FIXTURES / "quantified.invented.draft.json"


def _run_truth(draft_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--file", str(draft_path), "--candidate", str(CANDIDATE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_real_metric_passes_gate_a() -> None:
    result = _run_truth(REAL)
    assert result.returncode == 0, (
        "a claim foregrounding a REAL metric (digit present in the cited span) must PASS "
        f"Gate A (exit 0), got {result.returncode}\nstderr: {result.stderr}"
    )


def test_invented_number_fails_as_numeric_invention() -> None:
    result = _run_truth(INVENTED)
    assert result.returncode == 1, (
        "an invented number absent from the cited span must hard-FAIL Gate A (exit 1), got "
        f"{result.returncode}\nstderr: {result.stderr}"
    )
    # Parse the machine-readable gate result and assert the offending set is
    # EXACTLY the invented claim — not merely that the substring appears
    # somewhere. A substring check would still pass if the non-target claim 0
    # later regressed (e.g. failing as unresolved_span), masking a fixture
    # regression while claiming to prove the FAIL is due to numeric_invention.
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"gmj_check_truth.py must emit a JSON gate_result on stdout; got: {result.stdout!r}"
            f"\nstderr: {result.stderr}"
        ) from exc
    offending = doc["content"]["offending_claims"]
    assert offending == [
        {
            "claim_index": 1,
            "rule_violated": "numeric_invention",
            "offending_span": "professional_experience[1].achievements[1]",
        }
    ], (
        "expected ONLY claim 1 to fail as numeric_invention (implicitly proving "
        f"claim 0 stayed Gate-A-clean); got {offending}"
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
