#!/usr/bin/env python3
"""Tests for gmj_batch.py's concurrency-safe manifest write path (CONC-03).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_batch_manifest_concurrency.py``. Proves:

- ``_mutate_manifest_with_retry`` never loses a SIBLING offer/run's interleaved update — two
  read-modify-write cycles racing on the SAME ``manifest.json`` both land (Test 1),
- a genuinely CONFLICTING interleaved write (same run this call intends to mutate) resolves via
  the retry loop's own mutation winning (last-writer-via-retry), not a silent revert, and the
  manifest still validates against ``schemas/batch_manifest.schema.json`` (Test 2),
- the real ``mark`` CLI subcommand, now routed through the retry-wrapped write path, still
  preserves every sibling run's fields unchanged (Test 3, a regression-equivalent of
  ``test_gmj_batch.py``'s ``test_mark_preserves_siblings``).

Discipline (test_gmj_batch.py): every test asserts the exit code AND a specific field/sentinel,
and asserts ``"Traceback" not in`` any captured stderr so an unrelated crash's nonzero exit never
masquerades as a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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


# --- Test 1: interleaved SIBLING write is never lost -------------------------

def test_mutate_with_retry_sibling_write_not_lost() -> None:
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


# --- Test 2: genuinely CONFLICTING interleaved write on the SAME run ---------

def test_mutate_with_retry_same_run_conflict_last_writer_wins() -> None:
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
