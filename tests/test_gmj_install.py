#!/usr/bin/env python3
"""PACKAGE-01/02 clean-directory install contract (RED-first, Wave-0).

The machine-checkable acceptance contract for the ``gmj-core`` payload (18-06) and the
``bin/gmj-tools.cjs`` installer (18-07). It builds a clean temp install root, runs the
installer at it, and asserts the six PACKAGE acceptance checks. This test is EXPECTED to
fail RED right now — ``gmj-core/`` and the installer do not exist yet (they land in Waves
2–3). It fails for the *not-yet-built target*, never a harness error: node-availability is
degraded-to-skip, the payload/manifest absence surfaces as a named assertion, and every
subprocess assertion also checks ``"Traceback" not in result.stderr`` so an unrelated crash
never masquerades as a pass.

The six named checks (each a ``test_*`` function so it is individually reported):
  1. hooks resolve      — every hook command in the installed settings.json resolves to a file.
  2. en+ua CV render    — installed gmj_render_cv.py renders a valid PDF for en (unconditional)
                          and ua (guarded on DejaVu Cyrillic font availability). Structural
                          ``%PDF-`` + pypdf pages>=1 only — NEVER byte-hash (UTC-stamped render).
  3. dry pipeline slice — approved sample draft -> gmj_draft_to_cv_yaml bridge ->
                          gmj_render_cv.py --no-template --lang en -> valid PDF, in the temp dir.
  4. settings paths     — every command path across the full 8-registration set resolves.
  5. idempotent merge   — 2x install is byte-identical AND, seeding a user-owned hook UNDER the
                          existing managed SubagentStop ``.*`` matcher, the user command and BOTH
                          managed gmj hooks coexist (inner-hooks[] dedup/preservation, per matcher).
  6. payload census     — every on-disk gmj-*/gmj_* app file (minus framework_globs minus the two
                          build-time tools) appears as a key in gmj-core/gmj-file-manifest.json.

No pytest — run with ``python3 tests/test_gmj_install.py``. macOS has no ``timeout`` binary, so
subprocess time limits use ``subprocess.run(timeout=...)`` wrappers, never a shell ``timeout``.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INSTALLER_REL = "gmj-core/bin/gmj-tools.cjs"
PAYLOAD_MANIFEST = REPO_ROOT / "gmj-core" / "gmj-file-manifest.json"
OWNERSHIP_MANIFEST = REPO_ROOT / "config" / "ownership-manifest.yaml"

# Committed fixtures reused verbatim (deterministic inputs; outputs go to a temp dir).
TRUTH_CANDIDATE = REPO_ROOT / "tests" / "fixtures" / "truth" / "candidate.truth.sample.yaml"
UA_OVERLAY = REPO_ROOT / "tests" / "fixtures" / "truth" / "candidate.ua.yaml"
SAMPLE_DRAFT = REPO_ROOT / "tests" / "fixtures" / "cv.draft.sample.json"

# Build-time tooling that is DELIBERATELY excluded from the shipped payload (18-06). Encoding
# the exclusion here keeps CHECK 6 from false-failing against that intentional omission.
BUILD_TIME_TOOLS = {
    "scripts/gmj_rebrand.py",
    "scripts/gmj_remove_gsd.py",
}

# The 8 managed hook command basenames the installer must register (settings.json shape).
MANAGED_HOOK_BASENAMES = {
    "gmj-session-bootstrap.sh",              # SessionStart x3 matchers
    "gmj-block-destructive-commands.sh",     # PreToolUse Bash
    "gmj-sources-scope-guard.sh",            # PreToolUse WebSearch|WebFetch
    "gmj-collective-handoff-contract.sh",    # PostToolUse Task
    "gmj-subagent-stop-quality-reminder.sh", # SubagentStop .*  (1 of 2)
    "gmj-validate-envelope.sh",              # SubagentStop .*  (2 of 2)
}


class _Result:
    """Minimal CompletedProcess stand-in so a TimeoutExpired reads like a failed run."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> _Result:
    """Run a subprocess with a python-level timeout (no macOS ``timeout`` binary)."""
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or REPO_ROOT),
            timeout=timeout,
        )
        return _Result(cp.returncode, cp.stdout, cp.stderr)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _Result(124, out, err + "\nTIMEOUT")


def _node() -> str | None:
    return shutil.which("node")


# Cache the shared install so the 6 checks don't reinstall 6x once GREEN.
_INSTALL_CACHE: dict[str, object] = {}


