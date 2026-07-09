# give-me-job — Architecture

**Status:** Source of truth for the collective's architecture, current through v4.0 (Phase 39).
**Scope of authority:** This is the single authoritative architecture document. The two
`CLAUDE.md` files (`./CLAUDE.md`, `./.claude/CLAUDE.md`) point here rather than duplicating
the roster or the data flow. When those files and this document disagree, **this document
wins** and the CLAUDE.md prose should be treated as legacy pending consolidation.

---

## 1. Purpose & Scope

This document formally defines the **redesigned decomposition** of the give-me-job
collective: the member roster, each spoke's bounded contract and isolation boundary, the
end-to-end data flow of one offer, and the anti-drift principles the design enforces.

It is a *designed deliverable* (requirement ARCH-01): the roster and merges were locked in
`.planning/PROJECT.md`; this document formalizes them, it does not re-litigate them.

**In scope for this document:** the hub + 5-spoke roster, per-spoke input/output contracts,
the offer→render data flow, the anti-drift floor plus three chartered measures beyond it,
and the legacy→new mapping.

**Out of scope (deferred, see §8):** JSON Schemas / hashing / the deterministic routing
engine (Phase 2), each spoke's actual behavior (Phases 3–6), and dual-mode + retry-cap loop
enforcement (Phase 7). Envelope kinds are **forward-referenced in prose only** here — no
schema is defined in this document.

---

## 2. System Overview

The collective is a **hub-and-spoke** system. A single top-level hub
(`gmj-orchestrator`) holds the `Task` tool and delegates to five bounded spokes; spokes
never spawn other spokes (a nested hub loses `Task` in Claude Code). Two retained supporting
agents (`gmj-candidate-analyzer`, `gmj-candidate-configurator`) sit outside the 5-spoke artifact
roster but feed the canonical profile.

Every hop below is a **typed file artifact** identified by its path — never a conversation
transcript. This is the artifact-only handoff invariant (see §6): a spoke receives file
paths and emits file paths, so no spoke inherits another spoke's context.

```
                         config/sources.yaml  (board/geo/lang allow-list)
                                     │  (mandatory read before any web search)
                                     ▼
   offer (URL / pasted text) ──▶  gmj-offer-scout  ──▶  offer_spec  (frozen, hashed)   [Phase 3]
                                                          │        file artifact
                                                          ▼
        config/candidate.yaml  ─────────▶  gmj-artifact-composer  ◀──  offer_spec
            (canonical truth)                     │
                                          artifact_draft  (CV / cover letter / interview-prep)
                                                  │   file artifact
                                                  ▼
                                          gmj-truth-verifier   (Gate A: truthfulness — HARD BLOCK)
                                                  │   gate_result (Gate A)
                                                  │   ── every claim must trace to candidate.yaml
                                          pass ◀──┘   fail ──▶ names offending lines, loop to composer
                                                  ▼
                                          gmj-fit-evaluator    (Gate B: target-fit HARD BLOCK,
                                                  │          Gate C: polish ADVISORY)
                                                  │   gate_result (Gate B/C)
                                          pass ◀──┘   fail ──▶ loop to composer (bounded retry)
                                                  ▼
                                          gmj-cv-generator ──▶ output/cv/*.pdf   (via scripts/cv/gmj_render_cv.py)
```

**Every arrow is a typed file artifact path, not a transcript.** Gate A (truth) must pass
before Gate B/C (fit) runs; truthfulness is never bypassed in any execution mode.

---

## 3. Roster Table

The consolidated collective is **exactly** the nine members below: the hub, the five core
spokes, two retained supporting agents, and the branded-template spoke. This table matches
`.planning/PROJECT.md`'s locked roster.

