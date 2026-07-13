#!/usr/bin/env python3
"""Unit tests for scripts/gmj_self_reflect.py (REFLECT-03/REFLECT-04).

Runnable as a plain assertion script (no pytest dependency). Calls
``classify()``/``classify_from_entries()``/``render_report()`` as direct Python
function imports (not via subprocess), per 06-PATTERNS.md's recommended shape for
this file.

Covers:
- The three-stage separation (classify -> render_report -> write_report) and the
  zero-mutation guarantee (write_report is the only filesystem-write call).
- The normal-run fixture produces zero (or near-zero) findings — no false positives
  on ordinary activity.
- Both CONTEXT.md-named acceptance-bar patterns (worktree-base-drift,
  pycache-hook-log-pollution) are detected with a proposed fix when present in
  fixture logs, individually and simultaneously when both fixture files are read
  together from the same directory.
- A malformed/partial JSONL line never crashes the analyzer.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution-logs"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_self_reflect  # noqa: E402


NORMAL_RUN = FIXTURES / "normal-run.jsonl"
WORKTREE_DRIFT = FIXTURES / "recurring-worktree-drift.jsonl"
PYCACHE_FAILURE = FIXTURES / "recurring-pycache-failure.jsonl"
CAP_RAISE_MISUSE = FIXTURES / "recurring-cap-raise-misuse.jsonl"


def _read_jsonl(path: Path) -> list[dict]:
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def _copy_fixtures_to_tmp(*fixture_paths: Path) -> Path:
    """Copy the given fixture JSONL files into an isolated tmp log-dir.

    Renamed to match ``classify()``'s ``tool-calls-*.jsonl`` glob pattern (the
    fixture files use descriptive names like ``recurring-worktree-drift.jsonl``,
    which would not otherwise be picked up by the on-disk reader). SubagentStop
    entries in the worktree-drift fixture reference transcript_path values that
    are relative to the real FIXTURES dir; rewrite them to absolute paths in the
    copied file so classify() can resolve them regardless of tmp cwd.
    """
    tmp = Path(tempfile.mkdtemp(prefix="self-reflect-"))
    for idx, src in enumerate(fixture_paths):
        entries = _read_jsonl(src)
        for entry in entries:
            tp = entry.get("transcript_path")
            if tp and not Path(tp).is_absolute():
                entry["transcript_path"] = str((FIXTURES / tp).resolve())
        dest = tmp / f"tool-calls-2026-07-1{idx}.jsonl"
        with dest.open("w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
    return tmp


# --------------------------------------------------------------------------- Task 1 tests

def test_three_stage_functions_exist_and_are_callable() -> None:
    assert callable(gmj_self_reflect.classify)
    assert callable(gmj_self_reflect.render_report)
    assert callable(gmj_self_reflect.write_report)


def test_write_report_is_the_only_filesystem_write_call() -> None:
    """Grep-verifiable: no write/unlink/rename call exists anywhere else in the file."""
    source = (REPO_ROOT / "scripts" / "gmj_self_reflect.py").read_text(encoding="utf-8")
    # Find every write-shaped call site outside write_report()'s own body.
    write_shaped = re.compile(r"\.write_text\(|\.write\(|\.unlink\(|\.rename\(|open\([^)]*['\"]w")
    func_match = re.search(
        r"def write_report\(.*?\n(?:.*\n)*?(?=\ndef |\Z)", source
    )
    assert func_match, "write_report() function body not found"
    body_start, body_end = func_match.span()
    outside_text = source[:body_start] + source[body_end:]
    matches = write_shaped.findall(outside_text)
    assert not matches, f"unexpected write-shaped call(s) outside write_report(): {matches}"


def test_normal_run_produces_no_false_positive_findings() -> None:
    entries = _read_jsonl(NORMAL_RUN)
    findings = gmj_self_reflect.classify_from_entries(entries)
    assert findings == [], f"expected zero findings on normal-run fixture, got: {findings}"


def test_malformed_jsonl_line_never_crashes_classify() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="self-reflect-malformed-"))
    log_file = tmp / "tool-calls-2026-07-12.jsonl"
    good_entry = json.dumps(
        {"ts": "2026-07-12T10:00:00Z", "source": "tool-call", "tool_name": "Bash", "command": "ls"}
    )
    log_file.write_text(
        good_entry + "\n" + "{not valid json,,,\n" + "\n" + good_entry + "\n",
        encoding="utf-8",
    )
    # Must not raise.
    findings = gmj_self_reflect.classify(tmp)
    assert isinstance(findings, list)


def test_classify_returns_list_of_dicts_with_required_fields() -> None:
    entries = _read_jsonl(WORKTREE_DRIFT)
    tmp = _copy_fixtures_to_tmp(WORKTREE_DRIFT)
    findings = gmj_self_reflect.classify(tmp)
    for finding in findings:
        assert "pattern" in finding
        assert "occurrences" in finding
        assert "proposed_fix" in finding
        assert finding["proposed_fix"]


# --------------------------------------------------------------------------- Task 2 tests

def test_worktree_drift_pattern_detected_with_fix() -> None:
    tmp = _copy_fixtures_to_tmp(WORKTREE_DRIFT)
    findings = gmj_self_reflect.classify(tmp)
    match = next((f for f in findings if f["pattern"] == "worktree-base-drift"), None)
    assert match is not None, f"worktree-base-drift not found in findings: {findings}"
    assert match["occurrences"] >= 3, f"expected >=3 occurrences, got {match['occurrences']}"
    assert match["proposed_fix"], "expected a non-empty proposed_fix"

    report = gmj_self_reflect.render_report(findings)
    assert "worktree-base-drift" in report
    assert match["proposed_fix"][:40] in report or "Proposed fix" in report


def test_pycache_pollution_pattern_detected_with_fix() -> None:
    tmp = _copy_fixtures_to_tmp(PYCACHE_FAILURE)
    findings = gmj_self_reflect.classify(tmp)
    match = next((f for f in findings if f["pattern"] == "pycache-hook-log-pollution"), None)
    assert match is not None, f"pycache-hook-log-pollution not found in findings: {findings}"
    assert match["occurrences"] >= 2, f"expected >=2 occurrences, got {match['occurrences']}"
    assert match["proposed_fix"], "expected a non-empty proposed_fix"

    report = gmj_self_reflect.render_report(findings)
    assert "pycache-hook-log-pollution" in report


def test_cap_raise_misuse_pattern_detected_with_fix() -> None:
    """New gmj-pipeline-domain detector (REFLECT-07): fires on a repeated
    gmj_check_cap.py --raised re-invocation sequence for the same offer/artifact-type,
    mirroring the exact command-field shape confirmed against the real 2026-07-13 log."""
    tmp = _copy_fixtures_to_tmp(CAP_RAISE_MISUSE)
    findings = gmj_self_reflect.classify(tmp)
    match = next((f for f in findings if f["pattern"] == "gmj-pipeline-cap-raise-misuse"), None)
    assert match is not None, f"gmj-pipeline-cap-raise-misuse not found in findings: {findings}"
    assert match["occurrences"] >= 2, f"expected >=2 occurrences, got {match['occurrences']}"
    assert match["proposed_fix"], "expected a non-empty proposed_fix"

    report = gmj_self_reflect.render_report(findings)
    assert "gmj-pipeline-cap-raise-misuse" in report
    assert match["proposed_fix"] in report


def test_cap_raise_misuse_pattern_not_false_positive_on_normal_run() -> None:
    """The new predicate must not fire on ordinary, non-repeated command text."""
    entries = _read_jsonl(NORMAL_RUN)
    findings = gmj_self_reflect.classify_from_entries(entries)
    assert not any(f["pattern"] == "gmj-pipeline-cap-raise-misuse" for f in findings), (
        f"gmj-pipeline-cap-raise-misuse false-positived on normal-run fixture: {findings}"
    )


def test_both_patterns_surfaced_together_from_combined_logs() -> None:
    tmp = _copy_fixtures_to_tmp(WORKTREE_DRIFT, PYCACHE_FAILURE)
    findings = gmj_self_reflect.classify(tmp)
    patterns_found = {f["pattern"] for f in findings}
    assert "worktree-base-drift" in patterns_found, (
        f"worktree-base-drift missing from combined findings: {findings}"
    )
    assert "pycache-hook-log-pollution" in patterns_found, (
        f"pycache-hook-log-pollution missing from combined findings: {findings}"
    )

    report = gmj_self_reflect.render_report(findings)
    assert "worktree-base-drift" in report or "Worktree base drift" in report
    assert "pycache-hook-log-pollution" in report or "pycache" in report.lower()
    # Both proposed-fix sentences must be literally present in the rendered text, not
    # just the internal findings dict (so a rendering-only regression still fails).
    for finding in findings:
        if finding["pattern"] in ("worktree-base-drift", "pycache-hook-log-pollution"):
            assert finding["proposed_fix"] in report


def test_report_ends_with_status_action_safety_footer() -> None:
    report = gmj_self_reflect.render_report([])
    assert "STATUS: findings only" in report
    assert "ACTION: run `/gsd-self-reflect --apply`" in report
    assert "SAFETY: this tool has no fix-application code path at all" in report


def test_apply_flag_fails_loudly_at_cli_layer() -> None:
    rc = gmj_self_reflect.main(["--apply"])
    assert rc == 1, "passing --apply directly to this script must fail (D-07 boundary)"


def test_absent_log_dir_returns_empty_findings_not_error() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="self-reflect-absent-"))
    missing_dir = tmp / "does-not-exist"
    findings = gmj_self_reflect.classify(missing_dir)
    assert findings == []


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
