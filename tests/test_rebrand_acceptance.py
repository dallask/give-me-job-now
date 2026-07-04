#!/usr/bin/env python3
"""Acceptance gate for the gmj- rebrand sweep (REBRAND-02): grep-0 + hooks-resolve + hook-fire.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_rebrand_acceptance.py``. This IS a real gate in the ``tests/test_*.py``
glob. It proves the three machine-checkable halves of REBRAND-02 after each wave:

  1. ``test_grep0_selfscoped`` — for every app entry whose NEW-named file is already on disk
     (i.e. that wave has run), NO reference to its OLD name survives anywhere in the app tree.
     SPLIT match strategy (driven off config/ownership-manifest.yaml via scripts/gmj_rebrand.py's
     ``build_rules`` — the SAME source of truth the rename engine uses, so grep and the rename can
     never drift):
       * distinctive dash-names (agents/skills/hooks + single-file commands) are grepped as
         DELIMITED tokens across the WHOLE app tree — catching filename tokens (gate_<old>_cv_1.json),
         JSON gate keys, DAG node ids, dispatch names and frontmatter — while skipping the
         correctly-renamed ``gmj-<old>`` form and the stable ``<old>.log`` runtime-log filenames;
       * prose-colliding script stems (route/extract/render_cv …) stay reference-form-scoped
         (``from <stem> import`` / ``import <stem>`` / ``<stem>.py``), never grepped bare;
       * a generic-word DIRECTORY-GROUP command (``pipeline`` — homographic with ``scripts/pipeline/``,
         ``.pipeline/`` runtime state, ``config/pipeline.*.yaml`` and ``pipeline_dir`` identifiers)
         is command-path-scoped (``commands/<old>`` / ``/<old>/<sub>`` / ``/<old>:``), never grepped
         bare — so the acceptance grep is a REAL backstop, not a vacuous pass over corrupted homographs.
     Types not yet renamed are reported pending (the file is green throughout the sweep and
     fully asserting once every wave has run).
  2. ``test_grep0_backstop_fires_and_is_precise`` — a NEGATIVE self-test that PLANTS a surviving
     old filename token + JSON gate key and proves the distinctive scan goes RED on them, with a
     positive control proving a correctly-renamed ``gmj-<old>`` token never trips it (so the gate
     is neither vacuously-green nor permanently-red).
  3. ``test_hooks_resolve`` / ``test_hooks_fire_smoke`` — every ``.claude/settings.json`` hook
     ``command`` path resolves on disk AND subprocess-invokes + gates deterministically (benign
     stdin -> exit 0; a hostile input to each security hook -> block/exit 2). Live in-session
     firing is the DV-20 deferral handled in 17-08.

HARD CONSTRAINT: pure file parsing + a bounded subprocess smoke of the hook scripts only. It
executes ZERO renamed pipeline artifacts and asserts ZERO pipeline behavior/scores.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
# Single source of truth for the rename forms + tree walk: the engine that DRIVES the rename.
# Importing it (rather than re-deriving regexes) guarantees the acceptance grep and the actual
# rewrite can never diverge. The engine is dependency-free (no cross-script import), so this
# import stays valid through every wave.
import gmj_rebrand as R  # noqa: E402

SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# --- hook smoke fixtures (keyed on the gmj-STRIPPED basename so they survive the hooks wave) ---
# Benign stdin that drives each hook down its no-op / skip path -> exit 0.
_BENIGN_STDIN = {
    "session-bootstrap": "{}",
    "block-destructive-commands": '{"tool_name":"Read","tool_input":{}}',
    "sources-scope-guard": '{"tool_name":"Read","tool_input":{}}',
    "collective-handoff-contract": '{"tool_input":{"subagent_type":"general-purpose"}}',
    "subagent-stop-quality-reminder": "{}",
    "validate-envelope": "{}",
}
# Hostile stdin that MUST make each security hook block (exit 2) — proves it still fires/gates
# post-rename (Pitfall 5: a stale settings.json path would make the guard silently fail open).
_GATING_STDIN = {
    "block-destructive-commands": ('{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/gmj-smoke"}}', 2),
    "sources-scope-guard": ('{"tool_name":"WebFetch","tool_input":{"url":"https://evil.example.invalid/x"}}', 2),
}


# --------------------------------------------------------------------------- grep-0

def _new_present(entry: dict) -> bool:
    """True once this entry's NEW-named file/dir exists on disk (its wave has run)."""
    return entry["new_path"].exists()


