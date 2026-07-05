#!/usr/bin/env python3
"""Build the standalone ``gmj-core/`` install payload (PACKAGE-01).

Vendors the full give-me-job app payload into ``gmj-core/`` and emits a
path->sha256 census manifest, so the 18-07 installer has a self-contained,
tamper-detectable distributable to stage onto a runtime.

The payload is derived by a **fresh disk census** of ``gmj-*``/``gmj_*`` app
artifacts MINUS ``config/ownership-manifest.yaml`` ``framework_globs`` — NEVER by
replaying the Phase-17 rename map. Phases 10-16 birthed ``gmj-`` files that are
absent from the rename map (e.g. gmj-template-creator, gmj-batch, gmj_runs,
gmj_visual_diff); a rename-map replay would silently miss them. Census-by-glob is
the only complete source, and it is exactly what ``tests/test_gmj_install.py``
CHECK 6 asserts against the emitted manifest.

Two build-time tools are DELIBERATELY excluded from the shipped runtime payload:
``scripts/gmj_rebrand.py`` and ``scripts/gmj_remove_gsd.py`` — they are dev
tooling, not runtime spokes. This exclusion mirrors CHECK 6's ``BUILD_TIME_TOOLS``.

Config is split two ways (18-PATTERNS.md lines 74-76):
  - app-config    -> copied verbatim (overwrite-safe on install).
  - user-data     -> shipped as ``<name>.sample`` templates ONLY, with NO real
                     PII. The populated ``config/candidate.yaml`` (name/phone/
                     email) is NEVER vendored (T-18-05 Information Disclosure).

The script is re-runnable / idempotent: it rebuilds the payload subtrees it owns
from scratch on every run, then re-hashes. Keys in the manifest are sorted for
byte-stable output.

No pytest, no third-party deps beyond PyYAML (already required repo-wide). Run:
``python3 scripts/gmj_build_payload.py``
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root
DEFAULT_MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"

PAYLOAD_ROOT = REPO_ROOT / "gmj-core"
MANIFEST_PATH = PAYLOAD_ROOT / "gmj-file-manifest.json"
VERSION_PATH = PAYLOAD_ROOT / "VERSION"

# First standalone payload release. Mirrors .claude/gsd-core/VERSION semantics
# (VERSION string == manifest "version" field).
PAYLOAD_VERSION = "1.0.0"

# Payload subtrees this build script OWNS and rebuilds from scratch each run.
# (gmj-core/bin/ — the 18-07 installer — is intentionally NOT in this set, so a
# future re-run never clobbers it.)
OWNED_SUBDIRS = ("agents", "skills", "commands", "hooks", "scripts", "schemas", "config", "templates")

# Build-time tooling excluded from the shipped runtime payload — MUST match
# tests/test_gmj_install.py BUILD_TIME_TOOLS exactly (repo-relative posix paths).
BUILD_TIME_TOOLS = {
    "scripts/gmj_rebrand.py",
    "scripts/gmj_remove_gsd.py",
}

# --- config split (18-PATTERNS.md lines 74-76) -------------------------------

# app-config: copied verbatim into gmj-core/config/ (overwrite-safe on install).
# Values are repo-relative source paths.
APP_CONFIG_FILES = (
    "config/pipeline.dag.yaml",
    "config/pipeline.config.yaml",
    "config/fit_thresholds.yaml",
    "config/i18n/labels.yaml",
    "config/ownership-manifest.yaml",
)

# user-data: config/sources.yaml, config/credentials.yaml, config/preferences.yaml
# carry no identity PII (they are allow-lists / ranking knobs), so their real
# content is a reasonable starting TEMPLATE — shipped verbatim as `<name>.sample`.
# Source -> sample-destination-basename (under gmj-core/config/).
USER_DATA_COPY_AS_SAMPLE = {
    "config/sources.yaml": "sources.yaml.sample",
    "config/credentials.yaml": "credentials.yaml.sample",
    "config/preferences.yaml": "preferences.yaml.sample",
}

# candidate.yaml (+ .ua/.ru overlays) DO carry identity PII (name/phone/email), so
# the populated profile is NEVER vendored. Ship synthetic placeholder templates.
SAMPLE_CANDIDATE = """\
# SAMPLE candidate profile (template) — replace every value with your real data.
# Synthetic placeholder content, NO real PII. Scaffolded on install ONLY if
# config/candidate.yaml is absent (never clobbers your populated profile).
# Schema: .claude/skills/gmj-candidate-yaml-schema/SKILL.md
name: "Your Name"
title: "Your Professional Title"
summary: "One-paragraph professional summary describing your experience and focus."
contact:
  phone: "+00000000000"
  email:
    - "you@example.com"
  address: "City, Country"
technical_expertise:
  - resume_title: "Core Skills"
    skills:
      - "Skill A"
      - "Skill B"
