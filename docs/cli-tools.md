# CLI tools — the deterministic script surface

> **Every script named here resolves to a real file under `scripts/`.**
> `python3 tests/test_docs_current.py` (`test_every_docs_script_exists`) fails the build if any
> `gmj_*.py` token drifts from disk. This page is the reader-facing catalog of *what each script
> does* (purpose = the script's own module docstring, line 1) and *how the scripts group together*.

The collective is a **two-layer control plane**. The lower layer is a set of **34 small,
single-purpose Python CLI tools** (`scripts/**/gmj_*.py`): each is deterministic, makes exactly one
decision, exits `0` on success / `1` on failure, and touches **no LLM and no network**. The upper
layer — the LLM hub [`gmj-orchestrator`](agents.md) — never decides whether a gate passed, whether
the retry cap is hit, or whether an artifact is deliverable; it shells out to these scripts via
`Bash` and obeys their exit codes. Every safety decision in the pipeline is one of the scripts below.

> **Count discipline.** This catalog enumerates the **disk set of 34** (`scripts/**/gmj_*.py`),
> not the `config/ownership-manifest.yaml` rename map (which lists only the 23 scripts that were
> renamed during the rebrand). Ten scripts — `gmj_build_payload.py`, `gmj_rebrand.py`,
> `gmj_remove_gsd.py`, `gmj_batch.py`, `gmj_runs.py`, `gmj_merge_shortlists.py`,
> `gmj_check_claims.py`, `gmj_dashboard.py`, `gmj_dashboard_model.py`, `gmj_dashboard_actions.py` —
> were authored natively `gmj_`-prefixed and are not part of that rename map.

See [flows.md](flows.md) for the end-to-end sequences these scripts drive,
[references.md](references.md) for the JSON envelope schemas they read and emit, and
[commands.md](commands.md) for the slash commands that shell out to them.

The **31 runtime tools** below are grouped by directory; the **3 build/packaging tools** live in a
separate [Packaging & maintenance](#packaging--maintenance) section at the end because they are
one-off maintenance utilities, not steps a user runs during a pipeline.

---

## Runtime CLI tools (31)

### `scripts/artifacts/` (6)

Provenance, truth, fit, and the single-owner schema/span grammars for composed artifacts.

| Script | Purpose |
|--------|---------|
| `gmj_check_claims.py` | Executed provenance gate for a composed artifact draft (COMPOSE-03). |
| `gmj_check_truth.py` | Deterministic Gate-A pre-gate + `gate_result` emitter (TRUTH-01/03/04). |
| `gmj_record_retry.py` | Record a per-(offer-slug, artifact_type) retry counter into the pipeline state (COMPOSE-02). |
| `gmj_schema_fields.py` | Single owner of the `candidate.yaml` field-name schema (SCHEMA-06). |
| `gmj_score_fit.py` | Deterministic Gate-B (target-fit) scorer + `gate_result` emitter (FIT-01/02/03/05). |
| `gmj_yaml_path.py` | Single owner of the `candidate.yaml` dotted/indexed source-span grammar (COMPOSE-03). |

### `scripts/contracts/` (2)

Content-integrity hashing and envelope validation — the cross-cutting contract layer.

| Script | Purpose |
|--------|---------|
| `gmj_hash_artifact.py` | Compute content-integrity fingerprints (`offer_spec_hash` / `claims_hash`) — ARCH-05. |
| `gmj_validate_envelope.py` | Validate an `agent_result_v1` envelope against its per-kind JSON Schema. |

### `scripts/dashboard/` (3)

The read-only (opt-in `--manage`) btop-style Textual dashboard over pipeline run/batch state.

| Script | Purpose |
|--------|---------|
| `gmj_dashboard.py` | Read-only, btop-style Textual dashboard over `DashboardModel.snapshot()` (Phase 20). |
| `gmj_dashboard_model.py` | Headless dashboard read model — the single-sourced, torn-read-tolerant projection layer. |
| `gmj_dashboard_actions.py` | Dashboard action layer — the SOLE mutating / subprocess-launching module in `scripts/dashboard/`. |

### `scripts/cv/` (7)

Extraction, rendering, and the branded-template loop that turn approved drafts into deliverables.

| Script | Purpose |
|--------|---------|
| `gmj_draft_to_cv_yaml.py` | Span-driven bridge: reconstruct an approved `artifact_draft` into CV-YAML (E2E-02). |
| `gmj_extract.py` | Extract text (and light structure) from common candidate source files. |
| `gmj_render_cover_letter.py` | Render an approved cover_letter `artifact_draft` to a PDF via ReportLab. |
| `gmj_render_cv.py` | Render candidate YAML to PDF using ReportLab; optional Jinja2 HTML template via WeasyPrint if installed. |
| `gmj_render_interview_prep.py` | Emit an approved interview_prep `artifact_draft` as an ordered markdown document. |
| `gmj_template_lint.py` | Fail-closed zero-sample-strings gate for generated CV templates (TEMPLATE-02). |
| `gmj_visual_diff.py` | Deterministic visual-diff for a candidate CV template (TEMPLATE-03 / TEMPLATE-04). |

### `scripts/offers/` (3)

Freeze, tamper-check, and deterministically merge the offers discovered by the scout.

| Script | Purpose |
|--------|---------|
| `gmj_check_offer.py` | Re-check a frozen offer-spec for tampering by recompute-and-compare (INTAKE-02, INTAKE-03). |
| `gmj_freeze_offer.py` | Freeze a fielded offer draft into an immutable `offer-spec.json` (INTAKE-01, INTAKE-03). |
| `gmj_merge_shortlists.py` | Deterministic, LLM-free merge authority for parallel multi-board [`gmj-offer-scout`](agents.md) (SCOUT-02/04). |

### `scripts/pipeline/` (8)

The routing, gate-recording, cap, feedback, delivery-guard, and run-state control plane.

| Script | Purpose |
|--------|---------|
| `gmj_batch.py` | Deterministic per-offer batch control-plane CLI (SELECT-01, SELECT-02, SELECT-03). |
| `gmj_check_cap.py` | Honest hard-stop at the FROZEN retry cap (EXEC-03). |
| `gmj_check_delivery.py` | Gated delivery precondition — Gate A ∧ Gate B recorded pass (GUARD-03). |
| `gmj_map_feedback.py` | Pure `gate_result` → `gate_feedback` projection (GUARD-04). |
| `gmj_record_gate.py` | Record a gate's verdict as BOTH an audit artifact and routing state (GUARD-03). |
| `gmj_route.py` | Deterministic pipeline router (ARCH-06). |
| `gmj_runs.py` | Read-only run/batch inspector — the mirror image of the writer `gmj_batch.py` (ERGO-01..04). |
| `gmj_state_write.py` | Record frozen run facts into the pipeline state file (INTAKE-02, EXEC-01, GUARD-03). |

### `scripts/preferences/` (1)

Validates that offer-search preferences only ever narrow the source allow-list.

| Script | Purpose |
|--------|---------|
| `gmj_validate_preferences.py` | Validate `config/preferences.yaml`: shape (jsonschema) + subset-of-`sources.yaml` (Python). |

### `scripts/testing/` (1)

Feeds human UAT results back into the planning docs.

| Script | Purpose |
|--------|---------|
| `gmj_record_uat.py` | Record a human-testing UAT result and feed it back into the planning docs. |

---

## Packaging & maintenance

> **Not runtime steps.** These three tools build and maintain the standalone distribution. A user
> running the offer→artifacts pipeline never invokes them; they are enumerated here only so the
> catalog covers the full on-disk `scripts/**/gmj_*.py` set (and so the doc-test resolves them).

### `scripts/` root (3)

| Script | Purpose |
|--------|---------|
| `gmj_build_payload.py` | Build the standalone `gmj-core/` install payload (PACKAGE-01). |
| `gmj_rebrand.py` | Manifest-gated dry-run/apply rename+rewrite engine for the gmj rebrand (REBRAND-01/02/03). |
| `gmj_remove_gsd.py` | Dry-run / report-only GSD-framework-trace reporter (PACKAGE-03 + PACKAGE-04). |

The rebrand and GSD-removal tools are gated by `config/ownership-manifest.yaml` (the
framework-vs-app allow-list) and never operate outside it; `gmj_remove_gsd.py` is report-only and is
not executed during this milestone. See [requirements.md](requirements.md) for the REBRAND and
PACKAGE requirement families these tools realize.
