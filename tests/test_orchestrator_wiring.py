#!/usr/bin/env python3
"""Static wiring assertions for the rewired hub (.claude/agents/gmj-orchestrator.md).

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
HUB_PATH = AGENTS_DIR / "gmj-orchestrator.md"
PIPELINE_RUN_CMD = COMMANDS_DIR / "gmj-pipeline-run.md"

SPOKES = ["gmj-offer-scout", "gmj-artifact-composer", "gmj-truth-verifier", "gmj-fit-evaluator", "gmj-cv-generator"]
CONTROL_SCRIPTS = [
    "gmj_route.py",
    "gmj_check_offer.py",
    "gmj_record_gate.py",
    "gmj_check_cap.py",
    "gmj_map_feedback.py",
    "gmj_check_delivery.py",
    "gmj_pipeline_run.py",
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
    assert "gmj_check_offer.py" in hub, "gmj_check_offer.py not referenced in hub"
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


def test_hub_documents_per_type_state_isolation() -> None:
    # ARTF-01/04: the hub must state per-artifact-type state.json isolation explicitly —
    # each of the -cv/-cl/-ip derived-run_id suffixes, plus the "own ... state.json" phrasing.
    hub = _read(HUB_PATH)
    for suffix in ["-cv", "-cl", "-ip"]:
        assert suffix in hub, (
            f"hub does not name the per-type derived-run_id suffix {suffix!r} (ARTF-01/04)"
        )
    assert "own" in hub and "state.json" in hub, (
        "hub does not state per-artifact-type state.json isolation via 'own ... state.json' (ARTF-01/04)"
    )


def test_deliver_states_never_a_single_collapsed_boolean() -> None:
    # ARTF-01/04 (32-06 gap closure): Plan 32-04's own acceptance criteria required the
    # literal phrase "never a single collapsed boolean" to be a contiguous, grep-able
    # string in the hub persona. A prior markdown line-wrap split it across two physical
    # lines, so a naive single-line grep returned 0 despite 32-04-SUMMARY.md claiming 1.
    # This is a plain Python substring check (not multi-line-aware grep), which fails
    # correctly if the phrase is split by a line break and passes once it is contiguous.
    hub = _read(HUB_PATH)
    assert "never a single collapsed boolean" in hub, (
        "hub does not state the contiguous phrase 'never a single collapsed boolean' "
        "(ARTF-01/04) -- check for a markdown line-wrap splitting the phrase"
    )


def test_pipeline_run_documents_artifact_types_flag() -> None:
    # ARTF-03: the whole-flow command doc must document the --artifact-types flag and its
    # default artifact set.
    doc = _read(PIPELINE_RUN_CMD)
    assert "artifact-types" in doc, (
        "gmj-pipeline-run.md does not document the --artifact-types flag (ARTF-03)"
    )
    assert "cv,cover_letter,interview_prep" in doc, (
        "gmj-pipeline-run.md does not document the default artifact-types set 'cv,cover_letter,interview_prep' (ARTF-03)"
    )


def test_pipeline_commands_exist() -> None:
    # Plan 06 artifacts: the whole-flow command + six per-step wrappers.
    assert (COMMANDS_DIR / "gmj-pipeline-run.md").is_file(), "missing .claude/commands/gmj-pipeline-run.md"
    for step in ["scout", "freeze", "compose", "verify", "evaluate", "generate"]:
        path = COMMANDS_DIR / "gmj-pipeline" / f"{step}.md"
        assert path.is_file(), f"missing .claude/commands/gmj-pipeline/{step}.md"


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
