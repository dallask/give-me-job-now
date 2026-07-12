#!/usr/bin/env sh
# Stop-event dispatch hook (06-06, D-01/D-05 gap-closure — see
# docs/execution-log-wiring.md "path 2: locally-owned wrapper command" and this plan,
# .planning/workstreams/testplan-gen/phases/06-gsd-execution-observability-self-reflection/06-06-PLAN.md).
#
# Two independent, best-effort, non-blocking side effects fired from the SAME `Stop`
# event (deliberately combined into one hook rather than two near-duplicate scripts,
# since they share the identical trigger point and non-blocking contract):
#
#   1. DISPATCH (Gap 1 / D-01): derive phase/plan/outcome from the project's STATE.md
#      and shell out to `gmj_execution_log_writer.py`, appending one `gsd-workflow`-
#      tagged JSONL line to .planning/execution-logs/gsd-workflow-<date>.jsonl.
#   2. AUTO-FIRE (Gap 2 / D-05): bound the live execution-logs directory to a small
#      recent-date staging window and auto-run `gmj_self_reflect.py` (report-only —
#      this hook's auto-fire call site never includes the apply flag; auto-fire is
#      report-generation only, matching D-07's never-auto-apply constraint),
#      refreshing output/analysis/self-reflect-report.md.
#
# KNOWN, DISCLOSED LIMITATION: Claude Code's `Stop` event fires once per top-level
# agent turn, not once per exact GSD loop-hook point (execute:pre/execute:wave:post/
# etc.) — so the `--point execute:post` value used below is a best-effort
# approximation, not a precise loop-hook-point match a real GSD-core capability
# dispatch would produce. This tradeoff is accepted, not an oversight (see this
# plan's <objective> and docs/execution-log-wiring.md).
#
# 06-07 gap-closure: STATE.md discovery gains a preferred SESSION-SCOPED
# workstream-resolution tier ahead of the mtime-based candidate selection below
# (06-06/CR-01's fix). Live-verified during 06-07's own planning: with 3+ workstreams
# concurrently active in this repo (its actual normal operating mode), mtime recency
# alone is not a valid proxy for "the workstream whose own turn just ended" — every
# concurrent Claude Code session here shares the same CLAUDE_PROJECT_DIR, so only a
# SESSION-scoped signal (not a project-scoped one) can disambiguate. GSD core already
# ships this exact mechanism: `gsd-tools workstream get --raw` resolves a
# session-scoped active-workstream pointer keyed off TERM_SESSION_ID/ITERM_SESSION_ID
# (and related terminal/session env vars), stored per-session under
# $TMPDIR/gsd-workstream-sessions/<project-hash>/. A Stop-event hook subprocess is a
# child of that same terminal session and inherits its session env vars, so this
# resolver call sees exactly what the interactive session saw. This tier is strictly
# ADDITIVE: the mtime-based selection below remains fully intact as the fallback path
# for every environment where node/gsd-tools.cjs are unavailable, the lookup times
# out, or the session-scoped pointer has not been populated (e.g. a non-interactive/CI
# invocation with no terminal session at all).
#
# Non-blocking posture mirrors .claude/hooks/gmj-execution-log.sh exactly: no `set -e`;
# every mkdir/write/subprocess call individually guarded with `|| true`; unconditional
# `exit 0` at the very end on every code path, including all early-return branches.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.planning/execution-logs"

# Resolve the repo root that actually contains scripts/ (this hook's own script
# location — .claude/hooks/<this file> — two directories up), independent of
# PROJECT_DIR: PROJECT_DIR carries the project's *data* (.planning/, output/), but
# in test isolation (and in any multi-root/worktree setup) it may not be the same
# tree that holds the checked-in scripts/ directory this hook shells out to.
HOOK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || HOOK_DIR=""
if [ -n "$HOOK_DIR" ]; then
  SCRIPTS_REPO_ROOT=$(CDPATH= cd -- "${HOOK_DIR}/../.." 2>/dev/null && pwd -P) || SCRIPTS_REPO_ROOT=""
