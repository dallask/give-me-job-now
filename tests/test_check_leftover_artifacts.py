#!/usr/bin/env python3
"""RED contract for CLEAN-01 — scripts/pipeline/gmj_check_leftover_artifacts.py.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_check_leftover_artifacts.py``. This is the machine-checkable
acceptance contract that plan 06-01's implementation
(``scripts/pipeline/gmj_check_leftover_artifacts.py``) must turn GREEN. It is EXPECTED to
FAIL now (RED): the module does not exist yet, so importing it raises
``ModuleNotFoundError`` — that failure IS the RED confirmation for this task.

HARD CONSTRAINT: every fixture lives under its own ``tempfile.TemporaryDirectory()``
context manager. This file mutates NOTHING under the real repo's ``output/`` or
``.pipeline/`` directories — no fixture is ever planted, read, or written outside a
tempdir. Every assertion names the offending path/value so a failure is actionable.

Assertions (all currently RED — ModuleNotFoundError until
scripts/pipeline/gmj_check_leftover_artifacts.py exists):
  1. test_partial_offer_flagged_missing_two_types
  2. test_complete_offer_not_flagged
  3. test_empty_offer_dir_not_flagged
  4. test_missing_artifacts_dir_returns_empty_no_error
  5. test_advisory_scan_always_exits_zero
  6. test_nonexistent_output_dir_arg_exits_one_no_traceback
  7. test_two_offer_slugs_multiple_findings

Discipline: no broad try/except masks a real crash — the main() harness reports any
uncaught exception as a FAIL (exit 1), so a syntax/harness error can never pass green.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_leftover_artifacts.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_check_leftover_artifacts  # noqa: E402  (module under test; may not exist yet — RED)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _parse_findings(stdout: str) -> list[dict]:
    """Parse the script's stdout: first line is `partial: <N>`, then one JSON line per finding."""
    lines = stdout.strip().splitlines()
    assert lines, "expected at least a `partial: <N>` line in stdout, got empty output"
    assert lines[0].startswith("partial: "), (
        f"expected first stdout line to start with 'partial: ', got: {lines[0]!r}"
    )
    findings = [json.loads(line) for line in lines[1:] if line.strip()]
    return findings


def test_partial_offer_flagged_missing_two_types() -> None:
    """An offer-slug dir with only cover_letter.draft.json is flagged PARTIAL, missing cv+interview_prep."""
    with tempfile.TemporaryDirectory() as tmp:
        slug = "pathtoproject-drupal-developer"
        slug_dir = Path(tmp) / "output" / "artifacts" / slug
        slug_dir.mkdir(parents=True)
        (slug_dir / "cover_letter.draft.json").write_text("{}", encoding="utf-8")

        result = _run("--output-dir", str(Path(tmp) / "output"))
        assert result.returncode == 0, (
            f"expected exit 0 for a successful scan, got {result.returncode}: {result.stderr}"
        )

        findings = _parse_findings(result.stdout)
        assert len(findings) == 1, (
            f"expected exactly 1 finding for slug {slug!r}, got {len(findings)}: {findings}"
        )
        finding = findings[0]
        assert finding["offer_slug"] == slug, (
            f"expected offer_slug={slug!r}, got {finding.get('offer_slug')!r} in finding: {finding}"
        )
        assert finding["present"] == ["cover_letter"], (
            f"expected present=['cover_letter'], got {finding.get('present')} in finding: {finding}"
        )
        assert finding["missing"] == ["cv", "interview_prep"], (
            f"expected missing=['cv', 'interview_prep'] (sorted), got {finding.get('missing')} "
            f"in finding: {finding}"
        )


def test_complete_offer_not_flagged() -> None:
    """An offer-slug dir with all 3 draft.json files present reports zero findings."""
    with tempfile.TemporaryDirectory() as tmp:
        slug = "complete-offer-slug"
        slug_dir = Path(tmp) / "output" / "artifacts" / slug
        slug_dir.mkdir(parents=True)
        for artifact_type in ("cv", "cover_letter", "interview_prep"):
            (slug_dir / f"{artifact_type}.draft.json").write_text("{}", encoding="utf-8")

        result = _run("--output-dir", str(Path(tmp) / "output"))
        assert result.returncode == 0, (
            f"expected exit 0 for a successful scan, got {result.returncode}: {result.stderr}"
        )

        findings = _parse_findings(result.stdout)
        assert findings == [], (
            f"expected zero findings for a complete 3-of-3 offer slug {slug!r}, got: {findings}"
        )
        assert "partial: 0" in result.stdout, (
            f"expected 'partial: 0' line in stdout for a fully-complete offer, got stdout: "
            f"{result.stdout!r}"
        )


def test_empty_offer_dir_not_flagged() -> None:
    """An offer-slug subdir with zero .draft.json files (only a stray file) is NOT a leftover."""
    with tempfile.TemporaryDirectory() as tmp:
        slug = "untouched-offer-slug"
        slug_dir = Path(tmp) / "output" / "artifacts" / slug
        slug_dir.mkdir(parents=True)
        (slug_dir / "notes.txt").write_text("stray non-draft file", encoding="utf-8")

        result = _run("--output-dir", str(Path(tmp) / "output"))
        assert result.returncode == 0, (
            f"expected exit 0 for a successful scan, got {result.returncode}: {result.stderr}"
        )

        findings = _parse_findings(result.stdout)
        assert findings == [], (
            f"expected zero findings for an empty/untouched offer slug {slug!r} "
            f"(no .draft.json files present at all), got: {findings}"
        )