professional_experience:
  - company: "Example Corp"
    position: "Your Role"
    duration: "2020 - Present"
    location: "City, Country"
    description: "What you did in this role."
    achievements:
      - "A quantified achievement with a real metric."
education:
  - institution: "Your University"
    degree: "Your Degree"
    duration: "2010 - 2014"
languages:
  - language: "English"
    level: "Fluent"
"""

SAMPLE_CANDIDATE_UA = """\
# SAMPLE Ukrainian (ua) prose overlay template — translated prose scalars ONLY.
# Synthetic placeholder, NO real PII. Deep-merged over candidate.yaml at --lang ua.
name: "Ваше Ім'я"
title: "Ваша Посада"
summary: "Стислий професійний опис вашого досвіду та напряму роботи."
"""

SAMPLE_CANDIDATE_RU = """\
# SAMPLE Russian (ru) prose overlay template — translated prose scalars ONLY.
# Synthetic placeholder, NO real PII. Deep-merged over candidate.yaml at --lang ru.
name: "Ваше Имя"
title: "Ваша Должность"
summary: "Краткое профессиональное описание вашего опыта и направления работы."
"""

SAMPLE_CANDIDATE_FILES = {
    "candidate.yaml.sample": SAMPLE_CANDIDATE,
    "candidate.ua.yaml.sample": SAMPLE_CANDIDATE_UA,
    "candidate.ru.yaml.sample": SAMPLE_CANDIDATE_RU,
}


# --- framework deny-list (mirror scripts/gmj_rebrand.py:is_framework_path) ----

def load_framework_globs(manifest_path: Path) -> list[str]:
    """The manifest's framework deny-globs (empty list if unreadable)."""
    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a broken manifest must not crash the build
        return []
    globs = data.get("framework_globs") or []
    return [str(g) for g in globs if isinstance(g, str)]


def is_framework_path(rel: str, framework_globs: list[str]) -> bool:
    """True if ``rel`` (repo-relative posix path) matches any framework deny-glob.

    Matches case-sensitively against the full rel path, the basename, the stem,
    and every path component — mirroring gmj_rebrand.py so both path-anchored globs
    (``**/gsd-core/**``, ``.claude/hooks/lib/**``) and name globs (``gsd-*``,
    ``ai-agents-architect``) are enforced.
    """
    if not framework_globs:
        return False
    p = Path(rel)
    candidates = {rel, p.name, p.stem}
    candidates.update(p.parts)
    return any(
        fnmatch.fnmatchcase(cand, glob) for glob in framework_globs for cand in candidates
    )


# --- census -------------------------------------------------------------------

def census_payload(framework_globs: list[str]) -> list[tuple[Path, str]]:
    """Census the app payload by disk glob.

    Returns a list of ``(source_abs_path, payload_relpath)`` where payload_relpath
    is the path UNDER gmj-core/. The mapping mirrors CHECK 6's census exactly for
    the prefixed + schema globs (so the emitted manifest is a superset of the
    census keys), then adds the config split on top.
    """
    pairs: list[tuple[Path, str]] = []

    def add(src: Path, payload_rel: str) -> None:
        rel = src.relative_to(REPO_ROOT).as_posix()
        if is_framework_path(rel, framework_globs) or rel in BUILD_TIME_TOOLS:
            return
        pairs.append((src, payload_rel))

    # .claude/{agents,skills,commands,hooks}/gmj-* -> gmj-core/{cat}/... (strip .claude/)
    for cat in ("agents", "skills", "commands", "hooks"):
        root = REPO_ROOT / ".claude" / cat
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("gmj-*")):
            if entry.is_file():
                add(entry, f"{cat}/{entry.name}")
            elif entry.is_dir():
                for f in sorted(entry.rglob("*")):
                    if f.is_file():
                        sub = f.relative_to(root).as_posix()
                        add(f, f"{cat}/{sub}")

    # scripts/**/gmj_*.py -> gmj-core/scripts/... (keep scripts/ prefix)
    for f in sorted((REPO_ROOT / "scripts").rglob("gmj_*.py")):
        if f.is_file():
            rel = f.relative_to(REPO_ROOT).as_posix()  # begins with "scripts/"
            add(f, rel)

    # schemas/*.schema.json -> gmj-core/schemas/... (+ schemas/samples/* for parity)
    schemas = REPO_ROOT / "schemas"
    if schemas.is_dir():
        for f in sorted(schemas.glob("*.schema.json")):
            add(f, f.relative_to(REPO_ROOT).as_posix())
        samples = schemas / "samples"
        if samples.is_dir():
            for f in sorted(samples.rglob("*")):
                if f.is_file():
                    add(f, f.relative_to(REPO_ROOT).as_posix())

    # --- config split (NOT part of CHECK 6 census; shipped for a runnable payload) ---
    # app-config: verbatim copy.
    for src_rel in APP_CONFIG_FILES:
        src = REPO_ROOT / src_rel
        if src.is_file():
            # Preserve the config/ layout (incl. i18n/ subdir) under gmj-core/.
            add(src, src_rel)

    # --- runtime sibling assets (load-bearing on a clean-machine install) --------
    # Bundled DejaVu fonts — REQUIRED for Cyrillic (ua/ru) render. Helvetica (the
    # fallback) has NO Cyrillic glyphs, so a fontless payload silently ships glyphless
    # PDFs. These are `.ttf`, not `gmj_*.py`, so the prefixed globs never catch them.
    fonts_dir = REPO_ROOT / "scripts" / "cv" / "fonts"
    if fonts_dir.is_dir():
        for f in sorted(fonts_dir.glob("*.ttf")):
            add(f, f.relative_to(REPO_ROOT).as_posix())

    # Dependency manifests referenced verbatim by the installer's post-install pip hint
    # (gmj-tools.cjs REQUIREMENTS_HINT). Shipped scripts hard-require third-party deps
    # (reportlab, jsonschema, numpy/PIL) that are not in stdlib.
    for req_rel in (
        "scripts/cv/requirements.txt",
        "scripts/contracts/requirements.txt",
        "scripts/preferences/requirements.txt",
    ):
        req = REPO_ROOT / req_rel
        if req.is_file():
            add(req, req_rel)

    # Optional HTML CV templates (WeasyPrint/Jinja2 render path). Lower impact than
    # fonts (the ReportLab --no-template path still works), but a "standalone" payload
    # should carry them so the templated render path is not broken on a clean install.
    templates_dir = REPO_ROOT / "templates"
    if templates_dir.is_dir():
        for f in sorted(templates_dir.rglob("*")):
            if f.is_file():
                add(f, f.relative_to(REPO_ROOT).as_posix())

    return pairs


