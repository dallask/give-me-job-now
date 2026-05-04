# Token & Performance Improvement Plan — give-me-job collective

## Current state (measured)

```text
Corpus prompt mass (all agents + skills on disk): ~95 KB (~24 K tokens).
Per-turn loaded mass: only the active persona. The hub (vacancy-orchestrator.md,
13.6 KB) is the single file loaded on every hub turn; spoke prompts load on spawn.
The savings figures below distinguish corpus-total vs per-turn where relevant.

Top hotspots (bytes):
  vacancy-orchestrator.md         13,596   hub prompt, loaded every hub turn
  cv-template-creator.md           8,188   14 tools, open-ended Playwright loop
  cv-composer.md                   7,881   two LLM passes, re-reads candidate.yaml twice
  ai-agents-architect.md           5,808   + duplicate skill 2,571 B
  cv-generator.md                  5,749   30 lines of redundant command examples
  candidate-translator.md          4,266   full YAML through LLM, merge by chat
  candidate-yaml-schema/SKILL.md   4,037   content duplicated in agents that read it

14 spokes, 6 skills, 4 hooks, 1 slash command.
agent_result_v1 boilerplate:   ~3,600–4,800 tokens — identical JSON in all 13 agents
sources.yaml enforcement block: ~600 tokens — verbatim copy in 2 agents
cv-composer pass 2 re-read:     ~4,000 tokens — re-reads candidate.yaml + re-scores
Full skill-cv pipeline run:     ~25,000–30,000 input tokens
```

```
User goal → vacancy-orchestrator (13.6 KB) → vacancy-router → spoke(s) → cv-deliverable-gate
                                           ↘ FAST_PATH (inline, no router)

Skill-cv pipeline (S1–S9):
  S1 job-market-researcher
  S2 cv-composer Pass 1  ← reads candidate.yaml (2,200 tok)
  S3 [user approves gap report]
  S4 cv-composer Pass 2  ← re-reads candidate.yaml (2,200 tok again)
  S5 cv-generator
  S6 cv-reviewer
  S7 cv-enhancer
  S8 cv-generator (post-enhance)
  S9 cv-deliverable-gate
```

---

## Architectural decisions — where the two plans diverged

Each item records the competing approaches and the chosen direction with rationale.

### D1 — agent_result_v1 output contract

| Option | Source | Trade-off |
|--------|--------|-----------|
| Hoist into CLAUDE.md as one-liner | external plan | CLAUDE.md is always-loaded; grows it |
| Extract to `.claude/skills/agent-output-contract/SKILL.md` | this analysis | Explicit reference per agent; single source; zero CLAUDE.md growth |

**Decision: dedicated skill file.**
CLAUDE.md is already injected into every session context and should stay lean. A shared skill is the correct single-responsibility pattern — agents reference it explicitly, it can evolve independently, and it keeps CLAUDE.md as a routing/path document only.

### D2 — cv-review-rubric and vacancy-research-rubric skills

| Option | Source | Trade-off |
|--------|--------|-----------|
| Delete skills; agents already inline content | external plan | Loses canonical source; forces dual edits when rubric changes |
| Keep skills as single source; remove inline duplication from agents | this analysis | One edit point; agents stay smaller |

**Decision: keep skills, remove inline duplication from agents.**
Deleting the shared file eliminates single-source-of-truth. The correct fix is the inverse: trim the inline copy from the agent and let the agent reference the skill. This is the same pattern used by `cv-reviewer.md` today (which already delegates to `cv-review-rubric`) — extend that pattern consistently.

### D3 — sources.yaml enforcement

| Option | Source | Trade-off |
|--------|--------|-----------|
| Not explicitly addressed | external plan | Duplication remains after Phase 2 |
| Extract to `.claude/skills/sources-config-enforcement/SKILL.md` | this analysis | Single edit point; ~600 tok saved across corpus |