def _install_into(target: Path, timeout: int = 240) -> _Result:
    """Run ``node gmj-core/bin/gmj-tools.cjs install <target>`` from the repo root."""
    node = _node()
    assert node is not None  # callers gate on _node() first
    return run([node, INSTALLER_REL, "install", str(target)], cwd=REPO_ROOT, timeout=timeout)


def _shared_install() -> tuple[Path, _Result]:
    """Install once into a fresh temp root and cache (target_dir, result)."""
    if "target" not in _INSTALL_CACHE:
        target = Path(tempfile.mkdtemp(prefix="gmj-install-"))
        _INSTALL_CACHE["target"] = target
        _INSTALL_CACHE["result"] = _install_into(target)
    return _INSTALL_CACHE["target"], _INSTALL_CACHE["result"]  # type: ignore[return-value]


def _require_install() -> tuple[Path, _Result]:
    """Return the shared install; assert it succeeded (the RED failure point today)."""
    target, result = _shared_install()
    assert result.returncode == 0, (
        f"installer must exit 0 — not built yet? ({INSTALLER_REL}): "
        f"rc={result.returncode} stderr={result.stderr.strip()[:400]}"
    )
    assert "Traceback" not in result.stderr, f"installer crashed: {result.stderr}"
    return target, result


def _installed_settings(target: Path) -> dict:
    sp = target / ".claude" / "settings.json"
    assert sp.is_file(), f"installer did not write {sp}"
    return json.loads(sp.read_text(encoding="utf-8"))


def _hook_command_paths(settings: dict) -> list[str]:
    """Flatten every hook ``command`` string across all events/matchers."""
    cmds: list[str] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return cmds
    for _event, registrations in hooks.items():
        if not isinstance(registrations, list):
            continue
        for reg in registrations:
            for h in (reg or {}).get("hooks", []):
                cmd = h.get("command")
                if isinstance(cmd, str):
                    cmds.append(cmd)
    return cmds


def _resolve_hook_path(command: str, target: Path) -> Path:
    """Resolve a hook command's file path against the installed target dir."""
    # Registered as `$CLAUDE_PROJECT_DIR/.claude/hooks/<name>.sh`; on the target,
    # $CLAUDE_PROJECT_DIR is the install root.
    rel = command.replace("$CLAUDE_PROJECT_DIR", "").replace("${CLAUDE_PROJECT_DIR}", "")
    rel = rel.strip().lstrip("/")
    return target / rel


# --- CHECK 1: hooks resolve --------------------------------------------------

def test_check1_installed_hooks_resolve_to_files() -> None:
    if _node() is None:
        print("SKIP check1: node unavailable — cannot exercise the installer", file=sys.stderr)
        return
    target, _ = _require_install()
    settings = _installed_settings(target)
    cmds = _hook_command_paths(settings)
    assert cmds, "installed settings.json registered no hook commands"
    for cmd in cmds:
        p = _resolve_hook_path(cmd, target)
        assert p.is_file(), f"hook command does not resolve to a file on the target: {cmd} -> {p}"


# --- CHECK 2: en (unconditional) + ua (DejaVu-guarded) CV render -------------

def _assert_valid_pdf(path: Path) -> None:
    assert path.is_file(), f"no PDF written at {path}"
    with open(path, "rb") as fh:
        assert fh.read(5) == b"%PDF-", f"missing %PDF- magic bytes at {path}"
    import pypdf

    assert len(pypdf.PdfReader(str(path)).pages) >= 1, f"rendered PDF has zero pages: {path}"


def test_check2_en_and_ua_cv_render() -> None:
    if _node() is None:
        print("SKIP check2: node unavailable", file=sys.stderr)
        return
    target, _ = _require_install()
    render_script = target / "scripts" / "cv" / "gmj_render_cv.py"
    assert render_script.is_file(), f"installer did not scaffold the render script: {render_script}"

    # en leg — unconditional.
    en_pdf = target / "out-en.pdf"
    en = run(
        [sys.executable, str(render_script), "--config", str(TRUTH_CANDIDATE),
         "--no-template", "--lang", "en", "--out", str(en_pdf)],
        cwd=target,
    )
    assert en.returncode == 0, f"en render must succeed: {en.stderr}"
    assert "Traceback" not in en.stderr, f"en render crashed: {en.stderr}"
    _assert_valid_pdf(en_pdf)

    # ua leg — the PAYLOAD itself must ship the DejaVu Cyrillic font into the target
    # tree. A fontless payload falls back to Helvetica (no Cyrillic glyphs) and produces
    # a structurally-valid-but-glyphless PDF, so guarding on the *source* font dir (which
    # always has it) was a false pass (WR-05). Assert the font landed in the INSTALLED
    # tree so a payload that omits fonts fails here instead of shipping green (CR-01).
    target_font = target / "scripts" / "cv" / "fonts" / "DejaVuSans.ttf"
    assert target_font.is_file(), (
        f"payload did not ship the DejaVu Cyrillic font into the target: {target_font} — "
        f"ua/ru render would silently fall back to Helvetica (no Cyrillic glyphs)"
    )
    assert UA_OVERLAY.is_file(), f"committed ua overlay fixture missing: {UA_OVERLAY}"
    ua_pdf = target / "out-ua.pdf"
    ua = run(
        [sys.executable, str(render_script), "--config", str(TRUTH_CANDIDATE),
         "--no-template", "--lang", "ua", "--out", str(ua_pdf)],
        cwd=target,
    )
    assert ua.returncode == 0, f"ua render must succeed: {ua.stderr}"
    assert "Traceback" not in ua.stderr, f"ua render crashed: {ua.stderr}"
    _assert_valid_pdf(ua_pdf)