fi
if [ -f "${PROJECT_DIR}/scripts/gmj_execution_log_writer.py" ]; then
  SCRIPTS_ROOT="$PROJECT_DIR"
elif [ -n "$SCRIPTS_REPO_ROOT" ] && [ -f "${SCRIPTS_REPO_ROOT}/scripts/gmj_execution_log_writer.py" ]; then
  SCRIPTS_ROOT="$SCRIPTS_REPO_ROOT"
else
  SCRIPTS_ROOT="$PROJECT_DIR"
fi

# WR-01: wall-clock timeout guard for both python3 subprocess calls below. `|| true`
# only protects against a non-zero exit, not a hang — a hung subprocess would never
# reach `exit 0`, contradicting this hook's own non-blocking contract. `timeout` is
# GNU coreutils and not guaranteed present on macOS by default (only via Homebrew's
# `coreutils`, as `gtimeout`); when neither is found this degrades to no timeout at
# all (best-effort, matching every other guard in this hook).
TIMEOUT_BIN=""
command -v timeout >/dev/null 2>&1 && TIMEOUT_BIN="timeout 10"
if [ -z "$TIMEOUT_BIN" ]; then
  command -v gtimeout >/dev/null 2>&1 && TIMEOUT_BIN="gtimeout 10"
fi

# ---------------------------------------------------------------------------
# 1a. SESSION-SCOPED RESOLUTION TIER (06-07 gap-closure, ahead of the mtime-based
#     selection below): resolve the gsd-tools.cjs entry point via the same layered
#     fallback shape used elsewhere in GSD-invoking tooling (project-local install
#     first, then $HOME/.claude/gsd-core/bin/gsd-tools.cjs, then a PATH lookup).
#     Every step degrades to skipping this tier entirely on any failure — never an
#     error, never a hang (wrapped in the same $TIMEOUT_BIN guard already used
#     below for the writer/self-reflect subprocess calls).
# ---------------------------------------------------------------------------

RESOLVED_WORKSTREAM=""

GSD_TOOLS_PATH=""
if [ -f "${PROJECT_DIR}/gsd-core/bin/gsd-tools.cjs" ]; then
  GSD_TOOLS_PATH="${PROJECT_DIR}/gsd-core/bin/gsd-tools.cjs"
elif [ -f "${PROJECT_DIR}/.claude/gsd-core/bin/gsd-tools.cjs" ]; then
  GSD_TOOLS_PATH="${PROJECT_DIR}/.claude/gsd-core/bin/gsd-tools.cjs"
elif [ -f "${HOME}/.claude/gsd-core/bin/gsd-tools.cjs" ]; then
  GSD_TOOLS_PATH="${HOME}/.claude/gsd-core/bin/gsd-tools.cjs"
else
  GSD_TOOLS_CANDIDATE=$(command -v gsd-tools 2>/dev/null) || true
  [ -n "$GSD_TOOLS_CANDIDATE" ] && GSD_TOOLS_PATH="$GSD_TOOLS_CANDIDATE"
fi

if command -v node >/dev/null 2>&1 && [ -n "$GSD_TOOLS_PATH" ]; then
  WS_RAW=$($TIMEOUT_BIN node "$GSD_TOOLS_PATH" workstream get --raw 2>/dev/null || true)
  WS_RAW=$(printf '%s' "$WS_RAW" | tr -d '[:space:]')

  # Defensive validation before this untrusted subprocess-stdout string ever flows
  # into a filesystem path (T-06-07-01): non-empty, not the literal sentinel "none",
  # and a conservative safe-filename pattern (letters/digits/hyphen/underscore/dot
  # only) — reject anything shaped like a path traversal attempt.
  if [ -n "$WS_RAW" ] && [ "$WS_RAW" != "none" ]; then
    case "$WS_RAW" in
      *[!a-zA-Z0-9._-]*) WS_RAW="" ;;
      *..*) WS_RAW="" ;;
      "" | . | ..) WS_RAW="" ;;
    esac
  else
    WS_RAW=""
  fi

  if [ -n "$WS_RAW" ] && [ -f "${PROJECT_DIR}/.planning/workstreams/${WS_RAW}/STATE.md" ]; then
    RESOLVED_WORKSTREAM="$WS_RAW"
  fi
