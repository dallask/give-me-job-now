#!/usr/bin/env python3
"""Tests for gmj_batch.py's concurrency-safe manifest write path (CONC-03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_batch_manifest_concurrency.py``. Proves:

- ``test_real_concurrent_threads_no_lost_update_no_crash``: genuinely CONCURRENT, real OS
  threads (not nested inside another attempt's ``apply_fn``) racing
  ``_mutate_manifest_with_retry`` on the SAME ``manifest.json`` never lose an update and never
  crash with an uncaught traceback — this is the actual CR-01 regression test: a prior version
  of ``_mutate_manifest_with_retry``/``write_manifest`` reproducibly lost a sibling's update and
  crashed with an uncaught ``FileNotFoundError`` (shared, non-unique ``.tmp`` name) under exactly
  this scenario.
- ``test_concurrent_double_init_same_batch_id_no_crash``: the WR-03 regression — two genuinely
  concurrent ``init`` calls for the SAME ``--batch-id`` (thus the SAME per-(offer, artifact_type)
  ``run_id``s / ``state.json`` paths, and the SAME ``manifest.json`` path) never crash. Before the
  WR-03 fix, ``_seed_state`` used a shared, non-unique ``.tmp`` temp name (the same bug class
  CR-01 fixed in ``write_manifest``) and ``_cmd_init``'s direct ``write_manifest`` call held no
  lock, so a duplicate ``init`` invocation for the same batch_id could crash or silently race.
- ``test_simulated_sibling_write_not_lost_sequential`` / ``test_simulated_same_run_conflict_...``:
  the retry loop's own read-modify-write dance is exercised with a "second writer" simulated
  SEQUENTIALLY, nested inside the current attempt's own ``apply_fn`` call (i.e. sequenced by the
  Python call stack, not truly concurrent). These do NOT exercise genuine OS-level concurrency —
  the temp-file-collision / lost-update failure mode CR-01 identified can never trigger from
  inside them, since nothing here is really racing. They are kept (relabeled per WR-02/CR-01)
  because they still document the intended read-modify-write field-preservation semantics, but
  ``test_real_concurrent_threads_no_lost_update_no_crash`` above is the genuine concurrency proof.
- ``test_mark_cli_preserves_siblings_through_retry_path``: the real ``mark`` CLI subcommand,
  routed through the retry-wrapped write path, still preserves every sibling run's fields
  unchanged (a regression-equivalent of ``test_gmj_batch.py``'s ``test_mark_preserves_siblings``).

Discipline (test_gmj_batch.py): every test asserts the exit code AND a specific field/sentinel,
and asserts ``"Traceback" not in`` any captured stderr so an unrelated crash's nonzero exit never
masquerades as a pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
BATCH = REPO_ROOT / "scripts" / "pipeline" / "gmj_batch.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "batch" / "shortlist.thin-and-rich.json"
SCHEMA = REPO_ROOT / "schemas" / "batch_manifest.schema.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
import gmj_batch  # noqa: E402


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BATCH), *args], cwd=str(cwd), capture_output=True, text=True
    )


def _init(cwd: Path, select: str, *, batch_id: str = "b1") -> subprocess.CompletedProcess[str]:
    return _cli(
        [
            "init",
            "--shortlist",
            str(FIXTURE),
            "--select",
            select,
            "--batch-id",
            batch_id,
            "--pipeline-dir",
            ".pipeline",
        ],
        cwd,
    )


def _run_ids(manifest: dict) -> dict[tuple[int, str], str]:
    """{(offer_index, artifact_key): run_id} across every per-(offer, artifact_type) run."""
    out: dict[tuple[int, str], str] = {}
    for off in manifest["offers"]:
        for key, run in off["runs"].items():
            out[(off["offer_index"], key)] = run["run_id"]
    return out


# --- Test 0: GENUINE concurrent threads racing the SAME manifest (CR-01) ----

def test_real_concurrent_threads_no_lost_update_no_crash() -> None:
    """The actual CR-01 regression: real, genuinely concurrent OS threads (NOT nested inside
    another attempt's own ``apply_fn``) call ``_mutate_manifest_with_retry`` against the SAME
    ``manifest.json`` at (as close to) the same instant as a ``threading.Barrier`` can force.
    Every thread targets a DISTINCT run_id, so a correct implementation must land every single
    update with none lost, and must never raise (the pre-fix code either silently lost a sibling's
    update or crashed with an uncaught ``FileNotFoundError`` from two writers colliding on the
    same literal ``manifest.json.tmp`` temp path).
    """
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        pipeline_dir = (cwd / ".pipeline").resolve()
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr

        manifest, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        rids = _run_ids(manifest)
        # Every (offer, artifact_type) run_id across both offers -- 6 distinct targets, one per
        # thread, so no two threads ever intend to mutate the same run.
        targets = list(rids.values())
        assert len(targets) == 6, targets

        barrier = threading.Barrier(len(targets))
        errors: list[BaseException] = []
        errors_lock = threading.Lock()

        def worker(run_id: str) -> None:
            barrier.wait()  # maximize genuine overlap of concurrent attempts

            def apply_fn(m: dict) -> None:
                for offer in m["offers"]:
                    for run in offer["runs"].values():
                        if run["run_id"] == run_id:
                            run["status"] = "in_flight"

            try:
                rc = gmj_batch._mutate_manifest_with_retry(pipeline_dir, "b1", apply_fn)
                if rc != 0:
                    with errors_lock:
                        errors.append(RuntimeError(f"{run_id}: non-zero rc {rc}"))
            except BaseException as exc:  # noqa: BLE001 -- must never crash (CR-01)
                with errors_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(rid,)) for rid in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"genuinely concurrent writers must never crash or fail: {errors}"

        final, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        by_id = {
            run["run_id"]: run["status"]
            for offer in final["offers"]
            for run in offer["runs"].values()
        }
        for rid in targets:
            assert by_id[rid] == "in_flight", (
                f"every genuinely concurrent writer's own update must land, none lost: {by_id}"
            )
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        errs = list(Draft202012Validator(schema).iter_errors(final))
        assert not errs, f"manifest must still validate after concurrent writes: {errs}"


# --- Test 0b: GENUINE concurrent double-`init` for the SAME --batch-id (WR-03) ----

def test_concurrent_double_init_same_batch_id_no_crash() -> None:
    """WR-03 regression: two genuinely concurrent ``init`` calls for the SAME ``batch_id`` (and
    thus the SAME per-(offer, artifact_type) ``run_id``s, i.e. the SAME ``state.json`` paths, and
    the SAME ``manifest.json`` path) must never crash with an uncaught ``FileNotFoundError``.

    Before the WR-03 fix: ``_seed_state`` used a shared literal ``".tmp"`` temp name (the exact
    bug class CR-01 fixed in ``write_manifest``), so two real concurrent writers racing to
    ``tmp_path.replace(state_path)`` for the SAME ``state_path`` could collide on the same temp
    file and crash; and ``_cmd_init``'s direct ``write_manifest`` call was unguarded by any lock,
    so two concurrent ``init`` calls for the same batch_id could race the manifest write with no
    coordination. This scenario is realistic for a duplicate dispatch, a retry-on-timeout wrapper
    firing twice, or an orchestration bug re-invoking ``init`` with the same ``--batch-id``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        pipeline_dir = (cwd / ".pipeline").resolve()

        def make_args() -> argparse.Namespace:
            return argparse.Namespace(
                shortlist=str(FIXTURE),
                select="1,2",
                batch_id="dup-batch",
                run_id_prefix=None,
                config=gmj_batch.DEFAULT_CONFIG,
                execution_mode=None,
                retry_cap=None,
                max_parallel_offers=None,
                pipeline_dir=str(pipeline_dir),
            )

        barrier = threading.Barrier(2)
        results: list[int] = []
        errors: list[BaseException] = []
        results_lock = threading.Lock()

        def worker() -> None:
            barrier.wait()  # maximize genuine overlap of both concurrent init calls
            try:
                rc = gmj_batch._cmd_init(make_args())
                with results_lock:
                    results.append(rc)
            except BaseException as exc:  # noqa: BLE001 -- must never crash (WR-03)
                with results_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"genuinely concurrent double-init must never crash: {errors}"
        assert results == [0, 0], f"both concurrent init calls must exit 0: {results}"

        manifest, _, _ = gmj_batch._load_manifest(pipeline_dir, "dup-batch")
        assert manifest is not None, "manifest.json must exist and be valid after double-init"
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        errs = list(Draft202012Validator(schema).iter_errors(manifest))
        assert not errs, f"manifest must still validate after concurrent double-init: {errs}"

        # Every seeded state.json (shared run_ids across both racing init calls) must be intact
        # JSON with current_step set -- never a partial write or a missing file from a lost rename.
        rids = _run_ids(manifest)
        for run_id in rids.values():
            state_path = pipeline_dir / "runs" / run_id / "state.json"
            assert state_path.is_file(), f"state.json must exist for {run_id}: {state_path}"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state.get("current_step") == "gmj-artifact-composer", (
                f"state.json for {run_id} must have current_step seeded: {state}"
            )


# --- Test 1 (sequential simulation, NOT genuine concurrency -- see module docstring) ---

def test_simulated_sibling_write_not_lost_sequential() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        pipeline_dir = (cwd / ".pipeline").resolve()
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr

        manifest, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        rids = _run_ids(manifest)
        target_run_id = rids[(0, "cv")]
        sibling_run_id = rids[(1, "cv")]

        landed = {"done": False}

        def apply_fn(m: dict) -> None:
            if not landed["done"]:
                # Simulate a SECOND, already-landed `mark` call for a SIBLING offer/run: a fresh
                # load + direct write via gmj_batch.write_manifest, landing on disk BEFORE this
                # call's own write.
                sib_manifest, sib_path, sib_batches_dir = gmj_batch._load_manifest(
                    pipeline_dir, "b1"
                )
                for offer in sib_manifest["offers"]:
                    for run in offer["runs"].values():
                        if run["run_id"] == sibling_run_id:
                            run["status"] = "delivered"
                gmj_batch.write_manifest(sib_manifest, sib_path, sib_batches_dir)
                landed["done"] = True
            # Mutate THIS call's own intended run's status on the (now provably stale,
            # pre-sibling-write) in-memory dict `m`.
            for offer in m["offers"]:
                for run in offer["runs"].values():
                    if run["run_id"] == target_run_id:
                        run["status"] = "in_flight"

        rc = gmj_batch._mutate_manifest_with_retry(pipeline_dir, "b1", apply_fn)
        assert rc == 0, "the retry loop must succeed despite the interleaved sibling write"

        final, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        by_id = {
            run["run_id"]: run["status"]
            for offer in final["offers"]
            for run in offer["runs"].values()
        }
        assert by_id[sibling_run_id] == "delivered", (
            "the sibling's interleaved update must NOT be lost across the two writes"
        )
        assert by_id[target_run_id] == "in_flight", "this call's own update must also be applied"


# --- Test 2 (sequential simulation, NOT genuine concurrency -- see module docstring) ---

def test_simulated_same_run_conflict_last_writer_wins_sequential() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        pipeline_dir = (cwd / ".pipeline").resolve()
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr

        manifest, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        rids = _run_ids(manifest)
        target_run_id = rids[(0, "cv")]

        landed = {"done": False}

        def apply_fn(m: dict) -> None:
            if not landed["done"]:
                # Simulate a genuinely CONFLICTING interleaved write targeting the EXACT SAME run
                # this call intends to mutate.
                conf_manifest, conf_path, conf_batches_dir = gmj_batch._load_manifest(
                    pipeline_dir, "b1"
                )
                for offer in conf_manifest["offers"]:
                    for run in offer["runs"].values():
                        if run["run_id"] == target_run_id:
                            run["status"] = "error"
                gmj_batch.write_manifest(conf_manifest, conf_path, conf_batches_dir)
                landed["done"] = True
            for offer in m["offers"]:
                for run in offer["runs"].values():
                    if run["run_id"] == target_run_id:
                        run["status"] = "gate_exhausted"

        rc = gmj_batch._mutate_manifest_with_retry(pipeline_dir, "b1", apply_fn)
        assert rc == 0, "the retry loop must succeed and resolve the genuine conflict"

        final, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        by_id = {
            run["run_id"]: run["status"]
            for offer in final["offers"]
            for run in offer["runs"].values()
        }
        assert by_id[target_run_id] == "gate_exhausted", (
            "the retry loop's OWN mutation must win (last-writer-via-retry), "
            f"not silently reverted to the interleaved 'error' value: {by_id}"
        )
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        errs = list(Draft202012Validator(schema).iter_errors(final))
        assert not errs, f"manifest must still validate after conflict resolution: {errs}"


# --- Test 3: `_cmd_mark` end-to-end via the CLI subprocess path --------------

def test_mark_cli_preserves_siblings_through_retry_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        pipeline_dir = (cwd / ".pipeline").resolve()
        assert _init(cwd, "1,2").returncode == 0

        before, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        before_copy = json.loads(json.dumps(before))
        rids = _run_ids(before)
        target = rids[(0, "cv")]

        r = _cli(
            [
                "mark",
                "--batch",
                "b1",
                "--run-id",
                target,
                "--status",
                "delivered",
                "--pipeline-dir",
                ".pipeline",
            ],
            cwd,
        )
        assert r.returncode == 0, f"mark must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr

        after, _, _ = gmj_batch._load_manifest(pipeline_dir, "b1")
        expected = before_copy
        expected["offers"][0]["runs"]["cv"]["status"] = "delivered"
        assert after == expected, (
            "ONLY the targeted run's status may change through the retry-wrapped mark path — "
            f"no sibling key may be dropped or altered: {after}"
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
