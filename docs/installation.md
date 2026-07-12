# Installation — Standalone `gmj-core` install

give-me-job ships as a **self-contained, zero-dependency installer** that stages the
standalone `gmj-core/` payload onto any Claude Code runtime and merges its hook
registrations without clobbering user- or framework-owned settings. This page covers the
standalone install path and the Python render dependencies.

For running the collective once it is installed, see the operator guide in
[docs/RUNBOOK.md](RUNBOOK.md) §1. For the `config/*` files you populate afterward, see
[configuration.md](configuration.md); for the scripts the install stages, see
[cli-tools.md](cli-tools.md).

---

## Quick install (recommended)

The steps below (payload staging, hook merge, Python render dependencies) are automated by
one script:

```bash
bash gmj-core/bin/install.sh
```

It is safe to re-run — the script is idempotent (INSTALL-02).

---

## Fresh install (no local checkout)

`install.sh` also supports running with no existing checkout on disk — piped straight from
a `curl` fetch of the raw script, served from the public
[`give-me-job-now`](https://github.com/dallask/give-me-job-now) mirror (the script itself must
be fetchable without auth; the clone it performs still defaults to the private repo below):

```bash
curl -fsSL https://raw.githubusercontent.com/dallask/give-me-job-now/main/gmj-core/bin/install.sh | bash
```

In this mode the script clones the repository into a new directory (`give-me-job` by
default) before continuing the same install flow (`.venv` bootstrap, Python dependency
install, payload/config staging).

- **SSH prerequisite.** With no overrides, the script clones the **private** SSH remote
  `git@github.com:dallask/give-me-job.git` — the invoking host must already have SSH access
  configured (an SSH key registered with GitHub) for the default fresh-clone invocation to
  succeed.
- **`GMJ_REPO_URL`** overrides the git remote to clone (e.g. an HTTPS URL or a different
  fork). It must be a valid git remote; values are passed to `git clone` with a `--`
  option-terminator so they are always treated as a literal remote, never as a flag.
- **`GMJ_INSTALL_DIR`** overrides the destination directory name (default `give-me-job`).
  It must be a plain relative directory name — absolute paths, embedded path separators,
  and `..` segments are rejected — and the script refuses to clone into a path that already
  exists (file, directory, or symlink).

```bash
GMJ_REPO_URL=https://github.com/dallask/give-me-job.git \
GMJ_INSTALL_DIR=my-give-me-job \
  bash -c "curl -fsSL https://raw.githubusercontent.com/dallask/give-me-job-now/main/gmj-core/bin/install.sh | bash"
```

---

## What gets installed

### The `gmj-core/` payload

`gmj-core/` is the standalone install payload, built by `scripts/gmj_build_payload.py`
(PACKAGE-01). It vendors the full app payload — `agents/`, `skills/`, `commands/`, `hooks/`,
`scripts/`, `schemas/`, `config/`, `templates/` — plus a `bin/` installer, a `VERSION`
file, and a file-hash census manifest (a path → SHA-256 map) that makes the payload
self-contained and tamper-detectable.

The payload is derived by a **fresh disk census** of `gmj-*` / `gmj_*` app artifacts, not by
replaying any rename map, so files birthed after the original rebrand are never silently
missed. User-data config (a populated `candidate.yaml`) is **never** vendored — only
`<name>.sample` templates ship, so no real PII travels with the payload.

### The installer — `gmj-core/bin/gmj-tools.cjs`

`gmj-core/bin/gmj-tools.cjs` is a vendored, **zero-dependency** installer written in pure
Node builtins (`node:fs`, `node:path`, `node:crypto`) — no `npm install`, no transitive
dependencies (supply-chain hardening). It stages the payload into a caller-supplied target
directory and then idempotently **merges** the target's `.claude/settings.json`.

Invoke it from the source root:

```bash
node gmj-core/bin/gmj-tools.cjs install <target-dir>
```

Installer behavior:

- **Path containment.** The target dir and every manifest path are resolved absolute and
  asserted to stay under the install root before any write; `..` traversal and symlink
  escape are rejected.
- **Overwrite vs scaffold.** App code (agents/skills/commands/hooks/scripts/schemas + app
  config) is **overwrite-on-install**; user-data config (candidate / sources / credentials /
  preferences + language overlays) is **scaffold-if-absent** — a populated profile is never
  clobbered.
- **Settings merge.** `.claude/settings.json` is parsed-then-throw on malformed JSON (never
  silently overwritten), merged at the inner per-matcher `hooks[]` command level, and
  written only when the bytes change. A re-install is byte-identical (idempotent).

---

## Prerequisites

`install.sh` requires **Python 3.9 or newer**. The check runs before any `.venv` is
created, as part of the same aggregate-then-report prerequisite section that checks
`git`/`node`/`npx`/`pip` — a too-old interpreter is reported alongside any other missing
prerequisite in one aggregated stderr report, never a raw traceback.

## Python render dependencies

The CV / cover-letter / interview-prep renderers require a Python 3 environment.
`install.sh` bootstraps and reuses a project-local `.venv` and installs every dependency
file through `.venv/bin/python -m pip` — **never a bare system `pip`/`pip3`** — so installs
stay tied to that venv's own interpreter rather than polluting the system Python.

`install.sh` **aggregates and installs every `scripts/*/requirements.txt` and
`scripts/requirements-*.txt` file** it finds, mirroring this repo's own CI pattern in
[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) exactly — the loop
self-extends as new subsystem requirements files are added, so the installer and CI never
drift out of sync. The full current set:

