---
scope:
  keywords:
    - rules
    - index
    - invariant
    - convention
    - read-on-demand
---

# rules/ — load-bearing project invariants (Read on demand)

These files hold the collective's load-bearing invariants, one per file. **They are not
auto-loaded.** Read the matching rule on demand when your task matches its `scope:` — this keeps
agent context lean and saves tokens. Correctness rests on this convention plus the machine gate
`tests/test_rules_scope.py` (which checks every rule parses, carries a `scope:` block, and is
indexed), **not** on any flaky native auto-loader.

Each rule opens with a YAML frontmatter `scope:` block carrying ≥1 of `globs:` / `keywords:` /
`agent-names:`. Match your current task against those selectors; if it matches, Read the rule
before acting.

| Rule file | Scope (match on) | Read when… |
|-----------|------------------|------------|
| `truthfulness.md` | globs `config/candidate*.yaml`, `config/cv/**`; keywords fabrication, claim; agents gmj-truth-verifier, gmj-artifact-composer | You emit or verify any artifact claim — every claim must trace to `config/candidate.yaml`; reframe allowed, invention blocked. |
| `hub-and-spoke.md` | keywords orchestrator, Task, delegation, routing; agent gmj-orchestrator | You are about to `Task`-spawn, delegate, or reason about the routing topology — only the hub holds `Task`; spokes never spawn spokes. |
| `sources-scope.md` | glob `config/sources.yaml`; keywords web-search, WebFetch; agent gmj-offer-scout | You run any web search / offer discovery — stay inside `config/sources.yaml` boards/geos/langs; read it first. |
| `gmj-naming.md` | globs `.claude/agents/**`, `scripts/cv/**`; keywords naming, gmj-, prefix | You create or rename an agent, skill, command, hook, or script — use `gmj-` / `gmj_`; keep config/data filenames stable. |
| `python-render-only.md` | globs `scripts/cv/**`, `output/cv/**`; keywords render, PDF; agent gmj-cv-generator | You produce any PDF/document — render only via `scripts/cv/gmj_render_cv.py`; never author binaries in chat. |
| `gate-non-bypassability.md` | keywords gate, Gate A, Gate B, autonomous, retry-cap; agents gmj-orchestrator, gmj-fit-evaluator | You handle a quality gate or autonomous loop — Gate A/B are non-bypassable in any mode; auto-loops are retry-capped. |
| `docs-currency.md` | keywords milestone, finalize, docs, README, documentation | You finalize a milestone or touch docs/ or README — refresh the docs set and re-run `python3 tests/test_docs_current.py`. |
