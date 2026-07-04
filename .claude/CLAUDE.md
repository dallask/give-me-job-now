<!-- GSD:project-start source:PROJECT.md -->

## Project

**give-me-job — Autonomous Job/CV Collective**

A hub-and-spoke collective of specialized Claude Code agents, commands, skills, and
scripts that autonomously finds fitting job offers and produces truthful,
offer-optimized application artifacts — a CV (PDF), a cover letter, and an interview-prep
document — for one candidate. It is a CLI-driven redesign of this repo's existing
collective, hardened against the classic multi-agent failure modes (fabricated facts,
off-target drift, context bloat, silent quality decay) and operable both fully
autonomously and human-in-the-loop, with the composable flexibility of `open-gsd/gsd-core`.

**Core Value:** Given a real job offer, the system produces a **truthful, offer-optimized** set of
application artifacts that provably trace back to the candidate's real profile and pass
mandatory quality gates. If everything else fails, the artifacts must never fabricate and
must actually target the offer.

### Constraints

- **Tech stack**: Python for all PDF/document rendering (`gmj_render_cv.py`) — no manual binary/PDF authoring in chat. Keeps rendering deterministic and reproducible.
- **Architecture**: Hub-and-spoke only. One top-level orchestrator holds `Task`; spokes never spawn spokes (nested hubs lose `Task`). Preserves criteria/cycle tracking and prevents chain drift.
- **Truthfulness**: `config/candidate.yaml` is the single source of truth; every artifact claim must trace to it. Reframing/emphasis allowed; invention hard-blocked.
- **Search scope**: `gmj-offer-scout` may never search outside the boards/geos/languages declared in `config/sources.yaml`; the mandatory `sources.yaml` read stays enforced.
- **Runtime**: Runs inside Claude Code via `claude --dangerously-skip-permissions`; single-threaded event loop (parallelism is orchestrated task fan-out, not OS threads).
- **Safety**: Hard gates (truth, target-fit) are non-bypassable in any mode; autonomous mode removes the human pause, never the machine gate. Auto-loops are bounded by a retry cap.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3 - CV generation, PDF rendering, document extraction (`scripts/cv/gmj_render_cv.py`, `scripts/cv/gmj_extract.py`)
- YAML - Configuration and data storage (`config/candidate.yaml`, `config/sources.yaml`, skill-specific CV YAML)
- Shell (Bash) - Hooks and session management (`.claude/hooks/`)
- JavaScript/Node.js - Package management and MCP (`.claude/package.json`, `.mcp.json`)

## Runtime

- Python 3.x - for CV generation and document processing pipelines
- `pip` - Python dependency management
- Lockfile: Not present (requirements.txt used instead)

## Frameworks

- ReportLab 4.0.0+ - Built-in CV layout engine, PDF generation from programmatic drawing
- Jinja2 3.1.0+ - HTML template rendering for CV composition
- WeasyPrint (optional) - HTML-to-PDF conversion for styled CV templates
- PyYAML 6.0+ - YAML parsing for candidate profiles and configuration
- python-docx 1.1.0+ - DOCX document extraction
- openpyxl 3.1.0+ - Excel spreadsheet extraction
- pypdf 4.0.0+ - PDF text extraction and analysis
- Pillow 10.0.0+ - Image metadata extraction and processing
- Playwright MCP (@playwright/mcp) - Registered in `.mcp.json` for pixel-perfect CV template testing and screenshots
- None detected
- Bash scripting via `.claude/hooks/` for session lifecycle and pre-tool checks

## Key Dependencies

- PyYAML - Mandatory for candidate profile parsing; all CV pipelines depend on YAML configs (`config/candidate.yaml`, language overlays)
- ReportLab - Core PDF rendering engine for built-in CV template (ReportLab-only mode)
- Jinja2 - Required for HTML CV template rendering before WeasyPrint
- python-docx, openpyxl, pypdf, Pillow - Support document extraction tools; not required for core CV generation but enable `scripts/cv/gmj_extract.py` to ingest candidate source files (Word, Excel, PDF)

## Configuration

