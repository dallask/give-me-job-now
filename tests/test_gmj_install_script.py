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


# --- Test 12: full requirements aggregation installs every requirements file (INSTALL-01) --

def test_full_requirements_aggregation_installs_all_files() -> None:
    """Regression proof for the aggregation-loop fix: install.sh must install packages from
    ALL of scripts/*/requirements.txt and scripts/requirements-*.txt (9 files today), not
    just the 4 previously hard-coded ones. Checks one representative package unique to each
    of the four previously-missing requirements files, plus requirements-cleanup.txt."""
    if shutil.which("node") is None:
        print("SKIP test_full_requirements_aggregation_installs_all_files: node unavailable", file=sys.stderr)
        return

    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL

    result = run(["bash", str(install_sh)], cwd=checkout, timeout=300)
    assert result.returncode == 0, (
        f"install must exit 0: rc={result.returncode} stderr={result.stderr.strip()[:800]}"
    )
    assert "Traceback" not in result.stderr, f"install.sh crashed: {result.stderr}"

    venv_python = checkout / ".venv" / "bin" / "python"
    assert venv_python.is_file(), f"install.sh did not create {venv_python}"

    # One representative package per previously-missing requirements file:
    #   scripts/offers/requirements.txt      -> firecrawl-py (module: firecrawl)
    #   scripts/runtime/requirements.txt     -> claude-agent-sdk (module: claude_agent_sdk)
    #   scripts/requirements-cleanup.txt     -> questionary (module: questionary)
    #   scripts/publish/requirements.txt     -> python-semantic-release (no top-level import;
    #                                          checked via `pip show`)
    import_check = run(
        [str(venv_python), "-c", "import firecrawl, claude_agent_sdk, questionary; print('OK')"],
        cwd=checkout,
        timeout=30,
    )
    assert import_check.returncode == 0, (
        "expected firecrawl, claude_agent_sdk, questionary all importable post-install "
        f"(aggregation bug regression): rc={import_check.returncode} "
        f"stdout={import_check.stdout.strip()[:400]} stderr={import_check.stderr.strip()[:400]}"
    )
    assert "OK" in import_check.stdout, import_check.stdout

    pip_show = run(
        [str(venv_python), "-m", "pip", "show", "python-semantic-release"],
        cwd=checkout,
        timeout=30,
    )
    assert pip_show.returncode == 0, (
        "expected python-semantic-release (scripts/publish/requirements.txt) installed "
        f"post-install: rc={pip_show.returncode} stderr={pip_show.stderr.strip()[:400]}"
    )


# --- Test 13: Python version floor rejects an old interpreter (INSTALL-03) ---

