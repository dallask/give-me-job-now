#!/usr/bin/env bash
#
# gmj_publish_mirror.sh — sanitize-and-mirror publisher.
#
# Builds a PII-free public mirror of a private give-me-job branch (default
# feature/gsd) into a fresh throwaway clone, strips paths + redacts content via
# git-filter-repo, swaps config/*.yaml for the gmj-core sample payloads, injects
# a public README + LICENSE, runs a HARD verification gate (PII-denylist git
# grep + gitleaks), and — unless --dry-run — pushes the result to a separate
# public GitHub repo (https://github.com/dallask/give-me-job-now, MIT).
#
# SAFETY MODEL (read before running):
#   - This script NEVER filters the live working tree. It always clones the
#     source branch into a fresh `mktemp -d` directory and operates only on
#     that throwaway clone. An EXIT trap removes the clone on every exit path.
#   - --dry-run is the DEFAULT-SAFE mode: it performs every stage except the
#     final push and never contacts the remote. You must pass an EXPLICIT
#     non-dry-run invocation to push.
#   - Re-running regenerates the same filtered output from the same committed
#     input + your local (gitignored) redaction/denylist maps. Pushing to the
#     public `main` branch is EFFECTIVELY A FORCE-PUSH of regenerated history —
#     the public repo's history is not meant to be manually amended.
#
# See scripts/publish/README.md for full operator documentation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---- defaults -----------------------------------------------------------
DRY_RUN=1
ASSUME_YES=0
SOURCE_BRANCH="feature/gsd"
PUBLIC_REMOTE="git@github.com:dallask/give-me-job-now.git"
PUBLIC_BRANCH="main"

usage() {
  cat <<'EOF'
Usage: gmj_publish_mirror.sh [options]

Build (and optionally push) a PII-free public mirror of this repo.

Options:
  --dry-run                 Do everything except the final push (DEFAULT).
                             Never contacts the remote in this mode.
  --yes                     Skip the interactive confirmation before pushing
                             (only relevant when --dry-run is NOT set).
  --source-branch <name>    Branch to mirror from (default: feature/gsd).
  --public-remote <url>     Public git remote URL
                             (default: git@github.com:dallask/give-me-job-now.git).
  --public-branch <name>    Branch to push on the public remote (default: main).
  --help                    Show this help and exit 0.

Safety:
  - Always operates on a fresh `mktemp -d` clone, never the live working tree.
  - --dry-run is the default-safe mode; pass no --dry-run flag AND either
    answer "yes" interactively or pass --yes to actually push.
  - The verification gate (PII-denylist git grep + gitleaks) is HARD: any
    finding aborts before any push, in every mode.

See scripts/publish/README.md for the full operator runbook.
EOF
}

