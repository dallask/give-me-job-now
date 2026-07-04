#!/usr/bin/env python3
"""Structural gate for config/ownership-manifest.yaml (REBRAND-03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_ownership_manifest.py``. This IS a real gate in the
``tests/test_*.py`` glob. It proves the ownership manifest — the app allow-list that
scopes scripts/gmj_rebrand.py's ``git mv`` set AND defines the grep-0 reference forms —
is a faithful, framework-safe partition of the on-disk collective.

HARD CONSTRAINT (anti-circular): this gate performs PURE FILE PARSING + filesystem-glob
structural checks only. It executes ZERO renamed artifacts and asserts ZERO behavior. It
only proves that the manifest's `app` map (a) census-matches the on-disk artifacts, (b)
excludes every framework file, and (c) uses the correct `gmj-`/`gmj_` prefixes.

Design invariants:
- COUNT-AGNOSTIC: every count is derived from the parsed manifest + a filesystem glob;
  no 8/23/10/6/3 literal is hardcoded here. A new artifact simply becomes a new manifest
  entry that must resolve on disk (and vice-versa — no orphan, no phantom).
- Robust across the whole rebrand sweep: for every app entry, exactly ONE of
  {old-name-file, new-name-file} exists (pre-rename the old, post-rename the new).
- Every assert names the entry / file / prefix that failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Framework names/stems that must never be classified `app` and must be skipped as
# already-owned when scanning the disk for orphans.
_FRAMEWORK_TOKENS = ("ai-agents-architect", "managed-hooks-registry", "lib")
# Config/data file stems that must never be a standalone app entry (they stay stable).
# Matched as WHOLE tokens, not substrings: an agent/skill like `candidate-analyzer` or
# `candidate-yaml-schema` legitimately contains the word "candidate" — only a bare
# `candidate` / `sources` / `preferences` entry (i.e. the config filename itself) is illegal.
_CONFIG_DATA_STEMS = frozenset({"candidate", "sources", "preferences"})


def _load() -> dict:
    with open(MANIFEST, encoding="utf-8") as fh:
        m = yaml.safe_load(fh)
    assert isinstance(m, dict), "manifest did not parse to a mapping"
    assert m.get("version") == 1, f"manifest version != 1: {m.get('version')!r}"
    assert isinstance(m.get("app"), dict), "manifest has no `app` mapping"
    return m


def _is_framework_stem(stem: str) -> bool:
    """True for a GSD-owned / generic-framework artifact name (never an app rename)."""
    return stem.startswith("gsd-") or stem in _FRAMEWORK_TOKENS


def _agent_path(name: str) -> Path:
    return AGENTS_DIR / f"{name}.md"


def _skill_path(name: str) -> Path:
    return SKILLS_DIR / name  # skill is a directory


def _hook_path(name: str) -> Path:
    return HOOKS_DIR / f"{name}.sh"


def _command_exists(name: str) -> bool:
    """A command is either a `<name>.md` leaf file or a `<name>/` group directory."""
    return (COMMANDS_DIR / f"{name}.md").is_file() or (COMMANDS_DIR / name).is_dir()


def _script_exists(name: str) -> bool:
    """Scripts live under scripts/**; resolve by basename (dir is not renamed)."""
    return any(SCRIPTS_DIR.rglob(f"{name}.py"))


# ---- resolver table: type -> (existence predicate for a given basename) ----
_EXISTS = {
    "agents": lambda n: _agent_path(n).exists(),
    "skills": lambda n: _skill_path(n).is_dir(),
    "hooks": lambda n: _hook_path(n).is_file(),
    "commands": _command_exists,
    "scripts": _script_exists,
}


def test_census_equals_glob() -> None:
    """For every app entry exactly ONE of {old, new} exists on disk; no disk orphans.

    Two directions:
      (1) partition per entry — never neither (missing artifact) / never both (a stale
          copy left behind by a half-applied rename).
      (2) no orphan — every non-framework, non-already-`gmj` artifact on disk is named
          by some manifest entry (old or new), so nothing collective escapes the sweep.
    """
    m = _load()
    app = m["app"]

    # (1) per-entry exactly-one-exists partition.
    for atype, entries in app.items():
        exists = _EXISTS[atype]
        for e in entries:
            old, new = e["old"], e["new"]
            old_e, new_e = exists(old), exists(new)
            assert old_e ^ new_e, (
                f"{atype} entry {old}->{new}: expected exactly one on disk, "
                f"got old={old_e} new={new_e}"
            )

    # (2) reverse — no on-disk collective artifact is unnamed by the manifest.
    def named(atype: str) -> set[str]:
        return {e["old"] for e in app[atype]} | {e["new"] for e in app[atype]}

    # agents: *.md, skip framework + already-gmj-
    for p in AGENTS_DIR.glob("*.md"):
        s = p.stem
        if _is_framework_stem(s) or s.startswith("gmj-"):
            continue
        assert s in named("agents"), f"orphan agent on disk not in manifest: {s}"

    # skills: directories, skip framework + already-gmj-
    for p in SKILLS_DIR.iterdir():
        if not p.is_dir():
            continue
        s = p.name
        if _is_framework_stem(s) or s.startswith("gmj-"):
            continue
        assert s in named("skills"), f"orphan skill on disk not in manifest: {s}"

    # hooks: *.sh, skip framework + already-gmj-
    for p in HOOKS_DIR.glob("*.sh"):
        s = p.stem
        if _is_framework_stem(s) or s.startswith("gmj-"):
            continue
        assert s in named("hooks"), f"orphan hook on disk not in manifest: {s}"

    # commands: *.md leaves + group dirs, skip framework + already-gmj-
    cmd_names = named("commands")
    for p in COMMANDS_DIR.iterdir():
        if p.is_file() and p.suffix != ".md":
            continue  # skip .gitkeep and other non-command noise files
        s = p.stem if p.is_file() else p.name
        if _is_framework_stem(s) or s.startswith("gmj-"):
            continue
        assert s in cmd_names, f"orphan command on disk not in manifest: {s}"

    # scripts: **/*.py, skip already-gmj_ (there are no gsd- scripts under scripts/)
    for p in SCRIPTS_DIR.rglob("*.py"):
        s = p.stem
        if s.startswith("gmj_"):
            continue
        assert s in named("scripts"), f"orphan script on disk not in manifest: {s}"


def test_framework_never_in_app() -> None:
    """No framework token (gsd-*, ai-agents-architect, managed-hooks-registry, lib) is `app`."""
    m = _load()
    app = m["app"]
    for atype, entries in app.items():
        for e in entries:
            for slot in ("old", "new"):
                name = e[slot]
                assert not _is_framework_stem(name), (
                    f"framework name leaked into app.{atype}.{slot}: {name}"
                )


def test_prefix_correctness() -> None:
    """Every `new` carries the right prefix; no config/data basename is present."""
    m = _load()
    app = m["app"]
    dash_types = ("agents", "skills", "commands", "hooks")
    for atype in dash_types:
        for e in app[atype]:
            assert re.match(r"^gmj-", e["new"]), (
                f"app.{atype} new {e['new']!r} must start with 'gmj-'"
            )
    for e in app["scripts"]:
        assert re.match(r"^gmj_", e["new"]), (
            f"app.scripts new {e['new']!r} must start with 'gmj_'"
        )
    # config/data file stems must be absent as standalone (whole-token) app entries.
    for atype, entries in app.items():
        for e in entries:
            for slot in ("old", "new"):
                assert e[slot].lower() not in _CONFIG_DATA_STEMS, (
                    f"config/data file stem {e[slot]!r} leaked into app.{atype}.{slot}"
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
