# Commands — the give-me-job command surface

> **Every command named here resolves to a real file under `.claude/commands/`.**
> `python3 tests/test_docs_current.py` (`test_every_docs_command_exists`) fails the build if any
> `/gmj-…` token drifts from disk. Command **behaviour** is defined by each command file's own body;
> this page is the reader-facing catalog of *what each command is for* and *how the commands relate*.

The collective exposes **13 slash commands**: **7 top-level** entry points
(`.claude/commands/gmj-*.md`) and **6 pipeline steps** grouped under `.claude/commands/gmj-pipeline/`
(bare leaf filenames such as `scout.md` — the leaves carry no per-file prefix). Top-level commands
are the surfaces a user invokes directly; the pipeline leaves are thin per-step wrappers that name
exactly one script or one `Task` of the runtime control loop.

See [agents.md](agents.md) for the roster each command drives, [flows.md](flows.md) for the
end-to-end sequences these commands trigger, and [cli-tools.md](cli-tools.md) for the deterministic
scripts they shell out to.

> **Leaf-naming.** The `gmj-pipeline` group directory carries the prefix, but its leaves are bare.
> A leaf command is invoked as `/gmj-pipeline/scout` and its file lives at
> `.claude/commands/gmj-pipeline/scout.md`. Cross-links to a leaf use its bare rendered anchor,
> e.g. [the freeze step](commands.md#freeze).

---

## Top-level commands (7)

These seven are invoked directly by a user in a Claude Code session.

### gmj-collective

- **Purpose:** Run the `gmj-orchestrator` collective — the interactive hub. Loads the routing schema
  (User Request → Routing Analysis → Agent Selection → Task Delegation → Quality Gate → Result) and
  the CV toolchain, then awaits a goal in the same turn.
- **File:** `.claude/commands/gmj-collective.md`
- **Drives:** `gmj-orchestrator` (hub, the only `Task` holder) and, through it, every spoke.
- **When to use:** Conversational, human-in-the-loop work — routing a free-form goal, running the
  simple full-CV render, or letting the hub decide which spoke to delegate to.

### gmj-pipeline-run

- **Purpose:** Run the full **offer → artifacts** pipeline end to end: dual-mode (human-in-the-loop
  or autonomous), non-bypassable hard gates (Gate A truth, Gate B fit), and a frozen retry cap.
- **File:** `.claude/commands/gmj-pipeline-run.md`
- **Drives:** the runtime control loop — `gmj_state_write.py` init_run, then a
  `gmj_route.py` → `gmj_check_offer.py` → `Task(spoke)` loop across scout, freeze, compose, Gate A,
  Gate B, and deliver.
- **When to use:** One offer, whole flow, in a single command. See the
  [single-offer pipeline flow](flows.md#single-offer-pipeline).

### gmj-batch

- **Purpose:** Select several shortlisted offers and freeze + run each as its own gated pipeline under
  a single resumable **batch manifest**, with isolated per-offer retry counters.
- **File:** `.claude/commands/gmj-batch.md`
- **Drives:** `gmj_batch.py` (the deterministic batch control plane) which runs the existing
  single-offer loop once per selected offer.
- **When to use:** Producing artifacts for a shortlist of offers in one resumable run. See the
  [batch flow](flows.md#batch-multi-offer).

### gmj-interview

- **Purpose:** Gap-filling interviewer. Reads the real profile + coverage manifest, asks **only about
  real gaps** one question at a time, captures search preferences behind the validator guard, and
  hands profile facts to `gmj-candidate-configurator`.
- **File:** `.claude/commands/gmj-interview.md`
- **Drives:** a standalone persona (no `Task`) that writes `config/preferences.yaml` behind
  `gmj_validate_preferences.py` and routes facts to `gmj-candidate-configurator` for the canonical
  YAML write.
- **When to use:** Before a run, to fill profile gaps and record narrowing/ranking preferences. See
  the [interview / preferences flow](flows.md#interview--preferences-capture).

### gmj-runs

- **Purpose:** Terse, **read-only** timeline of pipeline runs and batches; surfaces (never executes)
  the resume command for each.
- **File:** `.claude/commands/gmj-runs.md`
- **Drives:** `gmj_runs.py` (the read-only inspector — mirror image of the `gmj_batch.py` writer).
- **When to use:** Inspecting run/batch state and finding the exact resume command. See the
  [runs inspection flow](flows.md#runs-inspection).

### gmj-dashboard

- **Purpose:** Launch the live **btop-style pipeline cockpit** — a read-only Textual timeline of
  pipeline run/batch state by default, with an explicit `--manage` flag that opts into the mutating
  action layer (`r`/`R`/`b`/`m`/`c` keys). As a read-only inspector persona it holds no `Task` and
  never spawns a spoke.
- **File:** `.claude/commands/gmj-dashboard.md`
- **Drives:** `python3 scripts/dashboard/gmj_dashboard.py` (read-only default; `--manage` opt-in).
- **When to use:** Live, at-a-glance inspection of pipeline run/batch state; add `--manage` when you
  want the opt-in action layer to drive runs/batches/config from the board. See the
  [dashboard flow](flows.md#dashboard).

### gmj-template

- **Purpose:** Paste a CV design screenshot → generate a reusable `{{ candidate.* }}`-bound
  HTML/Jinja2 template under `templates/cv/`, matched to the design via a bounded WeasyPrint
  compare==ship loop (cap 5, diff-ratio ≤ 0.10, keep-best).
- **File:** `.claude/commands/gmj-template.md`
- **Drives:** `gmj-template-creator` (spawned as the sole `Task`), plus `gmj_visual_diff.py`,
  `gmj_template_lint.py`, and `gmj_render_cv.py` in the compare-and-ship loop.
- **When to use:** Turning a branded design into a reusable render template. See the
  [template creation flow](flows.md#template-creation).

---

## Pipeline steps (6) — `gmj-pipeline/`

Each leaf is a **thin wrapper** naming exactly one script or one `Task` of the runtime control loop
that [`/gmj-pipeline-run`](flows.md#single-offer-pipeline) chains automatically — no control logic is
duplicated. Run them individually to drive or resume a single step.

### scout

- **Invoked as:** `/gmj-pipeline/scout`
- **Purpose:** Step 1 — run the `gmj-offer-scout` spoke (board-search or single-offer), scoped by
  `config/sources.yaml`, then hand the fielded draft to the freeze step.
- **File:** `.claude/commands/gmj-pipeline/scout.md`
- **Drives:** `Task(gmj-offer-scout)`; hands off to [freeze](commands.md#freeze).

### freeze

- **Invoked as:** `/gmj-pipeline/freeze`
- **Purpose:** Step 2 — freeze the offer draft into an immutable offer-spec and freeze
  mode/cap/run_id into run state (deterministic; no LLM).
- **File:** `.claude/commands/gmj-pipeline/freeze.md`
- **Drives:** `gmj_freeze_offer.py` (offer-spec) and `gmj_state_write.py` (run state).

### compose

- **Invoked as:** `/gmj-pipeline/compose`
- **Purpose:** Step 3 — run the `gmj-artifact-composer` spoke for **one** artifact type
  (`cv` | `cover_letter` | `interview_prep`); names `gmj_record_retry.py` for the per-type counter.
- **File:** `.claude/commands/gmj-pipeline/compose.md`
- **Drives:** `Task(gmj-artifact-composer)` and `gmj_record_retry.py`.

### verify

- **Invoked as:** `/gmj-pipeline/verify`
- **Purpose:** Step 4 — **Gate A** (truth). Run the deterministic truth check
  (`gmj_check_truth.py`, exit 0/1, no bypass) and record the verdict (`gmj_record_gate.py`).
- **File:** `.claude/commands/gmj-pipeline/verify.md`
- **Drives:** `gmj_check_truth.py` then `gmj_record_gate.py`. Gate A must pass before Gate B.

### evaluate

- **Invoked as:** `/gmj-pipeline/evaluate`
- **Purpose:** Step 5 — **Gate B** (target-fit). Run the deterministic fit scorer
  (`gmj_score_fit.py`, exit 0/1, no bypass) and record the verdict (`gmj_record_gate.py`).
- **File:** `.claude/commands/gmj-pipeline/evaluate.md`
- **Drives:** `gmj_score_fit.py` then `gmj_record_gate.py`.

### generate

- **Invoked as:** `/gmj-pipeline/generate`
- **Purpose:** Step 6 — run the `gmj-cv-generator` spoke to render a **gate-passed** artifact to PDF
  via `scripts/cv/gmj_render_cv.py`.
- **File:** `.claude/commands/gmj-pipeline/generate.md`
- **Drives:** `Task(gmj-cv-generator)` and `gmj_render_cv.py`; delivery is guarded by
  `gmj_check_delivery.py` (Gate A ∧ Gate B recorded pass).

---

## Command → flow map

| Command | Flow | Mode |
|---------|------|------|
| `/gmj-pipeline-run` | [Single-offer pipeline](flows.md#single-offer-pipeline) | dual-mode, gated |
| `/gmj-pipeline/scout` … `/gmj-pipeline/generate` | [Per-step pipeline](flows.md#per-step-pipeline) | one step each |
| `/gmj-batch` | [Batch (multi-offer)](flows.md#batch-multi-offer) | dual-mode, gated, resumable |
| `/gmj-interview` | [Interview / preferences capture](flows.md#interview--preferences-capture) | interactive |
| `/gmj-template` | [Template creation](flows.md#template-creation) | bounded compare-loop |
| `/gmj-runs` | [Runs inspection](flows.md#runs-inspection) | read-only |
| `/gmj-dashboard` | [Dashboard](flows.md#dashboard) | read-only (opt-in `--manage`) |
| `/gmj-collective` | [Simple full-CV render](flows.md#simple-full-cv-render) | interactive |

## Related sections

- [agents.md](agents.md) — the 9-agent roster these commands drive.
- [flows.md](flows.md) — the end-to-end runtime sequences.
- [cli-tools.md](cli-tools.md) — the deterministic scripts each command shells out to.
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) §5.1 — the authoritative runtime control loop.
