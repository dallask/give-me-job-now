# gmj-core/bin/gmj-cursor-adapter.README.md — Cursor roster generator (EXPERIMENTAL)

This generator and its output are **EXPERIMENTAL/UNSUPPORTED FOR AUTONOMOUS RUNS UNTIL PARITY
IS VERIFIED**. Its output (`.cursor/agents/*.md`) is **never** wired into `gmj-orchestrator.md`
or any default Claude Code path file — the existing `/gmj-collective` hub-and-spoke path remains
the default and is untouched by this generator or its output (see
`tests/test_gmj_cursor_adapter.py::test_default_claude_code_path_has_no_cursor_references`).

## What this is

`gmj-core/bin/gmj-cursor-adapter.cjs` is a roster **generator** — a pure file-transform script,
not a Cursor runtime and not a pipeline execution path. It translates this repo's 9
`.claude/agents/*.md` files into Cursor's `.cursor/agents/*.md` subagent format and nothing
else, per PROVIDER-02's minimal locked scope. It does not run the offer→artifact pipeline
against Cursor, does not spawn any Cursor session, and does not modify any `.claude/` file (the
generator is provably read-only with respect to its sources — see
`tests/test_gmj_cursor_adapter.py::test_generator_never_mutates_source_claude_agents_files`).

## Prerequisite

The **operator** needs their own Cursor CLI (`cursor-agent`) or Cursor IDE install to consume
the generated `.cursor/agents/*.md` output. This repo's own dependency manifests
(`requirements.txt` files, `.claude/package.json`) are unaffected and unrelated — the generator
itself is pure Node builtins with zero new dependencies (no `js-yaml`, no `npm install`).

## Usage

```bash
node gmj-core/bin/gmj-cursor-adapter.cjs generate
```

This resolves to the real defaults (`--src .claude/agents`, `--dest .cursor/agents`, both
relative to the repo root) and writes the translated roster directly into the working tree.
Override either side with `--src <dir>` / `--dest <dir>` (used only by this generator's own
fixture-based tests, never in normal operation).

## Field translation

| Claude Code field | Cursor field | Translation |
|---|---|---|
| `name` | `name` | Verbatim |
| `description` | `description` | Verbatim, plus an appended `[EXPERIMENTAL — Cursor adapter, generated from .claude/agents/<name>.md — see gmj-core/bin/CURSOR-HOOK-PARITY.md]` badge (and, for `gmj-orchestrator` only, an additional `[DO NOT INVOKE AS A SUBAGENT ...]` suffix) |
| `tools:` (an arbitrary Claude Code tool list) | `readonly:` (a coarse boolean) | **Lossy, documented translation, never claimed as equivalent.** Write-capable tools (`Write`, `Edit`, `Bash`, `Task`) force `readonly: false`; a `tools:` list containing none of those four resolves `readonly: true`. Only `gmj-truth-verifier` and `gmj-fit-evaluator` (both `Read, Glob, Grep`) resolve `readonly: true`; every other spoke resolves `readonly: false`. The original fine-grained `tools:` grant is preserved verbatim in the generated file's own header comment so a reader can see exactly what precision was lost. |
| `model: sonnet` | `model: inherit` | Cursor's own "use whatever the parent/session is using" value — never a literal `"sonnet"` passthrough, which is not a valid Cursor model ID |
| `color:` | — (dropped) | No Cursor equivalent field exists |

## Correction to an earlier assumption

Per `39-RESEARCH.md` Pitfall 1: Cursor's CLI has a tool **literally named `Task`**, confirmed via
this session's direct installed-binary source inspection (the binary's own Claude-Code-tool-name
mapping table maps `Task` to itself). This generator and its docs never state or imply that
Cursor lacks a `Task` tool. The real caution is different: `Task`'s availability is reportedly
unstable across Cursor's IDE/CLI/Cloud contexts (multiple `forum.cursor.com` bug reports, Jan–Apr
2026), and — unlike Claude Code, where nested `Task` is structurally absent — there is **no
confirmed structural restriction preventing a nested Cursor subagent from itself calling
`Task`**. The default on Cursor appears to be **open** (nesting possible), not **closed**
(nesting architecturally impossible), the opposite default from Claude Code.

## Hook parity

See [`gmj-core/bin/CURSOR-HOOK-PARITY.md`](./CURSOR-HOOK-PARITY.md) for the full enforcement-gap
checklist. In particular, the PreToolUse scope-guard hypothesis (whether Cursor's native hook
loader picking up this repo's unmodified `.claude/settings.json` actually enforces
`config/sources.yaml` on Cursor) is status:
**"not independently verified — reasoned from direct installed-binary source inspection, needs a human's live Cursor session to confirm"**.
Do not read this document, or any other document in this repo, as stating or implying that the
scope guard "works", "is enforced", or "is supported" on Cursor as a settled fact — it is a
strong, source-verified hypothesis pending a human's live-session confirmation.
