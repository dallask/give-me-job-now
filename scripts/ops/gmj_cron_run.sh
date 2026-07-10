#!/usr/bin/env bash
# gmj_cron_run.sh — cron/launchd-schedulable wrapper for an unattended /gmj-batch run.
#
# Satisfies OPS-02 (a documented + SCRIPTED recipe letting an operator run the autonomous
# pipeline unattended on a recurring OS-native schedule) and OPS-03 (a non-blocking overlap
# guard that fails a second overlapping tick closed instead of queueing or silently skipping).
#
# Lock: a single global lock at .pipeline/cron.lock (overridable via --lock-path), acquired
# via Python's fcntl.flock(LOCK_EX | LOCK_NB) — never shell flock(1), which does not exist on
# this repo's own macOS dev machine (see 50-RESEARCH.md Pitfall 2). The lock is acquired BEFORE
# invoking claude and held for the wrapper's entire outer lifetime: this script never backgrounds
# the claude call (no trailing `&`), so the lock is only released when the whole process (and
# thus the whole /gmj-batch run, since `claude -p` blocks until completion) exits — including on
# SIGKILL, since fcntl locks are held against the OS open-file-description and are released
# automatically by the kernel on any exit path (see 50-RESEARCH.md Pitfall 3 / T-50-05).
#
# Invocation: invokes `claude --dangerously-skip-permissions -p "/gmj-batch mode=autonomous"`
# exactly once per tick, as a discrete argv list (never a shell string / `sh -c` / `eval`), and
# surfaces its exit code verbatim — no retry loop, ever (see 50-RESEARCH.md Pitfall 6 / T-50-03).
#
# Usage:
#   scripts/ops/gmj_cron_run.sh [--lock-path <path>]
#
# --lock-path defaults to .pipeline/cron.lock (relative to the invocation's working directory,
# mirroring gmj_batch.py's own .pipeline-relative convention).

set -euo pipefail

LOCK_PATH=".pipeline/cron.lock"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --lock-path)
      if [ "$#" -lt 2 ]; then
        echo "gmj_cron_run: --lock-path requires a value" >&2
        exit 1
      fi
      LOCK_PATH="$2"
      shift 2
      ;;
    *)
      echo "gmj_cron_run: unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

LOCK_DIR="$(dirname -- "$LOCK_PATH")"
mkdir -p -- "$LOCK_DIR"

# The lock-acquire AND the claude exec happen inside the SAME python3 process (via os.execvp),
# rather than trying to hand a held fcntl lock across a shell `exec` boundary — fcntl locks are
# per-open-file-description, so losing the Python process would release the lock prematurely.
# os.execvp replaces the CURRENT process image (the one holding the open, locked file
# descriptor) with claude, so the lock is held for the OS lifetime of that single process until
# `claude -p` itself exits, with zero manual cleanup needed on any exit path.
exec python3 -c '
import fcntl
import os
import sys

lock_path = sys.argv[1]

f = open(lock_path, "w")
try:
    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print(f"gmj_cron_run: another run holds {lock_path}; exiting", file=sys.stderr)
    sys.exit(1)

# Python opens files with O_CLOEXEC by default (PEP 446), which would silently close (and thus
# release) this locked fd across execvp — clear FD_CLOEXEC so the held flock survives into the
# claude process image, which is the whole point of doing the acquire+exec in one process.
flags = fcntl.fcntl(f.fileno(), fcntl.F_GETFD)
fcntl.fcntl(f.fileno(), fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)

# Keep f open (and thus the lock held) — os.execvp replaces this process image with claude,
# so the open file descriptor (and its lock) survives for the lifetime of the claude process.
try:
    os.execvp("claude", ["claude", "--dangerously-skip-permissions", "-p", "/gmj-batch mode=autonomous"])
except FileNotFoundError:
    print("gmj_cron_run: '\''claude'\'' not found on PATH; check cron/launchd PATH env", file=sys.stderr)
    sys.exit(1)
' "$LOCK_PATH"