# --- CHECK 3: dry pipeline slice ---------------------------------------------

def test_check3_dry_pipeline_slice_renders_pdf() -> None:
    if _node() is None:
        print("SKIP check3: node unavailable", file=sys.stderr)
        return
    target, _ = _require_install()
    check_truth = target / "scripts" / "artifacts" / "gmj_check_truth.py"
    bridge = target / "scripts" / "cv" / "gmj_draft_to_cv_yaml.py"
    render = target / "scripts" / "cv" / "gmj_render_cv.py"
    for s in (check_truth, bridge, render):
        assert s.is_file(), f"installer did not scaffold a pipeline script: {s}"

    approved = run(
        [sys.executable, str(check_truth), "--file", str(SAMPLE_DRAFT),
         "--candidate", str(TRUTH_CANDIDATE)],
        cwd=target,
    )
    assert approved.returncode == 0, f"sample draft must be Gate-A approved: {approved.stderr}"
    assert "Traceback" not in approved.stderr, approved.stderr

    cv_yaml = target / "dry-cv.yaml"
    bridged = run(
        [sys.executable, str(bridge), "--file", str(SAMPLE_DRAFT), "--out", str(cv_yaml)],
        cwd=target,
    )
    assert bridged.returncode == 0, f"bridge must succeed: {bridged.stderr}"
    assert cv_yaml.is_file(), "bridge did not write the intermediate CV-YAML"

    dry_pdf = target / "dry-pipeline.pdf"
    rendered = run(
        [sys.executable, str(render), "--config", str(cv_yaml),
         "--no-template", "--lang", "en", "--out", str(dry_pdf)],
        cwd=target,
    )
    assert rendered.returncode == 0, f"dry-pipeline render must succeed: {rendered.stderr}"
    assert "Traceback" not in rendered.stderr, rendered.stderr
    _assert_valid_pdf(dry_pdf)


# --- CHECK 4: every settings command path resolves (full 8-registration set) --

def test_check4_all_settings_command_paths_resolve() -> None:
    if _node() is None:
        print("SKIP check4: node unavailable", file=sys.stderr)
        return
    target, _ = _require_install()
    settings = _installed_settings(target)
    cmds = _hook_command_paths(settings)
    # Explicit full-set coverage: all 8 managed registrations, every path present on disk.
    assert len(cmds) >= 8, f"expected the full 8-registration hook set, got {len(cmds)}: {cmds}"
    seen_basenames = set()
    for cmd in cmds:
        p = _resolve_hook_path(cmd, target)
        assert p.is_file(), f"settings command path does not resolve: {cmd} -> {p}"
        seen_basenames.add(p.name)
    missing = MANAGED_HOOK_BASENAMES - seen_basenames
    assert not missing, f"installed settings.json missing managed hook registrations: {sorted(missing)}"


# --- CHECK 5: idempotent merge + inner-matcher dedup/preservation ------------

def _seed_target_with_user_hook() -> tuple[Path, str]:
    """Create a target whose settings.json already holds a USER-OWNED hook UNDER the
    managed SubagentStop ``.*`` matcher (a non-gmj command not under .claude/hooks/gmj-*)."""
    target = Path(tempfile.mkdtemp(prefix="gmj-merge-"))
    claude = target / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    user_cmd = "$CLAUDE_PROJECT_DIR/.claude/hooks/user-owned-audit.sh"
    seed = {
        "hooks": {
            "SubagentStop": [
                {"matcher": ".*", "hooks": [{"type": "command", "command": user_cmd}]}
            ]
        }
    }
    (claude / "settings.json").write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")
    return target, user_cmd


