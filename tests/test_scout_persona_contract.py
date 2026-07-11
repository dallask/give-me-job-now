#!/usr/bin/env python3
"""Doc-lint contract for SCOUT-01 (job-seeker reframe) and SCOUT-03 (hub per-board fan-out).

Runnable as a plain assertion script (no pytest dependency), mirroring
``tests/test_freeze_offer.py``. Locks the DURABLE contract of the two agent docs — live
tone / ranking quality stays UAT-deferred (11-VALIDATION.md); there is no circular LLM
green-gate. Asserts over ``.claude/agents/gmj-offer-scout.md`` and
``.claude/agents/gmj-orchestrator.md``:

- gmj-offer-scout stays a NON-SPAWNING worker ("Does not spawn subagents" + the Rules line
  forbidding ``Task``) — T-11-08,
- gmj-offer-scout board search uses JOB-SEEKER framing (no plural recruiter token, no
  ``found <n> candidates`` phrasing) — SCOUT-01,
- the hub fans out ONE gmj-offer-scout Task PER BOARD in a single turn — SCOUT-03,
- the hub invokes ``gmj_merge_shortlists.py`` as the deterministic merge authority — SCOUT-03,
- the hub keeps the single-Task-holder / spokes-never-spawn-spokes invariant — T-11-08.

The recruiter needle literals (the grep targets) live in THIS file ONLY — they must never
be written into the agent docs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OFFER_SCOUT = REPO_ROOT / ".claude" / "agents" / "gmj-offer-scout.md"
ORCHESTRATOR = REPO_ROOT / ".claude" / "agents" / "gmj-orchestrator.md"
ARTIFACT_COMPOSER = REPO_ROOT / ".claude" / "agents" / "gmj-artifact-composer.md"
FIT_EVALUATOR = REPO_ROOT / ".claude" / "agents" / "gmj-fit-evaluator.md"
TRUTH_VERIFIER = REPO_ROOT / ".claude" / "agents" / "gmj-truth-verifier.md"
CV_GENERATOR = REPO_ROOT / ".claude" / "agents" / "gmj-cv-generator.md"

# Recruiter needle literals — kept in the test only, never in the agent docs.
RECRUITER_TOKEN = "candidates"
RECRUITER_PHRASE = re.compile(r"found\s+\S+\s+candidates", re.IGNORECASE)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing agent doc: {path}"
    return path.read_text(encoding="utf-8")


def test_offer_scout_non_spawning() -> None:
    t = _read(OFFER_SCOUT)
    assert "Does not spawn subagents" in t, (
        "gmj-offer-scout.md must keep the front-matter 'Does not spawn subagents' invariant "
        "(non-spawning worker; hub owns fan-out) — T-11-08"
    )
    assert "Do **not** call `Task`" in t, (
        "gmj-offer-scout.md must keep the Rules line 'Do **not** call `Task`.' — T-11-08"
    )


def test_offer_scout_jobseeker_framing() -> None:
    t = _read(OFFER_SCOUT)
    assert RECRUITER_TOKEN not in t.lower(), (
        f"gmj-offer-scout.md must not contain the plural recruiter token '{RECRUITER_TOKEN}' "
        "(job-seeker framing, SCOUT-01)"
    )
    assert not RECRUITER_PHRASE.search(t), (
        "gmj-offer-scout.md must not use recruiter phrasing 'found <n> candidates' (SCOUT-01)"
    )


def test_hub_fans_out_per_board() -> None:
    t = _read(ORCHESTRATOR)
    tl = t.lower()
    assert "per board" in tl, (
        "gmj-orchestrator.md must document per-board fan-out ('per board') — SCOUT-03"
    )
    assert "gmj-offer-scout" in tl, (
        "gmj-orchestrator.md must name gmj-offer-scout as the per-board worker — SCOUT-03"
    )


def test_hub_invokes_merge() -> None:
    t = _read(ORCHESTRATOR)
    assert "gmj_merge_shortlists.py" in t, (
        "gmj-orchestrator.md must invoke gmj_merge_shortlists.py as the deterministic "
        "ranking/dedup/scope authority — SCOUT-03"
    )


def test_hub_keeps_single_task_holder() -> None:
    t = _read(ORCHESTRATOR)
    tl = t.lower()
    assert "only you" in tl and "call `task`" in tl, (
        "gmj-orchestrator.md must keep 'Only you call `Task`' single-holder invariant — T-11-08"
    )
    assert "spokes never spawn spokes" in tl or "never spawn other spokes" in tl, (
        "gmj-orchestrator.md must keep the spokes-never-spawn-spokes invariant — T-11-08"
    )


def test_all_collective_agents_have_final_output_mandatory_section() -> None:
    files = [
        (OFFER_SCOUT, "gmj-offer-scout.md"),
        (ARTIFACT_COMPOSER, "gmj-artifact-composer.md"),
        (FIT_EVALUATOR, "gmj-fit-evaluator.md"),
        (TRUTH_VERIFIER, "gmj-truth-verifier.md"),
        (CV_GENERATOR, "gmj-cv-generator.md"),
    ]
    for path, label in files:
        t = _read(path)
        assert "Final Output" in t, (
            f"{label} must carry the hardened 'Final Output — MANDATORY' closing section "
            "(GUIDE-01, D-01/D-02/D-03) — the uniform envelope-emission hardening"
        )


def test_offer_scout_documents_shortlist_as_sole_canonical_key() -> None:
    t = _read(OFFER_SCOUT)
    assert "safety net" in t.lower(), (
        "gmj-offer-scout.md must document the D-06 emphasis: gmj_merge_shortlists.py's "
        "'entries' alias is a safety net, not a second valid canonical key"
    )
    assert "shortlist" in t, (
        "gmj-offer-scout.md must still document 'shortlist' as the canonical per-board "
        "top-level key name (GUIDE-02, D-06)"
    )


def test_orchestrator_documents_hook_error_retry_protocol() -> None:
    # GUIDE-01 gap closure (04-04-PLAN.md): locks the bounded HOOK_ERROR contract-violation
    # retry protocol into gmj-orchestrator.md so it cannot silently regress.
    t = _read(ORCHESTRATOR)
    assert "HOOK_ERROR" in t, (
        "gmj-orchestrator.md must document the HOOK_ERROR contract-violation retry trigger "
        "(GUIDE-01, 04-04-PLAN.md gap closure)"
    )
    assert "gmj_check_envelope_retry.py" in t, (
        "gmj-orchestrator.md must name gmj_check_envelope_retry.py as the deterministic "
        "bounded-retry verdict script (GUIDE-01, 04-04-PLAN.md gap closure)"
    )
    assert "retry_exhausted" in t, (
        "gmj-orchestrator.md must document the 'retry_exhausted' hard-stop branch, not just "
        "the happy retry path (GUIDE-01, 04-04-PLAN.md gap closure)"
    )
    tl = t.lower()
    assert "only you" in tl and "call `task`" in tl, (
        "gmj-orchestrator.md must keep the single-Task-holder invariant alongside the new "
        "HOOK_ERROR retry protocol (T-11-08, 04-04-PLAN.md gap closure)"
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
