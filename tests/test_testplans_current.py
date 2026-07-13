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
``scripts/gmj_testplan_signals.py`` — never the rendered per-flow Markdown output files the
generator writes under its own docs output directory. Those rendered files are a purely
mechanical, downstream artifact of the source data; checking the source once is sufficient.

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


def _local_ref_target(schema: dict, ref: str) -> dict | None:
    """Resolve a local ``#/$defs/<name>`` (or absolute-URN-suffixed) ``$ref`` within ``schema``.

    Only same-document local refs are supported (the only kind these 3 schemas use) — an
    absolute URN ref (e.g. ``urn:give-me-job:schema:gate_result#/$defs/offending_claim``) is
    matched by its trailing ``#/$defs/...`` fragment, since this schema's own ``$id`` is that
    same URN. Fails closed (returns ``None``) on anything else rather than raising.
    """
    frag = ref.split("#", 1)[-1] if "#" in ref else ref
    if not frag.startswith("/$defs/"):
        return None
    name = frag[len("/$defs/") :]
    target = schema.get("$defs", {}).get(name)
    return target if isinstance(target, dict) else None


def _expand_branches(schema: dict, node: dict) -> list[dict]:
    """Return every concrete object-schema ``node`` could be, expanding ``$ref``/``oneOf``/``allOf``.

    A field described only as ``{"$ref": "..."}`` or ``{"oneOf": [...]}`` (e.g.
    ``content``'s ``oneOf`` of the 3 gate-variant $defs) has no ``properties`` of its own —
    the real fields live inside each expanded branch. Returns a flat list of dicts, each a
    candidate "this is what the field actually looks like" — the caller tries each.
    """
    branches: list[dict] = [node]
    out: list[dict] = []
    seen: list[int] = []
    while branches:
        current = branches.pop()
        if id(current) in seen:
            continue
        seen.append(id(current))
        if "$ref" in current:
            target = _local_ref_target(schema, current["$ref"])
            if target is not None:
                branches.append(target)
            continue
        for branch_key in ("oneOf", "allOf"):
            for sub in current.get(branch_key, []):
                if isinstance(sub, dict):
                    branches.append(sub)
        out.append(current)
    return out


def _walk_segments(schema: dict, root: dict, segments: list[str]) -> dict | None:
    """Walk ``segments`` through ``root``'s properties, expanding $ref/oneOf/allOf at each hop.

    Returns the final field's own schema-fragment dict, or ``None`` if any segment fails to
    resolve in every candidate branch. Fails closed rather than raising.
    """
    if not segments:
        return None
    nodes = _expand_branches(schema, root)
    field: dict | None = None
    for seg in segments:
        next_nodes: list[dict] = []
        field = None
        for node in nodes:
            props = node.get("properties")
            if isinstance(props, dict) and seg in props and isinstance(props[seg], dict):
                field = props[seg]
                next_nodes.extend(_expand_branches(schema, field))
        if field is None:
            return None
        nodes = next_nodes
    return field


def _resolve_field(schema: dict, dotted_path: str) -> dict | None:
    """Resolve ``dotted_path`` against ``schema``, trying every plausible starting root.

    Returns the final field's own schema-fragment dict (so a caller can read ``enum`` etc.),
    or ``None`` if the path resolves nowhere. Fails closed rather than raising on a
    malformed/renamed path.
    """
    segments = dotted_path.split(".")
    def_by_name = {
        name: body for name, body in schema.get("$defs", {}).items() if isinstance(body, dict)
    }

    # Ordinary case: walk the full dotted path from the schema root, or from each $def's own
    # body (a citation may name a field that lives inside a $def object accessed only via
    # $ref, e.g. content.verdict resolves through content's oneOf into $defs/gate_a_content).
    roots: list[dict] = [schema, *def_by_name.values()]
    for root in roots:
        field = _walk_segments(schema, root, segments)
        if field is not None:
            return field

    # A citation's leading segment may itself BE a $def name (e.g.
    # "offending_claim.rule_violated", where "offending_claim" is a $defs key referenced only
    # via $ref from an array's `items`, never a property anywhere) — retry with that leading
    # segment pre-consumed directly against its own named $def body.
    if segments and segments[0] in def_by_name:
        field = _walk_segments(schema, def_by_name[segments[0]], segments[1:])
        if field is not None:
            return field

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
        field = _resolve_field(schema, dotted_path)
        if field is None:
            violations.append(
                f"{flow_slug}: {schema_relpath}: {dotted_path} — expected field present, actual: field not found"
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
        field = _resolve_field(schema, dotted_path)
        live_enum = field.get("enum") if isinstance(field, dict) else None
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
            # (angle-bracket <...>, brace-glob {...}, or a bare **/* glob wildcard) —
            # never asserted to exist on disk (no run has ever executed in this checkout).
            if not (
                re.search(r"<[^>]+>", pattern)
                or re.search(r"\{[^}]+\}", pattern)
                or "**" in pattern
            ):
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
