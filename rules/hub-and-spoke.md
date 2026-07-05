---
scope:
  keywords:
    - hub-and-spoke
    - orchestrator
    - Task
    - spawn
    - delegation
    - routing
  agent-names:
    - gmj-orchestrator
---

# Invariant: Hub-and-spoke (only the hub holds Task)

The architecture is hub-and-spoke only, and it must stay that way.

- **Only the hub** (`gmj-orchestrator`, run at top level) may call `Task` to spawn spokes.
- **Spokes never spawn spokes.** Nested `Task` contexts do not receive the `Task` tool, so a
  nested hub loses the ability to delegate — the pipeline silently stalls. Never `Task`-spawn the
  orchestrator itself.
- Routing is mandatory: **User Request → Routing Analysis → Agent Selection → Task Delegation →
  Quality Gate → Result.** This preserves criteria/cycle tracking and prevents chain drift.
