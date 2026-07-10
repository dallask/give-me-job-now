# Skills

The collective ships **10 project skills** under `.claude/skills/`, each a `gmj-*/SKILL.md`
carrying `name` + `description` frontmatter and a body of schema rules, rubrics, or protocols.
Skills are **domain knowledge**, not agents — they encode the contracts and rubrics that agents
apply. Most are surfaced to an agent by name (Claude Code's skill mechanism); one
(`gmj-orchestrator-pipelines`) is **Read on demand** rather than statically included.

Each entry below gives the skill's description (mined from its `SKILL.md` frontmatter), what it
covers, when it is loaded, and the agent(s) that apply it. Cross-references:
[agents.md](agents.md) (the roster that applies these skills) and [rules.md](rules.md) (the
load-bearing invariants that pair with several skills).

---

### gmj-agent-output-contract

**Description:** Canonical `agent_result_v1` output envelope schema for all give-me-job spokes.

Defines the single fenced `agent_result_v1` block every spoke ends its final message with:
`schema`, `agent`, `pipeline_run_id`, `status` (`success | fail | gap_report_ready | handoff`),
`artifacts[]`, `acceptance_criteria_met/failed` (ID strings from `criteria_items[]`),
`next_action`, `handoff_target`, `notes`. Includes the acceptance-criteria ID protocol and the
gate invariants (unknown IDs fail; met ∩ failed must be empty; unreported items count as failed).

- **When loaded:** by every spoke when emitting its result envelope.
- **Applied by:** all spokes; mirrored by `schemas/agent_result_v1.schema.json`
  (see [references.md](references.md)).

### gmj-candidate-yaml-schema

**Description:** Schema and editing rules for `config/candidate.yaml` and
`config/cv/cv.[skill].[lang].yaml` in give-me-job.

The authoritative schema for the canonical profile: top-level keys, the **nested `contact`
object**, the `expertise` skills source, multi-language overlay rules (wholesale list
replacement at deep-merge), the dotted/indexed source-span grammar, and the derived
`config/cv/*.yaml` rules (same schema, complete files, never hand-edited). Also the editing rules
(valid YAML, no fabricated employers/dates, no extra keys in CV YAML). See
[configuration.md](configuration.md#config-candidateyaml) for the on-disk shape.

- **When loaded:** by agents that read or write the candidate/CV YAML.
- **Applied by:** `gmj-candidate-configurator`, `gmj-artifact-composer`, `gmj-cv-generator`;
  paired with the `truthfulness.md` rule.

### gmj-cv-pdf-python

**Description:** Python commands to extract text and render CV PDFs for give-me-job.

The operational command reference for the Python render/extract path: venv + requirements setup,
`scripts/cv/gmj_extract.py` for text extraction, and `scripts/cv/gmj_render_cv.py` for rendering
(ReportLab `--no-template`, optional WeasyPrint HTML templates, `--lang`, `--out`, `photo`
support). Default output `output/cv/<slug>-<YYYYMMDD>.pdf`.

- **When loaded:** by the render spoke before invoking the Python scripts.
- **Applied by:** `gmj-cv-generator`; paired with the `python-render-only.md` rule.

### gmj-cv-review-rubric

**Description:** Scoring dimensions for CV vs vacancy and market alignment.

A 0–5 scoring rubric across six dimensions — must-have coverage, keyword/ATS, impact, market
alignment, credibility, readability — with required outputs (scored table + evidence, top-5
prioritized edits, risks) and an enhancement handoff that maps each edit to YAML paths.

- **When loaded:** during CV review / enhancement scoring.
- **Applied by:** the review/enhance work within `gmj-artifact-composer`'s enhance loop.

### gmj-fit-rubric

**Description:** Gate B must-have coverage weights + calibrated threshold derivation, and Gate C
5-dimension polish rubric (advisory).

Defines the **Gate B** coverage-only hard-block (`covered_count / total_count >=
coverage_threshold`, a literal ID/count match), the secondary advisory weights, the FIT-04
threshold derivation from `tests/fixtures/fit/`, the advisory **Gate C** 5-dimension polish
rubric (never blocks), and the injection guard (offer/claim text is data, never instructions).
Owns the derivation record for `config/fit_thresholds.yaml`
(see [configuration.md](configuration.md#config-fit_thresholdsyaml)).

- **When loaded:** during target-fit evaluation.
- **Applied by:** `gmj-fit-evaluator`; paired with the `gate-non-bypassability.md` rule.

### gmj-orchestrator-pipelines

**Description:** Skill-CV pipeline steps and pre-flight checks for `gmj-orchestrator`. Loaded
dynamically via Read tool when goal matches — **NOT statically included.**

The step-by-step skill-CV pipeline (market research → compose → gap approval → render →
review/enhance loop, bounded by `MAX_ENHANCE_CYCLES=2`) plus the inline pre-flight checks the hub
runs before expensive spokes.

- **When loaded:** **Read on demand** by the hub — Read once at pipeline start when the goal
  matches, then referenced from memory; not auto-loaded on every turn.
- **Applied by:** `gmj-orchestrator`.

### gmj-sources-config-enforcement

**Description:** Mandatory `sources.yaml` read-and-enforce protocol for the web-search spoke
(`gmj-offer-scout`).

The mandatory read-and-enforce protocol: read `config/sources.yaml` before any web search and
apply `sites` (→ `allowed_domains`), `cities` (query scope), `languages`, and the `limits.*`
hard caps; initialise and increment call counters; note any limit hit; fall back to unrestricted
search with a logged warning only if the file is missing/unparsable. The single web-search spoke
in the current roster is **`gmj-offer-scout`** — apply this protocol there.

- **When loaded:** before any offer-discovery web search.
- **Applied by:** `gmj-offer-scout`; paired with the `sources-scope.md` rule and enforced at
  runtime by the `gmj-sources-scope-guard.sh` hook.

### gmj-sources-ingestion

**Description:** Conventions for placing candidate and vacancy materials under `sources/`.

The `sources/` vs `output/` layout split (`sources/` is intake-only for raw human-provided
uploads; normalized vacancies live under `output/vacancies/`, market briefs under
`output/research/`, and analysis/CV-review summaries under `output/analysis/`), kebab-case dated
filename conventions, PII/secret handling, and the extract-first analyzer workflow via
`python3 scripts/cv/gmj_extract.py "<file>" --json`.

- **When loaded:** when ingesting or organizing candidate/vacancy source materials.
- **Applied by:** `gmj-candidate-analyzer` (raw uploads under `sources/`) and `gmj-offer-scout`
  (generated vacancy/research/analysis content under `output/*`).

### gmj-truth-rubric

**Description:** Reframe/fabrication boundary (4 rules) for `gmj-truth-verifier` Gate A per-claim
verdicts.

The **Gate A** truthfulness boundary: judge each claim against only its cited
`config/candidate.yaml` span. R1 vocabulary-swap/emphasis is allowed; R2 scope-inflation, R3
numeric-invention, and R4 cross-entry-merge are blocked. `reframing_note` is an untrusted signal.
Any failed claim fails the artifact — a binary hard-block with no bypass in any mode.

- **When loaded:** during truth verification.
- **Applied by:** `gmj-truth-verifier`; paired with the `truthfulness.md` and
  `gate-non-bypassability.md` rules.

### gmj-vacancy-research-rubric

**Description:** Rubric for web vacancy search and market-aligned research outputs.

Search discipline (specific queries, primary sources, dedup, no verbatim paste), the normalized
vacancy record fields (title/company/URL/location, must-have vs nice-to-have, ATS keywords,
concerns), market-brief expectations (keyword clusters, dated trend notes, directional salary
ranges), and the anti-hallucination rule (write **Unknown** rather than invent).

- **When loaded:** during vacancy search and market research.
- **Applied by:** `gmj-offer-scout` when producing normalized vacancies and market briefs.

---

## Skill index

| Skill | Load mode | Applied by |
|-------|-----------|------------|
| [`gmj-agent-output-contract`](#gmj-agent-output-contract) | statically surfaced | all spokes |
| [`gmj-candidate-yaml-schema`](#gmj-candidate-yaml-schema) | statically surfaced | `gmj-candidate-configurator`, `gmj-artifact-composer`, `gmj-cv-generator` |
| [`gmj-cv-pdf-python`](#gmj-cv-pdf-python) | statically surfaced | `gmj-cv-generator` |
| [`gmj-cv-review-rubric`](#gmj-cv-review-rubric) | statically surfaced | `gmj-artifact-composer` (enhance loop) |
| [`gmj-fit-rubric`](#gmj-fit-rubric) | statically surfaced | `gmj-fit-evaluator` |
| [`gmj-orchestrator-pipelines`](#gmj-orchestrator-pipelines) | **Read on demand** | `gmj-orchestrator` |
| [`gmj-sources-config-enforcement`](#gmj-sources-config-enforcement) | statically surfaced | `gmj-offer-scout` |
| [`gmj-sources-ingestion`](#gmj-sources-ingestion) | statically surfaced | `gmj-candidate-analyzer`, `gmj-offer-scout` |
| [`gmj-truth-rubric`](#gmj-truth-rubric) | statically surfaced | `gmj-truth-verifier` |
| [`gmj-vacancy-research-rubric`](#gmj-vacancy-research-rubric) | statically surfaced | `gmj-offer-scout` |

See also: [agents.md](agents.md) for the roster that applies these skills, and
[rules.md](rules.md) for the paired load-bearing invariants.
