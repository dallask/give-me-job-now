#!/usr/bin/env python3
"""Interactive, questionary-based cleanup wizard for generated content (OPS-01).

This tool lets an operator select which of the 8 fixed generated-content categories
(7 ``output/*`` subfolders + ``.pipeline/runs/``) to delete, shows a per-category and
combined count+size summary before anything is touched, and gates EVERY deletion behind
a single, un-skippable ``questionary.confirm(default=False)`` prompt. The safety
guarantee is the PRESENCE of that mandatory interactive confirm gate: there is no
``--yes``/``--force``/``--no-confirm``/``-y`` flag or any other non-interactive bypass
code path anywhere in this file. Declining the confirm (pressing Enter alone, or an
explicit "no") performs zero deletions and exits 0; selecting zero categories
short-circuits before the confirm prompt is ever shown.

This module is wholly independent of its sibling read-only reporter script — no shared
imports, no shared function names, no edits to that file. The two tools solve different
problems (generated-content category cleanup vs. dead/unused-file detection) and happen
only to share a directory and a ``gmj_cleanup_*`` naming prefix.

CLI: ``python3 scripts/gmj_cleanup_wizard.py [--repo-root .]``; presents the checkbox
selection, the count+size summary, and the confirm gate. ``--repo-root`` exists solely
for testability (pointing category resolution at an isolated tree) — it does not, and
must never, provide any way to skip the confirm prompt.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import questionary

REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root

# Fixed, module-level 8-category taxonomy (per 44-CONTEXT.md D-01). This is the single
# source both the checkbox-choice builder and the delete-dispatch loop read from — no
# second hard-coded path list anywhere in this file. Keys are the stable, human-readable
# labels used in both the CLI output and the test suite; values are the Path each label
# resolves to under REPO_ROOT.
CATEGORIES: dict[str, Path] = {
    "output/analysis/": REPO_ROOT / "output" / "analysis",
    "output/artifacts/": REPO_ROOT / "output" / "artifacts",
    "output/cv/": REPO_ROOT / "output" / "cv",
    "output/offers/": REPO_ROOT / "output" / "offers",
    "output/research/": REPO_ROOT / "output" / "research",
    "output/vacancies/": REPO_ROOT / "output" / "vacancies",
    "output/logs/": REPO_ROOT / "output" / "logs",
    ".pipeline/runs/": REPO_ROOT / ".pipeline" / "runs",
}

# .pipeline/runs/ has no .gitkeep convention (git-ignored entirely, per CLAUDE.md); every
# other (output/*) category recreates its .gitkeep after a delete, matching the repo's
# git-tracked-empty-dir convention. Derived from the category key, not scattered string
# comparisons.
_NO_GITKEEP_CATEGORY_KEY = ".pipeline/runs/"


def _category_path(repo_root: Path, label: str, default_path: Path) -> Path:
    """Re-anchor ``default_path`` (a module-level ``CATEGORIES`` value) under ``repo_root``.

    Single source for the relative-path re-derivation used by both the stats-gathering
    loop and the delete-dispatch loop in ``main()`` — extracted so the two loops can
    never silently diverge (e.g. a future edit to the fallback derivation in one copy
    without the matching edit to the other). ``default_path`` is expressed relative to
    the module-level ``REPO_ROOT``; if it is not (e.g. a fixture path outside the repo
    tree entirely), the label itself (with its trailing slash stripped) is used as the
    relative path instead.
    """
    try:
        relative = default_path.relative_to(REPO_ROOT)
    except ValueError:
        relative = Path(label.rstrip("/"))
    return repo_root / relative


def compute_category_stats(path: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for every file under ``path``.

    A missing directory returns (0, 0) rather than raising — an ``output/*`` subfolder
    or ``.pipeline/runs/`` may simply not exist yet on disk (nothing generated there),
    which is a normal, not-empty-error state for this wizard.
    """
    if not path.is_dir():
        return 0, 0
    files = [f for f in path.rglob("*") if f.is_file()]
    count = len(files)
    size = sum(f.stat().st_size for f in files)
    return count, size


def validate_repo_root(repo_root: Path) -> Path:
    """Resolve ``repo_root`` and reject it if it does not look like this repo's root.

    Guards against the wider blast radius an unauthenticated ``--repo-root`` override
    would otherwise have: ``resolve_category_path()`` only checks that a category path
    is contained *within* whatever ``repo_root`` it is given — it has no way to know
    whether that root is actually this repository. Without this check, ``--repo-root /``
    (or any other arbitrary tree) would cause every category to "legitimately" resolve
    inside that root and pass containment trivially, and a subsequent confirmed delete
    would ``shutil.rmtree()`` real paths far outside this project. Requiring a ``.git``
    directory at the resolved root is a cheap, effective sentinel check — this tool is
    only ever meant to run against a git checkout of this repo (or a test fixture that
    deliberately sets up its own ``.git`` marker). Raises ``ValueError`` naming the
    offending root if the sentinel is missing.
    """
    resolved_root = repo_root.resolve()
    if not (resolved_root / ".git").exists():
        raise ValueError(
            f"--repo-root {resolved_root} does not look like a git repo root (no "
            f".git entry found) — refusing to treat it as a deletion boundary"
        )
    return resolved_root