def test_python_version_floor_rejects_old_interpreter() -> None:
    """A shadow-PATH python3 shim reporting a version below the 3.9 floor must cause
    install.sh to exit 1, name the required minimum version in stderr, and leave no .venv
    directory behind — BEFORE any venv is created.

    Uses a dedicated fresh checkout (git clone, like tests 7/10/11) rather than the shared
    `_scratch_checkout()` cache — other tests in this module install into that shared
    checkout's `.venv`, which would make the "no .venv left behind" assertion meaningless
    if run after them."""
    checkout = Path(tempfile.mkdtemp(prefix="gmj-oldpython-checkout-"))
    clone = subprocess.run(
        ["git", "clone", str(REPO_ROOT), str(checkout)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert clone.returncode == 0, f"dedicated checkout clone failed: {clone.stderr}"
    install_sh = checkout / INSTALL_SH_REL

    shadow = Path(tempfile.mkdtemp(prefix="gmj-oldpython-shadow-"))
    shim = shadow / "python3"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "--version" ]; then\n'
        '  echo "Python 3.8.10"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "-c" ]; then\n'
        "  exit 1\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | 0o111)

    # Prepend the shim directory ahead of the real PATH so the fake python3 shadows the
    # real interpreter, while every other binary (git, node, npx, bash itself) still
    # resolves normally (make_shadow_path()'s precedence-preserving approach, applied here
    # as a minimal standalone prefix since only python3 needs shadowing).
    env = dict(os.environ, PATH=f"{shadow}{os.pathsep}{os.environ.get('PATH', '')}")

    venv_dir = checkout / ".venv"
    # Guard: fail loudly (not silently pass) if a leftover .venv from a prior test run
    # would make the "no .venv left behind" assertion meaningless.
    assert not venv_dir.is_dir(), f"pre-existing {venv_dir} would invalidate this test"

    result = run(["bash", str(install_sh)], cwd=checkout, env=env, timeout=30)
    assert result.returncode == 1, (
        f"expected exit 1 with an old python3 shim on PATH: rc={result.returncode} "
        f"stdout={result.stdout.strip()[:400]} stderr={result.stderr.strip()[:400]}"
    )
    assert "3.9" in result.stderr, (
        f"aggregated report must name the required minimum version (3.9): {result.stderr}"
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert not venv_dir.is_dir(), (
        "install.sh must not create .venv when the python3 version-floor check fails "
        f"(found {venv_dir})"
    )


# --- Test 14: post-install smoke check is present (static/grep check) --------

def test_post_install_smoke_check_present() -> None:
    """Static assertion (same style as tests 8/9): install.sh must contain an import-based
    smoke check block, positioned after the pip-install loop and before the gmj-tools.cjs
    delegate call."""
    install_sh = REPO_ROOT / INSTALL_SH_REL
    text = install_sh.read_text(encoding="utf-8")

    pip_loop_idx = text.find("scripts/*/requirements.txt")
    assert pip_loop_idx != -1, "install.sh must contain the requirements-aggregation loop"

    smoke_check_idx = text.find("import yaml")
    assert smoke_check_idx != -1, (
        "install.sh must contain a post-install import-based smoke check (e.g. "
        "'import yaml, jsonschema, ...')"
    )
    assert smoke_check_idx > pip_loop_idx, (
        "the post-install smoke check must come AFTER the pip-install aggregation loop"
    )

    delegate_idx = text.find("gmj-tools.cjs install")
    assert delegate_idx != -1, "install.sh must contain the gmj-tools.cjs install delegate call"
    assert smoke_check_idx < delegate_idx, (
        "the post-install smoke check must come BEFORE the gmj-tools.cjs delegate call"
    )


# --- Test 15 (Test A): non-TTY output has zero ANSI escape bytes (wizard UI) ---

def test_non_tty_output_has_zero_ansi_escape_bytes() -> None:
    """Redirecting stdout to a file guarantees `[ -t 1 ]` is false. The wizard UI layer must
    detect this and emit plain text — zero `\\x1b`/`\\033` bytes anywhere in stdout."""
    if shutil.which("node") is None:
        print("SKIP test_non_tty_output_has_zero_ansi_escape_bytes: node unavailable", file=sys.stderr)
        return

    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL

    out_file = Path(tempfile.mkdtemp(prefix="gmj-nontty-out-")) / "stdout.txt"
    with out_file.open("wb") as fh:
        cp = subprocess.run(
            ["bash", str(install_sh)],
            cwd=str(checkout),
            stdout=fh,
            stderr=subprocess.PIPE,
            timeout=300,
        )
    assert cp.returncode == 0, (
        f"non-TTY install must exit 0: rc={cp.returncode} "
        f"stderr={cp.stderr.decode(errors='replace').strip()[:800]}"
    )
    data = out_file.read_bytes()
    assert b"\x1b" not in data, (
        "non-TTY stdout must contain zero ANSI escape bytes (\\x1b), found at least one"
    )


# --- Test 16 (Test B): spinner cleanup is trap-registered and leaves no orphan --

def test_tty_like_run_does_not_leave_orphaned_spinner_process() -> None:
    """Primary oracle: install.sh must register a `trap ... EXIT` covering spinner cleanup
    (static/code-inspection check — cheap and non-flaky). Secondary oracle: after a forced
    prerequisite-failure run exits, no leftover spinner-loop process (matched by the
    script's own spinner marker) should still be running."""
    install_sh = REPO_ROOT / INSTALL_SH_REL
    text = install_sh.read_text(encoding="utf-8")

    assert re.search(r"trap\s+'spinner_stop'\s+EXIT", text), (
        "install.sh must register a trap 'spinner_stop' ... EXIT so any exit path kills a "
        "still-running spinner"
    )
    assert "spinner_stop" in text and "spinner_start" in text, (
        "install.sh must define both spinner_start and spinner_stop"
    )

    # Secondary, best-effort dynamic check: force a failure (missing python3) and confirm no
    # leftover process matching this script's spinner marker is still running shortly after
    # the script under test exits.
    result = _run_install_with_hidden("python3")
    assert result.returncode == 1, (
        f"expected exit 1 with python3 hidden: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    if shutil.which("pgrep") is not None:
        pgrep = subprocess.run(
            ["pgrep", "-f", "gmj-install-step"],
            capture_output=True,
            text=True,
        )
        assert pgrep.returncode != 0, (
            f"found leftover process(es) matching the install.sh temp-log marker after exit: "
            f"{pgrep.stdout.strip()}"
        )


# --- Test 17 (Test C): failure output includes a remediation hint -------------

def test_missing_prerequisite_failure_includes_remediation_text() -> None:
    """A missing-python3 failure must now surface a remediation hint (an install link or
    'run: ...' instruction) distinct from the bare 'not found on PATH' line."""
    result = _run_install_with_hidden("python3")
    assert result.returncode == 1, (
        f"expected exit 1 with python3 hidden: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    combined = result.stdout + result.stderr
    assert "python3" in combined, f"missing-python3 report must name python3: {combined[:400]}"
    assert (
        "https://www.python.org/downloads/" in combined
        or "install" in combined.lower()
    ), (
        f"missing-python3 failure must include a remediation hint (install link or 'run: ...' "
        f"instruction), not just the bare error: {combined.strip()[:800]}"
    )


# --- Test 18 (Test D): state-aware next-steps branch on config population -----

def test_state_aware_next_steps_branch_on_populated_vs_template_config() -> None:
    """A checkout with the repo's real (populated) config/candidate.yaml + config/sources.yaml
    must print the 'already set up' branch text. A checkout with template-shaped config
    (the shipped .sample content) must instead print the populate-candidate.yaml branch text."""
    if shutil.which("node") is None:
        print(
            "SKIP test_state_aware_next_steps_branch_on_populated_vs_template_config: "
            "node unavailable",
            file=sys.stderr,
        )
        return

    # Populated case: this repo's own real config, via the shared scratch checkout.
    checkout = _scratch_checkout()
    install_sh = checkout / INSTALL_SH_REL
    populated = run(["bash", str(install_sh)], cwd=checkout, timeout=300)
    assert populated.returncode == 0, (
        f"populated-config install must exit 0: {populated.stderr.strip()[:800]}"
    )
    assert "already" in populated.stdout.lower() or "looks set up" in populated.stdout.lower(), (
        f"populated-config next-steps must mention the already-set-up branch: "
        f"{populated.stdout.strip()[-800:]}"
    )
    assert "/gmj-pipeline-run" in populated.stdout, (
        f"populated-config next-steps must name a concrete run command: "
        f"{populated.stdout.strip()[-800:]}"
    )

    # Template-shaped case: a dedicated fresh checkout with candidate.yaml overwritten with
    # the shipped .sample content before running (the sample templates ship under
    # gmj-core/config/, not config/ — sources.yaml.sample is byte-identical to this repo's
    # own config/sources.yaml today, so only candidate.yaml is a meaningful populated-vs-
    # template signal here).
    candidate_sample = REPO_ROOT / "gmj-core" / "config" / "candidate.yaml.sample"
    if not candidate_sample.is_file():
        print(
            "SKIP test_state_aware_next_steps_branch_on_populated_vs_template_config: "
            "gmj-core/config/candidate.yaml.sample not found, cannot construct templated "
            "checkout",
            file=sys.stderr,
        )
        return

    dedicated = Path(tempfile.mkdtemp(prefix="gmj-templated-checkout-"))
    clone = subprocess.run(
        ["git", "clone", str(REPO_ROOT), str(dedicated)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if clone.returncode != 0:
        print(
            "SKIP test_state_aware_next_steps_branch_on_populated_vs_template_config: "
            f"dedicated clone failed: {clone.stderr.strip()[:400]}",
            file=sys.stderr,
        )
        return

    dedicated_candidate = dedicated / "config" / "candidate.yaml"
    dedicated_candidate.write_bytes(candidate_sample.read_bytes())

    dedicated_install_sh = dedicated / INSTALL_SH_REL
    templated = run(["bash", str(dedicated_install_sh)], cwd=dedicated, timeout=300)
    assert templated.returncode == 0, (
        f"templated-config install must exit 0: {templated.stderr.strip()[:800]}"
    )
    assert "populate config/candidate.yaml" in templated.stdout.lower(), (
        f"templated-config next-steps must mention populating candidate.yaml: "
        f"{templated.stdout.strip()[-800:]}"
    )


# --- Test 19 (Test E): 5-stage structure guard (static/grep check) ------------

def test_install_sh_still_contains_stage_markers_and_five_stage_total() -> None:
    """Static guard against an accidental stage-boundary redesign: every stage_header call
    must reference the literal total 5, and all 5 original stage comment markers must
    still be present."""
    install_sh = REPO_ROOT / INSTALL_SH_REL
    text = install_sh.read_text(encoding="utf-8")

    stage_calls = re.findall(r'stage_header\s+\d+\s+"?\$?STAGE_TOTAL"?', text)
    assert stage_calls, "install.sh must contain stage_header calls using STAGE_TOTAL"

    stage_total_match = re.search(r'STAGE_TOTAL=5\b', text)
    assert stage_total_match, "install.sh must define STAGE_TOTAL=5 (literal total of 5 stages)"

    for marker in (
        "1. Prerequisite",
        "2. Run-in-place",
        "3. Idempotent",
        "4. Delegate config",
        "5. Next steps",
    ):
        assert marker in text, (
            f"install.sh is missing the original stage-boundary comment marker: {marker!r} "
            "— guarding against an accidental stage-boundary redesign"
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