- No `.env` file in repository (configuration is YAML-based and checked in)
- Path-based configuration: agent tools reference `config/sources.yaml` for job board allowlist and search geo/lang limits
- `.mcp.json` - MCP server configuration for Playwright browser automation
- `requirements.txt` at `scripts/cv/requirements.txt` - Pinned dependency versions for CV generation pipeline
- `.claude/package.json` - Minimal Node.js config for MCP (no npm packages installed, only MCP server declaration)

## Platform Requirements

- Python 3.x with pip
- Bash shell (for hooks and scripts)
- Node.js + npx (for Playwright MCP server)
- Optional: Fonts at `/usr/share/fonts/truetype/dejavu/` or bundled in `scripts/cv/fonts/` for Cyrillic (DejaVu Sans for ua/ru CV rendering)
- Optional: WeasyPrint system dependencies (if rendering HTML templates via WeasyPrint; requires GObject and CSS support libraries)
- No production deployment detected
- CV PDFs generated locally and stored in `output/cv/`
- Agents run within Claude Code environment (no external API server required)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Python scripts: `snake_case.py` (e.g., `gmj_render_cv.py`, `gmj_extract.py`)
- Agent definitions: `kebab-case.md` (e.g., `gmj-candidate-analyzer.md`, `gmj-cv-generator.md`)
- YAML configuration: `kebab-case.yaml` or `name.[lang].yaml` (e.g., `candidate.yaml`, `candidate.ua.yaml`)
- Markdown documentation: `UPPERCASE.md` (e.g., `CLAUDE.md`, `README.md`) or `lowercase.md` for agent/skill docs
- Python: snake_case (e.g., `extract_pdf()`, `load_candidate()`, `photo_path_for()`)
- Private functions: leading underscore `_function_name()` (e.g., `_register_unicode_font()`, `_load_labels()`)
- Entry point: `main()` as CLI entry point
- snake_case for all variables and parameters (e.g., `config_path`, `out_path`, `candidate`, `font_regular`)
- Constants: UPPERCASE_WITH_UNDERSCORES (e.g., `LANGS`, `DEFAULT_LANG`)
- Temporal/shorthand: single letters acceptable in limited scope (e.g., `k`, `v` in dict iteration; `p` for Path in walks)
- PascalCase for class names (if any exist; not prominent in codebase)
- Python type hints use modern syntax: `dict`, `list`, `str`, `Path`, `tuple[str, str]` (leverages `from __future__ import annotations`)

## Code Style

- No automated formatter (no Prettier, Black, or autopep8 config present)
- Indentation: 4 spaces (Python standard)
- Line length: appears to follow default conventions (~120–150 char target based on existing code)
- Docstrings: module-level required; function-level for public functions only
- No `.eslintrc`, `.flake8`, or `pyproject.toml` with lint config present
- Code follows standard Python conventions implicitly
- Type hints used throughout but no mypy config enforced

## Import Organization

- No path aliases detected (imports use absolute paths from repo root or standard library)
- Relative imports rare; project uses repo-root-relative paths for file operations (e.g., `config_path`, `repo_root_from_config()`)

## Error Handling

- `try`/`except` blocks for optional dependencies (e.g., `ImportError` when WeasyPrint unavailable falls back to ReportLab)
- Type validation with `isinstance()` checks (e.g., `if isinstance(contact, dict)`)
- Path validation with `.is_file()`, `.is_absolute()` before operations
- Graceful degradation: missing overlays, fonts, templates skip without crashing
- Exit codes: `return 0` on success, `return 1` on error
- stderr output: `print(..., file=sys.stderr)` for error messages
- `gmj_extract.py` catches `OSError` for unreadable files, returns fallback "binary" type
- `gmj_render_cv.py` validates YAML structure (`isinstance(base, dict)`) before processing
- Font registration walks multiple directories; uses fallback "Helvetica" if DejaVu unavailable

## Logging

- Quiet by default (no debug logging; progress printed to stdout only when needed)
- Errors print to stderr with context (e.g., "Template not found: {path}")
- JSON output via `--json` flag (e.g., `gmj_extract.py --json` outputs structured results)
- Agent output contract (`agent_result_v1`) used for agent status reporting

## Comments

