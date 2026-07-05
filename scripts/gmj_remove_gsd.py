#!/usr/bin/env python3
"""Dry-run / report-ONLY GSD-framework-trace reporter (PACKAGE-03 + PACKAGE-04).

This tool enumerates every GSD-framework trace it WOULD remove and prints a labelled
REMOVE PLAN behind a loud "NOT executed — run later" banner. It is a hard-wired dry run:
there is NO removal branch in this file at all. The safety guarantee is the ABSENCE of any
deletion code path this milestone, not a flag or an environment toggle — a future milestone
adds the real removal as a separate, explicit step. Until then this reporter reads and prints
only, and makes zero filesystem mutations (re-runnable / idempotent).

Classification is manifest-driven: traces are derived from ``config/ownership-manifest.yaml``
``framework_globs`` (the same allow-list authority the installer uses) PLUS an enumerated
framework-trace set — the gsd-core tree, gsd- prefixed agents / skills / commands / hooks, the
.planning tree, and gsd- prefixed JSON state files. Paths are matched against the manifest
allow-list ONLY; this tool NEVER content-scans files for the framework substring, so app
content can never be false-classified as a framework trace. Every app-owned path is excluded.

CLI (mirrors scripts/pipeline/gmj_runs.py): ``python3 scripts/gmj_remove_gsd.py
[--manifest config/ownership-manifest.yaml]``; prints the REMOVE PLAN + banner to stdout and
exits 0. A missing / unparsable manifest prints a structured stderr message and exits 1.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"

# Directories pruned from the walk (volatile / generated / vendored). Mirrors the snapshot
# skip-set in tests/test_gmj_remove_gsd.py so the reporter never wanders into churn-heavy trees.
PRUNE_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", "output", ".venv", "venv"}

# Aggregate (do not enumerate children) for large or app-name-bearing trees. .planning holds
# phase dirs whose names carry the collective's own token, so listing individual files there
# would be noisy and confusing; the framework trace is the WHOLE tree either way.
AGGREGATE_ROOTS = (".claude/gsd-core/", ".planning/")

# Deterministic display order for trace groups; anything unlisted sorts last (alpha).
GROUP_ORDER = (
    ".claude/gsd-core/",
    ".planning/",
    ".claude/agents/gsd-*",
    ".claude/skills/gsd-*",
    ".claude/commands/gsd-*",
    ".claude/hooks/ (gsd-*, lib/**, managed-hooks-registry.cjs)",
    "gsd-*.json state files",
    "other framework (manifest framework_globs)",
)

BAR = "=" * 74


# --------------------------------------------------------------------------- manifest load

def load_framework_globs(manifest_path: Path) -> list[str]:
    """The manifest's ``framework_globs`` deny-list (raises on missing / unparsable / non-list).

    Ported from scripts/gmj_rebrand.py: this is the single authority for what counts as a
    framework trace. A missing or malformed manifest is a misconfiguration and raises — the
    reporter must never degrade to "report everything".
    """
    resolved = manifest_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"ownership manifest not found: {resolved}")
    data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{resolved}: top-level YAML must be a mapping")
    globs = data.get("framework_globs", [])
    if not isinstance(globs, list):
        raise ValueError("ownership manifest `framework_globs` must be a list")
    return [str(g) for g in globs]


def is_framework_path(path: Path, framework_globs: list[str]) -> bool:
    """True if ``path`` matches any framework deny-glob (verbatim from gmj_rebrand.py).

    Each glob is matched case-sensitively against the repo-relative posix path, the basename,
    the stem, and every path component, so both path-anchored globs (``**/gsd-core/**``,
    ``.claude/hooks/lib/**``) and name/stem globs (``gsd-*``, ``ai-agents-architect``) are
    enforced. This is a path allow-list check — never a content grep.
    """
    if not framework_globs:
        return False
    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = path.name
    candidates = {rel, path.name, Path(path.name).stem}
    candidates.update(Path(rel).parts)
    return any(fnmatch.fnmatchcase(cand, glob) for glob in framework_globs for cand in candidates)


# --------------------------------------------------------------------------- classification

def trace_group(rel: str, path: Path, framework_globs: list[str]) -> str | None:
    """Return the framework-trace group label for ``rel``, or None for app / unrelated paths.

    Classification is path-vs-manifest only. The .planning tree is an enumerated framework
    trace (planning artifacts belong to the framework, not the app). Everything else must
    match ``framework_globs`` to count — so app gmj-/gmj_ paths are never included.
    """
    parts = rel.split("/")
    if parts[0] == ".planning":
        return ".planning/"
    if not is_framework_path(path, framework_globs):
        return None
    if "gsd-core" in parts:
        return ".claude/gsd-core/"
    name = path.name
    if name.endswith(".json") and name.startswith("gsd-"):
        return "gsd-*.json state files"
    if rel.startswith(".claude/agents/") and name.startswith("gsd-"):
        return ".claude/agents/gsd-*"
    if rel.startswith(".claude/skills/") and any(seg.startswith("gsd-") for seg in parts):
        return ".claude/skills/gsd-*"
    if rel.startswith(".claude/commands/") and any(seg.startswith("gsd-") for seg in parts):
        return ".claude/commands/gsd-*"
    if rel.startswith(".claude/hooks/"):
        return ".claude/hooks/ (gsd-*, lib/**, managed-hooks-registry.cjs)"
    return "other framework (manifest framework_globs)"


def build_remove_plan(framework_globs: list[str]) -> dict[str, list[str]]:
    """Walk the repo and group every framework-trace path by its trace group (sorted rels)."""
    groups: dict[str, list[str]] = {}
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
        for fn in files:
            p = Path(root) / fn
            try:
                rel = p.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                continue
            group = trace_group(rel, p, framework_globs)
            if group is None:
                continue
            groups.setdefault(group, []).append(rel)
    for members in groups.values():
        members.sort()
    return groups


# --------------------------------------------------------------------------- rendering

def _group_sort_key(label: str) -> tuple[int, str]:
    try:
        return (GROUP_ORDER.index(label), "")
    except ValueError:
        return (len(GROUP_ORDER), label)


def _safe(line: str) -> bool:
    """A printed line may name an app-owned token only if it is genuinely a framework trace.

    Defence in depth for the app/framework boundary: any line carrying the collective's
    ``gmj-`` token that does NOT also carry the framework substring is dropped from the plan,
    so an app path can never leak into the removal report.
    """
    return "gmj-" not in line or "gsd" in line.lower()


def render_plan(groups: dict[str, list[str]]) -> list[str]:
    """Build the REMOVE PLAN + banner as a list of output lines (nothing printed / written)."""
    total = sum(len(v) for v in groups.values())
    lines: list[str] = []
    lines.append(BAR)
    lines.append("GSD-REMOVAL REMOVE PLAN  (dry-run / report only)")
    lines.append(BAR)
    lines.append("")
    lines.append(
        f"Derived from config/ownership-manifest.yaml framework_globs + the enumerated "
        f"framework-trace set. {total} framework path(s) WOULD be removed:"
    )
    lines.append("")

    for label in sorted(groups, key=_group_sort_key):
        members = groups[label]
        lines.append(f"  {label}  ({len(members)} path(s))")
        if label in AGGREGATE_ROOTS:
            lines.append("    (whole tree — every path under this root)")
        else:
            for rel in members:
                lines.append(f"    - {rel}")
        lines.append("")

    lines.append(BAR)
    lines.append("STATUS: NOT executed — this is a report only; nothing was removed.")
    lines.append("ACTION: run later — perform the real removal as a separate, explicit step,")
    lines.append("        in a future milestone, once GSD is no longer driving the build.")
    lines.append("SAFETY: this tool has no removal code path at all; a dry run is the only mode.")
    lines.append(BAR)

    return [ln for ln in lines if _safe(ln)]


# --------------------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report-only GSD-framework-trace remover (dry-run; no removal branch exists)."
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help="Ownership manifest path (source of framework_globs).",
    )
    args = parser.parse_args()

    try:
        framework_globs = load_framework_globs(args.manifest)
    except Exception as exc:  # noqa: BLE001  fail-closed: never degrade to reporting everything
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    groups = build_remove_plan(framework_globs)
    for line in render_plan(groups):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
