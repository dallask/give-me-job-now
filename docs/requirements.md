# Requirements — the milestone inventory

> **Canonical source: each shipped milestone's archived requirements file under
> [`.planning/milestones/`](../.planning/milestones/)** (e.g.
> [`v4.0-REQUIREMENTS.md`](../.planning/milestones/v4.0-REQUIREMENTS.md) for the current
> milestone). Each archived file holds that milestone's authoritative requirement text,
> per-item checkboxes, and phase traceability table. This page is the reader-facing summary: it
> groups requirements into families, gives each a one-line description, and names **where each is
> realized** (agent / script / schema / config). When this page disagrees with an archived
> `.planning/milestones/*-REQUIREMENTS.md` file, that file wins.

Milestone **v2.0 — "Standalone gmj Collective"** hardened the collective against the classic
multi-agent failure modes (fabricated facts, off-target drift, context bloat, silent quality decay)
and packaged it as a standalone, installable distribution. Its **core value**: given a real job
offer, the system produces truthful, offer-optimized application artifacts that provably trace back
to the candidate's real profile and pass mandatory quality gates. That core value is unchanged by
every later milestone.

Requirements are organized into **12 families** (52 requirements total). Each family maps to exactly
one roadmap phase. All families are **Complete** except `DOCS-02` (the root `README.md`), which is
authored in a later plan of the documentation phase.

See [features.md](features.md) for the user-facing capabilities these requirements deliver, the
authoritative [architecture](ARCHITECTURE.md) for how the roster realizes them, and
[cli-tools.md](cli-tools.md) for the deterministic scripts named below.

---

## Requirement families

| Family | What it guarantees | Primarily realized in | Disposition |
|--------|--------------------|-----------------------|-------------|
| **SCHEMA** (×6) | The updated `config/candidate.yaml` is the single source of truth every consumer renders/verifies against, with a single-owner field schema preventing renderer/bridge/validator drift. | `config/candidate.yaml`; `scripts/artifacts/gmj_schema_fields.py`, `gmj_yaml_path.py`; `scripts/cv/gmj_draft_to_cv_yaml.py`; [`gmj-candidate-yaml-schema`](skills.md) skill; [`gmj-candidate-configurator`](agents.md) | Complete |
| **INTERVIEW** (×6) | An interactive interviewer asks only about real gaps, never writes the master YAML directly, never leads, and captures search preferences behind a subset-of-scope validator. | [`/gmj-interview`](commands.md); `config/preferences.yaml`; `scripts/preferences/gmj_validate_preferences.py`; [`gmj-candidate-configurator`](agents.md) | Complete |
| **SCOUT** (×5) | Offer discovery is job-seeker-framed, ranked by preferences strictly within `config/sources.yaml` scope, parallel across boards, and deterministically merged; the scope-guard never fails open. | [`gmj-offer-scout`](agents.md); `scripts/offers/gmj_merge_shortlists.py`; `config/sources.yaml`; [`gmj-sources-config-enforcement`](skills.md) skill; [`gmj-sources-scope-guard`](rules.md) hook | Complete |
| **SELECT** (×4) | The user can multi-select offers; each gets its own frozen offer-spec and independently-gated artifact set, run under a resumable batch manifest. | [`/gmj-batch`](commands.md); `scripts/pipeline/gmj_batch.py`; `schemas/batch_manifest.schema.json` | Complete |
| **TEMPLATE** (×6) | A pasted CV-design screenshot becomes a reusable `{{ candidate.* }}`-bound HTML/Jinja2 template, matched via a bounded compare==ship visual loop with zero sample-text leakage and Cyrillic support. | [`gmj-template-creator`](agents.md); [`/gmj-template`](commands.md); `scripts/cv/gmj_visual_diff.py`, `gmj_template_lint.py`; [`gmj-cv-generator`](agents.md) | Complete |
| **ARTIFACT** (×3) | Interview-prep and cover-letter artifacts are richer and offer-tailored while staying span-traced and gated; quantified framing lifts fit without inventing facts. | [`gmj-artifact-composer`](agents.md); `scripts/cv/gmj_render_interview_prep.py`, `gmj_render_cover_letter.py` | Complete |
| **REGRESSION** (×3) | Deterministic UAT-deferred behaviors become asserted regression tests; LLM-judgment items become scored evals (never boolean CI gates); every deferred item is converted or explicitly re-deferred. | `tests/` regression + eval suites | Complete |
| **ERGO** (×4) | The user can list, inspect, and resume runs/batches over a terse-by-default timeline with a `--json` mode — read-only over existing per-run state and gate logs, no second datastore. | [`/gmj-runs`](commands.md); `scripts/pipeline/gmj_runs.py` | Complete |
| **REBRAND** (×4) | All app-owned agents/skills/commands/hooks/scripts adopt the `gmj-`/`gmj_` prefix in lockstep, gated by an explicit framework-vs-app ownership manifest. | `scripts/gmj_rebrand.py`; `config/ownership-manifest.yaml` | Complete |
| **PACKAGE** (×4) | A `gmj-core/` payload + `bin/gmj-tools.cjs` installer stands the collective up on a clean runtime; a report-only GSD-removal tool is prepared (not executed this milestone). | `scripts/gmj_build_payload.py`, `scripts/gmj_remove_gsd.py`; `gmj-core/` | Complete |
| **STRUCT** (×3) | The project structure is clarified, a frontmatter-scoped `rules/` folder keeps agent context lean, and `CLAUDE.md` is refreshed with no stale references. | `rules/`; `.claude/CLAUDE.md` | Complete |
| **DOCS** (×4) | A cross-linked, English-only `docs/` set + a root `README.md` describe the system, verified against the codebase, with a documented refresh-at-finalization convention. | `docs/`; `README.md`; `tests/test_docs_current.py`; [`docs-currency`](rules.md) rule | DOCS-02 pending; rest Complete |

