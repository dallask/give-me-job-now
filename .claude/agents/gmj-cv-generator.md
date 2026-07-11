---
name: gmj-cv-generator
description: Generates CV PDF from config/candidate.yaml using Python gmj_render_cv.py. Supports optional Jinja HTML template with WeasyPrint if installed; otherwise ReportLab built-in layout.
tools: Read, Bash, Glob, LS
model: sonnet
color: teal
---

## Receives (bounded input)

- The finalized candidate/CV YAML config path (`config/candidate.yaml` or
  `config/cv/cv.[skill].[lang].yaml`), read-only.
- **Draft mode (Phase 8):** the path to an **approved** `artifact_draft` JSON (Gate A truth
  AND Gate B target-fit both recorded pass), plus its `content.artifact_type` and
  `content.language`. Only approved drafts are dispatched — the hub runs
  `gmj_check_delivery.py` first (see Draft mode below).
- Render flags: `--lang`, `--template`/`--no-template`, and optionally `--out`.
- Input budget: <= 128 KB of structured input.   <!-- GUARD-05 #1 per-spoke input budget -->

## Must NEVER receive

- Raw candidate source documents — only the finalized YAML path.
- Offer or gate conversation transcripts (artifact paths only).   <!-- GUARD-05 #3 -->
- Anything other than the finalized YAML path plus render flags.
- Never re-fetch, re-summarize, or paraphrase the offer — read the frozen offer-spec content fields only (INTAKE-02/04); the hub runs `gmj_check_offer.py` before each dispatch to reinforce this single source.

## Emits

- The rendered PDF (and, in template mode, the HTML) as `file` artifacts.
- Toward Phase 8 this forward-references the `artifact_draft` / `file` envelope kind;
  the schema is defined in Phase 2 under `schemas/`.

## Template choice (ask before rendering)

- If the orchestrator prompt **already** specifies the mode (`--no-template` or an explicit `--template templates/cv/<file>.html`), verify that HTML path exists when applicable, then proceed to **Commands**.
- **Config default (D-07):** When the orchestrator prompt does NOT specify `--no-template`/`--template` and the user has not been asked yet, `gmj_render_cv.py` itself resolves a template from `config/preferences.yaml`'s `cv:` block (`cv.default`/`cv.mode`) before falling back to `baxter.html` — this happens automatically inside the script; the agent does not need to read `preferences.yaml` itself or pass an extra flag for this case. The agent's own 'ask the user' step below, and any orchestrator-supplied `--template`/`--no-template` flag, are explicit caller intent and ALWAYS short-circuit this config-driven default (same precedence tier as an explicit `--template` flag).
- Otherwise **ask the user** which CV template to use: **built-in ReportLab** (`--no-template`) or **HTML** under `templates/cv/` (name the `.html` file, e.g. `default.html`, `enhancv-inspired.html`).
- **Validate HTML paths**: only accept real template files at `templates/cv/*.html` (use `Read`/`Glob`/`LS` to confirm they exist). Reject any `--template` argument containing `..` or an absolute path — the slug must resolve to a real file directly under `templates/cv/`.
- **By-name slug render (TEMPLATE-06)**: **any** stored template under `templates/cv/` is renderable by name via `--template templates/cv/<slug>.html` with **no per-template wiring** — this includes newly generated branded templates produced this phase (e.g. `gmj-baseline.html` and any slug the `gmj-template-creator` spoke writes). A freshly generated slug is a first-class render option the moment its `.html` file exists; nothing in `gmj_render_cv.py` or this agent needs to be changed to render it.

### Prototype image instead of a template file

If the user answers with an **image** (attached screenshot, mock, or a path like `*.png` / `*.jpg` / `*.webp`) **instead of** a `templates/cv/*.html` path:

- Do **not** run `gmj_render_cv.py` for PDF generation.
- Stop and return control to the hub with this exact block so **`gmj-orchestrator`** can delegate next:

```text
ORCHESTRATOR_HANDOFF
action: delegate_cv_template_creator
summary: User chose a visual prototype (image), not an HTML template under templates/cv/. A new Jinja template must be created first (e.g. gmj-template-creator from the prototype), then gmj-cv-generator can run again with the real --template path (renderable by name as templates/cv/<slug>.html once written).
```

