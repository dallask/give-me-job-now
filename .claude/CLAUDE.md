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
- Textual 6.1+ (`<7`) - Read-only, opt-in `--manage` btop-style TUI cockpit (`scripts/dashboard/gmj_dashboard.py`)
- claude-agent-sdk (EXPERIMENTAL) - `scripts/runtime/gmj_sdk_runner.py`, an additive, unsupported-for-autonomous-runs alternate runtime prototype dispatching one spoke through the SDK instead of the CLI
- None detected
- Bash scripting via `.claude/hooks/` for session lifecycle and pre-tool checks

## Key Dependencies

- PyYAML - Mandatory for candidate profile parsing; all CV pipelines depend on YAML configs (`config/candidate.yaml`, language overlays)
- ReportLab - Core PDF rendering engine for built-in CV template (ReportLab-only mode)
- Jinja2 - Required for HTML CV template rendering before WeasyPrint
- python-docx, openpyxl, pypdf, Pillow - Support document extraction tools; not required for core CV generation but enable `scripts/cv/gmj_extract.py` to ingest candidate source files (Word, Excel, PDF)
- Textual - Required for the `gmj-dashboard` operator cockpit (`scripts/dashboard/gmj_dashboard.py`); not required for the core offer→artifacts pipeline

## Configuration

- No `.env` file in repository (configuration is YAML-based and checked in)
- Path-based configuration: agent tools reference `config/sources.yaml` for job board allowlist and search geo/lang limits
- `.mcp.json` - MCP server configuration for Playwright browser automation
- Multiple pinned `requirements.txt` files per script family: `scripts/cv/requirements.txt` (CV render/extract), `scripts/dashboard/requirements.txt` (Textual dashboard), `scripts/contracts/requirements.txt`, `scripts/preferences/requirements.txt`, and `scripts/runtime/requirements.txt` (EXPERIMENTAL Claude Agent SDK runtime)
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
> That document defines the hub + 5-spoke roster, per-spoke isolation boundaries, the
> offer→artifacts data flow, the two-layer runtime control loop, and the anti-drift principles.
> The summary below reflects the current collective; when it disagrees with
> `docs/ARCHITECTURE.md`, that document wins.

## System Overview

Hub-and-spoke. A single top-level hub (`gmj-orchestrator`) holds `Task` and delegates to five
bounded spokes; spokes never spawn spokes (a nested hub loses `Task`). Two retained supporting
agents feed the canonical profile. Every hop is a **typed file-artifact path**, never a transcript
(artifact-only handoff). Gate A (truth) must pass before Gate B/C (fit); truthfulness is never
bypassed in any mode.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **gmj-orchestrator** | Hub: routing, task delegation, quality gates, cycle tracking; only `Task` holder | `.claude/agents/gmj-orchestrator.md` |
| **gmj-offer-scout** | Discover, normalize, and rank offers within `config/sources.yaml` scope; emit a frozen, hashed `offer_spec` | `.claude/agents/gmj-offer-scout.md` |
| **gmj-artifact-composer** | From `config/candidate.yaml` + `offer_spec`, compose CV / cover letter / interview-prep; owns the gap-report pass and enhance loop | `.claude/agents/gmj-artifact-composer.md` |
| **gmj-truth-verifier** | Gate A (truthfulness, hard block): re-ground every claim against `config/candidate.yaml`; reframe allowed, invention blocked | `.claude/agents/gmj-truth-verifier.md` |
| **gmj-fit-evaluator** | Gate B (target-fit coverage, hard block) + Gate C (polish, advisory) | `.claude/agents/gmj-fit-evaluator.md` |
| **gmj-cv-generator** | Render approved artifacts to PDF via `scripts/cv/gmj_render_cv.py` (render-only) | `.claude/agents/gmj-cv-generator.md` |
| **gmj-candidate-analyzer** | Parse candidate source materials; extract structured data | `.claude/agents/gmj-candidate-analyzer.md` |
| **gmj-candidate-configurator** | Canonical write/merge into `config/candidate.yaml` | `.claude/agents/gmj-candidate-configurator.md` |
| **gmj-template-creator** | Create branded-CV HTML template from a screenshot/prototype (Playwright MCP) | `.claude/agents/gmj-template-creator.md` |

