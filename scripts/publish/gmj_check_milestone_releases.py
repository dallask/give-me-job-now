#!/usr/bin/env python3
"""gmj_check_milestone_releases.py — REL-05 future-proofing safeguard.

Compares shipped milestones recorded as ``## vX.Y ...`` headings in
``.planning/MILESTONES.md`` against ``scripts/publish/milestone-releases.yaml``'s ``tag``
entries. Prevents a future milestone from being silently missed from the release ledger
the way v5.0/v6.0/v7.0 (and, at the time this safeguard was built, v9.0) originally were —
control flow mirrors ``scripts/pipeline/gmj_check_delivery.py`` (read → set-difference →
exit 0/1). All error paths go to stderr with no traceback.

CLI: ``gmj_check_milestone_releases.py [--milestones PATH] [--releases PATH]`` — both
default to this repo's real paths. Exits 0 (clean, prints an ``OK: ...`` summary to
stdout) or 1 (a gap was found; names every missing ``vX.Y.0`` tag on stderr). This
exit-0/1 contract is strict and has no bypass flag — the pytest wrapper
(``tests/test_milestone_releases_coverage.py``) that surfaces this check in CI chooses to
treat a detected gap as advisory (warns, never asserts); that is a CI-integration
decision layered on top, not a relaxation of this script's own contract.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/publish/ -> repo root
DEFAULT_MILESTONES = REPO_ROOT / ".planning" / "MILESTONES.md"
DEFAULT_RELEASES = REPO_ROOT / "scripts" / "publish" / "milestone-releases.yaml"

HEADING_RE = re.compile(r"^##\s+v(\d+\.\d+)\b")


def shipped_milestone_tags(milestones_text: str) -> set[str]:
    """Derive the vX.Y.0 tag set implied by every `## vX.Y ...` heading.

    Only the first `vX.Y` token immediately after `## ` is captured, so a duplicated
    title fragment later in the same heading line (e.g. `## v6.0 v6.0 (Shipped: ...)`)
    never produces a spurious second match. A line that doesn't start with `## v`
    (e.g. a `**Phases completed:**` line) simply doesn't match and is skipped, never
    raising.
    """
    versions = {
        m.group(1) for line in milestones_text.splitlines() if (m := HEADING_RE.match(line))
    }
    return {f"v{v}.0" for v in versions}


def yaml_release_tags(releases_data: dict) -> set[str]:
    """Return the `tag` value set from a parsed {"releases": [{"tag": ..., ...}]} dict.

    An entry dict missing a `tag` key is skipped, never raising a KeyError.
    """
    return {entry["tag"] for entry in releases_data.get("releases", []) if "tag" in entry}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when a MILESTONES.md-shipped milestone has no milestone-releases.yaml entry."
        )
    )
    parser.add_argument(
        "--milestones",
        type=Path,
        default=DEFAULT_MILESTONES,
        help="Path to MILESTONES.md (default: repo's real .planning/MILESTONES.md)",
    )
    parser.add_argument(
        "--releases",
        type=Path,
        default=DEFAULT_RELEASES,
        help="Path to milestone-releases.yaml (default: repo's real scripts/publish/milestone-releases.yaml)",
    )
    args = parser.parse_args()

    milestones_path = args.milestones.expanduser()
    if not milestones_path.is_file():
        print(f"Not a file: {milestones_path}", file=sys.stderr)
        return 1

    releases_path = args.releases.expanduser()
    if not releases_path.is_file():
        print(f"Not a file: {releases_path}", file=sys.stderr)
        return 1

    milestones_text = milestones_path.read_text(encoding="utf-8")

    try:
        releases_data = yaml.safe_load(releases_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"Invalid releases YAML: {exc}", file=sys.stderr)
        return 1
    if not isinstance(releases_data, dict):
        print("Releases YAML must parse to a mapping.", file=sys.stderr)
        return 1

    shipped = shipped_milestone_tags(milestones_text)
    released = yaml_release_tags(releases_data)
    missing = sorted(shipped - released)

    if missing:
        print(f"Missing release entries for: {', '.join(missing)}", file=sys.stderr)
        return 1

    print(f"OK: all {len(shipped)} shipped milestones have a release entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
