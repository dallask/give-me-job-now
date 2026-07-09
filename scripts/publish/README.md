# scripts/publish/ — sanitize-and-mirror publisher

Operator documentation for `gmj_publish_mirror.sh`, a manual, deterministic tool that produces a
PII-free public mirror of this private repo's `feature/gsd` branch (default) and — on operator
confirmation — pushes it to a separate public GitHub repo:
**https://github.com/dallask/give-me-job-now** (MIT license).

This publishes a **snapshot mirror**, not a synced fork: the private repo keeps real candidate
data for daily use; the destination repo ships the same code/docs with all PII stripped and
`config/*.yaml` swapped for the `gmj-core/config/*.sample` synthetic payloads.

> **Destination visibility.** The script is **visibility-agnostic**: it never checks or requires
> the destination repo's GitHub visibility (private vs. public) before pushing. During setup and
> testing the destination repo (`give-me-job-now`) may be **private**; the operator flips it to
> public manually, on GitHub, only once satisfied with the mirrored result. The PII-safety gates
> (denylist `git grep` + gitleaks) are HARD regardless of destination visibility — that guarantee
> does not depend on, or change with, whether the repo happens to be public yet.

## Prerequisites

- **`git-filter-repo`** — required, hard-fails if missing. Install: `pip install git-filter-repo`
  (or `brew install git-filter-repo` on macOS).
- **`gitleaks`** — recommended, not required. If present, the verification gate runs it as a
  **HARD** check (any finding aborts the publish). If absent, the script prints a prominent
  warning and continues — the PII-denylist `git grep` gate still hard-gates regardless.

## One-time setup: the real PII map + denylist

Two files hold your **real** PII tokens and must **never** be committed. They are gitignored in
this repo (`scripts/publish/replacements.txt`, `scripts/publish/pii-denylist.txt`) and are also
path-removed from the mirror itself as defense in depth (`scripts/publish/paths-to-remove.txt`).
Only their `.sample` templates ship.

1. Copy the templates:
   ```
   cp scripts/publish/replacements.sample.txt scripts/publish/replacements.txt
   cp scripts/publish/pii-denylist.sample.txt scripts/publish/pii-denylist.txt
   ```
2. Fill in the real values by reading them **from `config/candidate.yaml`** (never hardcode them
   anywhere else). The templates reference each token by its YAML location, e.g.:
   - `contact.phone`
   - `contact.email[0]` (personal email), `contact.email[1]` (gmail)
   - `contact.website.personal[*]` (personal domains)
   - `contact.messengers.telegram` (handle)
   - the CV-subject `name` (Latin variant) and its Cyrillic variant (if `candidate.ua.yaml` /
     `candidate.ru.yaml` carry one)
   - `contact.address`
3. `scripts/publish/replacements.txt` format: one `literal==>replacement` mapping per line, fed to
   `git filter-repo --replace-text` (rewrites every occurrence across all history).
4. `scripts/publish/pii-denylist.txt` format: one literal token per line. The verification gate
   `git grep`s the filtered mirror's entire history for every line in this file; **zero hits**
   are required to proceed.

## How to run

**Always dry-run first:**

```
scripts/publish/gmj_publish_mirror.sh --dry-run
```

`--dry-run` is the **default-safe mode** — passing no flags at all is equivalent to `--dry-run`.
It performs every stage (clone, filter, redact, config swap, doc injection, verification gate)
and stops at the push boundary, printing exactly what *would* be pushed, without ever contacting
the remote.

To actually publish, you must explicitly opt out of dry-run and confirm:

```
scripts/publish/gmj_publish_mirror.sh --no-dry-run
```

This prompts for a typed `yes` confirmation before pushing (skip the prompt with `--yes`, e.g. for
scripted/CI use — see the GitHub Action below).

