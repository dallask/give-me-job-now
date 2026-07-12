#!/usr/bin/env bash
# gmj-core/bin/install.sh — one-script installer (INSTALL-01/02/03/04).
#
# Supports both invocation modes:
#   - run-in-place: `bash gmj-core/bin/install.sh` from inside an existing checkout.
#   - fresh-clone:  `curl -fsSL https://raw.githubusercontent.com/dallask/give-me-job-now/main/gmj-core/bin/install.sh | bash`
#     with no local checkout — clones
#     the repo into a new directory first, then continues the same flow.
#
# Order is load-bearing: prerequisites are checked FIRST, before any git-based mode detection
# or clone, so a missing `git` itself is caught by the aggregated report below rather than
# falling through into a `git clone`/`git rev-parse` call that would crash with a raw
# "command not found" (see 37-RESEARCH.md Pitfall 3 / this plan's key_links note).
#
# --- Wizard UI layer (bash 3.2-safe) -----------------------------------------
# Everything in this section is presentation only — it never changes an exit code, an env
# var contract, or a check's pass/fail decision. Every existing check below still runs with
# real exit-code propagation; this section only wraps it with color/spinner/progress text.
set -euo pipefail

# --- TTY + color detection ----------------------------------------------------
IS_TTY=0
if [ -t 1 ]; then
  IS_TTY=1
fi

COLOR_GREEN=""
COLOR_RED=""
COLOR_YELLOW=""
COLOR_CYAN=""
COLOR_BOLD=""
COLOR_RESET=""

if [ "$IS_TTY" -eq 1 ]; then
  if command -v tput >/dev/null 2>&1 && tput colors >/dev/null 2>&1; then
    COLOR_GREEN="$(tput setaf 2 2>/dev/null || true)"
    COLOR_RED="$(tput setaf 1 2>/dev/null || true)"
    COLOR_YELLOW="$(tput setaf 3 2>/dev/null || true)"
    COLOR_CYAN="$(tput setaf 6 2>/dev/null || true)"
    COLOR_BOLD="$(tput bold 2>/dev/null || true)"
    COLOR_RESET="$(tput sgr0 2>/dev/null || true)"
  else
    # Raw ANSI SGR fallback — only reached when tput itself is unavailable but stdout is
    # still a real TTY.
    COLOR_GREEN=$'\033[0;32m'
    COLOR_RED=$'\033[0;31m'
    COLOR_YELLOW=$'\033[0;33m'
    COLOR_CYAN=$'\033[0;36m'
    COLOR_BOLD=$'\033[1m'
    COLOR_RESET=$'\033[0m'
  fi
fi
# IS_TTY=0 leaves every color variable as the empty string set above — no escape byte is
# ever written to non-TTY output (piped/redirected/CI).

# Best-effort Unicode detection (bash 3.2-safe — no `${var,,}`, only `case` for folding).
UNICODE_OK=0
_locale_charmap=""
if command -v locale >/dev/null 2>&1; then
  _locale_charmap="$(locale charmap 2>/dev/null || true)"
fi
case "$_locale_charmap" in
  *UTF-8*|*utf-8*|*UTF8*|*utf8*) UNICODE_OK=1 ;;
esac
if [ "$UNICODE_OK" -eq 0 ]; then
  case "${LANG:-}${LC_ALL:-}" in
    *UTF-8*|*utf-8*|*UTF8*|*utf8*) UNICODE_OK=1 ;;
  esac
fi

CHECK_MARK="[x]"
CROSS_MARK="[ ]"
if [ "$UNICODE_OK" -eq 1 ]; then
  CHECK_MARK="✓"
  CROSS_MARK="✗"
fi

# --- Stage header helper -------------------------------------------------------
CURRENT_STAGE=0
STAGE_TOTAL=5

stage_header() {
  local n="$1" total="$2" label="$3"
  CURRENT_STAGE="$n"
  if [ "$IS_TTY" -eq 1 ]; then
    printf '%s%s==> [%s/%s] %s%s\n' "$COLOR_CYAN" "$COLOR_BOLD" "$n" "$total" "$label" "$COLOR_RESET"
  else
    printf '[%s/%s] %s\n' "$n" "$total" "$label"
  fi
}

