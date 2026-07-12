<div align="center">

# 😡 Give Me Job NOW! 😡

**Unemployment Termination Squad**

*No Cap, No Fabrication, Just Applications*

**The last job agency you'll ever need. Point it at the vacancies, set your "I-deserve-a-billion-dollar-salary" filter, and go take a nap. Feed it a real job offer. It returns a truthful, laser-targeted CV, cover letter, and interview-prep — zero fabrication, no excuses.**

<p align="center">
    <a href="docs/installation.md"><img src="https://img.shields.io/badge/python-3.x-blue?logo=python&logoColor=white" alt="Python"/></a>
    <a href="docs/ARCHITECTURE.md"><img src="https://img.shields.io/badge/architecture-hub--and--spoke-informational" alt="Architecture"/></a>
    <a href="https://github.com/anthropics/claude-code"><img src="https://img.shields.io/badge/built%20with-Claude%20Code-6b4fbb?logo=anthropic&logoColor=white" alt="Built with Claude Code"/></a>
    <a href="https://github.com/dallask/give-me-job-now/releases"><img src="https://img.shields.io/github/v/release/dallask/give-me-job-now?logo=git&logoColor=white" alt="Releases"/></a>
    <a href="#-license"><img src="https://img.shields.io/github/license/dallask/give-me-job-now?logo=opensourceinitiative&logoColor=white" alt="License"/></a>
    <a href="http://example.com"><img src="https://img.shields.io/badge/author-Ievgen%20Kyvgyla-orange?logo=homepage&logoColor=white" alt="Author"/></a>
    <a href="#-documentation-index"><img src="https://img.shields.io/badge/docs-16%20guides-blueviolet?logo=readthedocs&logoColor=white" alt="Docs"/></a>
    <a href="https://github.com/dallask/give-me-job-now/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/dallask/give-me-job-now/tests.yml?logo=pytest&logoColor=white&label=tests" alt="Tests"/></a>
</p>

</div>

---

## Table of Contents

- [🤖 What is give-me-job](#-what-is-give-me-job)
- [🎯 Core value](#-core-value)
- [🔀 Hub-and-spoke model](#-hub-and-spoke-model)
- [🔒 Truthfulness guarantee](#-truthfulness-guarantee)
- [⚡ Quickstart](#-quickstart)
- [📚 Documentation index](#-documentation-index)
- [💬 Support](#-support)
- [🙏 Acknowledgements](#-acknowledgements)
- [⚠️ Warning](#-warning)
- [📄 License](#-license)

---

## 🤖 What is give-me-job

**give-me-job** is a standalone hub-and-spoke collective of specialized Claude Code agents,
commands, skills, and Python scripts that, given a real job offer, autonomously produces a
**truthful, offer-optimized** set of application artifacts — a CV (PDF), a cover letter, and an
interview-prep document — for one candidate.

---

## 🎯 Core value

Given a real offer, the system produces application artifacts that **provably trace back to the
candidate's real profile** (`config/candidate.yaml`) and **pass mandatory quality gates**. If
everything else fails, the artifacts must never fabricate and must actually target the offer.
Reframing and emphasis are allowed; invention is hard-blocked.

---

## 🔀 Hub-and-spoke model

A single top-level orchestrator, **`gmj-orchestrator`**, is the only role that holds `Task` and
delegates to spokes. Spokes never spawn spokes (nested hubs lose `Task` in Claude Code), so
routing stays a clean **User Request → Routing → Agent Selection → Task Delegation → Quality
Gate → Result** loop. This topology preserves criteria tracking and prevents chain drift.

For the authoritative roster and data flow, see
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — the source of truth for the hub + 5-spoke
roster, per-spoke boundaries, and the offer→render pipeline.

---

## 🔒 Truthfulness guarantee

`config/candidate.yaml` is the single source of truth. Every artifact claim must trace to it.
Two hard gates — **Gate A (truth)** and **Gate B (target-fit)** — are non-bypassable in any
mode. Autonomous mode removes the human pause, never the machine gate; auto-loops are bounded by
a retry cap.

---

## ⚡ Quickstart

New here? This is the fast path from a fresh clone to your first run.

**Requirements**

- **Python 3.x** — required, for the render/dependency environment. See
  **[docs/installation.md](docs/installation.md)**.
- **git** — required, for cloning/updating the repo.
- **Claude Code** (or **Cursor**, experimental) — Claude Code is the required runtime. Cursor is
  an alternative, but it's experimental — a CONDITIONAL GO viability spike, not a fully verified
  runtime path. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
- **Firecrawl** — optional, opt-in via the `search_provider` key in `config/preferences.yaml`
  (commented out by default); credentials are `.env`-only.

**Install**

```bash
bash gmj-core/bin/install.sh
```

Safe to re-run (idempotent). Full detail: **[docs/installation.md](docs/installation.md)**.

**First command**

Run `/gmj-collective` to launch the interactive hub — the friendliest entry point for a
new user. For a fully autonomous run instead, use `/gmj-pipeline-run`. For the full
end-to-end real-offer walkthrough, see **[docs/RUNBOOK.md](docs/RUNBOOK.md)**.

---

## 📚 Documentation index

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
| [Showcase](docs/SHOWCASE.md) | End-to-end narrative with a concrete walked offer→artifacts example (both gates firing). |
| [Demo walkthrough](docs/DEMO-WALKTHROUGH.md) | Scripted live demo — exact command sequence, narration beats, and an asciinema recording plan. |
| [Human testing plan](docs/HUMAN-TESTING-PLAN.md) | Manual verification plan for the collective. |

---

## 💬 Support

This is a personal, single-candidate project without a dedicated support channel. If you're
looking at this as a reference implementation, the architecture and rules docs above
(`docs/ARCHITECTURE.md`, `rules/README.md`) are the best starting point for understanding the
design; issues can be filed against this repository.

---

## 🙏 Acknowledgements

Built with [Claude Code](https://github.com/anthropics/claude-code) on top of the
[GSD Core](https://github.com/open-gsd/gsd-core) planning/execution framework — the phase
loop (discuss → plan → execute → verify → ship), `.planning/` state model, and this README's
formatting conventions are all downstream of that project. PDF/document rendering relies on
[ReportLab](https://www.reportlab.com/), [Jinja2](https://jinja.palletsprojects.com/), and
optionally [WeasyPrint](https://weasyprint.org/); configuration parsing uses
[PyYAML](https://pyyaml.org/).

---

## ⚠️ Warning

This project is under active development.
Use at your own risk.
If something can break, it will — probably right when you need it most.
That's totally fine, bugs are just unannounced features.
Feel free to ping me about any issues. I'll do my best to ignore them.

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

**Truthful by construction. Offer-optimized by design.**

Made by [Ievgen Kyvgyla](http://example.com)

</div>
