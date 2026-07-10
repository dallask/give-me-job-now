# Rules — load-bearing invariants (Read on demand)

The `rules/` directory holds the collective's load-bearing invariants, **one per file**. They
are **not auto-loaded**. Each agent Reads the matching rule on demand when its current task
matches the rule's `scope:` selector — this keeps agent context lean and saves tokens.

Every rule file opens with a YAML frontmatter `scope:` block carrying at least one of `globs:` /
`keywords:` / `agent-names:`. Match your task against those selectors; if it matches, Read the
rule **before** acting. Correctness rests on this convention plus the machine gate
`tests/test_rules_scope.py`, which checks that every rule parses, carries a `scope:` block, and
is indexed in the canonical table — **not** on any flaky native auto-loader.

The canonical index lives at [../rules/README.md](../rules/README.md); the table below mirrors
it. When the two disagree, the canonical index wins. `rules/*.md` live at repo-root (not
`.claude/rules/`) — a deliberate, reaffirmed placement decision; see
[../rules/README.md](../rules/README.md)'s "Why repo-root, not `.claude/rules/`" section for the
rationale.

## Rule index (7 rules)

| Rule file | Scope (match on) | Read when… |
|-----------|------------------|------------|
| `truthfulness.md` | globs `config/candidate*.yaml`, `config/cv/**`; keywords fabrication, claim; agents `gmj-truth-verifier`, `gmj-artifact-composer` | You emit or verify any artifact claim — every claim must trace to `config/candidate.yaml`; reframe allowed, invention blocked. |
| `hub-and-spoke.md` | keywords orchestrator, Task, delegation, routing; agent `gmj-orchestrator` | You are about to `Task`-spawn, delegate, or reason about the routing topology — only the hub holds `Task`; spokes never spawn spokes. |
| `sources-scope.md` | glob `config/sources.yaml`; keywords web-search, WebFetch; agent `gmj-offer-scout` | You run any web search / offer discovery — stay inside `config/sources.yaml` boards/geos/langs; read it first. |
| `gmj-naming.md` | globs `.claude/agents/**`, `scripts/cv/**`; keywords naming, gmj-, prefix | You create or rename an agent, skill, command, hook, or script — use `gmj-` / `gmj_`; keep config/data filenames stable. |
| `python-render-only.md` | globs `scripts/cv/**`, `output/cv/**`; keywords render, PDF; agent `gmj-cv-generator` | You produce any PDF/document — render only via `scripts/cv/gmj_render_cv.py`; never author binaries in chat. |
| `gate-non-bypassability.md` | keywords gate, Gate A, Gate B, autonomous, retry-cap; agents `gmj-orchestrator`, `gmj-fit-evaluator` | You handle a quality gate or autonomous loop — Gate A/B are non-bypassable in any mode; auto-loops are retry-capped. |
| `docs-currency.md` | keywords milestone, finalize, docs, README, documentation | You finalize a milestone or touch `docs/` or `README` — refresh the docs set and re-run `python3 tests/test_docs_current.py`. |

## How the invariants connect

- **Truthfulness** and **gate non-bypassability** are the two safety-critical hard blocks:
  `gmj-truth-verifier` runs Gate A (truth) and `gmj-fit-evaluator` runs Gate B (target-fit).
  Neither gate can be bypassed in any mode; autonomous mode removes the human pause, never the
  machine gate. See [agents.md](agents.md) for the agents that own each gate.
- **Hub-and-spoke** protects the topology that makes gate/cycle tracking possible — only
  `gmj-orchestrator` holds `Task`.
- **Sources scope** and **python-render-only** bound the two external surfaces: web search
  (`gmj-offer-scout`) and PDF rendering (`gmj-cv-generator`).
- **gmj-naming** and **docs-currency** keep the roster and its documentation from drifting;
  `docs-currency.md` is the invariant that mandates re-running `tests/test_docs_current.py`
  whenever this documentation set changes.

## See also

- [../rules/README.md](../rules/README.md) — the canonical Read-on-demand rule index.
- [references.md](references.md) — contracts, schemas, and the envelope structure the rules
  reference.
- [agents.md](agents.md) — the roster whose behavior these invariants constrain.