# --- Step-result helpers --------------------------------------------------------
step_ok() {
  local label="$1"
  if [ "$IS_TTY" -eq 1 ]; then
    printf '%s%s%s %s\n' "$COLOR_GREEN" "$CHECK_MARK" "$COLOR_RESET" "$label"
  else
    printf 'OK: %s\n' "$label"
  fi
}

step_fail() {
  local label="$1" remediation="$2" log_file="${3:-}"
  if [ "$IS_TTY" -eq 1 ]; then
    printf '%s%s%s %s%s%s\n' "$COLOR_RED" "$CROSS_MARK" "$COLOR_RESET" "$COLOR_RED" "$label" "$COLOR_RESET" >&2
  else
    printf 'FAILED: %s\n' "$label" >&2
  fi
  if [ -n "$remediation" ]; then
    printf '%s\n' "$remediation" >&2
  fi
  if [ -n "$log_file" ] && [ -s "$log_file" ]; then
    echo "--- last 20 lines of captured output ($log_file) ---" >&2
    tail -n 20 "$log_file" >&2
  fi
}

# --- Spinner (bash 3.2-safe background process, TTY-only) ----------------------
SPINNER_PID=""

spinner_start() {
  # Never runs when IS_TTY=0 — non-TTY output stays spinner-free plain text.
  if [ "$IS_TTY" -ne 1 ]; then
    return 0
  fi
  local message="$1"
  (
    local chars='|/-\'
    local i=0
    while true; do
      i=$(( (i + 1) % 4 ))
      printf '\r%s%s%s %s' "$COLOR_YELLOW" "${chars:$i:1}" "$COLOR_RESET" "$message"
      sleep 0.1
    done
  ) &
  SPINNER_PID=$!
  disown "$SPINNER_PID" 2>/dev/null || true
}

spinner_stop() {
  if [ -n "${SPINNER_PID:-}" ]; then
    if kill -0 "$SPINNER_PID" 2>/dev/null; then
      kill "$SPINNER_PID" 2>/dev/null || true
      wait "$SPINNER_PID" 2>/dev/null || true
    fi
    SPINNER_PID=""
    if [ "$IS_TTY" -eq 1 ]; then
      printf '\r%80s\r' "" 2>/dev/null || true
    fi
  fi
}

# Registered immediately after spinner_stop is defined so ANY exit path — including a
# set -e-triggered early exit from a prerequisite check above this trap registration point —
# still kills a running spinner. spinner_stop is idempotent/safe to call with no spinner
# running (it checks SPINNER_PID is set first).
trap 'spinner_stop' EXIT INT TERM

# --- run_captured: capture-then-tail wiring for a long-running command ---------
# Runs "$@" with combined stdout+stderr captured to a per-step temp log while a spinner
# brackets the call (TTY only). On success, calls step_ok and returns 0. On failure, calls
# step_fail with the given remediation text and returns the ORIGINAL non-zero exit code —
# never swallowed, never hardcoded to `exit 1`. Uses explicit `if ! cmd ...; then` (not
# command substitution) so `set -e` semantics are preserved for the caller.
run_captured() {
  local label="$1" remediation="$2"
  shift 2
  local log_file
  log_file="$(mktemp "${TMPDIR:-/tmp}/gmj-install-step.XXXXXX")"
  spinner_start "$label..."
  local rc=0
  if "$@" >"$log_file" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  spinner_stop
  if [ "$rc" -eq 0 ]; then
    step_ok "$label"
    rm -f "$log_file" 2>/dev/null || true
    return 0
  fi
  step_fail "$label" "$remediation" "$log_file"
  return "$rc"
}

# --- 1. Prerequisite check (aggregate-then-report, never exit-on-first) -----

stage_header 1 "$STAGE_TOTAL" "Prerequisite check"

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

# Python minimum-version floor. Guarded by `command -v python3` so a genuinely-missing
# python3 is reported once via the check_bin path above, never a second confusing
# "version check failed" message — this participates in the same aggregate-then-report
# array as every other prerequisite, not a separate ad-hoc exit.
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    missing+=("  - python3: found $(python3 --version 2>&1) but a minimum of Python 3.9 is required. Install a newer interpreter: 'pyenv install 3.12' (recommended) or your OS package manager (e.g. 'apt install python3.12' on Debian/Ubuntu, 'brew install python@3.12' on macOS).")
  fi
fi

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
  step_fail "Prerequisite check" "ERROR: missing prerequisites:"
  printf '%s\n' "${missing[@]}" >&2
  exit 1
