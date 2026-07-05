# Agents — the give-me-job roster

> **Authoritative roster source of truth: [docs/ARCHITECTURE.md](ARCHITECTURE.md) §3–4.**
> This section is a reader-facing mirror of that contract. Every agent named here resolves to a
> real `.claude/agents/gmj-*.md` file on disk, and `python3 tests/test_docs_current.py`
> (`test_every_docs_agent_exists`) fails the build if any token drifts. When the two disagree,
> ARCHITECTURE.md wins and this file is corrected toward it.

The collective is a **hub-and-spoke** topology: one top-level orchestrator holds the `Task`
tool and delegates to spokes; spokes never spawn spokes (nested hubs lose `Task` in Claude
Code). See [rules.md](rules.md) for the load-bearing invariants and [flows.md](flows.md) for how
these agents chain across an end-to-end run. Command entry points that drive them are cataloged
in [commands.md](commands.md).

## Roster (9 agents)

The collective is **exactly** these nine members: the hub, five core spokes, two retained
supporting agents, and the branded-template spoke. (`.claude/agents/` also holds ~35 unrelated
`gsd-*` and general-tooling agents — those are not part of the job collective.)

| Member | Kind | Role (one line) | Disposition |
|--------|------|-----------------|-------------|
| `gmj-orchestrator` | Hub | Holds `Task`; routes/delegates, runs quality gates, tracks cycles | Retained (hub) |
| `gmj-offer-scout` | Spoke | Find + normalize + rank offers within `config/sources.yaml` scope; emit a frozen offer-spec | Core spoke |
| `gmj-artifact-composer` | Spoke | From `candidate.yaml` + offer-spec, compose CV / cover letter / interview-prep; owns the bounded enhance loop | Core spoke |
| `gmj-truth-verifier` | Spoke | Re-ground every artifact claim against `candidate.yaml`; hard-block fabrications (Gate A) | Core spoke |
| `gmj-fit-evaluator` | Spoke | Score target-fit (coverage-led hard-block, Gate B) and polish (advisory, Gate C) | Core spoke |
| `gmj-cv-generator` | Spoke | Render artifact PDF(s) via Python (`gmj_render_cv.py`) | Retained & extended |
| `gmj-candidate-analyzer` | Supporting | Parse candidate source materials; propose machine-mergeable findings | Retained (supporting) |
| `gmj-candidate-configurator` | Supporting | Canonical write/merge into `config/candidate.yaml` | Retained (supporting) |
| `gmj-template-creator` | Spoke | Turn a pasted screenshot into a reusable HTML/Jinja2 CV template via the WeasyPrint visual-diff loop | Active (optional / branded-template) |

## Per-agent contracts

Each block below is mined from the agent's own `.claude/agents/gmj-*.md` frontmatter and its
ARCHITECTURE.md §4 contract. The **Must NEVER receive** line is the explicit context-isolation
boundary — a spoke's narrow structured input is a hard ceiling, not a suggestion.

### gmj-orchestrator

- **Role:** Hub of the collective — the only role that holds `Task`. Runs the routing schema
  *User Request → Routing Analysis → Agent Selection → Task Delegation → Quality Gate → Result*,
  delegates to spokes, enforces the gates, and tracks retry cycles.
- **Receives:** the user goal and, across a run, each spoke's `agent_result_v1` envelope (paths,
  not raw transcripts).
