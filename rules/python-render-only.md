---
scope:
  globs:
    - "scripts/cv/**"
    - "output/cv/**"
    - "templates/cv/**"
  keywords:
    - render
    - PDF
    - reportlab
    - weasyprint
    - gmj_render_cv
  agent-names:
    - gmj-cv-generator
---

# Invariant: Python-render-only

All PDF / document rendering happens via Python (`scripts/cv/gmj_render_cv.py`), never by manual
binary or PDF authoring in chat.

- Produce CV PDFs **only** by invoking `gmj_render_cv.py` (ReportLab, or WeasyPrint for HTML
  templates) — never hand-emit PDF bytes or fabricate a binary artifact.
- This keeps rendering **deterministic and reproducible**: the same YAML always yields the same
  document.