- Module-level docstrings required for all scripts
- Function docstrings for public/complex functions (e.g., `_register_unicode_font()` explains return value)
- Inline comments for non-obvious logic or config values (e.g., "strip timestamp → ...")
- Avoid redundant comments; code should be self-documenting
- Not used (Python project; no TypeScript)
- Docstrings follow basic Python convention (one-liner + optional expansion)

## Function Design

- Most functions 10–50 lines (e.g., `load_candidate()`, `photo_path_for()`)
- Larger functions break down stages (e.g., `render_reportlab()` ~210 lines but organized by section: header, summary, contact, skills, experience, etc.)
- Use explicit named parameters; keyword-only arguments marked with `*` (e.g., `render_reportlab(candidate, out_path, *, repo_root, labels)`)
- Prefer optional arguments via `or` defaults (e.g., `candidate.get("name") or "Candidate"`)
- Type hints on all parameters and return types
- Single return per function or clearly documented multiple returns (tuple syntax e.g., `tuple[str, str]`)
- None for void operations (e.g., `_prune_old_outputs()` → None)
- Nullable returns typed explicitly (e.g., `Path | None`)

## Module Design

- No `__all__` declarations (Python scripts are not libraries; all functions assumed public)
- Main entry point: `if __name__ == "__main__": raise SystemExit(main())`
- Utility functions sorted by dependency order (helpers before public callers)
- Not used (no index files or aggregating imports)

## YAML Configuration Conventions

- Root keys use snake_case (e.g., `technical_expertise`, `professional_experience`, `key_achievements`)
- Nested objects are dictionaries; collections are lists
- Comments use `# ` prefix on same line or above
- Overlay files: `config/candidate.[lang].yaml` (e.g., `candidate.ua.yaml`, `candidate.ru.yaml`)
- Deep merge: overlay keys override base, preserving unspecified base values
- Naming: overlay keys match base schema exactly (snake_case)

## Agent Output Contract

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

> **Authoritative source of truth: [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).**
> That document defines the redesigned hub + 5-spoke roster (`gmj-offer-scout`,
> `gmj-artifact-composer`, `gmj-fit-evaluator`, `gmj-truth-verifier`, `gmj-cv-generator` + retained
> `gmj-candidate-analyzer` / `gmj-candidate-configurator`), per-spoke boundaries, the offer→render
> data flow, and the anti-drift principles. The inline architecture prose below describes
> the **superseded legacy 13-agent pipeline** — retained for reference only while the
> collective is consolidated in Phase 1. Do not treat the roster below as current.

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **gmj-orchestrator** | Hub: routing, task delegation, quality gates, cycle tracking | `.claude/agents/gmj-orchestrator.md` |
| **vacancy-router** | Route user goal to appropriate spoke; emit ROUTING_DECISION | `.claude/agents/vacancy-router.md` |
| **job-market-researcher** | Web search for job trends, keywords, salary bands scoped to `sources.yaml` | `.claude/agents/job-market-researcher.md` |
| **vacancy-scraper** | Fetch job postings from URLs in `sources.yaml` sites; normalize to markdown | `.claude/agents/vacancy-scraper.md` |
| **gmj-candidate-analyzer** | Parse resumes, spreadsheets, docs in `sources/candidate/`; extract structured data | `.claude/agents/gmj-candidate-analyzer.md` |
| **gmj-candidate-configurator** | Merge candidate findings into `config/candidate.yaml` | `.claude/agents/gmj-candidate-configurator.md` |
| **candidate-translator** | Translate prose fields to ua/ru; write `config/candidate.{lang}.yaml` overlays | `.claude/agents/candidate-translator.md` |
| **cv-composer** | Two-pass skill CV extraction: Pass 1 gap report, Pass 2 write `config/cv/cv.{skill}.{lang}.yaml` | `.claude/agents/cv-composer.md` |
| **gmj-cv-generator** | Render PDF from YAML using `scripts/cv/gmj_render_cv.py` (ReportLab or HTML template) | `.claude/agents/gmj-cv-generator.md` |
| **cv-template-creator** | Create HTML template from user prototype/screenshot using Playwright MCP | `.claude/agents/cv-template-creator.md` |
| **cv-reviewer** | Gap analysis: score CV vs vacancy and market brief; output `sources/analysis/cv-review-*.md` | `.claude/agents/cv-reviewer.md` |
| **cv-enhancer** | Apply review edits to `config/cv/cv.{skill}.{lang}.yaml` or `config/candidate.yaml` | `.claude/agents/cv-enhancer.md` |
| **cv-deliverable-gate** | Verify YAML parses, PDFs exist/readable, acceptance criteria met | `.claude/agents/cv-deliverable-gate.md` |

