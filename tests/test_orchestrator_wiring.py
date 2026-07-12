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
BATCH_CMD = COMMANDS_DIR / "gmj-batch.md"

SPOKES = ["gmj-offer-scout", "gmj-artifact-composer", "gmj-truth-verifier", "gmj-fit-evaluator", "gmj-cv-generator"]
CONTROL_SCRIPTS = [
    "gmj_route.py",
    "gmj_check_offer.py",
    "gmj_record_gate.py",
    "gmj_check_cap.py",
    "gmj_map_feedback.py",
    "gmj_check_delivery.py",
    "gmj_pipeline_run.py",
    "gmj_dispatch_cap.py",
    "gmj_check_offer_liveness.py",
    "gmj_check_dependencies.py",
    "gmj_check_leftover_artifacts.py",
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


def test_hub_documents_bounded_concurrent_dispatch() -> None:
    # CONC-06: the hub must document the bounded concurrent-offer dispatch loop as a
    # subsection of "Parallel fan-out, sequential gates", placed after "Board-search
    # fan-out" -- never as a disconnected new heading elsewhere in the file.
    hub = _read(HUB_PATH)
    assert "### Bounded concurrent-offer dispatch" in hub, (
        "hub does not document the bounded concurrent-offer dispatch subsection (CONC-06)"
    )
    assert hub.index("### Bounded concurrent-offer dispatch") > hub.index(
        "### Board-search fan-out"
    ), "bounded concurrent-offer dispatch subsection must come after Board-search fan-out"
    assert "gmj_dispatch_cap.py" in hub, "hub does not name gmj_dispatch_cap.py (CONC-06)"


def test_batch_command_no_longer_defers_parallelism() -> None:
    # CONC-06: gmj-batch.md must no longer claim parallelism is deferred/single-threaded-only.
    # <!-- planner-discipline-allow: parallel deferred -->
    batch_doc = _read(BATCH_CMD)
    assert "parallel deferred" not in batch_doc, (
        "gmj-batch.md still claims parallel dispatch is deferred (CONC-06)"
    )
    assert "max-parallel-offers" in batch_doc, (
        "gmj-batch.md does not document --max-parallel-offers (CONC-06)"
    )


def test_no_nested_orchestrator_task_recommended() -> None:
    # T-35-09: every literal "Task(gmj-orchestrator)" occurrence in either doc must sit
    # inside a prohibiting sentence (contains "never" on the same line), never a
    # recommending one.
    for path in (HUB_PATH, BATCH_CMD):
        text = _read(path)
        for line in text.splitlines():
            if "Task(gmj-orchestrator)" in line:
                assert "never" in line.lower(), (
                    f"{path.name}: line recommends Task(gmj-orchestrator) without 'never': {line!r}"
                )


def test_bounded_dispatch_states_completeness_backstop() -> None:
    # T-01-04/T-01-05: the hub must state the SAME mandatory-resume-before-declaring-done
    # invariant as gmj-batch.md's step 6, worded consistently (identical sentinel substring),
    # positioned after "### Bounded concurrent-offer dispatch" and after step 4's "Greedy
    # refill." text, and before "## Result" -- mirroring
    # test_hub_documents_bounded_concurrent_dispatch's .index()-ordering style.
    hub = _read(HUB_PATH)
    sentinel = "the hub MUST loop back to step 4"
    assert sentinel in hub, (
        f"hub does not state the mandatory-backstop sentinel {sentinel!r} (T-01-04)"
    )
    # Also assert the identical sentinel is present in gmj-batch.md, proving both docs are
    # worded consistently.
    batch_doc = _read(BATCH_CMD)
    assert sentinel in batch_doc, (
        f"gmj-batch.md does not state the same mandatory-backstop sentinel {sentinel!r} "
        "as the hub -- both docs must state the identical invariant"
    )
    dispatch_idx = hub.index("### Bounded concurrent-offer dispatch")
    greedy_refill_idx = hub.index("Greedy refill.")
    sentinel_idx = hub.index(sentinel)
    result_idx = hub.index("## Result")
    assert dispatch_idx < greedy_refill_idx < sentinel_idx < result_idx, (
        "completeness-backstop sentinel must be positioned after '### Bounded concurrent-offer "
        "dispatch', after step 4's 'Greedy refill.' text, and before '## Result'"
    )
    subsection = hub[dispatch_idx:result_idx]
    assert "gmj_batch.py resume" in subsection, (
        "hub's Bounded concurrent-offer dispatch subsection must name gmj_batch.py resume (T-01-04)"
    )
    assert "gmj_batch.py status" in subsection, (
        "hub's Bounded concurrent-offer dispatch subsection must name gmj_batch.py status (T-01-04)"
    )


def test_hub_documents_preflight_liveness_check() -> None:
    # GUIDE-03: the hub must document the pre-freeze liveness check, advisory-only.
    hub = _read(HUB_PATH)
    assert "gmj_check_offer_liveness.py" in hub, (
        "hub does not reference gmj_check_offer_liveness.py (GUIDE-03)"
    )
    assert "before freezing" in hub.lower(), (
        "hub does not state the liveness check runs before freezing (GUIDE-03)"
    )
    assert "advisory" in hub.lower(), (
        "hub does not mention 'advisory' near the liveness check (GUIDE-03)"
    )


def test_hub_documents_preflight_dependency_check() -> None:
    # GUIDE-04: the hub must document the pre-dispatch dependency check inside init_run.
    hub = _read(HUB_PATH)
    assert "gmj_check_dependencies.py" in hub, (
        "hub does not reference gmj_check_dependencies.py (GUIDE-04)"
    )
    assert (
        "before the first spoke dispatch" in hub.lower()
        or "before the first `task()`" in hub.lower()
    ), "hub does not state the dependency check runs before the first spoke dispatch (GUIDE-04)"


def test_hub_documents_guide05_prose_template() -> None:
    # GUIDE-05: the hub must document the single human-readable guidance template and apply
    # it at the existing HOOK_ERROR and cap-exhaustion sections.
    hub = _read(HUB_PATH)
    assert "GUIDE-05" in hub, "hub does not name the GUIDE-05 prose template section"
    assert "what happened" in hub, "hub does not state the GUIDE-05 template shape"
    assert "HOOK_ERROR" in hub and "failure_class" in hub, (
        "hub does not tie the GUIDE-05 template to both HOOK_ERROR and failure_class surfaces"
    )


def test_offer_scout_documents_liveness_signal_source() -> None:
    # GUIDE-03: the scout must document its role supplying the observed liveness signal.
    scout = _read(AGENTS_DIR / "gmj-offer-scout.md")
    assert "gmj_check_offer_liveness.py" in scout or "liveness" in scout.lower(), (
        "gmj-offer-scout.md does not mention the liveness signal source (GUIDE-03)"
    )


def test_pipeline_commands_exist() -> None:
    # Plan 06 artifacts: the whole-flow command + six per-step wrappers.
    assert (COMMANDS_DIR / "gmj-pipeline-run.md").is_file(), "missing .claude/commands/gmj-pipeline-run.md"
    for step in ["scout", "freeze", "compose", "verify", "evaluate", "generate"]:
        path = COMMANDS_DIR / "gmj-pipeline" / f"{step}.md"
        assert path.is_file(), f"missing .claude/commands/gmj-pipeline/{step}.md"


def test_hub_references_leftover_check_script() -> None:
    # CLEAN-01: the hub must reference the new leftover-artifact detection script.
    hub = _read(HUB_PATH)
    assert "gmj_check_leftover_artifacts.py" in hub, (
        "hub does not reference gmj_check_leftover_artifacts.py (CLEAN-01)"
    )


def test_leftover_check_runs_before_guide04_and_before_dispatch() -> None:
    # CLEAN-02: the leftover check must be documented as running BEFORE the existing
    # GUIDE-04 dependency check and before any Task() dispatch, per 06-CONTEXT.md's
    # locked Trigger-points decision (detection is the FIRST init_run action).
    hub = _read(HUB_PATH)
    leftover_idx = hub.index("gmj_check_leftover_artifacts.py")
    guide04_idx = hub.index("gmj_check_dependencies.py")
    assert leftover_idx < guide04_idx, (
        "hub must mention gmj_check_leftover_artifacts.py BEFORE gmj_check_dependencies.py "
        "(CLEAN-02: leftover check runs first in init_run)"
    )
    # A phrase equivalent to "before the first spoke dispatch"/"before any Task()" must
    # appear near the leftover-check mention (within the same section).
    nearby = hub[leftover_idx : leftover_idx + 2000].lower()
    assert "before any `task()`" in nearby or "before the first spoke dispatch" in nearby or (
        "before any task()" in nearby
    ), (
        "hub does not state the leftover check runs before any Task()/first spoke dispatch "
        "near its gmj_check_leftover_artifacts.py mention (CLEAN-02)"
    )


def test_hub_documents_genuine_choice_gate_not_advisory_hint() -> None:
    # CLEAN-02: the new section must be a genuine, blocking choice gate -- distinguish it
    # from a pure advisory hint (GUIDE-03/04 never block; this is the one exception).
    hub = _read(HUB_PATH)
    heading = "## Leftover artifact detection (CLEAN-01/02/03)"
    assert heading in hub, f"hub does not contain the new section heading: {heading!r}"
    start = hub.index(heading)
    # Scan to the next top-level '## ' heading after this one, or end of file.
    next_heading_idx = hub.find("\n## ", start + len(heading))
    section_end = next_heading_idx if next_heading_idx != -1 else len(hub)
    section = hub[start:section_end]
    lowered = section.lower()
    assert "choice" in lowered or "choose" in lowered, (
        "new CLEAN-01/02/03 section does not contain 'choice'/'choose' language"
    )
    assert "wait" in lowered or "waits" in lowered, (
        "new CLEAN-01/02/03 section does not state the hub WAITS for a reply"
    )


def test_hub_never_invokes_cleanup_wizard_via_bash() -> None:
    # CLEAN-02 / T-06-06: every line mentioning gmj_cleanup_wizard.py must either carry a
    # "never"/"NEVER" token on the same line, or be unambiguously framed as an instruction
    # FOR THE HUMAN to run themselves (never paired with a Bash: / Bash( call pattern).
    hub = _read(HUB_PATH)
    assert "gmj_cleanup_wizard.py" in hub, "hub does not name scripts/gmj_cleanup_wizard.py"
    human_run_framing_found = False
    for line in hub.splitlines():
        if "gmj_cleanup_wizard.py" not in line:
            continue
        lowered = line.lower()
        assert not (
            ("bash:" in lowered or "bash(" in lowered) and "gmj_cleanup_wizard.py" in line
        ), f"hub pairs a Bash call pattern with gmj_cleanup_wizard.py on the same line: {line!r}"
        if "yourself" in lowered or "your own terminal" in lowered:
            human_run_framing_found = True
    assert human_run_framing_found, (
        "hub does not have at least one gmj_cleanup_wizard.py line framed as "
        "human-run-themselves ('yourself' / 'your own terminal')"
    )


def test_hub_documents_autonomous_default_logged() -> None:
    # CLEAN-03: the autonomous-mode branch must read leftover_artifacts_default from state
    # and always render a GUIDE-05-style logged line naming the applied default.
    hub = _read(HUB_PATH)
    assert "leftover_artifacts_default" in hub, (
        "hub does not mention leftover_artifacts_default (CLEAN-03)"
    )
    # Reuse the GUIDE-05 baseline assertions, then add one more: the GUIDE-05 template's
    # "applies to" list (or the new section itself) names the leftover-detection surface.
    assert "GUIDE-05" in hub, "hub does not name the GUIDE-05 prose template section"
    assert "what happened" in hub, "hub does not state the GUIDE-05 template shape"
    guide05_idx = hub.index("## Human-readable guidance template (GUIDE-05)")
    applies_to_idx = hub.index("This template applies to:", guide05_idx)
    next_heading_idx = hub.find("\n## ", applies_to_idx)
    applies_to_section = hub[applies_to_idx : next_heading_idx if next_heading_idx != -1 else len(hub)]
    assert (
        "gmj_check_leftover_artifacts.py" in applies_to_section
        or "leftover_artifacts_default" in applies_to_section
    ), (
        "GUIDE-05's 'applies to' bullet list does not name gmj_check_leftover_artifacts.py "
        "or leftover_artifacts_default as a surface the template applies to (CLEAN-03)"
    )


def test_hub_documents_output_artifacts_scan_target() -> None:
    # 06-RESEARCH.md Pitfall 3 guard: the new section must explicitly name
    # output/artifacts as the detection scan target, never .pipeline/runs.
    hub = _read(HUB_PATH)
    heading = "## Leftover artifact detection (CLEAN-01/02/03)"
    assert heading in hub, f"hub does not contain the new section heading: {heading!r}"
    start = hub.index(heading)
    next_heading_idx = hub.find("\n## ", start + len(heading))
    section = hub[start : next_heading_idx if next_heading_idx != -1 else len(hub)]
    assert "output/artifacts" in section, (
        "new CLEAN-01/02/03 section does not name output/artifacts as the scan target"
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
