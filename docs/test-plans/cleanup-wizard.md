# Test Plan — gmj-cleanup-wizard

> ⚠️ **destructive-if-confirmed**: This flow can permanently delete real local data if a human confirms the deletion prompt. Run only against a disposable fixture directory, never a real working copy with data you need, unless deletion is the intended outcome.

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

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| The single `questionary.confirm(default=False)` prompt returns `True` — the ONLY gate to a delete action; the safety guarantee is the presence of that mandatory interactive confirm gate. Declining (Enter alone, or any non-confirm) short-circuits before the confirm prompt is ever shown, resulting in zero deletions | There is no failure mode distinct from "user declined" — this is a destructive-if-confirmed flow whose only two terminal states are "confirmed -> deletions executed" and "declined/no input -> zero deletions." No `--yes`/`--force`/`-y`/`--no-confirm` bypass flag exists anywhere in the argparse surface, verified by a dedicated regression test | `scripts/gmj_cleanup_wizard.py`'s `questionary.confirm(default=False)` return value + `tests/test_gmj_cleanup_wizard.py::test_no_bypass_flag_in_argparse` (the machine-verified absence-of-bypass regression guard) + `--repo-root` flag (testability-only, documented as not a bypass path) | None — fully mechanical |

---

_Generated from `.claude/commands/gmj-cleanup-wizard.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
