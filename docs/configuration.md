# Configuration

Every file under `config/` is hand-authored (or, for the derived CV YAMLs and language
overlays, generated from the canonical profile) and read by a named consumer — an agent, a
deterministic Python script, or a hook. This page documents the **full configuration surface**:
one `### config/<file>` block per file, each giving its purpose, its on-disk shape, and the
schema / validator / consumer that owns it.

Config and data filenames are **stable** — they keep their plain names (`candidate.yaml`,
`sources.yaml`, …) and are never `gmj-` / `gmj_` prefixed (that prefix rule applies only to
agents, skills, commands, hooks, and scripts). The JSON Schemas that validate the structured
config envelopes live under `schemas/` and are catalogued in [references.md](references.md).

Related reading: [skills.md](skills.md) (the schema/rubric skills that document some of these
shapes), [cli-tools.md](cli-tools.md) (the `gmj_*.py` consumers), and
[agents.md](agents.md) (the spokes that read each file).

---

### config/candidate.yaml

The **canonical candidate profile** — the single source of truth every artifact claim must
trace back to. English base file. It is written only by `gmj-candidate-configurator` or a human,
never mutated mid-run. Top-level keys (all snake_case):

```yaml
name: "Your Name"
photo: sources/candidate/photo.jpg        # optional; path relative to repo root (or contact.photo)
title: "Lead Software Engineer & AI-Augmented Tech Lead | …"
summary: "Lead software engineer with 19+ years …"
contact:                                  # nested object — no flat github/linkedin scalars
  phone: "+380…"
  email:                                  # array of strings (one or more addresses)
    - "hello@example.pro"
  address: "City, Country"
  website:
    personal: ["https://…"]              # arrays of URLs
    company:  ["https://…"]
    portfolio: ["https://…"]
    media:                                # social URLs live here, not at top level
      linkedin: "https://…"
      github:   "https://…"
      facebook: "https://…"
      instagram: "https://…"
  messengers:
    whatsapp: "+380…"
    viber:    "+380…"
    telegram: "@handle"
expertise:                                # the skills source — no separate flat `skills` key
  - resume_title: "AI Engineering & Agentic Systems"
    skills: ["Generative AI application development", "…"]
key_achievements:                         # optional; Enhancv-style section
  - { title: "…", description: "…", icon: "🏆" }
languages:
  - { language: "English", proficiency: "…" }
professional_experience:
  - company: "…"
    position: "…"
    location: "…"
    duration: "…"
    company_description: "…"              # optional
    achievements: ["…", "…"]             # array of strings
independent_projects:                     # entries may be objects or strings
  - { name: "…", role: "…", duration: "…", description: "…" }
education:
  - { institution: "…", program: "…", location: "…", duration: "…" }
certifications:                           # optional; issuer-grouped
  - { issuer: "…", year: "…", credentials: ["…", "…"] }
```

