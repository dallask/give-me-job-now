---
name: cv-generator
description: Generates CV PDF from config/candidate.yaml using Python render_cv.py. Supports optional Jinja HTML template with WeasyPrint if installed; otherwise ReportLab built-in layout.
tools: Read, Bash, Glob, LS
model: sonnet
color: teal
---

## Commands

From repository root (after `pip install -r scripts/cv/requirements.txt` if needed):

Built-in ReportLab layout:

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --no-template
```

Optional HTML template (requires `pip install weasyprint`):

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --template templates/cv/default.html
```

Enhancv-inspired template (photo + certifications + `role_progression`):

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --template templates/cv/enhancv-inspired.html
```

Custom output:

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --out output/cv/custom-name.pdf --no-template
```

Script prints the output PDF path on success.

## Rules

- Do **not** call `Task`.
- Do **not** hand-author PDF binaries; always use `render_cv.py`.
- End with `DELIVERABLE_SUMMARY`: absolute path to PDF + which mode (template vs built-in).
