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
#      recent-date staging window and auto-run `gmj_self_reflect.py` (report-only,
#      NEVER --apply), refreshing output/analysis/self-reflect-report.md.
#
# KNOWN, DISCLOSED LIMITATION: Claude Code's `Stop` event fires once per top-level
# agent turn, not once per exact GSD loop-hook point (execute:pre/execute:wave:post/
# etc.) — so the `--point execute:post` value used below is a best-effort
# approximation, not a precise loop-hook-point match a real GSD-core capability
# dispatch would produce. This tradeoff is accepted, not an oversight (see this
# plan's <objective> and docs/execution-log-wiring.md).
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

# ---------------------------------------------------------------------------
# 1. DISPATCH: locate STATE.md (first-match-wins: top-level, then most-recently
#    -modified per-workstream candidate), parse phase/plan/status, map to outcome,
#    and invoke the writer.
# ---------------------------------------------------------------------------

STATE_MD=""
if [ -f "${PROJECT_DIR}/.planning/STATE.md" ]; then
  STATE_MD="${PROJECT_DIR}/.planning/STATE.md"
else
  STATE_MD=$(find "${PROJECT_DIR}/.planning/workstreams" -maxdepth 2 -name "STATE.md" -type f 2>/dev/null \
    -exec ls -t {} + 2>/dev/null | head -1)
fi

PHASE=""
PLAN=""
OUTCOME="checkpoint"

if [ -n "$STATE_MD" ] && [ -f "$STATE_MD" ]; then
  PARSED=$(python3 -c "
import sys

state_path = sys.argv[1]
phase = ''
plan = ''
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
                    # This hook has no dedicated 'current plan number' frontmatter
                    # field to key off; per this plan's own <behavior> spec, derive
                    # --plan from current_phase_name (a stable per-phase identifier)
                    # rather than leaving it unpopulated.
                    plan = line.split(':', 1)[1].strip().strip('\"').strip(chr(39))
                elif line.startswith('status:'):
                    status = line.split(':', 1)[1].strip().strip('\"').strip(chr(39))
except Exception:
    phase = ''
    plan = ''
    status = ''
print(phase)
print(plan)
print(status)
" "$STATE_MD" 2>/dev/null || true)

  PHASE=$(printf '%s\n' "$PARSED" | sed -n '1p')
  PLAN=$(printf '%s\n' "$PARSED" | sed -n '2p')
  STATUS=$(printf '%s\n' "$PARSED" | sed -n '3p')

  case "$STATUS" in
    executing|complete) OUTCOME="pass" ;;
    blocked|failed) OUTCOME="fail" ;;
    *) OUTCOME="checkpoint" ;;
  esac
fi

python3 "${SCRIPTS_ROOT}/scripts/gmj_execution_log_writer.py" \
  --point execute:post \
  --outcome "$OUTCOME" \
  ${PHASE:+--phase "$PHASE"} \
  ${PLAN:+--plan "$PLAN"} \
  --log-dir "$LOG_DIR" \
  >/dev/null 2>&1 || true

# D-09/REFLECT-05: this hook never blocks — unconditional success exit regardless of
# whether the dispatch above succeeded.
exit 0
