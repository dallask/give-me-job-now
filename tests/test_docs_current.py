#!/usr/bin/env python3
"""RED contract for DOCS-03 — the authored docs + root README carry only the current gmj- roster.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_docs_current.py``. This IS a real gate in the ``tests/test_*.py``
glob. It is the machine-checkable acceptance contract that the Phase-19 documentation
plans must turn GREEN: every ``gmj-`` agent / ``/gmj-`` command / ``gmj_*.py`` script /
skill / hook token named in the authored ``docs/*.md`` + root ``README.md`` must resolve to
a real file on disk, no legacy 13-agent-roster token may be presented as CURRENT, and every
root-README ``.md`` link must resolve inside the repo. It is EXPECTED to FAIL now (RED):
``README.md`` is not yet written and ``docs/ARCHITECTURE.md`` §7 still presents the
superseded ``cv-template-creator`` / ``vacancy-router`` / … roster as current.

Ground-truth entity sets are built from the SOURCE trees (``.claude/``, ``scripts/``) — NEVER
from the ``gmj-core/`` payload copy — so the gate tracks the real roster, not a snapshot.

STALE_TOKENS is the single source of truth for the stale-roster grep gate. Grep discipline
(mirrors tests/test_claude_md_current.py; threat T-19-06 — avoid a false-negative that lets a
stale token slip through): a token occurrence counts as a CURRENT-roster reference UNLESS the
line is a comment (``<!--``) / blockquote (``>``) line, or sits inside an explicitly-marked
historical/superseded block (a heading or line carrying a ``historical`` / ``superseded``
marker, or an HTML-comment-delimited block). A bare current mention fails; each failure names
the token + file + line.

Path safety (threat T-19-01): every root-README ``.md`` link is resolved relative to REPO_ROOT
and asserted to stay INSIDE REPO_ROOT (``..`` traversal rejected) BEFORE ``.is_file()`` — mirrors
the run_id path-sanitization precedent.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Single source of truth: the superseded legacy-13-agent-roster names to keep out of the
# CURRENT docs (reused VERBATIM from tests/test_claude_md_current.py). NOT the retained gmj- roster.
STALE_TOKENS = (
    "vacancy-router",
    "job-market-researcher",
    "vacancy-scraper",
    "candidate-translator",
    "cv-composer",
    "cv-template-creator",
    "cv-reviewer",
    "cv-enhancer",
    "cv-deliverable-gate",
)

# Positive-presence anchors the root README must retain.
HUB_NAME = "gmj-orchestrator"
ARCH_POINTER = "ARCHITECTURE.md"

# ---------------------------------------------------------------------------
# Ground-truth entity sets — built from the SOURCE trees only (never gmj-core/).
# ---------------------------------------------------------------------------
AGENTS = {p.stem for p in (REPO_ROOT / ".claude/agents").glob("gmj-*.md")}
SKILLS = {p.name for p in (REPO_ROOT / ".claude/skills").glob("gmj-*") if p.is_dir()}
HOOKS = {p.stem for p in (REPO_ROOT / ".claude/hooks").glob("gmj-*.sh")}
SCRIPTS = {p.name for p in (REPO_ROOT / "scripts").rglob("gmj_*.py")}
CMD_FILES = set((REPO_ROOT / ".claude/commands").glob("gmj-*.md")) | set(
    (REPO_ROOT / ".claude/commands/gmj-pipeline").glob("*.md")
)
# Resolved command-file set for membership checks, and the gmj- command STEMS (top-level
# commands only — gmj-pipeline/* leaves are bare and are matched via full-path resolution).
_RESOLVED_CMDS = {p.resolve() for p in CMD_FILES}
COMMAND_STEMS = {p.stem for p in CMD_FILES if p.stem.startswith("gmj-")}

# Every kebab entity token must land in one of these stems (or the allow-list below).
ENTITY_STEMS = AGENTS | SKILLS | HOOKS | COMMAND_STEMS

# BLOCKER-1 allow-list: legitimate non-entity gmj- tokens the docs may contain — the packaged
# payload dir (gmj-core), the installer bin stem (gmj-tools), the command GROUP dir whose leaves
# are bare (gmj-pipeline), and the naming rule file (gmj-naming). A token in this set is skipped,
# never a failure; a typo'd agent/skill/hook/command name still fails.
ALLOWED_NONENTITY = {"gmj-core", "gmj-tools", "gmj-pipeline", "gmj-naming", "gmj-cursor-adapter"}

# ---------------------------------------------------------------------------
# File scopes.
# ---------------------------------------------------------------------------
# Authored docs the entity miners scan (README.md is authored last — absent files are skipped).
DOC_FILES = sorted((REPO_ROOT / "docs").glob("*.md")) + [REPO_ROOT / "README.md"]

# Stale-roster scan: the authored docs PLUS the non-doc source files whose legacy tokens the
# Phase-19 reconciliation must fix — gated under the same historical-allowance, regression-proof.
STALE_SCAN_FILES = DOC_FILES + [
    REPO_ROOT / "rules/sources-scope.md",
    REPO_ROOT / ".claude/skills/gmj-sources-config-enforcement/SKILL.md",
    REPO_ROOT / ".claude/commands/gmj-collective.md",
    REPO_ROOT / "rules/README.md",
]

# Canonical lowercase README section files (11) — the Architecture section reuses the existing
# authoritative docs/ARCHITECTURE.md rather than a duplicate lowercase architecture.md (DOCS-01).
CANONICAL_SECTIONS = (
    "requirements.md",
    "installation.md",
    "configuration.md",
    "rules.md",
    "skills.md",
    "agents.md",
    "commands.md",
    "flows.md",
    "cli-tools.md",
    "references.md",
    "features.md",
)

# ---------------------------------------------------------------------------
# Token-mining regexes.
# ---------------------------------------------------------------------------
GMJ_KEBAB = re.compile(r"(?<![\w-])gmj-[a-z0-9-]+(?![\w-])")   # agents/skills/hooks/cmd stems
GMJ_SCRIPT = re.compile(r"(?<![\w])gmj_[a-z0-9_]+\.py")        # scripts
# Leading (?<![\w]) so a `/gmj-…` that is a substring of a file PATH (e.g.
# `.claude/agents/gmj-cv-generator.md`, `.claude/commands/gmj-pipeline/{…}`) is NOT mis-mined as a
# command invocation — only standalone `/gmj-…` command tokens are collected.
GMJ_CMD = re.compile(r"(?<![\w])/gmj-[a-z0-9/-]+(?![\w])")    # /command tokens

# README markdown-link target (a `.md` path, optional #anchor + optional "title" tolerated).
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?(?:\s+\"[^\"]*\")?\)")

_HEADING = re.compile(r"^#{1,6}\s")


def _has_marker(text: str) -> bool:
    low = text.lower()
    return "historical" in low or "superseded" in low


# Explicit inline historical annotations (WR-03): a trailing `(historical)` /
# `(superseded)` tag, or a ~~strikethrough~~ span mentioning the word. Used ONLY for
# the per-line allowance so a normal prose line that merely happens to say
# "superseded"/"historical" (e.g. "X replaces the superseded flow and is CURRENT")
# no longer escapes the stale scan. Heading- and block-scoped allowances still use
# the broader `_has_marker`.
_INLINE_HIST = re.compile(r"\((?:historical|superseded)\)", re.IGNORECASE)
_STRIKE_HIST = re.compile(r"~~[^~]*(?:historical|superseded)[^~]*~~", re.IGNORECASE)


def _line_marked_historical(text: str) -> bool:
    """True iff the line carries an EXPLICIT inline historical annotation.

    Not merely any occurrence of the word — that coarse match (WR-03) let a line
    presenting a legacy name AS CURRENT evade detection just by containing the word.
    """
    return bool(_INLINE_HIST.search(text) or _STRIKE_HIST.search(text))


def _current_sites(text: str, token: str) -> list[int]:
    """Line numbers where ``token`` appears as a CURRENT reference (exclusions applied).

    Excluded (NOT counted): blockquote (``>``) / HTML-comment (``<!--``) lines, any line
    inside a heading-section whose heading is marked historical/superseded, any line inside
    an HTML-comment-delimited ``historical``/``superseded`` block, and any line carrying an
    EXPLICIT inline historical annotation (a trailing ``(historical)``/``(superseded)`` tag
    or a ``~~strikethrough~~`` span) — NOT a line that merely mentions the word.
    """
    pattern = re.compile(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])")
    sites: list[int] = []
    section_historical = False
    in_hist_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # HTML-comment marker lines. A self-contained single-line comment
        # (`<!-- … -->` closed on the SAME line) marks only itself and never opens a
        # block — this closes the WR-01 hole where one innocent `<!-- superseded -->`
        # comment silenced stale-token detection for the entire rest of the file. A
        # multi-line historical BLOCK is opened only by an UN-closed `<!-- historical …`
        # marker and closed by a later `<!-- /historical -->` / `<!-- end … -->` marker.
        if stripped.startswith("<!--") and _has_marker(stripped):
            low = stripped.lower()
            if "end" in low or "/" in stripped:
                in_hist_block = False          # explicit close marker (`<!-- /historical -->`)
            elif stripped.endswith("-->"):
                pass                           # self-contained marker: affects only itself
            else:
                in_hist_block = True           # un-closed `<!-- historical …` opens a block
            continue
        # A heading resets the section's historical disposition based on its own text.
        if _HEADING.match(line):
            section_historical = _has_marker(line)
        # Exclusions: comment/quote line, marked block/section, or a self-marked line.
        if stripped.startswith(">") or stripped.startswith("<!--"):
            continue
        if in_hist_block or section_historical or _line_marked_historical(line):
            continue
        if pattern.search(line):
            sites.append(i)
    return sites


def _mine(regex: re.Pattern[str], files: list[Path]):
    """Yield (token, relpath, lineno) for every ``regex`` match in each existing file.

    Fixed-path files that do not yet exist (e.g. README.md before it is authored) are SKIPPED
    — their existence is enforced separately by the README tests, not by the entity/stale miners.
    """
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT)
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for m in regex.finditer(line):
                yield m.group(0), rel, lineno


def _inside_repo(path: Path) -> bool:
    """True iff ``path`` resolves inside REPO_ROOT (rejects ``..`` traversal)."""
    try:
        path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def _resolve_command(token: str) -> bool:
    """Resolve a mined ``/gmj-…`` token to a real command file (or an allow-listed group)."""
    stem = token.lstrip("/").rstrip("/")
    if stem in ALLOWED_NONENTITY:  # e.g. the `gmj-pipeline` group dir (bare leaves)
        return True
    candidate = REPO_ROOT / ".claude/commands" / f"{stem}.md"
    if not _inside_repo(candidate):
        return False
    return candidate.resolve() in _RESOLVED_CMDS


def test_no_stale_roster_presented_as_current() -> None:
    """No STALE_TOKEN appears as a current-roster reference across docs + reconciled sources."""
    violations: list[str] = []
    for path in STALE_SCAN_FILES:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        for token in STALE_TOKENS:
            sites = _current_sites(text, token)
            if sites:
                violations.append(f"{rel}: '{token}' as current on line(s) {sites[:10]}")
    assert not violations, (
        "legacy roster token(s) still presented as current "
        f"({len(violations)}): " + " | ".join(violations)
    )


def test_every_docs_agent_exists() -> None:
    """Every mined gmj- kebab token resolves to a real agent/skill/hook/command (or allow-list)."""
    violations: list[str] = []
    for token, rel, ln in _mine(GMJ_KEBAB, DOC_FILES):
        if token in ALLOWED_NONENTITY:
            continue
        if token in ENTITY_STEMS:
            continue
        violations.append(f"{rel}:{ln}: unknown gmj- token '{token}'")
    assert not violations, (
        "gmj- token(s) resolve to no agent/skill/hook/command "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_every_docs_skill_exists() -> None:
    """Every mined kebab token that names a skill resolves to a real SKILL.md on disk.

    Grounds the docs->disk direction: a skill token named in the docs must back a real
    ``.claude/skills/<name>/SKILL.md`` file. (The old form only re-checked that a SKILLS
    set member is a directory, which is true by construction — a tautology; WR-02.)
    """
    violations: list[str] = []
    for token, rel, ln in _mine(GMJ_KEBAB, DOC_FILES):
        if token not in SKILLS:
            continue  # not a skill reference — resolution owned by test_every_docs_agent_exists
        if not (REPO_ROOT / ".claude/skills" / token / "SKILL.md").is_file():
            violations.append(f"{rel}:{ln}: skill '{token}' has no SKILL.md")
    assert not violations, "docs skill token(s) unresolved: " + " | ".join(violations[:20])


def test_every_docs_script_exists() -> None:
    """Every mined gmj_*.py basename resolves in the on-disk SCRIPTS set."""
    violations: list[str] = []
    for token, rel, ln in _mine(GMJ_SCRIPT, DOC_FILES):
        if token not in SCRIPTS:
            violations.append(f"{rel}:{ln}: unknown script '{token}'")
    assert not violations, (
        "docs reference script(s) not in scripts/**/gmj_*.py "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_every_docs_command_exists() -> None:
    """Every mined /gmj-… command token resolves to a real command file."""
    violations: list[str] = []
    for token, rel, ln in _mine(GMJ_CMD, DOC_FILES):
        if not _resolve_command(token):
            violations.append(f"{rel}:{ln}: unknown command '{token}'")
    assert not violations, (
        "docs reference command(s) with no file under .claude/commands/ "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_readme_links_resolve() -> None:
    """Every root-README `.md` link resolves to a real file INSIDE the repo (no `..` escape)."""
    readme = REPO_ROOT / "README.md"
    assert readme.is_file(), "README.md missing (authored in plan 19-09)"
    text = readme.read_text(encoding="utf-8")
    violations: list[str] = []
    for m in LINK.finditer(text):
        target = m.group(1)
        resolved = REPO_ROOT / target
        # Path-safety (T-19-01): reject traversal BEFORE touching the filesystem.
        if not _inside_repo(resolved):
            violations.append(f"link escapes repo: '{target}'")
            continue
        if not resolved.is_file():
            violations.append(f"broken link: '{target}'")
    assert not violations, (
        "README.md link(s) unresolved "
        f"({len(violations)}): " + " | ".join(violations[:20])
    )


def test_readme_indexes_every_section() -> None:
    """README links every canonical section file + the authoritative docs/ARCHITECTURE.md."""
    readme = REPO_ROOT / "README.md"
    assert readme.is_file(), "README.md missing (authored in plan 19-09)"
    text = readme.read_text(encoding="utf-8")
    missing: list[str] = []
    for name in (*CANONICAL_SECTIONS, "ARCHITECTURE.md"):
        # Require a real Markdown link opener `](docs/<name>` — not a bare prose mention —
        # and assert the target file actually exists on disk (IN-02).
        if f"](docs/{name}" not in text:
            missing.append(f"{name} (not linked)")
        elif not (REPO_ROOT / "docs" / name).is_file():
            missing.append(f"{name} (file missing)")
    assert not missing, "README index omits section(s): " + ", ".join(missing)


def test_docs_name_hub_and_arch_pointer() -> None:
    """README names the gmj- hub and points at the authoritative docs/ARCHITECTURE.md."""
    readme = REPO_ROOT / "README.md"
    assert readme.is_file(), "README.md missing (authored in plan 19-09)"
    text = readme.read_text(encoding="utf-8")
    assert HUB_NAME in text, f"README missing gmj- hub name '{HUB_NAME}'"
    assert ARCH_POINTER in text, "README missing pointer to docs/ARCHITECTURE.md"


def test_historical_allowance_is_scoped() -> None:
    """Lock the WR-01/WR-03 tightening: markers must not silence beyond their scope.

    Directly exercises `_current_sites` so a future regression that re-broadens the
    historical allowance is caught here rather than only via a live doc edit.
    """
    tok = "vacancy-scraper"

    # WR-01: a self-contained single-line comment marks only itself — a stale token on a
    # LATER line is still caught (previously the comment silenced the rest of the file).
    text = (
        "gmj lists cv-composer here\n"
        "<!-- superseded roster note -->\n"
        "gmj still lists vacancy-scraper here\n"
    )
    assert _current_sites(text, tok) == [3], (
        "WR-01 regression: single-line comment marker silenced a later line"
    )

    # WR-03: a prose line merely mentioning the word (not an explicit annotation) that
    # presents a legacy name AS CURRENT is still caught.
    prose = "vacancy-scraper replaces the superseded manual flow and is CURRENT.\n"
    assert _current_sites(prose, tok) == [1], (
        "WR-03 regression: bare 'superseded' prose mention silenced a current reference"
    )

    # An EXPLICIT inline annotation still excludes its line (kept intentionally).
    annotated = "vacancy-scraper (superseded) — do not use\n"
    assert _current_sites(annotated, tok) == [], (
        "explicit inline (superseded) annotation should exclude its line"
    )

    # Section-scoped: a marked heading silences its section, and the NEXT heading resets it
    # (preserves docs/ARCHITECTURE.md §7 behavior while re-arming detection afterwards).
    sectioned = (
        "## 7. Legacy Mapping (superseded — historical)\n"
        "row mentions vacancy-scraper\n"
        "## 8. Current\n"
        "gmj lists vacancy-scraper as current\n"
    )
    assert _current_sites(sectioned, tok) == [4], (
        "section-scoped allowance must reset at the next heading"
    )

    # A genuine multi-line HTML-comment block still silences until its explicit close.
    block = (
        "<!-- historical\n"
        "vacancy-scraper legacy row\n"
        "<!-- /historical -->\n"
        "gmj lists vacancy-scraper as current\n"
    )
    assert _current_sites(block, tok) == [4], (
        "multi-line historical block must close at its explicit end marker"
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
