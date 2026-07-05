---
scope:
  globs:
    - "config/sources.yaml"
  keywords:
    - web-search
    - WebSearch
    - WebFetch
    - sources.yaml
    - scope
    - job-board
  agent-names:
    - gmj-offer-scout
---

# Invariant: Search scope is bounded by sources.yaml

Any web-search / offer-discovery agent (`gmj-offer-scout` and legacy web-search spokes) must read
`config/sources.yaml` **before any `WebSearch`/`WebFetch` call** and may never search outside it.

- The allowed **boards/sites, geos/cities, and languages** are exactly those declared in
  `config/sources.yaml`; searches outside the listed scope are not permitted.
- The mandatory `sources.yaml` read stays enforced. If the file is absent, log a fallback warning
  and proceed unrestricted — but never silently widen scope when it is present.
