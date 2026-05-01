# /job-collective — Hub-and-spoke job/CV pipeline

---
allowed-tools: Task(*), Read(*), Write(*), Edit(*), Glob(*), Grep(*), Bash(*), LS(*), WebSearch(*), WebFetch(*)
description: Run the vacancy-orchestrator collective (routing schema + CV toolchain).
---

## What to do

1. Use the **`vacancy-orchestrator`** subagent as the **only** hub that calls `Task`.
2. Follow the schema: **User Request → Routing Analysis → Agent Selection → Task Delegation → Quality Gate → Result**.
3. Paths:
   - Inputs: `sources/` (see `.claude/skills/sources-ingestion/SKILL.md`)
   - Candidate data: `config/candidate.yaml`
   - PDF output: `output/cv/` via `scripts/cv/render_cv.py` (see `.claude/skills/cv-pdf-python/SKILL.md`)

## User message template

Paste your goal after invoking this command, for example:

- “Analyze materials under `sources/`, refresh `config/candidate.yaml`, generate PDF, review against `sources/vacancies/foo.md`.”
- “Research PHP/Drupal remote market trends for EU, then tune keywords in YAML.”

The orchestrator should call **`vacancy-router`** first, then delegate spokes one step at a time and run **`cv-deliverable-gate`** before declaring completion.
