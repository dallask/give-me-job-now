# Execution-log gsd-workflow-layer wiring (D-01 fallback)

**Status:** writer ready, dispatch point pending a GSD-core-side hook. This is an
explicit, documented partial-completion state, not a silent gap.

## Why this doc exists

Phase 06's `06-CAPABILITY-SPIKE.md` (Plan 01) investigated whether the
`gsd-workflow-step-granularity` capture layer (D-01) could be wired as a real
`.gsd/capabilities/execution-log/` overlay — the GSD-idiomatic mechanism used by
first-party capabilities like `code-review`, `drift`, and `mempalace` at loop-hook
points such as `execute:post`/`ship:post`.

The spike's binding result:

```
VERDICT: fallback-required
```

Root cause (recorded in full in `06-CAPABILITY-SPIKE.md`): `gsd-tools capability
install --scope project --yes` is blocked by an `engines.gsd ">=1.6.0"` pre-check that
resolves the running host version to `0.0.0` (a `readHostVersion()` resolution defect
in this installation's `gsd-core` payload — the real running version is `1.6.1`, per
independent `capability list --raw` / `capability state --raw` cross-checks). This is a
false negative in an environment defect external to this repo (`gsd-core` is
externally maintained tooling, not this repo's own code) — not a structural or
consent-flow problem with the overlay-authoring mechanism itself, and not something
this repo should route around by editing `gsd-core` internals.

Per this phase's `<scope_reduction_prohibition>`/planner-authority constraints, this
plan (06-03) does not re-litigate or silently diverge from that VERDICT: it does
**not** author a `.gsd/capabilities/execution-log/` overlay. Instead, it documents the
ready-to-invoke writer and the pending dispatch gap explicitly, here.

## What is built and ready today

`scripts/gmj_execution_log_writer.py` is a complete, tested, standalone CLI script.
Given the phase/plan/wave/outcome context available at any GSD loop-hook dispatch
point, it appends one structured JSONL entry tagged `source: "gsd-workflow"` to
`.planning/execution-logs/gsd-workflow-<YYYY-MM-DD>.jsonl` — the same directory Plan
02's tool-call-granularity hook (`.claude/hooks/gmj-execution-log.sh`) already writes
`tool-calls-<date>.jsonl` entries into, using a distinct per-source file-naming
convention so the two independent writer layers never contend for the same file
handle.

Example invocation (exactly what a future dispatch point would run):

```bash
python3 scripts/gmj_execution_log_writer.py \
  --point execute:post --phase 6 --plan 03 --wave 2 --outcome pass
```

This appends an entry shaped like:

```json
{"ts": "2026-07-12T10:30:00Z", "source": "gsd-workflow", "point": "execute:post", "phase": "6", "plan": "03", "wave": "2", "outcome": "pass"}
```

The full CLI contract (`--point`, `--phase`, `--plan`, `--wave`, `--outcome`,
`--log-dir`, `--extra-json`), its fail-closed CLI-usage-error behavior (invalid
`--outcome`/`--point` exits non-zero with a stderr message), and its fail-open
runtime-degradation behavior (an unwritable log directory prints a stderr warning and
still exits 0 — D-09, never a workflow-blocking failure) are all covered by
`tests/test_gmj_execution_log_writer.py`.

## What is NOT done: the dispatch point

`execute-phase.md`/`ship.md` (and the other GSD workflow files that would call this
script at `execute:post`/`ship:post`) are GSD-core-owned files — outside this repo's
`scripts/`/`.claude/` ownership boundary per `docs/ARCHITECTURE.md`'s conventions —
and are **not edited by this plan**. No code in this repo currently invokes
`gmj_execution_log_writer.py` automatically at any loop-hook boundary.

This means REFLECT-01's gsd-workflow-layer coverage is: **writer ready, dispatch point
pending a GSD-core-side hook.** The tool-call-granularity layer (Plan 02,
`.claude/hooks/gmj-execution-log.sh`) is fully wired and live today; this
gsd-workflow-layer writer is a ready-to-invoke script awaiting its dispatch point.

Downstream consumers (Plan 04's analyzer) must handle an empty/absent
`gsd-workflow-*.jsonl` glob gracefully — this phase's success criteria do not assume
gsd-workflow-layer entries exist unconditionally (see `06-03-PLAN.md`'s threat register,
T-06-03-04).

## Recommended paths forward (unchanged from 06-CAPABILITY-SPIKE.md's ranking)

1. **Retry the overlay path** once the `engines.gsd` host-version-resolution defect is
   independently fixed upstream in `gsd-core`, or by omitting `engines.gsd` entirely
   from a future capability manifest (confirmed optional by `validateVersionEnvelope`).
   This is the GSD-idiomatic path and should be preferred if/when it becomes viable.
2. **Wire a locally-owned wrapper command** that directly shells out to
   `scripts/gmj_execution_log_writer.py` at the points where this repo's own tooling
   (not GSD-core's shared workflow files) already has phase/plan/wave/outcome context
   available — e.g. from a project-local slash command or script that already knows it
   just finished an `execute:post`-equivalent step.

Either path is a future, separate change. Re-verify this doc against
`06-CAPABILITY-SPIKE.md`'s VERDICT (and re-attempt path 1 first) after any GSD-core
update, per this repo's general `rules/docs-currency.md` convention.