**Decision: shared skill.**
`job-market-researcher.md` and `vacancy-scraper.md` contain verbatim identical 30-line blocks. A skill reference is cleaner than Python scripting for what is purely a behavioural constraint.

### D4 — cv-composer two passes

| Option | Source | Trade-off |
|--------|--------|-----------|
| Write pass1-state.json; Pass 2 reads artifact | this analysis | Still two LLM passes; still pays for scoring twice |
| `scripts/cv/compose.py` (TF-IDF/keyword scoring) + single LLM pass | external plan | Deterministic scoring for free; one LLM call total |

**Decision: Python-first (external plan).**
The LLM should not be doing deterministic keyword-overlap filtering on a static YAML. `compose.py` produces the filtered JSON and gap report; the single remaining LLM pass handles only the creative work: title/summary adaptation and prose translation. This eliminates the second Sonnet call entirely.

### D5 — translation

| Option | Source | Trade-off |
|--------|--------|-----------|
| Shared translation-policy skill | this analysis | Still LLM-driven; reduces duplication but not cost |
| `scripts/cv/translate.py` + compact JSON exchange | external plan | One LLM call with ~100-string JSON payload; Python merges result |

**Decision: Python-first (external plan).**
LLM-merging a 332-line YAML is wasteful. `translate.py` extracts only the translatable field set by JSON-Pointer, sends a compact `{path: en_string}` dict to the LLM, receives `{path: translated}` back, and Python merges it into the overlay file. The agent shrinks to ~1 KB.

### D6 — cv-reviewer + cv-enhancer

| Option | Source | Trade-off |
|--------|--------|-----------|
| Keep separate | — | Clean separation; two spawns per review cycle |
| Merge into cv-tuner `--mode review\|apply` | external plan | Halves review-cycle spawns; needs JSON contract defined first |

**Decision: merge (external plan), but JSON contract must be specified before implementation.**
The merge is correct architecturally. The prerequisite is a defined `review_result_v1` JSON schema so `--mode apply` has a stable input contract. This schema is specified in Phase 2 below and must be implemented before Phase 3's topology change.

### D7 — vacancy-router

| Option | Source | Trade-off |
|--------|--------|-----------|
| Keep always; haiku model is correct | this analysis | Extra spawn for well-known goals |
| Collapse into FAST_PATH; router only for free-form goals | external plan | −1 spawn for most runs |

**Decision: collapse (external plan).**
FAST_PATH already covers the common cases. The router adds latency with no value for goals that pattern-match exactly. Keep the router agent for free-form/ambiguous goals; skip it otherwise.

### D8 — cv-template-creator screenshot cost

| Option | Source | Trade-off |
|--------|--------|-----------|
| Reduce tool count (remove mcp__playwright__browser_tabs) | this analysis | Minor; root cost unaddressed |
| `scripts/cv/diff_layout.py` + bounded iterations (max 3) | external plan | LLM sees JSON diff, not base64 bitmaps; bounded loop |

**Decision: diff_layout.py (external plan).**
Full-page screenshots encoded as base64 in tool results are the real per-turn token cost — not the tool list length. The diff script feeds bbox/color/font deltas as JSON; the LLM only edits CSS where deltas exceed threshold. Cap at 3 iterations removes the open-ended loop risk.

---

## Phase 1 — Prompt diet (safe, no behaviour change)

**Goal:** cut ~30–40% of always-loaded prompt mass with zero pipeline logic change.

### P1-1: Shared `agent_result_v1` output contract skill

Create `.claude/skills/agent-output-contract/SKILL.md` with the canonical `agent_result_v1`
JSON schema, field definitions, and the `acceptance_criteria_met` rule (PASS items only —
do not echo prompt verbatim). In each of the 13 spoke agents replace the 12–18 line block
with one line:

```
End with `agent_result_v1` envelope — schema in `.claude/skills/agent-output-contract/SKILL.md`.
```

**Saves:** ~3,600–4,800 tokens across the corpus.

### P1-2: Compress `acceptance_criteria` round-trip (ID-based)

