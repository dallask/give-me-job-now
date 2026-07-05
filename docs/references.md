# References — Contracts, Schemas & Envelopes

The give-me-job collective exchanges **typed file artifacts**, never transcripts. Every
hop between the hub (`gmj-orchestrator`) and a spoke is a JSON envelope validated against a
versioned schema under `schemas/`. This page is the reference for those contracts: the
shared `agent_result_v1` envelope, the eight JSON Schemas, and the documentation-currency
convention that keeps this reference honest.

See also: [configuration.md](configuration.md) for the `config/*` file shapes, and
[cli-tools.md](cli-tools.md) for the deterministic scripts that read and write these
envelopes.

---

## The `agent_result_v1` envelope

Every spoke emits the same base envelope so the hub can parse status, artifacts, and
handoff uniformly. The canonical field set lives in
`schemas/agent_result_v1.schema.json` and is mirrored by the
[`gmj-agent-output-contract`](skills.md) skill (the human-authored copy each spoke follows).
Per-kind schemas `$ref` this base rather than redefining it, so existing emitters stay
valid (the contract is back-compat locked).

Envelope fields:

```json
{
  "schema": "agent_result_v1",
  "schema_version": "1.0.0",
  "agent": "gmj-offer-scout",
  "pipeline_run_id": "",
  "status": "success",
  "artifacts": [
    { "type": "file", "path": "/abs/path/to/artifact.json" }
  ],
  "acceptance_criteria_met": [],
  "acceptance_criteria_failed": [],
  "next_action": "none",
  "handoff_target": null,
  "notes": "One-line key outcome, counts, or handoff reason."
}
```

- **`schema`** — always the literal string `"agent_result_v1"`. **Required.**
- **`status`** — one of `success`, `fail`, `gap_report_ready`, `handoff`. **Required.**
- **`schema_version`** — locked contract version string (e.g. `"1.0.0"`) for
  forward-compatible evolution.
- **`agent`** — exact agent name (the `.md` filename without extension).
- **`pipeline_run_id`** — run id copied verbatim from the orchestrator prompt, or empty
  string if absent.
- **`artifacts`** — array of `{ "type", "path" }` objects; each is one file or section the
  spoke wrote or confirmed. `path` is absolute.
- **`acceptance_criteria_met` / `acceptance_criteria_failed`** — string arrays of criterion
  ids.
- **`next_action`** — one of `none`, `retry`, `await_user_approval`, `handoff`.
- **`handoff_target`** — `null` unless `status` is `handoff`; then the name of the next
  agent.
- **`notes`** — one-line key outcome, counts, or handoff reason.

Emitted envelopes are validated at runtime by the `gmj-validate-envelope.sh` hook against
`scripts/contracts/gmj_validate_envelope.py`.

---

## JSON Schemas (`schemas/*.json`)

Eight versioned schemas define every typed payload. Each uses a local `urn:` `$id` (never a
fetchable URL — an SSRF-hardening precedent), and the per-kind schemas reuse the shared
envelope via `$ref`.

| Schema | What it validates |
|--------|-------------------|
| `agent_result_v1.schema.json` | Shared base envelope field set for every spoke; per-kind schemas `$ref` it. |
| `artifact_draft.schema.json` | A draft application artifact (CV / cover letter / interview-prep) from `gmj-artifact-composer`. |
| `gate_result.schema.json` | A quality-gate verdict from `gmj-truth-verifier` (Gate A) or `gmj-fit-evaluator` (Gate B/C). |
| `gate_feedback.schema.json` | Structured-only composer-retry feedback projected from a `gate_result`. |
| `offer_spec.schema.json` | A normalized, hash-stamped job offer from `gmj-offer-scout`. |
| `preferences.schema.json` | The shape of `config/preferences.yaml` — narrow/rank-only search signals. |
| `shortlist.schema.json` | The deterministic, scope-filtered offer shortlist. |
| `batch_manifest.schema.json` | The per-offer batch manifest for a multi-offer run. |

### `agent_result_v1.schema.json`

The shared base (documented above). Defines two `$defs`: `artifact` (`{ type, path }`) and
`envelope` (the common fields). Payload objects stay `additionalProperties`-permissive so
per-kind schemas and later phases can extend without breaking the contract.

### `artifact_draft.schema.json`

A draft artifact emitted by `gmj-artifact-composer`, pinning `kind: "artifact_draft"` and
`schema_version: "1.0"`. Its `content` carries a provenance-tagged `claims` array,
discriminated by `artifact_type`:

```json
{
  "artifact_type": "cv",
  "language": "en",
  "claims": [
    {
      "text": "Led migration of the billing service",
      "source_span": "professional_experience[2].achievements[0]",
      "section": "experience",
      "reframing_note": "emphasis only — no new scope"
    }
  ]
}
```

