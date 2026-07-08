#!/usr/bin/env bash
# gmj-core/bin/install.sh — one-script installer (INSTALL-01/02/03/04).
#
# Supports both invocation modes:
#   - run-in-place: `bash gmj-core/bin/install.sh` from inside an existing checkout.
#   - fresh-clone:  `curl -fsSL <raw-url>/install.sh | bash` with no local checkout — clones
#     the repo into a new directory first, then continues the same flow.
#
# Order is load-bearing: prerequisites are checked FIRST, before any git-based mode detection
# or clone, so a missing `git` itself is caught by the aggregated report below rather than
# falling through into a `git clone`/`git rev-parse` call that would crash with a raw
# "command not found" (see 37-RESEARCH.md Pitfall 3 / this plan's key_links note).
set -euo pipefail

# --- 1. Prerequisite check (aggregate-then-report, never exit-on-first) -----

missing=()

check_bin() {
  local name="$1" hint="$2"
  if ! command -v "$name" >/dev/null 2>&1; then
    missing+=("  - ${name}: not found on PATH. ${hint}")
  fi
}

check_bin git    "Install git: https://git-scm.com/downloads"
check_bin python3 "Install Python 3: https://www.python.org/downloads/"
check_bin node    "Install Node.js: https://nodejs.org/"
check_bin npx     "npx ships with Node.js (npm >=5.2); install/upgrade Node.js: https://nodejs.org/"

# Pip resolution: prefer `python3 -m pip` (ties it to the just-detected python3 interpreter),
# fall back to a bare `pip3`/`pip` binary only if that fails (37-RESEARCH.md Pitfall 4).
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -m pip --version >/dev/null 2>&1 \
     && ! command -v pip3 >/dev/null 2>&1 \
     && ! command -v pip >/dev/null 2>&1; then
    missing+=("  - pip: no working pip found for python3 (tried 'python3 -m pip', 'pip3', 'pip'). Install pip: https://pip.pypa.io/en/stable/installation/")
  fi
fi

if [ "${#missing[@]}" -gt 0 ]; then
  echo "ERROR: missing prerequisites:" >&2
  printf '%s\n' "${missing[@]}" >&2
  exit 1
fi

# --- 2. Run-in-place vs. fresh-clone mode detection (git is guaranteed present here) --

REPO_ROOT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
    if [ ! -f "$REPO_ROOT/scripts/contracts/requirements.txt" ] || [ ! -f "$REPO_ROOT/gmj-core/bin/gmj-tools.cjs" ]; then
      echo "ERROR: $REPO_ROOT does not look like a give-me-job checkout (missing scripts/contracts/requirements.txt or gmj-core/bin/gmj-tools.cjs)." >&2
      exit 1
    fi
    MODE="run-in-place"
  fi
fi

if [ -z "${REPO_ROOT:-}" ]; then
  # Piped via curl | bash (no BASH_SOURCE file on disk), or run from outside any checkout.
  MODE="fresh-clone"
  REPO_URL="${GMJ_REPO_URL:-git@github.com:dallask/give-me-job.git}"
  INSTALL_DIR="${GMJ_INSTALL_DIR:-give-me-job}"
  case "$INSTALL_DIR" in
    /*|*/*|*..*)
      echo "ERROR: GMJ_INSTALL_DIR must be a plain relative directory name (no path separators or \"..\" segments); got \"$INSTALL_DIR\"." >&2
      exit 1
      ;;
  esac
  if [ -e "$INSTALL_DIR" ] || [ -L "$INSTALL_DIR" ]; then
    echo "ERROR: install target \"$INSTALL_DIR\" already exists (file, dir, or symlink) — refusing to clone into a pre-existing path." >&2
    exit 1
  fi
  echo "Fresh-clone mode: cloning \"$REPO_URL\" into \"$INSTALL_DIR\"..."
  git clone -- "$REPO_URL" "$INSTALL_DIR"
  REPO_ROOT="$(cd "$INSTALL_DIR" && pwd)"
fi

cd "$REPO_ROOT"
echo "Mode: $MODE — repo root: $REPO_ROOT"

# --- 3. Idempotent .venv bootstrap + Python dependency installation ---------

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# Always through .venv/bin/python -m pip — never a bare system pip3/pip binary, so every
# install is tied to the venv's own interpreter regardless of what a stray system pip3
# resolves to (37-RESEARCH.md Pitfall 4).
.venv/bin/python -m pip install -r scripts/contracts/requirements.txt
.venv/bin/python -m pip install -r scripts/dashboard/requirements.txt
.venv/bin/python -m pip install -r scripts/cv/requirements.txt
.venv/bin/python -m pip install -r scripts/preferences/requirements.txt

# --- 4. Delegate config/hook staging (never reimplemented — INSTALL-04) -----

# Self-targeting this checkout re-copies whatever gmj-core/'s payload currently holds onto
# the canonical source tree. This is an existing, documented repo discipline (not a new
# runtime check, per 37-RESEARCH.md Assumption A2 / Open Question 1): any edit to a censused
# source file must be followed by rebuilding the payload (`python3 scripts/gmj_build_payload.py`)
# before self-targeting this script, or the stale gmj-core/ snapshot silently regresses the edit.
node gmj-core/bin/gmj-tools.cjs install .

# --- 5. Next steps -----------------------------------------------------------

echo ""
echo "Next steps:"
echo "  1. Populate config/candidate.yaml with your profile."
echo "  2. Set your search scope in config/sources.yaml."
echo "  3. Run a first real offer per docs/RUNBOOK.md."