The orchestrator already computes a `criteria_hash`. Extend the contract using **stable
short IDs** rather than positional indices:

- Hub passes `criteria_hash` + `criteria_items[]` where each item has `{id, text}`.
  IDs are short, human-readable slugs: `crit-yaml-parses`, `crit-pdf-exists`, `crit-auth-01`.
- Spokes return `met_ids[]` + `failed_ids[]` (arrays of ID strings), not verbatim text
  and not integer positions.
- Gate resolves each returned ID against the original `criteria_items[]` map.

**Why IDs, not integer indices:** positional indices silently misalign if any hub or
spoke ever reorders the array (no length change, no detectable error). IDs are
order-independent and self-describing — a stray ID that doesn't map is trivially
caught. Token cost is equivalent to integer indices in practice (IDs average 15–25 chars).

**Gate invariants (hard checks):**
- Every returned ID must exist in `criteria_items[]`; unknown IDs fail the gate.
- `set(met_ids) ∩ set(failed_ids)` must be empty.
- `len(met_ids) + len(failed_ids) ≤ len(criteria_items)` (unreported items counted as failed).

This eliminates the full-criteria echo in every spoke return message.

### P1-3: Slim the orchestrator hub

Move from `vacancy-orchestrator.md`:
- §Skill-CV pipeline pseudocode (lines 133–202, ~70 lines) → `.claude/skills/orchestrator-pipelines/SKILL.md`
- §Pre-flight checks (lines 213–239, ~27 lines) → same skill file (to be replaced by `preflight.py` in Phase 2)

**Important — skills are static includes, not conditionally loaded.** A skill reference
in an agent's system prompt is injected at spawn time regardless of the goal. The hub
must instead use the `Read` tool at runtime: when the goal pattern matches
`generate cv for`, the hub calls `Read(".claude/skills/orchestrator-pipelines/SKILL.md")`
as its first action and proceeds with that content. When the goal does not match, the
hub never calls `Read` and the skill content is never loaded. The skill file reference
must not appear in the hub's static frontmatter or body text.

**Read-once rule (required):** the hub must `Read` the pipeline skill exactly once per
pipeline run (on the first matching turn) and reference its content from conversation
memory on subsequent turns. Repeated `Read` calls across pipeline steps would re-inject
the full skill body per turn and negate the savings. Encode this rule as a one-liner in
the slimmed hub prompt: *"Read orchestrator-pipelines/SKILL.md once on pipeline start;
do not re-Read during subsequent steps of the same run."*

Target hub size: 13.6 KB → ~5 KB.

### P1-4: Shared `sources.yaml` enforcement skill

Move the verbatim 30-line constraint block out of both `job-market-researcher.md` and
`vacancy-scraper.md` into `.claude/skills/sources-config-enforcement/SKILL.md`.
Replace with one-liner reference in each agent.

**Saves:** ~600 tokens corpus-wide; one edit point for constraint policy.

### P1-5: Remove inline duplication from rubric-consuming agents

`cv-reviewer.md` already references `cv-review-rubric/SKILL.md` — that is the correct
pattern. Audit `job-market-researcher.md` for any inlined vacancy-research-rubric content
and replace with a skill reference. Do not delete the skill files.

### P1-6: Delete `ai-agents-architect` skill duplicate

`.claude/skills/ai-agents-architect/SKILL.md` (2.5 KB) overlaps >80% with the agent file.
The agent is the authoritative version. Delete the skill file only after grepping for any
agent that references it by path.

### P1-7: Remove `LS` where `Glob` is already listed

`candidate-analyzer.md` and `cv-deliverable-gate.md` both list `Glob` and `LS` in tools.
`Glob` subsumes `LS` for file discovery. Remove `LS` from both frontmatter tool lists.

### P1-8: Hygiene

