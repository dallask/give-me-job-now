#!/usr/bin/env python3
"""Deterministic INGEST checks for Phase 3.1 candidate ingestion (INGEST-01/03/04/05).

Runnable as a plain assertion script (no pytest dependency), matching the repo
convention of ``python3 tests/test_*.py``. Each test reads the synthetic no-PII
fixtures under ``tests/fixtures/`` and proves an executed invariant rather than an
agent self-report:

- census==glob: the coverage manifest lists exactly the intake files (Pitfall 5),
- ``.doc`` is flagged ``needs-conversion`` by the real ``extract.py`` (Pitfall 2),
- an image routes to the vision reader, never ``extract.py`` (INGEST-03),
- ``candidate-analyzer`` structurally cannot write the master YAML (INGEST-04),
- the merged candidate YAML parses through ``yaml.safe_load`` (INGEST-04),
- every provenance sidecar key resolves into a real merged-YAML node and every
  new ingested fact carries a provenance entry (INGEST-05).

Only stdlib + PyYAML are used.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from yaml_path import resolve_path  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CANDIDATE_DIR = FIXTURES / "candidate"

EXTRACT_PY = REPO_ROOT / "scripts" / "cv" / "extract.py"
MANIFEST = FIXTURES / "candidate_coverage_manifest.sample.json"
MERGED_YAML = FIXTURES / "candidate.merged.sample.yaml"
PROVENANCE = FIXTURES / "candidate.provenance.sample.json"
ANALYZER = REPO_ROOT / ".claude" / "agents" / "candidate-analyzer.md"

# Sections in the merged YAML that represent newly-ingested facts requiring provenance.
NEW_FACT_SECTIONS = ("education", "certifications")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_file_paths() -> set[str]:
    manifest = _load_json(MANIFEST)
    return {entry["path"] for entry in manifest["files"]}


def _globbed_file_paths() -> set[str]:
    return {
        p.relative_to(REPO_ROOT).as_posix()
        for p in CANDIDATE_DIR.rglob("*")
        if p.is_file()
    }


def _agent_frontmatter_tools(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise AssertionError(f"{path} has no YAML frontmatter block")
    meta = yaml.safe_load(parts[1]) or {}
    raw = meta.get("tools", "")
    if isinstance(raw, list):
        return [str(t).strip() for t in raw]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def test_manifest_covers_every_file() -> None:
    manifest_paths = _manifest_file_paths()
    glob_paths = _globbed_file_paths()
    assert manifest_paths == glob_paths, (
        "coverage manifest census must equal the intake glob (census==glob).\n"
        f"only in manifest: {sorted(manifest_paths - glob_paths)}\n"
        f"only on disk:     {sorted(glob_paths - manifest_paths)}"
    )


def test_doc_flagged_needs_conversion() -> None:
    doc = CANDIDATE_DIR / "sample-old.doc"
    result = subprocess.run(
        [sys.executable, str(EXTRACT_PY), str(doc), "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"extract.py failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["kind"] == "needs-conversion", (
        f"legacy .doc must be flagged needs-conversion, got {payload['kind']!r}"
    )


def test_image_routed_to_vision_not_extractpy() -> None:
    manifest = _load_json(MANIFEST)
    jpg = [e for e in manifest["files"] if e["path"].endswith(".jpg")]
    assert jpg, "manifest must contain the .jpg intake entry"
    entry = jpg[0]
    assert entry["extractor"] == "read-vision", (
        f".jpg must route to read-vision, got {entry['extractor']!r}"
    )
    assert "extract.py" not in entry["extractor"], (
        "images must never be routed through extract.py (Pitfall 3)"
    )


def test_analyzer_cannot_write_master() -> None:
    tools = _agent_frontmatter_tools(ANALYZER)
    assert "Write" not in tools, (
        f"candidate-analyzer must not hold the Write tool; got {tools}"
    )


def test_merged_yaml_parses() -> None:
    loaded = yaml.safe_load(MERGED_YAML.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), "merged candidate YAML must parse to a dict"


def test_provenance_covers_new_facts() -> None:
    merged = yaml.safe_load(MERGED_YAML.read_text(encoding="utf-8"))
    provenance = _load_json(PROVENANCE)

    # 1. Every provenance key resolves to a real node in the merged YAML.
    for key in provenance:
        try:
            resolve_path(merged, key)
        except (KeyError, IndexError, TypeError) as exc:
            raise AssertionError(
                f"provenance key {key!r} does not resolve in merged YAML: {exc}"
            ) from exc

    # 2. Every newly-ingested fact carries a provenance entry.
    expected_keys: set[str] = set()
    for section in NEW_FACT_SECTIONS:
        items = merged.get(section) or []
        for i in range(len(items)):
            expected_keys.add(f"{section}[{i}]")
    missing = expected_keys - set(provenance)
    assert not missing, f"new facts missing a provenance entry: {sorted(missing)}"


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
