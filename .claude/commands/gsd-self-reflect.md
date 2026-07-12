# /gsd-self-reflect — On-demand execution-log self-reflection findings + gated apply

---
allowed-tools: Bash(*), Read(*)
description: Run the report-only self-reflection analyzer and present findings; --apply reviews and applies exactly one proposed fix, atomically committed.
---

## What to do

You are a **read-only findings presenter** by default, and a **single-fix, explicit-consent
applier** only when the user passes `--apply`. This command never batches multiple fixes into
one invocation, and the report-only path never touches `scripts/gmj_self_reflect_apply.py`.

### Report-only path (no `--apply`)

1. Run the analyzer:
   `Bash: python3 scripts/gmj_self_reflect.py --log-dir .planning/execution-logs/ --output output/analysis/self-reflect-report.md`
2. `Read` the generated `output/analysis/self-reflect-report.md`.
3. Present the findings **inline** in your response — name each recurring pattern found
   (heading, occurrence count, proposed fix, a few evidence lines), do not just print the file
   path and tell the user to go read it themselves.
4. If the report contains no named findings (the "No recurring patterns found" section), say so
   plainly: **"No recurring patterns found — nothing to report this run."** Do not present an
   empty-looking report with no framing.
5. Always end with this exact framing, verbatim (REFLECT-05's user-facing proof this command is
   observational, not a gate):

   > No fix has been applied. Findings are report-only. Run `/gsd-self-reflect --apply` to
   > review and apply one proposed fix, atomically committed.

The report-only path never invokes `scripts/gmj_self_reflect_apply.py` and never creates a git
commit — it is pure read + present.

### `--apply` path (explicit, single-fix, atomic-commit)

Mirrors `$HOME/.claude/gsd-core/workflows/code-review-fix.md`'s `check_review_exists` ->
`check_review_status` -> apply -> commit-once shape, adapted to this analyzer's report instead
of `REVIEW.md`. Never batch-applies all findings in one invocation — one fix per `--apply` run.

1. **Require the report to already exist** (mirrors `check_review_exists` — do NOT auto-run the
   analyzer first):

   ```bash
   REPORT_PATH="output/analysis/self-reflect-report.md"
   if [ ! -f "$REPORT_PATH" ]; then
     echo "Error: No self-reflect-report.md found. Run /gsd-self-reflect first."
     exit 1
   fi
   ```

2. **Determine which finding to apply.** If the user supplied a finding/pattern id as a
   follow-up argument (e.g. `/gsd-self-reflect --apply worktree-base-drift`), use it directly.
   Otherwise, `Read` the report, list its named findings (pattern id + heading), and ask the user
   which one to apply. Never batch-apply all findings in one invocation, even though
   `code-review-fix.md`'s `--all`/`--auto` batch modes exist for code review specifically — this
   simpler command deliberately does not adopt that batch mode, per D-07's opt-in, explicit
   framing.

3. **Run the apply script for exactly that one finding:**

   ```bash
   python3 scripts/gmj_self_reflect_apply.py --report "$REPORT_PATH" --finding "<finding-id>"
   ```

   This script never auto-generates the report (step 1 already required it to exist), exits
   non-zero with a clear message if the finding id is unknown or if it recognizes the finding but
   its proposed fix is prose-only (requires manual human judgment, not a mechanical apply), and
   is idempotent-safe if the fix was already applied in a prior invocation.

4. **On `{"status": "applied", ...}`,** create exactly ONE git commit covering only the files the
   script reports as changed:

   ```bash
   git add <files_changed...>
   git commit -m "fix(self-reflect): apply <finding-id> fix"
   ```

   This command layer owns the commit — `gmj_self_reflect_apply.py` never commits itself, mirroring
   `code-review-fix.md`'s division of "the fixer agent applies, the orchestrator commits once."

5. **On `{"status": "already_applied", ...}`,** report that the fix is already present — do not
   create a commit and do not treat this as an error.

6. **On any non-zero exit** (unknown finding, non-mechanical finding, missing report), present
   the script's stderr message directly to the user and stop — do not retry with a different
   finding id or fabricate an apply.

7. Present the result: what changed, the commit hash (if a commit was made), and remind the user
   that only one fix was applied per invocation — re-run `/gsd-self-reflect --apply` again for
   another finding.

## Auto-fire note (execute:post / ship:post)

Per `06-03-SUMMARY.md`'s recorded `VERDICT: fallback-required`, the GSD-core-side
`execute:post`/`ship:post` dispatch point that would auto-fire this analyzer is not wired in
this GSD installation (blocked upstream by an `engines.gsd` host-version-resolution defect, not
a structural problem in this repo). This command's on-demand path (`/gsd-self-reflect` with no
flags) is fully functional regardless — it does not depend on that dispatch point at all.

## CLI-only invocation

```bash
claude --dangerously-skip-permissions
# then, in the session:
/gsd-self-reflect            # report-only: run analyzer, present findings inline
/gsd-self-reflect --apply    # requires a prior report; apply exactly one named fix, atomically committed
```

There is no UI — this command runs entirely from the CLI.