Also emit one-line `DELIVERABLE_SUMMARY: NO_PDF — handoff to gmj-template-creator; user provided image instead of templates/cv/*.html`.

## Commands

From repository root (after `pip install -r scripts/cv/requirements.txt` if needed):

Built-in ReportLab layout (English, default):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --no-template
```

Ukrainian CV — ReportLab (loads `config/candidate.ua.yaml` overlay if it exists):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --lang ua --no-template
```

Russian CV — HTML template:

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --lang ru --template templates/cv/default.html
```

Optional HTML template (requires `pip install weasyprint`):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --template templates/cv/default.html
```

Enhancv-inspired template (photo + certifications + `role_progression`):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --template templates/cv/enhancv-inspired.html
```

Generated branded slug (any `templates/cv/<slug>.html` written by `gmj-template-creator`, e.g. the `gmj-baseline` slug — renders by name with no per-template wiring, TEMPLATE-06):

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --template templates/cv/gmj-baseline.html
```

Custom output:

```bash
python3 scripts/cv/gmj_render_cv.py --config config/candidate.yaml --out output/cv/custom-name.pdf --no-template
```

When using `--template`, the script prints **two lines** to stdout:
1. The HTML file path (`<name>-<YYYY-MM-DD_HH:MM:SS>.html`)
2. The PDF file path (`<name>-<YYYY-MM-DD_HH:MM:SS>.pdf`)

When using `--no-template` (ReportLab), only the PDF path is printed.

**Do NOT pass `--out` unless the user explicitly requested a custom filename.** Without `--out`, the script auto-generates a timestamped filename under `output/cv/`. Passing `--out` overrides that and loses the timestamp.

Both output files share the same base name and timestamp; only the extension differs.

## Draft mode (approved artifact_draft to artifacts)

This mode is **additive** — the legacy direct-YAML render path above (`config/candidate.yaml` /
`config/cv/*.yaml`) is preserved and unchanged. Draft mode renders an **approved**
`artifact_draft` (Gate A **and** Gate B recorded pass) whose content was fixed upstream by
the gates; the agent authors no content and no PDF itself.

**Delivery precondition (hub-enforced):** before dispatching a render, the hub resolves the
pipeline root `<root>` (`pipeline-dir=<dir>` prompt arg, else `GMJ_PIPELINE_DIR` environment
variable, else `.pipeline` fallback — same resolution as `/gmj-pipeline-run`) and runs
`python3 scripts/pipeline/gmj_check_delivery.py --state <root>/runs/<run_id>/state.json`
(named in `.claude/commands/gmj-pipeline/generate.md`). The agent renders **only** approved
drafts — a draft missing either recorded gate verdict is never rendered.

Branch on `content.artifact_type`:

- **`cv`** — bridge the approved draft to a CV-YAML, then render it to PDF (pass `--lang`
  explicitly so the correct labels/overlay apply):
  ```bash
  python3 scripts/cv/gmj_draft_to_cv_yaml.py --file <draft.json> --out <cv.yaml>
  python3 scripts/cv/gmj_render_cv.py --config <cv.yaml> --lang <content.language> --out output/cv/<name>.pdf
  ```
- **`cover_letter`** — render the approved cover-letter draft to PDF:
  ```bash
  python3 scripts/cv/gmj_render_cover_letter.py --file <draft.json> --lang <content.language>
  ```
- **`interview_prep`** — render the approved interview-prep draft to a markdown document:
  ```bash
  python3 scripts/cv/gmj_render_interview_prep.py --file <draft.json>
  ```

Emit each produced PDF / document path as a `file` artifact in the `agent_result_v1`
envelope (same contract as legacy mode, below).

**No-manual-PDF (E2E-02, threat T-08-11):** the Rules "Do NOT hand-author PDF binaries"
below applies to **all** rendering — `gmj_render_cv.py`, `gmj_render_cover_letter.py`, and
`gmj_render_interview_prep.py`. Every artifact is produced by a Python renderer via `Bash`;
the agent never authors a PDF or document body by hand. Tools stay `Read, Bash, Glob, LS`.

## HTML sibling (ARTF-02)

The CV render is the **only** artifact type with a first-class HTML deliverable.
`gmj_render_cv.py` prints the HTML path as its **own stdout line BEFORE the PDF path**
**only on the success branch** — the agent must inspect stdout for that extra line to
detect success (a single-line stdout means no HTML sibling was produced).

