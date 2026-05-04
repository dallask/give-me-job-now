---
name: cv-generator
description: Generates CV PDF from config/candidate.yaml using Python render_cv.py. Supports optional Jinja HTML template with WeasyPrint if installed; otherwise ReportLab built-in layout.
tools: Read, Bash, Glob, LS
model: sonnet
color: teal
---

## Template choice (ask before rendering)

- If the orchestrator prompt **already** specifies the mode (`--no-template` or an explicit `--template templates/cv/<file>.html`), verify that HTML path exists when applicable, then proceed to **Commands**.
- Otherwise **ask the user** which CV template to use: **built-in ReportLab** (`--no-template`) or **HTML** under `templates/cv/` (name the `.html` file, e.g. `default.html`, `enhancv-inspired.html`).
- **Validate HTML paths**: only accept real template files at `templates/cv/*.html` (use `Read`/`Glob`/`LS` to confirm they exist).

### Prototype image instead of a template file

If the user answers with an **image** (attached screenshot, mock, or a path like `*.png` / `*.jpg` / `*.webp`) **instead of** a `templates/cv/*.html` path:

- Do **not** run `render_cv.py` for PDF generation.
- Stop and return control to the hub with this exact block so **`vacancy-orchestrator`** can delegate next:

```text
ORCHESTRATOR_HANDOFF
action: delegate_cv_template_creator
summary: User chose a visual prototype (image), not an HTML template under templates/cv/. A new Jinja template must be created first (e.g. cv-template-creator from the prototype), then cv-generator can run again with the real --template path.
```

Also emit one-line `DELIVERABLE_SUMMARY: NO_PDF — handoff to cv-template-creator; user provided image instead of templates/cv/*.html`.

## Commands

From repository root (after `pip install -r scripts/cv/requirements.txt` if needed):

Built-in ReportLab layout (English, default):

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --no-template
```

Ukrainian CV — ReportLab (loads `config/candidate.ua.yaml` overlay if it exists):

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --lang ua --no-template
```

Russian CV — HTML template:

```bash
python3 scripts/cv/render_cv.py --config config/candidate.yaml --lang ru --template templates/cv/default.html
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

When using `--template`, the script prints **two lines** to stdout:
1. The HTML file path (`<name>-<YYYY-MM-DD_HH:MM:SS>.html`)
2. The PDF file path (`<name>-<YYYY-MM-DD_HH:MM:SS>.pdf`)

When using `--no-template` (ReportLab), only the PDF path is printed.

**Do NOT pass `--out` unless the user explicitly requested a custom filename.** Without `--out`, the script auto-generates a timestamped filename under `output/cv/`. Passing `--out` overrides that and loses the timestamp.

Both output files share the same base name and timestamp; only the extension differs.

## Language support

- `--lang en` (default) — English labels, English base YAML.
- `--lang ua` — Ukrainian labels from `config/i18n/labels.yaml`; merges `config/candidate.ua.yaml` overlay if present (prose only; skills/contact stay from base).
- `--lang ru` — Russian labels; merges `config/candidate.ru.yaml` overlay if present.
- **Always generate exactly one PDF per invocation** — the language specified by `--lang`. Never loop over multiple languages or produce multiple PDFs in a single run.
- If the orchestrator requests a non-English CV and no overlay exists yet, return control with a note suggesting `candidate-translator` should run first. Section labels will still be translated even without an overlay.
- Output filenames include a language suffix when `--lang` is not `en` (e.g., `yevhen-kyvhyla-ua-2026-05-04_....pdf`).

## Rules

- Do **not** call `Task`.
- Do **not** hand-author PDF binaries; always use `render_cv.py`.
- End with an `agent_result_v1` JSON block as your **final output** — unless you emitted `ORCHESTRATOR_HANDOFF`, in which case use `"status": "handoff"` and set `handoff_target` (see below).

## Output contract

End with an `agent_result_v1` envelope — full schema and field rules in `.claude/skills/agent-output-contract/SKILL.md`.
- **Success:** `status: success`, artifacts: HTML path (template mode) + PDF path, notes: mode used.
- **Handoff:** `status: handoff`, `handoff_target: "cv-template-creator"`, artifacts: `[]`, notes: "User provided prototype image; template must be created first".