## Pattern Overview

- **Single delegation hub** (`gmj-orchestrator`) runs at top level; spokes never spawn other spokes via `Task`
- **Mandatory routing** all goals flow through `vacancy-router` to extract `ROUTING_DECISION` JSON with acceptance criteria
- **Criteria tracking** across the pipeline: each spoke receives `criteria_items[]` array (id + text), must return pass/fail mapping
- **Quality gates** after critical operations (configurator, generator, enhancer); gate verifies criteria met before next phase
- **Iteration cap** (`MAX_ENHANCE_CYCLES = 2`): enhance/generate loops limited; after 2 failures, halt and ask user
- **Pipeline run ID** every task prompt includes `pipeline_run_id` for log filtering and audit trail

## Layers

- Purpose: Route user requests, delegate tasks, track quality gates, cap iterations
- Location: `.claude/agents/gmj-orchestrator.md` (hub), `.claude/agents/vacancy-router.md` (routing logic)
- Contains: Task invocations, routing decision parsing, cycle tracking, quality gate handling
- Depends on: All spokes return `agent_result_v1` envelopes; orchestrator parses them
- Used by: Entry point `/gmj-collective` command
- Purpose: Gather market trends, job postings, candidate materials
- Location: `.claude/agents/job-market-researcher.md`, `.claude/agents/vacancy-scraper.md`, `.claude/agents/gmj-candidate-analyzer.md`
- Contains: Web searches, document parsing, structured extraction
- Depends on: `config/sources.yaml` for site/city/language scope; `sources/` for input materials
- Used by: Orchestrator delegates based on user goal
- Purpose: Normalize candidate data to master YAML; translate prose to target languages
- Location: `.claude/agents/gmj-candidate-configurator.md`, `.claude/agents/candidate-translator.md`
- Contains: YAML schema validation, structured merging, language overlays
- Depends on: `config/candidate.yaml` schema; gmj-candidate-analyzer output
- Used by: CV generation pipeline
- Purpose: Extract skill-relevant content, render PDFs with optional HTML templating
- Location: `.claude/agents/cv-composer.md`, `.claude/agents/gmj-cv-generator.md`, `.claude/agents/cv-template-creator.md`
- Contains: Confidence scoring, skill filtering, gap detection, Python rendering via `scripts/cv/gmj_render_cv.py`
- Depends on: `config/candidate.yaml`, market briefs, optional HTML templates in `templates/cv/`
- Used by: Skill-specific CV pipeline; simple full-CV pipeline
- Purpose: Score CV vs vacancy/market; apply improvements in iteration loop
- Location: `.claude/agents/cv-reviewer.md`, `.claude/agents/cv-enhancer.md`
- Contains: Scoring rubrics, gap analysis, YAML/PDF edits
- Depends on: CV YAMLs (`config/cv/` or `config/candidate.yaml`), job posting markdown, market briefs
- Used by: Enhancement loop; may cycle up to 2 times before quality gate
- Purpose: Verify YAML validity, PDF existence/readability, acceptance criteria met
- Location: `.claude/agents/cv-deliverable-gate.md`
- Contains: File validation, YAML parsing, criteria mapping
- Depends on: Acceptance criteria from router; output files from prior agents
- Used by: After generator, enhancer, template-creator to gate next phase

## Data Flow

### Primary Request Path (Full CV, English)

### Skill-Specific CV Pipeline

### Localization (Multi-Language) Flow

### Data Sources

