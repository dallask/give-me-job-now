---
name: candidate-yaml-schema
description: Schema and editing rules for config/candidate.yaml in give-me-job.
---

# Candidate YAML (`config/candidate.yaml`)

## Top-level keys (preserve structure)

- `name` (string)
- `photo` (optional string): path to headshot **relative to repo root**, e.g. `sources/candidate/photo.jpg`. Same key may live under `contact.photo`.
- `title` (string)
- `summary` (string)
- `contact` (object): `phone`, `email`, `secondary_email`, `address`, `website`, `github`, `linkedin`, `portfolio`, `company_site`, optional `photo` (same semantics as top-level `photo`)
- `technical_expertise` (array): items with `resume_title`, `skills` (array of strings)
- `skills` (array of strings): flat highlights
- `languages` (array): items with `language`, `proficiency`
- `professional_experience` (array): items with `company`, `position`, `location`, `duration`, optional `company_description`, `linkedin`, `achievements` (array of strings)
- `key_achievements` (optional array): items with `title`, `description` for a “Key achievements” section (Enhancv-style templates)
- `certifications` (optional array): items with `issuer`, optional `year`, `credentials` (array of strings)
- `independent_projects` (array): entries may be objects (`name`, `role`, `duration`, `description`) or strings
- `education` (array): items with `institution`, `program`, `location`, `duration`

## Multi-language overlay files

The base file `config/candidate.yaml` is English. Language-specific prose is stored in **overlay files** at:
- `config/candidate.ua.yaml` — Ukrainian
- `config/candidate.ru.yaml` — Russian

At render time, `render_cv.py --lang ua` deep-merges the overlay over the base. Non-translated fields (skills, contact, URLs, dates) are inherited from the base and must **not** be duplicated in overlays.

**Translatable fields** (may appear in overlays): `name`, `title`, `summary`, `professional_experience[*].company_description`, `professional_experience[*].achievements`, `education[*].program`, `key_achievements[*].title`, `key_achievements[*].description`, `independent_projects[*].description`.

**Section labels** (not in YAML) are stored in `config/i18n/labels.yaml` keyed by `en`, `ua`, `ru`. To add a new label, add it to all three language blocks.

## Editing rules

1. Keep valid YAML; prefer single quotes for strings containing `:` or `@`.
2. Merge new bullets into `achievements` rather than replacing entire jobs unless instructed.
3. Do not fabricate employers, dates, or credentials—mark unknowns in chat, not in YAML.
4. After edits, mentally validate required colons and list indentation (two spaces).
5. When editing overlay files, preserve the same list length and order as `config/candidate.yaml`.