fi

# ---------------------------------------------------------------------------
# 1b. DISPATCH: locate STATE.md. When the session-scoped tier above resolved and
#     validated a workstream, its STATE.md is used directly (it is authoritative —
#     it identifies the workstream whose own terminal session actually triggered
#     this Stop event, not merely whichever candidate has the newest mtime).
#     Otherwise, fall through to the existing mtime-based selection (CR-01's fix,
#     unchanged): gather every candidate — the top-level file (if present) and
#     every per-workstream STATE.md — and pick whichever was modified most
#     recently. A hardcoded "top-level always wins" precedence would unconditionally
#     shadow an actively-executing workstream's STATE.md with a stale top-level one
#     (CR-01) whenever both happen to exist, which is the common case in
#     multi-workstream projects.
# ---------------------------------------------------------------------------

STATE_MD=""
if [ -n "$RESOLVED_WORKSTREAM" ]; then
  STATE_MD="${PROJECT_DIR}/.planning/workstreams/${RESOLVED_WORKSTREAM}/STATE.md"
else
  CANDIDATES=""
  [ -f "${PROJECT_DIR}/.planning/STATE.md" ] && CANDIDATES="${PROJECT_DIR}/.planning/STATE.md"
  WS_CANDIDATES=$(find "${PROJECT_DIR}/.planning/workstreams" -maxdepth 2 -name "STATE.md" -type f 2>/dev/null)
  if [ -n "$WS_CANDIDATES" ]; then
    CANDIDATES=$(printf '%s\n%s' "$CANDIDATES" "$WS_CANDIDATES")
  fi
  STATE_MD=$(printf '%s\n' "$CANDIDATES" | grep -v '^$' | xargs ls -t 2>/dev/null | head -1)
fi

PHASE=""
PLAN=""
PHASE_NAME=""
OUTCOME="checkpoint"

if [ -n "$STATE_MD" ] && [ -f "$STATE_MD" ]; then
  PARSED=$(python3 -c "
import sys

state_path = sys.argv[1]
phase = ''
phase_name = ''
status = ''
try:
    with open(state_path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    lines = text.splitlines()
    if lines and lines[0].strip() == '---':
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_idx = i
                break
        if end_idx is not None:
            for line in lines[1:end_idx]:
                if line.startswith('current_phase:'):
                    phase = line.split(':', 1)[1].strip().strip('\"').strip(chr(39))
                elif line.startswith('current_phase_name:'):
                    # WR-02: this hook has no dedicated 'current plan number'
                    # frontmatter field to key off. current_phase_name is a
                    # descriptive phase-name label, not the short plan-number
                    # identifier gmj_execution_log_writer.py's own docstring
                    # documents for --plan (e.g. '03'). Carry it separately as
                    # phase_name via --extra-json instead of overloading --plan.
                    phase_name = line.split(':', 1)[1].strip().strip('\"').strip(chr(39))
                elif line.startswith('status:'):
                    status = line.split(':', 1)[1].strip().strip('\"').strip(chr(39))
except Exception:
    phase = ''
    phase_name = ''
    status = ''
print(phase)
print(phase_name)
print(status)
" "$STATE_MD" 2>/dev/null || true)

  PHASE=$(printf '%s\n' "$PARSED" | sed -n '1p')
  PHASE_NAME=$(printf '%s\n' "$PARSED" | sed -n '2p')
  STATUS=$(printf '%s\n' "$PARSED" | sed -n '3p')

  case "$STATUS" in
    executing|complete) OUTCOME="pass" ;;
    blocked|failed) OUTCOME="fail" ;;
    *) OUTCOME="checkpoint" ;;
  esac
fi

