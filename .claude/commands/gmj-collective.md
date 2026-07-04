# /gmj-collective — Hub-and-spoke job/CV pipeline

---
allowed-tools: Task(*), Read(*), Glob(*), LS(*)
description: Run the gmj-orchestrator collective (routing schema + CV toolchain).
---

## What to do

1. **Hub runs here (top level):** Follow `.claude/agents/gmj-orchestrator.md` **in this chat session**—you are the hub. Use **`Task`** only to spawn **spokes** (`vacancy-router`, `cv-template-creator`, `gmj-cv-generator`, `cv-deliverable-gate`, etc.). **Never** call `Task` with `subagent_type: gmj-orchestrator`. Nesting the hub inside `Task` removes `Task` from that context (“Task is not available inside subagents”), which breaks the whole pipeline.
2. Follow the schema: **User Request → Routing Analysis → Agent Selection → Task Delegation → Quality Gate → Result**. The hub must **actually invoke** `Task` for each spoke—never stop at “I will delegate” without a `Task` call in the same turn.
3. Paths:
   - Inputs: `sources/` (see `.claude/skills/gmj-sources-ingestion/SKILL.md`)
   - Candidate data: `config/candidate.yaml`
   - PDF output: `output/cv/` via `scripts/cv/gmj_render_cv.py` (see `.claude/skills/gmj-cv-pdf-python/SKILL.md`)

## User message template

Paste your goal after invoking this command, for example:

- “Analyze materials under `sources/`, refresh `config/candidate.yaml`, generate PDF, review against `sources/vacancies/foo.md`.”
- “Research PHP/Drupal remote market trends for EU, then tune keywords in YAML.”
- “I attached a CV layout screenshot—create `templates/cv/…` to match it (browser MCP for pixel tweaks), then render PDF.”

The orchestrator should call **`vacancy-router`** first, then delegate spokes one step at a time and run **`cv-deliverable-gate`** before declaring completion.
