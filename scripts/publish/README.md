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
7. Overwrites `config/candidate.yaml` (+ `.ua`/`.ru` overlays), `config/credentials.yaml`, and
   `config/preferences.yaml` in the temp clone with the `gmj-core/config/*.sample` payloads, then
   injects `public-assets/README.public.md` → `README.md` and `public-assets/LICENSE` → `LICENSE`,
   committing all of it as one swap commit (the real commit author identity is **preserved**, not
   rewritten — only this one swap commit is added as the new HEAD).
8. **Verification gate (hard)**: `git grep`s every line of the real denylist across **all**
   history refs in the filtered clone — any hit aborts (naming only the fact of a hit + ref, never
   printing the token value). Then, if `gitleaks` is present, runs `gitleaks detect` over the
   filtered clone as a second hard gate; if absent, prints a warning and continues (the denylist
   grep alone still gates).
9. **Push stage**: in `--dry-run` mode, prints the would-be push target and stops — no remote
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
