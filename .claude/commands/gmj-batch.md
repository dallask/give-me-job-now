# /gmj-batch — Multi-select shortlist → per-offer gated artifact batch

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*), AskUserQuestion(*)
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

1. **Read the shortlist, display it ranked, then narrow via a bounded prompt.**
   `Read .pipeline/shortlist.json`. If it is absent, advise running a board-search first
   (`/gmj-pipeline/scout`, or the collective via `/gmj-collective`) to produce it — do not
   fabricate offers. The `shortlist` array is **already score-descending** at write time
   (`scripts/offers/gmj_merge_shortlists.py`'s `merge()` — do not re-sort, do not restate its
   sort logic in prose, per this doc's own "do not restate gate/cap logic" discipline below).
   Display it **in that array order** (array order IS the authoritative 1-indexed display
   order), rendering per entry: `title`, `company` (if present), `salary`, `mode` (work
   conditions), `score` (SELECT-05).

   - **Human-in-the-loop mode:** present a bounded **`AskUserQuestion`** offering `top-3` /
     `top-5` / `all` / `custom indices` as the narrowing options (SELECT-06). Map the answer to
     Step 2's `gmj_batch.py init --select` value: `top-3` -> `top3`, `top-5` -> `top5`, `all` ->
     `all`, `custom indices` -> the user's raw string passed straight through unchanged. The
     persona forwards the `top{N}` sentinel itself — it does **not** compute a raw index string
     (e.g. `"1,2,3"`) for `top-3`/`top-5`. `gmj_batch.py`'s `_expand_top3_selection()` clamps to
     `min(N, len(shortlist))` at script level before calling `resolve_selection()`; a
     hub-computed `"1,2,3"` against a 2-entry shortlist would hit `resolve_selection()`'s own
     out-of-range error instead of degrading gracefully. The persona never re-derives these
     indices itself and never re-sorts by score itself — both are the deterministic scripts'
     job, per this doc's own "Bash drives every safety decision" framing below.
   - **Autonomous mode:** skip the `AskUserQuestion` prompt entirely (no human present to ask)
     and call `gmj_batch.py init --select top3` directly — the underlying
     selection-resolution machinery (`resolve_selection()` plus the `top{N}` expansion) is
     identical in both modes; only whether the human prompt fires differs.

2. **Init the batch.**
   `Bash: python3 scripts/pipeline/gmj_batch.py init --shortlist .pipeline/shortlist.json --select "<sel>" [--execution-mode <mode>] [--max-parallel-offers N]`.
   `--max-parallel-offers N` overrides the `max_parallel_offers` default (3) from
   `config/pipeline.config.yaml`; frozen into the batch's manifest at `init` time, same moment
   `--execution-mode`/`--retry-cap` freeze today. Read the printed `batch_id` and the per-offer lines
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

4. **Bounded greedy-refill dispatch across offers, scoped to each offer's run_ids.** After
   `init`, repeatedly ask `scripts/pipeline/gmj_dispatch_cap.py --batch <batch_id>` (via `Bash`)
   how many offers may start/continue right now — bounded by the batch's frozen
   `max_parallel_offers` — then dispatch up to that many offers' next pipeline steps as
   parallel `Task` calls in the SAME hub turn. The per-offer pipeline loop itself — for
   **each** artifact type (`cv` / `cover_letter` / `interview_prep`) run the
   `gmj-orchestrator` loop verbatim: `gmj_route.py` (next step) → `gmj_check_offer.py` before
   each dispatch → `Task(<spoke>)` → on a gate node: `gmj_check_truth.py` (Gate A) →
   `gmj_record_gate.py` → `gmj_score_fit.py` (Gate B) → `gmj_record_gate.py` → on FAIL:
   `gmj_record_retry.py --increment` → `gmj_check_cap.py` (below-cap → `gmj_map_feedback.py` →
   `Task(gmj-artifact-composer)` recompose; at-cap → **HARD STOP** naming the failing artifact
   + the last gate's reason) → `gmj_check_delivery.py` (Gate A ∧ Gate B recorded pass) →
   `Task(gmj-cv-generator)` render — stays **completely unchanged** and runs once per offer per
   artifact type, exactly as documented above. Consult `execution_mode` ONLY for the post-PASS
   human pause; both gates block identically in every mode. Mark each terminal completion via
   `gmj_batch.py mark` (step 5 below), then immediately re-ask `gmj_dispatch_cap.py` to top
   back up to the cap (greedy refill) until every offer's 3 runs reach a terminal status.

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

- **`select`** — the offer selection: `1,3,5` (1-indexed, comma-separated), `all`, or `top{N}`
  (e.g. `top3`, `top5` — the first N by score, clamped to the shortlist's actual length at
  script level). Passed to `gmj_batch.py init --select`.
- **`mode`** — `human_in_the_loop` | `autonomous`. Overrides the `execution_mode` default;
  frozen into each run state at `init` (a mid-run config edit cannot change an in-flight
  run). `mode` gates ONLY the post-PASS human pause, never the machine gate. `mode ==
  autonomous` also skips the Step-1 `AskUserQuestion` picker and calls `gmj_batch.py init
  --select top3` directly; the underlying selection-resolution machinery
  (`resolve_selection()`) and its output shape are identical in both modes — only the human
  prompt differs.
- **`--max-parallel-offers`** — overrides the `max_parallel_offers` default (3) from
  `config/pipeline.config.yaml`; frozen into the batch's manifest at `init` (a mid-batch
  config edit cannot change an in-flight batch). Bounds how many offers' pipelines may be
  concurrently in flight at once — `gmj_dispatch_cap.py` reads this frozen value.
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