Full v2.0 per-requirement text and its phase-by-phase traceability table live in
[`.planning/milestones/v2.0-REQUIREMENTS.md`](../.planning/milestones/v2.0-REQUIREMENTS.md).
Milestones **v3.0** ("Skill-CV Depth") and **v3.1** hardened and extended the artifact/fit
pipeline between v2.0 and v4.0; their requirement text lives in
[`v3.0-REQUIREMENTS.md`](../.planning/milestones/v3.0-REQUIREMENTS.md) and
[`v3.1-REQUIREMENTS.md`](../.planning/milestones/v3.1-REQUIREMENTS.md).

---

## v4.0 requirements — "Multi-Runtime & Parallel Throughput"

Milestone **v4.0** diversified the collective's runtime/provider surface, sped up multi-offer
processing via bounded parallel fan-out, and broadened default deliverables — while keeping the
existing Claude Code CLI path and the truth/fit gates untouched. **29 requirements** across **8
families**, all **Complete**; full text and the phase traceability table (Phases 32–39) live in
[`v4.0-REQUIREMENTS.md`](../.planning/milestones/v4.0-REQUIREMENTS.md).

| Family | What it guarantees | Primarily realized in | Disposition |
|--------|--------------------|-----------------------|-------------|
| **ARTF** (×4) | `/gmj-pipeline-run` generates all three artifact types by default, each independently composed and gated under its own derived `run_id` (no shared verdict); CV render always produces a saved PDF **and** a first-class `.html` sibling; `--artifact-types` narrows the set. | `scripts/pipeline/gmj_pipeline_run.py`; `scripts/cv/gmj_render_cv.py`; `scripts/pipeline/gmj_check_delivery.py`; [architecture](ARCHITECTURE.md) §5.1 | Complete |
| **DOCTAB** (×3) | `gmj-dashboard` gains a read-only "docs" tab listing `docs/*.md` in a `DataTable`, opening a dismissible Markdown modal re-read fresh from disk on each open. | `scripts/dashboard/gmj_dashboard.py`, `gmj_dashboard_model.py` | Complete |
| **SEARCH** (×4) | A Playwright MCP viability spike for bot-protected boards, evaluated honestly; the spike returned **NO-GO**, so `gmj-offer-scout`, the scope-guard hook, and schemas remain byte-identical (SEARCH-02..04 vacuously satisfied). | `.planning/phases/34-*/34-RESEARCH.md`; `gmj-offer-scout` (unchanged) | Complete (NO-GO) |
| **CONC** (×6) | A frozen `max_parallel_offers` cap bounds concurrent offer pipelines; a deterministic dispatch-cap script (never the model) decides what's dispatchable; concurrent-safe manifest writes; per-offer failure isolation; Gate A/B still enforced per-offer-per-type; expressed as parallel `Task` calls in one hub turn, never a nested sub-orchestrator. | `scripts/pipeline/gmj_dispatch_cap.py`, `gmj_batch.py`; [architecture](ARCHITECTURE.md) §5.1 | Complete |
| **CLEANUP** (×2) | A proposal-only report enumerates unused-file candidates with evidence, excluding anything with an active reference; zero deletions executed. | `scripts/gmj_cleanup_report.py`; `output/analysis/cleanup-report.md` | Complete |
| **INSTALL** (×4) | A `.sh` installer clones/installs all 4 `requirements.txt` files plus Node/MCP deps, is idempotent, checks prerequisites, and delegates config/hook staging to the existing `gmj-tools.cjs` installer. | `gmj-core/bin/install.sh`, `gmj-tools.cjs` | Complete |
| **SDK** (×3) | An experimental, additive-only Claude Agent SDK runtime prototype dispatches one spoke via `claude-agent-sdk`, alongside — never replacing — the Claude Code CLI path; ships a hook-parity checklist, labeled unsupported for autonomous runs until parity is verified. | `scripts/runtime/gmj_sdk_runner.py`, `HOOK-PARITY.md`; [architecture](ARCHITECTURE.md) §5.2 | Complete |
| **PROVIDER** (×3) | An experimental, additive-only Cursor adapter generator translates `.claude/agents/*.md` into `.cursor/agents/*.md`, never wired into the default flow; documented enforcement gaps (no confirmed PreToolUse-hook parity, no confirmed Task-nesting restriction). | `gmj-core/bin/gmj-cursor-adapter.cjs`, `CURSOR-HOOK-PARITY.md`; [architecture](ARCHITECTURE.md) §5.2 | Complete |