- **output/cv/ retention in render_cv.py:** add a post-write prune step to
  `scripts/cv/render_cv.py` — after writing a new PDF, delete siblings older than the
  last K=5 per `(skill, lang)` pair (configurable via `CV_KEEP_LAST` env var). This has
  zero dependencies on Phase 2 or 3 and should be done in Phase 1 to speed up
  `Glob`/artifact-manifest scans from Phase 1 onward.
- **output/cv/ archive:** move existing overflow to `output/cv/_archive/`.
- Clean up `.claude/settings.local.json`: remove one-off `[empty]`-path entries and ad-hoc port allow rules.

**Phase 1 expected savings:** ~30 KB of always-loaded prompts → ~7–8 K tokens off every
hub turn, ~3–5 K off each spoke spawn.

---

## Phase 2 — Deterministic work moves to Python

**Goal:** stop paying the LLM for filtering, scoring, and translation that code can do
faster, deterministically, and for free. This phase requires Phase 1 to be complete.

### P2-1: `scripts/cv/compose.py` — replace cv-composer Pass 1

```
compose.py --candidate config/candidate.yaml \
           --brief sources/research/<slug>-market-brief.md \
           --skill <slug> --lang <lang> \
           --threshold 0.4 \
           --out tmp/cv-<slug>-<lang>-filtered.json \
           --gap-md sources/analysis/cv-<slug>-<lang>-gaps.md \
           --gap-json sources/analysis/cv-<slug>-<lang>-gaps.json
```

What Python does:
- Parse `candidate.yaml` and the market brief.
- Score every scoreable section by keyword overlap + TF-IDF against the skill description
  and the brief's required-skills list.
- **Synonym map (required):** TF-IDF misses semantic synonyms — "drone operations" vs
  "UAV piloting" yields zero keyword overlap and would be incorrectly dropped. `compose.py`
  must load a synonym map seeded from the market brief's own terminology (extract
  noun-phrase pairs from the brief; optionally extend with a static `config/synonyms.yaml`).
  Synonym expansion runs before TF-IDF scoring so domain-specific vocabulary is matched.
- Apply confidence threshold (default 0.3); items scoring 0.3–0.7 are flagged for
  LLM tie-breaking (wider band than initially estimated to account for synonym coverage
  gaps; calibrate against existing `config/cv/` outputs before narrowing).

**Tie-breaker band measurement (hard prerequisite before P2-1 ships):** run `compose.py`
in dry-run mode against `fpv`, `underground-mining`, and at least two additional skill
slugs. Record the percentage of sections that fall in the 0.3–0.7 band per sample.

- If the median across samples is **≤ 25 %**, keep the band as designed; LLM tie-breaker
  runs on a small minority and the "one Sonnet call saved" claim holds.
- If the median is **25–40 %**, narrow the band (e.g. 0.35–0.6) and/or extend the
  synonym map, then remeasure.
- If the median is **> 40 %**, the deterministic gain is not real. Redesign P2-1: either
  accept two LLM calls (downgrade the claim) or move tie-breaking out of the main pass
  into a single batched LLM call over all ambiguous sections.

The chosen band and the measurement result are recorded in
`sources/analysis/compose-band-calibration.md` as the authoritative tuning record.
- Write the filtered candidate dict as `tmp/cv-<slug>-<lang>-filtered.json`.
- Write the gap report as both markdown (human-readable) and JSON (machine-readable sibling).

The `cv-composer` agent then runs a **single LLM pass** (replaces both Pass 1 and Pass 2):
- Input: `filtered.json` + `approved_additions` from orchestrator.
- Task: adapt `title`/`summary` for the role; translate prose if `lang != en`.
- Output: `config/cv/cv.<slug>.<lang>.yaml`.
- System prompt shrinks from 7.9 KB (two-pass) to ~3 KB (single pass).

**Saves:** one full Sonnet call per CV run (the largest single avoidable cost).

### P2-2: `scripts/cv/translate.py` — replace LLM-driven translation

```
translate.py --candidate config/candidate.yaml \
             --lang ua \
             --out config/candidate.ua.yaml
```

