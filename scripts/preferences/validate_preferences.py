#!/usr/bin/env python3
"""Validate config/preferences.yaml: shape (jsonschema) + subset-of-sources.yaml (Python).

Two-layer gate. Layer 1 checks the STRUCTURE of preferences.yaml against
schemas/preferences.schema.json via ``jsonschema.Draft202012Validator`` backed by a
``referencing.Registry`` populated only with local repo schema files (never the deprecated
RefResolver, never network retrieval). Layer 2 checks the SCOPE invariant that
``preferences.yaml``'s ``scope`` block is a strict SUBSET of ``config/sources.yaml`` —
a rule JSON Schema cannot express because it references another file's arrays.

Fails CLOSED: any shape error, any out-of-scope scope-axis item, or a missing/unparsable
sources.yaml exits non-zero (a missing allow-list means "no scope defined", never "all
allowed"). NEVER writes sources.yaml (opens it read-only via ``yaml.safe_load``).

CLI: ``validate_preferences.py --file <preferences.yaml> [--sources config/sources.yaml]
[--schema schemas/preferences.schema.json]``; exit 0 = OK, exit 1 = shape error /
out-of-scope / missing-sources. Dual-use: runnable standalone AND invocable as the
/gmj-interview persona's pre-write guard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# scripts/preferences/ -> repo root (same depth as scripts/contracts/validate_envelope.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SOURCES = REPO_ROOT / "config" / "sources.yaml"
DEFAULT_SCHEMA = REPO_ROOT / "schemas" / "preferences.schema.json"
DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"


def _norm_site(url: str) -> str:
    """Normalize a board URL to its bare host.

    Replicates the sources-scope-guard.sh ``url_host()`` rule EXACTLY: strip ANY
    ``scheme://`` prefix (matching the hook's ``s#^[a-zA-Z][a-zA-Z0-9+.-]*://##``, not
    just http/https), strip the path, strip a leading ``www.``, strip a trailing
    ``:port``, lowercase. Both sides of the subset compare MUST use this or the check
    silently mismatches.
    """
    # Lowercase first, then strip any scheme://; equivalent to the hook's case-insensitive
    # ``[a-zA-Z][a-zA-Z0-9+.-]*://`` on the already-lowercased string.
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", str(url).strip().lower())
    s = s.split("/")[0]          # strip path
    if s.startswith("www."):
        s = s[4:]                # strip leading www.
    s = s.split(":")[0]          # strip trailing :port
    return s


def load_yaml(path: Path) -> dict:
    """Load a YAML file as a dict via ``yaml.safe_load`` ONLY (untrusted-input doctrine).

    Raises on parse errors and on a non-dict top-level document (fail-closed callers
    turn either into a non-zero exit).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data


def build_registry(schema_dir: Path) -> Registry:
    """Build a Registry from every local schemas/*.schema.json, keyed on its $id.

    Local files only — no network/remote retrieval, so cross-file ``$ref`` resolves
    without SSRF risk (mirrors scripts/contracts/validate_envelope.py).
    """
    resources = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def shape_errors(prefs: dict, schema_path: Path) -> list[str]:
    """Return structured ``<path>: <message>`` shape errors (empty when prefs conforms)."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = build_registry(schema_path.parent)
    validator = Draft202012Validator(schema, registry=registry)
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(prefs), key=lambda e: list(e.path))
    ]


def _scope(prefs: dict) -> dict:
    scope = prefs.get("scope") or {}
    return scope if isinstance(scope, dict) else {}


def subset_offenders(prefs: dict, sources: dict) -> list[str]:
    """Return every scope-axis item in prefs NOT within sources.yaml. Empty => in-scope."""
    offenders: list[str] = []
    scope = _scope(prefs)

    allow_sites = {_norm_site(s) for s in (sources.get("sites") or [])}
    allow_cities = {str(c).strip().lower() for c in (sources.get("cities") or [])}
    allow_langs = {str(l).strip().lower() for l in (sources.get("languages") or [])}

    for site in scope.get("sites") or []:
        if _norm_site(site) not in allow_sites:
            offenders.append(f"sites '{site}' not in sources.yaml.sites")
    for city in scope.get("cities") or []:
        if str(city).strip().lower() not in allow_cities:
            offenders.append(f"cities '{city}' not in sources.yaml.cities")
    for lang in scope.get("languages") or []:
        if str(lang).strip().lower() not in allow_langs:
            offenders.append(f"languages '{lang}' not in sources.yaml.languages")
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate preferences.yaml (shape + subset-of-sources.yaml, fail-closed)."
    )
    parser.add_argument("--file", type=Path, required=True, help="preferences.yaml to validate.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES,
        help="The sources.yaml allow-list (read-only).",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="The preferences JSON Schema.",
    )
    args = parser.parse_args()

    # (1) --file must exist and parse.
    prefs_path = args.file.expanduser().resolve()
    if not prefs_path.is_file():
        print(f"Not a file: {prefs_path}", file=sys.stderr)
        return 1
    try:
        prefs = load_yaml(prefs_path)
    except (yaml.YAMLError, ValueError, OSError) as exc:
        print(f"Unparsable preferences.yaml: {exc}", file=sys.stderr)
        return 1

    # (2) FAIL CLOSED on sources: missing or unparsable allow-list => no scope defined => reject.
    sources_path = args.sources.expanduser().resolve()
    if not sources_path.is_file():
        print(
            f"FAIL-CLOSED: sources.yaml not found: {sources_path} "
            "(a missing allow-list means no scope is defined, never all-allowed)",
            file=sys.stderr,
        )
        return 1
    try:
        sources = load_yaml(sources_path)
    except (yaml.YAMLError, ValueError, OSError) as exc:
        print(f"FAIL-CLOSED: unparsable sources.yaml: {exc}", file=sys.stderr)
        return 1

    # (3) Shape gate (jsonschema).
    errors = shape_errors(prefs, args.schema.expanduser().resolve())
    if errors:
        for error in errors:
            print(f"SHAPE-ERROR: {error}", file=sys.stderr)
        return 1

    # (4) Subset gate (Python cross-check against sources.yaml).
    offenders = subset_offenders(prefs, sources)
    if offenders:
        for offender in offenders:
            print(f"OUT-OF-SCOPE: {offender}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