# ---- flag parsing ---------------------------------------------------------
# --dry-run is on by default; track whether the operator explicitly disabled it
EXPLICIT_NO_DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-dry-run)
      DRY_RUN=0
      EXPLICIT_NO_DRY_RUN=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --source-branch)
      [ $# -ge 2 ] || { echo "ERROR: --source-branch requires a value" >&2; exit 1; }
      SOURCE_BRANCH="$2"
      shift 2
      ;;
    --public-remote)
      [ $# -ge 2 ] || { echo "ERROR: --public-remote requires a value" >&2; exit 1; }
      PUBLIC_REMOTE="$2"
      shift 2
      ;;
    --public-branch)
      [ $# -ge 2 ] || { echo "ERROR: --public-branch requires a value" >&2; exit 1; }
      PUBLIC_BRANCH="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown flag: $1" >&2
      usage
      exit 1
      ;;
  esac
done

# NOTE: this script's actual publish contract (per PLAN.md) treats --dry-run as
# the flag that OPTS INTO the safe mode, defaulting to dry-run=1 above so a bare
# invocation with no flags is already safe. A real publish requires the operator
# to have NOT passed --dry-run at all (DRY_RUN stays 0 only if neither --dry-run
# nor the default applies) — since we default DRY_RUN=1, a genuine push requires
# no --dry-run flag present in argv. We detect that case via EXPLICIT_NO_DRY_RUN
# for clarity in log output, but the effective gate is simply: DRY_RUN == 0.

step() { printf '\n==> [%s] %s\n' "$(date -u +%H:%M:%S)" "$1"; }
fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

step "Prerequisite check"
command -v git >/dev/null 2>&1 || fail "git is required but not found on PATH."
command -v git-filter-repo >/dev/null 2>&1 || fail "git-filter-repo is required but not found on PATH. Install: pip install git-filter-repo (see scripts/publish/README.md)."

GITLEAKS_PRESENT=0
if command -v gitleaks >/dev/null 2>&1; then
  GITLEAKS_PRESENT=1
  echo "gitleaks detected — will run as a HARD gate."
else
  echo "WARNING: gitleaks not found on PATH — the gitleaks scan will be SKIPPED. The PII-denylist git grep gate still runs and is hard. Install gitleaks for full coverage (see scripts/publish/README.md)."
fi

step "Working-tree guard"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
[ -n "$REPO_ROOT" ] || fail "Could not resolve repo root via git rev-parse --show-toplevel."

if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
  fail "Source repo working tree is not clean. Commit or stash changes first so the mirror reflects committed state."
fi

git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$SOURCE_BRANCH" \
  || git -C "$REPO_ROOT" rev-parse --verify --quiet "$SOURCE_BRANCH" >/dev/null \
  || fail "Source branch '$SOURCE_BRANCH' does not exist in $REPO_ROOT."

step "Resolve real PII map + denylist (from the PRIVATE repo root, never the temp clone)"
REAL_REPLACEMENTS="$REPO_ROOT/scripts/publish/replacements.txt"
REAL_DENYLIST="$REPO_ROOT/scripts/publish/pii-denylist.txt"

[ -f "$REAL_REPLACEMENTS" ] || fail "Missing $REAL_REPLACEMENTS. Copy scripts/publish/replacements.sample.txt to scripts/publish/replacements.txt and fill in the real tokens (see scripts/publish/README.md)."
[ -f "$REAL_DENYLIST" ] || fail "Missing $REAL_DENYLIST. Copy scripts/publish/pii-denylist.sample.txt to scripts/publish/pii-denylist.txt and fill in the real tokens (see scripts/publish/README.md)."

step "Create fresh throwaway clone"
TMPDIR_CLONE="$(mktemp -d "${TMPDIR:-/tmp}/gmj-publish-mirror.XXXXXX")"

cleanup() {
  rm -rf "$TMPDIR_CLONE"
}
trap cleanup EXIT

# Assert the temp clone dir is never equal to, nor inside, the repo root.
case "$TMPDIR_CLONE" in
  "$REPO_ROOT"|"$REPO_ROOT"/*)
    fail "Refusing to operate: temp clone path ($TMPDIR_CLONE) is inside the live repo root ($REPO_ROOT). This is a safety-critical guard against filtering the live tree."
    ;;
esac
[ "$TMPDIR_CLONE" != "$REPO_ROOT" ] || fail "Refusing to operate: temp clone path equals the live repo root."

echo "Temp clone dir: $TMPDIR_CLONE"
git clone --no-local --branch "$SOURCE_BRANCH" "file://$REPO_ROOT" "$TMPDIR_CLONE"

step "filter-repo: path removals"
PATHS_TO_REMOVE="$REPO_ROOT/scripts/publish/paths-to-remove.txt"
[ -f "$PATHS_TO_REMOVE" ] || fail "Missing $PATHS_TO_REMOVE."
git -C "$TMPDIR_CLONE" filter-repo --force --invert-paths --paths-from-file "$PATHS_TO_REMOVE"

step "filter-repo: content redaction (--replace-text)"
git -C "$TMPDIR_CLONE" filter-repo --force --replace-text "$REAL_REPLACEMENTS"

step "VERIFICATION GATE (hard) — PII-denylist git grep across redacted history"
# Runs HERE — after redaction, BEFORE the config-swap + public-docs injection below —
# deliberately. The injected README/LICENSE are human-authored, human-reviewed public
# content (e.g. intentional author name/site credit) that would otherwise false-positive
# against the same denylist tokens used to catch ACCIDENTAL leaks in the bulk historical
# commit corpus. This gate protects the historical data; it does not re-scan curated
# public-facing content added after it. gitleaks (below, after injection) still covers
# the full final state for a different class of check (secret patterns, not name-matching).
DENYLIST_HIT=0
while IFS= read -r token || [ -n "$token" ]; do
  # Skip blank lines and comment lines.
  case "$token" in
    ''|'#'*) continue ;;
  esac
  # Grep across all refs/history in the filtered clone. Never print the value —
  # only report that a hit occurred (offending ref, not the token content).
  if git -C "$TMPDIR_CLONE" grep -q -F -- "$token" $(git -C "$TMPDIR_CLONE" rev-list --all) -- 2>/dev/null; then
    echo "DENYLIST HIT: a denylisted token was found in history (token withheld from output)." >&2
    DENYLIST_HIT=1
  fi
done < "$REAL_DENYLIST"

[ "$DENYLIST_HIT" -eq 0 ] || fail "PII-denylist verification FAILED: at least one denylisted token is present in the filtered mirror's history. Aborting before any push."
echo "  denylist git grep: 0 hits across redacted history."

step "Config swap: gmj-core sample payloads"
SAMPLE_DIR="$REPO_ROOT/gmj-core/config"

copy_sample() {
  local sample_name="$1"
  local target_rel="$2"
  local sample_path="$SAMPLE_DIR/$sample_name"
  [ -f "$sample_path" ] || fail "Missing sample payload: $sample_path"
  mkdir -p "$(dirname "$TMPDIR_CLONE/$target_rel")"
  cp "$sample_path" "$TMPDIR_CLONE/$target_rel"
  echo "  swapped: $target_rel <- gmj-core/config/$sample_name"
}

copy_sample "candidate.yaml.sample"    "config/candidate.yaml"
copy_sample "candidate.ua.yaml.sample" "config/candidate.ua.yaml"
copy_sample "candidate.ru.yaml.sample" "config/candidate.ru.yaml"
copy_sample "credentials.yaml.sample"  "config/credentials.yaml"
copy_sample "preferences.yaml.sample"  "config/preferences.yaml"

step "Inject public docs (README + LICENSE)"
[ -f "$REPO_ROOT/LICENSE" ] || fail "Missing $REPO_ROOT/LICENSE"
[ -f "$REPO_ROOT/README.md" ] || fail "Missing $REPO_ROOT/README.md"
cp "$REPO_ROOT/LICENSE" "$TMPDIR_CLONE/LICENSE"

# Transform root README.md into the public mirror's README.md by applying the
# PRIVATE-ONLY/PUBLIC-MIRROR marker convention (documented at the top of README.md
# itself): PRIVATE-ONLY blocks (markers + everything between them) are deleted;
# PUBLIC-MIRROR blocks are uncommented (markers deleted, inner content kept verbatim).
python3 -c "
import re
import sys

with open(sys.argv[1], encoding='utf-8') as f:
    text = f.read()

# Delete each PRIVATE-ONLY block: start marker line, end marker line, and
# everything between them (non-greedy so multiple separate blocks are each
# matched independently).
text = re.sub(
    r'<!-- PRIVATE-ONLY:START -->\n.*?<!-- PRIVATE-ONLY:END -->\n?',
    '',
    text,
    flags=re.DOTALL,
)

# Uncomment each PUBLIC-MIRROR block: drop the two wrapper lines, keep the
# inner content verbatim (it was inert markdown sitting inside one open HTML
# comment).
text = re.sub(
    r'<!-- PUBLIC-MIRROR:START\n(.*?)\nPUBLIC-MIRROR:END -->\n?',
    lambda m: m.group(1) + '\n',
    text,
    flags=re.DOTALL,
)

with open(sys.argv[2], 'w', encoding='utf-8') as f:
    f.write(text)
" "$REPO_ROOT/README.md" "$TMPDIR_CLONE/README.md"

step "Commit the config swap + doc injection (author identity preserved, NOT rewritten)"
git -C "$TMPDIR_CLONE" add -A
if git -C "$TMPDIR_CLONE" diff --cached --quiet; then
  echo "  no changes to commit (config swap + docs already match working tree — unexpected but non-fatal)"
else
  git -C "$TMPDIR_CLONE" commit -m "chore(publish): swap in gmj-core sample config + public README/LICENSE for public mirror"
fi

step "VERIFICATION GATE (hard-when-present) — gitleaks"
if [ "$GITLEAKS_PRESENT" -eq 1 ]; then
  GITLEAKS_CONFIG_ARGS=()
  # Read from REPO_ROOT (the private repo), not the filtered clone — .gitleaks.toml
  # is excluded from the mirror (paths-to-remove.txt) so it never ships publicly,
  # same pattern as the root README.md/LICENSE injection above (also read from
  # REPO_ROOT, not the filtered clone).
  if [ -f "$REPO_ROOT/.gitleaks.toml" ]; then
    GITLEAKS_CONFIG_ARGS=(--config "$REPO_ROOT/.gitleaks.toml")
  fi
  if ! gitleaks detect --source "$TMPDIR_CLONE" --no-banner "${GITLEAKS_CONFIG_ARGS[@]}"; then
    fail "gitleaks detected findings in the filtered mirror. Aborting before any push."
  fi
  echo "  gitleaks: 0 findings."
else
  echo "  WARNING: gitleaks scan SKIPPED (gitleaks not installed). Denylist grep still hard-gated above."
fi

step "Push stage"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: would push $TMPDIR_CLONE HEAD to remote '$PUBLIC_REMOTE' as '$PUBLIC_BRANCH' (refspec HEAD:$PUBLIC_BRANCH)."
  echo "DRY RUN: no remote was contacted. Stopping here successfully."
  exit 0
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  echo "This will FORCE-PUSH regenerated history to the PUBLIC repo's '$PUBLIC_BRANCH' branch at:"
  echo "  $PUBLIC_REMOTE"
  echo "This REPLACES the public branch history. Type 'yes' to continue, anything else aborts."
  read -r CONFIRM
  [ "$CONFIRM" = "yes" ] || fail "Operator did not confirm. Aborting before any push."
fi

git -C "$TMPDIR_CLONE" remote add public "$PUBLIC_REMOTE"
git -C "$TMPDIR_CLONE" push --force public "HEAD:$PUBLIC_BRANCH"
echo "Pushed filtered mirror to $PUBLIC_REMOTE ($PUBLIC_BRANCH)."