- `scripts/contracts/requirements.txt` — envelope validation (`jsonschema`)
- `scripts/dashboard/requirements.txt` — the `gmj-dashboard` Textual TUI cockpit (`textual`)
- `scripts/cv/requirements.txt` — the render stack: **reportlab** (built-in ReportLab CV
  layout engine), **PyYAML**, **Jinja2**, **pypdf**, plus document-extraction support
  (`python-docx`, `openpyxl`, `Pillow`, `PyMuPDF`). **WeasyPrint** ships in the same file
  and stays optional (only needed for HTML-template rendering)
- `scripts/preferences/requirements.txt` — the preferences validator
  (`gmj_validate_preferences.py`): `PyYAML` + `jsonschema`
- `scripts/offers/requirements.txt` — offer discovery: `firecrawl-py`, `python-dotenv`
- `scripts/pipeline/requirements.txt` — pipeline control: `PyMuPDF`, `PyYAML`
- `scripts/publish/requirements.txt` — release automation: `python-semantic-release`,
  `PyYAML`
- `scripts/runtime/requirements.txt` — the EXPERIMENTAL Claude Agent SDK runtime prototype:
  `claude-agent-sdk`
- `scripts/requirements-cleanup.txt` — the cleanup wizard (root-level file, matched by the
  second glob term, not `scripts/*/requirements.txt`): `questionary`

If you are installing manually instead of running `install.sh`, create and activate the
same `.venv` first, then install through it (same aggregation `install.sh` uses):

```bash
python3 -m venv .venv
for req in scripts/*/requirements.txt scripts/requirements-*.txt; do
  .venv/bin/python -m pip install -r "$req"
done
```

---

## Cyrillic fonts (ua / ru)

Rendering **ua / ru Cyrillic** CVs needs a Unicode font. The **bundled DejaVu fonts** under
`scripts/cv/fonts/` (`DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`) cover this, so **no system
font install is required**. If DejaVu is unavailable the renderer falls back to Helvetica
(Latin-only).

---

## Verifying an install

`install.sh` runs a **post-install import smoke check automatically** right after the
requirements-aggregation loop: it imports one representative core package from each
always-required requirements file (`yaml`, `jsonschema`, `textual`, `reportlab`, `jinja2`)
through the newly-installed `.venv/bin/python` and prints `OK` on success. WeasyPrint and
`firecrawl-py` are intentionally excluded from this check — WeasyPrint has documented
optional system-library failure modes, and `firecrawl-py` is optional/API-key-gated, so
neither should false-fail a legitimately optional/degraded install. If the smoke check
fails, `install.sh` prints a clear stderr message naming the failure and exits 1 — never a
raw Python traceback.

### Wizard output

`install.sh` presents its 5 stages as a colored wizard when run in an interactive terminal:
bold cyan `[N/5]` stage headers, a green checkmark on each successful step, and an animated
spinner (bash-only, no dependency) during long-running steps (venv creation, each
per-requirements-file `pip install`, `git clone` in fresh-clone mode, and the
`gmj-tools.cjs install` delegate call). When stdout is **not** a TTY (piped, redirected, or
run in CI) the script automatically falls back to the same information as plain,
spinner-free text — zero ANSI escape bytes are ever written to non-TTY output. On any step
failure the script prints a red failure banner, a remediation hint specific to that failure
mode (e.g. an install link, a `pyenv`/package-manager suggestion, or a manual re-run command
with `--verbose`), and the tail of the real captured command output — never a raw,
uncaptured error dump. The final "Next steps" block is state-aware: it inspects
`config/candidate.yaml` and `config/sources.yaml` and leads with whichever guidance is
actually relevant — "run your first real offer" when both look populated, or "populate
candidate.yaml" (with a pointer to `/gmj-interview`) when candidate.yaml still looks
template-shaped.

On the target host, in a fresh Claude Code session, confirm the four acceptance checks:

1. The `gmj-*` hooks fire.
2. An `en` and a `ua` CV render.
3. A dry pipeline run passes.
4. `.claude/settings.json` hook paths resolve on the target host.

The deterministic slice of this install (temp-dir install, payload census, idempotent
settings-merge, the four acceptance checks, and the removal dry-run) is machine-verified by
`tests/test_gmj_install.py` and `tests/test_gmj_remove_gsd.py`. The one-script installer
(`gmj-core/bin/install.sh` itself — prerequisite aggregation, run-in-place vs. fresh-clone
mode detection, idempotent `.venv` reuse, and the shell-injection/symlink-safety
regressions) is machine-verified by `tests/test_gmj_install_script.py`.

> **Note (DV-21 — deferred).** A real **cross-machine clean-runtime install** — copying the
> payload to a second host with dependencies absent and a different OS, running the
> installer, `pip install`-ing the requirements, and confirming the four acceptance checks
> live — needs a genuinely clean external host plus human judgment and cannot be
> auto-asserted from an in-repo subagent. It is recorded as a **non-blocking** deferred
> verification (DV-21, `clean_runtime_install_uat_deferred`); the in-repo deterministic
> substrate is green.

---

## Next steps

- Populate `config/candidate.yaml` and the search scope in `config/sources.yaml` — see
  [configuration.md](configuration.md).
- Run your first real offer end to end — see [docs/RUNBOOK.md](RUNBOOK.md) §1–§3.
