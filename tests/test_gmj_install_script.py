#!/usr/bin/env python3
"""INSTALL-01/02/03/04 end-to-end contract for gmj-core/bin/install.sh (RED-first, Wave 0).

The machine-checkable acceptance contract for the one-script installer
(``gmj-core/bin/install.sh``). Mirrors ``tests/test_gmj_install.py``'s no-framework
``main()``/``test_*`` auto-collection convention, ``_Result`` stand-in, and ``run()``
subprocess-timeout wrapper, extended with an optional ``env`` parameter (needed to build a
"shadow PATH" that hides exactly one prerequisite binary, and to override the fresh-clone
``GMJ_REPO_URL``/``GMJ_INSTALL_DIR`` env vars).

This test is EXPECTED to fail RED right now — ``gmj-core/bin/install.sh`` does not exist yet
(it lands in Task 2). It fails for the *not-yet-built target*, never a harness crash: every
``bash <install.sh>`` invocation surfaces as a named ``FAIL test_*`` assertion (a
"no such file or directory"-class subprocess failure, never an unhandled exception escaping
``main()``), and the two static/grep tests (8-9) surface a ``FileNotFoundError`` the same way.

No pytest — run with ``python3 tests/test_gmj_install_script.py``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH_REL = Path("gmj-core") / "bin" / "install.sh"


class _Result:
    """Minimal CompletedProcess stand-in so a TimeoutExpired reads like a failed run."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: int = 180,
) -> _Result:
    """Run a subprocess with a python-level timeout (no macOS ``timeout`` binary).

    Extends ``tests/test_gmj_install.py``'s ``run()`` with an ``env`` parameter, forwarded
    straight through to ``subprocess.run`` — needed for the shadow-PATH and
    ``GMJ_REPO_URL``-override scenarios below.
    """
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or REPO_ROOT),
            env=env,
            timeout=timeout,
        )
        return _Result(cp.returncode, cp.stdout, cp.stderr)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _Result(124, out, err + "\nTIMEOUT")


def make_shadow_path(hide: set[str]) -> str:
    """Build a PATH containing every binary currently resolvable, except those named in
    `hide` (matched by basename). Preserves PATH ordering precedence (first match wins).

    Copied from 37-RESEARCH.md's Code Examples verbatim — solves Pitfall 3 (``git`` and
    ``dirname`` share ``/usr/bin`` on Debian-family machines, so a naive "strip a whole PATH
    directory" test would also break the script's own ability to run).
    """
    shadow = Path(tempfile.mkdtemp(prefix="gmj-shadow-path-"))
    seen: set[str] = set()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        d = Path(directory)
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            if entry.name in seen or entry.name in hide:
                continue
            if not os.access(entry, os.X_OK):
                continue
            try:
                (shadow / entry.name).symlink_to(entry.resolve())
                seen.add(entry.name)
            except OSError:
                continue
    return str(shadow)


# Module-level cache so every run-in-place-based test below shares one local (non-network)
# clone of this repo's own working tree, rather than re-cloning per test.
_SCRATCH_CACHE: dict[str, Path] = {}


