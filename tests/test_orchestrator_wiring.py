#!/usr/bin/env python3
"""Static wiring assertions for the rewired hub (.claude/agents/vacancy-orchestrator.md).

Runnable as a plain assertion script (no pytest dependency), mirroring
tests/test_route.py. Every assertion is a file read — no live Task, no subprocess
spoke run (live multi-agent convergence is Phase-8 UAT). This test locks the
Phase-7 hub rewire: the new 5-spoke roster + the deterministic control scripts are
referenced, check_offer runs before dispatch, the hub holds Task AND Bash, the
retired legacy tokens are gone, and no spoke frontmatter holds Task.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
HUB_PATH = AGENTS_DIR / "vacancy-orchestrator.md"

SPOKES = ["offer-scout", "artifact-composer", "truth-verifier", "fit-evaluator", "cv-generator"]
CONTROL_SCRIPTS = [
    "route.py",
    "check_offer.py",
    "record_gate.py",
    "check_cap.py",
    "map_feedback.py",
    "check_delivery.py",
]
# Retired legacy tokens — the old cv-* review/enhance roster, the deliverable gate,
# the fast-path label, the enhance-cycle constant, and the LLM router — must be ABSENT
# from the rewired hub body (T-07-23). Built as data so the test file itself is the
# authoritative forbidden list.
FORBIDDEN_TOKENS = [
    "cv-reviewer",
    "cv-enhancer",
    "cv-deliverable-gate",
    "FAST_PATH",
    "MAX_ENHANCE_CYCLES",
    "vacancy-router",
]


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file missing: {path}"
    return path.read_text(encoding="utf-8")


def _frontmatter_tools(text: str) -> str:
    """Return the raw `tools:` line value from a YAML frontmatter block."""
    match = re.search(r"^tools:\s*(.+)$", text, flags=re.MULTILINE)
    assert match, "no `tools:` line found in frontmatter"
    return match.group(1)


def test_hub_names_the_new_roster() -> None:
    hub = _read(HUB_PATH)
    for spoke in SPOKES:
        assert spoke in hub, f"hub does not reference new-roster spoke: {spoke}"


def test_hub_references_all_control_scripts() -> None:
    hub = _read(HUB_PATH)
    for script in CONTROL_SCRIPTS:
        assert script in hub, f"hub does not reference control script: {script}"


def test_check_offer_runs_before_dispatch() -> None:
    hub = _read(HUB_PATH)
    assert "check_offer.py" in hub, "check_offer.py not referenced in hub"
    # The doc must tie check_offer to running before each dispatch (INTAKE-02).
    assert "before each" in hub.lower() or "before every" in hub.lower(), (
        "hub does not state check_offer runs before each/every spoke dispatch"
    )


def test_hub_tools_include_task_and_bash() -> None:
    tools = _frontmatter_tools(_read(HUB_PATH))
    assert "Task" in tools, f"hub tools must include Task; got: {tools}"
    assert "Bash" in tools, f"hub tools must include Bash; got: {tools}"


def test_legacy_tokens_absent_from_hub() -> None:
    hub = _read(HUB_PATH)
    for token in FORBIDDEN_TOKENS:
        assert hub.count(token) == 0, f"retired legacy token still present in hub: {token}"


def test_only_hub_holds_task() -> None:
    # Task-only invariant (Pitfall 5 / T-07-20): the hub's tools list Task; no spoke's does.
    hub_tools = _frontmatter_tools(_read(HUB_PATH))
    assert "Task" in hub_tools, "hub frontmatter tools must include Task"
    for spoke in SPOKES:
        spoke_tools = _frontmatter_tools(_read(AGENTS_DIR / f"{spoke}.md"))
        tool_set = {t.strip() for t in spoke_tools.split(",")}
        assert "Task" not in tool_set, f"spoke {spoke} must NOT hold Task; got: {spoke_tools}"


def test_pipeline_commands_exist() -> None:
    # Plan 06 artifacts: the whole-flow command + six per-step wrappers.
    assert (COMMANDS_DIR / "pipeline-run.md").is_file(), "missing .claude/commands/pipeline-run.md"
    for step in ["scout", "freeze", "compose", "verify", "evaluate", "generate"]:
        path = COMMANDS_DIR / "pipeline" / f"{step}.md"
        assert path.is_file(), f"missing .claude/commands/pipeline/{step}.md"


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