---

## v6.0 requirements — "Pipeline Hardening, Ops Tooling & Site Rebuild"

Milestone **v6.0** fixed real defects surfaced by the first live end-to-end
`/gmj-pipeline-run` and the full test suite, added operator hygiene tooling, investigated an
optional external-search integration, relocated/restructured a couple of file-layout
conventions, and rebuilt the public site on Next.js — all while keeping truth/fit gates and
hub-and-spoke untouched. **23 requirements** across **6 families**, all **Complete**; full
text and the phase traceability table (Phases 41-47) live in
[`v6.0-REQUIREMENTS.md`](../.planning/milestones/v6.0-REQUIREMENTS.md).

| Family | What it guarantees | Primarily realized in | Disposition |
|--------|--------------------|-----------------------|-------------|
| **PIPE** (×11) | Gate A's stale-fixture drift is fixed (numeric-invention vs. unresolved-span classified correctly); CV renderer `repr()`-leak fixes across both backends; photo rendering; single-language-per-artifact selection; populated Education/Languages/Certifications; a pinned shortlist entry shape with defensive normalization; a `discovered_at` liveness signal; the documented `current_step` seeding convention; differentiated cap-exhaustion reporting plus a bounded `propose_raise` auto-retry. | `scripts/artifacts/gmj_check_truth.py`, `gmj_format_fields.py`; `scripts/offers/gmj_detect_language.py`, `gmj_merge_shortlists.py`; `scripts/pipeline/gmj_check_cap.py`; Phase 41 | Complete |
| **STRUCT** (×3, of which STRUCT-01/02 realize in Phase 42 and STRUCT-03 in Phase 43) | `sources/` restructured to strictly intake-only (git-ignored generated subfolders); `output/{analysis,artifacts,offers,research,vacancies,logs,cv}/` established as the single generated-content root via an atomic, multi-consumer migration; `rules/*.md` repo-root placement reaffirmed and documented. | `.gitignore`; `CLAUDE.md` Paths table; `rules/README.md`; Phases 42-43 | Complete |
| **OPS** (×1) | An interactive `questionary`-based cleanup wizard lets the operator select and delete generated-content categories behind an un-skippable confirm — a wholly independent sibling of the read-only reporter. | `scripts/gmj_cleanup_wizard.py`; Phase 44 | Complete |
| **SEARCH** (×3) | A viability spike evaluates a Firecrawl-style external scrape/search tool as an opt-in `gmj-offer-scout` alternative; verdict **NO-GO** (SEARCH-02/03 vacuously satisfied — zero source files touched). | `.planning/phases/45-optional-search-integration-spike/45-RESEARCH.md`; `gmj-offer-scout` (unchanged); Phase 45 | Complete (NO-GO) |
| **SITE** (×4) | The public site is rebuilt on Next.js App Router (static export) with reusable components, SCSS design tokens extracted from the DaisyUI `night` theme (Tailwind CDN + DaisyUI removed), a new push/PR `build-site.yml` CI workflow separate from the existing `workflow_dispatch`-only `publish-site.yml`, and a documented source-tree placement decision. | `web/` (Next.js project), `web/app/`, `web/components/`, `web/styles/`; `.github/workflows/build-site.yml`, `.github/workflows/publish-site.yml`; Phase 46 | Complete |
| **DOCS** (×1) | `docs/*.md` and the public site's own content are refreshed for v6.0 currency, verified via `tests/test_docs_current.py`. | `docs/`; `web/content/docs/*.mdx`; `README.md`; Phase 47 | Complete (this phase) |

