---
name: gmj-sources-ingestion
description: Conventions for placing candidate and vacancy materials under sources/.
---

# `sources/` layout

| Path | Purpose |
|------|---------|
| `sources/` | Raw uploads: PDF/DOCX/XLSX/images/text notes |
| `sources/vacancies/` | Normalized job postings (`vacancy-scraper`) |
| `sources/research/` | Market briefs (`job-market-researcher`) |
| `sources/analysis/` | Analyzer summaries, CV reviews |

## Filename conventions

- Use lowercase kebab-case: `jd-acme-backend.pdf`, `market-brief-php-ukraine.md`.
- Prefer dated suffix for volatile research: `market-brief-2026-05-01.md`.

## PII and secrets

- Avoid committing secrets, offers with compensation NDA, government IDs, or scans you would not share with a recruiter.
- Redact phone/email in shared repos if needed; keep canonical contact only in `config/candidate.yaml`.

## Analyzer workflow

- Run `python3 scripts/cv/gmj_extract.py "<file>" --json` from repo root for structured text.
