#!/usr/bin/env python3
"""RED contract for STRUCT-01 — structure cleanup + removal-evidence manifest.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_structure_cleanup.py``. This IS a real gate in the
``tests/test_*.py`` glob. It is the machine-checkable acceptance contract that plan
18-05 (the structure cleanup) must turn GREEN. It is EXPECTED to FAIL now (RED): the
legacy ``example/`` prototype, gitignored ``__pycache__`` build artifacts, and the
``REMOVED-FILES.md`` evidence manifest do not yet reflect the cleaned end state.

HARD CONSTRAINT: pure filesystem read + reference-count grep. Executes ZERO artifacts,
mutates nothing. Every assertion names the offending path so a failure is actionable.

Assertions (all currently RED):
  (a) test_no_legacy_example_dir      — REPO_ROOT/example/ is absent (STRUCT-01).
  (b) test_no_pycache_build_artifacts — no __pycache__ dir under scripts/** or tests/**.
  (c) test_removed_files_manifest_exists — the REMOVED-FILES.md evidence doc exists.
  (d) test_removed_basenames_zero_refs — every basename it lists has ZERO inbound
      references across *.md *.py *.yaml *.json *.sh (excluding .git/, .planning/, and
      the framework .claude/gsd-core/ tree), comment lines (``^#``) filtered out — the
      grep-0 gate style of tests/test_rebrand_acceptance.py, never a bare unfiltered ==0.

Discipline: no broad try/except masks a real crash — the main() harness reports any
uncaught exception as a FAIL (exit 1), so a syntax/harness error can never pass green.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_PHASE_SLUG = "18-standalone-restructure-installer-gsd-removal"


def _resolve_phase_dir() -> Path:
    """The phase dir lives under .planning/phases/ during the milestone and is moved to
    .planning/milestones/v{X.Y}-phases/ by /gsd-cleanup at milestone close. Resolve either
    location so the STRUCT-01 evidence gate survives archival."""
    live = REPO_ROOT / ".planning" / "phases" / _PHASE_SLUG
    if live.is_dir():
        return live
    for archived in sorted(
        (REPO_ROOT / ".planning" / "milestones").glob(f"v*-phases/{_PHASE_SLUG}")
    ):
        if archived.is_dir():
            return archived
    return live  # fall back to the live path so a missing manifest fails loudly


PHASE_DIR = _resolve_phase_dir()
REMOVED_FILES_MANIFEST = PHASE_DIR / "REMOVED-FILES.md"

# Extensions that constitute an "inbound reference" surface (mirrors the rebrand grep set).
SEARCH_EXTS = frozenset({".md", ".py", ".yaml", ".json", ".sh"})


def _is_excluded(rel: Path) -> bool:
    """True for paths outside the app tree we grep: VCS, planning docs, framework core."""
    parts = rel.parts
    if not parts:
        return True
    if parts[0] in (".git", ".planning"):
        return True
    if len(parts) >= 2 and parts[0] == ".claude" and parts[1] == "gsd-core":
        return True
    return False


def _searchable_files() -> list[Path]:
    """Every app file whose extension is a reference surface, excluding framework/VCS/planning."""
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in SEARCH_EXTS:
            continue
        rel = p.relative_to(REPO_ROOT)
        if _is_excluded(rel):
            continue
        out.append(p)
    return out


def _parse_removed_basenames(text: str) -> set[str]:
    """Extract removed basenames from the REMOVED-FILES.md evidence table.

    Format (18-PATTERNS line 322): a markdown table whose FIRST column is the removed
    ``path``. We take the basename of each path-like first cell, skipping the header and
    the ``|---|`` separator row. This is the contract 18-05 must emit.
    """
    basenames: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].strip("`").strip()
        if not first:
            continue
        # separator row (only dashes/colons/spaces) or a header label.
        if set(first) <= set("-: "):
            continue
        if first.lower() in ("path", "file", "removed", "basename", "removed path"):
            continue
        # a path-like cell has a slash or a file extension.
        if "/" in first or re.search(r"\.\w+$", first):
            basenames.add(Path(first).name)
    return basenames


def _inbound_ref_count(basename: str, files: list[Path]) -> list[str]:
    """Repo-relative ``path:lineno`` sites referencing ``basename`` on non-comment lines.

    Comment lines (``grep -v '^#'`` — a stripped line beginning with ``#``) are filtered
    so a stray note never masquerades as a live code reference. The token is matched with
    word-ish boundaries so a longer name that merely contains ``basename`` is not counted.
    """
    token = re.compile(r"(?<![\w./-])" + re.escape(basename) + r"(?![\w-])")
    sites: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):  # grep -v '^#' (comment/heading lines)
                continue
            if token.search(line):
                sites.append(f"{p.relative_to(REPO_ROOT)}:{i}")
    return sites


def test_no_legacy_example_dir() -> None:
    """The legacy example/ prototype directory must not exist under REPO_ROOT."""
    example = REPO_ROOT / "example"
    assert not example.exists(), (
        f"legacy prototype dir still present: {example.relative_to(REPO_ROOT)}/ "
        "(STRUCT-01 requires it removed)"
    )


def test_no_pycache_build_artifacts() -> None:
    """No __pycache__ build-artifact directory under scripts/** or tests/**."""
    offenders: list[str] = []
    for root in ("scripts", "tests"):
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for d in base.rglob("__pycache__"):
            if d.is_dir():
                offenders.append(str(d.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"gitignored build artifacts present ({len(offenders)}): {sorted(offenders)}"
    )


def test_removed_files_manifest_exists() -> None:
    """The STRUCT-01 evidence manifest REMOVED-FILES.md must exist in the phase dir."""
    assert REMOVED_FILES_MANIFEST.is_file(), (
        f"removal evidence manifest missing: "
        f"{REMOVED_FILES_MANIFEST.relative_to(REPO_ROOT)}"
    )


def test_removed_basenames_zero_refs() -> None:
    """Every removed basename in the manifest has ZERO inbound references (comment-filtered)."""
    assert REMOVED_FILES_MANIFEST.is_file(), (
        f"cannot check inbound refs — manifest missing: "
        f"{REMOVED_FILES_MANIFEST.relative_to(REPO_ROOT)}"
    )
    basenames = _parse_removed_basenames(
        REMOVED_FILES_MANIFEST.read_text(encoding="utf-8")
    )
    assert basenames, (
        f"manifest {REMOVED_FILES_MANIFEST.relative_to(REPO_ROOT)} lists no removed "
        "paths (expected a table whose first column is each removed path)"
    )
    files = _searchable_files()
    for basename in sorted(basenames):
        sites = _inbound_ref_count(basename, files)
        assert not sites, (
            f"removed file '{basename}' still has {len(sites)} inbound reference(s) "
            f"(comment lines excluded): {sites[:15]}"
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