| Member | Kind | Role (one line) | Disposition | Owning phase |
|--------|------|-----------------|-------------|--------------|
| `gmj-orchestrator` | Hub | Holds `Task`; routes/delegates, runs gates, tracks cycles | Retained (hub) | Phase 2 (routing rewire) |
| `gmj-offer-scout` | Spoke | Find + normalize + rank offers within `sources.yaml` scope; emit a frozen offer-spec | New (merges scraper + researcher) | Phase 3 (Offer Intake) |
| `gmj-artifact-composer` | Spoke | From `candidate.yaml` + offer-spec, produce CV / cover letter / interview-prep; owns the gap-report pass and enhance loop | New (merges composer + enhancer + reviewer gap-role) | Phase 4 (Compose) |
| `gmj-truth-verifier` | Spoke | Re-ground every artifact claim against `candidate.yaml`; hard-block fabrications (Gate A) | New (no legacy equivalent) | Phase 5 (Truth) |
| `gmj-fit-evaluator` | Spoke | Score target-fit (coverage-led hard-block, Gate B) and polish (advisory, Gate C) | New (reviewer scoring-role) | Phase 6 (Fit) |
| `gmj-cv-generator` | Spoke | Render artifact PDF(s) via Python (`gmj_render_cv.py`) | Retained & extended | Phase 8 (E2E) |
| `gmj-candidate-analyzer` | Supporting | Parse candidate source materials; extract structured data | Retained (supporting) | Phase 3.1 (Ingestion) |
| `gmj-candidate-configurator` | Supporting | Canonical write/merge into `config/candidate.yaml` | Retained (supporting) | Phase 3.1 (INGEST-04) |
| `gmj-template-creator` | Spoke | Turn a pasted screenshot into a reusable HTML/Jinja2 CV template under `templates/cv/` via the WeasyPrint visual-diff loop; never calls `Task` | Active (optional / branded-template) | Phase 13 (Template Creation) |

> **Reconciling "exactly."** `.claude/agents/` also contains ~35 `gsd-*.md` files and
> `ai-agents-architect.md`. Those are **unrelated GSD / general tooling, not the job
> collective**. The consolidated collective is precisely the nine members listed above:
> hub + 5 core spokes + 2 retained supporting agents + the branded-template spoke.

---

## 4. Per-Spoke Contracts

Each spoke runs in **isolated context** with a **bounded, narrow structured input**
(GUARD-02). The "Must NEVER receive" line is the explicit isolation boundary; the input
budget is a hard ceiling (over-budget input is a contract violation — see §6). Envelope
kinds are forward-referenced only; their schemas land in Phase 2 under `schemas/`.
Input-budget figures are provisional bounded defaults; each spoke's own phase finalizes them.

### 4.1 gmj-offer-scout
- **Role:** Discover, normalize, and rank job offers within `config/sources.yaml` scope, and
  emit a single frozen, hash-stamped offer-spec.
- **Receives:** an offer URL / pasted text (single-offer intake) **or** a board-search
  request; `config/sources.yaml` (allow-list) — read before any web search.
- **Must NEVER receive:** `config/candidate.yaml` or any candidate PII (gmj-offer-scout is
  offer-side only); another spoke's transcript (paths only); freedom to search outside the
  `sources.yaml` boards / geos / languages.
- **Emits:** `agent_result_v1` with an `offer_spec` artifact (schema: Phase 2).
- **Input budget:** ≤ 64 KB structured input.

### 4.2 gmj-artifact-composer
- **Role:** From canonical `candidate.yaml` + the frozen offer-spec, compose all three
  artifacts (CV, cover letter, interview-prep); owns the gap-report pass and the enhance loop.
- **Receives:** `config/candidate.yaml` (read-only), the frozen `offer_spec` artifact, and
  gate feedback (`gate_result` files) when looping.
- **Must NEVER receive:** raw web/offer-board access (gmj-offer-scout already froze the
  offer-spec); write access to `config/candidate.yaml` (canonical profile is never mutated by
  a pipeline run); another spoke's transcript.
- **Emits:** `agent_result_v1` with an `artifact_draft` artifact per artifact type (schema: Phase 2).
- **Input budget:** ≤ 256 KB structured input (profile + offer-spec + prior gate feedback).

### 4.3 gmj-truth-verifier
- **Role:** Re-ground every claim in each artifact draft against `candidate.yaml`; hard-block
  any fabrication (Gate A). Reframing/emphasis is allowed; invention is blocked.
- **Receives:** an `artifact_draft` artifact and `config/candidate.yaml` (read-only) as the
  ground-truth source.
- **Must NEVER receive:** fit/market/target-fit scoring inputs or `gmj-fit-evaluator` outputs —
  the truth gate is deliberately isolated from the fit gate so the safety-critical check
  stays narrow and un-diluted; any offer-board access; another spoke's transcript.
- **Emits:** `agent_result_v1` with a `gate_result` artifact (Gate A); on failure it names the
  offending lines (schema: Phase 2).
- **Input budget:** ≤ 256 KB structured input (draft + canonical profile).

