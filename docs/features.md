# Features — Core Value, Guarantees & Capabilities

give-me-job is a hub-and-spoke collective of Claude Code agents, commands, skills, and
deterministic scripts that, given a **real job offer**, produces a **truthful,
offer-optimized** set of application artifacts — a CV (PDF), a cover letter (PDF), and an
interview-prep document — that provably trace back to one candidate's real profile and pass
mandatory quality gates.

See also: the authoritative [architecture](ARCHITECTURE.md), the end-to-end
[flows.md](flows.md), and the per-spoke [agents.md](agents.md).

---

## Core value

> Given a real job offer, the system produces a truthful, offer-optimized set of application
> artifacts that provably trace back to the candidate's real profile and pass mandatory
> quality gates. If everything else fails, the artifacts must never fabricate and must
> actually target the offer.

The whole design is hardened against the classic multi-agent failure modes: fabricated
facts, off-target drift, context bloat, and silent quality decay.

---

## Guarantees

### Truthfulness (hard-blocked fabrication)

`config/candidate.yaml` is the **single source of truth**. Every claim in every artifact
must trace to a dotted/indexed span in that file. Reframing and emphasis are allowed;
invention is hard-blocked. `gmj-truth-verifier` re-grounds every claim at **Gate A** and
names any offending span — no artifact reaches "delivered" without a recorded Gate A pass.

### Target-fit (non-bypassable coverage gate)

`gmj-fit-evaluator` scores must-have coverage against the frozen offer at **Gate B**. A
Gate-B failure loops back to the composer with the missing must-haves named. An artifact
that does not actually target the offer cannot ship. **Gate C (polish)** runs alongside as
advisory-only.

### Non-bypassable gates in every mode

Gate A (truth) and Gate B (target-fit) are non-bypassable in **any** execution mode.
Autonomous mode removes the *human* pause, never the *machine* gate — the truth and
target-fit checks block identically whether a human is in the loop or not.

---

## Architecture principles

### Hub-and-spoke topology

One top-level hub — `gmj-orchestrator` — holds `Task` and delegates to bounded spokes
(`gmj-offer-scout`, `gmj-artifact-composer`, `gmj-truth-verifier`, `gmj-fit-evaluator`,
`gmj-cv-generator`), supported by `gmj-candidate-analyzer`, `gmj-candidate-configurator`,
and `gmj-template-creator`. Spokes never spawn spokes: a nested hub loses `Task`, so this is
a hard invariant, not a style choice.

### Artifact-only handoff

Spokes exchange **typed file-artifact paths, never transcripts or conversation**. Every
arrow in the data flow is a named file path validated against a schema (see
[references.md](references.md)). This is the connective tissue that keeps each spoke's
context clean and prevents cross-task drift.

### Deterministic two-layer control plane

A deterministic layer of small, single-purpose Python scripts (exit `0`/`1`, no LLM, no
network) makes every safety decision; the LLM layer (`gmj-orchestrator`) dispatches spokes
and calls those scripts via `Bash`. The model never decides whether a gate passed, whether
the retry cap is hit, or whether an artifact is deliverable.

---

## Anti-drift principles

Beyond the committed floor (isolated context per spoke, typed-file handoff, mandatory
gates), three enforceable measures guard against the multi-agent failure modes:

1. **Input budget.** Each spoke declares a bounded maximum input size. Over-budget input is
   a contract violation, not a soft warning — it prevents context bloat from silently
   re-introducing cross-task drift.
2. **No-progress early-stop.** An enhance/retry cycle that makes no measurable gate-metric
   progress stops early rather than burning the full retry cap. This prevents silent
   quality-decay loops.
3. **Artifact-only handoff.** Asserted as an architectural invariant — every hop is a file
   path, never a transcript.

---

## Capabilities

### Dual-mode execution with a retry cap

`execution_mode` is frozen at run start and gates **only** the post-PASS human pause:
`human_in_the_loop` pauses for approval after a gate passes; `autonomous` proceeds
automatically. Retry loops are bounded by a `retry_cap`; cap exhaustion is a hard stop —
never a "ship the last attempt" fallback.

### Parallel fan-out, sequential gates

Independent work — ranking N offers and composing the three artifact types — is dispatched
as parallel `Task` calls in one hub turn (orchestrated fan-out on Claude Code's
single-threaded loop). Gated steps run sequentially per artifact so verdicts never race.

### Bounded-concurrency multi-offer batches

`/gmj-batch` extends the same fan-out idiom across offers, not just artifact types. A batch's
`max_parallel_offers` (default 3, `config/pipeline.config.yaml`) is frozen into the batch
manifest at init — the same freeze-once pattern as `execution_mode`/`retry_cap`. A deterministic
script (`gmj_dispatch_cap.py`) — never the model — decides which offers may dispatch right now;
each offer still runs the unmodified single-offer loop with its own isolated retry-counter slot,
so one offer's gate exhaustion or error is isolated and never stalls or corrupts a sibling
offer's run in the same wave.

### Gap-filling interviewer & preferences capture

