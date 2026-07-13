---
scope:
  keywords:
    - milestone
    - finalize
    - docs
    - README
    - documentation
---

# Invariant: docs are a milestone deliverable, refreshed + re-verified at finalization

Documentation is not written once; it is re-earned each milestone. At every milestone
finalization the docs describe the shipped system AS-IS, and a machine gate proves it.

- **Refresh at finalization.** Before finalizing any milestone, the `docs/` set and the root
  `README.md` MUST be refreshed to describe the shipped system as it actually is — no stale
  agent names, paths, flows, or removed features.
- **Re-verify with the gate.** Run `python3 tests/test_docs_current.py`; it MUST exit `0`.
  Also run `python3 tests/test_testplans_current.py`; it MUST exit `0` too — this second gate
  catches signal-table drift in `scripts/gmj_testplan_signals.py`'s hand-authored citations
  (schema field paths, enum values, script/file paths, config literals, command flags) against
  the live codebase. Both gates join the standing `tests/test_*.py` suite and are
  non-negotiable for finalization.
- **Fix in the doc, never fabricate.** When the gate reports a doc/code mismatch, correct the
  DOC to match the code — never invent behavior to satisfy a doc. Docs trace to the codebase.
- **English-only.** All docs and this rule stay in English.
