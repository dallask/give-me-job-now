#!/usr/bin/env bash
# Full-suite runner for the Phase 02 contract layer (ARCH-04/05/06, GUARD-01).
#
# Wraps the RESEARCH Code Examples into one gate:
#   - per-kind valid/invalid schema validation (gmj_validate_envelope.py),
#   - hash reproducibility demo (gmj_hash_artifact.py, ARCH-05),
#   - deterministic route demo (gmj_route.py, ARCH-06),
#   - the SubagentStop hook's offline extraction+validation path against the
#     mock transcript fixture (validate-envelope.sh must BLOCK the malformed envelope).
#
# Prints one line per check and a final PASS/FAIL summary; exits 0 only if every
# check passes. No pytest/unittest dependency — plain exit-code assertions, matching
# repo convention (RESEARCH Validation Architecture).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VALIDATOR="scripts/contracts/gmj_validate_envelope.py"
HASHER="scripts/contracts/gmj_hash_artifact.py"
ROUTER="scripts/pipeline/gmj_route.py"
HOOK=".claude/hooks/validate-envelope.sh"
SAMPLES="schemas/samples"
DAG="config/pipeline.dag.yaml"
MOCK="tests/fixtures/mock_transcript.jsonl"
LOG="${REPO_ROOT}/.claude/logs/validate-envelope.log"

PASS=0
FAIL=0

# check <description> <expected: 0|nonzero> <actual-rc>
check() {
  local desc="$1" expect="$2" rc="$3"
  if { [ "$expect" = "0" ] && [ "$rc" -eq 0 ]; } || { [ "$expect" = "nonzero" ] && [ "$rc" -ne 0 ]; }; then
    printf 'PASS  %s\n' "$desc"
    PASS=$((PASS + 1))
  else
    printf 'FAIL  %s (expected %s, got rc=%s)\n' "$desc" "$expect" "$rc"
    FAIL=$((FAIL + 1))
  fi
}

# Run a command silently and echo its exit code without tripping `set -e`.
rc_of() {
  set +e
  "$@" >/dev/null 2>&1
  local rc=$?
  set -e
  printf '%s' "$rc"
}

echo "== Phase 02 contract full-suite =="

# 1. Per-kind schema validation: valid → 0, invalid → non-zero (ARCH-04, GUARD-01)
for kind in offer_spec artifact_draft gate_result; do
  check "validate ${kind}.valid   → accept" 0       "$(rc_of python3 "$VALIDATOR" --file "$SAMPLES/${kind}.valid.json")"
  check "validate ${kind}.invalid → reject" nonzero "$(rc_of python3 "$VALIDATOR" --file "$SAMPLES/${kind}.invalid.json")"
done

# 1b. Gate B/C content variants (Phase 06): both must validate against the extended gate_result schema.
check "validate gate_result.gateb.valid → accept" 0 "$(rc_of python3 "$VALIDATOR" --file "$SAMPLES/gate_result.gateb.valid.json")"
check "validate gate_result.gatec.valid → accept" 0 "$(rc_of python3 "$VALIDATOR" --file "$SAMPLES/gate_result.gatec.valid.json")"

# 2. Hash reproducibility (ARCH-05)
A=$(python3 "$HASHER" --kind offer_spec --file "$SAMPLES/offer_spec.valid.json")
B=$(python3 "$HASHER" --kind offer_spec --file "$SAMPLES/offer_spec.valid.json")
if [ "$A" = "$B" ]; then check "hash reproducible (identical input → identical hash)" 0 0; else check "hash reproducible" 0 1; fi

# 3. Deterministic route (ARCH-06): sample state → gmj-fit-evaluator, no LLM
ROUTE_OUT=$(python3 "$ROUTER" --state "$SAMPLES/state.sample.json" --dag "$DAG" 2>/dev/null || true)
if printf '%s' "$ROUTE_OUT" | grep -q 'gmj-fit-evaluator'; then check "route sample state → gmj-fit-evaluator" 0 0; else check "route sample state → gmj-fit-evaluator (got: $ROUTE_OUT)" 0 1; fi

# 4. SubagentStop hook extraction+validation path (ARCH-04): must BLOCK the mock malformed envelope
HOOK_INPUT=$(printf '{"transcript_path":"%s/%s","agent_id":"gmj-offer-scout"}' "$REPO_ROOT" "$MOCK")
HOOK_RC=$(set +e; printf '%s' "$HOOK_INPUT" | CLAUDE_PROJECT_DIR="$REPO_ROOT" bash "$HOOK" >/dev/null 2>&1; printf '%s' $?; set -e)
check "hook blocks malformed mock envelope" nonzero "$HOOK_RC"
# The block must be recorded with a structured field-path error naming the offending field.
if tail -1 "$LOG" 2>/dev/null | grep -q 'BLOCK:.*status'; then
  check "hook logs field-path error (status)" 0 0
else
  check "hook logs field-path error (status)" 0 1
fi

echo "----------------------------------"
printf 'Total: %d passed, %d failed\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS"
else
  echo "RESULT: FAIL"
fi
[ "$FAIL" -eq 0 ]
