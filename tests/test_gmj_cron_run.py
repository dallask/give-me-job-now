#!/usr/bin/env python3
"""Tests for scripts/ops/gmj_cron_run.sh's overlap guard + argv-shape (OPS-02, OPS-03).

Plain-python3 self-running harness (NO pytest required) — run with
``python3 tests/test_gmj_cron_run.py``. Proves:

- ``test_second_overlapping_invocation_exits_nonzero``: a REAL two-subprocess proof (not a
  mocked unit test) that a second overlapping invocation of the wrapper fails immediately
  (non-zero exit, non-blank stderr, no traceback) while the first proceeds to completion. A fake
  ``claude`` stub is prepended onto ``PATH`` so this test has zero network/LLM dependency and
  stays fast and deterministic — the wrapper's own ``os.execvp("claude", ...)`` call resolves to
  the fake stub, not a real Claude Code CLI invocation.
- ``test_wrapper_invokes_claude_as_argv_never_shell_string``: a lightweight source-text
  assertion (mirroring this repo's existing doc-lint substring-check style, e.g.
  ``tests/test_gmj_batch_persona.py``) proving the wrapper builds the claude invocation as a
  discrete argv list — the exact prompt string ``/gmj-batch mode=autonomous`` appears, and no
  ``sh -c`` / ``eval`` construction wraps the claude invocation.
- ``test_lock_released_after_first_process_exits``: after the first process from the overlap
  test completes, a THIRD invocation against the same lock path succeeds immediately — proving
  the lock is released (not stuck) once its holder exits normally.
- ``test_claude_missing_from_path_exits_cleanly``: shadows ``PATH`` with an empty directory
  (no ``claude`` stub anywhere resolvable) and asserts the wrapper exits non-zero with a clean,
  actionable ``gmj_cron_run: ...`` stderr message and no raw Python ``Traceback`` — proving the
  wrapper's ``os.execvp("claude", ...)`` failure path degrades the same way every other failure
  path in this script does, instead of surfacing an uncaught ``FileNotFoundError``.

Discipline (mirrors tests/test_gmj_batch_manifest_concurrency.py's module docstring): every test
asserts the exit code AND a specific field/sentinel, and asserts ``"Traceback" not in`` any
captured stderr so an unrelated crash's nonzero exit never masquerades as a pass.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "ops" / "gmj_cron_run.sh"

# How long the fake claude stub sleeps before exiting 0 — long enough to make the two/three
# process overlap timing deterministic without being flaky (a real-subprocess test, not a
# mocked unit test, per CONTEXT.md/PATTERNS.md guidance: favor a generous delay over a
# hair-trigger race).
_FAKE_CLAUDE_SLEEP_SECS = 1.5


def _write_fake_claude(bin_dir: Path) -> None:
    """Write a PATH-shadowed fake ``claude`` executable: sleeps, then exits 0, no output.

    Used so ``os.execvp("claude", ...)`` inside the wrapper resolves to this stub instead of a
    real Claude Code CLI invocation — no network/LLM dependency, deterministic timing.
    """
    stub = bin_dir / "claude"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f"sleep {_FAKE_CLAUDE_SLEEP_SECS}\n"
        "exit 0\n"
    )
    stub.chmod(0o755)


def _run_wrapper(lock_path: Path, *, fake_claude_dir: Path, blocking: bool):
    """Invoke the real wrapper script with a PATH-shadowed fake ``claude`` prepended.

    ``blocking=True`` uses ``subprocess.run`` (waits for completion, captures output).
    ``blocking=False`` uses ``subprocess.Popen`` (caller controls timing/joining).
    """
    import os

    env = {**os.environ, "PATH": f"{fake_claude_dir}:{os.environ.get('PATH', '')}"}
    args = ["bash", str(WRAPPER), "--lock-path", str(lock_path)]
    if blocking:
        return subprocess.run(args, capture_output=True, text=True, env=env)
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env
    )


# --- Test 1: real two-process overlap-guard proof (OPS-03) -----------------------------------

def test_second_overlapping_invocation_exits_nonzero() -> None:
    with tempfile.TemporaryDirectory() as bin_dir_s, tempfile.TemporaryDirectory() as lock_dir_s:
        bin_dir = Path(bin_dir_s)
        lock_path = Path(lock_dir_s) / "cron.lock"
        _write_fake_claude(bin_dir)

        proc_a = _run_wrapper(lock_path, fake_claude_dir=bin_dir, blocking=False)
        try:
            # Let A acquire the lock and start its (fake) claude sleep before B attempts.
            time.sleep(0.5)

            proc_b = _run_wrapper(lock_path, fake_claude_dir=bin_dir, blocking=True)

            assert proc_b.returncode != 0, (
                f"second overlapping invocation must exit non-zero, got {proc_b.returncode}; "
                f"stdout={proc_b.stdout!r} stderr={proc_b.stderr!r}"
            )
            assert proc_b.stderr.strip() != "", "held-lock failure must print a clear stderr message, got blank stderr"
            assert "another run holds" in proc_b.stderr, (
                f"expected a clear held-lock message, got stderr={proc_b.stderr!r}"
            )
            assert "Traceback" not in proc_b.stderr, proc_b.stderr
        finally:
            stdout_a, stderr_a = proc_a.communicate(timeout=30)
            assert proc_a.returncode == 0, (
                f"first invocation must proceed to completion (exit 0), got {proc_a.returncode}; "
                f"stdout={stdout_a!r} stderr={stderr_a!r}"
            )
            assert "Traceback" not in stderr_a, stderr_a


# --- Test 2: argv-shape proof (no shell-string interpolation) — OPS-02 -----------------------

def test_wrapper_invokes_claude_as_argv_never_shell_string() -> None:
    text = WRAPPER.read_text(encoding="utf-8")

    assert "/gmj-batch mode=autonomous" in text, (
        "wrapper must forward the exact literal prompt '/gmj-batch mode=autonomous'"
    )
    assert '"claude"' in text, "wrapper must build the claude invocation as a discrete argv element"
    assert '"--dangerously-skip-permissions"' in text, (
        "wrapper must pass --dangerously-skip-permissions as a discrete argv element"
    )
    assert '"-p"' in text, "wrapper must pass -p as a discrete argv element"

    # No shell-string / eval construction wrapping the claude invocation. Strip full-line `#`
    # comments first so prose mentioning these tokens (e.g. explaining what NOT to do) doesn't
    # produce a false positive — only executable-code occurrences count.
    code_lines = [
        line for line in text.splitlines() if not line.strip().startswith("#")
    ]
    code_text = "\n".join(code_lines)
    assert "sh -c" not in code_text, "wrapper must never build the claude invocation via 'sh -c' string interpolation"
    assert not any(
        line.strip() == "eval" or line.strip().startswith("eval ") for line in code_lines
    ), "wrapper must never pipe the claude invocation through eval"
    assert "shell=True" not in code_text, "wrapper must never use shell=True anywhere"


# --- Test 3: lock released after holder exits (not stuck) — OPS-03 ---------------------------

def test_lock_released_after_first_process_exits() -> None:
    with tempfile.TemporaryDirectory() as bin_dir_s, tempfile.TemporaryDirectory() as lock_dir_s:
        bin_dir = Path(bin_dir_s)
        lock_path = Path(lock_dir_s) / "cron.lock"
        _write_fake_claude(bin_dir)

        proc_a = _run_wrapper(lock_path, fake_claude_dir=bin_dir, blocking=False)
        try:
            stdout_a, stderr_a = proc_a.communicate(timeout=30)
            assert proc_a.returncode == 0, (
                f"setup invocation must exit 0 before the release proof, got {proc_a.returncode}; "
                f"stderr={stderr_a!r}"
            )
        finally:
            if proc_a.poll() is None:
                proc_a.kill()
                proc_a.wait(timeout=10)

        proc_c = _run_wrapper(lock_path, fake_claude_dir=bin_dir, blocking=True)
        assert proc_c.returncode == 0, (
            f"a fresh invocation after the holder exits must succeed (lock not stuck), "
            f"got {proc_c.returncode}; stdout={proc_c.stdout!r} stderr={proc_c.stderr!r}"
        )
        assert "Traceback" not in proc_c.stderr, proc_c.stderr


# --- Test 4: claude missing from PATH exits cleanly, no traceback (WR-01/WR-02) --------------

def test_claude_missing_from_path_exits_cleanly() -> None:
    import os

    with tempfile.TemporaryDirectory() as empty_bin_dir_s, tempfile.TemporaryDirectory() as lock_dir_s:
        empty_bin_dir = Path(empty_bin_dir_s)
        lock_path = Path(lock_dir_s) / "cron.lock"

        # Shadow PATH with the empty directory PLUS the standard system dirs ("/usr/bin:/bin")
        # needed for the wrapper's own use of `dirname`/`mkdir`/`python3` and for subprocess.run's
        # `bash` invocation below to resolve — neither ships a `claude` binary on any standard
        # install, so this keeps the test's premise intact: no real `claude` is resolvable.
        env = {**os.environ, "PATH": f"{empty_bin_dir}:/usr/bin:/bin"}
        args = ["bash", str(WRAPPER), "--lock-path", str(lock_path)]
        proc = subprocess.run(args, capture_output=True, text=True, env=env)

        assert proc.returncode != 0, (
            f"missing-claude invocation must exit non-zero, got {proc.returncode}; "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
        assert proc.stderr.strip() != "", "missing-claude failure must print a clear stderr message, got blank stderr"
        assert "claude" in proc.stderr and "PATH" in proc.stderr, (
            f"expected a clear claude-not-on-PATH message, got stderr={proc.stderr!r}"
        )
        assert "Traceback" not in proc.stderr, proc.stderr


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