def _active_entries_by_type() -> "tuple[dict, dict, list[str]]":
    """(index, {type: renamed-entries}, [pending types]) — pending = wave not yet run."""
    manifest = R.load_manifest(R.DEFAULT_MANIFEST)
    index = R.build_app_index(manifest)
    active: dict[str, list[dict]] = {}
    pending: list[str] = []
    for atype, entries in index.items():
        done = [e for e in entries if _new_present(e)]
        active[atype] = done
        if not done:
            pending.append(atype)
    return index, active, pending


def test_grep0_selfscoped() -> None:
    """No app OLD name survives anywhere in the app tree, self-scoped to already-renamed types."""
    _index, active, pending = _active_entries_by_type()
    files = R.iter_app_files()
    total_active = 0
    for atype, entries in active.items():
        if not entries:
            continue
        total_active += len(entries)
        rules = R.build_rules(entries, atype)
        sites = R.collect_sites(rules, files)
        shown = "; ".join(
            f"{R._rel(f)}:{ln}[{old}]" if ln else f"{R._rel(f)}(name)[{old}]"
            for f, ln, old in sites[:25]
        )
        assert not sites, f"{atype}: {len(sites)} surviving old-name reference(s): {shown}"
    print(f"grep0: {total_active} renamed entr(y/ies) asserted clean; pending (unrenamed) types: {pending}")


def test_grep0_backstop_fires_and_is_precise() -> None:
    """NEGATIVE self-test: the distinctive-name scan MUST fire on a planted old token, and MUST
    NOT fire on a correctly-renamed gmj- token (proves the backstop is real, mirrors the
    gate-cluster tripwire's negative proof)."""
    old, new = "fit-evaluator", "gmj-fit-evaluator"
    entry = {"old": old, "new": new, "old_path": REPO_ROOT / "x", "new_path": REPO_ROOT / "y"}
    rules = R.build_rules([entry], "agents")  # dash-type (distinctive) rules
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        planted_name = dp / f"gate_{old}_cv_1.json"     # surviving old FILENAME token
        planted_name.write_text('{"ok": true}\n', encoding="utf-8")
        planted_key = dp / "state.json"                 # surviving old JSON gate KEY
        planted_key.write_text(f'{{"gate_results": {{"{old}": "pass"}}}}\n', encoding="utf-8")
        control = dp / f"gate_{new}_cv_1.json"          # correctly-renamed control
        control.write_text(f'{{"gate_results": {{"{new}": "pass"}}}}\n', encoding="utf-8")

        sites = R.collect_sites(rules, sorted([planted_name, planted_key, control]))
        name_hits = {Path(f).name for f, ln, _ in sites if ln == 0}
        key_hits = {Path(f).name for f, ln, _ in sites if ln > 0}

        assert planted_name.name in name_hits, "backstop MISSED the planted old FILENAME token"
        assert planted_key.name in key_hits, "backstop MISSED the planted old JSON gate KEY"
        assert control.name not in name_hits, "backstop FALSE-fired on a correctly-renamed gmj- filename"
        assert control.name not in key_hits, "backstop FALSE-fired on a correctly-renamed gmj- JSON key"


# --------------------------------------------------------------------------- engine hardening

def _init_git_repo(root: Path) -> None:
    """Init a throwaway git repo (isolated config) for an apply-staging assertion."""
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.email", "t@example.invalid"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(root), check=True)


