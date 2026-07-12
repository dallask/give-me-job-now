#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/gmj_cv_template_config.py (TMPL-01, TMPL-02).

Exercises `resolve_template(...)`'s full explicit > config > fallback precedence (D-07),
the default/random/all mode semantics (D-04), per-`state_path` rotation-state reuse across
Gate-B retries of the same offer (D-05/D-06), and never-hard-fail misconfiguration handling
(D-09) -- including path-traversal rejection of `cv.default`/`cv.templates` filename values
(V12, mirroring `gmj_batch.py`'s `_safe_id()` guard class).

Every test builds its own isolated `tempfile.TemporaryDirectory()` containing a synthetic
`preferences.yaml` and a synthetic `templates/` directory -- never touches the real
`config/preferences.yaml` or `templates/cv/`. No pytest import; the module defines its own
`test_*` functions plus a `main()` runner (still independently pytest-collectible). Run with
``python3 tests/test_cv_template_config.py``.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "cv"))

import gmj_cv_template_config as tc  # noqa: E402


def _write_prefs(dir_path: Path, cv_block: dict | None) -> Path:
    """Write a synthetic preferences.yaml with only a `cv:` block (or none)."""
    prefs_path = dir_path / "preferences.yaml"
    if cv_block is None:
        prefs_path.write_text("salary:\n  min: 1000\n  currency: USD\n", encoding="utf-8")
    else:
        lines = ["cv:"]
        if "templates" in cv_block:
            items = ", ".join(repr(t) for t in cv_block["templates"])
            lines.append(f"  templates: [{items}]")
        if "default" in cv_block:
            lines.append(f"  default: {cv_block['default']!r}")
        if "mode" in cv_block:
            lines.append(f"  mode: {cv_block['mode']!r}")
        prefs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return prefs_path


def _make_templates_dir(dir_path: Path, filenames: list[str]) -> Path:
    templates_dir = dir_path / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        # Only touch a real file for safe, non-traversal names; unsafe entries (e.g.
        # absolute paths or ".." payloads) are intentionally NOT created on disk -- the
        # module must reject them before ever checking existence.
        if "/" not in name and "\\" not in name and ".." not in name:
            (templates_dir / name).touch()
    return templates_dir


def test_explicit_template_always_wins() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path, {"templates": ["a.html"], "default": "a.html", "mode": "default"}
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html"])
        explicit = Path("/some/explicit.html")
        result = tc.resolve_template(
            explicit_template=explicit,
            no_template=False,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result == explicit, (
            f"explicit_template must win regardless of prefs content, got {result!r}"
        )


def test_no_template_flag_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path, {"templates": ["a.html"], "default": "a.html", "mode": "default"}
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html"])
        result = tc.resolve_template(
            explicit_template=None,
            no_template=True,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result is None, f"no_template=True must return None, got {result!r}"


def test_default_mode_uses_cv_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["baxter.html", "default.html"],
                "default": "baxter.html",
                "mode": "default",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html", "default.html"])
        result = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result == "baxter.html", f"expected 'baxter.html', got {result!r}"


def test_absent_prefs_file_falls_back_to_documented_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = tmp_path / "does-not-exist.yaml"
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html"])
        result = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result == tc.DOCUMENTED_DEFAULT_TEMPLATE, (
            f"absent prefs file must fall back to documented default, got {result!r}"
        )


def test_prefs_with_no_cv_block_falls_back_to_documented_default() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(tmp_path, None)
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html"])
        result = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result == tc.DOCUMENTED_DEFAULT_TEMPLATE, (
            f"prefs with no cv: block must fall back to documented default, got {result!r}"
        )


def test_random_mode_reuses_same_pick_for_same_state_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["a.html", "b.html", "c.html"],
                "default": "a.html",
                "mode": "random",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html", "b.html", "c.html"])
        state_path = tmp_path / "state.json"
        assert not state_path.is_file(), "state.json must be fresh before the first call"

        first = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_path,
            templates_dir=templates_dir,
        )
        assert state_path.is_file(), "rotation state must be persisted after the first call"
        second = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_path,
            templates_dir=templates_dir,
        )
        assert first == second, (
            f"random mode must reuse the SAME pick for the same state_path (D-05): "
            f"{first!r} != {second!r}"
        )
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert "cv_template_rotation" in state_data, (
            "state.json must record rotation state under a 'cv_template_rotation' key"
        )


