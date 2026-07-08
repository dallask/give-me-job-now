# Hook Parity Checklist — scripts/runtime/gmj_sdk_runner.py (EXPERIMENTAL)

This checklist is EXPERIMENTAL/UNSUPPORTED FOR AUTONOMOUS RUNS UNTIL PARITY IS VERIFIED. It
covers exactly the two safety mechanisms SDK-03 requires: the `PreToolUse` scope guard and the
`SubagentStop` envelope-validation guard. Neither item required reimplementing the underlying
enforcement logic — both `gmj_sdk_runner.py` hook callbacks shell out to the existing,
**unmodified** `.claude/hooks/*.sh` scripts; only the registration mechanism changes (an
in-process Python async callable registered on `ClaudeAgentOptions.hooks`, instead of a
shell-invoked hook registered in `.claude/settings.json`).

## (a) PreToolUse scope guard

- **Target:** `.claude/hooks/gmj-sources-scope-guard.sh` (allow-list enforcement over
  `config/sources.yaml`, INTAKE-05).
- **Status: verified.**
- **Reasoning:** `gmj_sdk_runner.py::pretooluse_scope_guard` shells out to this unmodified
  script via `subprocess.run`, translating the SDK's `PreToolUseHookInput` dict into the exact
  JSON stdin shape the script already parses. This is directly, end-to-end exercised — not
  merely asserted — by `tests/test_gmj_sdk_runner.py::test_pretooluse_scope_guard_denies_offscope_host`
  (asserts a real deny decision against a real, isolated `config/sources.yaml` copy) and
  `tests/test_gmj_sdk_runner.py::test_pretooluse_scope_guard_allows_in_scope_host` (asserts a
  real allow/pass-through against an in-scope host from that same real config file), plus
  `tests/test_gmj_sdk_runner.py::test_pretooluse_scope_guard_passthrough_non_web_tool` (confirms
  non-`WebSearch`/`WebFetch` tool calls pass through untouched, matching the `.sh` script's own
  early-`exit 0` contract). These tests call the real `.sh` script as a real subprocess — no
  mocking of the enforcement layer itself.
- **Mechanism:** `gmj_sdk_runner.py::pretooluse_scope_guard` (in-process async hook registered
  under `ClaudeAgentOptions.hooks["PreToolUse"]`) shells out to the unmodified
  `.claude/hooks/gmj-sources-scope-guard.sh`.
- **Field mapping:** `tool_name`, `tool_input` — identical field names on both sides
  (live-confirmed by 38-RESEARCH.md's live `hook_test.py` run and mirrored directly in
  `pretooluse_scope_guard`'s payload construction). No renaming was needed for this item.

## (b) SubagentStop envelope validation

- **Target:** `.claude/hooks/gmj-validate-envelope.sh` /
  `scripts/contracts/gmj_validate_envelope.py` (`agent_result_v1` schema check, GUARD-01).
- **Status: not independently verified — reasoned from API docs.**
- **Reasoning:** This prototype's minimal `run_spoke()` dispatches via a single, system-prompt-only
  `claude_agent_sdk.query()` call with no nested `Task`/`AgentDefinition` inside that call — it is
  itself the top-level spoke dispatch, not a hub spawning a further subagent. Because of that, the
  SDK's own `SubagentStop` event does not fire within this vertical slice's own test suite; there
  is no real bad-envelope scenario to trigger it against in-process. The hook-registration API
  shape and live firing behavior for `SubagentStop` WAS independently live-verified during the
  research spike, however: `38-RESEARCH.md`'s `subagent_test.py` registered a real
  `SubagentStop` `HookMatcher`, dispatched a real named subagent via `AgentDefinition` + the `Task`
  tool, and observed the hook fire with a full field set (`session_id`, `transcript_path`, `cwd`,
  `prompt_id`, `permission_mode`, `agent_id`, `agent_type`, `effort`, `hook_event_name`,
  `stop_hook_active`, `agent_transcript_path`, `last_assistant_message`, `background_tasks`,
  `session_crons`) — a live, executed result, not a documentation read.
  `gmj_sdk_runner.py::subagentstop_envelope_guard` is implemented and registered in
  `ClaudeAgentOptions.hooks["SubagentStop"]` following that exact live-confirmed field mapping
  (`transcript_path`, `agent_id` — identical names on both sides, per that same research session),
  and its shell-out-to-the-unmodified-`.sh`-script logic is structurally identical to (a)'s proven
  pattern, but its own fire path is not exercised by this prototype's own test suite (no nested
  subagent dispatch occurs in `run_spoke()`'s single `query()` call). Note the SDK-only extra
  field `last_assistant_message`, which is absent from the CLI path's own `SubagentStop` hook
  stdin shape (`{transcript_path, agent_id, agent_type}` per `gmj-validate-envelope.sh`'s own
  header comments) — RESEARCH.md Pitfall 3 flags this as a real field-set divergence a future
  contributor must not assume away.
- **Mechanism:** `gmj_sdk_runner.py::subagentstop_envelope_guard` (in-process async hook
  registered under `ClaudeAgentOptions.hooks["SubagentStop"]`) shells out to the unmodified
  `.claude/hooks/gmj-validate-envelope.sh`.
- **Field mapping:** `transcript_path` — identical name; `agent_id`/`agent_type` — identical
  name; `last_assistant_message` — **SDK-only addition**, not present in the CLI path's own hook
  stdin (RESEARCH.md Pitfall 3).

## Summary

Neither checklist item required reimplementing the underlying enforcement logic in Python — both
(a) and (b) shell out to the existing, unmodified `.sh` scripts that already gate the default
Claude Code CLI path, so there is exactly one implementation of each safety mechanism, not two
that could silently drift. Item (a) is fully, end-to-end proven by this prototype's own test
suite against real subprocess calls. Item (b) reuses the identical shell-out pattern and a
live-confirmed field mapping from the research spike, but its own fire path inside this
prototype's minimal single-`query()`-call vertical slice is not independently exercised — this is
recorded here explicitly, not silently assumed, per CONTEXT.md's required wording.
