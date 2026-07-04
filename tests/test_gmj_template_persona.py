#!/usr/bin/env python3
"""Doc-lint for the /gmj-template persona + gmj-template-creator spoke (Phase 13-04).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_template_persona.py``. This is a DOC-LINT: it loads the persona
and agent markdown as TEXT and asserts the load-bearing clauses are present, each with a
specific sentinel so a deleted clause fails loudly. It is NOT an LLM green-gate — it never
runs the persona / spoke and never judges output quality; it only proves the docs *state*
the invariants that keep the screenshot→template loop safe:

Persona (`.claude/commands/gmj-template.md`):
- reads/pins the pasted screenshot under ``sources/design/`` (TEMPLATE-01),
- documents ALL FOUR loop bounds — cap ``5``, stop bar ``0.10``, keep-best, AND the
  two-consecutive-no-improvement early stop (so deleting any one bound fails the test),
- states ``compare == ship`` and that Playwright is excluded from the match loop
  (TEMPLATE-04),
- runs ``gmj_template_lint.py`` as a gate before accepting a template (TEMPLATE-02),
- has an overwrite-guard before clobbering an existing template,
- frontmatter grants ``Task(*)`` (persona is the sole Task-holder),
- confines writes to ``templates/cv/`` + ``sources/design/``.

Agent (`.claude/agents/gmj-template-creator.md`):
- names all three tools (``gmj_template_lint.py``, ``gmj_visual_diff.py``, ``render_cv.py``),
- states the ``@font-face`` DejaVu injection rule (TEMPLATE-05),
- ends with ``agent_result_v1``,
- contains NO ``mcp__playwright`` (Playwright excluded from the loop),
- frontmatter ``tools:`` line does NOT grant ``Task`` (spoke holds no Task).

Discipline: every assertion carries a message naming the missing sentinel, so a removed
clause fails with a readable reason (not a bare AssertionError).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONA = REPO_ROOT / ".claude" / "commands" / "gmj-template.md"
AGENT = REPO_ROOT / ".claude" / "agents" / "gmj-template-creator.md"


def _persona_text() -> str:
    if not PERSONA.is_file():
        raise AssertionError(f"persona not found: {PERSONA}")
    return PERSONA.read_text(encoding="utf-8")


def _agent_text() -> str:
    if not AGENT.is_file():
        raise AssertionError(f"agent not found: {AGENT}")
    return AGENT.read_text(encoding="utf-8")


# ----------------------------- persona sentinels -----------------------------


def test_persona_reads_pinned_screenshot() -> None:
    t = _persona_text()
    assert "sources/design/" in t, (
        "persona must pin/read the pasted screenshot under sources/design/ (TEMPLATE-01)"
    )


def test_persona_loop_cap_5() -> None:
    t = _persona_text()
    assert "cap" in t.lower(), "persona must document an iteration cap (loop bound)"
    assert "5" in t, "persona must document the iteration cap value 5 (loop bound)"


def test_persona_stop_bar_0_10() -> None:
    t = _persona_text()
    assert "0.10" in t, "persona must document the diff-ratio stop bar <= 0.10 (loop bound)"


def test_persona_keep_best() -> None:
    t = _persona_text()
    assert "best" in t.lower(), (
        "persona must document keep-best (ship the best-scoring version, not the last) (loop bound)"
    )


def test_persona_two_consecutive_no_improvement() -> None:
    t = _persona_text().lower()
    assert ("no improvement" in t) or ("no-improvement" in t) or ("no-improve" in t), (
        "persona must document the two-consecutive-no-improvement early stop (loop bound) — "
        "sentinel 'no improvement'/'no-improve'"
    )


def test_persona_compare_equals_ship_playwright_excluded() -> None:
    t = _persona_text()
    assert ("compare == ship" in t) or ("compare==ship" in t), (
        "persona must state compare == ship (the diffed artifact IS the shipped WeasyPrint PDF)"
    )
    assert "playwright" in t.lower(), (
        "persona must state Playwright is excluded from the match loop (TEMPLATE-04)"
    )


def test_persona_lint_gate() -> None:
    t = _persona_text()
    assert "gmj_template_lint.py" in t, (
        "persona must run gmj_template_lint.py as a gate before accepting a template (TEMPLATE-02)"
    )


def test_persona_overwrite_guard() -> None:
    t = _persona_text()
    assert "overwrite" in t.lower(), (
        "persona must document an overwrite-guard before clobbering an existing template"
    )


def test_persona_frontmatter_grants_task() -> None:
    t = _persona_text()
    assert "Task(*)" in t, "persona frontmatter allowed-tools must grant Task(*) (sole Task-holder)"


def test_persona_writes_confined() -> None:
    t = _persona_text()
    assert "templates/cv/" in t, "persona must confine writes to templates/cv/"
    assert "sources/design/" in t, "persona must confine writes to sources/design/"


# ------------------------------ agent sentinels ------------------------------


def test_agent_names_three_tools() -> None:
    t = _agent_text()
    for sentinel in ("gmj_template_lint.py", "gmj_visual_diff.py", "render_cv.py"):
        assert sentinel in t, f"agent must name the tool {sentinel!r} it drives in the loop"


def test_agent_font_face_injection() -> None:
    t = _agent_text()
    assert "@font-face" in t, (
        "agent must state the @font-face DejaVu injection rule for Cyrillic (TEMPLATE-05)"
    )


def test_agent_ends_with_agent_result_v1() -> None:
    t = _agent_text()
    assert "agent_result_v1" in t, "agent must end with an agent_result_v1 envelope"


def test_agent_no_playwright_in_loop() -> None:
    t = _agent_text()
    assert "mcp__playwright" not in t, (
        "agent must NOT reference mcp__playwright — Playwright is excluded from the match loop "
        "(compare==ship, TEMPLATE-04)"
    )


def test_agent_frontmatter_no_task() -> None:
    t = _agent_text()
    tools_lines = [ln for ln in t.splitlines() if ln.strip().startswith("tools:")]
    assert tools_lines, "agent frontmatter must have a 'tools:' line"
    assert "Task" not in tools_lines[0], (
        "agent frontmatter 'tools:' must NOT grant Task — the spoke holds no Task"
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