| Flow | Input Path | Output Path | Handler |
|------|-----------|-------------|---------|
| Research | (WebSearch/WebFetch) | `sources/research/{topic}-market-brief.md` | job-market-researcher |
| Vacancies | (WebFetch URLs from sources.yaml) | `sources/vacancies/{posting}.md` | vacancy-scraper |
| Candidate docs | `sources/candidate/*` | (analyzed in memory) | gmj-candidate-analyzer |
| Configuration | gmj-candidate-analyzer output | `config/candidate.yaml` | gmj-candidate-configurator |
| Translation | `config/candidate.yaml` | `config/candidate.{lang}.yaml` | candidate-translator |
| CV composition | `config/candidate.yaml` + market briefs | `config/cv/cv.{skill}.{lang}.yaml` | cv-composer |
| CV generation | `config/candidate.yaml` or `config/cv/` | `output/cv/*.pdf` | gmj-cv-generator (via gmj_render_cv.py) |
| CV review | `output/cv/*.pdf` + `sources/vacancies/*.md` + market brief | `sources/analysis/cv-review-*.md` | cv-reviewer |
| CV enhancement | review output | `config/cv/` or `config/candidate.yaml` updated | cv-enhancer |

- **Master candidate YAML** (`config/candidate.yaml`) is never modified by pipelines; only orchestrator or human hands edit it
- **Skill CVs** (`config/cv/cv.{skill}.{lang}.yaml`) are generated by cv-composer and updated by cv-enhancer; isolated per skill+lang
- **Language overlays** (`config/candidate.{lang}.yaml`) contain only prose; rendered overlaid at PDF time via `gmj_render_cv.py` merge logic
- **Analysis artifacts** (`sources/analysis/`) are ephemeral reports; not fed back into config
- **Acceptance criteria** tracked via `criteria_items[]` (id+text) and `criteria_hash` across task boundaries; gate verifies completeness

## Key Abstractions

- Purpose: Represent candidate profile with sections for professional experience, skills, education, certifications, projects, achievements
- Examples: `config/candidate.yaml`, `config/candidate.ua.yaml`, `config/cv/cv.fpv.ua.yaml`
- Pattern: Flat top-level keys (name, title, summary, contact, technical_expertise, skills, professional_experience, education, certifications, key_achievements, independent_projects, languages, photo); technical_expertise is list of blocks (resume_title + skills list); professional_experience is list of jobs with company, position, duration, location, description, achievements
- Purpose: Encapsulate agent selection logic and acceptance criteria in JSON; allows orchestrator to parse objectively
- Examples: `{"next_agent": "cv-composer", "criteria_items": [{"id": "crit-yaml-parses", "text": "cv YAML is valid"}, ...], "criteria_hash": "abc123..."}`
- Pattern: Deterministic routing based on artifact manifest + user goal; criteria always include checksum for integrity
- Purpose: Standardized output format for all spokes; enables orchestrator to parse status, artifacts, notes uniformly
- Examples: `{"status": "success", "artifacts": [{"type": "pdf", "path": "/abs/path/file.pdf"}], "notes": "...", "cycle_number": 0}`
- Pattern: Always JSON block at end of agent output; status one of (success, fail, handoff, gap_report_ready); artifacts list of {type, path} objects
- Purpose: Minimize YAML duplication by merging prose fields only at render time
- Examples: `config/candidate.ua.yaml` contains only translated prose; `gmj_render_cv.py` deep-merges over base
- Pattern: Overlay same list structure as base; only translatable fields (name, title, summary, prose descriptions); skills/urls/dates inherited
- Purpose: Score every content item (job, skill, cert) 0–100 against skill domain; include only ≥ threshold
- Examples: cv-composer uses threshold 70 by default; can be overridden per run
- Pattern: Internal scoring logic per item type; default to false-negative prevention (include borderline items)

## Entry Points

- Location: `.claude/commands/gmj-collective.md`
- Triggers: User invokes slash command in Claude Code session
- Responsibilities: Instructs hub orchestrator to load `.claude/agents/gmj-orchestrator.md` and await user goal in same turn; hub must use `Task` only to spawn spokes (never nest orchestrator inside Task)
- Location: `.claude/settings.json` → SessionStart hooks → `.claude/hooks/gmj-session-bootstrap.sh`
- Triggers: On session startup, resume, or clear
- Responsibilities: Initialize session state, print bootstrap banner, prepare environment for orchestrator
- Location: `.claude/settings.json` → PreToolUse hooks → `.claude/hooks/gmj-block-destructive-commands.sh`
- Triggers: Before every Bash command
- Responsibilities: Block destructive git commands, file deletions, etc.; raise errors on risky patterns
- Location: `.claude/settings.json` → PostToolUse hooks → `.claude/hooks/gmj-collective-handoff-contract.sh`
- Triggers: After every Task call
- Responsibilities: Log Task payload (pipeline_run_id, spoke name, criteria) to handoff log for audit trail

