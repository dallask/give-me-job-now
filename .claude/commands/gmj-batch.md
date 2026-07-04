# /gmj-batch — Multi-select shortlist → per-offer gated artifact batch

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Select several shortlisted offers; freeze + run each as its own gated pipeline under a resumable batch manifest.
---

## What to do

You are the **top-level hub persona** for a multi-offer batch. You read the shortlist,
prompt the user to pick several offers, and drive the **EXISTING single-offer pipeline
loop once per selected offer** — the same `gmj_route.py → gmj_check_offer.py → Task(spoke) →
gates → deliver` loop documented in `.claude/agents/gmj-orchestrator.md`, only wrapped
per offer under a resumable batch manifest. The deterministic engine
`scripts/pipeline/gmj_batch.py` does the **deciding** (selection resolve, manifest CRUD,
resume-set recompute); you do the **dispatching**.

### Hub at top level — never nest the hub (Pitfall 4)

**Hub runs here (top level):** Follow the `gmj-orchestrator` control loop **in this
chat session** — you are the hub. Use **`Task`** only to spawn **spokes** (`gmj-offer-scout`,
`gmj-artifact-composer`, `gmj-truth-verifier`, `gmj-fit-evaluator`, `gmj-cv-generator`). **Never** call
`Task` with `subagent_type: gmj-orchestrator`. Nesting the hub inside `Task` removes
`Task` from that context ("Task is not available inside subagents"), which breaks the whole
pipeline (Pitfall 4). `scripts/pipeline/gmj_batch.py` is invoked via **`Bash`** and holds
**no** `Task` — it is pure files + stdout; the persona is the only `Task`-holder.

### Bash drives every safety decision

Drive the deterministic control plane via **`Bash`** for every safety decision — the hub
never judges a gate, a cap, freeze integrity, or delivery. `gmj_batch.py` (the batch
engine) and the per-run scripts (`gmj_route.py`, `gmj_check_offer.py`, `gmj_check_truth.py`,
`gmj_score_fit.py`, `gmj_record_gate.py`, `gmj_record_retry.py`, `gmj_check_cap.py`, `gmj_map_feedback.py`,
`gmj_check_delivery.py`) own those verdicts. **Do NOT restate or reimplement gate / cap /
freeze / route logic in prose** beyond naming the existing scripts; the persona
orchestrates, it never re-judges a gate.

## Batch loop

1. **Read the shortlist.** `Read .pipeline/shortlist.json`. If it is absent, advise running
   a board-search first (`/pipeline/scout`, or the collective via `/job-collective`) to
   produce it — do not fabricate offers. Display the ranked list **in `shortlist` array
   order** (that array order IS the authoritative 1-indexed display order) and prompt for a
   selection: **`1,3,5` | `all`**.

2. **Init the batch.**
   `Bash: python3 scripts/pipeline/gmj_batch.py init --shortlist .pipeline/shortlist.json --select "<sel>" [--execution-mode <mode>]`.
   Read the printed `batch_id` and the per-offer lines
   `offer_index=<i> run_id=<base_run_id> thin=<true|false>`. `init` is the single producer
   of the manifest and of the **three** seeded per-(offer, artifact_type) `state.json` files
   per offer (`<base_run_id>-cv` / `-cl` / `-ip`), each already frozen with mode/cap/run_id
   and seeded `current_step: gmj-artifact-composer`. **Do NOT re-init those states.**

3. **Per offer: re-field (if thin) → freeze → stamp.**
   - **`thin: true` → `Task(gmj-offer-scout)` single-offer re-field (the PRIMARY freeze
     source, SELECT-02).** The coarse shortlist entry carries no Gate-B fields
     (`must_haves` / `nice_to_haves` / `responsibilities` / `employment_type` /
     `raw_text_excerpt`), so a thin offer MUST be re-fielded before freeze. Dispatch
     `gmj-offer-scout` **single-offer intake seeded/scoped by that shortlist entry's
     `trace.source_url` + title/company** (NOT a fresh board search) to produce a
     gate-quality fielded offer draft. If `thin: false`, use the coarse seed draft that
     `init` already wrote under `.pipeline/batches/<batch_id>/drafts/offer-<i>.draft.json`.
   - **Freeze:** `Bash: python3 scripts/offers/gmj_freeze_offer.py --file <draft-path>` →
     prints the immutable, hash-stamped offer-spec path; read the `offer_spec_hash` from
     that written offer-spec file.
   - **Stamp the manifest:**
     `Bash: python3 scripts/pipeline/gmj_batch.py record-spec --batch <batch_id> --offer-index <i> --offer-spec-path <path> --offer-spec-hash <hash>`
     — writes the real freeze values into the manifest offer entry (replacing the empty
     init placeholders Phase 16 inspects).
   - **Record the hash into each per-type state:** for **each** of that offer's three
     per-(offer, artifact_type) run_ids (`<base_run_id>-cv` / `-cl` / `-ip`):
     `Bash: python3 scripts/pipeline/gmj_state_write.py --state .pipeline/runs/<per_type_run_id>/state.json --offer-spec-path <path> --offer-spec-hash <hash>`
     so `gmj_check_offer.py` can integrity-check that per-type run against the frozen spec.
     `init` already froze mode/cap/run_id + seeded `current_step` into all three — record
     ONLY the offer-spec here; do not re-init.

