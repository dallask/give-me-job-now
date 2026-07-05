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

### Artifact depth

The collective produces three application artifacts, not just a CV: a **CV** (PDF), a
**cover letter** (PDF), and an **interview-prep** document — each composed from the same
truthful source and each passing both hard gates before delivery.

### Operator ergonomics

- `/gmj-pipeline-run` drives the whole offer→artifacts pipeline (dual-mode, retry-capped).
- `/gmj-collective` runs the interactive hub.
- The per-step commands under `/gmj-pipeline/` (scout, freeze, compose, verify, evaluate,
  generate) expose each stage individually.
- `/gmj-runs` is a read-only run/batch timeline inspector for auditing what happened.

Run-scoped state and gate-log audit artifacts live under `.pipeline/runs/<run_id>/` (the
`run_id` is sanitized before it becomes a directory name).