What Python does:
- Extract all translatable fields by JSON-Pointer path (authoritative list in
  `config/translation-policy.yaml` — a plain data file, not a skill; mixing translation
  policy with the output contract is a single-responsibility violation).
- Call the LLM **once** with a compact `{"path": "english string", ...}` payload.
- Receive `{"path": "translated string", ...}` back.
- Merge translated values into the overlay YAML by path.

The `candidate-translator` agent shrinks from 4.3 KB to ~1 KB (contract + edge-case notes only).

**Saves:** ~70% of current translator LLM cost.

### P2-2a: `config/translation-policy.yaml` — translation field ownership

Create `config/translation-policy.yaml` as the single authoritative source for which
fields are translatable. Format:

```yaml
translatable:
  - /summary
  - /experience/*/description
  - /education/*/notes
  # ...
non_translatable:
  - /contact
  - /skills
  - /experience/*/company
  # ...
```

Both `translate.py` (Phase 2) and `candidate-translator.md` (thinned agent) reference
this file. The `candidate-yaml-schema/SKILL.md` brief reference to translatable fields
is replaced by a pointer to this file. This resolves the three-location duplication
identified in the analysis.

### P2-3: `scripts/cv/preflight.py` — replace hub pre-flight prose

```
preflight.py --skill <slug> --lang <lang>
```

Returns JSON:
```json
{
  "candidate_yaml_ok": true,
  "skill_cv_yaml_exists": false,
  "overlay_present": false,
  "market_brief_present": true,
  "output_writable": true
}
```

The hub calls this as a single Bash command and reads the JSON. The ~27-line pre-flight
prose block in `orchestrator-pipelines/SKILL.md` (moved there in Phase 1) is replaced
by one line referencing the script.

### P2-4: JSON intermediates contract (`review_result_v1`)

**This must be defined before Phase 3's cv-tuner merge.**

Define `review_result_v1` schema:
```json
{
  "score": 0–100,
  "gaps": [{"field": "...", "issue": "...", "severity": "high|medium|low"}],
  "suggestions": [{"field": "...", "action": "...", "example": "..."}],
  "verdict": "PASS|REVISE"
}
```

Every review run writes:
- `sources/analysis/cv-<slug>-<lang>-review.md` — human-readable (kept for user)
- `sources/analysis/cv-<slug>-<lang>-review.json` — machine-readable (read by enhancer/tuner)

The next spoke reads the JSON only — not the markdown. Reduces enhancer context load significantly.

### P2-5: Python script failure contract

`compose.py`, `translate.py`, and `preflight.py` replace LLM calls. A crash (malformed
YAML, missing market brief, import error) leaves the orchestrator with no output and no
signal. Required contract for all three scripts:

- Exit code 0 on success, non-zero on any error.
- On error, write to stdout:
  ```json
  {"ok": false, "error": "human-readable message", "code": "MISSING_BRIEF|YAML_PARSE|..."}
  ```
- The orchestrator **must** check exit code before proceeding to the LLM pass. On non-zero
  exit, the hub surfaces the error JSON to the user and halts the pipeline. No silent
  continuation.

### P2-6: `tmp/` directory management

Three scripts write intermediates to `tmp/`: `filtered.json`, `layout-diff.json`, and
any preflight state. Without namespacing, two simultaneous pipeline runs collide on
`tmp/cv-fpv-ua-filtered.json`.

- All scripts accept a `--run-id` argument (default: `pipeline_run_id` passed by orchestrator).
- Outputs go to `tmp/<run_id>/` — e.g. `tmp/abc123/cv-fpv-ua-filtered.json`.
- Add `tmp/` to `.gitignore`.
- The orchestrator passes its `pipeline_run_id` as `--run-id` to every script call so
  all intermediates for a run are co-located and trivially prunable after the gate passes.

**Phase 2 expected savings:** eliminates one Sonnet pass per CV (cv-composer); cuts translator
cost ~70%; removes ~3 KB from agent prompts; reduces inter-agent context via JSON.