fi
step_ok "All prerequisites present (git, python3 >=3.9, node, npx, pip)"

# --- OS/WSL detection (label only — never gates or changes install behavior) --
#
# WSL is bash/POSIX-compatible with native Linux, so this is purely a diagnostic label
# printed in the "Mode: ..." line below; it must never branch subsequent install logic.
# `uname -s` gives the primary OS family; for the Linux case, `/proc/version` is checked
# for a case-insensitive "microsoft"/"wsl" substring (the standard, documented portable
# WSL-detection technique) to relabel it WSL.
OS_LABEL="$(uname -s)"
case "$OS_LABEL" in
  Darwin) OS_LABEL="macOS" ;;
  Linux)
    OS_LABEL="Linux"
    if [ -r /proc/version ] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
      OS_LABEL="WSL"
    fi
    ;;
esac

# --- 2. Run-in-place vs. fresh-clone mode detection (git is guaranteed present here) --

stage_header 2 "$STAGE_TOTAL" "Mode detection / clone"

REPO_ROOT=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
    if [ ! -f "$REPO_ROOT/scripts/contracts/requirements.txt" ] || [ ! -f "$REPO_ROOT/gmj-core/bin/gmj-tools.cjs" ]; then
      step_fail "Mode detection / clone" "ERROR: $REPO_ROOT does not look like a give-me-job checkout (missing scripts/contracts/requirements.txt or gmj-core/bin/gmj-tools.cjs)."
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
      step_fail "Mode detection / clone" "ERROR: GMJ_INSTALL_DIR must be a plain relative directory name (no path separators or \"..\" segments); got \"$INSTALL_DIR\"."
      exit 1
      ;;
  esac
  if [ -e "$INSTALL_DIR" ] || [ -L "$INSTALL_DIR" ]; then
    step_fail "Mode detection / clone" "ERROR: install target \"$INSTALL_DIR\" already exists (file, dir, or symlink) — refusing to clone into a pre-existing path. Rename or remove it, or override the destination with GMJ_INSTALL_DIR=<other-name>."
    exit 1
  fi
  echo "Fresh-clone mode: cloning \"$REPO_URL\" into \"$INSTALL_DIR\"..."
  if ! run_captured "git clone \"$REPO_URL\"" \
    "Clone failed. Check that \"$REPO_URL\" is reachable and, for SSH remotes, that this host has an SSH key registered with GitHub. Override the remote with GMJ_REPO_URL=<https-or-ssh-url> if needed." \
    git clone -- "$REPO_URL" "$INSTALL_DIR"; then
    exit 1
  fi
  REPO_ROOT="$(cd "$INSTALL_DIR" && pwd)"
fi

cd "$REPO_ROOT"
if [ "$IS_TTY" -eq 1 ]; then
  printf '%sMode: %s — repo root: %s — OS: %s%s\n' "$COLOR_CYAN" "$MODE" "$REPO_ROOT" "$OS_LABEL" "$COLOR_RESET"
else
  echo "Mode: $MODE — repo root: $REPO_ROOT — OS: $OS_LABEL"
fi
step_ok "Mode detection / clone complete ($MODE)"

# --- 3. Idempotent .venv bootstrap + Python dependency installation ---------

stage_header 3 "$STAGE_TOTAL" "Python environment + dependency install"

if [ ! -d .venv ]; then
  if ! run_captured "Create .venv" \
    "venv creation failed. Check available disk space and directory permissions in \"$REPO_ROOT\", and confirm the python3 'venv' module is installed (e.g. 'apt install python3-venv' on Debian/Ubuntu)." \
    python3 -m venv .venv; then
    exit 1
  fi
else
  step_ok "Reusing existing .venv"
fi