def _scratch_checkout() -> Path:
    """Return a shared local clone of REPO_ROOT (an ordinary non-bare git repo — no
    SSH/network needed), caching the resulting Path across calls."""
    if "path" not in _SCRATCH_CACHE:
        tempdir = Path(tempfile.mkdtemp(prefix="gmj-scratch-checkout-"))
        repo = tempdir / "repo"
        cp = subprocess.run(
            ["git", "clone", str(REPO_ROOT), str(repo)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert cp.returncode == 0, f"local scratch clone of REPO_ROOT failed: {cp.stderr}"
        _SCRATCH_CACHE["path"] = repo
    return _SCRATCH_CACHE["path"]


def _snapshot_yaml_bytes(config_dir: Path) -> dict[str, bytes]:
    """Map every ``*.yaml`` file under ``config_dir`` (recursive, relative-path keys) to its
    raw bytes — the idempotency oracle for INSTALL-02."""
    out: dict[str, bytes] = {}
    if not config_dir.is_dir():
        return out
    for f in sorted(config_dir.rglob("*.yaml")):
        if f.is_file():
            out[str(f.relative_to(config_dir))] = f.read_bytes()
    return out


# --- Test 1: run-in-place install twice is idempotent (INSTALL-01/02) --------

def test_run_in_place_install_twice_idempotent() -> None:
    if shutil.which("node") is None:
        print("SKIP test_run_in_place_install_twice_idempotent: node unavailable", file=sys.stderr)
        return

    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL
    config_dir = checkout / "config"

    before = _snapshot_yaml_bytes(config_dir)

    first = run(["bash", str(install_sh)], cwd=checkout, timeout=300)
    assert first.returncode == 0, (
        f"first install must exit 0 — not built yet? rc={first.returncode} "
        f"stderr={first.stderr.strip()[:800]}"
    )
    assert "Traceback" not in first.stderr, f"install.sh crashed: {first.stderr}"

    venv_dir = checkout / ".venv"
    assert venv_dir.is_dir(), f"install.sh did not create {venv_dir}"

    after_first = _snapshot_yaml_bytes(config_dir)
    assert after_first == before, (
        "config/*.yaml changed on the first install — must scaffold-if-absent, never clobber "
        "(INSTALL-02)"
    )

    # Canary proves .venv is REUSED (not deleted+recreated) on the second run.
    canary = venv_dir / "GMJ_CANARY"
    canary.write_text("gmj-canary\n", encoding="utf-8")

    second = run(["bash", str(install_sh)], cwd=checkout, timeout=300)
    assert second.returncode == 0, f"second install must exit 0: {second.stderr.strip()[:800]}"
    assert "Traceback" not in second.stderr, f"install.sh crashed on 2nd run: {second.stderr}"

    after_second = _snapshot_yaml_bytes(config_dir)
    assert after_second == before, (
        "config/*.yaml changed on the second install — idempotency violated (INSTALL-02)"
    )
    assert canary.is_file() and canary.read_text(encoding="utf-8") == "gmj-canary\n", (
        ".venv was deleted+recreated rather than reused across the second install (INSTALL-02)"
    )


# --- Tests 2-5: one prerequisite hidden at a time (INSTALL-03) ---------------

def _run_install_with_hidden(tool: str, timeout: int = 30) -> _Result:
    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL
    env = dict(os.environ, PATH=make_shadow_path({tool}))
    return run(["bash", str(install_sh)], cwd=checkout, env=env, timeout=timeout)


def _assert_clean_prerequisite_failure(result: _Result, tool: str) -> None:
    assert result.returncode == 1, (
        f"expected exit 1 with {tool!r} hidden from PATH: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    assert tool in result.stderr, f"missing-{tool} report must name {tool!r}: {result.stderr}"
    assert "Traceback" not in result.stderr, result.stderr
    assert "dirname: command not found" not in result.stderr, (
        f"unrelated crash string leaked into the aggregated report: {result.stderr}"
    )
    assert "syntax error" not in result.stderr, (
        f"bash syntax-error text leaked into the aggregated report: {result.stderr}"
    )


def test_prerequisite_missing_git_aggregates_and_exits_nonzero() -> None:
    _assert_clean_prerequisite_failure(_run_install_with_hidden("git"), "git")


def test_prerequisite_missing_python3_aggregates_and_exits_nonzero() -> None:
    _assert_clean_prerequisite_failure(_run_install_with_hidden("python3"), "python3")


def test_prerequisite_missing_node_aggregates_and_exits_nonzero() -> None:
    _assert_clean_prerequisite_failure(_run_install_with_hidden("node"), "node")


def test_prerequisite_missing_npx_aggregates_and_exits_nonzero() -> None:
    _assert_clean_prerequisite_failure(_run_install_with_hidden("npx"), "npx")


# --- Test 6: multiple missing prerequisites are aggregated together ----------

def test_missing_prerequisites_are_all_reported_together() -> None:
    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL
    env = dict(os.environ, PATH=make_shadow_path({"node", "npx"}))
    result = run(["bash", str(install_sh)], cwd=checkout, env=env, timeout=30)
    assert result.returncode == 1, (
        f"expected exit 1 with node+npx both hidden: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    assert "node" in result.stderr, f"aggregated report must name node: {result.stderr}"
    assert "npx" in result.stderr, f"aggregated report must name npx: {result.stderr}"


# --- Test 7: fresh-clone mode via local GMJ_REPO_URL override (INSTALL-01) ---

def test_fresh_clone_mode_local_repo_url_override() -> None:
    install_sh_src = REPO_ROOT / INSTALL_SH_REL

    isolated_dir = Path(tempfile.mkdtemp(prefix="gmj-freshclone-isolated-"))
    check = subprocess.run(
        ["git", "-C", str(isolated_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        print(
            "SKIP test_fresh_clone_mode_local_repo_url_override: isolated temp dir "
            "unexpectedly has a .git ancestor",
            file=sys.stderr,
        )
        return

    isolated_install_sh = isolated_dir / "install.sh"
    isolated_install_sh.write_bytes(install_sh_src.read_bytes())
    isolated_install_sh.chmod(isolated_install_sh.stat().st_mode | 0o111)

    workdir = Path(tempfile.mkdtemp(prefix="gmj-freshclone-workdir-"))
    env = dict(os.environ, GMJ_REPO_URL=str(REPO_ROOT), GMJ_INSTALL_DIR="cloned-repo")
    result = run(["bash", str(isolated_install_sh)], cwd=workdir, env=env, timeout=300)
    assert result.returncode == 0, (
        f"fresh-clone install must exit 0: {result.stderr.strip()[:800]}"
    )
    assert "Traceback" not in result.stderr, f"fresh-clone install crashed: {result.stderr}"

    cloned = workdir / "cloned-repo"
    assert (cloned / "gmj-core" / "bin" / "gmj-tools.cjs").is_file(), (
        "fresh-clone mode did not land gmj-tools.cjs into the cloned repo"
    )
    assert (cloned / ".venv").is_dir(), "fresh-clone mode did not bootstrap .venv"


# --- Test 8: install.sh never references the hook-registration file (INSTALL-04) --

def test_install_sh_never_references_hook_registration_file() -> None:
    install_sh = REPO_ROOT / INSTALL_SH_REL
    text = install_sh.read_text(encoding="utf-8")
    assert "settings.json" not in text, (
        "install.sh must delegate all settings.json handling to gmj-tools.cjs, never "
        "reference it directly (INSTALL-04)"
    )


# --- Test 9: quoting + no-dynamic-execution static check (Security Domain V5) --

_DYNAMIC_EXEC_RE = re.compile(r"\beval\b")


def test_install_sh_quotes_repo_url_and_install_dir_overrides() -> None:
    install_sh = REPO_ROOT / INSTALL_SH_REL
    text = install_sh.read_text(encoding="utf-8")
    assert '"$REPO_URL"' in text, (
        'install.sh must double-quote every "$REPO_URL" expansion (V5)'
    )
    assert '"$INSTALL_DIR"' in text, (
        'install.sh must double-quote every "$INSTALL_DIR" expansion (V5)'
    )
    match = _DYNAMIC_EXEC_RE.search(text)
    assert match is None, (
        f"install.sh must never dynamically/indirectly execute a string "
        f"(found {match.group(0)!r} — V5)"
    )


# --- Test 10: CR-01 regression — GMJ_REPO_URL flag-injection into git clone ---

def test_fresh_clone_rejects_option_like_repo_url() -> None:
    """Regression for CR-01: a GMJ_REPO_URL value starting with '-' must never be
    parsed by git as a flag (e.g. --upload-pack=<cmd> achieving command execution).
    Uses a local marker-file technique — no real command execution against a real
    remote, only a local marker path that must never be created."""
    install_sh_src = REPO_ROOT / INSTALL_SH_REL

    isolated_dir = Path(tempfile.mkdtemp(prefix="gmj-cr01-isolated-"))
    check = subprocess.run(
        ["git", "-C", str(isolated_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        print(
            "SKIP test_fresh_clone_rejects_option_like_repo_url: isolated temp dir "
            "unexpectedly has a .git ancestor",
            file=sys.stderr,
        )
        return

    isolated_install_sh = isolated_dir / "install.sh"
    isolated_install_sh.write_bytes(install_sh_src.read_bytes())
    isolated_install_sh.chmod(isolated_install_sh.stat().st_mode | 0o111)

    workdir = Path(tempfile.mkdtemp(prefix="gmj-cr01-workdir-"))
    marker = workdir / "PWNED_marker"
    payload = f"--upload-pack=touch {marker};"
    env = dict(os.environ, GMJ_REPO_URL=payload, GMJ_INSTALL_DIR="cr01-target")
    result = run(["bash", str(isolated_install_sh)], cwd=workdir, env=env, timeout=30)

    assert not marker.exists(), (
        "CR-01 regression: injected --upload-pack command executed and created "
        f"{marker} — GMJ_REPO_URL flag-injection is not blocked"
    )
    assert result.returncode != 0, (
        "a bare option-like GMJ_REPO_URL must fail as a literal (non-existent) repo "
        f"URL, not succeed: rc={result.returncode}"
    )


# --- Test 11: CR-02 regression — pre-planted symlink at the install target -----

def test_fresh_clone_refuses_preexisting_symlink_install_dir() -> None:
    """Regression for CR-02: a pre-existing symlink at GMJ_INSTALL_DIR must be
    rejected, not silently followed by git clone into wherever it points."""
    install_sh_src = REPO_ROOT / INSTALL_SH_REL

    isolated_dir = Path(tempfile.mkdtemp(prefix="gmj-cr02-isolated-"))
    check = subprocess.run(
        ["git", "-C", str(isolated_dir), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        print(
            "SKIP test_fresh_clone_refuses_preexisting_symlink_install_dir: isolated "
            "temp dir unexpectedly has a .git ancestor",
            file=sys.stderr,
        )
        return

    isolated_install_sh = isolated_dir / "install.sh"
    isolated_install_sh.write_bytes(install_sh_src.read_bytes())
    isolated_install_sh.chmod(isolated_install_sh.stat().st_mode | 0o111)

    workdir = Path(tempfile.mkdtemp(prefix="gmj-cr02-workdir-"))
    victim = Path(tempfile.mkdtemp(prefix="gmj-cr02-victim-"))
    link_name = "cr02-target"
    (workdir / link_name).symlink_to(victim, target_is_directory=True)

    env = dict(os.environ, GMJ_REPO_URL=str(REPO_ROOT), GMJ_INSTALL_DIR=link_name)
    result = run(["bash", str(isolated_install_sh)], cwd=workdir, env=env, timeout=30)

    assert result.returncode != 0, (
        "install.sh must refuse to clone into a pre-existing symlink install target, "
        f"not silently follow it: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    assert not any(victim.iterdir()), (
        "CR-02 regression: install.sh wrote through the pre-planted symlink into "
        f"{victim} instead of refusing"
    )
    assert (workdir / link_name).is_symlink(), (
        "the pre-existing symlink must remain untouched after install.sh refuses"
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
