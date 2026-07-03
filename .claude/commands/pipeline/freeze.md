# /pipeline/freeze — Step 2: freeze offer-spec + init run state

---
allowed-tools: Bash(*), Read(*), LS(*)
description: Freeze the offer draft into an immutable offer-spec and freeze mode/cap/run_id into run state (deterministic; no LLM).
---

## What this step names (thin wrapper — deterministic scripts only)

- **Freeze the offer** (immutable, hash-stamped):
  ```bash
  python3 scripts/offers/freeze_offer.py --file <fielded-offer-draft.json>
  # → offer-spec.json + offer_spec_hash
  ```
- **Init / freeze run facts** into run-scoped state (mode + cap + run_id, plus the frozen offer-spec path/hash):
  ```bash
  python3 scripts/pipeline/state_write.py \
    --state .pipeline/runs/<run_id>/state.json \
    --config config/pipeline.config.yaml \
    --execution-mode <human_in_the_loop|autonomous> \
    --retry-cap <int> --run-id <run_id> \
    --offer-spec-path <offer-spec.json> --offer-spec-hash <hash>
  ```

`execution_mode` + `retry_cap` are **frozen** here and read from state thereafter — a mid-run config edit cannot change an in-flight run. No spoke, no `Task`; pure deterministic control plane.