## Architectural Constraints

- **Threading:** Single-threaded event loop (Claude Code runtime). Spokes run sequentially; orchestrator awaits each `Task` completion before delegating next
- **Global state:** Candidate YAML is singleton master (`config/candidate.yaml`); never modified during runs. Skill CVs are isolated per (skill, lang) pair; safe for concurrent creation (though runs are sequential)
- **Circular imports:** None observed; agent module structure is flat (agents don't import each other; orchestrator imports all agents as strings for Task delegation)
- **File I/O:** All spokes use `Read`/`Write`/`Edit` tools; no direct file system access. Rendering via `Bash` call to `gmj_render_cv.py` script
- **Task nesting:** Forbidden. Orchestrator runs at top level; `Task` contexts do not receive `Task` tool (nest-safe). Spokes never call `Task`
- **Python environment:** `scripts/cv/gmj_render_cv.py` requires `pyyaml` and `reportlab` (or `weasyprint` for HTML templates); dependencies listed in `scripts/cv/requirements.txt`
- **Criteria tracking:** Every routing decision generates `criteria_hash` (SHA-1 of sorted `acceptance_criteria`); gate verifies hash matches to catch modified/corrupted criteria

## Anti-Patterns

### Nested Orchestrator (HUB_CONTEXT_REQUIRED)

### Skipping Router

### Modifying Master YAML During Runs

### Forking/Chaining Spokes in Subagents

### Skipping Quality Gate

## Error Handling

- **File not found:** Spoke logs file path, returns `status: fail`; orchestrator checks manifest + re-runs search if needed
- **Invalid YAML:** Spoke calls `python3 -c "yaml.safe_load(...)"` to validate; returns error message; orchestrator asks user to fix or re-run configurator
- **PDF generation error:** `gmj-cv-generator` captures stderr from `gmj_render_cv.py`; returns `status: fail` with error details
- **Criteria mismatch:** Gate computes `criteria_hash` and compares to router's hash; if mismatch, returns `status: fail` with mismatched ID list
- **Max cycles reached:** After 2 enhancer+generator pairs, gate returns `status: fail` + `cycle_number >= 2`; orchestrator stops and asks user for guidance

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| gmj-agent-output-contract | Canonical agent_result_v1 output envelope schema for all give-me-job spokes. | `.claude/skills/gmj-agent-output-contract/SKILL.md` |
| gmj-candidate-yaml-schema | Schema and editing rules for config/candidate.yaml and config/cv/cv.[skill].[lang].yaml in give-me-job. | `.claude/skills/gmj-candidate-yaml-schema/SKILL.md` |
| gmj-cv-pdf-python | Python commands to extract text and render CV PDFs for give-me-job. | `.claude/skills/gmj-cv-pdf-python/SKILL.md` |
| gmj-cv-review-rubric | Scoring dimensions for CV vs vacancy and market alignment. | `.claude/skills/gmj-cv-review-rubric/SKILL.md` |
| gmj-orchestrator-pipelines | Skill-CV pipeline steps and pre-flight checks for gmj-orchestrator. Loaded dynamically via Read tool when goal matches — NOT statically included. | `.claude/skills/gmj-orchestrator-pipelines/SKILL.md` |
| gmj-sources-config-enforcement | Mandatory sources.yaml read-and-enforce protocol for web search agents (job-market-researcher, vacancy-scraper). | `.claude/skills/gmj-sources-config-enforcement/SKILL.md` |
| gmj-sources-ingestion | Conventions for placing candidate and vacancy materials under sources/. | `.claude/skills/gmj-sources-ingestion/SKILL.md` |
| gmj-vacancy-research-rubric | Rubric for web vacancy search and market-aligned research outputs. | `.claude/skills/gmj-vacancy-research-rubric/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
