# Hook Parity Checklist — gmj-core/bin/gmj-cursor-adapter.cjs (EXPERIMENTAL)

This checklist is EXPERIMENTAL/UNSUPPORTED FOR AUTONOMOUS RUNS UNTIL PARITY IS VERIFIED. The
generator's own scope is roster-file translation only — it builds no Cursor-side enforcement
dispatcher itself. Every item below records what IS and IS NOT independently proven about
Cursor's own native mechanisms, mirroring the discipline `scripts/runtime/HOOK-PARITY.md`
already established for the Claude Agent SDK prototype (Phase 38).

## (a) PreToolUse scope guard

- **Target:** `.claude/hooks/gmj-sources-scope-guard.sh` (allow-list enforcement over
  `config/sources.yaml`).
- **Status: "not independently verified — reasoned from direct installed-binary source inspection, needs a human's live Cursor session to confirm"**
- **Reasoning:** `39-RESEARCH.md` Finding 1 confirms — via this session's direct read of the
  installed `cursor-agent` binary's own source — a real `preToolUse` hook event with a genuine
  pre-execution `allow`/`deny`/`ask` veto. Finding 2 confirms the binary's hook-config resolver
  explicitly includes `claudeProjectConfigPath`/`claudeProjectLocalConfigPath` (i.e. this repo's
  own `.claude/settings.json`) in its search list, and its Claude-Code-tool-name mapping table
  maps `WebFetch`/`WebSearch` to themselves with no renaming — making this repo's existing,
  unmodified `PreToolUse` registration a plausible zero-adapter-code reuse candidate. This could
  NOT be exercised end-to-end in this or any sandboxed environment: no `CURSOR_API_KEY`/
  `cursor-agent login` credentials are available (confirmed via a real, fast-failing live attempt
  this session — `Error: Authentication required`), so it remains a documented hypothesis, not a
  proven fact.
- **Mechanism:** IF Finding 2 holds, Cursor's native hook dispatcher would call the SAME
  unmodified `.claude/hooks/gmj-sources-scope-guard.sh` this repo's Claude Code path already uses
  — never a second, hand-ported implementation (`39-RESEARCH.md` Pattern 1, "one implementation,
  not two").
- **Field mapping:** `tool_name`, `tool_input` — identical field names on both sides, per the
  binary's own confirmed translation table.

## (b) SubagentStop envelope validation

- **Target:** `.claude/hooks/gmj-validate-envelope.sh` / `scripts/contracts/gmj_validate_envelope.py`.
- **Status: "not independently verified — reasoned from direct installed-binary source inspection"**
- **Reasoning:** `39-RESEARCH.md` Finding 4 confirmed a real `subagentStop` hook event exists in
  the installed binary's own source, with a field set independently cross-corroborated against
  Cursor's own published docs. This phase built no dispatcher wiring it at all — out of
  PROVIDER-02's locked minimal scope (roster generation only, no orchestrator changes, no
  Cursor-native pipeline re-validation). Its fire path is therefore not exercised by any test in
  this phase at all, a stronger caveat than even Phase 38's own SDK precedent (which at least had
  a registered, if unexercised, callback).

## (c) Task-nesting / hub-and-spoke discipline

- **Status: "open — no runtime equivalent; enforced by code review/convention only"**
- **Reasoning:** `39-RESEARCH.md` Finding 5: multiple independent `forum.cursor.com` bug reports
  (Jan–Apr 2026) describe Cursor's own `Task` tool as unstable/inconsistently available across
  contexts, and no systemic "nested-subagents-cannot-call-Task" invariant analogous to Claude
  Code's was found — the default appears **OPEN** (nesting possible) rather than **CLOSED**
  (nesting architecturally impossible), the opposite default from Claude Code. This generator's
  own mitigation is limited to the `gmj-orchestrator.md` translation's dual-placed "DO NOT INVOKE
  AS A SUBAGENT" banner (built in Plan 39-01) — a documentation-level convention, not a runtime
  guarantee. Finding 4's `subagentStart` + `parent_conversation_id` combination is a theoretically
  viable future runtime guard, explicitly NOT built this phase (out of scope, per CONTEXT.md).

## (d) Tool-grant precision loss (`tools:` -> `readonly:`)

- **Status: "known, permanent precision loss — documented, not closeable this phase"**
- **Reasoning:** Cursor's subagent frontmatter exposes only a coarse `readonly` boolean, with no
  per-tool allow-list field (confirmed exhaustively via the installed CLI's own embedded help
  text). Every generated `.cursor/agents/*.md` file's own header comment documents the original
  Claude Code `tools:` grant verbatim (`39-RESEARCH.md` Pitfall 2), and
  `tests/test_gmj_cursor_adapter.py::test_readonly_split_matches_research_table` (Plan 39-01)
  proves the coarse mapping matches the documented table exactly.

## Summary

Neither item (a) nor item (b) required reimplementing the underlying enforcement logic — both
record what would call the existing, unmodified `.claude/hooks/gmj-sources-scope-guard.sh` /
`scripts/contracts/gmj_validate_envelope.py`, the same "one implementation, not two" principle
`scripts/runtime/HOOK-PARITY.md` already established for the SDK prototype. Item (a)'s exact
status tag: **"not independently verified — reasoned from direct installed-binary source
inspection, needs a human's live Cursor session to confirm"**. PROVIDER-01's verdict
(`39-RESEARCH.md`): **CONDITIONAL GO**. The single concrete next step that would close items
(a)/(b): a human with a real, authenticated Cursor account running `cursor-agent` against this
exact repo (or a scratch copy) and attempting an off-`sources.yaml`-scope `WebSearch`/
`WebFetch`-shaped action, confirming whether the existing `.claude/settings.json` hook fires with
no new `.cursor/hooks.json` file present.