def resolve_category_path(repo_root: Path, category_path: Path) -> Path:
    """Resolve ``category_path`` and reject any resolution that escapes ``repo_root``'s tree.

    Covers T-44-01 (symlink-escape / crafted-root tampering): a category directory that
    is (or contains) a symlink pointing outside the active repo_root must never be
    treated as a valid deletion target. Uses ``Path.resolve()`` (which follows symlinks)
    and verifies containment via ``is_relative_to()`` before any deletion proceeds.
    Raises ``ValueError`` naming the offending path if containment fails. Does NOT
    itself validate that ``repo_root`` is this repository — see ``validate_repo_root()``,
    called once in ``main()`` before this function is ever reached, for that check.
    """
    resolved_root = repo_root.resolve()
    resolved_category = category_path.resolve()
    if not (resolved_category == resolved_root or resolved_category.is_relative_to(resolved_root)):
        raise ValueError(
            f"category path {category_path} resolves to {resolved_category}, which "
            f"escapes the active repo_root {resolved_root} — refusing to treat this as "
            f"a valid deletion target (T-44-01 symlink/path-escape guard)"
        )
    return resolved_category


def delete_category(path: Path, category_key: str) -> None:
    """Delete everything under ``path``, then recreate the directory (and .gitkeep if applicable).

    ``shutil.rmtree()`` is the only call in this file that removes a category's
    contents; it is invoked exclusively from this function, which is itself only ever
    called from the post-confirm branch of ``main()`` — never from stats computation or
    choice-building. After removal, the directory is recreated via
    ``mkdir(parents=True, exist_ok=True)`` so the category remains a valid, existing
    (empty) directory. ``.gitkeep`` is recreated for every category EXCEPT
    ``.pipeline/runs/``, which has no such convention (it is entirely git-ignored).
    """
    if path.is_dir():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    if category_key != _NO_GITKEEP_CATEGORY_KEY:
        (path / ".gitkeep").touch()


def human_size(n: int) -> str:
    """Format a byte count as a short human-readable string (e.g. '1.5 KB')."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - unreachable, satisfies type checkers


def build_arg_parser() -> argparse.ArgumentParser:
    """Build this tool's ArgumentParser.

    Exposes only ``--repo-root`` (for testability). There is NO ``--yes``/``--force``/
    ``-y``/``--no-confirm`` option anywhere in this parser — the single confirm gate in
    ``main()`` can never be bypassed via a CLI flag (T-44-02 regression guard, verified
    by tests/test_gmj_cleanup_wizard.py::test_no_bypass_flag_in_argparse).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Interactive cleanup wizard for generated-content categories "
            "(output/* + .pipeline/runs/). Every deletion is gated behind a mandatory "
            "interactive confirm prompt; there is no non-interactive bypass."
        )
    )
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="Repo root categories resolve against (default: this repo's root).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        repo_root: Path = validate_repo_root(args.repo_root)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    stats: dict[str, tuple[int, int]] = {}
    choices: list[questionary.Choice] = []
    for label, default_path in CATEGORIES.items():
        # Re-anchor each category under the (possibly overridden) repo_root for
        # testability, mirroring the relative layout of the module-level CATEGORIES dict.
        category_path = _category_path(repo_root, label, default_path)

        try:
            count, size = compute_category_stats(category_path)
        except Exception as exc:  # noqa: BLE001  fail-closed: report, never silently skip
            print(f"FAIL: could not compute stats for {label} ({category_path}): {exc}", file=sys.stderr)
            return 1

        stats[label] = (count, size)
        choices.append(
            questionary.Choice(title=f"{label} ({count} files, {human_size(size)})", value=label)
        )

    selected: list[str] = questionary.checkbox(
        "Select categories to delete:", choices=choices
    ).ask()

    if not selected:
        print("Nothing selected, exiting.")
        return 0

    total_count = 0
    total_size = 0
    print("The following categories will be deleted:")
    for label in selected:
        count, size = stats[label]
        total_count += count
        total_size += size
        print(f"  {label}: {count} files, {human_size(size)}")
    print(f"Total: {total_count} files, {human_size(total_size)}")

    confirmed = questionary.confirm(
        "Delete the above categories? This cannot be undone.", default=False
    ).ask()

    if not confirmed:
        print("Deletion declined, exiting.")
        return 0

    for label in selected:
        category_path = _category_path(repo_root, label, CATEGORIES[label])

        try:
            resolved = resolve_category_path(repo_root, category_path)
            delete_category(resolved, label)
        except Exception as exc:  # noqa: BLE001  fail-closed: report, never silently skip
            print(f"FAIL: could not delete {label} ({category_path}): {exc}", file=sys.stderr)
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