- **Success:** two stdout lines — the `.html` path, then the `.pdf` path. The default
  WeasyPrint/Jinja2 template path (`templates/cv/baxter.html`) succeeded.
- **Graceful degrade:** when WeasyPrint/Jinja2 is unavailable, the script degrades to
  ReportLab-only rendering — a single stdout line (PDF path only) — and writes the
  non-blocking warning `Falling back to ReportLab built-in layout.` to stderr. This is a
  **graceful degrade, never a render failure** (exit code stays 0).
- **Hard failure (mid-render crash):** `render_weasyprint_html()` writes the `.html` file to
  disk **before** invoking WeasyPrint's PDF step, so any exception during that PDF step
  (WeasyPrint internal error, bad CSS, missing font/image resource — anything other than the
  `ImportError` that triggers the graceful-degrade branch above) crashes the script non-zero
  with **zero** stdout lines, yet the `.html` file may already exist on disk with **no**
  matching `.pdf`. Stdout-line-count alone cannot distinguish "no HTML produced" from "HTML
  produced then the PDF step crashed" in this case — the agent must not infer either outcome
  from stdout when the exit code is non-zero.

The agent's `agent_result_v1.notes` field **must** state exactly one of these three
outcomes for a CV render:
- `"HTML produced"` — exit 0, the HTML sibling line was present on stdout.
- `"HTML degraded to PDF-only (WeasyPrint unavailable)"` — exit 0, only the PDF path was
  printed.
- `"render failed (exit <code>) — check for stray .html sibling"` — non-zero exit; report
  `status: fail`, and separately check (e.g. via `LS`/`Glob` on the expected `output/cv/`
  filename) whether a stray `.html` file was left behind with no matching `.pdf`, so the
  operator can clean it up rather than mistaking it for a successful render.

Never report a uniform "success" note that hides which branch ran — the stderr warning
is invisible to the operator unless the dispatching agent explicitly surfaces it here.

## Language support

- `--lang en` (default) — English labels, English base YAML.
- `--lang ua` — Ukrainian labels from `config/i18n/labels.yaml`; merges `config/candidate.ua.yaml` overlay if present (prose only; skills/contact stay from base).
- `--lang ru` — Russian labels; merges `config/candidate.ru.yaml` overlay if present.
- **Always generate exactly one PDF per invocation** — the language specified by `--lang`. Never loop over multiple languages or produce multiple PDFs in a single run.
- If the orchestrator requests a non-English CV and no overlay exists yet, return control with a note suggesting `candidate-translator` should run first. Section labels will still be translated even without an overlay.
- Output filenames include a language suffix when `--lang` is not `en` (e.g., `yevhen-kyvhyla-ua-2026-05-04_....pdf`).

## Rules

- Do **not** call `Task`.
- Do **not** hand-author PDF binaries or document bodies; always render through the Python
  scripts — `gmj_render_cv.py` (CV), `gmj_render_cover_letter.py` (cover letter), and
  `gmj_render_interview_prep.py` (interview prep). This covers both legacy and draft mode.
- End with an `agent_result_v1` JSON block as your **final output** — unless you emitted `ORCHESTRATOR_HANDOFF`, in which case use `"status": "handoff"` and set `handoff_target` (see below).

## Output contract

End with an `agent_result_v1` envelope — full schema and field rules in `.claude/skills/gmj-agent-output-contract/SKILL.md`.
- **Success:** `status: success`, artifacts: HTML path (template mode) + PDF path, notes: mode used
  — for a CV render (`content.artifact_type == "cv"` or legacy YAML mode), notes must also state
  the HTML outcome per "HTML sibling (ARTF-02)" above: `"HTML produced"` or `"HTML degraded to
  PDF-only (WeasyPrint unavailable)"`.
- **Failure (CV render, non-zero exit):** `status: fail`, artifacts: `[]` (do not report a stray
  `.html` as a delivered artifact), notes must state the exit code and note per "HTML sibling
  (ARTF-02)" above that a `.html` sibling may exist on disk with no matching `.pdf`.
- **Handoff:** `status: handoff`, `handoff_target: "gmj-template-creator"`, artifacts: `[]`, notes: "User provided prototype image; template must be created first".