### 4.4 gmj-fit-evaluator
- **Role:** Score target-fit — must-have coverage is the primary metric (Gate B, hard-block)
  — plus advisory polish (Gate C: clarity, concision, formatting, quantified impact).
- **Receives:** an `artifact_draft` that has already passed Gate A, and the frozen
  `offer_spec` (for must-have coverage / keyword / seniority matching).
- **Must NEVER receive:** `config/candidate.yaml` raw PII beyond what the draft contains, nor
  the truth-gate's internal reasoning — Gate B/C runs only on Gate-A-passed drafts; another
  spoke's transcript.
- **Emits:** `agent_result_v1` with a `gate_result` artifact (Gate B/C); exact
  thresholds/weights are defined in Phase 6 (schema: Phase 2).
- **Input budget:** ≤ 256 KB structured input (draft + offer-spec).

### 4.5 gmj-cv-generator
- **Role:** Render the approved artifact(s) to PDF via Python (`scripts/cv/gmj_render_cv.py`);
  deterministic, no content authoring.
- **Receives:** a gate-passed `artifact_draft` / the CV YAML path to render.
- **Must NEVER receive:** freedom to alter artifact content (render-only — content is fixed
  upstream); another spoke's transcript.
- **Emits:** `agent_result_v1` with an `artifact_draft` / rendered `file` artifact
  (`output/cv/*.pdf`) (schema: Phase 2).
- **Input budget:** ≤ 128 KB structured input (YAML + render options).

---

## 5. Data Flow (narrative)

1. **Intake.** The user supplies an offer URL/text, or requests a board search.
   `gmj-offer-scout` reads `config/sources.yaml` (mandatory) and, staying within its allow-list,
   normalizes and ranks offers, then freezes the chosen one as a hash-stamped `offer_spec`
   file. Downstream spokes all read that same frozen artifact.
2. **Compose.** `gmj-artifact-composer` reads canonical `config/candidate.yaml` plus the
   `offer_spec` and emits `artifact_draft` files (CV, cover letter, interview-prep). It owns
   the gap-report pass and the enhance loop.
3. **Gate A — truth.** `gmj-truth-verifier` reads each `artifact_draft` and `candidate.yaml`,
   re-grounds every claim, and emits a `gate_result`. A fabrication is a hard block: the draft
   loops back to the composer with the offending lines named. Gate A must pass first.
4. **Gate B/C — fit + polish.** `gmj-fit-evaluator` reads the Gate-A-passed draft and the
   `offer_spec`, scores must-have coverage (Gate B hard-block) and polish (Gate C advisory),
   and emits a `gate_result`. A Gate-B failure loops back to the composer (bounded retry).
5. **Render.** A draft that passes both gates reaches `gmj-cv-generator`, which renders it to
   `output/cv/*.pdf` via `gmj_render_cv.py`.

At every hop the exchanged unit is a **named file artifact path**, never a transcript.

---

## 5.1 Runtime Control Loop (Phase 7)

The §5 data flow describes *what* moves between spokes. This section describes *how* the
hub drives it at runtime: a **two-layer control plane**. A *deterministic layer* of small
single-purpose Python scripts (exit 0/1, no LLM, no network) makes every safety decision;
the *LLM layer* — the `gmj-orchestrator` hub, the only `Task` holder — dispatches spokes
and calls those scripts via `Bash` for every control decision. Safety lives entirely in the
deterministic layer: the model never decides whether a gate passed, whether the retry cap is
hit, or whether an artifact is deliverable.

