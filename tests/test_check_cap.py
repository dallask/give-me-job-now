#!/usr/bin/env python3
"""Plain-python3 tests for scripts/pipeline/gmj_check_cap.py (EXEC-03).

Proves the retry loop honestly hard-stops at the FROZEN cap: below the cap the
guard prints ``continue`` and exits 0; at or over the cap it emits a distinct
EXHAUSTED report (naming the failing artifact + reason) and exits nonzero — with
NO "deliver best-effort" branch anywhere (Pitfall 2, T-07-12). The cap is read
from ``state.retry_cap`` (frozen), never from config; a bool/missing cap is
rejected (T-07-14). No pytest — run with ``python3 tests/test_check_cap.py``.

PIPE-07/PIPE-08 (phase 41-04): the EXHAUSTED report also carries a
``failure_class`` (``narrow``/``systemic``) heuristic classification, and the
FIRST time an offer/type reaches cap (current == cap, no prior raise), the
script emits a distinct ``propose_raise`` status (exit 2) instead of the final
report — bounded to exactly one raise per CONTEXT.md's "ONE bounded cap raise"
decision, tracked by the caller-supplied ``--raised`` flag.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_check_cap.py"


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


def test_below_cap_continues() -> None:
    state_path = _seed_state(
        {"retry_cap": 3, "retry_counts": {"acme": {"cv": 1}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode == 0, f"below-cap must exit 0: {result.stderr}"
    assert result.stdout.strip() == "continue", (
        f"below-cap must print 'continue': {result.stdout!r}"
    )


def test_missing_counter_treated_as_zero_continues() -> None:
    # No retry_counts entry for this (offer,type) → treat count as 0 → below cap.
    state_path = _seed_state({"retry_cap": 2})
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cover_letter",
    )
    assert result.returncode == 0, f"missing counter → 0 → continue: {result.stderr}"
    assert result.stdout.strip() == "continue", result.stdout


def test_at_cap_emits_exhausted_report() -> None:
    # At cap WITH --raised (this offer/type already used its one bounded
    # raise) → the final EXHAUSTED report, not propose_raise. The bare
    # first-time-at-cap case (no --raised) is covered separately by
    # test_first_exhaustion_emits_propose_raise_not_final_report.
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"cv": 2}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--reason", "truth gate failed on claim X",
        "--raised",
    )
    assert result.returncode != 0, "at-cap must exit nonzero (hard stop)"
    report = json.loads(result.stdout)
    assert report["status"] == "exhausted", f"expected exhausted: {report!r}"
    assert report["artifact"] == "cv", f"report must name artifact: {report!r}"
    assert report["reason"] == "truth gate failed on claim X", (
        f"report must carry the failing reason: {report!r}"
    )


def test_over_cap_emits_exhausted_report() -> None:
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"interview_prep": 5}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "interview_prep",
    )
    assert result.returncode != 0, "over-cap must exit nonzero"
    report = json.loads(result.stdout)
    assert report["status"] == "exhausted", report
    assert report["artifact"] == "interview_prep", report
    # A default reason is present even when --reason is omitted.
    assert isinstance(report["reason"], str) and report["reason"], report


def test_no_deliver_or_best_effort_signal_anywhere() -> None:
    # An exhausted run must NEVER emit a passing/deliver signal (ship-last defense).
    state_path = _seed_state(
        {"retry_cap": 1, "retry_counts": {"acme": {"cv": 1}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "deliver" not in combined, "no deliver signal on exhaustion"
    assert "best-effort" not in combined and "best effort" not in combined, (
        "no best-effort signal on exhaustion"
    )
    assert "continue" not in combined, "exhausted run must not signal continue"


def test_missing_cap_rejected() -> None:
    state_path = _seed_state({"retry_counts": {"acme": {"cv": 0}}})
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode == 1, "missing retry_cap must be rejected (exit 1)"
    assert result.stdout.strip() == "", "no stdout token on error"
    assert result.stderr.strip(), "error must be reported to stderr"


def test_bool_cap_rejected() -> None:
    # bool is a subclass of int — must be rejected explicitly (T-07-14).
    state_path = _seed_state(
        {"retry_cap": True, "retry_counts": {"acme": {"cv": 0}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode == 1, "bool retry_cap must be rejected (exit 1)"
    assert result.stderr.strip(), "error must be reported to stderr"


def test_invalid_state_json_rejected() -> None:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text("{not valid json", encoding="utf-8")
    result = _run(
        "--state", str(tmp),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode == 1, "invalid JSON must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on malformed state"


def test_missing_state_file_rejected() -> None:
    result = _run(
        "--state", "/nonexistent/state.json",
        "--offer-slug", "acme",
        "--artifact-type", "cv",
    )
    assert result.returncode == 1, "missing state file must exit 1"
    assert "Traceback" not in result.stderr


def test_invalid_artifact_type_rejected() -> None:
    state_path = _seed_state({"retry_cap": 2})
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "resume",
    )
    assert result.returncode != 0, "off-enum artifact_type rejected by argparse choices"


def test_first_exhaustion_emits_propose_raise_not_final_report() -> None:
    # current == cap, no --raised flag → FIRST time this exact count reaches
    # cap → propose_raise (exit 2), NOT the final flat EXHAUSTED report.
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"cv": 2}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--reason", "gate failed",
    )
    assert result.returncode == 2, (
        f"first exhaustion must exit 2 (propose_raise), got {result.returncode}: {result.stderr}"
    )
    report = json.loads(result.stdout)
    assert report == {
        "status": "propose_raise",
        "artifact": "cv",
        "current_cap": 2,
        "proposed_cap": 3,
        "reason": "gate failed",
    }, report


def test_second_exhaustion_after_raise_emits_final_exhausted_no_further_raise() -> None:
    # Cap already raised once (2 -> 3); caller passes --raised to signal this
    # offer/type already used its one bounded raise → final EXHAUSTED (exit 1),
    # NEVER a second propose_raise.
    state_path = _seed_state(
        {"retry_cap": 3, "retry_counts": {"acme": {"cv": 3}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--reason", "gate failed again",
        "--raised",
    )
    assert result.returncode == 1, (
        f"second exhaustion (already raised) must exit 1 (final), got {result.returncode}"
    )
    report = json.loads(result.stdout)
    assert report["status"] == "exhausted", report
    assert report["artifact"] == "cv", report
    assert "failure_class" in report, report


def test_exhausted_report_classifies_systemic_vs_narrow() -> None:
    # Narrow: a reason implying a single failing claim / claim-index pattern.
    state_path = _seed_state(
        {"retry_cap": 1, "retry_counts": {"acme": {"cv": 1}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--reason", "single claim failed: claims[3] unresolved_span",
        "--raised",
    )
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["failure_class"] == "narrow", report

    # Systemic: generic/empty reason implying multiple/unclear failing claims.
    state_path2 = _seed_state(
        {"retry_cap": 1, "retry_counts": {"acme": {"cover_letter": 1}}}
    )
    result2 = _run(
        "--state", str(state_path2),
        "--offer-slug", "acme",
        "--artifact-type", "cover_letter",
        "--reason", "multiple claims fabricated across the draft",
        "--raised",
    )
    assert result2.returncode == 1, result2.stderr
    report2 = json.loads(result2.stdout)
    assert report2["failure_class"] == "systemic", report2


def test_over_cap_without_raise_marker_still_treated_as_final_exhausted() -> None:
    # current > cap (already over, not exactly at cap) — never emits
    # propose_raise (which only fires exactly AT the first-reached cap); goes
    # straight to the final EXHAUSTED report. Preserves
    # test_over_cap_emits_exhausted_report's existing contract even without
    # --raised.
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"interview_prep": 5}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "interview_prep",
    )
    assert result.returncode == 1, "over-cap must exit 1 (final), never propose_raise"
    report = json.loads(result.stdout)
    assert report["status"] == "exhausted", report
    assert "failure_class" in report, report


def test_new_cap_atomically_bumps_retry_cap_preserving_siblings() -> None:
    # PIPEFIX-01: --new-cap writes the bumped retry_cap back to disk, preserving
    # every sibling key (e.g. retry_counts) byte-for-byte in shape.
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"cv": 2}}}
    )
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--new-cap", "3",
        "--raised",
    )
    assert result.returncode == 0, f"new-cap bump then below-bumped-cap must exit 0: {result.stderr}"
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["retry_cap"] == 3, f"retry_cap must be bumped on disk: {on_disk!r}"
    assert on_disk["retry_counts"] == {"acme": {"cv": 2}}, (
        f"sibling key retry_counts must be preserved: {on_disk!r}"
    )


def test_new_cap_rejects_malformed_or_missing_existing_cap() -> None:
    # A malformed (bool) or missing existing retry_cap is rejected the same way
    # the read-path guard rejects it — before any write happens.
    state_path = _seed_state({"retry_cap": True, "retry_counts": {"acme": {"cv": 0}}})
    result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--new-cap", "3",
    )
    assert result.returncode == 1, "bool existing retry_cap must be rejected (exit 1)"
    assert result.stderr.strip(), "error must be reported to stderr"
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["retry_cap"] is True, "no partial write on rejection"

    state_path2 = _seed_state({"retry_counts": {"acme": {"cv": 0}}})
    result2 = _run(
        "--state", str(state_path2),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--new-cap", "3",
    )
    assert result2.returncode == 1, "missing existing retry_cap must be rejected (exit 1)"
    assert result2.stderr.strip(), "error must be reported to stderr"

    # Negative new-cap value is also rejected, no write.
    state_path3 = _seed_state({"retry_cap": 2, "retry_counts": {"acme": {"cv": 2}}})
    result3 = _run(
        "--state", str(state_path3),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--new-cap", "-1",
    )
    assert result3.returncode == 1, "negative --new-cap must be rejected (exit 1)"
    assert result3.stderr.strip(), "error must be reported to stderr"
    on_disk3 = json.loads(state_path3.read_text(encoding="utf-8"))
    assert on_disk3["retry_cap"] == 2, "no partial write on negative --new-cap rejection"


def test_full_bump_then_raised_sequence_prevents_false_exhausted() -> None:
    # PIPEFIX-01 regression: seed retry_cap 2, retry_counts.acme.cv = 2 (AT cap).
    # First prove the OLD (bug) sequence: --raised WITHOUT bumping the cap first
    # still reproduces the false EXHAUSTED verdict (proves the bug is real and
    # this regression test would have caught it).
    state_path = _seed_state(
        {"retry_cap": 2, "retry_counts": {"acme": {"cv": 2}}}
    )
    old_result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--raised",
    )
    assert old_result.returncode == 1, (
        "OLD unbumped --raised sequence must still reproduce the false EXHAUSTED bug"
    )
    old_report = json.loads(old_result.stdout)
    assert old_report["status"] == "exhausted", old_report

    # Now apply the FIXED sequence: bump the cap via --new-cap first (a separate
    # invocation, matching the orchestrator doc's prescribed bump-then-raised
    # order), THEN re-invoke the SAME --raised call.
    bump_result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--new-cap", "3",
    )
    assert bump_result.returncode == 0, f"cap bump must succeed: {bump_result.stderr}"
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["retry_cap"] == 3, on_disk

    fixed_result = _run(
        "--state", str(state_path),
        "--offer-slug", "acme",
        "--artifact-type", "cv",
        "--raised",
    )
    assert fixed_result.returncode == 0, (
        f"fixed bump-then-raised sequence must exit 0 (continue), not false-exhausted: "
        f"{fixed_result.stderr}"
    )
    assert fixed_result.stdout.strip() == "continue", fixed_result.stdout


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
