#!/usr/bin/env bash
# SubagentStop — non-blocking reminder to run quality gate after critical spokes
set -euo pipefail

INPUT_JSON=$(cat || true)
NAME=""
if command -v jq >/dev/null 2>&1; then
  NAME=$(echo "$INPUT_JSON" | jq -r '.tool_input.subagent_type // .stop_reason.subagent_type // empty' 2>/dev/null || true)
fi
if [ -z "$NAME" ]; then
  NAME=$(echo "$INPUT_JSON" | grep -o '"subagent_type":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
fi

case "$NAME" in
  cv-generator|artifact-composer|candidate-configurator|truth-verifier)
    echo "" >&2
    echo "━━━━━━━━ job-collective reminder ━━━━━━━━" >&2
    echo " Subagent '$NAME' stopped — have vacancy-orchestrator run the quality gate before final PASS." >&2
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
    ;;
esac

exit 0