- **Must NEVER receive:** a nested `Task` context — the hub must run at top level (a
  Task-nested orchestrator cannot spawn spokes). See [rules.md](rules.md#hub-and-spoke).
- **Emits:** routing decisions, gate verdicts, and the final assembled result.
- **Tools:** `Task, Read, Glob, LS, Bash`.

### gmj-offer-scout

- **Role:** Discover, normalize, and rank job offers within `config/sources.yaml` scope, then
  hand a fielded draft to `gmj_freeze_offer.py` and emit an `offer_spec` envelope pointing at
  the frozen file.
- **Receives:** an offer URL / pasted text (single-offer intake) **or** a board-search request;
  `config/sources.yaml` (the allow-list) — read before any web search.
- **Must NEVER receive:** `config/candidate.yaml` or any candidate PII (offer-side only);
  freedom to search outside the `sources.yaml` boards / geos / languages. See
  [rules.md](rules.md#sources-scope).
- **Emits:** `agent_result_v1` with an `offer_spec` artifact.
- **Tools:** `WebSearch, WebFetch, Read, Write, Glob, LS`.

### gmj-artifact-composer

- **Role:** From canonical `candidate.yaml` + the frozen offer-spec, compose all three artifact
  types (CV, cover letter, interview-prep); owns the gap-report pass and the bounded enhance
  loop.
- **Receives:** `config/candidate.yaml` (read-only), the frozen `offer_spec`, and gate feedback
  (`gate_result` files) when looping.
- **Must NEVER receive:** raw web/offer-board access (the offer-spec is already frozen); write
  access to `config/candidate.yaml` (the canonical profile is never mutated by a run).
- **Emits:** `agent_result_v1` with an `artifact_draft` artifact per artifact type.
- **Tools:** `Read, Write, Edit, Glob, Grep`.

### gmj-truth-verifier

- **Role:** Gate A — re-ground every claim in each artifact draft against `config/candidate.yaml`
  and hard-block any fabrication. Reframing/emphasis is allowed; invention is blocked.
- **Receives:** an `artifact_draft` artifact and `config/candidate.yaml` (read-only) as the
  ground-truth source.
- **Must NEVER receive:** fit/market/target-fit scoring inputs or `gmj-fit-evaluator` outputs —
  the truth gate stays isolated from the fit gate so the safety-critical check stays narrow.
- **Emits:** `agent_result_v1` with a Gate A `gate_result` artifact; on failure it names the
  offending lines. See [rules.md](rules.md#truthfulness).
- **Tools:** `Read, Glob, Grep`.

### gmj-fit-evaluator

- **Role:** Score an artifact draft against the frozen `offer_spec` — must-have coverage first
  (Gate B, hard-block), then advisory polish (Gate C: clarity, concision, formatting, quantified
  impact). Read-only, recommendations only.
- **Receives:** an `artifact_draft` that has already passed Gate A, and the frozen `offer_spec`.
- **Must NEVER receive:** raw `config/candidate.yaml` PII beyond what the draft contains, nor the
  truth gate's internal reasoning — Gate B/C runs only on Gate-A-passed drafts.
- **Emits:** `agent_result_v1` with a Gate B/C `gate_result` artifact.
- **Tools:** `Read, Glob, Grep`.

### gmj-cv-generator

- **Role:** Render the approved artifact(s) to PDF via Python (`scripts/cv/gmj_render_cv.py`);
  deterministic, no content authoring. Uses an optional Jinja HTML template with WeasyPrint if
  installed, otherwise the ReportLab built-in layout.
- **Receives:** a gate-passed `artifact_draft` / the CV YAML path to render.
- **Must NEVER receive:** freedom to alter artifact content — rendering is render-only; content
  is fixed upstream. See [rules.md](rules.md#python-render-only).
- **Emits:** `agent_result_v1` with a rendered `file` artifact (`output/cv/*.pdf`).
- **Tools:** `Read, Bash, Glob, LS`.

### gmj-candidate-analyzer

- **Role:** Ingest candidate materials from `sources/candidate/` (pdf, docx, txt, images, and
  authorized credential URLs), routing each by type. Proposes machine-mergeable findings plus a
  coverage manifest for the configurator.
- **Receives:** files under `sources/candidate/` and authorized credential URLs.
- **Must NEVER receive:** write access to the master YAML — it proposes findings but never
  writes `config/candidate.yaml`.
- **Emits:** structured findings + a coverage manifest for `gmj-candidate-configurator`.
- **Tools:** `Read, Bash, Glob, Grep, WebFetch`.

### gmj-candidate-configurator

- **Role:** Canonical writer/merger of `config/candidate.yaml` from structured analyzer output or
  user instructions. Preserves schema and existing strengths unless asked to replace.
- **Receives:** the analyzer's structured findings, or direct user edit instructions.
- **Must NEVER receive:** a mandate to invent content — merges only what the analyzer or user
  supplies, preserving the existing profile.
- **Emits:** an updated `config/candidate.yaml` (the single source of truth for every artifact).
- **Tools:** `Read, Write, Edit, Glob, Bash`.

### gmj-template-creator

- **Role:** From a pasted CV design screenshot, generate a reusable HTML/Jinja2 template under
  `templates/cv/` that binds `candidate.*` fields, matched to the design via the WeasyPrint
  compare-then-ship visual-diff loop. Injects the `@font-face` DejaVu rule for Cyrillic.
- **Receives:** a pasted design screenshot and the candidate schema field names.
- **Must NEVER receive:** the `Task` tool — it is a spoke and never calls `Task`.
- **Emits:** a reusable HTML/Jinja2 template under `templates/cv/` for `gmj-cv-generator` to
  render against.
- **Tools:** `Read, Bash, Glob, LS, Write`.

## See also

- [ARCHITECTURE.md](ARCHITECTURE.md) — the authoritative roster + per-spoke contracts.
- [rules.md](rules.md) — the load-bearing invariants (hub-and-spoke, truthfulness, gate
  non-bypassability, sources scope).
- [flows.md](flows.md) — how these agents chain across an end-to-end pipeline run.
- [commands.md](commands.md) — the command entry points that drive the collective.