# --- build --------------------------------------------------------------------

def clean_owned_subdirs() -> None:
    """Remove the payload subtrees this script owns (idempotent rebuild)."""
    for name in OWNED_SUBDIRS:
        target = PAYLOAD_ROOT / name
        if target.exists():
            shutil.rmtree(target)


def copy_payload(pairs: list[tuple[Path, str]]) -> None:
    """Copy each censused source into gmj-core/ preserving relative layout."""
    for src, payload_rel in pairs:
        dest = PAYLOAD_ROOT / payload_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_user_data_samples() -> None:
    """Write the user-data SAMPLE templates (scaffold-if-absent on install)."""
    config_dir = PAYLOAD_ROOT / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    # PII-free synthetic candidate templates.
    for dest_name, content in SAMPLE_CANDIDATE_FILES.items():
        (config_dir / dest_name).write_text(content, encoding="utf-8")
    # PII-free real config verbatim, renamed as `.sample`.
    for src_rel, dest_name in USER_DATA_COPY_AS_SAMPLE.items():
        src = REPO_ROOT / src_rel
        if src.is_file():
            shutil.copy2(src, config_dir / dest_name)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def emit_manifest() -> int:
    """Walk the built gmj-core/ tree and emit gmj-file-manifest.json.

    Shape mirrors .claude/gsd-file-manifest.json verbatim:
    ``{version, timestamp, mode:"full", files:{"gmj-core/<rel>": "<sha256>"}}``.
    Every payload file under gmj-core/ (except the manifest itself) is a key.
    Keys sorted for byte-stable output. Returns the number of files hashed.
    """
    files: dict[str, str] = {}
    for f in sorted(PAYLOAD_ROOT.rglob("*")):
        if not f.is_file():
            continue
        if f == MANIFEST_PATH:
            continue
        key = f.relative_to(REPO_ROOT).as_posix()  # "gmj-core/<rel>"
        files[key] = sha256_of(f)

    manifest = {
        "version": PAYLOAD_VERSION,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
        + f"{_dt.datetime.now(_dt.timezone.utc).microsecond // 1000:03d}Z",
        "mode": "full",
        "files": dict(sorted(files.items())),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(files)


def build() -> int:
    framework_globs = load_framework_globs(DEFAULT_MANIFEST)
    pairs = census_payload(framework_globs)

    PAYLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    clean_owned_subdirs()
    copy_payload(pairs)
    write_user_data_samples()

    VERSION_PATH.write_text(PAYLOAD_VERSION + "\n", encoding="utf-8")

    hashed = emit_manifest()
    print(
        f"gmj-core payload built: {len(pairs)} censused files copied, "
        f"{hashed} files hashed into {MANIFEST_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the standalone gmj-core/ install payload + sha256 manifest."
    )
    parser.parse_args()
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