def test_apply_stages_content_rewrite_of_renamed_file() -> None:
    """CR-01: after git mv + rewrite, the CONTENT rewrite of a renamed file must be STAGED.

    Reproduces the exact quirk the review flagged: ``git mv`` stages a rename from the
    pre-rewrite index blob, leaving the working-tree content edit unstaged. Proves
    ``R.stage_all()`` closes the gap — ``git diff --cached`` for the renamed destination shows
    the rewritten line (NOT a 0-line pure rename)."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d).resolve()
        _init_git_repo(repo)
        scripts = repo / "scripts"
        scripts.mkdir()
        mod = scripts / "route.py"
        # A file that BOTH gets renamed AND has an internal reference rewritten (its own .py name).
        mod.write_text("# see route.py for details\nvalue = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True)

        entry = {"old": "route", "new": "gmj_route",
                 "old_path": mod, "new_path": scripts / "gmj_route.py"}
        rules = R._script_rules([entry])
        orig_root = R.REPO_ROOT
        R.REPO_ROOT = repo
        try:
            changed = R.apply_rewrites(rules, [mod])
            assert changed == 1, "apply_rewrites did not rewrite the renamed file's content"
            R.git_mv(entry["old_path"], entry["new_path"])
            R.stage_all()
        finally:
            R.REPO_ROOT = orig_root

        diff = subprocess.run(
            ["git", "diff", "--cached"], cwd=str(repo), capture_output=True, text=True, check=True
        ).stdout
        assert "gmj_route.py" in diff, "renamed destination absent from staged diff"
        # The content edit — not just the rename — must be in the index.
        assert "-# see route.py for details" in diff, "old content line not staged as removed"
        assert "+# see gmj_route.py for details" in diff, "rewritten content line not staged as added"


def _apply_script_rules(entry: dict, text: str) -> str:
    """Run the script reference-form rules over one text blob (test helper)."""
    out = text
    for pat, repl, _e in R._script_rules([entry]):
        out = pat.sub(lambda m, r=repl: r, out)
    return out


def test_aliased_import_rewrite_preserves_alias() -> None:
    """WR-03: ``import <stem> as <alias>`` rewrites to valid Python, preserving the alias."""
    import ast

    entry = {"old": "extract", "new": "gmj_extract",
             "old_path": REPO_ROOT / "x", "new_path": REPO_ROOT / "y"}

    # Aliased import: rewrite the module name only, keep the alias — no double ``as``.
    aliased = _apply_script_rules(entry, "import extract as ex\n")
    assert aliased == "import gmj_extract as ex\n", f"aliased import corrupted: {aliased!r}"
    ast.parse(aliased)  # must be valid Python (the old bug produced a SyntaxError here)

    # Plain import (no alias): still gets the compat alias binding the old stem.
    plain = _apply_script_rules(entry, "import extract\n")
    assert plain == "import gmj_extract as extract\n", f"plain import wrong: {plain!r}"
    ast.parse(plain)

    # from-import form and prose are unaffected.
    assert _apply_script_rules(entry, "from extract import foo\n") == "from gmj_extract import foo\n"
    assert _apply_script_rules(entry, "we extract the value\n") == "we extract the value\n"
    # A longer stem that merely starts with the old name must not be touched.
    assert _apply_script_rules(entry, "import extractor as e\n") == "import extractor as e\n"


# --------------------------------------------------------------------------- hooks

def _registered_hook_paths() -> list[str]:
    """Repo-relative paths of every hook `command` registered in settings.json."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    paths: list[str] = []
    for event in settings["hooks"].values():
        for group in event:
            for h in group.get("hooks", []):
                paths.append(h["command"].replace("$CLAUDE_PROJECT_DIR/", ""))
    return paths


def _hook_key(rel_path: str) -> str:
    """The gmj-STRIPPED basename (no .sh) so smoke fixtures survive the hooks-wave rename."""
    stem = Path(rel_path).stem
    return stem[len("gmj-"):] if stem.startswith("gmj-") else stem


def test_hooks_resolve() -> None:
    """Every settings.json hook command path resolves on disk (Pitfall 5 — no stale hook path)."""
    paths = _registered_hook_paths()
    assert len(paths) >= 6, f"expected >=6 hook registrations, got {len(paths)}"
    missing = [p for p in paths if not (REPO_ROOT / p).is_file()]
    assert not missing, f"settings.json hook paths do not resolve: {missing}"
    # The 6 app hooks must all be registered (rename-robust: keyed on the stripped basename).
    keys = {_hook_key(p) for p in paths}
    expected = set(_BENIGN_STDIN)
    assert expected <= keys, f"settings.json missing app-hook registration(s): {sorted(expected - keys)}"


def test_hooks_fire_smoke() -> None:
    """Each registered hook subprocess-runs + gates deterministically (proves it executes post-rename).

    Benign stdin -> exit 0; a hostile input to each security hook -> block/exit 2. Live in-session
    firing (SessionStart banner, real destructive-command block, live WebSearch scope-guard,
    malformed SubagentStop envelope) is the DV-20 deferral verified in 17-08.
    """
    paths = sorted(set(_registered_hook_paths()))
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = d  # keep hook log writes out of the repo tree
        for rel in paths:
            hook = REPO_ROOT / rel
            assert hook.is_file(), f"registered hook does not resolve: {rel}"
            key = _hook_key(rel)
            stdin = _BENIGN_STDIN.get(key, "{}")
            proc = subprocess.run(
                ["bash", str(hook)], input=stdin.encode(), cwd=str(REPO_ROOT),
                env=env, capture_output=True, timeout=30,
            )
            assert proc.returncode == 0, (
                f"benign smoke of {rel} exited {proc.returncode} (expected 0): "
                f"{proc.stderr.decode()[-200:]}"
            )
            if key in _GATING_STDIN:
                hostile, expect_rc = _GATING_STDIN[key]
                blocked = subprocess.run(
                    ["bash", str(hook)], input=hostile.encode(), cwd=str(REPO_ROOT),
                    env=env, capture_output=True, timeout=30,
                )
                assert blocked.returncode == expect_rc, (
                    f"security hook {rel} did NOT gate a hostile input: exited "
                    f"{blocked.returncode}, expected {expect_rc} (Pitfall 5 — fail-open risk)"
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