def _subagentstop_commands(settings: dict) -> list[str]:
    """All command strings registered under the SubagentStop ``.*`` matcher."""
    out: list[str] = []
    for reg in settings.get("hooks", {}).get("SubagentStop", []) or []:
        if (reg or {}).get("matcher") == ".*":
            for h in reg.get("hooks", []):
                if isinstance(h.get("command"), str):
                    out.append(h["command"])
    return out


def test_check5_idempotent_merge_inner_matcher_dedup() -> None:
    if _node() is None:
        print("SKIP check5: node unavailable", file=sys.stderr)
        return
    target, user_cmd = _seed_target_with_user_hook()
    settings_path = target / ".claude" / "settings.json"

    first = _install_into(target)
    assert first.returncode == 0, (
        f"first install must exit 0 — not built yet? rc={first.returncode} "
        f"stderr={first.stderr.strip()[:400]}"
    )
    assert "Traceback" not in first.stderr, first.stderr
    after_first_bytes = settings_path.read_bytes()

    settings = json.loads(after_first_bytes.decode("utf-8"))
    sub_cmds = _subagentstop_commands(settings)
    # The user entry is preserved (no eviction)...
    assert user_cmd in sub_cmds, f"user-owned SubagentStop hook was evicted: {sub_cmds}"
    # ...and BOTH managed gmj hooks coexist under the SAME matcher (no duplication)...
    for managed in ("gmj-subagent-stop-quality-reminder.sh", "gmj-validate-envelope.sh"):
        matches = [c for c in sub_cmds if c.endswith(managed)]
        assert len(matches) == 1, (
            f"managed hook {managed} must appear exactly once under SubagentStop .*: {sub_cmds}"
        )

    # Second install is a byte-identical no-op (idempotency).
    second = _install_into(target)
    assert second.returncode == 0, f"second install must exit 0: {second.stderr}"
    assert "Traceback" not in second.stderr, second.stderr
    assert settings_path.read_bytes() == after_first_bytes, (
        "settings.json must be byte-identical after a 2nd install (idempotent merge)"
    )


# --- CHECK 6: payload census-completeness (RESEARCH Pitfall 6) ----------------

def _load_framework_globs() -> list[str]:
    import yaml

    data = yaml.safe_load(OWNERSHIP_MANIFEST.read_text(encoding="utf-8")) or {}
    globs = data.get("framework_globs") or []
    return [g for g in globs if isinstance(g, str)]


def _is_framework(rel: str, framework_globs: list[str]) -> bool:
    candidates = {rel, Path(rel).name}
    return any(
        fnmatch.fnmatchcase(cand, glob) for glob in framework_globs for cand in candidates
    )


def _census_manifest_keys() -> set[str]:
    """On-disk app payload -> expected gmj-file-manifest.json keys (gmj-core/<...>).

    Census = gmj-*/gmj_* app files (agents, skills, commands incl. gmj-pipeline/ leaves,
    hooks, scripts) + schemas/*.schema.json, MINUS framework_globs MINUS the two build-time
    tools. NOTE: the ship-vs-scaffold ``config/`` template split is an unresolved Research
    OpenQ owned by 18-06, so config templates are intentionally NOT asserted here — the
    born-gmj census purpose (Pitfall 6) is fully served by the prefixed + schema globs.
    """
    framework_globs = _load_framework_globs()
    keys: set[str] = set()

    def add(disk_rel: str, core_rel: str) -> None:
        if _is_framework(disk_rel, framework_globs) or disk_rel in BUILD_TIME_TOOLS:
            return
        keys.add(f"gmj-core/{core_rel}")

    # .claude/{agents,skills,commands,hooks}/gmj-* -> gmj-core/{cat}/... (strip .claude/)
    for cat in ("agents", "skills", "commands", "hooks"):
        root = REPO_ROOT / ".claude" / cat
        if not root.is_dir():
            continue
        for entry in root.glob("gmj-*"):
            if entry.is_file():
                rel = entry.relative_to(REPO_ROOT).as_posix()
                add(rel, f"{cat}/{entry.name}")
            elif entry.is_dir():
                for f in entry.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(REPO_ROOT).as_posix()
                        sub = f.relative_to(root).as_posix()
                        add(rel, f"{cat}/{sub}")

    # scripts/**/gmj_*.py -> gmj-core/scripts/... (keep scripts/ prefix)
    for f in (REPO_ROOT / "scripts").rglob("gmj_*.py"):
        rel = f.relative_to(REPO_ROOT).as_posix()
        add(rel, rel)  # rel already begins with "scripts/"

    # schemas/*.schema.json -> gmj-core/schemas/...
    schemas = REPO_ROOT / "schemas"
    if schemas.is_dir():
        for f in schemas.glob("*.schema.json"):
            rel = f.relative_to(REPO_ROOT).as_posix()
            add(rel, rel)  # rel already begins with "schemas/"

    return keys


