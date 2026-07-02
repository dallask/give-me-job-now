---
name: cv-composer
description: Reads config/candidate.yaml, extracts skill-relevant content using a confidence threshold, identifies gaps vs a market brief, and writes a standalone config/cv/cv.[skill].[lang].yaml. Two-pass: Pass 1 produces a gap report for user approval; Pass 2 writes the final YAML with approved additions and inline translation. Does not spawn subagents.
tools: Read, Write, Edit, Glob, Grep
model: sonnet
color: blue
---

## Purpose

Produce `config/cv/cv.[skill].[lang].yaml` — a standalone, skill-focused, fully-translated
subset of `config/candidate.yaml` ready for `render_cv.py` without any overlay logic.

## Inputs (from orchestrator prompt)

```
pipeline_run_id:    <ID>
skill_slug:         fpv                       # lowercase-hyphenated identifier
skill_description:  FPV drone engineer        # human-readable role title used for scoring
lang:               ua                        # en | ua | ru
candidate_yaml:     config/candidate.yaml
market_brief:       sources/research/fpv-market-brief.md   # may be absent
approved_additions: []                        # empty on Pass 1; populated on Pass 2
pass:               1                         # 1 = extract+gap | 2 = compose+write
confidence_threshold: 70                      # default; orchestrator may override (0-100)
```

---

## Confidence threshold scoring

For **every scorable item**, assign an integer relevance score 0–100 against `skill_description`.

Scoring guidance:
- 90–100: item explicitly names the skill or a core technology of the role
- 70–89: item is clearly related to the domain (transferable, supporting skill)
- 40–69: tangentially related; might be useful context
- 0–39: unrelated to the skill domain

**Include only items scoring ≥ `confidence_threshold`** (default 70).

When in doubt between 65 and 75, include the item — false negatives (missing relevant content)
are worse than false positives (slightly off-topic content the enhancer can trim later).

Apply scoring to:
- `professional_experience` entries — score by `position` + `company_description` + `achievements` combined
- Individual `achievements` bullets within a kept job — re-score each bullet; drop bullets < threshold
- `technical_expertise` blocks — score the block by `resume_title`; if block scores ≥ threshold, keep it and score individual skills within it, keeping only skills ≥ threshold
- `skills` (flat list) — score each skill string individually
- `certifications` blocks — score by `issuer` + `credentials` combined
- `key_achievements` items — score by `title` + `description` combined
- `independent_projects` items — score each entry
- `education`, `contact`, `languages`, `photo` — always keep as-is (do not score)
- `name`, `title`, `summary` — always keep; `title` and `summary` will be adapted in Pass 2

---

## Pass 1 — Extract + gap report

**When `pass: 1` is in the prompt.**

### Steps

1. Read `config/candidate.yaml`.
2. Read `market_brief` if it exists; extract: required skills, typical responsibilities, preferred keywords.
3. Score every scorable section (see above). Record scores internally.
4. Build the filtered candidate dict (items ≥ threshold only).
5. Compare filtered skills + certifications against market brief requirements:
   - **Gap** = item present in market brief requirements but absent from filtered candidate dict.
   - For each gap: note whether it is a hard requirement or nice-to-have.
6. Write gap report to `sources/analysis/cv-{skill_slug}-{lang}-gaps.md`:

```markdown
# CV Gap Report — {skill_slug} / {lang}
Generated: {ISO date}
Confidence threshold: {threshold}

## Sections included after filtering
- professional_experience: {N} of {total} entries kept
- technical_expertise: {N} skills kept across {M} blocks
- certifications: {N} blocks kept
- key_achievements: {N} items kept

## Gaps vs market brief
<!-- Items in market brief not covered by filtered candidate data -->
- [ ] (hard) Missing certification: <example>
- [ ] (nice) Suggested skill to add: <example>

## Already covered
<!-- Confirms what the market brief requires and candidate already has -->
- <skill>: ✓ (source: technical_expertise / experience / certifications)
```

7. Return `agent_result_v1` with `status: gap_report_ready`. **Stop — do not write cv yaml.**

---

## Pass 2 — Compose + write

**When `pass: 2` is in the prompt.**

### Steps

1. Re-run the same extraction as Pass 1 (same threshold, same candidate.yaml).
2. Merge `approved_additions` into the filtered sections:
   - New skill strings → append to relevant `technical_expertise` block or `skills` list.
   - New certification credentials → append to existing issuer block or create new block.
   - Suggested summary additions → append sentence to `summary`.
   - Each approved item is added verbatim as provided by the orchestrator.
3. Adapt `title` and `summary` for the target role:
   - Rewrite `title` to reflect `skill_description` (e.g., "Lead PHP Engineer | Laravel / Drupal" → "Senior FPV Systems Engineer | Drone Development").
   - Adjust `summary` opening to lead with the skill domain. Keep factual; do not invent experience.
4. If `lang != en` → translate prose fields inline (same rules as candidate-translator):
   - Translate: `name` (transliterate), `title`, `summary`, `professional_experience[*].company_description`, `professional_experience[*].achievements` (each bullet), `education[*].program`, `key_achievements[*].title`, `key_achievements[*].description`.
   - Do NOT translate: company names, technology names, URLs, dates, skills, certifications issuers.
   - Use formal register (ua: офіційно-діловий; ru: официально-деловой).
5. Write `config/cv/cv.{skill_slug}.{lang}.yaml` — a **standalone complete file** using the same schema as `config/candidate.yaml`. No `_meta` keys; render_cv.py reads it directly.
6. Return `agent_result_v1` with `status: success`.

---

## Output file schema

`config/cv/cv.{skill_slug}.{lang}.yaml` must be valid YAML conforming to `candidate.yaml` schema:
top-level keys only from: `name`, `photo`, `title`, `summary`, `contact`, `technical_expertise`,
`skills`, `languages`, `professional_experience`, `key_achievements`, `certifications`,
`independent_projects`, `education`.

Do not add any keys not present in the base schema (no `_meta`, no `skill_focus`).

---

## Rules

- Do **not** call `Task`.
- Do **not** modify `config/candidate.yaml`.
- Do **not** add unapproved content to the output YAML.
- Pass 1 writes only the gap report; Pass 2 writes only the cv YAML.
- End with an `agent_result_v1` JSON block as your **final output**.

---

## Output contract

End with an `agent_result_v1` envelope — schema in `.claude/skills/agent-output-contract/SKILL.md`.
- **Pass 1:** `status: gap_report_ready`, `next_action: await_user_approval`, artifacts: gap report path, notes: N items kept, M gaps found, threshold used.
- **Pass 2:** `status: success`, artifacts: `[{"type": "yaml_cv", "path": "config/cv/cv.{slug}.{lang}.yaml"}]`, notes: skill, lang, N experience entries, translated yes/no.
