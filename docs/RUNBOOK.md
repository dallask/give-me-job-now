# RUNBOOK — End-to-end real-offer run

Operator guide for running the give-me-job collective against a **real, current job
offer** and producing the truthful, offer-optimized artifacts (CV PDF + cover-letter PDF +
interview-prep document) end to end via `/gmj-pipeline-run`.

This runbook maps the two done-criteria for Phase 8:

- **E2E-01 — deterministic guard demo (DONE).** Proven, repeatable, no human judgment.
- **E2E-03 — live real-offer run (human-acceptance UAT).** Requires an operator driving a
  real offer and accepting the delivered artifacts.

`gmj-cv-generator` renders every artifact through Python scripts — **E2E-02** (Python-rendered
CV + cover, no manual authoring) is covered by the bridge + renderers named below.

---

## 1. Setup (dependencies)

The recommended path is the one-script installer — it bootstraps a project-local `.venv`
and installs all four dependency files (`scripts/contracts/`, `scripts/dashboard/`,
`scripts/cv/`, `scripts/preferences/`) plus stages config/hooks:

```bash
bash gmj-core/bin/install.sh
```

If installing manually instead, from the repository root, install each requirements file
through the same `.venv` (see [docs/installation.md](installation.md) for the full
reference):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/contracts/requirements.txt
.venv/bin/python -m pip install -r scripts/dashboard/requirements.txt
.venv/bin/python -m pip install -r scripts/cv/requirements.txt
.venv/bin/python -m pip install -r scripts/preferences/requirements.txt
```

The `scripts/cv/requirements.txt` install brings in the render stack — notably
**reportlab** (the built-in ReportLab CV layout engine) and **PyYAML** / **pypdf**. The
**bundled DejaVu fonts** under `scripts/cv/fonts/` (`DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`)
cover **ua/ru Cyrillic** rendering, so no system font install is required. **WeasyPrint**
(HTML template rendering) ships in the same file and stays optional.

---

## 2. Running a real offer

Drive a live run against a **real, current offer** plus a **real, populated**
`config/candidate.yaml` (the single source of truth — every artifact claim must trace back
to it):

```bash
claude --dangerously-skip-permissions
# then, in the session:
/gmj-pipeline-run
# state your: mode (human_in_the_loop | autonomous), offer (URL/text or offer-spec.json), run_id?
```

### Default artifact set — all three, independently gated

`/gmj-pipeline-run` produces **all three artifact types by default** — CV, cover letter,
interview-prep — each derives its own `run_id` (`<run_id>-cv` / `-cl` / `-ip`) and passes
through **Gate A ∧ Gate B independently**; a PASS on one artifact type never satisfies
delivery for another. Pass `--artifact-types` with a comma-list to narrow the default set,
e.g. `--artifact-types=cv,cover_letter`; an unknown/typo'd value hard-fails before any
dispatch, naming the invalid value and the valid set (`cv,cover_letter,interview_prep`).

### Hub-at-top-level rule (Pitfall 6 / T-08-12)

The **hub runs at top level in this chat session** — you are the `gmj-orchestrator`.
`Task` spawns **spokes only** (`gmj-offer-scout`, `gmj-artifact-composer`, `gmj-truth-verifier`,
`gmj-fit-evaluator`, `gmj-cv-generator`). **Never** call `Task` with
`subagent_type: gmj-orchestrator` — nesting the hub inside `Task` removes `Task` from
that context and breaks the whole pipeline (see `.claude/CLAUDE.md` hub-and-spoke rule).

### Control loop (`docs/ARCHITECTURE.md` §5.1)

The deterministic control plane makes every safety decision; the hub calls scripts via
`Bash` and never judges a gate itself:

1. **init_run** — freeze `execution_mode` + `retry_cap` + `run_id` into
   `.pipeline/runs/<run_id>/state.json`.
2. **route** — `gmj_route.py` picks the next step; `gmj_check_offer.py` runs before each dispatch
   (stale offer aborts); `Task(spoke)` produces a draft or gate_result.
3. **gate** — at a gate node, `gmj_check_truth.py` (Gate A) / `gmj_score_fit.py` (Gate B) exit 0/1
   with no bypass; `gmj_record_gate.py` records the verdict. FAIL → `gmj_record_retry.py` →
   `gmj_check_cap.py` (below cap: `gmj_map_feedback.py` → re-compose; at cap: HARD STOP).
4. **deliver** — `gmj_check_delivery.py` confirms **Gate A ∧ Gate B recorded pass** before any
   artifact is delivered.

`execution_mode` gates **only the human pause**, never the machine gate: HITL pauses for
approval after a PASS; autonomous proceeds automatically. Truth (Gate A) and target-fit
(Gate B) block identically in both modes.

---

## 3. Outputs

Each delivered artifact passes **Gate A (truth)** and **Gate B (target-fit)** before it
ships:

- **CV** — PDF **and** HTML under `output/cv/` (draft → `gmj_draft_to_cv_yaml.py` bridge →
  `gmj_render_cv.py --lang <lang>`, template mode by default).
- **Cover letter** — PDF under `output/cv/` (`gmj_render_cover_letter.py`).
- **Interview-prep** — markdown document (`gmj_render_interview_prep.py`).

Gate verdicts and run state are logged under **`.pipeline/runs/<run_id>/`** — the audit
trail (GUARD-03 / T-08-13): the recorded `gate_result` artifacts prove which verdicts
passed for each delivered artifact.

**Reclaiming disk space.** `scripts/gmj_cleanup_wizard.py` is an interactive, checkbox-driven
CLI for deleting generated `output/*` content and `.pipeline/runs/` state — every category is
confirm-gated (no bypass flag), so nothing is removed without an explicit final confirmation.

---

## 4. Done-criteria map

| Criterion | What it proves | How it is exercised | Status |
|-----------|----------------|---------------------|--------|
| **E2E-01** | Deterministic guard enforcement: nothing fabricated/off-target ships; an approved draft renders to a real PDF with zero manual authoring | `python3 tests/test_e2e_guards.py` (matrix + dry-run + wiring + runbook assertions) | **DONE** — deterministic, repeatable |
| **E2E-02** | CV + cover letter rendered via Python, no manual PDF authoring | bridge (`gmj_draft_to_cv_yaml.py`) + renderers (`gmj_render_cv.py`, `gmj_render_cover_letter.py`, `gmj_render_interview_prep.py`), wired in `.claude/agents/gmj-cv-generator.md` | Covered |
| **E2E-03** | Live real-offer run produces accepted artifacts end to end | `/gmj-pipeline-run` on a real offer + populated `config/candidate.yaml` | **Human-acceptance UAT** — operator drives + accepts |

**E2E-01** is the deterministic floor (machine-proven). **E2E-03** is the live acceptance
run a human performs with a real offer; it cannot be auto-asserted because it depends on a
current external posting and human judgment of the delivered artifacts.

---

## 5. Scheduled / unattended runs

`scripts/ops/gmj_cron_run.sh` lets an operator run the autonomous pipeline
(`/gmj-batch mode=autonomous`) unattended on a recurring OS-native schedule (cron or launchd),
with a non-blocking overlap guard: if a scheduled run is still in progress when the next tick
fires, the second invocation exits non-zero immediately (fail closed — no queueing, no silent
skip) rather than starting a second overlapping run.

### One-time prerequisite: workspace trust

Before adding any cron/launchd entry, run `claude` **interactively** in this repo directory at
least once and accept the workspace-trust prompt (or pre-set `hasTrustDialogAccepted: true` for
this project path in `~/.claude.json`). Without this one-time step, a fresh (never-interactively-
run) workspace **silently ignores** `.claude/settings.json`'s declared `permissions.allow`
entries on every scheduled `-p` invocation — `--dangerously-skip-permissions` itself still works
regardless of trust status, but the declared allow-list is otherwise a no-op on an untrusted
workspace. This is a one-time setup step, not a per-run requirement.

### macOS `launchd` example

Create a `.plist` (e.g. `~/Library/LaunchAgents/com.gmj.cron-run.plist`) pointing at the wrapper,
redirecting stdout/stderr into this repo's existing git-ignored `output/logs/` convention:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.gmj.cron-run</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/absolute/path/to/give-me-job/scripts/ops/gmj_cron_run.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/absolute/path/to/give-me-job</string>
  <key>StartInterval</key>
  <integer>86400</integer>
  <key>StandardOutPath</key>
  <string>/absolute/path/to/give-me-job/output/logs/gmj-cron-run.out.log</string>
  <key>StandardErrorPath</key>
  <string>/absolute/path/to/give-me-job/output/logs/gmj-cron-run.err.log</string>
</dict>
</plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/com.gmj.cron-run.plist`. `StartInterval` is
in seconds (86400 = daily); a `StartCalendarInterval` dict is the alternative for a fixed
time-of-day schedule.

### Portable `crontab` example

```
# Daily at 03:00 — invoke the wrapper directly, NOT prefixed by shell flock(1).
0 3 * * * cd /absolute/path/to/give-me-job && bash scripts/ops/gmj_cron_run.sh >> output/logs/gmj-cron-run.log 2>&1
```

Note there is **no `flock(1)` prefix** on this line. Unlike common Linux cron-locking recipes,
this repo's own macOS dev machine has no `flock(1)` shell utility (`flock` is a `util-linux`
package command, absent from macOS's BSD userland by default) — and none is needed here anyway:
`scripts/ops/gmj_cron_run.sh` already implements its own overlap guard internally via Python's
`fcntl.flock(LOCK_EX | LOCK_NB)`, so no external `flock` prefix is correct or required.

### Fail-closed overlap behavior

The wrapper exits non-zero the instant it finds `.pipeline/cron.lock` already held (visible to
cron's mail-on-error, or to `launchd`'s `StandardErrorPath` log) — it never retries and never
queues a second overlapping tick. The lock is acquired before the `claude` invocation and held
for the wrapper's entire outer lifetime (the `claude -p` call is never backgrounded), so it is
only released once the whole scheduled run completes.