def test_check6_payload_census_completeness() -> None:
    census = _census_manifest_keys()
    assert census, "census computed an empty app payload set — glob logic is broken"
    assert not (BUILD_TIME_TOOLS & {k[len("gmj-core/"):] for k in census}), (
        "build-time tools must be excluded from the census"
    )
    assert PAYLOAD_MANIFEST.is_file(), (
        f"payload manifest not built yet: {PAYLOAD_MANIFEST} (Wave 2/3). "
        f"Census awaiting {len(census)} keys, e.g. {sorted(census)[:5]}"
    )
    manifest = json.loads(PAYLOAD_MANIFEST.read_text(encoding="utf-8"))
    files = manifest.get("files")
    assert isinstance(files, dict), "gmj-file-manifest.json must carry a 'files' map"
    manifest_keys = set(files.keys())
    missing = sorted(census - manifest_keys)
    assert not missing, f"payload manifest is missing {len(missing)} app files: {missing}"

    # Independent completeness oracle for the load-bearing runtime siblings the prefixed
    # census is structurally blind to (fonts, requirements.txt, templates). Without these
    # positive assertions a fontless / dependency-less payload can ship green (WR-06 / CR-01).
    required_runtime_assets = {
        "gmj-core/scripts/cv/fonts/DejaVuSans.ttf",
        "gmj-core/scripts/cv/fonts/DejaVuSans-Bold.ttf",
        "gmj-core/scripts/cv/requirements.txt",
        "gmj-core/scripts/contracts/requirements.txt",
        "gmj-core/scripts/preferences/requirements.txt",
    }
    missing_assets = sorted(required_runtime_assets - manifest_keys)
    assert not missing_assets, (
        f"payload manifest omits load-bearing runtime assets (CR-01): {missing_assets}"
    )
    # HTML CV templates: assert each source template appears in the manifest (if any ship).
    templates_dir = REPO_ROOT / "templates"
    if templates_dir.is_dir():
        for tpl in sorted(templates_dir.rglob("*")):
            if tpl.is_file():
                key = "gmj-core/" + tpl.relative_to(REPO_ROOT).as_posix()
                assert key in manifest_keys, (
                    f"HTML template present in source but missing from payload manifest: {key}"
                )


# --- CHECK 7: build reproducibility (WR-01) ----------------------------------

BUILD_SCRIPT = REPO_ROOT / "scripts" / "gmj_build_payload.py"


def test_check7_double_build_manifest_is_reproducible() -> None:
    """Two builds of the same source tree emit an identical manifest file-set + hashes,
    and with SOURCE_DATE_EPOCH pinned the whole manifest is byte-identical (WR-01).

    Builds into throwaway GMJ_PAYLOAD_ROOT dirs so the committed gmj-core/ is untouched.
    """
    import os

    def build(root: Path) -> bytes:
        env = dict(os.environ)
        env["GMJ_PAYLOAD_ROOT"] = str(root)
        env["SOURCE_DATE_EPOCH"] = "1700000000"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cp = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=180,
        )
        assert cp.returncode == 0, f"build failed: {cp.stderr}"
        assert "Traceback" not in cp.stderr, f"build crashed: {cp.stderr}"
        return (root / "gmj-file-manifest.json").read_bytes()

    a = Path(tempfile.mkdtemp(prefix="gmj-build-a-"))
    b = Path(tempfile.mkdtemp(prefix="gmj-build-b-"))
    m1, m2 = build(a), build(b)
    j1, j2 = json.loads(m1), json.loads(m2)

    assert set(j1["files"]) == set(j2["files"]), (
        "manifest file-set differs between rebuilds (non-reproducible census)"
    )
    assert j1["files"] == j2["files"], "manifest hashes differ between rebuilds"
    assert m1 == m2, "manifest not byte-identical under a pinned SOURCE_DATE_EPOCH"
    # The build-time installer must NOT churn the census (it is authored in place).
    assert "gmj-core/bin/gmj-tools.cjs" not in j1["files"], (
        "bin/ installer must be excluded from the manifest census (rebuild idempotency)"
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
