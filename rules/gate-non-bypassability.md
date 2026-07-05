---
scope:
  keywords:
    - gate
    - Gate A
    - Gate B
    - non-bypassable
    - autonomous
    - retry-cap
    - quality-gate
  agent-names:
    - gmj-orchestrator
    - gmj-truth-verifier
    - gmj-fit-evaluator
---

# Invariant: Gate non-bypassability

The hard quality gates are machine gates that cannot be turned off.

- **Gate A (truth)** and **Gate B (target-fit)** are non-bypassable in **any** mode.
- **Autonomous mode removes the human pause, never the machine gate.** Running unattended changes
  who approves, not whether the gate runs.
- Auto-loops (enhance/generate cycles) are **retry-capped**; after the cap is hit, halt and surface
  to the user rather than looping unbounded or forcing a pass.
