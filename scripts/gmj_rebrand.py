#!/usr/bin/env python3
"""Manifest-gated dry-run/apply rename+rewrite engine for the gmj- rebrand (REBRAND-01/02/03).

Consumer / contract: this is the per-wave mechanism invoked by 17-03..07. It reads
``config/ownership-manifest.yaml`` (the app old->new allow-list built in 17-01), refuses any
target NOT on the app allow-list (framework files are hard-blocked), and for one chosen
``--type`` at a time either:

  * ``--dry-run`` (default): prints the complete, reviewable ``git mv`` + reference-rewrite
    plan for that artifact type and makes ZERO filesystem/git changes (exit 0); or
  * ``--apply``: performs the history-preserving ``git mv`` for each app file of that type AND
    rewrites every internal reference to it across the app tree (Coupling A-F) in the same run.

Fail-closed doctrine (mirrors ``scripts/offers/gmj_merge_shortlists.py`` config load): a missing,
unparsable, or ``app``-less manifest prints a structured stderr message and exits 1 — it NEVER
degrades to "rename everything". Every rename target is checked against the manifest allow-set
before any ``git mv``, so a framework file (``gsd-*``, ``managed-hooks-registry.cjs``, ``lib/`` …)
can never be moved.

Reference forms are built PER stem/name from the manifest map, NEVER from bare stems:
  * scripts (``gmj_`` prefix): ``from <stem> import`` / ``import <stem>`` / ``<stem>.py`` path
    forms only — so prose "router/routing" / "extraction" is never corrupted (Pitfall 1/2).
  * agents/skills/commands/hooks (``gmj-`` prefix): the distinctive name as a DELIMITED token
    (``_ - . /`` and line bounds act as delimiters), skipping the already-renamed ``gmj-<old>``
    form and the stable ``<old>.log`` runtime-log filenames — so gate-artifact filename tokens,
    JSON gate keys, DAG node ids, dispatch names, ``name:`` frontmatter and hook paths all move
    together (the gate-cluster rides the agents wave atomically).

CLI: ``gmj_rebrand.py --type <scripts|agents|commands|skills|hooks> [--dry-run | --apply]
      [--manifest config/ownership-manifest.yaml]``; exit 0 (+ printed plan/summary) on success,
exit 1 (stderr) on a missing/unparsable manifest or a non-app target.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root (ONE fewer .parent than merge_shortlists)

DEFAULT_MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"


def load_yaml(path: Path) -> dict:
    """Load a YAML file as a dict via ``yaml.safe_load`` ONLY (raises on non-dict top level).

    Inlined (NOT imported from scripts/preferences/validate_preferences.py) on purpose: this
    engine self-excludes from its own reference-rewrite, so a ``from validate_preferences import``
    edge would break the moment 17-03 renames that module — silently halting the rest of the
    sweep. Keeping the loader dependency-free makes the engine survive every wave it drives.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return data

CLAUDE_DIR = REPO_ROOT / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
HOOKS_DIR = CLAUDE_DIR / "hooks"
COMMANDS_DIR = CLAUDE_DIR / "commands"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Safe filesystem path component: alphanumerics plus . _ - only (borrowed verbatim from
# scripts/pipeline/record_gate.py SAFE_COMPONENT — a manifest typo can't traverse via git mv).
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")

# Directory names pruned from the reference-rewrite tree walk: framework (.git/gsd-core),
# planning docs, stale bytecode, ephemeral runtime runs (.pipeline) and logs, and vendored deps.
# gsd-* files/dirs are pruned separately by prefix.
EXCLUDE_DIRS = {".git", ".planning", "gsd-core", "__pycache__", ".pipeline", "node_modules", "logs"}

# The rebrand tooling itself carries old names by design (the manifest map, this engine, and the
# rebrand-acceptance tests) — never rewrite or scan them, or the engine would corrupt its own map.
SELF_EXCLUDE = {
    (REPO_ROOT / "config" / "ownership-manifest.yaml").resolve(),
    (REPO_ROOT / "scripts" / "gmj_rebrand.py").resolve(),
    (REPO_ROOT / "tests" / "test_ownership_manifest.py").resolve(),
    (REPO_ROOT / "tests" / "test_rebrand_acceptance.py").resolve(),
    (REPO_ROOT / "tests" / "test_gate_cluster_consistency.py").resolve(),
}

DASH_TYPES = ("agents", "skills", "commands", "hooks")


# --------------------------------------------------------------------------- manifest load

def load_manifest(path: Path) -> dict:
    """Fail-closed manifest load: missing / unparsable / ``app``-less all raise (never 'rename all').

    A MISSING manifest is a misconfiguration, not "no app files" — raise so the caller exits 1
    (mirrors gmj_merge_shortlists.py's missing-sources fail-closed).
    """
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"ownership manifest not found: {resolved} "
            "(a missing manifest means no allow-list is defined, never 'rename everything')"
        )
    data = load_yaml(resolved)  # raises on parse error / non-dict top level
    if not isinstance(data.get("app"), dict):
        raise ValueError(f"ownership manifest lacks an `app` block: {resolved}")
    return data


