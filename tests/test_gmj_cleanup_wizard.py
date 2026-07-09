#!/usr/bin/env python3
"""RED contract for OPS-01 — scripts/gmj_cleanup_wizard.py.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_cleanup_wizard.py``. This is the machine-checkable acceptance
contract that plan 44-01's implementation (``scripts/gmj_cleanup_wizard.py``) must turn
GREEN. It is EXPECTED to FAIL now (RED): the module does not exist yet, so importing it
raises ``ModuleNotFoundError`` — that failure IS the RED confirmation for this task.

HARD CONSTRAINT: every fixture lives under its own ``tempfile.TemporaryDirectory()``
context manager. This file mutates NOTHING under the real repo's ``output/`` or
``.pipeline/`` directories — no fixture is ever planted, read, or written outside a
tempdir. Every assertion names the offending path/value so a failure is actionable.

This file covers only the pure/non-interactive logic (category stats computation,
path-restriction against symlink escape, .gitkeep-preserving delete, the fixed 8-category
taxonomy, and the argparse surface having no bypass flag) — it never drives an actual
``questionary`` interactive prompt (no TTY in this harness).

Assertions (all currently RED — ModuleNotFoundError until scripts/gmj_cleanup_wizard.py exists):
  1. test_compute_category_stats_counts_files_and_size
  2. test_compute_category_stats_empty_dir_returns_zero
  3. test_compute_category_stats_missing_dir_returns_zero_not_raise
  4. test_delete_category_recreates_gitkeep_for_output_categories
  5. test_delete_category_pipeline_runs_no_gitkeep_recreated
  6. test_resolve_category_path_rejects_escape_via_symlink
  7. test_categories_dict_has_exactly_eight_fixed_entries
  8. test_no_bypass_flag_in_argparse

Discipline: no broad try/except masks a real crash — the main() harness reports any
uncaught exception as a FAIL (exit 1), so a syntax/harness error can never pass green.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_cleanup_wizard  # noqa: E402  (module under test; may not exist yet — RED)


def test_compute_category_stats_counts_files_and_size() -> None:
    """Given 2 known-size files + a .gitkeep, compute_category_stats returns exact count/size.

    Chosen convention: .gitkeep IS included in the count/size (compute_category_stats walks
    every file under the category path with no filtering — filtering .gitkeep out of the
    count/size math is explicitly NOT required per 44-PATTERNS.md, so this test asserts the
    simpler, unfiltered behavior explicitly rather than leaving it ambiguous).
    """
    with tempfile.TemporaryDirectory() as tmp:
        category_path = Path(tmp) / "output" / "artifacts"
        category_path.mkdir(parents=True)
        (category_path / "a.txt").write_bytes(b"12345")  # 5 bytes
        (category_path / "b.txt").write_bytes(b"1234567890")  # 10 bytes
        (category_path / ".gitkeep").write_bytes(b"")  # 0 bytes

        count, size = gmj_cleanup_wizard.compute_category_stats(category_path)

        assert count == 3, (
            f"expected count=3 (a.txt, b.txt, .gitkeep, per the chosen unfiltered-count "
            f"convention), got {count}"
        )
        assert size == 15, (
            f"expected size=15 (5 + 10 + 0 bytes), got {size}"
        )


def test_compute_category_stats_empty_dir_returns_zero() -> None:
    """An empty tempdir category (no files at all, not even .gitkeep) returns count=0, size=0."""
    with tempfile.TemporaryDirectory() as tmp:
        category_path = Path(tmp) / "output" / "research"
        category_path.mkdir(parents=True)

        count, size = gmj_cleanup_wizard.compute_category_stats(category_path)

        assert count == 0, f"expected count=0 for an empty dir, got {count}"
        assert size == 0, f"expected size=0 for an empty dir, got {size}"


def test_compute_category_stats_missing_dir_returns_zero_not_raise() -> None:
    """A category path that does not exist on disk returns (0, 0) rather than raising."""
    with tempfile.TemporaryDirectory() as tmp:
        category_path = Path(tmp) / "output" / "does_not_exist"
        assert not category_path.exists(), (
            f"test construction error: {category_path} must not exist for this fixture"
        )

        count, size = gmj_cleanup_wizard.compute_category_stats(category_path)

        assert count == 0, (
            f"compute_category_stats on missing dir {category_path} must return count=0 "
            f"(not raise FileNotFoundError), got count={count}"
        )
        assert size == 0, (
            f"compute_category_stats on missing dir {category_path} must return size=0 "
            f"(not raise FileNotFoundError), got size={size}"
        )


def test_delete_category_recreates_gitkeep_for_output_categories() -> None:
    """delete_category() on an output/* -shaped fixture rmtrees then recreates dir + .gitkeep."""
    with tempfile.TemporaryDirectory() as tmp:
        category_path = Path(tmp) / "output" / "cv"
        category_path.mkdir(parents=True)
        (category_path / "resume.pdf").write_bytes(b"fake-pdf-bytes")
        (category_path / ".gitkeep").write_bytes(b"")

        gmj_cleanup_wizard.delete_category(category_path, "output/cv/")

        assert category_path.is_dir(), (
            f"expected {category_path} to exist as a directory after delete_category(), "
            f"but it does not"
        )
        remaining = sorted(p.name for p in category_path.iterdir())
        assert remaining == [".gitkeep"], (
            f"expected {category_path} to contain ONLY a recreated .gitkeep after delete "
            f"(original files removed), got: {remaining}"
        )
        assert (category_path / ".gitkeep").is_file(), (
            f"expected {category_path / '.gitkeep'} to exist (recreated) after delete_category() "
            f"for an output/* category"
        )


def test_delete_category_pipeline_runs_no_gitkeep_recreated() -> None:
    """delete_category() on a .pipeline/runs/-shaped fixture (no .gitkeep) leaves it empty."""
    with tempfile.TemporaryDirectory() as tmp:
        category_path = Path(tmp) / ".pipeline" / "runs"
        category_path.mkdir(parents=True)
        (category_path / "run-abc123").mkdir()
        (category_path / "run-abc123" / "state.json").write_text("{}", encoding="utf-8")

        gmj_cleanup_wizard.delete_category(category_path, ".pipeline/runs/")

        assert category_path.is_dir(), (
            f"expected {category_path} to exist as a directory after delete_category(), "
            f"but it does not"
        )
        remaining = list(category_path.iterdir())
        assert remaining == [], (
            f"expected {category_path} to be completely empty after delete_category() "
            f"(no .gitkeep convention for .pipeline/runs/), got: {remaining}"
        )
        assert not (category_path / ".gitkeep").exists(), (
            f"expected NO .gitkeep to be created under {category_path} — "
            f".pipeline/runs/ has no such convention (git-ignored entirely)"
        )


def test_resolve_category_path_rejects_escape_via_symlink() -> None:
    """resolve_category_path() must reject a category path that symlink-escapes repo_root (T-44-01)."""
    with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_outside:
        repo_root = Path(tmp_root)
        outside_target = Path(tmp_outside) / "escaped-target"
        outside_target.mkdir()
        (outside_target / "sensitive.txt").write_text("should never be deletable", encoding="utf-8")

        output_dir = repo_root / "output"
        output_dir.mkdir()
        escaping_category = output_dir / "artifacts"
        escaping_category.symlink_to(outside_target, target_is_directory=True)

        rejected = False
        try:
            gmj_cleanup_wizard.resolve_category_path(repo_root, escaping_category)
        except ValueError as exc:
            rejected = True
            assert str(escaping_category) in str(exc) or "escap" in str(exc).lower(), (
                f"resolve_category_path() must name the offending escaping path "
                f"({escaping_category}) or clearly say it escapes repo_root in its "
                f"ValueError message; got: {exc}"
            )

        assert rejected, (
            f"resolve_category_path(repo_root={repo_root}, "
            f"category_path={escaping_category} [symlinked to {outside_target}, outside "
            f"repo_root's tree]) must raise ValueError to satisfy T-44-01 (symlink-escape "
            f"path-containment guard) — it did not raise at all"
        )


def test_categories_dict_has_exactly_eight_fixed_entries() -> None:
    """CATEGORIES has exactly 8 entries matching the fixed literal set from 44-CONTEXT.md."""
    expected_keys = {
        "output/analysis/",
        "output/artifacts/",
        "output/cv/",
        "output/offers/",
        "output/research/",
        "output/vacancies/",
        "output/logs/",
        ".pipeline/runs/",
    }

    actual_keys = set(gmj_cleanup_wizard.CATEGORIES.keys())

    assert len(gmj_cleanup_wizard.CATEGORIES) == 8, (
        f"CATEGORIES must have exactly 8 entries (standing regression guard against "
        f"silently adding/removing a category), got {len(gmj_cleanup_wizard.CATEGORIES)}: "
        f"{sorted(actual_keys)}"
    )
    assert actual_keys == expected_keys, (
        f"CATEGORIES key set must exactly match the fixed 8-category taxonomy from "
        f"44-CONTEXT.md.\nExpected: {sorted(expected_keys)}\nGot: {sorted(actual_keys)}"
    )


def test_no_bypass_flag_in_argparse() -> None:
    """build_arg_parser()'s ArgumentParser registers no --yes/--force/--no-confirm/-y option."""
    parser = gmj_cleanup_wizard.build_arg_parser()

    forbidden_strings = {"--yes", "--force", "--no-confirm", "-y"}
    registered_option_strings: set[str] = set()
    for action in parser._actions:  # noqa: SLF001  introspecting argparse is the standard way
        registered_option_strings.update(action.option_strings)

    collision = forbidden_strings & registered_option_strings
    assert not collision, (
        f"build_arg_parser() must expose NO confirm-bypass flag (T-44-02 regression guard) "
        f"— found forbidden option string(s) {sorted(collision)} among registered options: "
        f"{sorted(registered_option_strings)}"
    )


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
