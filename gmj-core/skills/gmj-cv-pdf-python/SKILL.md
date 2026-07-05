---
name: gmj-cv-pdf-python
description: Python commands to extract text and render CV PDFs for give-me-job.
---

# Environment

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r scripts/cv/requirements.txt
```

Optional HTML template path needs **WeasyPrint** (may require extra OS libs on macOS):

```bash
pip install weasyprint
```

If WeasyPrint fails to install, use **built-in ReportLab** only (`--no-template`).

# Extract text

```bash
python3 scripts/cv/gmj_extract.py path/to/file.pdf
python3 scripts/cv/gmj_extract.py path/to/file.docx --json
```

# Render PDF

Default output directory: `output/cv/<slug>-<YYYYMMDD>.pdf`

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --no-template
```

With template (WeasyPrint):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --template templates/cv/default.html
```

**Enhancv-style layout** (sections aligned to analyzed Enhancv/Resume.pdf: summary, experience, education, optional key achievements, skills, certifications, projects). Supports **`photo`** in YAML (path relative to repo root):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --template templates/cv/enhancv-inspired.html
```

Set `photo: sources/candidate/photo.jpg` (or `contact.photo`) in `config/candidate.yaml`. ReportLab `--no-template` mode also shows the photo when set.

Custom output:

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --out output/cv/my-cv.pdf --no-template
```

The script prints the final PDF path on stdout.