4. **Per offer, SEQUENTIALLY, run the UNCHANGED per-offer pipeline loop** (single-threaded
   default; parallel deferred) scoped to that offer's run_ids. For **each** artifact type
   (`cv` / `cover_letter` / `interview_prep`) run the `gmj-orchestrator` loop verbatim:
   `gmj_route.py` (next step) → `gmj_check_offer.py` before each dispatch → `Task(<spoke>)` →
   on a gate node: `gmj_check_truth.py` (Gate A) → `gmj_record_gate.py` → `gmj_score_fit.py` (Gate B) →
   `gmj_record_gate.py` → on FAIL: `gmj_record_retry.py --increment` → `gmj_check_cap.py`
   (below-cap → `gmj_map_feedback.py` → `Task(gmj-artifact-composer)` recompose; at-cap → **HARD
   STOP** naming the failing artifact + the last gate's reason) → `gmj_check_delivery.py`
   (Gate A ∧ Gate B recorded pass) → `Task(gmj-cv-generator)` render. Consult `execution_mode`
   ONLY for the post-PASS human pause; both gates block identically in every mode.

5. **Mark delivered.** After a per-artifact-type run's `gmj_check_delivery.py` passes and it
   renders:
   `Bash: python3 scripts/pipeline/gmj_batch.py mark --batch <batch_id> --run-id <per_type_run_id> --status delivered`.

## Per-(offer, artifact_type) gate isolation — never batched

**Load-bearing invariant:** there is exactly **one `state.json` per `run_id`**, and Gate A
∧ Gate B are recorded **per-(offer, artifact_type)** — never a shared `gate_results` across
offers or across artifact types. Each of the three artifact types per offer keeps its own
recorded Gate A ∧ Gate B verdict in its own run state; a PASS on one artifact type never
satisfies delivery for another, and one offer's verdict never masks another offer's. A
batched or shared gate would clobber `state.gate_results` across the three DAG runs
(Pitfall 3 / T-12-02) — do not batch gates.

## Resume

`/gmj-batch --resume <batch_id>` resumes a crashed or paused batch. When `<batch_id>` is
**omitted**, auto-detect the **latest** batch under `.pipeline/batches/` (newest
`manifest.json`). Then:

`Bash: python3 scripts/pipeline/gmj_batch.py resume --batch <batch_id>` → prints one line
per **non-delivered** run (`offer_index=<i> artifact_type=<key> run_id=<rid>`), or
`nothing to resume` when all delivered. Delivery is recomputed from the **recorded Gate A ∧
Gate B verdict alone** (`check_delivery` predicate) — never the manifest `status` label,
never a rendered-PDF path. Loop **ONLY** the returned non-delivered runs back through steps
3–5 (offers already frozen keep their stamped offer-spec; already-delivered runs are
skipped).

## Parameters

- **`select`** — the offer selection: `1,3,5` (1-indexed, comma-separated) or `all`. Passed
  to `gmj_batch.py init --select`.
- **`mode`** — `human_in_the_loop` | `autonomous`. Overrides the `execution_mode` default;
  frozen into each run state at `init` (a mid-run config edit cannot change an in-flight
  run). `mode` gates ONLY the post-PASS human pause, never the machine gate.
- **`--resume <batch_id>`** — resume an existing batch (explicit); auto-detect the latest
  batch under `.pipeline/batches/` when the id is omitted.

## CLI-only invocation

```bash
claude --dangerously-skip-permissions
# then, in the session:
/gmj-batch            # then state your selection (1,3,5 | all) and mode
/gmj-batch --resume   # resume the latest batch (or pass an explicit <batch_id>)
```

There is no UI — the batch runs entirely from the CLI.