# --------------------------------------------------------------------------- path resolution

def _resolve_pair(atype: str, old: str, new: str) -> tuple[Path, Path]:
    """Resolve the (old_path, new_path) file/dir pair for one app entry (paths need not exist)."""
    if atype == "agents":
        return AGENTS_DIR / f"{old}.md", AGENTS_DIR / f"{new}.md"
    if atype == "skills":
        return SKILLS_DIR / old, SKILLS_DIR / new  # a skill is a directory
    if atype == "hooks":
        return HOOKS_DIR / f"{old}.sh", HOOKS_DIR / f"{new}.sh"
    if atype == "commands":
        # A command is either a <name>.md leaf OR a <name>/ group directory (e.g. pipeline).
        if (COMMANDS_DIR / f"{old}.md").is_file() or (COMMANDS_DIR / f"{new}.md").is_file():
            return COMMANDS_DIR / f"{old}.md", COMMANDS_DIR / f"{new}.md"
        return COMMANDS_DIR / old, COMMANDS_DIR / new
    if atype == "scripts":
        # Scripts live under scripts/**; the subdir is NOT renamed — resolve by basename.
        for p in SCRIPTS_DIR.rglob(f"{old}.py"):
            return p, p.parent / f"{new}.py"
        for p in SCRIPTS_DIR.rglob(f"{new}.py"):
            return p.parent / f"{old}.py", p
        return SCRIPTS_DIR / f"{old}.py", SCRIPTS_DIR / f"{new}.py"
    raise ValueError(f"unknown artifact type: {atype!r}")


def build_app_index(manifest: dict) -> dict[str, list[dict]]:
    """Resolve every manifest app entry to {old, new, old_path, new_path}, keyed by type."""
    index: dict[str, list[dict]] = {}
    for atype, entries in manifest["app"].items():
        resolved = []
        for e in entries:
            old, new = e["old"], e["new"]
            old_path, new_path = _resolve_pair(atype, old, new)
            resolved.append({"old": old, "new": new, "old_path": old_path, "new_path": new_path})
        index[atype] = resolved
    return index


def app_allow_set(index: dict[str, list[dict]]) -> set[Path]:
    """The set of resolvable app file/dir paths (old AND new) — the rename allow-list."""
    allow: set[Path] = set()
    for entries in index.values():
        for e in entries:
            allow.add(e["old_path"].resolve())
            allow.add(e["new_path"].resolve())
    return allow


def assert_app_target(path: Path, allow_set: set[Path]) -> None:
    """Refuse to touch any path not proven on the app allow-list (framework hard-block).

    Mirrors the gmj_merge_shortlists.py write path-containment guard: a target outside the
    manifest's app set (a framework file, or an out-of-tree path) raises before any git mv.
    """
    if path.resolve() not in allow_set:
        raise ValueError(f"Refusing to rename non-app file: {path}")


# --------------------------------------------------------------------------- rewrite rules

def _dash_rules(entries: list[dict]) -> list[tuple[re.Pattern, str, dict]]:
    """Distinctive-name token rules (agents/skills/commands/hooks).

    Match the old name as a DELIMITED token: not preceded by ``gmj-`` (skip already-renamed),
    not bordered by ``[A-Za-z0-9-]`` (so ``_ . /`` and line bounds are delimiters — catches
    ``gate_<old>_cv_1.json`` filename tokens and ``"<old>"`` JSON keys), and NOT immediately
    followed by ``.log`` (stable runtime-log filenames stay — Coupling F / Open Q2).
    """
    rules = []
    for e in entries:
        old = re.escape(e["old"])
        pat = re.compile(rf"(?<!gmj-)(?<![A-Za-z0-9-]){old}(?![A-Za-z0-9-])(?!\.log)")
        rules.append((pat, e["new"], e))
    return rules


def _script_rules(entries: list[dict]) -> list[tuple[re.Pattern, str, dict]]:
    """Prose-safe reference-form rules for python script stems (``gmj_`` prefix).

    Only ``from <stem> import`` / ``import <stem>`` / ``<stem>.py`` (bare or path-prefixed) —
    never the bare stem, so "router/routing" and "extraction" prose is untouched (Pitfall 2).

    Plain module imports (``import <stem>``) are rewritten to an ALIASED form
    ``import gmj_<stem> as <stem>`` rather than bare ``import gmj_<stem>``: importers that use
    the module-qualified access pattern (``<stem>.func(...)``, e.g. ``route.next_step`` /
    ``hash_artifact.hash_artifact``) would otherwise raise ``NameError`` at first call, since a
    bare-stem qualified-reference rewrite (``<stem>.`` -> ``gmj_<stem>.``) cannot be applied
    tree-wide without corrupting prose ("we extract." / "the route.") — Pitfall 2. Aliasing the
    import preserves the local binding name so every downstream ``<stem>.`` reference keeps
    resolving, while the physical module file is still renamed (``git mv``) and grep-0 stays
    green (no ``import <stem>`` / ``from <stem> import`` / ``<stem>.py`` reference form survives).
    """
    rules = []
    for e in entries:
        old, new = re.escape(e["old"]), e["new"]
        rules.append((re.compile(rf"(?<![A-Za-z0-9_])from {old} import"), f"from {new} import", e))
        rules.append((re.compile(rf"(?<![A-Za-z0-9_])import {old}(?![A-Za-z0-9_])"), f"import {new} as {e['old']}", e))
        rules.append((re.compile(rf"(?<![A-Za-z0-9_]){old}\.py(?![A-Za-z0-9_])"), f"{new}.py", e))
    return rules


