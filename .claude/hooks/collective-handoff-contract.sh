#!/usr/bin/env bash
# PostToolUse matcher: Task
# Parses agent_result_v1 envelope from spoke output.
# exit 1 (hard halt) on contract violations — prevents silent bad pipelines.
set -euo pipefail

LOG_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/logs/handoff-contract.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

INPUT_JSON=$(cat || true)

# Validate JSON input
if ! echo "$INPUT_JSON" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  echo "[$(timestamp)] handoff-contract: non-JSON stdin, skip" >> "$LOG_FILE"
  exit 0
fi

# Extract subagent name for logging
AGENT=""
if command -v jq >/dev/null 2>&1; then
  AGENT=$(echo "$INPUT_JSON" | jq -r '.tool_input.subagent_type // .tool_input.agent // empty' 2>/dev/null || true)
fi

# Only enforce agent_result_v1 contract on known collective agents.
# Non-collective agents (Explore, Plan, general-purpose, etc.) are exempt.
# vacancy-router is exempt: it has its own structured contract (ROUTING_DECISION JSON)
# and runs on haiku which does not reliably emit a second output block.
COLLECTIVE_AGENTS="candidate-analyzer candidate-configurator job-market-researcher vacancy-scraper cv-template-creator cv-generator cv-reviewer cv-enhancer cv-deliverable-gate"
IS_COLLECTIVE="false"
for known in $COLLECTIVE_AGENTS; do
  if [ "$AGENT" = "$known" ]; then
    IS_COLLECTIVE="true"
    break
  fi
done

if [ "$IS_COLLECTIVE" = "false" ]; then
  # Log non-collective agent Task completions at info level but do not enforce contract.
  {
    echo "[$(timestamp)] run=${RUN_ID:-unknown} agent=${AGENT} (non-collective, skipped contract check)"
  } >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

# Extract full text from tool response content blocks
TEXT_DUMP=$(printf '%s' "$INPUT_JSON" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tr = data.get('tool_response') or {}
    parts = []
    for block in tr.get('content') or []:
        if isinstance(block, dict) and 'text' in block:
            parts.append(block['text'])
    sys.stdout.write('\n'.join(parts))
except Exception:
    pass
" 2>/dev/null || true)

# Extract pipeline_run_id from prompt if present (best-effort)
RUN_ID=$(echo "$INPUT_JSON" | python3 -c "
import json, sys, re
try:
    data = json.load(sys.stdin)
    prompt = data.get('tool_input', {}).get('prompt', '')
    m = re.search(r'pipeline_run_id[:\s]+([A-Za-z0-9_-]+)', prompt)
    if m:
        sys.stdout.write(m.group(1))
except Exception:
    pass
" 2>/dev/null || true)
RUN_ID="${RUN_ID:-unknown}"

# Parse agent_result_v1 block from the spoke output
PARSE_RESULT=$(echo "$TEXT_DUMP" | python3 -c "
import sys, json, re

text = sys.stdin.read()

# Find fenced agent_result_v1 block
m = re.search(r'\`\`\`agent_result_v1\s*\n(.*?)\n\s*\`\`\`', text, re.DOTALL)
if not m:
    print('MISSING_ENVELOPE')
    sys.exit(0)

raw = m.group(1).strip()
try:
    obj = json.loads(raw)
except json.JSONDecodeError as e:
    print(f'INVALID_JSON:{e}')
    sys.exit(0)

required = ['schema', 'agent', 'status', 'artifacts', 'acceptance_criteria_met',
            'acceptance_criteria_failed', 'next_action', 'handoff_target', 'notes']
missing = [k for k in required if k not in obj]
if missing:
    print(f'MISSING_FIELDS:{missing}')
    sys.exit(0)

if obj.get('schema') != 'agent_result_v1':
    print(f'WRONG_SCHEMA:{obj.get(\"schema\")}')
    sys.exit(0)

status = obj.get('status', '')
next_action = obj.get('next_action', '')
handoff_target = obj.get('handoff_target')
failed = obj.get('acceptance_criteria_failed', [])
run_id = obj.get('pipeline_run_id', '')
agent = obj.get('agent', '')
artifacts = len(obj.get('artifacts', []))
met = len(obj.get('acceptance_criteria_met', []))
fail_count = len(failed)
notes = obj.get('notes', '')

print(f'OK|{agent}|{status}|{next_action}|{artifacts}|{met}|{fail_count}|{run_id}|{notes}')
" 2>/dev/null || echo "PARSE_ERROR")

{
  if [[ "$PARSE_RESULT" == "MISSING_ENVELOPE" ]]; then
    echo "[$(timestamp)] run=${RUN_ID} subagent=${AGENT} ERROR: no agent_result_v1 block in output"
  elif [[ "$PARSE_RESULT" == INVALID_JSON:* ]]; then
    echo "[$(timestamp)] run=${RUN_ID} subagent=${AGENT} ERROR: malformed JSON in agent_result_v1 — ${PARSE_RESULT}"
  elif [[ "$PARSE_RESULT" == MISSING_FIELDS:* ]]; then
    echo "[$(timestamp)] run=${RUN_ID} subagent=${AGENT} ERROR: missing required fields — ${PARSE_RESULT}"
  elif [[ "$PARSE_RESULT" == WRONG_SCHEMA:* ]]; then
    echo "[$(timestamp)] run=${RUN_ID} subagent=${AGENT} ERROR: wrong schema value — ${PARSE_RESULT}"
  elif [[ "$PARSE_RESULT" == PARSE_ERROR ]]; then
    echo "[$(timestamp)] run=${RUN_ID} subagent=${AGENT} ERROR: parser crashed — check hook script"
  elif [[ "$PARSE_RESULT" == OK\|* ]]; then
    IFS='|' read -r _ agent status next_action artifacts met fail_count run_id notes <<< "$PARSE_RESULT"
    log_run="${run_id:-${RUN_ID}}"
    echo "[$(timestamp)] run=${log_run} agent=${agent} status=${status} next=${next_action} artifacts=${artifacts} met=${met} failed=${fail_count} notes=${notes}"
    if [[ "$status" == "fail" ]] && [[ "$next_action" != "retry" ]] && [[ "$next_action" != "handoff" ]]; then
      echo "[$(timestamp)] run=${log_run} agent=${agent} WARN: status=fail but next_action=${next_action} — check remediation"
    fi
  fi
} >> "$LOG_FILE"

# Hard halt on contract violations (Q3 decision: hard halt)
case "$PARSE_RESULT" in
  MISSING_ENVELOPE|INVALID_JSON:*|MISSING_FIELDS:*|WRONG_SCHEMA:*|PARSE_ERROR)
    echo "HOOK_ERROR: agent_result_v1 contract violation from subagent '${AGENT}'. See .claude/logs/handoff-contract.log for details." >&2
    exit 1
    ;;
esac

exit 0
