# /pipeline/scout — Step 1: discover + rank offers within scope

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*), Bash(*)
description: Run the gmj-offer-scout spoke (board-search or single-offer), scoped by config/sources.yaml, then hand to /pipeline/freeze.
---

## What this step names (thin wrapper — no control logic here)

- **Spoke:** `Task(subagent_type: gmj-offer-scout)` — board-search (rank N offers) or single-offer intake.
  `gmj-offer-scout` **must** read `config/sources.yaml` (the board/geo/language allow-list) before any web search; it may never search outside that scope.
- **Next:** hand the chosen offer to **`/pipeline/freeze`**, which freezes it into an immutable `offer-spec.json`.

Emits an `offer_spec` draft (file artifact). Ranking N offers is parallel `Task` fan-out; the gated steps that follow run sequentially. The hub (`/pipeline-run`) owns dispatch — this command just names the spoke + `sources.yaml` scope.
