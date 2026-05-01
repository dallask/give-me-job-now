---
name: candidate-yaml-schema
description: Schema and editing rules for config/candidate.yaml in give-me-job.
---

# Candidate YAML (`config/candidate.yaml`)

## Top-level keys (preserve structure)

- `name` (string)
- `title` (string)
- `summary` (string)
- `contact` (object): `phone`, `email`, `address`, `website`, `github`, `linkedin` — all optional strings
- `technical_expertise` (array): items with `resume_title`, `skills` (array of strings)
- `skills` (array of strings): flat highlights
- `languages` (array): items with `language`, `proficiency`
- `professional_experience` (array): items with `company`, `position`, `location`, `duration`, optional `company_description`, `linkedin`, `achievements` (array of strings)
- `independent_projects` (array): entries may be objects or strings depending on usage
- `education` (array): items with `institution`, `program`, `location`, `duration`

## Editing rules

1. Keep valid YAML; prefer single quotes for strings containing `:` or `@`.
2. Merge new bullets into `achievements` rather than replacing entire jobs unless instructed.
3. Do not fabricate employers, dates, or credentials—mark unknowns in chat, not in YAML.
4. After edits, mentally validate required colons and list indentation (two spaces).
