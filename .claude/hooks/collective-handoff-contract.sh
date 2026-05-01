#!/usr/bin/env bash
# PostToolUse matcher Task — log handoff markers; fail-open on parse errors
set -euo pipefail

LOG_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/logs/handoff-contract.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

INPUT_JSON=$(cat || true)
if ! echo "$INPUT_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  echo "[$(timestamp)] handoff-contract: non-JSON stdin, skip" >> "$LOG_FILE"
  exit 0
fi

AGENT=""
if command -v jq >/dev/null 2>&1; then
  AGENT=$(echo "$INPUT_JSON" | jq -r '.tool_input.subagent_type // .tool_input.agent // empty' 2>/dev/null || true)
fi

TEXT_DUMP=$(printf '%s' "$INPUT_JSON" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tr = data.get('tool_response') or {}
    parts = []
    for block in tr.get('content') or []:
        if isinstance(block, dict) and 'text' in block:
            parts.append(block['text'])
    sys.stdout.write('\\n'.join(parts))
except Exception:
    pass
" 2>/dev/null || true)

{
  echo "[$(timestamp)] subagent=$AGENT len=${#TEXT_DUMP}"
  if echo "$TEXT_DUMP" | grep -q "ROUTING_DECISION"; then
    echo "[$(timestamp)] OK: ROUTING_DECISION present"
  fi
  if echo "$TEXT_DUMP" | grep -q "DELIVERABLE_SUMMARY"; then
    echo "[$(timestamp)] OK: DELIVERABLE_SUMMARY present"
  fi
  if ! echo "$TEXT_DUMP" | grep -qE "ROUTING_DECISION|DELIVERABLE_SUMMARY|QUALITY_GATE_RESULT"; then
    echo "[$(timestamp)] WARN: missing ROUTING_DECISION/DELIVERABLE_SUMMARY/QUALITY_GATE_RESULT"
  fi
} >> "$LOG_FILE"

exit 0