### Flag reference

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | (implicit default) | Do everything except the final push; never contacts the remote. |
| `--no-dry-run` | — | Explicitly disable dry-run mode to allow a real push. |
| `--yes` | off | Skip the interactive typed confirmation before pushing. |
| `--source-branch <name>` | `feature/gsd` | Branch of this repo to mirror from. |
| `--public-remote <url>` | `git@github.com:dallask/give-me-job-now.git` | Public git remote URL. |
| `--public-branch <name>` | `main` | Branch to push on the public remote. |
| `--help` | — | Print usage and exit 0. |

## What the script does, in order

1. Checks prerequisites (`git`, `git-filter-repo`; detects `gitleaks`).
2. **Working-tree guard**: resolves the repo root, requires a clean working tree, confirms the
   source branch exists. This is safety-critical — the script never operates on `$repo_root/.git`.
3. Clones the source branch into a fresh `mktemp -d` directory (asserted to never equal, or live
   inside, the repo root) with an `EXIT` trap that removes it on every exit path.
4. Requires the real `scripts/publish/replacements.txt` + `pii-denylist.txt` to exist (read from
   the **private** repo root, never from the temp clone).
5. Runs `git filter-repo --invert-paths --paths-from-file scripts/publish/paths-to-remove.txt` to
   drop `.planning/`, real personal source documents, generated per-offer artifacts, and the
   (gitignored) real PII map/denylist themselves, from every commit.
6. Runs `git filter-repo --replace-text scripts/publish/replacements.txt` to redact every real PII
   token to its sample-equivalent placeholder, across all history.
7. **Verification gate (hard)** — PII-denylist: `git grep`s every line of the real denylist across
   **all** history refs in the filtered clone, at this point (redacted, but *before* the public
   docs injection below) — any hit aborts (naming only the fact of a hit + ref, never printing the
   token value). This ordering is deliberate: `public-assets/README.public.md`/`LICENSE` are
   human-authored, human-reviewed public content (e.g. an intentional author name/site credit) that
   would otherwise false-positive against the same tokens used to catch *accidental* leaks in the
   bulk historical commit corpus. The gate protects the historical data; it does not re-scan
   curated public-facing content added after it.
8. Overwrites `config/candidate.yaml` (+ `.ua`/`.ru` overlays), `config/credentials.yaml`, and
   `config/preferences.yaml` in the temp clone with the `gmj-core/config/*.sample` payloads, then
   injects `public-assets/README.public.md` → `README.md` and `public-assets/LICENSE` → `LICENSE`,
   committing all of it as one swap commit (the real commit author identity is **preserved**, not
   rewritten — only this one swap commit is added as the new HEAD).
9. **Verification gate (hard-when-present)** — gitleaks: if `gitleaks` is present, runs
   `gitleaks detect` over the **full final state** (including the just-injected docs) as a second
   hard gate — a different class of check (secret patterns, not name-matching), so it's safe to run
   after injection too. If absent, prints a warning and continues (the denylist grep above still
   gates regardless).
10. **Push stage**: in `--dry-run` mode, prints the would-be push target and stops — no remote
    contact. Otherwise, prompts for confirmation (unless `--yes`), then
    `git push --force public HEAD:$PUBLIC_BRANCH`.

## Safety model

- The script **never** filters the live working tree — only a throwaway `mktemp -d` clone, always
  cleaned up via an `EXIT` trap.
- `--dry-run` is the default-safe mode; a real push requires an explicit `--no-dry-run`.
- The verification gate is **HARD**: the PII-denylist `git grep` always gates; `gitleaks` gates
  whenever installed. Neither can be bypassed by a flag.
- The real PII map + denylist never reach the public repo: gitignored in the private repo AND
  path-removed from the mirror itself (defense in depth).

## Re-running / force-push behavior

Re-running the script regenerates the same filtered output deterministically from the same
committed rules + your local real maps. **Pushing to the public `main` branch is effectively a
force-push of regenerated history** — the public mirror's history is not meant to be manually
amended or merged into; each publish run replaces it wholesale.

## Optional: GitHub Action

