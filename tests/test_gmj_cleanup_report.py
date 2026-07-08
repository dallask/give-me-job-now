#!/usr/bin/env python3
"""RED contract for CLEANUP-01/CLEANUP-02 — scripts/gmj_cleanup_report.py.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_cleanup_report.py``. This is the machine-checkable acceptance
contract that plan 36-01's implementation (``scripts/gmj_cleanup_report.py``) must turn
GREEN. It is EXPECTED to FAIL now (RED): the module does not exist yet, so importing it
raises ``ModuleNotFoundError`` — that failure IS the RED confirmation for this task.

HARD CONSTRAINT: every fixture lives under its own ``tempfile.TemporaryDirectory()``
context manager. This file mutates NOTHING under the real REPO_ROOT — no fixture is ever
planted, read, or written outside a tempdir. Every assertion names the offending path so
a failure is actionable.

Assertions (all currently RED — ModuleNotFoundError until scripts/gmj_cleanup_report.py exists):
  (a) test_high_confidence_zero_references_reported  — a zero-reference fixture is tier "high".
  (b) test_referenced_fixture_excluded_from_candidates — a plainly-referenced fixture is absent.
  (c) test_comment_only_hit_tagged_review_recommended — a comment-only mention is tier "review".
  (d) test_manifest_glob_owned_fixture_excluded       — a manifest-glob-owned fixture is absent
      even with zero literal reference hits.
  (e) test_two_runs_touch_only_report_path            — two consecutive build+write runs mutate
      only the designated report output path.
  (f) test_word_boundary_regex_no_false_positive_on_short_basename — a bare-word substring
      collision in prose does not falsely register as a reference.
  (g) test_manifest_load_fails_closed_on_missing_and_non_list — a missing/malformed manifest
      raises rather than silently degrading to "report everything".

Discipline: no broad try/except masks a real crash — the main() harness reports any
uncaught exception as a FAIL (exit 1), so a syntax/harness error can never pass green.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import gmj_cleanup_report  # noqa: E402  (module under test; may not exist yet — RED)


def test_high_confidence_zero_references_reported() -> None:
    """A fixture file with zero references anywhere in the tree is tier 'high'."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "unused_candidate.py").write_text(
            "# an inert module with no callers anywhere in this fixture tree\n"
            "VALUE = 1\n",
            encoding="utf-8",
        )
        result = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        assert "unused_candidate.py" in result, (
            f"expected 'unused_candidate.py' present in classify() result, got keys: "
            f"{sorted(result)}"
        )
        entry = result["unused_candidate.py"]
        assert entry["tier"] == "high", (
            f"unused_candidate.py: expected tier 'high', got {entry['tier']!r} "
            f"(evidence: {entry.get('evidence')!r})"
        )
        evidence = entry.get("evidence", "")
        assert "0 hits" in evidence, (
            f"unused_candidate.py: evidence must cite '0 hits', got {evidence!r}"
        )


def test_referenced_fixture_excluded_from_candidates() -> None:
    """A fixture referenced on a non-comment line elsewhere is entirely absent from the result."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "referenced.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "caller.md").write_text(
            "See referenced.py for the implementation details.\n",
            encoding="utf-8",
        )
        result = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        assert "referenced.py" not in result, (
            f"referenced.py is referenced from caller.md on a non-comment line — must be "
            f"ABSENT from classify() result entirely, got entry: {result.get('referenced.py')!r}"
        )


def test_comment_only_hit_tagged_review_recommended() -> None:
    """A fixture whose only mention sits on a comment line is tier 'review', not 'high' or absent."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "commented.py").write_text("VALUE = 3\n", encoding="utf-8")
        (root / "notes.md").write_text(
            "# TODO: revisit commented.py later, low priority\n",
            encoding="utf-8",
        )
        result = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        assert "commented.py" in result, (
            f"commented.py has a comment-only mention — must be PRESENT (tier 'review'), "
            f"got keys: {sorted(result)}"
        )
        entry = result["commented.py"]
        assert entry["tier"] == "review", (
            f"commented.py: expected tier 'review' (comment-only hit), got {entry['tier']!r}"
        )