`/gmj-interview` runs a gap-filling interviewer that captures missing profile facts and
structured preferences into `config/preferences.yaml` — narrowing and ranking offer search
without ever widening the `config/sources.yaml` allow-list.

### Per-offer batch

`/gmj-batch` takes a multi-select shortlist and runs a per-offer, per-artifact-type gated
batch, recording each `(offer, artifact_type)` run independently in a `batch_manifest` so
Gate A ∧ Gate B never clobber across artifact types.

### Screenshot → branded CV template

`/gmj-template` drives `gmj-template-creator` to turn a screenshot or prototype into a
branded CV HTML template (via Playwright MCP), which the renderer can then use for
pixel-faithful output.

### Artifact depth (default-generated, independently gated)

The collective produces three application artifacts by default per single-offer run, not just
a CV: a **CV**, a **cover letter**, and an **interview-prep** document — each composed from the
same truthful source and each passing both hard gates before delivery independently (a Gate-B
failure on one type never blocks another). An operator narrows the default set via
`--artifact-types=cv,cover_letter`, with an unknown/typo'd type hard-failing before any dispatch.
The CV render additionally always attempts a first-class `.html` sibling alongside the PDF
(guaranteed on the default WeasyPrint/Jinja2 path, gracefully PDF-only with a surfaced warning
otherwise).

### Operator cockpit (`gmj-dashboard`)

`/gmj-dashboard` launches a live, btop-style Textual TUI that **projects** the collective's
on-disk run/batch state as a read-only cockpit by default — brand banner, counters, a live runs
table, domain-metrics panels, a pipeline-DAG strip, drill-in modals, vacancies + batch rollup,
command palette/filter, and a **docs** tab that lists every `docs/*.md` file and opens a wide,
read-only Markdown modal re-read fresh from disk on each open. An explicit `--manage` flag opts
into a mutating action layer (`gmj_dashboard_actions.py`, the sole mutating/launching module)
that can launch real gated runs, edit config, and batch offers — provably unable to write a gate
verdict or force delivery. See [flows.md](flows.md#dashboard) and
[commands.md](commands.md#gmj-dashboard).

### Standalone installer

`bash gmj-core/bin/install.sh` takes a fresh machine to a working install: it clones (or reuses)
the repo, bootstraps a project-local `.venv`, installs every script family's pinned
`requirements.txt` through that venv (never a bare system `pip`), and stages the `gmj-core/`
payload via the vendored, zero-dependency `gmj-core/bin/gmj-tools.cjs` installer. It is
idempotent (safe to re-run) and also supports a fresh-clone/piped install with no existing
checkout on disk. See [installation.md](installation.md).

### Project cleanup proposal

`scripts/gmj_cleanup_report.py` is a read-only, report-only unused-file/folder scanner gated by
the same ownership manifest that scopes the `gmj-` rebrand — it proposes candidates for human
review under `output/analysis/cleanup-report.md` and contains no deletion/rename/move code
path.

### Operator ergonomics

- `/gmj-pipeline-run` drives the whole offer→artifacts pipeline (dual-mode, retry-capped),
  generating the full default artifact set unless narrowed.
- `/gmj-collective` runs the interactive hub.
- The per-step commands under `/gmj-pipeline/` (scout, freeze, compose, verify, evaluate,
  generate) expose each stage individually.
- `/gmj-batch` runs a bounded-concurrency, multi-offer gated batch (see above).
- `/gmj-runs` is a read-only run/batch timeline inspector for auditing what happened.
- `/gmj-dashboard` is the live operator cockpit (read-only by default, opt-in `--manage`).

Run-scoped state and gate-log audit artifacts live under `.pipeline/runs/<run_id>/` (the
`run_id` is sanitized before it becomes a directory name).

---

## Experimental runtime & provider prototypes (additive, non-default)

Two scoped, additive spikes explore running the collective outside the default Claude Code CLI
path. Neither changes `.claude/agents/`, `.claude/commands/`, or `.claude/settings.json`, and
neither is reachable from the default `/gmj-pipeline-run` / `/gmj-batch` / `/gmj-collective`
entry points — both require explicitly invoking their own script/generator.

- **Claude Agent SDK runtime.** `scripts/runtime/gmj_sdk_runner.py` dispatches a single spoke
  through the `claude-agent-sdk` Python SDK instead of the CLI, preserving the `agent_result_v1`
  contract. Labeled experimental/unsupported for autonomous runs until PreToolUse scope-guard and
  SubagentStop envelope-validation parity are independently verified (see
  `scripts/runtime/HOOK-PARITY.md`).
- **Cursor provider adapter.** `gmj-core/bin/gmj-cursor-adapter.cjs` is a pure file-transform
  generator — not a Cursor runtime or execution path — that translates the 9
  `.claude/agents/*.md` files into Cursor's `.cursor/agents/*.md` subagent format. Documented
  known enforcement gaps relative to Claude Code (no confirmed `PreToolUse`-hook parity
  end-to-end, no confirmed Task-nesting-restriction equivalent) are tracked in
  `gmj-core/bin/CURSOR-HOOK-PARITY.md` until closed or verified against a real Cursor session.