def build_rules(entries: list[dict], atype: str) -> list[tuple[re.Pattern, str, dict]]:
    return _script_rules(entries) if atype == "scripts" else _dash_rules(entries)


# --------------------------------------------------------------------------- tree walk + rewrite

def iter_app_files() -> "list[Path]":
    """Sorted list of app-tree files, pruning framework / ephemeral / self dirs and gsd-* files."""
    out: list[Path] = []
    for root, dirs, filenames in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("gsd-")]
        for fn in filenames:
            if fn.startswith("gsd-"):
                continue
            p = Path(root) / fn
            if p.resolve() in SELF_EXCLUDE:
                continue
            out.append(p)
    return sorted(out)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def collect_sites(rules, files: "list[Path]") -> list[tuple[Path, int, str]]:
    """Every (file, lineno, old-name) reference-rewrite site — lineno 0 means a path/filename token."""
    sites: list[tuple[Path, int, str]] = []
    for f in files:
        rel_str = _rel(f)
        for pat, _repl, e in rules:
            if pat.search(rel_str):
                sites.append((f, 0, e["old"]))
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat, _repl, e in rules:
                if pat.search(line):
                    sites.append((f, i, e["old"]))
    return sites


def apply_rewrites(rules, files: "list[Path]") -> int:
    """Rewrite every reference form in each text file; return the count of files changed."""
    changed = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text = text
        for pat, repl, _e in rules:
            new_text = pat.sub(lambda m, r=repl: r, new_text)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            changed += 1
    return changed


def git_mv(old_path: Path, new_path: Path) -> None:
    """History-preserving ``git mv``, sanitizing the new basename before the shell-out."""
    new_name = new_path.name
    if new_name in (".", "..") or not SAFE_COMPONENT.match(new_name):
        raise ValueError(f"Unsafe rename target component: {new_name!r}")
    subprocess.run(["git", "mv", str(old_path), str(new_path)], cwd=str(REPO_ROOT), check=True)


def purge_pycache() -> None:
    """Delete stale __pycache__ so old module .pyc can't shadow a renamed module (Pitfall 7)."""
    for base in (SCRIPTS_DIR, REPO_ROOT / "tests"):
        for d in base.rglob("__pycache__"):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- CLI

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manifest-gated dry-run/apply gmj- rename + reference-rewrite engine (one --type per wave)."
    )
    parser.add_argument(
        "--type", required=True, choices=["scripts", "agents", "commands", "skills", "hooks"],
        help="Artifact type to rename this wave.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print the plan; make no changes (default).")
    mode.add_argument("--apply", action="store_true", help="Execute git mv + reference rewrites.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Ownership manifest path.")
    args = parser.parse_args()
    do_apply = bool(args.apply)  # dry-run is the default whenever --apply is absent

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:  # noqa: BLE001  fail-closed: any load failure -> exit 1, never rename-all
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 1

    index = build_app_index(manifest)
    allow_set = app_allow_set(index)
    entries = index.get(args.type, [])

    # Allow-list guard: prove every target of this type is app-owned before touching anything.
    try:
        for e in entries:
            assert_app_target(e["old_path"], allow_set)
            assert_app_target(e["new_path"], allow_set)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    rules = build_rules(entries, args.type)
    files = iter_app_files()

    if not do_apply:
        print(f"# DRY-RUN plan for --type {args.type} ({len(entries)} app files)")
        mv_count = 0
        for e in entries:
            if e["old_path"].exists():
                print(f"git mv {_rel(e['old_path'])} {_rel(e['new_path'])}")
                mv_count += 1
        sites = collect_sites(rules, files)
        for f, lineno, old in sites:
            where = f"{_rel(f)}:{lineno}" if lineno else f"{_rel(f)} (path/filename token)"
            print(f"rewrite {where} [{old}]")
        print(f"# {mv_count} git-mv target(s), {len(sites)} reference-rewrite site(s); dry-run changed nothing")
        return 0

    # APPLY: rewrite references across the tree, then git mv the physical files, then purge bytecode.
    try:
        changed = apply_rewrites(rules, files)
        for e in entries:
            if e["old_path"].exists():
                assert_app_target(e["old_path"], allow_set)
                git_mv(e["old_path"], e["new_path"])
    except (ValueError, subprocess.CalledProcessError, OSError) as exc:
        print(f"apply failed for --type {args.type}: {exc}", file=sys.stderr)
        return 1
    purge_pycache()
    print(f"applied --type {args.type}: {len(entries)} rename target(s), {changed} file(s) rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