`.github/workflows/publish-mirror.yml` wraps this script for `workflow_dispatch`-only (manual
trigger) CI use. It is **never** wired to `push`/`pull_request`/`schedule`. See the comments in
that file for the required repository secrets (the real replacements/denylist content, plus a
`PUBLIC_REPO_PAT` with push access to the public repo).

## Release pipeline (ships into the public mirror)

Unlike `publish-mirror.yml` (excluded from the mirror — see `paths-to-remove.txt`), a second
workflow, **`.github/workflows/release.yml`**, ships *into* the public mirror itself, because the
public repo needs its own release CI (this repo's own private CI doesn't run there).

### What ships

- `.github/workflows/release.yml` — triggers on `push` to `main` in the **public** repo, which is
  exactly what `gmj_publish_mirror.sh`'s force-push does on every publish (no cross-repo dispatch
  needed).
- `scripts/publish/milestone-releases.yaml` — real, historical release backfill data: one entry
  per actually-shipped milestone (v1.0.0..v4.0.0), each anchored to a real commit by an **exact
  commit-message match**, never a hardcoded SHA (SHAs are rewritten by `git-filter-repo` on every
  mirror publish; commit messages survive verbatim).
- `scripts/publish/gmj_bootstrap_releases.py` — reads `milestone-releases.yaml`, resolves each
  anchor commit, and idempotently (delete-then-recreate) creates the tag + GitHub Release.
- `pyproject.toml` (`[tool.semantic_release]`) — config for `python-semantic-release`, which
  analyzes conventional commits beyond the last milestone anchor to cut further real releases
  automatically.

### One-time manual setup in the PUBLIC repo

`release.yml` uses the default `GITHUB_TOKEN` (no PAT) to push tags and create releases — but some
org/repo defaults ship that token as read-only. In the **public** repo's GitHub settings:

```
Settings → Actions → General → Workflow permissions → "Read and write permissions"
```

This is required once, manually, before `release.yml` can push tags/releases on its own.

### Re-publish semantics (idempotent, fresh every run)

Every mirror publish force-rewrites the public repo's entire history (`git-filter-repo`, not
incremental), which orphans previously-created release tags. `release.yml` compensates by
**recreating all 5 milestone releases fresh, every time it runs** — this is by design, per the
operator's explicit re-publish choice, not a bug. Practically: do not expect a GitHub Release's
"created at" timestamp in the UI to stay stable across republishes; the release **notes/content**
stay accurate and pinned to the real historical `date` in `milestone-releases.yaml`, but the
Release object itself is deleted and recreated on every run.

This same orphaning affects any release `python-semantic-release` cuts on its own beyond the
last milestone (e.g. a real `v4.1.0`): its tag survives a force-rewrite of `main`, but the commit
it points to — including that release's `CHANGELOG.md` — does not, since `main` was rewritten
from scratch on the private side and never included that commit. `semantic-release` only checks
whether the tag exists, not whether it's still reachable, so it would otherwise conclude "already
released" and silently skip re-cutting a release that `main` no longer actually contains (this
was a real gap found and fixed after CI surfaced a missing `CHANGELOG.md`). `release.yml`'s
**"Prune orphaned tags/releases from previous mirror rewrites"** step runs before both the
milestone backfill and `semantic-release`: it deletes any tag (and its GitHub Release, if any)
that is not an ancestor of the current `HEAD`, so every run — milestone tags and
`semantic-release`'s own — always recomputes fresh against what's really on `main`.

### PUBLIC_REPO_PAT scope (cross-reference)

If you use `publish-mirror.yml`'s CI path to publish, note that `PUBLIC_REPO_PAT` now needs
`workflow` scope in addition to push/contents access (classic PAT: `repo` + `workflow`;
fine-grained PAT: Contents read/write + Workflows read/write) — see the updated secret comment in
`.github/workflows/publish-mirror.yml`. This widening is required because `release.yml` (unlike
`publish-mirror.yml` itself) now ships into and must run inside the public repo, and GitHub
requires `workflow` scope on any token that pushes a commit touching `.github/workflows/*`.
