# Test Plan — gmj-cleanup-wizard

This file verifies the `gmj-cleanup-wizard` flow for a human operator running it directly.

## Setup & Preconditions

- `--repo-root` — testability-only. Re-anchors category resolution at a different root than this repo's own root. The given path must be a git repo root (i.e. contain a `.git` entry) — `validate_repo_root()` refuses any root that isn't, to bound the blast radius of an unauthenticated override.

## Test 1 — gmj-cleanup-wizard

**Proves:** OPS-01 — Interactive cleanup wizard for generated-content categories (output/* + .pipeline/runs/); confirm-gated, no-bypass-flag deletion of generated-content categories; with no confirm-bypass flag anywhere in its CLI.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
python3 scripts/gmj_cleanup_wizard.py [--repo-root <path>]
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-cleanup-wizard.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**
- A human operator confirms the observed output/state matches OPS-01's documented behavior above by reading the real output, not by delegating to a script's exit code alone.

---

_Generated from `.claude/commands/gmj-cleanup-wizard.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