---

## Implementation-level requirement tags

Beyond the 12 milestone families above, the deterministic CLI tools carry **finer-grained
requirement tags** in their module docstrings — the acceptance anchors each script satisfies. These
are the traceability breadcrumbs you see in [cli-tools.md](cli-tools.md), for example:

- **COMPOSE-02 / COMPOSE-03** — retry accounting and executed provenance for composed drafts
  (`gmj_record_retry.py`, `gmj_check_claims.py`, `gmj_yaml_path.py`).
- **TRUTH-01/03/04** — Gate A deterministic truth pre-gate (`gmj_check_truth.py`).
- **FIT-01/02/03/05** — Gate B target-fit scoring (`gmj_score_fit.py`); the calibrated
  `coverage_threshold` (FIT-04) lives in `config/fit_thresholds.yaml`.
- **INTAKE-01/02/03** — offer freeze, tamper-check, and run-state writes
  (`gmj_freeze_offer.py`, `gmj_check_offer.py`, `gmj_state_write.py`).
- **GUARD-03 / GUARD-04** — gate-verdict recording, delivery precondition, and feedback projection
  (`gmj_record_gate.py`, `gmj_check_delivery.py`, `gmj_map_feedback.py`).
- **ARCH-05 / ARCH-06 / EXEC-01/03** — content-integrity hashing, deterministic routing, and the
  frozen retry cap (`gmj_hash_artifact.py`, `gmj_route.py`, `gmj_check_cap.py`).
- **PACKAGE-01 / REBRAND-01/02/03** — the build and rebrand maintenance tools
  (`gmj_build_payload.py`, `gmj_rebrand.py`).
- **PIPE-06** — the documented no-go for non-numeric wrong-span detection
  (`scripts/pipeline/gmj_check_cap.py`'s `propose_raise` semantics).

These tags are internal implementation anchors; the milestone-level families in the table above —
and their canonical text in [`.planning/REQUIREMENTS.md`](../.planning/REQUIREMENTS.md) — remain the
authoritative acceptance inventory.