# Always through .venv/bin/python -m pip — never a bare system pip3/pip binary, so every
# install is tied to the venv's own interpreter regardless of what a stray system pip3
# resolves to (37-RESEARCH.md Pitfall 4).
#
# Full requirements aggregation: mirrors .github/workflows/tests.yml's exact glob pair
# (`scripts/*/requirements.txt scripts/requirements-*.txt`) so this loop self-extends as
# new subsystem requirements files are added, the same as CI — never a hand-enumerated
# file list, which is what silently under-installed dependencies before this fix.
for req in scripts/*/requirements.txt scripts/requirements-*.txt; do
  if ! run_captured "Installing $req" \
    "pip install failed for \"$req\". Check your network connection/proxy settings, then re-run manually for a full trace: .venv/bin/python -m pip install -r \"$req\" --verbose" \
    .venv/bin/python -m pip install -r "$req"; then
    exit 1
  fi
done

# --- Post-install validation: import smoke check on the core always-required -
# packages (one representative import per always-required requirements file). WeasyPrint
# and firecrawl-py are intentionally excluded — WeasyPrint has documented optional
# system-library failure modes (see docs/installation.md) and firecrawl-py is
# optional/API-key-gated, so neither should false-fail a legitimately optional/degraded
# install.
if ! run_captured "Post-install smoke check" \
  "One or more core packages (PyYAML, jsonschema, textual, reportlab, Jinja2) failed to import from .venv. Re-run this script, or install manually per docs/installation.md." \
  .venv/bin/python -c "import yaml, jsonschema, textual, reportlab, jinja2; print('OK')"; then
  exit 1
fi

# --- 4. Delegate config/hook staging (never reimplemented — INSTALL-04) -----

stage_header 4 "$STAGE_TOTAL" "Config / hook staging"

# Self-targeting this checkout re-copies whatever gmj-core/'s payload currently holds onto
# the canonical source tree. This is an existing, documented repo discipline (not a new
# runtime check, per 37-RESEARCH.md Assumption A2 / Open Question 1): any edit to a censused
# source file must be followed by rebuilding the payload (`python3 scripts/gmj_build_payload.py`)
# before self-targeting this script, or the stale gmj-core/ snapshot silently regresses the edit.
if ! run_captured "gmj-tools.cjs install ." \
  "gmj-tools.cjs install failed. Check that node is on PATH and this checkout has write permission, then re-run manually for a full trace: node gmj-core/bin/gmj-tools.cjs install ." \
  node gmj-core/bin/gmj-tools.cjs install .; then
  exit 1
fi

# --- 5. Next steps -----------------------------------------------------------

stage_header 5 "$STAGE_TOTAL" "Next steps"

echo ""
echo "Next steps:"
echo "  Activate the venv: source .venv/bin/activate"

# State-aware next-steps: read config/candidate.yaml and config/sources.yaml from the
# already-resolved $REPO_ROOT (never a hardcoded relative guess) and branch the printed
# guidance on whether each still looks template-shaped.
CANDIDATE_YAML="$REPO_ROOT/config/candidate.yaml"
SOURCES_YAML="$REPO_ROOT/config/sources.yaml"

candidate_populated=0
if [ -f "$CANDIDATE_YAML" ]; then
  if ! grep -qiE 'SAMPLE candidate profile \(template\)' "$CANDIDATE_YAML" 2>/dev/null \
     && ! grep -qE '"?Your Name"?' "$CANDIDATE_YAML" 2>/dev/null \
     && ! grep -qE 'you@example\.com' "$CANDIDATE_YAML" 2>/dev/null; then
    candidate_populated=1
  fi
fi

sources_populated=0
if [ -f "$SOURCES_YAML" ]; then
  if ! grep -qiE 'SAMPLE sources' "$SOURCES_YAML" 2>/dev/null; then
    if grep -qE '^[[:space:]]*sites:' "$SOURCES_YAML" 2>/dev/null \
       || grep -qE '^[[:space:]]*cities:' "$SOURCES_YAML" 2>/dev/null; then
      sources_populated=1
    fi
  fi
fi

if [ "$candidate_populated" -eq 1 ] && [ "$sources_populated" -eq 1 ]; then
  echo "  Your config looks set up — run a first real offer:"
  echo "    /gmj-pipeline-run"
  echo "  See docs/RUNBOOK.md §1-3 for the full walkthrough."
elif [ "$candidate_populated" -eq 0 ]; then
  echo "  1. Populate config/candidate.yaml with your real profile (see docs/configuration.md)."
  echo "     Alternative: run /gmj-interview for a gap-filling interactive flow."
  if [ "$sources_populated" -eq 0 ]; then
    echo "  2. Set your search scope in config/sources.yaml."
  fi
  echo "  3. Run a first real offer per docs/RUNBOOK.md."
else
  echo "  1. Set your search scope in config/sources.yaml."
  echo "  2. Run a first real offer per docs/RUNBOOK.md (/gmj-pipeline-run)."
fi