- **Schema / owner:** the [`gmj-candidate-yaml-schema`](skills.md#gmj-candidate-yaml-schema)
  skill documents the full key set, nesting, and editing rules; `scripts/artifacts/gmj_schema_fields.py`
  is the single code owner of the field-name schema, and `scripts/artifacts/gmj_yaml_path.py`
  owns the dotted/indexed source-span grammar (`contact.email[0]`,
  `professional_experience[0].achievements[2]`) used to trace claims back to spans.
- **Consumers:** `gmj-artifact-composer` reads it (read-only) to compose artifacts;
  `gmj-truth-verifier` re-grounds every claim against it at Gate A; `gmj-cv-generator` renders
  it to PDF via `scripts/cv/gmj_render_cv.py`.

### config/candidate.ua.yaml, config/candidate.ru.yaml

**Prose-only language overlays** (Ukrainian, Russian). They carry only translatable fields and
are deep-merged over the English base at render time — non-translated fields (contact, URLs,
dates) are inherited from the base and must **not** be duplicated. The merge replaces list
sections **wholesale**, so any list an overlay provides must be a complete translation mirroring
the base structure exactly. `candidate.ru.yaml` today carries just `title` + `summary`:

```yaml
title: 'Інженер …'      # translatable fields only
summary: 'Інженер з практичним досвідом …'
```

- **Schema / owner:** same [`gmj-candidate-yaml-schema`](skills.md#gmj-candidate-yaml-schema)
  skill (see its "Multi-language overlay files" section); the deep-merge logic lives in
  `scripts/cv/gmj_render_cv.py`.
- **Consumer:** `scripts/cv/gmj_render_cv.py --lang ua|ru` merges the overlay before rendering.

### config/sources.yaml

The **board / geo / language allow-list** that hard-bounds all web search. Its arrays are the
only boards, cities, and languages the offer-search spoke may touch — it can never be widened at
runtime.

```yaml
sites:                    # allow-listed job-board URLs → derived allowed_domains
  - https://www.work.ua/
  - https://robota.ua/
cities:                   # geo scope appended to every query
  - Kyiv
languages:                # search + result languages
  - ua
  - ru
  - en
limits:
  max_vacancies: 10       # hard cap on vacancy files written this run
  max_search_queries: 6   # hard cap on WebSearch calls this run
  max_fetches: 8          # hard cap on WebFetch calls this run
```

- **Schema / owner:** prose contract in `rules/sources-scope.md`; the read-and-enforce protocol
  is documented in the
  [`gmj-sources-config-enforcement`](skills.md#gmj-sources-config-enforcement) skill.
- **Consumers:** `gmj-offer-scout` must read it before any search; the
  `gmj-sources-scope-guard.sh` hook enforces the host allow-list on every `WebFetch`/`WebSearch`.

### config/preferences.yaml

**Structured narrowing / ranking signals** for offer search. Every field only *narrows or ranks*
within `sources.yaml`; its `scope` block may only restrict the boards/geos/languages already
declared there — never widen them.

```yaml
salary: { min: 3000, currency: USD, period: month }
work_conditions: { mode: [remote, hybrid], relocation: false }
preferences: ["fully remote", "async team"]
search_keywords: [php, laravel, drupal]
ranking: { salary_weight: 0.4, remote_weight: 0.6 }
scope:                          # each list must be a SUBSET of sources.yaml
  sites: [https://robota.ua/]
  cities: [Kyiv]
  languages: [ua]
```

- **Schema / owner:** `schemas/preferences.schema.json` (`additionalProperties: false` root +
  leaves); `scripts/preferences/gmj_validate_preferences.py` enforces the jsonschema shape **and**
  the subset-of-`sources.yaml` invariant (fail-closed) and never writes `sources.yaml`.
- **Consumer:** read by the hub to narrow/rank; an optional `cover_letter_tone` hint is read by
  the hub only (never the composer).

### config/credentials.yaml

The **candidate credential-fetch allow-list** (INGEST-02) — hosts authorizing credential fetches
(profile pages, certificate / badge pages). It is **separate** from the job-board search scope in
`sources.yaml`: a host here is not thereby a permitted offer-search domain, and vice versa.

```yaml
credential_sites:
  - https://www.linkedin.com/
  - https://www.credly.com/
  - https://coursera.org/
```

- **Schema / owner:** inline header comment (no JSON Schema).
- **Consumer:** the `gmj-sources-scope-guard.sh` hook fetch-allows a `WebFetch` host that is on
  *either* this list or `sources.yaml`; hosts on neither stay blocked (exit 2). Each
  credential-list fetch is logged to `.claude/logs/credential-intake.log`.

### config/i18n/labels.yaml

**Section-label i18n** for CV rendering. Section headings ("Summary", "Experience", …) are not
stored in the candidate YAML — they live here, keyed by language (`en`, `ua`, `ru`). To add a
label, add it to all three blocks.

```yaml
en: { summary: "Summary", experience: "Experience", education: "Education", … }
ua: { summary: "Резюме", experience: "Досвід роботи", … }
ru: { summary: "Резюме", experience: "Опыт работы", … }
```

- **Schema / owner:** no JSON Schema — three parallel language blocks with matching keys.
- **Consumer:** `scripts/cv/gmj_render_cv.py` looks up labels by the render `--lang`.

### config/fit_thresholds.yaml

The **Gate B calibrated deliverable** (FIT-04). `coverage_threshold` is *derived* from the
labeled calibration fixtures under `tests/fixtures/fit/`, not adopted as a placeholder round
number, and is frozen before a run. The `weights` block feeds only an optional advisory composite
and never contributes to the coverage-only hard-block verdict.

```yaml
coverage_threshold: 0.7        # PRIMARY hard-block: covered_count / total_count >= this
weights:                       # SECONDARY advisory only; sum to 1.0
  coverage: 0.70
  keyword_alignment: 0.15
  language_match: 0.10
  seniority_scope_match: 0.05
```

- **Schema / owner:** inline header; the derivation record and Gate C rubric live in the
  [`gmj-fit-rubric`](skills.md#gmj-fit-rubric) skill.
- **Consumer:** `scripts/artifacts/gmj_score_fit.py` loads it via `yaml.safe_load` with an
  `isinstance` guard and computes the Gate B verdict.

### config/pipeline.config.yaml

Two **operator-authored knobs** (EXEC-01, GUARD-03) governing how a run executes.

```yaml
execution_mode: human_in_the_loop   # human_in_the_loop | autonomous
retry_cap: 2                        # max enhance/generate retry cycles per run
```

`execution_mode` gates only the post-PASS human pause (`autonomous` removes the human pause,
never the machine gate); `retry_cap` bounds the enhance/generate loop. **Freeze contract:** at run
start these values are copied into `.pipeline/runs/<run_id>/state.json`, and every downstream
control decision reads that frozen copy — a mid-run edit to this file cannot change an in-flight
run.

- **Schema / owner:** inline header; loaded via `yaml.safe_load` with an `isinstance` guard
  (`retry_cap` validated as an int excluding bool).
- **Consumer:** `scripts/pipeline/gmj_state_write.py` freezes the values into run state.

### config/pipeline.dag.yaml

The **fixed pipeline DAG** for the deterministic router (ARCH-06). It maps each step to its
successor; gate nodes branch on a *recorded verdict* in state, never on model reasoning.

```yaml
steps:
  gmj-offer-scout:      { next: gmj-artifact-composer }
  gmj-artifact-composer: { next: gmj-truth-verifier }
  gmj-truth-verifier:                       # gate node
    gate: true
    on_pass: gmj-fit-evaluator
    on_fail: gmj-artifact-composer
  gmj-fit-evaluator:                        # gate node
    gate: true
    on_pass: gmj-cv-generator
    on_fail: gmj-artifact-composer
  gmj-cv-generator:     { next: null }      # terminal node
```

- **Schema / owner:** inline header.
- **Consumer:** `scripts/pipeline/gmj_route.py` reads this DAG plus a state file and emits the
  next step as JSON — no `Task` call, no LLM. See [flows.md](flows.md) for the runtime loop.

### config/ownership-manifest.yaml

The **framework | app split** and the app `old → new` rename map (REBRAND-03). It classifies
every artifact as `framework` (GSD-owned, never touched) or `app` (the collective's own
agents/skills/commands/scripts/hooks, `gmj-`/`gmj_`-renamed). The `app` map is the single source
of truth consumed by the rename engine.

```yaml
version: 1
framework_globs: ["gsd-*", "**/gsd-core/**", …]
app:
  agents:   [{ old: <legacy-agent-name>,   new: gmj-orchestrator }, …]        # 8
  scripts:  [{ old: <legacy-script-stem>,  new: gmj_score_fit }, …]           # 23
  skills:   [{ old: <legacy-skill-name>,   new: gmj-fit-rubric }, …]          # 10
  commands: [{ old: <legacy-command-group>, new: gmj-pipeline }, …]           # 3 groups
  hooks:    [{ old: <legacy-hook-name>,    new: gmj-sources-scope-guard }, …] # 6
```

- **Schema / owner:** inline header; gated by `tests/test_ownership_manifest.py`.
- **Consumer:** `scripts/gmj_rebrand.py` (the manifest-gated `git mv` + reference-rewrite engine).

### config/cv/

Directory holding **derived, standalone skill-specific CV YAMLs** named
`cv.[skill].[lang].yaml` (e.g. `cv.fpv.ua.yaml`). They use the *exact same schema* as
`config/candidate.yaml` (no extra keys), are complete files (not overlays) carrying translated
prose directly, and are regenerated — never hand-edited. `lang` is inferred from the filename
suffix at render time.

- **Schema / owner:** the [`gmj-candidate-yaml-schema`](skills.md#gmj-candidate-yaml-schema)
  skill (see its "Skill-specific CV files" section).
- **Consumer:** rendered with
  `python3 scripts/cv/gmj_render_cv.py --config config/cv/cv.[skill].[lang].yaml`.

---

See also: [references.md](references.md) for the `schemas/*.json` envelope contracts and the
`agent_result_v1` output envelope; [rules.md](rules.md) for the invariants (`sources-scope.md`,
`truthfulness.md`) that several of these files enforce.
