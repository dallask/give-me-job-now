#!/usr/bin/env python3
"""Atomic-rename tripwire for the gate-node / spoke-name cluster (REBRAND-04, Pitfall 4).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gate_cluster_consistency.py``. This IS a real gate in the
``tests/test_*.py`` glob.

The pipeline gate-node identity (``truth-verifier`` / ``fit-evaluator``) is duplicated as a bare
string across many sites with NO mapping layer: the DAG gate nodes (config/pipeline.dag.yaml),
``GATE_NODES`` (record_gate.py), ``REQUIRED_GATES`` (check_delivery.py), ``COLLECTIVE_AGENTS``
(collective-handoff-contract.sh), and the persisted ``gate_results`` keys + ``current_step`` in
the fixture ``state.json`` files. If a wave renames some of those sites to ``gmj-`` but not the
others, the delivery gate reads a missing key and can silently mis-gate (T-07-13).

This gate asserts the cluster is CONSISTENT — every site names the SAME strings — regardless of
whether that string is still the old value or the new ``gmj-`` value. It is therefore GREEN when
the cluster is all-old (pre-agents-wave) AND all-new (post), and RED only when the cluster is
half-renamed. The constant-bearing files are located by CONTENT (not fixed filename) so the gate
survives the scripts/hooks waves that rename those files themselves.

HARD CONSTRAINT: pure file parsing + set algebra only. It executes ZERO pipeline code and asserts
ZERO gate verdicts/scores.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DAG = REPO_ROOT / "config" / "pipeline.dag.yaml"
SCRIPTS_DIR = REPO_ROOT / "scripts"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "pipeline" / "runs"


def _iter_files(base: Path, suffix: str):
    """Yield non-framework files under *base* with *suffix*, skipping gsd-*/__pycache__."""
    for p in base.rglob(f"*{suffix}"):
        parts = set(p.relative_to(base).parts)
        if "__pycache__" in parts or p.name.startswith("gsd-"):
            continue
        if p.is_file():
            yield p


def _find_list_literal(const: str, base: Path, suffix: str) -> list[str] | None:
    """First ``<const> = [ "a", "b" ]`` list literal found by CONTENT under *base* (rename-robust)."""
    pat = re.compile(rf"{re.escape(const)}\s*=\s*\[(.*?)\]", re.DOTALL)
    for p in _iter_files(base, suffix):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        m = pat.search(text)
        if m:
            return [a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', m.group(1))]
    return None


def _find_shell_list(const: str, base: Path) -> list[str] | None:
    """First ``<const>="a b c"`` space-separated shell list found by CONTENT under *base*."""
    pat = re.compile(rf'{re.escape(const)}="([^"]*)"')
    for p in _iter_files(base, ".sh"):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        m = pat.search(text)
        if m:
            return m.group(1).split()
    return None


def _dag_nodes() -> "tuple[set[str], set[str]]":
    """(all DAG node ids, gate-node ids where ``gate: true``)."""
    data = yaml.safe_load(DAG.read_text(encoding="utf-8"))
    steps = data.get("steps", {}) if isinstance(data, dict) else {}
    all_nodes = set(steps)
    gate_nodes = {k for k, v in steps.items() if isinstance(v, dict) and v.get("gate") is True}
    return all_nodes, gate_nodes


def _fixtures() -> list[tuple[str, set[str], str | None]]:
    """(fixture name, gate_results keys, current_step) for every PARSEABLE fixture state.json.

    Deliberately-malformed fixtures (e.g. the *-bad error-handling fixture) are skipped — they
    are not gate-cluster evidence.
    """
    out: list[tuple[str, set[str], str | None]] = []
    if not FIXTURES.is_dir():
        return out
    for sj in sorted(FIXTURES.rglob("state.json")):
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        keys = set((data.get("gate_results") or {}).keys())
        step = data.get("current_step")
        out.append((sj.parent.name, keys, step if isinstance(step, str) else None))
    return out


def cluster_problems(
    dag_all: set[str],
    dag_gates: set[str],
    gate_nodes: list[str] | None,
    required_gates: list[str] | None,
    collective: list[str] | None,
    fixtures: list[tuple[str, set[str], str | None]],
) -> list[str]:
    """Pure predicate: return every way the gate-node cluster disagrees on its identity (empty=OK).

    Factored out so the negative self-test can prove a half-renamed input goes RED without
    touching any real file.
    """
    problems: list[str] = []
    canonical = set(dag_gates)
    if not canonical:
        problems.append("DAG declares no gate: true nodes")
    if gate_nodes is None:
        problems.append("GATE_NODES literal not found")
    elif set(gate_nodes) != canonical:
        problems.append(f"GATE_NODES {sorted(gate_nodes)} != DAG gate nodes {sorted(canonical)}")
    if required_gates is None:
        problems.append("REQUIRED_GATES literal not found")
    elif set(required_gates) != canonical:
        problems.append(f"REQUIRED_GATES {sorted(required_gates)} != DAG gate nodes {sorted(canonical)}")
    if collective is None:
        problems.append("COLLECTIVE_AGENTS literal not found")
    elif not canonical <= set(collective):
        problems.append(f"DAG gate nodes {sorted(canonical)} not all in COLLECTIVE_AGENTS {sorted(collective)}")
    for name, keys, step in fixtures:
        if not keys <= canonical:
            problems.append(f"fixture {name}: gate_results keys {sorted(keys)} not subset of {sorted(canonical)}")
        if step is not None and step not in dag_all:
            problems.append(f"fixture {name}: current_step {step!r} not a DAG node {sorted(dag_all)}")
    return problems


def test_gate_node_identity_consistent() -> None:
    """Every gate-cluster site names the SAME strings (all-old OR all-new; never half-renamed)."""
    dag_all, dag_gates = _dag_nodes()
    gate_nodes = _find_list_literal("GATE_NODES", SCRIPTS_DIR, ".py")
    required_gates = _find_list_literal("REQUIRED_GATES", SCRIPTS_DIR, ".py")
    collective = _find_shell_list("COLLECTIVE_AGENTS", HOOKS_DIR)
    fixtures = _fixtures()
    assert fixtures, "no parseable fixture state.json found — fixture layout changed"
    problems = cluster_problems(dag_all, dag_gates, gate_nodes, required_gates, collective, fixtures)
    assert not problems, "gate-cluster inconsistency:\n  - " + "\n  - ".join(problems)


def test_half_rename_is_detected_red() -> None:
    """NEGATIVE proof: consistent all-old and all-new pass; a half-renamed cluster is flagged RED."""
    old_gates = {"truth-verifier", "fit-evaluator"}
    new_gates = {"gmj-truth-verifier", "gmj-fit-evaluator"}
    old_all = {"offer-scout", "artifact-composer", "truth-verifier", "fit-evaluator", "cv-generator"}
    new_all = {"gmj-" + n for n in old_all}
    old_collective = ["candidate-analyzer", "offer-scout", "truth-verifier", "fit-evaluator", "cv-generator"]
    new_collective = ["gmj-" + n for n in old_collective]

    # (a) all-old and (b) all-new are both CONSISTENT (empty problems).
    all_old = cluster_problems(
        old_all, old_gates, list(old_gates), list(old_gates), old_collective,
        [("f1", {"truth-verifier"}, "cv-generator")],
    )
    assert all_old == [], f"all-old cluster wrongly flagged: {all_old}"
    all_new = cluster_problems(
        new_all, new_gates, list(new_gates), list(new_gates), new_collective,
        [("f1", {"gmj-truth-verifier"}, "gmj-cv-generator")],
    )
    assert all_new == [], f"all-new cluster wrongly flagged: {all_new}"

    # (c) DAG renamed but GATE_NODES stale -> RED.
    half_const = cluster_problems(
        new_all, new_gates, list(old_gates), list(new_gates), new_collective, [],
    )
    assert half_const, "half-rename (stale GATE_NODES) NOT detected"

    # (d) DAG renamed but a fixture gate key stale -> RED.
    half_fixture = cluster_problems(
        new_all, new_gates, list(new_gates), list(new_gates), new_collective,
        [("stale", {"truth-verifier"}, "gmj-cv-generator")],
    )
    assert half_fixture, "half-rename (stale fixture gate key) NOT detected"


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
