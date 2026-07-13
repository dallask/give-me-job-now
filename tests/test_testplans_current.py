#!/usr/bin/env python3
"""Drift-detection gate for scripts/gmj_testplan_signals.py's SIGNAL_TABLE_BY_SLUG (TPGEN-09/TPGEN-10).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_testplans_current.py``. This IS a real gate in the ``tests/test_*.py``
glob, following the exact structural convention of ``tests/test_docs_current.py`` (module
docstring, ``REPO_ROOT`` constant, named constants, one ``test_*`` function per assertion
group, ``globals()``-introspection ``main()``, ``PASS``/``FAIL`` stdout/stderr lines,
``sys.exit``-compatible ``raise SystemExit(main())``).

Unlike ``test_docs_current.py`` (authored RED-first against not-yet-written docs), this gate
is expected to PASS now (GREEN) against the current, non-drifted 10-flow signal table (per
Success Criterion 3 / D-05 in 05-CONTEXT.md) — Phase 4 already fact-checked every cited
entity once at authoring time, so running this gate today should report all tests passing.
It exists to catch FUTURE drift: the moment a hand-authored citation inside
``scripts/gmj_testplan_signals.py``'s ``SIGNAL_TABLE_BY_SLUG`` (a schema field path, an enum
value set, a script/file path, a config literal value, or a command flag) no longer resolves
against the live codebase, this gate turns RED and names exactly which flow/entity drifted.

Check target (D-01): the hand-authored ``SIGNAL_TABLE_BY_SLUG`` source data in
``scripts/gmj_testplan_signals.py`` — never the rendered per-flow Markdown output files under
``docs/test-plans/*.md``. Those rendered files are a purely mechanical, downstream artifact of
the source data; checking the source once is sufficient.

Ground-truth entity sets are built directly from the SOURCE trees (``schemas/``, ``scripts/``,
``config/``) — NEVER from the ``gmj-core/`` packaged payload copy — so the gate tracks the
real, live codebase, not a snapshot.

Failure-naming discipline (D-05): every violation names the flow slug, the specific cited
entity that drifted (e.g. ``schemas/gate_result.schema.json: content.verdict``), and
expected (as currently transcribed in ``gmj_testplan_signals.py``) vs. actual (what's really
on disk now, or "field not found"/"value not found" if removed) — mirrors
``test_docs_current.py``'s token+file+line naming discipline and truncated-join-into-assert
pattern (``" | ".join(violations[:20])``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_testplan_signals as sig  # noqa: E402  (Phase 4 signal-table data module; check target)

# ---------------------------------------------------------------------------
# Ground-truth entity sets — built from the SOURCE trees only (never gmj-core/).
# ---------------------------------------------------------------------------
SCRIPTS = {p.name for p in (REPO_ROOT / "scripts").rglob("gmj_*.py")}
SCRIPTS_SH = {p.name for p in (REPO_ROOT / "scripts").rglob("gmj_*.sh")} | {
    p.name for p in (REPO_ROOT / ".claude/hooks").glob("gmj-*.sh")
}

# ---------------------------------------------------------------------------
# D-02/D-03: small explicit (flow_slug, dotted_path, schema_relpath) tuple list, derived
# by reading each SIGNAL_TABLE_BY_SLUG cell in full (per read_first) — acceptable per
# Claude's Discretion (05-CONTEXT.md) since the table only cites 3 schema files.
# ---------------------------------------------------------------------------
FIELD_PATH_CITATIONS: tuple[tuple[str, str, str], ...] = (
    ("pipeline-run-hitl", "content.verdict", "schemas/gate_result.schema.json"),
    ("pipeline-run-hitl", "offending_claim.rule_violated", "schemas/gate_result.schema.json"),
    ("multi-offer-batch", "runs.cv.status", "schemas/batch_manifest.schema.json"),
    ("multi-offer-batch", "runs.cover_letter.status", "schemas/batch_manifest.schema.json"),
    ("multi-offer-batch", "runs.interview_prep.status", "schemas/batch_manifest.schema.json"),
    ("firecrawl-search", "search_provider", "schemas/preferences.schema.json"),
    ("initial-configuration", "scope.sites", "schemas/preferences.schema.json"),
    ("initial-configuration", "scope.cities", "schemas/preferences.schema.json"),
    ("initial-configuration", "scope.languages", "schemas/preferences.schema.json"),
)

# D-03 bullet 1: enum value sets cited alongside the field paths above. Each entry is
# (flow_slug, dotted_path, schema_relpath, cited_values) — cited_values is the exact set
# transcribed in the signal-table cell (subset-or-exact per D-03's own allowance).
ENUM_CITATIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("pipeline-run-hitl", "content.verdict", "schemas/gate_result.schema.json", ("pass", "fail")),
    (
        "pipeline-run-hitl",
        "offending_claim.rule_violated",
        "schemas/gate_result.schema.json",
        ("unresolved_span", "scope_inflation", "numeric_invention", "cross_entry_merge"),
    ),
    (
        "multi-offer-batch",
        "runs.cv.status",
        "schemas/batch_manifest.schema.json",
        ("waiting", "in_flight", "delivered", "gate_exhausted", "error"),
    ),
    (
        "firecrawl-search",
        "search_provider",
        "schemas/preferences.schema.json",
        ("firecrawl",),
    ),
)

# D-03 bullet 3: config-literal citations — (flow_slug, cited_value, yaml_relpath, yaml_key).
CONFIG_LITERAL_CITATIONS: tuple[tuple[str, float, str, str], ...] = (
    ("pipeline-run-hitl", 0.7, "config/fit_thresholds.yaml", "coverage_threshold"),
)

# D-03 bullet 4: command-flag citations — (flow_slug, flag, script_relpath, command_doc_relpath).
COMMAND_FLAG_CITATIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "cleanup-wizard",
        "--repo-root",
        "scripts/gmj_cleanup_wizard.py",
        ".claude/commands/gmj-cleanup-wizard.md",
    ),
)

# Mining regexes for the script/file-path check (D-03 bullet 2) — narrow and anchored,
# mirroring test_docs_current.py's GMJ_SCRIPT/GMJ_CMD word-boundary discipline.
SCRIPT_PY_REF = re.compile(r"(?<![\w])scripts/[a-zA-Z0-9_/]+\.py")
SCRIPT_SH_REF = re.compile(r"(?<![\w])scripts/[a-zA-Z0-9_/]+\.sh")
PIPELINE_RUN_PATTERN = re.compile(r"(?<![\w])\.pipeline/runs/[^`\s]+")


def _resolve_dotted_path(schema: dict, dotted_path: str) -> tuple[bool, str]:
    """Walk ``dotted_path`` segments through a JSON-Schema dict's properties/$defs/oneOf/allOf.

    Returns (found, detail). Fails closed (found=False) on any unresolved segment rather than
    raising — a malformed/renamed path must report "field not found", never crash the gate.
    """
    segments = dotted_path.split(".")
    # Collect every properties-dict this schema exposes: the root's own properties, plus
    # every $def's properties (a citation may refer to a field inside a $def object, e.g.
    # offending_claim.rule_violated lives inside $defs/offending_claim, not the schema root).
    candidate_prop_maps: list[dict] = []
    if isinstance(schema.get("properties"), dict):
        candidate_prop_maps.append(schema["properties"])
    for def_body in schema.get("$defs", {}).values():
        if isinstance(def_body, dict) and isinstance(def_body.get("properties"), dict):
            candidate_prop_maps.append(def_body["properties"])
        # oneOf/allOf branches inside a $def (e.g. gate_a_content/gate_b_content variants
        # live under the schema root's own oneOf, already $defs above; nested oneOf/allOf
        # branches are walked too for completeness).
        for branch_key in ("oneOf", "allOf"):
            for branch in def_body.get(branch_key, []) if isinstance(def_body, dict) else []:
                if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
                    candidate_prop_maps.append(branch["properties"])
    for branch_key in ("oneOf", "allOf"):
        for branch in schema.get(branch_key, []):
            if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
                candidate_prop_maps.append(branch["properties"])

    for props in candidate_prop_maps:
        node = props
        ok = True
        for seg in segments:
            if not isinstance(node, dict) or seg not in node:
                ok = False
                break
            field = node[seg]
            if not isinstance(field, dict):
                ok = False
                break
            # Descend into the next segment's properties, if any (nested dotted path).
            node = field.get("properties", {})
        if ok:
            return True, "resolved"
    return False, "field not found"


def _resolve_enum(schema: dict, dotted_path: str) -> list[str] | None:
    """Return the live ``enum`` array at ``dotted_path``, or ``None`` if unresolved."""
    segments = dotted_path.split(".")
    candidate_prop_maps: list[dict] = []
    if isinstance(schema.get("properties"), dict):
        candidate_prop_maps.append(schema["properties"])
    for def_body in schema.get("$defs", {}).values():
        if isinstance(def_body, dict) and isinstance(def_body.get("properties"), dict):
            candidate_prop_maps.append(def_body["properties"])
        for branch_key in ("oneOf", "allOf"):
            for branch in def_body.get(branch_key, []) if isinstance(def_body, dict) else []:
                if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
                    candidate_prop_maps.append(branch["properties"])
    for branch_key in ("oneOf", "allOf"):
        for branch in schema.get(branch_key, []):
            if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
                candidate_prop_maps.append(branch["properties"])

    for props in candidate_prop_maps:
        node = props
        ok = True
        field: dict = {}
        for seg in segments:
            if not isinstance(node, dict) or seg not in node:
                ok = False
                break
            field = node[seg]
            if not isinstance(field, dict):
                ok = False
                break
            node = field.get("properties", {})
        if ok and "enum" in field:
            return list(field["enum"])
    return None


def test_signal_table_field_paths_resolve() -> None:
    """D-02: every dotted field path cited in a signal-table cell resolves in its schema."""
    violations: list[str] = []
    assert set(sig.SIGNAL_TABLE_BY_SLUG) >= {
        slug for slug, _, _ in FIELD_PATH_CITATIONS
    }, "a cited flow slug is missing from SIGNAL_TABLE_BY_SLUG"
    for flow_slug, dotted_path, schema_relpath in FIELD_PATH_CITATIONS:
        schema_path = REPO_ROOT / schema_relpath
        if not schema_path.is_file():
            violations.append(
                f"{flow_slug}: {schema_relpath} — expected schema file present, actual: missing"
            )
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        found, detail = _resolve_dotted_path(schema, dotted_path)
        if not found:
            violations.append(
                f"{flow_slug}: {schema_relpath}: {dotted_path} — expected field present, actual: {detail}"
            )
    assert not violations, (
        "signal-table field-path citation(s) no longer resolve "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_signal_table_enum_values_resolve() -> None:
    """D-03 bullet 1: cited enum value sets still exist in the live schema's enum array."""
    violations: list[str] = []
    for flow_slug, dotted_path, schema_relpath, cited_values in ENUM_CITATIONS:
        schema_path = REPO_ROOT / schema_relpath
        if not schema_path.is_file():
            violations.append(
                f"{flow_slug}: {schema_relpath} — expected schema file present, actual: missing"
            )
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        live_enum = _resolve_enum(schema, dotted_path)
        if live_enum is None:
            violations.append(
                f"{flow_slug}: {schema_relpath}: {dotted_path} — expected enum present, actual: value not found"
            )
            continue
        missing = [v for v in cited_values if v not in live_enum]
        if missing:
            violations.append(
                f"{flow_slug}: {schema_relpath}: {dotted_path} — expected {list(cited_values)}, "
                f"actual {live_enum} (missing: {missing})"
            )
    assert not violations, (
        "signal-table enum-value citation(s) no longer resolve "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_signal_table_script_and_path_refs_resolve() -> None:
    """D-03 bullet 2: cited scripts/paths still exist; glob-tolerant run-state patterns are structurally plausible.

    For fixed script/hook file references, confirm ``(REPO_ROOT / ref).is_file()`` against the
    real on-disk SCRIPTS/SCRIPTS_SH sets built from repo SOURCE trees only. For the
    ``.pipeline/runs/<run_id>-{cv,cl,ip}/state.json`` / ``.pipeline/runs/<batch_id>/
    batch_manifest.json`` glob-tolerant patterns, only the PATTERN STRUCTURE (placeholder
    segments present) is asserted plausible — no run has ever executed in this repo checkout,
    so a literal on-disk file is never expected to exist (documented scoping distinction, D-03).
    """
    violations: list[str] = []
    for flow_slug, cell in sig.SIGNAL_TABLE_BY_SLUG.items():
        text = " ".join(str(v) for v in cell.values())
        for m in SCRIPT_PY_REF.finditer(text):
            ref = m.group(0)
            basename = ref.rsplit("/", 1)[-1]
            if basename not in SCRIPTS:
                violations.append(
                    f"{flow_slug}: {ref} — expected script present in scripts/**, actual: not found"
                )
        for m in SCRIPT_SH_REF.finditer(text):
            ref = m.group(0)
            basename = ref.rsplit("/", 1)[-1]
            if basename not in SCRIPTS_SH:
                violations.append(
                    f"{flow_slug}: {ref} — expected script present in scripts/**, actual: not found"
                )
        for m in PIPELINE_RUN_PATTERN.finditer(text):
            pattern = m.group(0).rstrip("'\"’.,")
            # Structural plausibility only: must contain a placeholder-shaped segment
            # (angle-bracket <...> or brace-glob {...}) — never asserted to exist on disk.
            if not (re.search(r"<[^>]+>", pattern) or re.search(r"\{[^}]+\}", pattern)):
                violations.append(
                    f"{flow_slug}: {pattern} — expected glob-tolerant placeholder segment, "
                    "actual: no placeholder segment found"
                )
    assert not violations, (
        "signal-table script/path citation(s) no longer resolve "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_signal_table_config_literals_match() -> None:
    """D-03 bullet 3: cited config literal values still match the live YAML config."""
    violations: list[str] = []
    for flow_slug, cited_value, yaml_relpath, yaml_key in CONFIG_LITERAL_CITATIONS:
        yaml_path = REPO_ROOT / yaml_relpath
        if not yaml_path.is_file():
            violations.append(
                f"{flow_slug}: {yaml_relpath} — expected config file present, actual: missing"
            )
            continue
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or yaml_key not in data:
            violations.append(
                f"{flow_slug}: {yaml_relpath}: {yaml_key} — expected key present, actual: value not found"
            )
            continue
        actual_value = data[yaml_key]
        if actual_value != cited_value:
            violations.append(
                f"{flow_slug}: {yaml_relpath}: {yaml_key} — expected {cited_value}, actual {actual_value}"
            )
    assert not violations, (
        "signal-table config-literal citation(s) no longer resolve "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_signal_table_command_flags_resolve() -> None:
    """D-03 bullet 4: cited command flags still exist in the target script's argparse surface or docs."""
    violations: list[str] = []
    flag_add_argument = re.compile(r"add_argument\(\s*[\"']")
    for flow_slug, flag, script_relpath, command_doc_relpath in COMMAND_FLAG_CITATIONS:
        script_path = REPO_ROOT / script_relpath
        doc_path = REPO_ROOT / command_doc_relpath
        found = False
        if script_path.is_file():
            text = script_path.read_text(encoding="utf-8")
            for m in flag_add_argument.finditer(text):
                # Structural match: add_argument( followed (within a short window) by the
                # flag string literal — not a bare substring search anywhere in the file.
                window = text[m.end() - 1 : m.end() + len(flag) + 4]
                if flag in window:
                    found = True
                    break
        if not found and doc_path.is_file():
            doc_text = doc_path.read_text(encoding="utf-8")
            if flag in doc_text:
                found = True
        if not found:
            violations.append(
                f"{flow_slug}: {flag} — expected flag in {script_relpath} argparse surface or "
                f"{command_doc_relpath}, actual: not found"
            )
    assert not violations, (
        "signal-table command-flag citation(s) no longer resolve "
        f"({len(violations)}): " + " | ".join(violations[:20])
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