- **`artifact_type`** — one of `cv`, `cover_letter`, `interview_prep`.
- **`language`** — one of `ua`, `ru`, `en` (the offer's single target language).
- **`claims[]`** — each claim requires `text`, `source_span` (a dotted/indexed
  `candidate.yaml` path), and `section`; `reframing_note` is optional. `source_span` is what
  makes every claim traceable back to the single source of truth.

### `gate_result.schema.json`

A gate verdict, pinning `kind: "gate_result"`. Its `content` is a `oneOf` over three gate
bodies:

- **Gate A (truth)** — `verdict` (`pass` / `fail`) plus `offending_claims[]`, each naming a
  `claim_index`, a `rule_violated` (`unresolved_span`, `scope_inflation`,
  `numeric_invention`, `cross_entry_merge`), and the `offending_span`.
- **Gate B (target-fit)** — coverage-gated `verdict`, a `coverage` block
  (`covered_ids`, `missing_ids`, `score` 0–1), and advisory sub-scores
  (`keyword_alignment`, `language_match`, `seniority_scope_match`) with a structured `why`.
- **Gate C (polish)** — advisory only (`advisory: true`, no `verdict`); five 0–5 `polish`
  dimensions: `clarity`, `concision`, `formatting`, `quantified_impact`,
  `natural_keywords`.

### `gate_feedback.schema.json`

The structured-only retry feedback projected from a `gate_result` by
`gmj_map_feedback.py`. It is `additionalProperties: false` so no evaluator prose, transcript,
or gate stdout can leak back into a re-compose:

```json
{
  "gate": "A",
  "missing_must_haves": [],
  "fabricated_claims": [
    { "claims_index": 3, "source_span": "skills[7]", "reason": "no matching source span" }
  ]
}
```

- **`gate`** — `A` or `B`.
- **`missing_must_haves`** — plain string array (Gate B coverage gaps).
- **`fabricated_claims[]`** — each carries `claims_index`, `source_span`, and a deterministic
  `reason` sentence.

### `offer_spec.schema.json`

A normalized job offer from `gmj-offer-scout`, pinning `kind: "offer_spec"`. The fielded
`content` requires `title`, `company`, `location`, `seniority`
(`intern`…`principal`), `employment_type`, `language`, `must_haves[]`, `nice_to_haves[]`,
`responsibilities[]`, `source_url`, and `raw_text_excerpt`. A sibling `offer_spec_hash`
carries the canonical SHA-256 over the frozen content subset (computed by
`gmj_hash_artifact.py`) — this is the freeze anchor the pipeline re-checks before every
dispatch.

### `preferences.schema.json`

The shape of `config/preferences.yaml`: `salary`, `work_conditions`, `preferences[]`,
`search_keywords[]`, `ranking`, `cover_letter_tone`, and a `scope` block (`sites`, `cities`,
`languages`). It is `additionalProperties: false` at the root **and** on every leaf so a
misspelled key is rejected. Every field only **narrows or ranks** within
`config/sources.yaml` — the subset invariant (which JSON Schema cannot express across files)
is enforced at runtime by `gmj_validate_preferences.py`.

### `shortlist.schema.json`

The deterministic offer shortlist (`kind: "offer_shortlist"`). Each entry pins exactly four
contract keys — `canonical_key`, `board`, `score`, and `trace` (which must carry at least
`source_url`) — and keeps `additionalProperties: true` so coarse fielded fields survive for a
later freeze without re-fetching.

### `batch_manifest.schema.json`

The per-offer batch manifest (`kind: "batch_manifest"`) written by `gmj_batch.py`. It is
offer-centric: each `offers[]` entry groups its per-`(offer, artifact_type)` runs under
`runs` (`cv`, `cover_letter`, `interview_prep`), each with its own `run_id` and `status`
(`pending`, `running`, `delivered`, `failed`), so Gate A ∧ Gate B are recorded independently
and never clobber across artifact types.

Sample instances for these schemas live under `schemas/samples/`.

---

## Related operator references

- **[docs/RUNBOOK.md](RUNBOOK.md)** — the end-to-end operator guide for running the
  collective against a real, current offer via `/gmj-pipeline-run` (setup, control loop,
  outputs, audit trail).
- **[docs/HUMAN-TESTING-PLAN.md](HUMAN-TESTING-PLAN.md)** — the behavioral-acceptance plan
  for the LLM-in-loop and live-run items that a human closes.

---

## Documentation currency (DOCS-04)

This reference — like every file under `docs/` and the root `README.md` — is a **milestone
deliverable**, not a write-once artifact. The convention is captured as a Read-on-demand
invariant in [rules/docs-currency.md](../rules/docs-currency.md):

- Before finalizing any milestone, the `docs/` set and the root `README.md` are refreshed to
  describe the shipped system **as-is** — no stale agent names, paths, flows, or removed
  features.
- The refresh is re-verified by a machine gate: `python3 tests/test_docs_current.py` must
  exit `0`. It mines every `gmj-` agent / `/gmj-` command / `gmj_*.py` script / skill / hook
  token named in the docs and asserts each resolves to a real file on disk, that no
  superseded roster name is presented as current, and that every root-README link resolves
  inside the repo.
- When the gate reports a doc/code mismatch, the **doc** is corrected to match the code —
  behavior is never invented to satisfy a doc.

See [rules.md](rules.md) for the full Read-on-demand rules index.
