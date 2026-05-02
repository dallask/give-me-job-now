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
| Candidate YAML | `config/candidate.yaml` |
| Raw materials & notes | `sources/` |
| Market briefs | `sources/research/` |
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
- `cv-template-creator` (Playwright MCP: `mcp__playwright__browser_*` in agent tools; `.mcp.json` server `playwright`), `cv-generator`, `cv-reviewer`, `cv-enhancer`, `cv-deliverable-gate`

## Entrypoints

- Slash command: **`/job-collective`** → `.claude/commands/job-collective.md`
- Session hooks: `.claude/settings.json` (bootstrap banner, Bash guardrails, handoff logging)

## Layout

- `config/` — candidate and other YAML configuration.
- `.claude/` — Claude Code settings, agents, hooks, skills, slash commands.
- `example/` — legacy prototype collective (reference only).

Update this file when conventions change.