---

## Phase 3 — Topology changes

**Goal:** shorter pipelines, fewer spawns, lower latency. Requires Phase 2 complete
(JSON intermediates contract must be live before cv-tuner is built).

### P3-1: Collapse vacancy-router into orchestrator FAST_PATH

Well-known goal patterns already exist in the FAST_PATH table. For goals that match,
skip the router spawn entirely. Keep `vacancy-router.md` only as a fallback for
free-form/ambiguous goals that don't pattern-match.

Result: common pipeline runs save one Task spawn and ~1–2 LLM turns.

### P3-2: Merge cv-reviewer + cv-enhancer into cv-tuner

Create `.claude/agents/cv-tuner.md` with two modes:

- `--mode review`: produce `review_result_v1` JSON + markdown; no edits to YAML.
- `--mode apply`: read `review_result_v1` JSON; apply suggested edits to the skill YAML.
- `--mode review+apply`: do both in a single Sonnet call — **only when the orchestrator
  passes `user_preapproved_loop: true` explicitly**. If that flag is absent or false,
  the hub must default to `--mode review` → surface diff to user → await confirmation →
  `--mode apply`. Silent auto-apply without user confirmation risks unnoticed enhancement
  errors passing through the gate.

**Prerequisite:** `review_result_v1` schema from P2-4 must be stable.

Keep `cv-reviewer.md` and `cv-enhancer.md` as deprecated stubs (with a deprecation note
pointing to `cv-tuner`) until acceptance tests confirm behaviour parity. Delete stubs
after gate passes on **≥ 4 skill samples** (not just `fpv` + `underground-mining`) —
see rollback rule in Implementation order.

**Size budget (hard gate):** `cv-tuner.md` must stay ≤ 5 KB. Merging critic + editor
rubrics risks *growing* the prompt: if the merged file exceeds 5 KB the topology
change trades one Sonnet spawn for a heavier one and the token math flips. The merge
ships only if the final file is within budget; otherwise keep the agents separate and
record the decision in this document.

Saves: −1 spawn per review cycle; worst-case review loop drops from 8 spawns to 5.

### P3-3: Downgrade mechanical spokes to Haiku

| Agent | Justification |
|-------|---------------|
| `cv-deliverable-gate` | File existence + YAML parse — deterministic checks |
| `candidate-configurator` | Mostly field merges; no creative synthesis |
| `candidate-translator` (post-Phase 2 thin version) | LLM task is ~100-string JSON translation only |
| `vacancy-router` (when still used for free-form) | Already Haiku — confirm and document |

Keep Sonnet on: `cv-composer`, `cv-tuner`, `cv-template-creator`, `job-market-researcher`,
`vacancy-scraper`, `cv-generator`.

**Model ID pinning (required):** "Haiku" is ambiguous. Pin to `claude-haiku-4-5-20251001`
in each downgraded agent's frontmatter to prevent silent drift on future CLI updates.
Sonnet pins should reference `claude-sonnet-4-6`; Opus-needing agents (if any) reference
`claude-opus-4-7`.

Per-call cost drops ~5–8× for the downgraded spokes.

### P3-4: `scripts/cv/diff_layout.py` + bounded cv-template-creator

```
diff_layout.py --prototype path/to/prototype.png \
               --preview path/to/current-preview.png \
               --out tmp/layout-diff.json
```

Returns JSON of bbox deltas, color deltas, font-size deltas per element. The LLM receives
the diff JSON — not base64 bitmaps — and edits only CSS properties where deltas exceed
threshold (default: >5 px, >10% color channel, >1 pt font size).

Cap `cv-template-creator` at **3 Playwright iterations** hard. If parity is not achieved
in 3 cycles, the agent returns a partial result with the diff JSON for user review.

Removes the open-ended screenshot loop (the most expensive per-turn cost in the project).

