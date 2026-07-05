#!/usr/bin/env bash
# SubagentStop — schema-validate the spoke's agent_result_v1 envelope; block on failure.
#
# ARCH-04 / GUARD-01: this is a THIN wrapper around scripts/contracts/gmj_validate_envelope.py.
# It does NOT re-implement jsonschema validation in Bash.
#
# RESEARCH Pitfall 1: SubagentStop stdin carries {transcript_path, agent_id, agent_type}
# — NOT the subagent output. We read `transcript_path` and extract the agent_result_v1
# block from the CURRENT subagent's FINAL assistant message only, then pipe it to the
# validator via --stdin.
#
# Scoping fix (#t8o): the transcript is shared across the whole session, so a stale or
# malformed envelope emitted by an EARLIER turn/subagent must never be re-validated on a
# later, unrelated SubagentStop. Validating the transcript-global last envelope caused a
# non-spoke subagent (e.g. a GSD executor that emits no envelope at all) to be blocked
# indefinitely by a leftover `uat02-bad` envelope. We therefore look ONLY at the final
# assistant message: real spokes carry their envelope there (still fully validated), while
# a final message with no envelope legitimately SKIPs.
#
# RESEARCH Pitfall 2: a SubagentStop block "prevents the subagent from stopping" and does
# not feed the reason back to the hub. The durable record is therefore the log; the
# existing PostToolUse:Task hook (gmj-collective-handoff-contract.sh) remains the complementary
# outer-contract gate and is intentionally left untouched.
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_FILE="${PROJECT_DIR}/.claude/logs/validate-envelope.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

INPUT_JSON=$(cat || true)

# Parse a top-level string field from the stdin JSON (jq with python3 fallback,
# per gmj-collective-handoff-contract.sh lines 22-23).
read_field() {
  local field="$1" val=""
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

TRANSCRIPT=$(read_field transcript_path)
AGENT_ID=$(read_field agent_id)

# RESEARCH Pitfall 1: nothing to validate if there is no transcript to read.
if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ]; then
  echo "[$(timestamp)] agent=${AGENT_ID:-unknown} SKIP: no readable transcript_path (nothing to validate)" >> "$LOG_FILE"
  exit 0
fi

# Extract the fenced agent_result_v1 block from the CURRENT subagent's FINAL assistant
# message. Reuses the same fenced-block regex as gmj-collective-handoff-contract.sh lines
# 82-83, but scoped to the last assistant message (not the transcript-global last match)
# so a stale envelope from an earlier turn/subagent is never re-validated (#t8o).
ENVELOPE=$(python3 - "$TRANSCRIPT" <<'PY' 2>/dev/null || true
import json, re, sys

path = sys.argv[1]
messages = []  # one concatenated text string per assistant message, transcript order
try:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = obj.get("message", obj) if isinstance(obj, dict) else {}
            # Only assistant messages carry the envelope; be liberal if role is absent.
            if isinstance(msg, dict) and msg.get("role") not in (None, "assistant"):
                continue
            content = msg.get("content") if isinstance(msg, dict) else None
            if content is None and isinstance(obj, dict):
                content = obj.get("content")
            parts = []
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
            if parts:
                messages.append("\n".join(parts))
except Exception:
    pass

# Scope to the current subagent's final output only: a non-spoke subagent whose last
# message has no envelope yields nothing here -> downstream SKIP (no false block).
final = messages[-1] if messages else ""
matches = re.findall(r"```agent_result_v1\s*\n(.*?)\n\s*```", final, re.DOTALL)
if matches:
    sys.stdout.write(matches[-1].strip())
PY
)

if [ -z "$ENVELOPE" ]; then
  echo "[$(timestamp)] agent=${AGENT_ID:-unknown} SKIP: no agent_result_v1 block found in transcript" >> "$LOG_FILE"
  exit 0
fi

# Thin-wrapper delegation: the executed validator owns all jsonschema logic and emits
# structured "<field/path>: <message>" errors on stderr (GUARD-01).
VALIDATOR="${PROJECT_DIR}/scripts/contracts/gmj_validate_envelope.py"
set +e
ERR_OUT=$(printf '%s' "$ENVELOPE" | python3 "$VALIDATOR" --stdin 2>&1 >/dev/null)
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  REASON_ONELINE=$(printf '%s' "$ERR_OUT" | tr '\n' ';' | sed 's/;*$//')
  echo "[$(timestamp)] agent=${AGENT_ID:-unknown} BLOCK: ${REASON_ONELINE}" >> "$LOG_FILE"
  # RESEARCH Pitfall 2: emit a block decision + reason on stdout (and exit 2). The hub is
  # not guaranteed to receive this, so the log above is the authoritative record.
  REASON_JSON=$(printf '%s' "$ERR_OUT" | python3 -c "import json,sys; sys.stdout.write(json.dumps(sys.stdin.read().strip()))" 2>/dev/null || printf '"envelope validation failed"')
  printf '{"decision":"block","reason":%s}\n' "$REASON_JSON"
  exit 2
fi

echo "[$(timestamp)] agent=${AGENT_ID:-unknown} OK: envelope valid" >> "$LOG_FILE"
exit 0