Every run-state path below is written under a resolved pipeline root `<root>`: the
`pipeline-dir=<dir>` prompt arg if present, else the `GMJ_PIPELINE_DIR` environment variable,
else `.pipeline` (the fallback, not the only path — see `/gmj-pipeline-run`'s Parameters
section and `gmj-orchestrator.md`'s `init_run`). The diagram below uses the generic `<root>`
token throughout; substitute the resolved root per the rule above.

```
 CLI: claude --dangerously-skip-permissions  →  /gmj-pipeline-run  (params: mode?, offer, run_id?, artifact-types?)
                                     │
                                     ▼
   0. resolve + derive   gmj_pipeline_run.py --run-id <run_id> --artifact-types <list>
                          validates against the 3-item enum (cv / cover_letter / interview_prep),
                          hard-fails BEFORE any dispatch on an unknown/typo'd type, and derives
                          one run_id per type: <run_id>-cv / <run_id>-cl / <run_id>-ip
                                     │
                                     ▼
   1. init_run   gmj_state_write.py   freeze execution_mode + retry_cap + run_id  ─┐  (once per
                       into <root>/runs/<run_id>-{cv,cl,ip}/state.json — ITS OWN     │   derived id)
   2. loop:                                                                        ▼
      a. gmj_route.py  --state <root>/runs/<run_id>-{cv,cl,ip}/state.json  →  next_step  (pure (state,dag)→step)
      b. gmj_check_offer.py  --file offer-spec.json      (before each dispatch; STALE ⇒ abort)
      c. Task(spoke for next_step)                   (parallel fan-out for 3 artifacts / N offers)
      d. spoke emits a file artifact (draft / gate_result)
      e. GATE node?
           gmj_check_truth.py (Gate A) | gmj_score_fit.py (Gate B)   exit 0/1 — NO bypass flag
           gmj_record_gate.py  → writes gate_result artifact under <root>/runs/<run_id>-{cv,cl,ip}/
                             AND sets state.gate_results[node]
           FAIL ⇒ gmj_record_retry.py --increment
                  gmj_check_cap.py
                    ├ below cap ⇒ gmj_map_feedback.py → {missing_must_haves,
                    │              fabricated_claims, gate} → Task(gmj-artifact-composer) ↺
                    └ at cap    ⇒ HARD STOP report (names failing artifact + reason)
           PASS ⇒ (HITL: pause for human) → route advances
   3. deliver:   gmj_check_delivery.py   (Gate A ∧ Gate B recorded pass?)  else blocked
                  — runs once per derived run_id; reported as a per-type breakdown,
                    never a single collapsed boolean
                                     │
                                     ▼
                output/cv/*.pdf (+ .html sibling, ARTF-02)  (gmj-cv-generator)
```

**Mode gates only the pause, never the gate.** `execution_mode` (frozen at `init_run`) is
consulted at exactly ONE point: the **post-PASS human-pause decision**. In
`human_in_the_loop` the hub pauses for approval after a gate PASS; in `autonomous` it
proceeds automatically. The mode value is **never** passed to `gmj_check_truth.py` /
`gmj_score_fit.py` and never alters the fail path — both gates block identically in both modes.
Autonomous mode removes the *human* pause, never the *machine* gate; truthfulness is never
bypassed.

**Cap exhaustion is a hard stop, never ship-last-attempt.** At `retry_count == retry_cap`,
`gmj_check_cap.py` reports exhaustion and the hub emits a hard-stop report naming the failing
artifact + the last gate's reason. Independently, `gmj_check_delivery.py` refuses to deliver any
artifact lacking a recorded Gate A ∧ Gate B pass — so even a loop bug cannot ship a failed
draft.

**Run-scoped state relocation.** State moves from a single `.pipeline/state.json` to a
per-run **`<root>/runs/<run_id>/state.json`** (`<root>` resolved as above — `.pipeline` is the
illustrative default, not the only path), which holds the resumable run state
(`current_step`, `completed_steps`, `gate_results`, `offer_spec_path`, `offer_spec_hash`,
`retry_counts`, plus the Phase-7 frozen keys `execution_mode`, `retry_cap`, `run_id`)
alongside the logged `gate_result` audit artifacts (`gate_<node>_<type>_<attempt>.json`).
`gmj_route.py` reads that file, so resume is a pure `(state, dag) → next_step` replay: passing an
existing `run_id` resumes; a single step runs exactly the one node `gmj_route.py` returns.
`run_id` is sanitized to a safe charset before it becomes a directory name (no path
traversal), and `<root>/runs/<run_id>/` is git-ignored (per-run state + gate logs stay local),
where `<root>` defaults to `.pipeline` but is configurable via `pipeline-dir`/`GMJ_PIPELINE_DIR`.

**Per-artifact-type state isolation (Phase 32, ARTF-01/04).** A single-offer run produces
the full default artifact set (CV, cover letter, interview-prep) by default; each requested
type gets its own `<root>/runs/<run_id>-{cv,cl,ip}/state.json`, derived and validated by
`scripts/pipeline/gmj_pipeline_run.py` (mirroring `gmj_batch.py`'s per-(offer, artifact_type)
run_id pattern) — never one shared file, because `gate_results` is keyed flatly by DAG node
name with no artifact-type dimension (`gmj_record_gate.py`), and a shared file would let a
later type's gate write clobber an earlier type's recorded verdict. `gmj_check_delivery.py`
runs once per derived run_id, and delivery is reported as an explicit per-type breakdown,
never a single collapsed boolean. An operator narrows the default set via
`--artifact-types=cv,cover_letter`, with an unknown/typo'd type hard-failing before any
dispatch. The CV render additionally always attempts a first-class `.html` sibling
(guaranteed on the default WeasyPrint/Jinja2 path, gracefully PDF-only with a surfaced
warning otherwise, ARTF-02).

### Parallel fan-out, sequential gates

Independent work is dispatched as **parallel `Task` calls in a single hub turn** — ranking
**N offers**, and composing the **3 artifact types** (CV / cover letter / interview-prep),
each with its own output path and its own isolated `retry_counts[offer][type]` slot.
Gated/dependent steps (compose → Gate A → Gate B → deliver) run **sequentially per
artifact**. This is orchestrated task fan-out on Claude Code's single-threaded event loop —
not OS threads.

The CLI entry points for this loop are `.claude/commands/gmj-pipeline-run.md` (whole flow) and
`.claude/commands/gmj-pipeline/{scout,freeze,compose,verify,evaluate,generate}.md` (per step);
each per-step command is a thin wrapper naming the exact script/Task above, with no control
logic duplicated.

### Bounded concurrent-offer dispatch (Phase 35, CONC-01..06)

`/gmj-batch` extends the same fan-out idiom across **offers**, not just artifact types. A batch's
`max_parallel_offers` (default 3, `config/pipeline.config.yaml`) is frozen into the batch manifest
at `gmj_batch.py init` — the same freeze-once pattern as `execution_mode`/`retry_cap`. The
deterministic decision of *which offers may dispatch right now* belongs entirely to
`scripts/pipeline/gmj_dispatch_cap.py` (never the model): given the manifest, each offer's 3
per-(offer, artifact_type) run states, and the frozen cap, it classifies every offer as
TERMINAL / FRESH / ACTIVE and returns the dispatchable run_ids plus free capacity. The hub loop is
**ask cap script → dispatch up to that many offers' next steps as parallel `Task` calls in one hub
turn → mark each terminal completion (`gmj_batch.py mark`, concurrent-safe `batch_manifest.json`
writes) → immediately re-ask the cap script (greedy refill)** — repeated until every offer's 3 runs
reach a terminal status. Each offer still runs the unmodified single-offer loop above, per
artifact type, with its own isolated `retry_counts[offer][type]` slot; Gate A/Gate B remain
non-bypassable per-offer-per-type, so concurrency introduces no shared/aggregate gate shortcut.
One offer's pipeline failure (gate exhaustion, error) is isolated — it never stalls or corrupts a
sibling offer's run in the same wave. Concurrency is implemented purely as multiple `Task` calls
issued in one hub turn, **never** as a per-offer nested sub-orchestrator, which would violate the
hub-and-spoke single-`Task`-holder invariant (§2, §6).

---

## 5.2 Experimental Runtime & Provider Prototypes (Phases 38–39, additive-only)

Two Phase-38/39 spikes explored running this collective outside the default Claude Code CLI path.
Both are **additive, experimental prototypes that sit alongside — and never replace — the working
Claude Code CLI path** described in §5/§5.1; neither changes any file under `.claude/agents/`,
`.claude/commands/`, or `.claude/settings.json`, confirmed by direct `git log`/`git status`/grep
checks against those paths across both phases.

- **Claude Agent SDK runtime (SDK-01..03).** `scripts/runtime/gmj_sdk_runner.py` is a scoped,
  isolated prototype (own directory, own `requirements.txt`) that dispatches a single spoke through
  the `claude-agent-sdk` Python SDK instead of the CLI, preserving the `agent_result_v1` contract.
  It ships with an explicit hook-parity checklist (`scripts/runtime/HOOK-PARITY.md`) and is labeled
  experimental/unsupported for autonomous runs until PreToolUse scope-guard and SubagentStop
  envelope-validation parity are independently verified.
- **Cursor provider adapter (PROVIDER-01..03).** `gmj-core/bin/gmj-cursor-adapter.cjs` is a pure
  file-transform generator — not a Cursor runtime, not a pipeline execution path — that translates
  the 9 `.claude/agents/*.md` files into Cursor's `.cursor/agents/*.md` subagent format. It is
  documented (`gmj-core/bin/CURSOR-HOOK-PARITY.md`) with known enforcement gaps relative to Claude
  Code: no confirmed PreToolUse-hook parity end-to-end, and no confirmed equivalent to the
  Task-nesting restriction — both explicitly labeled experimental until closed or independently
  verified against a real Cursor session.

Neither prototype introduces a new roster member (§3) or alters the §5 data flow; both are
reachable only by explicitly invoking their own script/generator, never by the default
`/gmj-pipeline-run` / `/gmj-batch` / `/gmj-collective` entry points.

---

## 6. Anti-Drift Principles

### Committed floor (from PROJECT.md)
- **Isolated context per spoke** — narrow structured input in, structured result out; the
  hub passes artifacts (files), not transcripts.
- **Typed-file / JSON handoff** — strict `agent_result_v1` output contracts between all agents.
- **Mandatory gates** — nothing reaches "delivered" without passing Gate A (truth) + Gate B
  (target-fit).

### Chartered measures beyond the floor (GUARD-05)
This anti-drift phase is chartered to discover and add further measures. Three are recorded
here as enforceable principles (the floor is a floor, not a ceiling):

1. **Input budget** — each spoke declares a bounded maximum input size (see §4). Over-budget
   input is a **contract violation**, not a soft warning; it prevents context bloat from
   silently re-introducing cross-task drift.
2. **No-progress early-stop** — an enhance/retry cycle that makes **no measurable
   gate-metric progress** across a cycle stops early rather than burning the full retry cap.
   This prevents silent quality-decay loops and wasted cycles.
3. **Artifact-only handoff** — spokes exchange **typed file artifact paths, never transcripts
   or conversation**. Asserted as an architectural invariant (visualized by every arrow in §2
   being a file path). This is the connective tissue that keeps each spoke's context clean.

---

## 7. Legacy → New Mapping (superseded — historical)

The redesign consolidates the legacy 13-file collective in place. Superseded legacy spoke
files are **moved to `example/`** (reference / prior-art), not hard-deleted — reversible and
history-preserving. See `example/` for the moved prior-art files.

| Legacy agent(s) | New home | Disposition |
|-----------------|----------|-------------|
| `vacancy-scraper` + `job-market-researcher` | `gmj-offer-scout` | Merged (find + normalize + rank) |
| `cv-composer` + `cv-enhancer` + `cv-reviewer` (gap-report role) | `gmj-artifact-composer` | Merged (compose + enhance loop) |
| `cv-reviewer` (scoring role) | `gmj-fit-evaluator` | Split out (scoring only) |
| — (no legacy equivalent) | `gmj-truth-verifier` | New spoke |
| `gmj-cv-generator` | `gmj-cv-generator` | Retained & extended |
| `gmj-orchestrator` | `gmj-orchestrator` | Retained (hub) |
| `gmj-candidate-analyzer` | `gmj-candidate-analyzer` | Retained (supporting) |
| `gmj-candidate-configurator` | `gmj-candidate-configurator` | Retained (supporting) |
| `vacancy-router` | — → `example/` | Retired (Phase 2 replaces LLM routing with a deterministic state-machine) |
| `cv-deliverable-gate` | — → `example/` | Retired (concept folds into Gate A/B/C stages, Phases 6/7) |
| `candidate-translator` | — → `example/` | Retired (single target language per offer in v1) |
| `cv-template-creator` | `gmj-template-creator` (re-added) | Superseded "retired" — template creation returned as an active optional spoke (Phase 13) |

> **Note:** §7's earlier "retired" disposition for template creation was **superseded** when
> the branded-template flow returned as the active `gmj-template-creator` spoke (Phase 13, with
> the `/gmj-template` command and template scripts). The row above reflects the current active home.

---

## 8. Deferred / Out-of-Scope

| Deferred item | Owning phase |
|---------------|--------------|
| Versioned JSON Schemas for envelope kinds (`offer_spec`, `artifact_draft`, `gate_result`) under `schemas/`, plus hashing | Phase 2 (ARCH-03..05, GUARD-01) |
| Deterministic routing engine (state-machine over `state.json`) replacing LLM routing | Phase 2 (ARCH-06) |
| Per-spoke behavior implementations (offer intake, compose, truth, fit) | Phases 3, 3.1, 4, 5, 6 |
| Exact fit thresholds/weights | Phase 6 (Fit) |
| Dual-mode execution (interactive default + autonomous flag) + retry-cap loop enforcement | Phase 7 — **landed**; runtime loop documented in §5.1 |

Envelope kinds above are forward-referenced in prose only; no schema is defined in this
document.
