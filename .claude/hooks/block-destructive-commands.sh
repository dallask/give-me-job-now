#!/usr/bin/env sh
# PreToolUse — block destructive Bash (exit 2 = block). Adapted from example collective.
set -e

LOG_FILE="${CLAUDE_PROJECT_DIR:-.}/.claude/logs/blocked-commands.log"
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

log() { echo "[$(timestamp)] $1" >> "$LOG_FILE" 2>/dev/null || true; }

INPUT_JSON=$(cat)

TOOL_NAME=""
COMMAND=""

if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(echo "$INPUT_JSON" | jq -r '.tool_name // empty' 2>/dev/null)
  COMMAND=$(echo "$INPUT_JSON" | jq -r '.tool_input.command // empty' 2>/dev/null)
fi

if [ -z "$TOOL_NAME" ]; then
  TOOL_NAME=$(echo "$INPUT_JSON" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

if [ -z "$COMMAND" ]; then
  COMMAND=$(echo "$INPUT_JSON" | grep -o '"command":"[^"]*"' | head -1 | sed 's/.*"command":"\(.*\)"/\1/')
fi

log "Bash check: $COMMAND"

block_command() {
  echo "BLOCKED: $1" >&2
  echo "Command: $2" >&2
  log "BLOCKED: $1 — $2"
  exit 2
}

case "$COMMAND" in
  *"rm -rf"*|*"rm -fr"*) block_command "recursive force deletion" "$COMMAND" ;;
esac

echo "$COMMAND" | grep -qiE 'rm[[:space:]]+.*-[[:alnum:]]*r[[:alnum:]]*f|rm[[:space:]]+.*-[[:alnum:]]*f[[:alnum:]]*r' && block_command "recursive rm -rf pattern" "$COMMAND"

echo "$COMMAND" | grep -qiE 'git[[:space:]]+reset[[:space:]]+--hard' && block_command "git reset --hard" "$COMMAND"
echo "$COMMAND" | grep -qiE 'git[[:space:]]+push[[:space:]]+.*--force' && block_command "git force push" "$COMMAND"
echo "$COMMAND" | grep -qiE 'curl[[:space:]].*\|[[:space:]]*(sh|bash|zsh)' && block_command "curl pipe to shell" "$COMMAND"
echo "$COMMAND" | grep -qiE 'wget[[:space:]].*\|[[:space:]]*(sh|bash|zsh)' && block_command "wget pipe to shell" "$COMMAND"
echo "$COMMAND" | grep -qiE 'docker[[:space:]]+system[[:space:]]+prune[[:space:]]+.*-f' && block_command "docker prune -f" "$COMMAND"

log "ALLOWED"
exit 0
