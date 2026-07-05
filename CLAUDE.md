# give-me-job

Project context for Claude Code sessions.

## Purpose

This repository is a **hub-and-spoke job/CV collective**: given a real job offer it produces truthful, offer-optimized application artifacts — a CV (PDF), a cover letter, and an interview-prep doc — that provably trace back to the candidate's real profile and pass mandatory truth + target-fit gates. Spokes cover offer discovery, artifact composition, truth verification, fit scoring, and Python PDF rendering.

## Architecture

> **Authoritative source of truth: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).**
> That document defines the hub + 5-spoke roster (`gmj-offer-scout`, `gmj-artifact-composer`,
> `gmj-fit-evaluator`, `gmj-truth-verifier`, `gmj-cv-generator` + retained `gmj-candidate-analyzer`
> / `gmj-candidate-configurator`), per-spoke boundaries, the offer→artifacts data flow, the
> two-layer runtime control loop, and the anti-drift principles. The sections below summarize the
> current collective; when they disagree with `docs/ARCHITECTURE.md`, that document wins.

## Hub-and-spoke rules

1. **`gmj-orchestrator`** (the hub **persona**—see `/gmj-collective`) is the **only** role that calls `Task` to spawn other agents. That persona must run at **top level** in the session (follow `gmj-orchestrator.md` in the main chat). **Do not** `Task`-spawn `gmj-orchestrator` itself: nested hubs do not get `Task` in Claude Code, so spokes cannot run.
2. Routing schema: **User Request → Routing Analysis → Agent Selection → Task Delegation → Quality Gate → Result**.
3. Subagents do **not** call `Task` (no peer-to-peer chaining).

## Paths (source of truth)

| Area | Path |
|------|------|
| Search sources config | `config/sources.yaml` |
| Master candidate YAML | `config/candidate.yaml` |
| Skill-specific CV YAMLs | `config/cv/cv.[skill].[lang].yaml` |
| Language overlays | `config/candidate.ua.yaml`, `config/candidate.ru.yaml` |
| i18n section labels | `config/i18n/labels.yaml` |
| Raw materials & notes | `sources/` |
| Market briefs | `sources/research/[skill]-market-brief.md` |
| CV gap reports | `sources/analysis/cv-[skill]-[lang]-gaps.md` |
| Normalized vacancies | `sources/vacancies/` |
| Analyzer / review artifacts | `sources/analysis/` |
| CV PDFs | `output/cv/` |
| Extract & render CLI | `scripts/cv/gmj_extract.py`, `scripts/cv/gmj_render_cv.py` |
| Optional HTML PDF template | `templates/cv/default.html` (requires WeasyPrint) |

## PDF generation

CV PDFs are produced **only** via Python (`scripts/cv/gmj_render_cv.py`), not by manual binary authoring in chat.

## Agents (`.claude/agents/`)

The current collective is the **hub + 5 spokes + 2 supporting agents + template creator**.
`docs/ARCHITECTURE.md` is the authoritative roster + data-flow source of truth.

- `gmj-orchestrator` — hub; the only role that holds `Task`, routes, runs gates, tracks cycles.
- `gmj-offer-scout` — spoke; discover, normalize, and rank offers within `config/sources.yaml` scope; emit a frozen, hashed `offer_spec`.
- `gmj-artifact-composer` — spoke; from `config/candidate.yaml` + `offer_spec`, compose the CV, cover letter, and interview-prep; owns the gap-report pass and enhance loop.
- `gmj-truth-verifier` — spoke; Gate A (truthfulness, hard block) — re-ground every claim against `config/candidate.yaml`; reframe allowed, invention blocked.
- `gmj-fit-evaluator` — spoke; Gate B (target-fit coverage, hard block) + Gate C (polish, advisory).
- `gmj-cv-generator` — spoke; render approved artifacts to PDF via `scripts/cv/gmj_render_cv.py` (render-only).
- `gmj-candidate-analyzer` — supporting; parse candidate source materials into structured data.
- `gmj-candidate-configurator` — supporting; canonical write/merge into `config/candidate.yaml`.
- `gmj-template-creator` — branded-CV HTML template creator from a screenshot/prototype (Playwright MCP: `mcp__playwright__browser_*`; `.mcp.json` server `playwright`).

> **Historical (superseded).** The earlier 13-agent pipeline (a standalone LLM router, split
> scraper/researcher, split composer/reviewer/enhancer, a standalone deliverable gate, a prose
> translator, and a template creator wired into the old skill-CV loop) has been consolidated into
> the roster above. See `docs/ARCHITECTURE.md` §7 for the legacy→new mapping.

## Entrypoints

- Slash command: **`/gmj-collective`** → `.claude/commands/gmj-collective.md`
- Session hooks: `.claude/settings.json` (bootstrap banner, Bash guardrails, handoff logging)

