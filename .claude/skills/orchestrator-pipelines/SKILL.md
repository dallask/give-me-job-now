---
name: orchestrator-pipelines
description: Skill-CV pipeline steps and pre-flight checks for vacancy-orchestrator. Loaded dynamically via Read tool when goal matches — NOT statically included.
---

# Skill-CV pipeline steps

Read this file once at pipeline start. Reference from conversation memory on subsequent steps — do NOT re-read during the same pipeline run.

## Pipeline steps

```
skill_cv_pipeline(skill_slug, skill_description, lang, template):

  [S1] Market research — if sources/research/{skill_slug}-market-brief.md absent:
       Task(job-market-researcher,
            "Research role requirements, required skills, keywords, and salary bands
             for a {skill_description}. Write to sources/research/{skill_slug}-market-brief.md")

  [S2] CV composition Pass 1 — extract + gap report:
       Task(cv-composer,
            skill_slug={slug}, skill_description={desc}, lang={lang},
            candidate_yaml=config/candidate.yaml,
            market_brief=sources/research/{slug}-market-brief.md,
            approved_additions=[],
            pass=1,
            confidence_threshold=70)
       → reads agent_result_v1 with status=gap_report_ready
       → gap report written to sources/analysis/cv-{slug}-{lang}-gaps.md

  [S3] User approval — PAUSE (do not spawn any Task):
       Read sources/analysis/cv-{slug}-{lang}-gaps.md
       Present to user as a formatted checklist:
         "Here are the gaps found for [skill_description]. Please confirm which to include:"
         - [ ] (hard) <gap item 1>
         - [ ] (nice) <gap item 2>
         ...
       Collect user YES/NO for each item.
       Build approved_additions = [items with YES].
       If user says "skip all" or "none" → approved_additions = [].
       Resume pipeline when user responds.

  [S4] CV composition Pass 2 — compose + write:
       Task(cv-composer,
            skill_slug={slug}, skill_description={desc}, lang={lang},
            candidate_yaml=config/candidate.yaml,
            market_brief=sources/research/{slug}-market-brief.md,
            approved_additions={approved list from S3},
            pass=2,
            confidence_threshold=70)
       → config/cv/cv.{slug}.{lang}.yaml written

  [S5] Render:
       Task(cv-generator,
            config=config/cv/cv.{slug}.{lang}.yaml,
            template=templates/cv/{template})
       → output/cv/cv.{slug}.{lang}-<timestamp>.pdf + .html

  [S6] Review (market brief as benchmark):
       Task(cv-reviewer,
            cv_yaml=config/cv/cv.{slug}.{lang}.yaml,
            market_brief=sources/research/{slug}-market-brief.md,
            skill_slug={slug})
       → sources/analysis/cv-review-{slug}-{lang}-<timestamp>.md

  [S7] Enhance:
       Task(cv-enhancer,
            cv_yaml=config/cv/cv.{slug}.{lang}.yaml,
            review=sources/analysis/cv-review-{slug}-{lang}-*.md)
       NOTE: cv-enhancer must target config/cv/cv.{slug}.{lang}.yaml — NOT config/candidate.yaml.
       Pass this path explicitly in the Task prompt.

  [S8] Re-render (same command as S5 but after enhance):
       Task(cv-generator, config=config/cv/cv.{slug}.{lang}.yaml, template=...)

  Repeat S6–S8 up to MAX_ENHANCE_CYCLES=2 (cycle_number tracks iterations).

  [S9] Quality gate:
       Task(cv-deliverable-gate,
            cv_yaml=config/cv/cv.{slug}.{lang}.yaml,
            pdf=output/cv/cv.{slug}.{lang}-*.pdf)
```

## If cv.{slug}.{lang}.yaml already exists

Before S2, `Glob("config/cv/cv.{slug}.{lang}.yaml")`:
- If the file is recent (mtime within last hour) ask: "cv.{slug}.{lang}.yaml already exists — regenerate from scratch or skip to render?"
- If user says skip → jump to S5.
- If user says regenerate → proceed from S2.

---

# Pre-flight checks before expensive spokes

Run these inline (using `Glob`/`Bash`) before spawning the listed spoke. Do **not** use a Task call for pre-flight. (Phase 2 will replace these with `scripts/cv/preflight.py`.)

**Before `cv-generator`:**
1. `Glob("config/candidate.yaml")` — must exist; if missing, stop and report.
2. `Bash: python3 -c "import yaml; yaml.safe_load(open('config/candidate.yaml'))"` — if non-zero exit, show parse error, do not spawn.

**Before `cv-generator` (multi-language):**
When `--lang ua` or `--lang ru` is requested:
1. `Glob("config/candidate.{lang}.yaml")` — if overlay does **not** exist, Task-spawn `candidate-translator` first (passing only the target `lang`), then spawn `cv-generator` with `--lang <code>`.
2. If overlay exists, spawn `cv-generator --lang <code>` directly.
3. **Spawn `cv-generator` exactly once** with the single requested `--lang`. Do not generate additional language variants unless explicitly asked.

**Before `cv-composer`:**
1. `config/candidate.yaml` must exist and parse cleanly.
2. `skill_slug` and `lang` must be explicit in the Task prompt — never leave them unset.
3. On Pass 2: `approved_additions` must be populated from the user's S3 response (may be empty list `[]` but must be present).

**Before `cv-reviewer` (Mode B — market brief):**
1. `sources/research/{skill_slug}-market-brief.md` must exist (written by job-market-researcher in S1).

**Before `cv-reviewer` (Mode A — vacancy):**
1. Vacancy file path must be present in the user goal or an explicit path. If missing, ask the user before delegating.

**Before `cv-enhancer`:**
1. `Glob("sources/analysis/cv-review-*.md")` — must return at least one file. If missing, inform user and offer to run `cv-reviewer` first.