def test_all_mode_round_robins_across_distinct_state_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["a.html", "b.html", "c.html"],
                "default": "a.html",
                "mode": "all",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html", "b.html", "c.html"])
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        state_a = runs_dir / "offer-a" / "state.json"
        state_b = runs_dir / "offer-b" / "state.json"
        state_c = runs_dir / "offer-c" / "state.json"

        picked_a = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_a,
            templates_dir=templates_dir,
        )
        picked_b = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_b,
            templates_dir=templates_dir,
        )
        picked_c = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_c,
            templates_dir=templates_dir,
        )
        assert [picked_a, picked_b, picked_c] == ["a.html", "b.html", "c.html"], (
            f"all mode must round-robin in order across NEW state_paths, got "
            f"{[picked_a, picked_b, picked_c]!r}"
        )

        picked_a_again = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_a,
            templates_dir=templates_dir,
        )
        assert picked_a_again == picked_a, (
            "a repeat call on the SAME state_path must reuse the original pick (D-05), "
            f"got {picked_a_again!r} != {picked_a!r}"
        )


def test_all_mode_rotation_counter_survives_genuinely_concurrent_threads() -> None:
    """02-REVIEW.md CR-02 regression: the shared ``_cv_rotation_counter.json`` under
    ``cv.mode: all`` is genuinely concurrently written by parallel offer dispatch
    (`.claude/CLAUDE.md`'s "Parallel fan-out, sequential gates" rule). Mirrors
    ``tests/test_gmj_batch_manifest_concurrency.py``'s ``threading.Barrier`` pattern to force
    REAL overlap (not sequenced by the Python call stack) — before the ``fcntl.flock`` fix, two
    threads racing this exact scenario could both read the same ``next_index``, both write back
    ``next_index + 1``, and silently lose one increment / assign a duplicate rotation slot to two
    different offers.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["a.html", "b.html", "c.html"],
                "default": "a.html",
                "mode": "all",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html", "b.html", "c.html"])
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        offer_ids = [f"offer-{i}" for i in range(8)]
        state_paths = {oid: runs_dir / oid / "state.json" for oid in offer_ids}

        barrier = threading.Barrier(len(offer_ids))
        results: dict[str, str] = {}
        results_lock = threading.Lock()
        errors: list[BaseException] = []
        errors_lock = threading.Lock()

        def worker(offer_id: str) -> None:
            barrier.wait()  # maximize genuine overlap of concurrent attempts
            try:
                picked = tc.resolve_template(
                    explicit_template=None,
                    no_template=False,
                    prefs_path=prefs_path,
                    state_path=state_paths[offer_id],
                    templates_dir=templates_dir,
                )
                with results_lock:
                    results[offer_id] = picked
            except BaseException as exc:  # noqa: BLE001 -- must never crash under contention
                with errors_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(oid,)) for oid in offer_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"genuinely concurrent rotation picks must never crash: {errors}"
        assert len(results) == len(offer_ids), (
            f"every genuinely concurrent caller's pick must land, none lost: {results}"
        )

        counter_path = runs_dir / tc._ROTATION_COUNTER_FILENAME
        counter = json.loads(counter_path.read_text(encoding="utf-8"))
        assert counter["next_index"] == len(offer_ids), (
            f"the shared counter must advance by exactly one per caller with no lost updates "
            f"under real concurrency, expected {len(offer_ids)}, got {counter['next_index']!r}"
        )

        # Round-robin coverage: with a proper lock, each of the 8 concurrent callers must have
        # been assigned a DISTINCT rotation slot (index 0..7 mod 3 templates) -- a lost update
        # would manifest as two offers colliding on the same slot/template pair.
        from collections import Counter

        picks = Counter(results.values())
        # 8 offers over a 3-template pool round-robins as {a: 3, b: 3, c: 2} in some order --
        # the exact multiset the lock-protected counter must produce with zero lost increments.
        assert sorted(picks.values()) == [2, 3, 3], (
            f"expected a clean 3/3/2 round-robin split over 8 offers / 3 templates with no lost "
            f"increments, got {dict(picks)}"
        )


def test_no_state_path_still_returns_a_valid_pick_unkeyed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["a.html", "b.html", "c.html"],
                "default": "a.html",
                "mode": "random",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html", "b.html", "c.html"])
        # No state_path -- explicit "unkeyed, independent per call" degrade (Pitfall 2),
        # not a bug: every call is free to pick independently since there's no offer/run
        # identity to key rotation-state reuse against.
        result = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=None,
            templates_dir=templates_dir,
        )
        assert result in {"a.html", "b.html", "c.html"}, (
            f"unkeyed random pick must still be a valid pool member, got {result!r}"
        )


def test_default_not_in_templates_warns_and_falls_back() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path, {"templates": ["a.html"], "default": "z.html", "mode": "default"}
        )
        templates_dir = _make_templates_dir(tmp_path, ["a.html"])
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            result = tc.resolve_template(
                explicit_template=None,
                no_template=False,
                prefs_path=prefs_path,
                state_path=None,
                templates_dir=templates_dir,
            )
        assert result == tc.DOCUMENTED_DEFAULT_TEMPLATE, (
            f"default not present in templates must fall back (D-09), got {result!r}"
        )
        stderr_text = stderr_capture.getvalue()
        assert stderr_text.strip(), "a stderr warning must be printed for the misconfiguration"
        assert "z.html" in stderr_text, (
            f"stderr warning must mention the offending value 'z.html', got: {stderr_text!r}"
        )


def test_empty_templates_under_random_mode_warns_and_falls_back() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path, {"templates": [], "default": "baxter.html", "mode": "random"}
        )
        templates_dir = _make_templates_dir(tmp_path, [])
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            result = tc.resolve_template(
                explicit_template=None,
                no_template=False,
                prefs_path=prefs_path,
                state_path=None,
                templates_dir=templates_dir,
            )
        assert result == tc.DOCUMENTED_DEFAULT_TEMPLATE, (
            f"empty templates under random mode must fall back (D-09), got {result!r}"
        )
        stderr_text = stderr_capture.getvalue()
        assert stderr_text.strip(), "a stderr warning must be printed for empty cv.templates"


def test_path_traversal_in_default_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["baxter.html"],
                "default": "../../etc/passwd",
                "mode": "default",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html"])
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            result = tc.resolve_template(
                explicit_template=None,
                no_template=False,
                prefs_path=prefs_path,
                state_path=None,
                templates_dir=templates_dir,
            )
        assert result == tc.DOCUMENTED_DEFAULT_TEMPLATE, (
            f"path-traversal default must never resolve, must fall back, got {result!r}"
        )
        stderr_text = stderr_capture.getvalue()
        assert stderr_text.strip(), "a stderr warning must be printed for the traversal attempt"


def test_path_traversal_in_templates_list_entry_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["/etc/passwd", "baxter.html"],
                "default": "baxter.html",
                "mode": "random",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html"])
        for i in range(10):
            result = tc.resolve_template(
                explicit_template=None,
                no_template=False,
                prefs_path=prefs_path,
                state_path=None,
                templates_dir=templates_dir,
            )
            assert result != "/etc/passwd", (
                f"unsafe pool entry must never be selected (draw {i}), got {result!r}"
            )


def test_default_mode_records_resolved_name_in_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        prefs_path = _write_prefs(
            tmp_path,
            {
                "templates": ["baxter.html", "default.html"],
                "default": "baxter.html",
                "mode": "default",
            },
        )
        templates_dir = _make_templates_dir(tmp_path, ["baxter.html", "default.html"])
        state_path = tmp_path / "state.json"
        assert not state_path.is_file(), "state.json must be fresh before the call"

        result = tc.resolve_template(
            explicit_template=None,
            no_template=False,
            prefs_path=prefs_path,
            state_path=state_path,
            templates_dir=templates_dir,
        )
        assert result == "baxter.html", f"expected 'baxter.html', got {result!r}"
        assert state_path.is_file(), "state.json must be written for default mode too"
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        assert state_data["cv_template_rotation"]["picked"] == "baxter.html", (
            "default mode must persist the resolved name into state.json exactly like "
            f"random/all do (RESEARCH.md Open Question 1), got: {state_data!r}"
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
