#!/usr/bin/env python3
"""gmj_bootstrap_releases.py — backfill real historical GitHub Releases.

Reads scripts/publish/milestone-releases.yaml (one entry per real shipped
milestone) and, for each entry, locates the anchor commit by an EXACT
commit-message match (never a hardcoded SHA — SHAs are rewritten on every
mirror publish by git-filter-repo, but commit messages survive verbatim).

For each release entry, idempotently (delete-then-recreate) creates:
  - an annotated git tag at the anchor SHA, dated with the release's real
    historical date (not today), pushed to origin
  - a GitHub Release (via `gh`) targeting that SHA

Requires `git`, `gh` on PATH and GH_TOKEN (or GITHUB_TOKEN) set in the
environment for `gh` to authenticate. Intended to run inside release.yml in
the PUBLIC mirror repo, but also runs safely (dry, tag/gh-free) for anchor
resolution checks against this repo's local history.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

DEFAULT_COMMITTER_TZ_OFFSET = "+03:00"


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(out.stdout.strip())


def resolve_repo_slug(explicit: str | None) -> str:
    if explicit:
        return explicit
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo
    out = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    url = out.stdout.strip()
    if url:
        # Handle both SSH (git@github.com:owner/name.git) and HTTPS forms.
        tail = url.split("github.com")[-1].lstrip(":/").removesuffix(".git")
        if tail:
            return tail
    raise SystemExit(
        "ERROR: could not resolve owner/repo slug — pass --repo, set "
        "GITHUB_REPOSITORY, or configure a github.com 'origin' remote."
    )


def load_releases(root: Path) -> list[dict]:
    releases_path = root / "scripts" / "publish" / "milestone-releases.yaml"
    if not releases_path.is_file():
        raise SystemExit(f"ERROR: missing {releases_path}")
    data = yaml.safe_load(releases_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("releases"), list):
        raise SystemExit(f"ERROR: {releases_path} did not parse to {{'releases': [...]}}")
    return data["releases"]


def find_anchor_sha(anchor_message: str) -> str:
    """Find the unique commit whose subject exactly equals anchor_message.

    Fails loudly (raises SystemExit) on zero or more-than-one match — ambiguity
    here must never silently pick a "close enough" commit.
    """
    out = subprocess.run(
        ["git", "log", "--all", "--format=%H\t%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    matches = []
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        if subject == anchor_message:
            matches.append(sha)
    if len(matches) == 0:
        raise SystemExit(
            f"ERROR: anchor commit not found for message: {anchor_message!r}"
        )
    if len(matches) > 1:
        raise SystemExit(
            f"ERROR: ambiguous anchor commit — {len(matches)} commits match "
            f"message {anchor_message!r}: {matches}"
        )
    return matches[0]


def gh_release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def delete_existing_release(tag: str) -> None:
    if not gh_release_exists(tag):
        return
    subprocess.run(
        ["gh", "release", "delete", tag, "--yes", "--cleanup-tag"],
        check=True,
    )


def create_tag(tag: str, sha: str, date: str, title: str) -> None:
    tag_datetime = f"{date}T12:00:00{DEFAULT_COMMITTER_TZ_OFFSET}"
    env = dict(os.environ)
    env["GIT_COMMITTER_DATE"] = tag_datetime
    env["GIT_AUTHOR_DATE"] = tag_datetime
    subprocess.run(
        ["git", "tag", "-a", tag, sha, "-m", title],
        check=True,
        env=env,
    )
    subprocess.run(["git", "push", "--force", "origin", tag], check=True)


def create_gh_release(tag: str, sha: str, title: str, notes: str) -> None:
    subprocess.run(
        [
            "gh", "release", "create", tag,
            "--target", sha,
            "--title", title,
            "--notes", notes,
        ],
        check=True,
    )


def bootstrap_releases(root: Path, *, dry_run: bool) -> int:
    releases = load_releases(root)
    results: list[tuple[str, str, str]] = []
    failed: list[str] = []

    for entry in releases:
        tag = entry["tag"]
        anchor_message = entry["anchor_message"]
        date = entry["date"]
        title = entry["title"]
        notes = entry.get("notes", "")

        try:
            sha = find_anchor_sha(anchor_message)
        except SystemExit as err:
            print(str(err), file=sys.stderr)
            failed.append(tag)
            continue

        if dry_run:
            results.append((tag, sha, "resolved (dry-run, no tag/gh calls)"))
            continue

        try:
            delete_existing_release(tag)
            create_tag(tag, sha, date, title)
            create_gh_release(tag, sha, title, notes)
        except subprocess.CalledProcessError as err:
            print(f"ERROR: failed to bootstrap release {tag}: {err}", file=sys.stderr)
            failed.append(tag)
            continue

        results.append((tag, sha, "recreated"))

    print("\nSummary:")
    print(f"{'tag':<10} {'sha':<42} status")
    for tag, sha, status in results:
        print(f"{tag:<10} {sha:<42} {status}")
    if failed:
        print(f"\nFAILED entries: {', '.join(failed)}", file=sys.stderr)
        return 1

    if len(results) != len(releases):
        print("ERROR: not all release entries produced a result.", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=None,
        help="owner/name of the GitHub repo (default: derived from git remote or GITHUB_REPOSITORY).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve anchor SHAs only — skip tag creation, push, and gh release calls.",
    )
    args = parser.parse_args()

    root = repo_root()

    if not args.dry_run:
        if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
            print(
                "ERROR: GH_TOKEN (or GITHUB_TOKEN) must be set in the environment "
                "for `gh` to authenticate.",
                file=sys.stderr,
            )
            return 1
        # Resolve --repo / GITHUB_REPOSITORY / origin remote eagerly so a bad
        # slug fails fast rather than mid-loop inside individual gh calls.
        resolve_repo_slug(args.repo)

    return bootstrap_releases(root, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
