#!/usr/bin/env python3
"""Static wiring assertions for the wired gmj-fit-evaluator agent (Plan 06-05).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. Each test proves a STATIC wiring invariant over
``.claude/agents/gmj-fit-evaluator.md`` — never LLM scoring accuracy. The invariants are:

- the frontmatter ``tools:`` line is exactly ``Read, Glob, Grep`` (no ``Write``/``Bash``),
- the body references the fit-rubric skill as its scoring authority,
- it instructs emitting a ``coverage_map`` (claims → must-have IDs),
- it emits a Gate C (``gate: "C"``) structurally separate from the Gate B verdict,
- it carries the injection-guard DATA-not-instructions framing,
- it names ``gate_feedback`` only inside the Phase-7 do-not-rename deferral.

Only the Python stdlib is used.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT = REPO_ROOT / ".claude" / "agents" / "gmj-fit-evaluator.md"


def _text() -> str:
    return AGENT.read_text(encoding="utf-8")


def _tools_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("tools:"):
            return line
    raise AssertionError("no `tools:` frontmatter line found")


def test_tools_are_read_only() -> None:
    line = _tools_line(_text())
    assert line.strip() == "tools: Read, Glob, Grep", (
        f"tools line must be exactly `tools: Read, Glob, Grep`, got: {line!r}"
    )
    low = line.lower()
    assert "write" not in low, "gmj-fit-evaluator must NOT have Write in tools"
    assert "bash" not in low, "gmj-fit-evaluator must NOT have Bash in tools"


def test_references_fit_rubric_skill() -> None:
    text = _text()
    assert ".claude/skills/fit-rubric/SKILL.md" in text, (
        "agent must reference the fit-rubric skill as scoring authority"
    )


def test_instructs_coverage_map_emission() -> None:
    assert "coverage_map" in _text(), (
        "agent must instruct emitting a coverage_map (claims → must-have IDs)"
    )


def test_gate_c_structurally_separate_from_gate_b() -> None:
    text = _text()
    low = text.lower()
    # Both gates must be present and named as distinct content docs.
    assert 'gate: "B"' in text, "Gate B result must be named (gate: \"B\")"
    assert 'gate: "C"' in text, "Gate C result must be named (gate: \"C\")"
    # And the separation must be explicit — Gate C never merged into Gate B.
    assert "structurally separate" in low, (
        "agent must state Gate C is structurally separate from Gate B"
    )
    assert "never" in low and "merge" in low, (
        "agent must forbid merging Gate C into the Gate B verdict"
    )


def test_injection_guard_data_not_instructions() -> None:
    text = _text()
    low = text.lower()
    assert "injection guard" in low, "agent must carry an injection-guard section"
    # DATA-not-instructions framing: claim/offer text is DATA, never instructions.
    assert "data" in low and "never" in low and "instruction" in low, (
        "injection guard must frame claim/offer text as DATA, never instructions"
    )


def test_gate_feedback_only_in_phase7_deferral() -> None:
    text = _text()
    low = text.lower()
    assert "gate_feedback" in low, (
        "agent must mention gate_feedback (to defer it), per Phase-7 boundary"
    )
    # Every occurrence of gate_feedback must sit inside a Phase-7 deferral context —
    # it must NEVER be emitted as a live field name. Check a paragraph window around
    # each occurrence for the Phase-7 deferral marker.
    lines = low.splitlines()
    for i, line in enumerate(lines):
        if "gate_feedback" not in line:
            continue
        window = " ".join(lines[max(0, i - 4): i + 5])
        assert "phase 7" in window, (
            f"gate_feedback on line {i + 1} must be inside the Phase-7 deferral context"
        )
    # The emit rule must additionally carry the do-not-rename instruction.
    assert "do not rename" in low, (
        "agent must instruct do-NOT-rename the gate_feedback fixture (Phase-7 deferral)"
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