> **Historical (superseded).** The earlier 13-agent pipeline — a standalone LLM router, a split
> scraper/researcher, a split composer/reviewer/enhancer, a standalone deliverable gate, a prose
> translator, and a template creator wired into the old skill-CV loop — was consolidated into the
> roster above. `docs/ARCHITECTURE.md` §7 holds the legacy→new mapping.

## Data Flow (offer → artifacts)

1. **Intake.** `gmj-offer-scout` reads `config/sources.yaml` (mandatory), stays within its allow-list, normalizes + ranks offers, and freezes the chosen one as a hash-stamped `offer_spec`.
2. **Compose.** `gmj-artifact-composer` reads `config/candidate.yaml` (read-only) + `offer_spec` and emits `artifact_draft` files (CV, cover letter, interview-prep); owns the gap-report pass and enhance loop.
3. **Gate A — truth.** `gmj-truth-verifier` re-grounds every claim against `config/candidate.yaml` and emits a `gate_result`; a fabrication is a hard block that loops back to the composer with offending lines named. Gate A passes first.
4. **Gate B/C — fit + polish.** `gmj-fit-evaluator` scores must-have coverage (Gate B hard block) and polish (Gate C advisory) against `offer_spec`; a Gate-B failure loops back to the composer (bounded retry).
5. **Render.** A draft that passes both gates reaches `gmj-cv-generator`, which renders it to `output/cv/*.pdf` via `gmj_render_cv.py`.

Every arrow is a named file-artifact path, not a transcript.

## Runtime Control Loop & Features

A **two-layer control plane**: a deterministic layer of small single-purpose Python scripts
(exit 0/1, no LLM, no network) makes every safety decision; the LLM layer (`gmj-orchestrator`, the
only `Task` holder) dispatches spokes and calls those scripts via `Bash`. The model never decides
whether a gate passed, whether the retry cap is hit, or whether an artifact is deliverable.

