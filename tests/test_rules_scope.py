#!/usr/bin/env python3
"""RED contract for STRUCT-02 — frontmatter-scoped ./rules/ invariant folder.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_rules_scope.py``. This IS a real gate in the ``tests/test_*.py``
glob. It is the machine-checkable acceptance contract that plan 18-03 (the rules folder)
must turn GREEN. It is EXPECTED to FAIL now (RED): the repo-root ``rules/`` directory and
the CLAUDE.md rules-index do not yet exist.

Per the locked STRUCT-02 decision (18-01-PLAN + 18-VALIDATION line 46) the rules live at
repo-root ``./rules/`` — NOT ``.claude/rules/``.

HARD CONSTRAINT: pure file parsing (PyYAML safe_load on the fenced frontmatter block,
mirroring tests/test_ownership_manifest.py). Executes ZERO artifacts, mutates nothing.
Every assertion names the missing rule or the unindexed/orphan file.

Assertions (all currently RED):
  (a) test_rules_dir_and_invariants — repo-root rules/ exists and holds the six invariant
      files (18-PATTERNS lines 206-212).
  (b) test_every_rule_has_scope_frontmatter — every rules/*.md parses a YAML frontmatter
      block with a ``scope:`` mapping carrying >=1 of globs / keywords / agent-names.
  (c) test_claude_md_indexes_every_rule — CLAUDE.md's rules-index references rules/ and
      names each rules/*.md on disk exactly (count-agnostic: no orphan, no phantom —
      the disk-census partition of tests/test_ownership_manifest.py).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = REPO_ROOT / "rules"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# The six invariant rule files (18-PATTERNS lines 206-212). The set is the contract 18-03
# must satisfy; a new invariant simply adds a file that the CLAUDE.md index must also name.
REQUIRED_RULES = (
    "truthfulness.md",
    "hub-and-spoke.md",
    "sources-scope.md",
    "gmj-naming.md",
    "python-render-only.md",
    "gate-non-bypassability.md",
)

# Accepted selector keys inside a rule's `scope:` mapping (>=1 must be present + non-empty).
SCOPE_SELECTORS = ("globs", "keywords", "agent-names", "agent_names", "agents")


def _parse_frontmatter(text: str) -> dict | None:
    """Return the parsed YAML frontmatter mapping, or None if there is no ``---`` fence."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    block = "\n".join(lines[1:end])
    parsed = yaml.safe_load(block)
    return parsed if isinstance(parsed, dict) else None


def _disk_rule_files() -> list[Path]:
    return sorted(RULES_DIR.glob("*.md")) if RULES_DIR.is_dir() else []


def test_rules_dir_and_invariants() -> None:
    """Repo-root rules/ exists and contains each of the six invariant files."""
    assert RULES_DIR.is_dir(), (
        f"rules directory absent: {RULES_DIR.relative_to(REPO_ROOT)}/ "
        "(STRUCT-02 requires repo-root ./rules/)"
    )
    missing = [name for name in REQUIRED_RULES if not (RULES_DIR / name).is_file()]
    assert not missing, f"rules/ missing invariant file(s): {missing}"


def test_every_rule_has_scope_frontmatter() -> None:
    """Every rules/*.md has YAML frontmatter with a scope: mapping and >=1 selector."""
    assert RULES_DIR.is_dir(), (
        f"cannot check frontmatter — rules directory absent: "
        f"{RULES_DIR.relative_to(REPO_ROOT)}/"
    )
    rule_files = _disk_rule_files()
    assert rule_files, f"no rules/*.md files found under {RULES_DIR.relative_to(REPO_ROOT)}/"
    for rf in rule_files:
        rel = rf.relative_to(REPO_ROOT)
        fm = _parse_frontmatter(rf.read_text(encoding="utf-8"))
        assert fm is not None, f"{rel}: no parseable YAML frontmatter (--- fenced block)"
        assert "scope" in fm, f"{rel}: frontmatter has no `scope:` key"
        scope = fm["scope"]
        assert isinstance(scope, dict), (
            f"{rel}: `scope:` must be a mapping carrying selectors, got {type(scope).__name__}"
        )
        present = [k for k in SCOPE_SELECTORS if scope.get(k)]
        assert present, (
            f"{rel}: `scope:` has none of the selectors {list(SCOPE_SELECTORS)} "
            "(need >=1 of globs / keywords / agent-names)"
        )


def test_claude_md_indexes_every_rule() -> None:
    """CLAUDE.md's rules-index references rules/ and names every rules/*.md — no orphan/phantom."""
    assert CLAUDE_MD.is_file(), f"CLAUDE.md missing at {CLAUDE_MD.relative_to(REPO_ROOT)}"
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert "rules/" in text, "CLAUDE.md has no rules-index pointer (expected a `rules/` reference)"

    referenced = {m.group(1) for m in re.finditer(r"rules/([\w.-]+\.md)", text)}
    disk = {p.name for p in _disk_rule_files()}

    orphan = disk - referenced  # on disk but not named by the index
    phantom = referenced - disk  # named by the index but not on disk
    assert not orphan, f"rules/ file(s) not referenced by CLAUDE.md index (orphan): {sorted(orphan)}"
    assert not phantom, f"CLAUDE.md index names non-existent rule file(s) (phantom): {sorted(phantom)}"
    assert referenced, "CLAUDE.md rules-index names no rule files"


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
