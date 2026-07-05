---
scope:
  globs:
    - "config/candidate.yaml"
    - "config/candidate.*.yaml"
    - "config/cv/**"
  keywords:
    - truthfulness
    - fabrication
    - never-fabricate
    - claim
    - source-of-truth
  agent-names:
    - gmj-truth-verifier
    - gmj-artifact-composer
    - gmj-cv-generator
---

# Invariant: Truthfulness (never fabricate)

`config/candidate.yaml` (plus its `config/candidate.{lang}.yaml` overlays) is the **single source
of truth**. Every claim in any produced artifact — CV, cover letter, interview-prep — must trace
back to it.

- **Reframing and emphasis are allowed:** you may reorder, re-title, or foreground real facts to
  target an offer.
- **Invention is hard-blocked:** never add skills, employers, dates, metrics, or achievements that
  are not present in the candidate profile. If a gap exists, report it — do not fill it.
- If everything else fails, the artifact must still never fabricate. Truth (Gate A) is the
  non-negotiable floor.
