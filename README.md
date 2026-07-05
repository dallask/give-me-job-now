# give-me-job — Autonomous Job/CV Collective

**give-me-job** is a standalone hub-and-spoke collective of specialized Claude Code agents,
commands, skills, and Python scripts that, given a real job offer, autonomously produces a
**truthful, offer-optimized** set of application artifacts — a CV (PDF), a cover letter, and an
interview-prep document — for one candidate.

## Core value

Given a real offer, the system produces application artifacts that **provably trace back to the
candidate's real profile** (`config/candidate.yaml`) and **pass mandatory quality gates**. If
everything else fails, the artifacts must never fabricate and must actually target the offer.
Reframing and emphasis are allowed; invention is hard-blocked.

## Hub-and-spoke model

A single top-level orchestrator, **`gmj-orchestrator`**, is the only role that holds `Task` and
delegates to spokes. Spokes never spawn spokes (nested hubs lose `Task` in Claude Code), so
routing stays a clean **User Request → Routing → Agent Selection → Task Delegation → Quality
Gate → Result** loop. This topology preserves criteria tracking and prevents chain drift.

For the authoritative roster and data flow, see
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the source of truth for the hub + 5-spoke
roster, per-spoke boundaries, and the offer→render pipeline.

## Truthfulness guarantee

`config/candidate.yaml` is the single source of truth. Every artifact claim must trace to it.
Two hard gates — **Gate A (truth)** and **Gate B (target-fit)** — are non-bypassable in any
mode. Autonomous mode removes the human pause, never the machine gate; auto-loops are bounded by
a retry cap.

## Quickstart

New here? Start with **[docs/installation.md](docs/installation.md)** to set up the Python 3
render environment and dependencies, then follow **[docs/RUNBOOK.md](docs/RUNBOOK.md)** for an
end-to-end real-offer run.

## Documentation index

| Section | Description |
|---------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | Authoritative hub + 5-spoke roster, per-spoke boundaries, offer→render data flow, anti-drift principles. |
| [Requirements](docs/requirements.md) | The v2.0 milestone requirement inventory and traceability. |
| [Installation](docs/installation.md) | Set up the Python 3 render environment and install dependencies. |
| [Configuration](docs/configuration.md) | Config and data files (`candidate.yaml`, `sources.yaml`, CV/overlay YAML) and their stable names. |
| [Rules](docs/rules.md) | Load-bearing project invariants, read on demand by matching `scope:`. |
| [Skills](docs/skills.md) | The 10 project skills under `.claude/skills/`. |
| [Agents](docs/agents.md) | The give-me-job agent roster. |
| [Commands](docs/commands.md) | The command surface under `.claude/commands/`. |
| [Flows](docs/flows.md) | The runtime sequences wiring commands and scripts together. |
| [CLI tools](docs/cli-tools.md) | The deterministic Python script surface under `scripts/`. |
| [References](docs/references.md) | Contracts, schemas, and the `agent_result_v1` envelope. |
| [Features](docs/features.md) | Core value, guarantees, and capabilities. |
| [Runbook](docs/RUNBOOK.md) | End-to-end walkthrough of a real-offer run. |
| [Human testing plan](docs/HUMAN-TESTING-PLAN.md) | Manual verification plan for the collective. |
