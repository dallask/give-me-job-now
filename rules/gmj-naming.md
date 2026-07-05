---
scope:
  globs:
    - ".claude/agents/**"
    - ".claude/skills/**"
    - ".claude/commands/**"
    - ".claude/hooks/**"
    - "scripts/cv/**"
  keywords:
    - naming
    - gmj-
    - gmj_
    - prefix
    - slug
---

# Invariant: gmj- / gmj_ naming convention

App-owned components carry a stable, greppable prefix that marks them as this collective's.

- **App agents, skills, commands, and hooks** use the `gmj-` (kebab-case) prefix, e.g.
  `gmj-orchestrator`, `gmj-offer-scout`, `/gmj-collective`.
- **App Python scripts** use the `gmj_` (snake_case) prefix, e.g. `gmj_render_cv.py`,
  `gmj_extract.py`.
- **Config and data filenames stay stable** (`config/candidate.yaml`, `config/sources.yaml`,
  `config/cv/cv.{skill}.{lang}.yaml`); do not rename them.
- Skill slugs are lowercase and hyphenated (`fpv`, `php-laravel`, `react-frontend`).
