#!/usr/bin/env python3
"""Doc-lint for .claude/commands/gmj-batch.md (SELECT-01, SELECT-02 persona invariants).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_batch_persona.py``. This is a DOC-LINT: it loads the persona
markdown as TEXT and asserts the load-bearing clauses are present, each with a specific
sentinel so a deleted clause fails loudly. It is NOT an LLM green-gate — it never runs the
persona or judges output quality; it only proves the persona *states* the invariants that
keep the batch hub safe:

- reads the shortlist (SELECT-01),
- accepts multi-select (`1,3,5` / `all`) (SELECT-01),
- hub at top level / never nested — documents the forbidden call
  ``subagent_type: gmj-orchestrator`` as prohibited (T-12-06),
- drives the EXISTING per-offer pipeline loop (names ``gmj_route.py`` + ``gmj_check_delivery.py``)
  and the deterministic batch engine (``gmj_batch.py`` init/record-spec/mark/resume),
- thin → ``gmj-offer-scout`` re-field is the primary freeze source, real spec stamped
  post-freeze (``gmj-offer-scout`` + ``gmj_freeze_offer.py`` + ``gmj_batch.py record-spec``)
  (SELECT-02),
- per-(offer, artifact_type) gates never batched (T-12-02),
- frontmatter grants ``Task(*)`` and ``Bash(*)``.

Discipline: every assertion carries a message naming the missing sentinel, so a removed
clause fails with a readable reason (not a bare AssertionError).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA = REPO_ROOT / ".claude" / "commands" / "gmj-batch.md"


def _persona_text() -> str:
    if not PERSONA.is_file():
        raise AssertionError(f"persona not found: {PERSONA}")
    return PERSONA.read_text(encoding="utf-8")


def test_reads_shortlist() -> None:
    t = _persona_text()
    assert ".pipeline/shortlist.json" in t, "persona must read .pipeline/shortlist.json (SELECT-01)"


def test_accepts_multi_select() -> None:
    t = _persona_text()
    assert "1,3,5" in t, "persona must document a comma multi-select like '1,3,5' (SELECT-01)"
    assert "`all`" in t, "persona must document the 'all' selection token (SELECT-01)"


def test_hub_at_top_level_never_nested() -> None:
    t = _persona_text()
    # The forbidden-call sentinel must appear, documented as prohibited (never-nest rule).
    assert "subagent_type: gmj-orchestrator" in t, (
        "persona must state the forbidden call 'subagent_type: gmj-orchestrator' "
        "(never-nest-the-hub rule, T-12-06)"
    )
    assert "Never" in t or "never" in t, "persona must forbid nesting the hub (never-nest rule)"


def test_drives_existing_pipeline_per_offer() -> None:
    t = _persona_text()
    for sentinel in ("gmj_route.py", "gmj_check_delivery.py"):
        assert sentinel in t, f"persona must name the existing per-offer loop script {sentinel!r}"
    for sentinel in (
        "gmj_batch.py init",
        "gmj_batch.py record-spec",
        "gmj_batch.py mark",
        "gmj_batch.py resume",
    ):
        assert sentinel in t, f"persona must invoke the deterministic engine call {sentinel!r}"


def test_thin_offer_scout_refield_then_stamp() -> None:
    t = _persona_text()
    assert "gmj-offer-scout" in t, "persona must route thin offers through gmj-offer-scout re-field (SELECT-02)"
    assert "gmj_freeze_offer.py" in t, "persona must freeze via gmj_freeze_offer.py after re-field (SELECT-02)"
    assert "gmj_batch.py record-spec" in t, (
        "persona must stamp the real offer-spec into the manifest post-freeze "
        "(gmj_batch.py record-spec)"
    )


def test_per_offer_artifact_type_gate_never_batched() -> None:
    t = _persona_text()
    # Assert the exact isolation phrase the persona ships (T-12-02).
    assert "per-(offer, artifact_type)" in t, (
        "persona must state the per-(offer, artifact_type) gate isolation invariant (T-12-02)"
    )
    assert "gate_results" in t, (
        "persona must name the never-shared gate_results to make the isolation invariant concrete"
    )


def test_frontmatter_grants_task_and_bash() -> None:
    t = _persona_text()
    assert "Task(*)" in t, "frontmatter allowed-tools must grant Task(*) (hub holds Task)"
    assert "Bash(*)" in t, "frontmatter allowed-tools must grant Bash(*) (drives the control plane)"


def test_displays_ranked_fields_before_selection() -> None:
    t = _persona_text()
    for sentinel in ("title", "company", "salary", "mode", "score"):
        assert sentinel in t, (
            f"persona must name {sentinel!r} as a per-entry display field before selection (SELECT-05)"
        )


def test_narrowing_uses_ask_user_question() -> None:
    t = _persona_text()
    assert "AskUserQuestion" in t, "persona must present narrowing via AskUserQuestion (SELECT-06)"
    assert "top-3" in t, "persona must document the 'top-3' narrowing option (SELECT-06)"
    assert "top-5" in t, "persona must document the 'top-5' narrowing option (SELECT-06)"
    assert "custom" in t, "persona must document a 'custom indices' narrowing option (SELECT-06)"


def test_autonomous_bypasses_ask_user_question_with_top3() -> None:
    t = _persona_text()
    assert "autonomous" in t, "persona must document the autonomous-mode bypass (SELECT-06)"
    assert "--select top3" in t, (
        "persona must document the autonomous bypass calling 'gmj_batch.py init --select top3' directly"
    )


def test_frontmatter_grants_ask_user_question() -> None:
    t = _persona_text()
    assert "AskUserQuestion(*)" in t, (
        "frontmatter allowed-tools must grant AskUserQuestion(*) (bounded human narrowing prompt)"
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
