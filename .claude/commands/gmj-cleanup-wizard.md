# /gmj-cleanup-wizard — Interactive, confirm-gated cleanup of generated-content categories

---
allowed-tools: Bash(*)
description: Interactive cleanup wizard for generated-content categories (output/* + .pipeline/runs/); confirm-gated, no-bypass-flag deletion of generated-content categories (OPS-01).
---

## What to do

You are a **direct-script invocation doc** — NOT a hub. You run
`python3 scripts/gmj_cleanup_wizard.py [--repo-root <path>]` via **`Bash`** in a live
terminal (the wizard needs a real TTY for its `questionary` checkbox/confirm prompts — it
cannot be driven by `Task`/subagent dispatch). There is no `Task`/spoke dispatch in this
flow at all: the frontmatter's `allowed-tools: Bash(*)` deliberately grants no
orchestration/dispatch tool (hub-holds-Task, per `CLAUDE.md`'s Architecture constraint) —
this is a non-hub-spoke, direct-script flow.

## Flags

`scripts/gmj_cleanup_wizard.py` exposes exactly one flag:

- **`--repo-root <path>`** — testability-only. Re-anchors category resolution at a
  different root than this repo's own root. The given path must be a git repo root (i.e.
  contain a `.git` entry) — `validate_repo_root()` refuses any root that isn't, to bound
  the blast radius of an unauthenticated override.

There is **no** `--yes`/`--force`/`-y`/`--no-confirm` bypass flag anywhere in this CLI —
the single `questionary.confirm(default=False)` prompt can never be skipped
non-interactively. There is no other way to invoke a deletion without answering that
prompt live.

## Interaction flow

This flow satisfies **OPS-01** — confirm-gated deletion of generated-content categories
with no bypass path.

The wizard operates on 8 fixed generated-content categories:

- `output/analysis/`
- `output/artifacts/`
- `output/cv/`
- `output/offers/`
- `output/research/`
- `output/vacancies/`
- `output/logs/`
- `.pipeline/runs/`

The interaction proceeds in order:

1. **Checkbox selection.** A `questionary.checkbox` prompt lists all 8 categories, each
   annotated with its live file count and human-readable size (e.g.
   `output/cv/ (12 files, 3.4 MB)`), computed fresh at invocation time.
2. **Zero-selection short-circuit.** Selecting zero categories (pressing Enter without
   toggling any checkbox) exits immediately, printing `Nothing selected, exiting.` and
   returning exit code `0` — no confirm prompt is ever shown in this path.
3. **Count+size summary.** A non-empty selection prints a per-category count+size line
   for each selected category, followed by a combined total (`Total: N files, X.Y MB`).
4. **The single confirm gate.** One un-skippable
   `questionary.confirm("Delete the above categories? This cannot be undone.",
   default=False)` prompt follows. Declining (pressing Enter alone, or an explicit "no")
   performs **zero deletions** and exits `0` with `Deletion declined, exiting.` printed.
5. **Confirmed delete.** Confirming deletes only the selected categories via
   `shutil.rmtree()`, then recreates each as an empty directory. Every category except
   `.pipeline/runs/` gets its `.gitkeep` recreated (matching this repo's git-tracked-
   empty-dir convention); `.pipeline/runs/` has no such convention — it is entirely
   git-ignored. Per-category outcomes are tracked independently: if a delete fails
   partway through the selected list, already-succeeded categories, the failed category,
   and any not-yet-attempted categories are each reported separately (exit code `1` if
   any category failed), rather than aborting silently on the first error.

## CLI-only invocation

```bash
claude --dangerously-skip-permissions
# then, in the session, or directly from a shell — either way requires a live TTY:
python3 scripts/gmj_cleanup_wizard.py [--repo-root <path>]
```

This must be run in a real (non-headless) terminal — the checkbox and confirm prompts
require a live TTY and cannot be driven programmatically or by `Task`/subagent dispatch.
