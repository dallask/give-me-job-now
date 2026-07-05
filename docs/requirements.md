# Requirements — the v2.0 milestone inventory

> **Canonical source: [`.planning/REQUIREMENTS.md`](../.planning/REQUIREMENTS.md).**
> That file holds the authoritative requirement text, per-item checkboxes, and the phase
> traceability table (52/52 mapped, Phases 9–19). This page is the reader-facing summary: it
> groups the milestone's requirements into families, gives each a one-line description, and names
> **where each is realized** (agent / script / schema / config). When this page disagrees with
> `.planning/REQUIREMENTS.md`, that file wins.

Milestone **v2.0 — "Standalone gmj Collective"** hardens the collective against the classic
multi-agent failure modes (fabricated facts, off-target drift, context bloat, silent quality decay)
and packages it as a standalone, installable distribution. Its **core value**: given a real job
offer, the system produces truthful, offer-optimized application artifacts that provably trace back
to the candidate's real profile and pass mandatory quality gates.

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

Full per-requirement text and the phase-by-phase traceability table live in
[`.planning/REQUIREMENTS.md`](../.planning/REQUIREMENTS.md).

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

These tags are internal implementation anchors; the milestone-level families in the table above —
and their canonical text in [`.planning/REQUIREMENTS.md`](../.planning/REQUIREMENTS.md) — remain the
authoritative acceptance inventory.