### P3-5: SubagentStop hook → hub prose (partial replacement)

Remove `.claude/hooks/subagent-stop-quality-reminder.sh` and fold the reminder into the
hub's last-message template to reduce hook overhead.

**Caveat:** the SubagentStop hook fires on every spoke exit regardless of hub state. The
hub last-message template only fires when the hub itself generates a message after the
spoke returns. If a spoke crashes or exits without a clean hub catch, the reminder is
silently lost. This is an acceptable trade-off for the common path, but the replacement
is not functionally equivalent in all edge cases. Do not claim full equivalence in commit
messages or documentation.

**Phase 3 expected savings:** −1 spoke from average pipeline (router skipped); −1 spoke
per review cycle (tuner merge); −2×–4× on template-creator wall time; lower model bill
on gate/configurator/translator.

---

## Cumulative outcome

```
Phase          Prompt mass loaded   Avg spawns / CV run   Notes
Today          ~95 KB               7–9                   2 enhance cycles worst-case
After Phase 1  ~62 KB  (−35%)       7–9                   pure prompt diet, no logic change
After Phase 2  ~58 KB               6–7                   single composer pass + scripted translator
After Phase 3  ~50 KB  (−47%)       4–5                   tuner merge, router skipped on FAST_PATH
```

Per full skill-cv pipeline run: ~25,000–30,000 input tokens today → estimated
**~12,000–15,000 after all phases** (−50%).

---

## Acceptance tests

### Phase 1

- `python3 scripts/cv/render_cv.py --config config/candidate.yaml --no-template` exits 0.
- `python3 scripts/cv/render_cv.py --config config/cv/cv.fpv.ua.yaml` exits 0.
- Hub still spawns correct spokes for "render PDF" and "generate cv for fpv in ukrainian".
- `cv-deliverable-gate` still PASSes for both sample CVs.
- Grep confirms no agent references the deleted skill files.

### Phase 2

- `compose.py` keep/drop decision agrees with LLM Pass 1 on ≥ 90 % of sections across
  **≥ 4 diverse skill samples** (must include `fpv` + `underground-mining` plus two more;
  measured as: for each section present in the existing skill YAML, `compose.py` includes
  it; for each section absent, `compose.py` excludes it — agreement rate must be ≥ 90 %
  per-sample, not just averaged).
- Tie-breaker band calibration result from P2-1a is recorded in
  `sources/analysis/compose-band-calibration.md` and falls within the acceptable
  bracket (median ≤ 40 %, ideally ≤ 25 %).
- `translate.py` round-trip on a 10-string sample is semantically equivalent to the
  current `candidate-translator` output.
- `review_result_v1` JSON is written alongside every markdown review; downstream spoke
  reads JSON successfully.

### Phase 3

- `cv-deliverable-gate` PASSes for both samples with `cv-tuner` replacing the
  reviewer+enhancer pair.
- Review→enhance→generate cycle shows ≤2 spawns (down from 3) for a single review loop.
- `cv-template-creator` finishes within 3 Playwright iterations on the existing prototype.
- `vacancy-router` is NOT spawned for the goal "generate cv for fpv in ukrainian"
  (FAST_PATH match confirmed in orchestrator logs).

---

## Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Heuristic scoring misses semantic synonyms (TF-IDF false drops) | High | Synonym map seeded from market brief terminology; widen LLM tie-breaker band to 0.3–0.7; calibrate against `config/cv/` outputs before narrowing threshold |
| Phase 3 topology built before JSON contract is stable | High | P2-4 (`review_result_v1` schema) is a hard prerequisite for P3-2 (cv-tuner); enforce in implementation order |
| `criteria_items[]` reordering silently misaligns indices | Resolved | Contract uses stable short IDs, not positions (P1-2). Risk eliminated by design. |
| Tie-breaker band > 40 % of sections negates P2-1 savings | High | Hard-prereq calibration step in P2-1 on ≥ 4 samples; redesign gates if band too wide; results recorded in `sources/analysis/compose-band-calibration.md` |
| cv-tuner merged prompt exceeds per-spawn budget | Medium | Hard ≤ 5 KB size budget gate in P3-2; if exceeded, merge is skipped and agents stay separate |
| Haiku model ID drift on CLI updates | Low | Pin exact model IDs (`claude-haiku-4-5-20251001`, etc.) in agent frontmatter |
| Rewriting cv-composer / translator blocks revert path | Medium | Archive originals under `.claude/agents/_archive/cv-composer.v1.md` etc. before deletion; revert is one `git mv` |
| Python script crash leaves orchestrator with no output or signal | High | All scripts must exit non-zero on error and write machine-readable error JSON to stdout; orchestrator checks exit code before proceeding |
| Concurrent pipeline runs collide on shared `tmp/` paths | Medium | `--run-id` namespacing under `tmp/<run_id>/`; `tmp/` in `.gitignore` |
| Removing skill file orphans a referencing agent | Medium | Grep all `.claude/agents/*.md` and `.claude/skills/*/SKILL.md` for references before any deletion |
| cv-tuner `--mode review+apply` auto-applies without user confirmation | Medium | Flag only permitted when `user_preapproved_loop: true`; default path is review → user gate → apply |
| cv-tuner `--mode apply` changes review-only contract | Medium | Keep `--mode review` exit path byte-identical to today's `cv-reviewer` output; run acceptance tests before deleting stubs |
| Haiku spokes stumble on edge cases | Low | Add `model_override: sonnet` field to orchestrator prompt; failing Haiku spoke can be re-spawned on Sonnet with `cycle_number` evidence |
| diff_layout.py threshold too aggressive, missing real regressions | Low | Default thresholds (>5 px, >10% color, >1 pt font) are conservative; expose as CLI flags for tuning |
| SubagentStop hook removal loses reminder on spoke crash | Low | Acceptable trade-off for common path; do not claim full equivalence |

---

## Implementation order

```
Phase 1 (no dependencies, do in one batch):
  P1-1  agent-output-contract skill
  P1-2  criteria hash + ID-based compression (short IDs, not integer positions)
  P1-3  orchestrator hub slim (with read-once rule)
  P1-4  sources-config-enforcement skill
  P1-5  rubric inline dedup
  P1-6  delete ai-agents-architect skill duplicate
  P1-7  LS cleanup
  P1-8  output/cv hygiene + settings.local cleanup

Phase 2 (depends on Phase 1 complete):
  P2-0   archive originals: git mv cv-composer.md → _archive/cv-composer.v1.md
         (same for candidate-translator.md) BEFORE rewriting
  P2-4   review_result_v1 JSON schema  ← do first (unblocks P3-2)
  P2-2a  config/translation-policy.yaml
  P2-1a  tie-breaker band calibration on ≥ 4 skill samples; record result in
         sources/analysis/compose-band-calibration.md; gate P2-1 on result
  P2-1   compose.py (synonym map + calibrated tie-breaker band)
  P2-2   translate.py
  P2-3   preflight.py
  P2-5   script failure contract (exit codes + error JSON)
  P2-6   tmp/<run_id>/ namespacing + .gitignore

Phase 3 (depends on Phase 2 P2-4 complete):
  P3-0  archive cv-reviewer.md and cv-enhancer.md → _archive/ before merge
  P3-1  router collapse
  P3-2  cv-tuner (requires P2-4; ≤ 5 KB size gate; user_preapproved_loop gate)
  P3-3  Haiku downgrades with pinned model IDs
  P3-4  diff_layout.py + template-creator bounds
  P3-5  SubagentStop hook removal (partial replacement — see caveat)

Rollback rule: archived agents under .claude/agents/_archive/ stay until cumulative
acceptance tests pass on ≥ 4 diverse skill samples. Only then are stubs deleted.
Revert path for any regression: git mv _archive/<agent>.v1.md .claude/agents/<agent>.md.
```