def test_missing_artifacts_dir_returns_empty_no_error() -> None:
    """--output-dir whose output/ has no artifacts/ subdirectory at all: empty findings, exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "output"
        output_dir.mkdir(parents=True)
        artifacts_dir = output_dir / "artifacts"
        assert not artifacts_dir.exists(), (
            f"test construction error: {artifacts_dir} must not exist for this fixture"
        )

        result = _run("--output-dir", str(output_dir))
        assert result.returncode == 0, (
            f"expected exit 0 when {artifacts_dir} does not exist (fresh repo, no prior run), "
            f"got {result.returncode}: {result.stderr}"
        )

        findings = _parse_findings(result.stdout)
        assert findings == [], (
            f"expected zero findings when artifacts/ subdir does not exist at all, got: {findings}"
        )


def test_advisory_scan_always_exits_zero() -> None:
    """Both zero-finding and multi-finding CLI invocations exit 0 (successful-scan contract)."""
    with tempfile.TemporaryDirectory() as tmp:
        # Zero-finding case: complete offer.
        complete_slug_dir = Path(tmp) / "output" / "artifacts" / "complete-slug"
        complete_slug_dir.mkdir(parents=True)
        for artifact_type in ("cv", "cover_letter", "interview_prep"):
            (complete_slug_dir / f"{artifact_type}.draft.json").write_text("{}", encoding="utf-8")

        result_zero = _run("--output-dir", str(Path(tmp) / "output"))
        assert result_zero.returncode == 0, (
            f"expected exit 0 for a zero-finding successful scan, got {result_zero.returncode}: "
            f"{result_zero.stderr}"
        )

    with tempfile.TemporaryDirectory() as tmp2:
        # Multi-finding case: partial offer.
        partial_slug_dir = Path(tmp2) / "output" / "artifacts" / "partial-slug"
        partial_slug_dir.mkdir(parents=True)
        (partial_slug_dir / "cv.draft.json").write_text("{}", encoding="utf-8")

        result_partial = _run("--output-dir", str(Path(tmp2) / "output"))
        assert result_partial.returncode == 0, (
            f"expected exit 0 for a multi-finding (partial) successful scan, got "
            f"{result_partial.returncode}: {result_partial.stderr}"
        )


def test_nonexistent_output_dir_arg_exits_one_no_traceback() -> None:
    """--output-dir pointing at a FILE (not a directory) is a genuine usage error: exit 1."""
    with tempfile.TemporaryDirectory() as tmp:
        not_a_dir = Path(tmp) / "not_a_dir.txt"
        not_a_dir.write_text("this is a file, not a directory", encoding="utf-8")

        result = _run("--output-dir", str(not_a_dir))
        assert result.returncode == 1, (
            f"expected exit 1 when --output-dir {not_a_dir} is a file (not a directory), "
            f"got {result.returncode}"
        )
        assert result.stderr.strip() != "", (
            f"expected a non-empty stderr message for the --output-dir-is-a-file usage error, "
            f"got empty stderr"
        )
        assert "Traceback" not in result.stderr, (
            f"expected no Python traceback in stderr for a handled usage error, got: "
            f"{result.stderr!r}"
        )


def test_two_offer_slugs_multiple_findings() -> None:
    """Two offer-slug subdirs (one partial, one complete) in the same tempdir: exactly 1 finding."""
    with tempfile.TemporaryDirectory() as tmp:
        partial_slug = "middle-fullstack-php-developer-wordpress-laravel"
        partial_dir = Path(tmp) / "output" / "artifacts" / partial_slug
        partial_dir.mkdir(parents=True)
        (partial_dir / "cv.draft.json").write_text("{}", encoding="utf-8")

        complete_slug = "another-complete-offer"
        complete_dir = Path(tmp) / "output" / "artifacts" / complete_slug
        complete_dir.mkdir(parents=True)
        for artifact_type in ("cv", "cover_letter", "interview_prep"):
            (complete_dir / f"{artifact_type}.draft.json").write_text("{}", encoding="utf-8")

        result = _run("--output-dir", str(Path(tmp) / "output"))
        assert result.returncode == 0, (
            f"expected exit 0 for a successful multi-slug scan, got {result.returncode}: "
            f"{result.stderr}"
        )

        findings = _parse_findings(result.stdout)
        assert len(findings) == 1, (
            f"expected exactly 1 finding (only the partial slug {partial_slug!r}; the complete "
            f"slug {complete_slug!r} must not cross-contaminate), got {len(findings)}: {findings}"
        )
        assert findings[0]["offer_slug"] == partial_slug, (
            f"expected the single finding to name the partial slug {partial_slug!r}, got: "
            f"{findings[0].get('offer_slug')!r} in finding: {findings[0]}"
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