## CLI entry points & features

The whole flow runs from the CLI (`claude --dangerously-skip-permissions`), dual-mode
(human-in-the-loop default, `autonomous` flag) with a retry-capped gate loop:

- `/gmj-pipeline-run` — whole offer→artifacts pipeline (freeze → compose → Gate A → Gate B/C → render), with parallel scout fan-out and per-artifact sequential gates.
- `/gmj-pipeline/{scout,freeze,compose,verify,evaluate,generate}` — per-step wrappers (thin, no control logic).
- `/gmj-batch` — multi-select shortlist → per-offer gated artifact batch.
- `/gmj-interview` — gap-filling interviewer & preferences capture.
- `/gmj-template` — screenshot → branded-CV template creator.
- `/gmj-runs` — read-only run/batch timeline inspector.

**Artifact depth:** three artifact types — CV, cover letter, interview-prep — each rendered by
Python (`scripts/cv/gmj_render_cv.py`, `gmj_render_cover_letter.py`, `gmj_render_interview_prep.py`).
Run state lives per-run under `.pipeline/runs/<run_id>/` (git-ignored).

## Contracts & schemas (`schemas/`)

Typed JSON envelopes are versioned under `schemas/*.schema.json`: `agent_result_v1`, `offer_spec`,
`artifact_draft`, `gate_result`, `gate_feedback`, `preferences`, `shortlist`, `batch_manifest`.
Every spoke emits an `agent_result_v1`; hops exchange typed file-artifact paths (never transcripts).
The migrated candidate/CV YAML schema and edit rules live in the `gmj-candidate-yaml-schema` skill.

## CV rendering

Full CV: `config/candidate.yaml` → `scripts/cv/gmj_render_cv.py [--lang ua|ru]` → PDF.
The offer-driven pipeline routes an approved `artifact_draft` through the gates before
`gmj-cv-generator` renders it. Skill-specific CV YAMLs (`config/cv/cv.[skill].[lang].yaml`) remain a
supported input to the renderer.

## Search sources config (`config/sources.yaml`)

Controls which job boards and geographies `gmj-offer-scout` is allowed to use:

```yaml
sites:     # allowed job board URLs — agents derive allowed_domains from these
cities:    # geo scope for all searches and salary data
languages: # search query languages and result language preference (ua | ru | en)
```

`gmj-offer-scout` **must** read this file before any `WebSearch` call. Searches outside the listed sites or cities are not permitted. If the file is absent, the scout logs a fallback warning and proceeds unrestricted.

## Skill slug convention

Skill slugs are lowercase, hyphenated: `fpv`, `php-laravel`, `drupal`, `react-frontend`.
The orchestrator normalises the user's free-form role description to a slug before passing it to spokes.

## Rules index (`rules/`)

Load-bearing project invariants live in repo-root `rules/*.md`, one per file, each with a
`scope:` frontmatter block. They are **Read on demand** (not auto-loaded) when a task matches a
rule's scope — see [`rules/README.md`](rules/README.md) for the convention and match table.
`tests/test_rules_scope.py` is the machine gate that keeps this index complete.

- [`rules/truthfulness.md`](rules/truthfulness.md) — never fabricate; `config/candidate.yaml` is the single source of truth.
- [`rules/hub-and-spoke.md`](rules/hub-and-spoke.md) — only the hub holds `Task`; spokes never spawn spokes.
- [`rules/sources-scope.md`](rules/sources-scope.md) — web search stays inside `config/sources.yaml` boards/geos/langs.
- [`rules/gmj-naming.md`](rules/gmj-naming.md) — `gmj-` / `gmj_` naming for app agents, skills, commands, hooks, scripts.
- [`rules/python-render-only.md`](rules/python-render-only.md) — all PDF/document rendering via Python (`gmj_render_cv.py`).
- [`rules/gate-non-bypassability.md`](rules/gate-non-bypassability.md) — hard gates (Gate A/B) are non-bypassable in any mode.

## Layout

- `config/` — canonical candidate YAML, language overlays, i18n labels, pipeline/fit config, `sources.yaml`.
- `config/cv/` — skill-specific CV YAML files (derived, not hand-edited).
- `schemas/` — versioned JSON envelope schemas (the contracts between agents).
- `scripts/` — Python spokes + tooling (`cv/`, `offers/`, `artifacts/`, `contracts/`, `pipeline/`, `preferences/`).
- `.claude/` — Claude Code settings, agents, hooks, skills, slash commands.
- `rules/` — Read-on-demand project invariants (`rules/README.md` indexes them).
- `gmj-core/` — packaged standalone payload + installer (`gmj-core/bin/gmj-tools.cjs`) for clean installs.

Update this file when conventions change.
