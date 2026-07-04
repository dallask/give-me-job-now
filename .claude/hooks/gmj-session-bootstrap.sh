#!/usr/bin/env bash
# SessionStart — remind operators of collective paths and generate pipeline run ID.
# Stdout only; never blocks the session.
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-.}"

# Generate a unique pipeline run ID for this session.
# Format: YYYYMMDDTHHMMss-<6 hex chars>
PIPELINE_RUN_ID="$(date +%Y%m%dT%H%M%S)-$(LC_ALL=C tr -dc 'a-f0-9' </dev/urandom 2>/dev/null | head -c6 || echo "000000")"
export PIPELINE_RUN_ID

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " give-me-job · Job/CV collective"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Orchestrator (hub): gmj-orchestrator"
echo " Routing schema: Request → Analysis → Selection → Delegation → Quality Gate → Result"
echo ""
echo " Paths:"
echo "   Sources (inputs):     ${ROOT}/sources/"
echo "   Candidate YAML:       ${ROOT}/config/candidate.yaml"
echo "   CV PDF output:        ${ROOT}/output/cv/"
echo "   Extract/render:       ${ROOT}/scripts/cv/"
echo ""
echo " Slash command: /gmj-collective (see .claude/commands/gmj-collective.md)"
echo " Pipeline run ID: ${PIPELINE_RUN_ID}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