def test_manifest_glob_owned_fixture_excluded() -> None:
    """A fixture matching a framework_globs glob is excluded even with zero literal hits.

    NOTE: gmj_remove_gsd.is_framework_path()'s ``rel`` resolution falls back to ``path.name``
    when the path does not resolve under the REAL REPO_ROOT (which is the case here, since the
    fixture lives in a tempdir, not the real repo). That fallback is intentional and documented
    here inline: it means glob matching against a fixture tree still works via the basename/stem
    candidate set, not the (inapplicable) repo-relative path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "gsd-owned.py").write_text("VALUE = 4\n", encoding="utf-8")
        result = gmj_cleanup_report.classify(repo_root=root, framework_globs=["gsd-*"])
        assert "gsd-owned.py" not in result, (
            f"gsd-owned.py matches framework_globs=['gsd-*'] — must be ABSENT despite zero "
            f"reference hits (manifest-glob exclusion wins independently), got entry: "
            f"{result.get('gsd-owned.py')!r}"
        )


def test_two_runs_touch_only_report_path() -> None:
    """Running the build+write path twice mutates ONLY the designated report output file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "some_file.py").write_text("VALUE = 5\n", encoding="utf-8")
        (root / "docs.md").write_text("no mention of anything special here\n", encoding="utf-8")
        output_path = root / "sources" / "analysis" / "cleanup-report.md"

        def _snapshot() -> dict[str, tuple[int, int]]:
            snap: dict[str, tuple[int, int]] = {}
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p == output_path:
                    continue
                rel = p.relative_to(root).as_posix()
                st = p.stat()
                snap[rel] = (st.st_mtime_ns, st.st_size)
            return snap

        before = _snapshot()

        classification = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        text = gmj_cleanup_report.render_report(classification, root)
        gmj_cleanup_report.write_report(text, output_path)

        classification2 = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        text2 = gmj_cleanup_report.render_report(classification2, root)
        gmj_cleanup_report.write_report(text2, output_path)

        after = _snapshot()

        assert before == after, (
            f"two consecutive runs mutated files outside the report output path "
            f"({output_path.relative_to(root)}): before={before} after={after}"
        )
        assert output_path.is_file(), (
            f"expected report output file to exist at {output_path.relative_to(root)}"
        )


def test_word_boundary_regex_no_false_positive_on_short_basename() -> None:
    """The bare word 'state' in prose must not falsely register as a reference to state.py."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "state.py").write_text("VALUE = 6\n", encoding="utf-8")
        (root / "prose.md").write_text(
            "In this design, the app's state is tracked elsewhere, not in a single module.\n",
            encoding="utf-8",
        )
        assert "state.py" not in (root / "prose.md").read_text(encoding="utf-8"), (
            "test construction error: prose.md must never contain the literal substring "
            "'state.py' (that would defeat the point of this negative test)"
        )
        result = gmj_cleanup_report.classify(repo_root=root, framework_globs=[])
        assert "state.py" in result, (
            f"state.py: expected present in classify() result, got keys: {sorted(result)}"
        )
        entry = result["state.py"]
        assert entry["tier"] == "high", (
            f"state.py: the bare word 'state' in prose must NOT count as a reference — "
            f"expected tier 'high', got {entry['tier']!r} (evidence: {entry.get('evidence')!r})"
        )


def test_manifest_load_fails_closed_on_missing_and_non_list() -> None:
    """A missing manifest raises FileNotFoundError; a non-list framework_globs raises ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        missing_path = root / "does-not-exist.yaml"
        raised_missing = False
        try:
            gmj_cleanup_report.load_framework_globs(missing_path)
        except FileNotFoundError:
            raised_missing = True
        assert raised_missing, (
            f"load_framework_globs({missing_path}) must raise FileNotFoundError for a "
            "missing manifest, not return [] silently"
        )

        bad_manifest = root / "bad-manifest.yaml"
        bad_manifest.write_text(
            "version: 1\nframework_globs: \"gsd-*\"\n",
            encoding="utf-8",
        )
        raised_bad = False
        try:
            gmj_cleanup_report.load_framework_globs(bad_manifest)
        except ValueError:
            raised_bad = True
        assert raised_bad, (
            f"load_framework_globs({bad_manifest}) must raise ValueError when "
            "`framework_globs` is a bare string (not a list), not return [] silently"
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
