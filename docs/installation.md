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
a `curl` fetch of the raw script:

```bash
curl -fsSL <raw-url>/install.sh | bash
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
  bash -c "curl -fsSL <raw-url>/install.sh | bash"
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

## Python render dependencies

The CV / cover-letter / interview-prep renderers require a Python 3 environment.
`install.sh` bootstraps and reuses a project-local `.venv` and installs every dependency
file through `.venv/bin/python -m pip` — **never a bare system `pip`/`pip3`** — so installs
stay tied to that venv's own interpreter rather than polluting the system Python. If you are
installing manually instead of running `install.sh`, create and activate the same `.venv`
first, then install through it (same order `install.sh` uses):

```bash
python3 -m venv .venv
```

Envelope validation requires `jsonschema`:

```bash
.venv/bin/python -m pip install -r scripts/contracts/requirements.txt
```

The `gmj-dashboard` Textual TUI cockpit requires a pinned `textual`:

```bash
.venv/bin/python -m pip install -r scripts/dashboard/requirements.txt
```

This installs the render stack — notably **reportlab** (the built-in ReportLab CV layout
engine), **PyYAML**, **Jinja2**, and **pypdf** — plus the document-extraction support
libraries (`python-docx`, `openpyxl`, `Pillow`, `PyMuPDF`). **WeasyPrint** ships in the same
file and stays optional (only needed for HTML-template rendering):

```bash
.venv/bin/python -m pip install -r scripts/cv/requirements.txt
```

The preferences validator (`gmj_validate_preferences.py`) requires `PyYAML` + `jsonschema`:

```bash
.venv/bin/python -m pip install -r scripts/preferences/requirements.txt
```

---

## Cyrillic fonts (ua / ru)

Rendering **ua / ru Cyrillic** CVs needs a Unicode font. The **bundled DejaVu fonts** under
`scripts/cv/fonts/` (`DejaVuSans.ttf`, `DejaVuSans-Bold.ttf`) cover this, so **no system
font install is required**. If DejaVu is unavailable the renderer falls back to Helvetica
(Latin-only).

---

## Verifying an install

On the target host, in a fresh Claude Code session, confirm the four acceptance checks:

1. The `gmj-*` hooks fire.
2. An `en` and a `ua` CV render.
3. A dry pipeline run passes.
4. `.claude/settings.json` hook paths resolve on the target host.

The deterministic slice of this install (temp-dir install, payload census, idempotent
settings-merge, the four acceptance checks, and the removal dry-run) is machine-verified by
`tests/test_gmj_install.py` and `tests/test_gmj_remove_gsd.py`.

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
