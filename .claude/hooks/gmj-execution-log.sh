#!/usr/bin/env sh
# Pure-observability hook (D-02, REFLECT-01/02/05): appends one structured JSONL
# entry per Bash/WebSearch/WebFetch/Task/Write/Edit/SubagentStop tool-call event to
# .planning/execution-logs/tool-calls-<date>.jsonl. This hook NEVER blocks — no
# `set -e` (RESEARCH.md Pitfall 1: a blocking hook's `set -e` header must never be
# copy-pasted into a pure-logging hook), every mkdir/write individually guarded with
# `|| true`, and an unconditional `exit 0` at the very end regardless of code path.
#
# Blended from two existing precedents in this repo:
#   - gmj-block-destructive-commands.sh: PreToolUse stdin JSON field extraction
#     (jq-then-python3 fallback chain).
#   - gmj-validate-envelope.sh: named `read_field` helper, log-dir setup, and the
#     SubagentStop transcript_path/agent_id guard (path recorded, content NOT read
#     here — that is Plan 04's analyzer's job).

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_DIR="${PROJECT_DIR}/.planning/execution-logs"
LOG_FILE="${LOG_DIR}/tool-calls-$(date -u '+%Y-%m-%d').jsonl"
mkdir -p "$LOG_DIR" 2>/dev/null || true

INPUT_JSON=$(cat 2>/dev/null || true)

# Named field reader (jq-then-python3 fallback), mirrors gmj-validate-envelope.sh
# lines 35-48 exactly — never string-interpolate raw JSON into a shell command.
read_field() {
  field="$1"
  val=""
  if command -v jq >/dev/null 2>&1; then
    val=$(printf '%s' "$INPUT_JSON" | jq -r --arg f "$field" '.[$f] // empty' 2>/dev/null || true)
  fi
  if [ -z "$val" ]; then
    val=$(printf '%s' "$INPUT_JSON" | FIELD="$field" python3 -c "import json,os,sys
try:
    print(json.load(sys.stdin).get(os.environ['FIELD'], ''))
except Exception:
    pass" 2>/dev/null || true)
  fi
  printf '%s' "$val"
}

# tool_name via the jq-then-python3 fallback chain, mirrors
# gmj-block-destructive-commands.sh lines 16-23.
TOOL_NAME=""
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT_JSON" | jq -r '.tool_name // empty' 2>/dev/null || true)
fi
if [ -z "$TOOL_NAME" ]; then
  TOOL_NAME=$(printf '%s' "$INPUT_JSON" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*:[[:space:]]*"\(.*\)"/\1/')
fi

EVENT_NAME=$(read_field hook_event_name)
TRANSCRIPT_PATH=$(read_field transcript_path)
AGENT_ID=$(read_field agent_id)

# For SubagentStop payloads: only the path is recorded, never the transcript's
# content (mirrors gmj-validate-envelope.sh's transcript_path guard, lines 50-57 —
# but this hook does not read the file at all, it only records the path string).
if [ -z "$EVENT_NAME" ] && [ -n "$TRANSCRIPT_PATH" ]; then
  EVENT_NAME="SubagentStop"
fi

# Build the JSONL line via python3 -c, never hand-built shell string concatenation
# (T-06-02-01 mitigation — json.dumps escapes embedded newlines/shell metacharacters
# safely). All raw untrusted values are passed as argv, never interpolated into a
# shell command or an f-string that touches the raw payload.
python3 -c "
import json, sys, datetime

tool_name = sys.argv[1] or 'unknown'
event_name = sys.argv[2] or 'unknown'
transcript_path = sys.argv[3]
agent_id = sys.argv[4]
input_json = sys.argv[5]

MAX_FIELD_LEN = 2000  # DoS mitigation (T-06-02-02): bound any single field's length.

def _truncate(value):
    if isinstance(value, str) and len(value) > MAX_FIELD_LEN:
        return value[:MAX_FIELD_LEN] + '...[truncated]'
    return value

try:
    payload = json.loads(input_json) if input_json else {}
    if not isinstance(payload, dict):
        payload = {}
except Exception:
    payload = {}

tool_input = payload.get('tool_input')
if not isinstance(tool_input, dict):
    tool_input = {}

entry = {
    'ts': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
    'source': 'tool-call',
    'event': event_name,
    'tool_name': tool_name,
    'outcome': 'observed',
}

# Bounded, truncated command capture (Bash tool calls).
command = tool_input.get('command')
if isinstance(command, str) and command:
    entry['command'] = _truncate(command)

# REFLECT-02: Write/Edit artifact-tracking — file_path (fallback: path).
file_path = tool_input.get('file_path') or tool_input.get('path')
if isinstance(file_path, str) and file_path:
    entry['artifacts'] = [_truncate(file_path)]
else:
    entry['artifacts'] = []

# SubagentStop-specific fields — path only, never transcript content.
if transcript_path:
    entry['transcript_path'] = _truncate(transcript_path)
if agent_id:
    entry['agent_id'] = _truncate(agent_id)

print(json.dumps(entry))
" "$TOOL_NAME" "$EVENT_NAME" "$TRANSCRIPT_PATH" "$AGENT_ID" "$INPUT_JSON" >> "$LOG_FILE" 2>/dev/null || true

# D-09/REFLECT-05: this hook never blocks — unconditional success exit regardless
# of whether the write above succeeded.
exit 0