- **Dual-mode + retry cap.** `execution_mode` (frozen at `init_run`) gates only the post-PASS human pause; `autonomous` removes the *human* pause, never the *machine* gate. Loops are retry-capped; cap exhaustion is a hard stop, never ship-last-attempt.
- **Parallel fan-out, sequential gates.** Independent work — ranking N offers and composing the 3 artifact types — is dispatched as parallel `Task` calls in one hub turn (orchestrated fan-out on Claude Code's single-threaded loop). Gated steps run sequentially per artifact.
- **Run-scoped state.** Resumable state + gate-log audit artifacts live under `.pipeline/runs/<run_id>/` (git-ignored); `run_id` is sanitized before it becomes a directory name.

CLI entry points: `/gmj-collective` (interactive hub), `/gmj-pipeline-run` (whole flow,
generating the full default artifact set unless narrowed), `/gmj-pipeline/{scout,freeze,compose,
verify,evaluate,generate}` (per-step), `/gmj-batch` (bounded-concurrency multi-offer batch),
`/gmj-interview` (gap-filling interviewer + preferences), `/gmj-template` (screenshot → branded
template), `/gmj-runs` (read-only run inspector), `/gmj-dashboard` (live btop-style pipeline
cockpit, read-only by default with an opt-in `--manage` action layer).

## Contracts, Schemas & Structure

Typed JSON envelopes are versioned under `schemas/*.schema.json`: `agent_result_v1`, `offer_spec`,
`artifact_draft`, `gate_result`, `gate_feedback`, `preferences`, `shortlist`, `batch_manifest`.
Every spoke emits `agent_result_v1`. The migrated candidate/CV YAML schema + edit rules live in the
`gmj-candidate-yaml-schema` skill.

Final structure: `config/` (canonical YAML, overlays, i18n, pipeline/fit config, `sources.yaml`),
`config/cv/` (derived skill CV YAML), `schemas/` (envelope contracts), `scripts/`
(`cv/`, `offers/`, `artifacts/`, `contracts/`, `pipeline/`, `preferences/`, `dashboard/` for the
`gmj-dashboard` cockpit, `runtime/` for the EXPERIMENTAL Claude Agent SDK runtime prototype),
`.claude/` (settings, agents, hooks, skills, commands), `rules/` (Read-on-demand invariants), and
`gmj-core/` (packaged standalone payload + installers `gmj-core/bin/install.sh` and
`gmj-core/bin/gmj-tools.cjs`, plus the EXPERIMENTAL `gmj-core/bin/gmj-cursor-adapter.cjs`).

## Anti-Patterns

- **Nested orchestrator** — never `Task`-spawn the hub; nested hubs lose `Task` and spokes cannot run.
- **Spokes chaining spokes** — spokes never call `Task`; only the hub delegates.
- **Mutating the master YAML during a run** — `config/candidate.yaml` is canonical truth, written only by `gmj-candidate-configurator` or a human.
- **Skipping a gate** — Gate A (truth) and Gate B (target-fit) are non-bypassable in any mode.
- **Transcript handoff** — spokes exchange typed file-artifact paths, never conversation.

## Error Handling

- **File not found / invalid YAML:** the spoke returns `status: fail`; the hub re-runs the prior step or asks the user.
- **PDF generation error:** `gmj-cv-generator` captures stderr from `gmj_render_cv.py` and returns `status: fail`.
- **Gate failure:** the deterministic gate script records the `gate_result` and loops to the composer until the retry cap; at the cap the hub emits a hard-stop report naming the failing artifact + reason.
- **Delivery guard:** `gmj_check_delivery.py` refuses to deliver any artifact lacking a recorded Gate A ∧ Gate B pass.

## Cross-Cutting Concerns

**Rules index (`rules/`).** Load-bearing invariants live in repo-root `rules/*.md`, one per file,
each with a `scope:` frontmatter block. They are **Read on demand** (not auto-loaded) when a task
matches a rule's scope — see [`rules/README.md`](../rules/README.md) for the convention and match
table; `tests/test_rules_scope.py` keeps the index complete. Core invariants: `truthfulness.md`,
`hub-and-spoke.md`, `sources-scope.md`, `gmj-naming.md`, `python-render-only.md`,
`gate-non-bypassability.md`.

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| gmj-agent-output-contract | Canonical agent_result_v1 output envelope schema for all give-me-job spokes. | `.claude/skills/gmj-agent-output-contract/SKILL.md` |
| gmj-candidate-yaml-schema | Schema and editing rules for config/candidate.yaml and config/cv/cv.[skill].[lang].yaml in give-me-job. | `.claude/skills/gmj-candidate-yaml-schema/SKILL.md` |
| gmj-cv-pdf-python | Python commands to extract text and render CV PDFs for give-me-job. | `.claude/skills/gmj-cv-pdf-python/SKILL.md` |
| gmj-cv-review-rubric | Scoring dimensions for CV vs vacancy and market alignment. | `.claude/skills/gmj-cv-review-rubric/SKILL.md` |
| gmj-fit-rubric | Gate B must-have coverage weights + calibrated threshold derivation, and Gate C 5-dimension polish rubric (advisory). | `.claude/skills/gmj-fit-rubric/SKILL.md` |
| gmj-orchestrator-pipelines | Skill-CV pipeline steps and pre-flight checks for gmj-orchestrator. Loaded dynamically via Read tool when goal matches — NOT statically included. | `.claude/skills/gmj-orchestrator-pipelines/SKILL.md` |
| gmj-sources-config-enforcement | Mandatory sources.yaml read-and-enforce protocol for the web-search spoke (gmj-offer-scout). | `.claude/skills/gmj-sources-config-enforcement/SKILL.md` |
| gmj-sources-ingestion | Conventions for placing candidate and vacancy materials under sources/. | `.claude/skills/gmj-sources-ingestion/SKILL.md` |
| gmj-truth-rubric | Reframe/fabrication boundary (4 rules) for gmj-truth-verifier Gate A per-claim verdicts. | `.claude/skills/gmj-truth-rubric/SKILL.md` |
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
