#!/usr/bin/env bash
# SessionStart — remind operators of collective paths (stdout only; never block)
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-.}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " give-me-job · Job/CV collective"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Orchestrator (hub): vacancy-orchestrator"
echo " Routing schema: Request → Analysis → Selection → Delegation → Quality Gate → Result"
echo ""
echo " Paths:"
echo "   Sources (inputs):     ${ROOT}/sources/"
echo "   Candidate YAML:       ${ROOT}/config/candidate.yaml"
echo "   CV PDF output:        ${ROOT}/output/cv/"
echo "   Extract/render:       ${ROOT}/scripts/cv/"
echo ""
echo " Slash command: /job-collective (see .claude/commands/job-collective.md)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
