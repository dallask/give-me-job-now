#!/usr/bin/env python3
"""Read-only, report-ONLY unused-file/folder proposal reporter (CLEANUP-01 + CLEANUP-02).

This tool walks the repo, classifies every non-excluded file as a candidate unused
file/folder ONLY when it finds zero references to it anywhere else in the repo (docs,
code, tests, schemas, hooks, agent/skill/command frontmatter), tags each candidate with
one of two confidence tiers, and writes a Markdown report for human review. It is a
hard-wired report: there is NO deletion/rename/move code path in this file at all. The
safety guarantee is the ABSENCE of any mutation code path (mirroring
``scripts/gmj_remove_gsd.py``'s existing precedent), not a flag or environment toggle.
This tool NEVER content-scans a file to decide ownership — that is the manifest's job
(``load_framework_globs``/``is_framework_path`` below); this tool only content-scans to
detect REFERENCES for the zero-hit classification.

Classification is two-source: (1) a candidate is excluded if it matches
``config/ownership-manifest.yaml``'s ``framework_globs`` (manifest-driven exclusion), and
(2) a candidate is excluded if any non-comment line elsewhere in the repo references its
basename. A candidate with zero references anywhere (including comments/prose) is tier
"high confidence"; a candidate with zero *code* hits but a comment/prose mention is tier
"review recommended". A candidate with any non-comment reference is fully excluded.

``load_framework_globs``/``is_framework_path`` are inlined here (verbatim logic from
``scripts/gmj_remove_gsd.py``) rather than imported: ``scripts/gmj_build_payload.py``'s
``BUILD_TIME_TOOLS`` deliberately excludes ``gmj_remove_gsd.py`` from the shipped
``gmj-core/`` runtime payload (it is dev-only tooling), but this reporter IS a shipped
runtime script, so it cannot have a hard import dependency on an excluded sibling module.
This is a deliberate small duplication, not a new manifest-authority source — the two
copies must stay in sync if ``gmj_remove_gsd.py``'s logic ever changes.

CLI (mirrors ``scripts/gmj_remove_gsd.py``): ``python3 scripts/gmj_cleanup_report.py
[--manifest config/ownership-manifest.yaml] [--repo-root .] [--output
sources/analysis/cleanup-report.md]``; writes the Markdown report and prints its path.
A missing/unparsable manifest prints a structured stderr message and exits 1 (fail
closed — never degrades to "report everything").
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "sources" / "analysis" / "cleanup-report.md"


def load_framework_globs(manifest_path: Path) -> list[str]:
    """The manifest's ``framework_globs`` deny-list (raises on missing / unparsable / non-list).

    Inlined verbatim from ``scripts/gmj_remove_gsd.py`` (see module docstring for why this
    is duplicated rather than imported). This is the single authority for what counts as a
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
    """True if ``path`` matches any framework deny-glob (inlined verbatim from gmj_remove_gsd.py).

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


# Directories pruned from every walk (volatile / generated / vendored / churn-heavy).
# Extends gmj_remove_gsd.PRUNE_DIRS with ".planning" and "gmj-core" as HARD skips: never
# walked, never reported. This is NOT an AGGREGATE_ROOTS-style reportable aggregate — the
# opposite of that tool's ".planning/" treatment, per 36-RESEARCH.md Pitfall 5.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", "output", ".venv", "venv",
    ".planning", "gmj-core",
}

# Extensions that constitute a reference-search surface. Extends
# tests/test_structure_cleanup.py's SEARCH_EXTS with ".cjs"/".js" per 36-RESEARCH.md
# Pitfall 3, so .claude/scripts/-style .cjs files and any .js file participate. Also
# extends with ".html"/".css"/".tcss"/".txt" (WR-01) so a reference that exists only
# inside a template's markup/CSS (e.g. templates/cv/*.html font url() refs) is not
# invisible to the tool.
SEARCH_EXTS = frozenset(
    {".md", ".py", ".yaml", ".json", ".sh", ".cjs", ".js", ".html", ".css", ".tcss", ".txt"}
)

# Every file under these trees counts as a reference-surface site regardless of
# extension, so hook/frontmatter references (Success Criterion 2) are never missed.
ALWAYS_SEARCH_DIRS = (".claude/hooks", ".claude/agents", ".claude/skills", ".claude/commands")

# An immediate-parent directory whose candidate members ALL share one confidence tier and
# number >= this threshold renders as one aggregate row instead of enumerating every path
# (mirrors gmj_remove_gsd.py's AGGREGATE_ROOTS folding concept, computed rather than
# hardcoded since this tool cannot know ahead of time which directory ends up fully unused).
AGGREGATE_THRESHOLD = 15

BAR = "=" * 74


# --------------------------------------------------------------------------- search corpus

def _searchable_files(repo_root: Path) -> list[Path]:
    """Every file that participates in the reference-search corpus under repo_root."""
    out: list[Path] = []
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(repo_root)
        except ValueError:
            continue
        if set(rel.parts) & SKIP_DIRS:
            continue
        rel_posix = rel.as_posix()
        always = any(
            rel_posix == d or rel_posix.startswith(d + "/") for d in ALWAYS_SEARCH_DIRS
        )
        if p.suffix in SEARCH_EXTS or always:
            out.append(p)
    return out


def _any_hits(basename: str, files: list[Path], repo_root: Path) -> list[str]:
    """Repo-relative path:lineno sites mentioning basename, on ANY line (comments included).

    This is the raw corpus for the "review recommended" detector — no comment filtering.
    """
    token = re.compile(r"(?<![\w.-])" + re.escape(basename) + r"(?![\w-])")
    sites: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if token.search(line):
                sites.append(f"{p.relative_to(repo_root)}:{i}")
    return sites


def _code_hits(basename: str, files: list[Path], repo_root: Path) -> list[str]:
    """Repo-relative path:lineno sites mentioning basename, EXCLUDING comment lines.

    Mirrors tests/test_structure_cleanup.py's _inbound_ref_count exactly — this is the
    "high confidence" detector's corpus (word-boundary regex, comment lines skipped).

    A leading ``#`` is a genuine comment marker in ``.py``/``.sh``/``.yaml`` etc, but in
    Markdown it denotes a HEADING, not a comment (WR-02) — e.g. a doc section titled
    ``# `gmj_offer_scout.py` design notes`` is a substantive reference, not a throwaway
    comment. For ``.md`` files, only HTML-style ``<!-- -->`` comment lines are skipped;
    a leading ``#`` is treated as ordinary (code-hit-eligible) content.
    """
    token = re.compile(r"(?<![\w.-])" + re.escape(basename) + r"(?![\w-])")
    sites: list[str] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        is_markdown = p.suffix == ".md"
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if is_markdown:
                if stripped.startswith("<!--"):
                    continue
            elif stripped.startswith("#"):
                continue
            if token.search(line):
                sites.append(f"{p.relative_to(repo_root)}:{i}")
    return sites


# --------------------------------------------------------------------------- enumeration

def enumerate_candidates(repo_root: Path, framework_globs: list[str]) -> list[Path]:
    """Every file under repo_root, pruned/skipped, minus manifest-owned framework paths."""
    candidates: list[Path] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = Path(root) / fn
            if is_framework_path(p, framework_globs):
                continue
            candidates.append(p)
    return candidates


# --------------------------------------------------------------------------- classification

def classify(repo_root: Path, framework_globs: list[str]) -> dict[str, dict[str, str]]:
    """Classify every non-excluded candidate under repo_root by reference evidence.

    Returns a dict keyed by repo-relative posix path -> {"tier": "high"|"review",
    "evidence": <str>}. A candidate with any non-comment (code) reference is excluded
    entirely (not present as a key at all).
    """
    files = _searchable_files(repo_root)
    result: dict[str, dict[str, str]] = {}
    for candidate in enumerate_candidates(repo_root, framework_globs):
        any_sites = _any_hits(candidate.name, files, repo_root)
        code_sites = _code_hits(candidate.name, files, repo_root)
        rel = candidate.relative_to(repo_root).as_posix()
        if not any_sites:
            result[rel] = {
                "tier": "high",
                "evidence": (
                    f"0 hits across {len(files)} searched files "
                    "(docs/code/tests/schemas/hooks/frontmatter)"
                ),
            }
        elif not code_sites:
            shown = any_sites[:3]
            suffix = f" (+{len(any_sites) - 3} more)" if len(any_sites) > 3 else ""
            result[rel] = {
                "tier": "review",
                "evidence": f"0 code hits; comment/prose mention(s): {', '.join(shown)}{suffix}",
            }
        # else: has code_sites -> fully excluded, no entry.
    return result


# --------------------------------------------------------------------------- rendering

def render_report(classification: dict[str, dict[str, str]], repo_root: Path) -> str:
    """Build the Markdown cleanup-proposal report as a single string."""
    by_parent: dict[str, dict[str, dict[str, str]]] = {}
    for rel, entry in classification.items():
        parent = Path(rel).parent.as_posix()
        by_parent.setdefault(parent, {})[rel] = entry

    def _rows_for_tier(tier: str, label: str) -> list[str]:
        rows: list[str] = []
        for parent in sorted(by_parent):
            members = by_parent[parent]
            tier_members = {r: e for r, e in members.items() if e["tier"] == tier}
            if not tier_members:
                continue
            # Fold into one aggregate row only if EVERY member of this parent (across
            # both tiers) shares this one tier AND the count clears the threshold.
            if len(tier_members) == len(members) and len(tier_members) >= AGGREGATE_THRESHOLD:
                rows.append(
                    f"| `{parent}/` | whole folder — {len(tier_members)} files, each {label} | {label} |"
                )
            else:
                for rel in sorted(tier_members):
                    entry = tier_members[rel]
                    rows.append(f"| `{rel}` | {entry['evidence']} | {label} |")
        return rows

    lines: list[str] = []
    lines.append("# Project Cleanup Proposal — Candidate Unused Files/Folders")
    lines.append("")
    lines.append(
        "This is a proposal-only report. No files were deleted, renamed, or moved by "
        "generating it. A human reviewer decides what (if anything) to remove; execution "
        "of any removal is a separate, later, human-gated step."
    )
    lines.append("")

    lines.append("## High confidence (zero references found anywhere)")
    lines.append("")
    lines.append("| Path | Evidence | Confidence |")
    lines.append("|------|----------|------------|")
    high_rows = _rows_for_tier("high", "high confidence")
    if high_rows:
        lines.extend(high_rows)
    else:
        lines.append("| _(none found)_ | | |")
    lines.append("")

    lines.append("## Review recommended (zero code hits, comment/prose mention found)")
    lines.append("")
    lines.append("| Path | Evidence | Confidence |")
    lines.append("|------|----------|------------|")
    review_rows = _rows_for_tier("review", "review recommended")
    if review_rows:
        lines.extend(review_rows)
    else:
        lines.append("| _(none found)_ | | |")
    lines.append("")

    lines.append(BAR)
    lines.append("STATUS: NOT executed — this is a report only; nothing was removed.")
    lines.append(
        "ACTION: A human reviewer decides; execution of any removal is a separate, "
        "later, human-gated step."
    )
    lines.append("SAFETY: this tool has no removal/rename/move code path at all.")
    lines.append(BAR)

    return "\n".join(lines) + "\n"


def write_report(text: str, output_path: Path) -> None:
    """The single filesystem-write call in this module — overwrite output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report-only unused-file/folder cleanup proposal (no removal branch exists)."
    )
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help="Ownership manifest path (source of framework_globs).",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="Repo root to walk (default: this repo's root).",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Markdown report output path (overwritten each run).",
    )
    args = parser.parse_args(argv)

    try:
        framework_globs = load_framework_globs(args.manifest)
    except Exception as exc:  # noqa: BLE001  fail-closed: never degrade to reporting everything
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    classification = classify(args.repo_root, framework_globs)
    text = render_report(classification, args.repo_root)
    write_report(text, args.output)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