# WR-02: --plan intentionally stays unpopulated here — this hook has no source of
# the short plan-number identifier the writer's own docstring documents for --plan
# (e.g. '03'); current_phase_name is a descriptive label, not that identifier, so it
# is carried separately via --extra-json's phase_name key rather than overloading
# --plan with a value that wouldn't group/sort the way the writer's contract implies.
#
# 06-07: also record which discovery tier actually sourced STATE.md — the resolved,
# validated session-scoped workstream name when tier 1a won, or the literal string
# "mtime-fallback" when the existing mtime tier was used instead (including when no
# STATE.md was found at all). Makes the discovery path's own decision auditable
# directly from the log entry, without re-deriving it by hand after the fact.
WORKSTREAM_FIELD="mtime-fallback"
[ -n "$RESOLVED_WORKSTREAM" ] && WORKSTREAM_FIELD="$RESOLVED_WORKSTREAM"

EXTRA_JSON=$(PHASE_NAME="$PHASE_NAME" WORKSTREAM_FIELD="$WORKSTREAM_FIELD" python3 -c "
import json
import os
payload = {'workstream': os.environ.get('WORKSTREAM_FIELD', 'mtime-fallback')}
phase_name = os.environ.get('PHASE_NAME', '')
if phase_name:
    payload['phase_name'] = phase_name
print(json.dumps(payload))
" 2>/dev/null || true)

$TIMEOUT_BIN python3 "${SCRIPTS_ROOT}/scripts/gmj_execution_log_writer.py" \
  --point execute:post \
  --outcome "$OUTCOME" \
  ${PHASE:+--phase "$PHASE"} \
  ${PLAN:+--plan "$PLAN"} \
  --log-dir "$LOG_DIR" \
  ${EXTRA_JSON:+--extra-json "$EXTRA_JSON"} \
  >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 2. AUTO-FIRE: stage only the 2 most-recent calendar dates (today + yesterday, UTC)
#    of tool-calls-*.jsonl / gsd-workflow-*.jsonl into a fresh temp dir (never point
#    the analyzer directly at the live, unbounded LOG_DIR — RESEARCH.md Common
#    Pitfall 4 / Open Question 3), then auto-run gmj_self_reflect.py against that
#    bounded staging dir. Every step (mktemp, copy, invocation, cleanup) is
#    individually guarded so a failure anywhere degrades to a no-op rather than
#    propagating a non-zero exit from this hook. ROADMAP SC3's "run ... after a
#    command/flow/agent/skill/test completes" is satisfied via this same Stop event
#    the dispatch step above uses — one hook, two independent best-effort side
#    effects sharing the identical trigger point and non-blocking contract.
# ---------------------------------------------------------------------------

(
  STAGING_DIR=$(mktemp -d 2>/dev/null) || exit 0
  trap 'rm -rf "$STAGING_DIR" 2>/dev/null || true' EXIT INT TERM

  TODAY=$(date -u '+%Y-%m-%d' 2>/dev/null) || exit 0
  YESTERDAY=$(date -u -v-1d '+%Y-%m-%d' 2>/dev/null || date -u -d 'yesterday' '+%Y-%m-%d' 2>/dev/null) || YESTERDAY=""

  if [ -d "$LOG_DIR" ]; then
    for d in "$TODAY" "$YESTERDAY"; do
      [ -z "$d" ] && continue
      for f in "${LOG_DIR}/tool-calls-${d}.jsonl" "${LOG_DIR}/gsd-workflow-${d}.jsonl"; do
        [ -f "$f" ] && cp "$f" "$STAGING_DIR/" 2>/dev/null || true
      done
    done
  fi

  mkdir -p "${PROJECT_DIR}/output/analysis" 2>/dev/null || true
  $TIMEOUT_BIN python3 "${SCRIPTS_ROOT}/scripts/gmj_self_reflect.py" \
    --log-dir "$STAGING_DIR" \
    --output "${PROJECT_DIR}/output/analysis/self-reflect-report.md" \
    >/dev/null 2>&1 || true
) || true

# D-09/REFLECT-05: this hook never blocks — unconditional success exit regardless of
# whether the dispatch/auto-fire steps above succeeded.
exit 0
