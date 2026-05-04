# give-me-job

Project context for Claude Code sessions.

## Purpose

This repository supports a **hub-and-spoke job/CV collective**: vacancy research, candidate document analysis, YAML configuration, PDF CV generation (Python), CV review vs job requirements, and enhancement loops.

## Hub-and-spoke rules

1. **`vacancy-orchestrator`** (the hub **persona**—see `/job-collective`) is the **only** role that calls `Task` to spawn other agents. That persona must run at **top level** in the session (follow `vacancy-orchestrator.md` in the main chat). **Do not** `Task`-spawn `vacancy-orchestrator` itself: nested hubs do not get `Task` in Claude Code, so spokes cannot run.
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
| Extract & render CLI | `scripts/cv/extract.py`, `scripts/cv/render_cv.py` |
| Optional HTML PDF template | `templates/cv/default.html` (requires WeasyPrint) |

## PDF generation

CV PDFs are produced **only** via Python (`scripts/cv/render_cv.py`), not by manual binary authoring in chat.

## Agents (`.claude/agents/`)

- `vacancy-orchestrator`, `vacancy-router`
- `job-market-researcher`, `vacancy-scraper`, `candidate-analyzer`, `candidate-configurator`
- `candidate-translator` — translates prose fields to `ua`/`ru`, writes `config/candidate.{lang}.yaml` overlays
- `cv-composer` — reads `candidate.yaml`, extracts skill-relevant content, identifies gaps, writes `config/cv/cv.[skill].[lang].yaml`
- `cv-template-creator` (Playwright MCP: `mcp__playwright__browser_*` in agent tools; `.mcp.json` server `playwright`), `cv-generator`, `cv-reviewer`, `cv-enhancer`, `cv-deliverable-gate`

## Entrypoints

- Slash command: **`/job-collective`** → `.claude/commands/job-collective.md`
- Session hooks: `.claude/settings.json` (bootstrap banner, Bash guardrails, handoff logging)

## CV generation pipelines

**Simple pipeline** — full CV, no skill filter:
`candidate.yaml` → `render_cv.py [--lang ua|ru]` → PDF

**Skill-specific pipeline** — targeted CV for a role:
`candidate.yaml` → `cv-composer` → `config/cv/cv.[skill].[lang].yaml` → `render_cv.py` → PDF → review/enhance loop

The skill-specific pipeline is triggered by goals like "generate CV for [role] in [language]". The orchestrator handles market research, gap approval, and the review-enhance loop automatically.

## Search sources config (`config/sources.yaml`)

Controls which job boards and geographies `job-market-researcher` and `vacancy-scraper` are allowed to use:

```yaml
sites:     # allowed job board URLs — agents derive allowed_domains from these
cities:    # geo scope for all searches and salary data
languages: # search query languages and result language preference (ua | ru | en)
```

Both agents **must** read this file before any `WebSearch` call. Searches outside the listed sites or cities are not permitted. If the file is absent, agents log a fallback warning and proceed unrestricted.

## Skill slug convention

Skill slugs are lowercase, hyphenated: `fpv`, `php-laravel`, `drupal`, `react-frontend`.
The orchestrator normalises the user's free-form role description to a slug before passing it to spokes.

## Layout

- `config/` — candidate YAML, language overlays, i18n labels.
- `config/cv/` — skill-specific CV YAML files (derived, not hand-edited).
- `.claude/` — Claude Code settings, agents, hooks, skills, slash commands.
- `example/` — legacy prototype collective (reference only).

Update this file when conventions change.
