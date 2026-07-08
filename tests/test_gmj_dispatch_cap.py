#!/usr/bin/env python3
"""Tests for scripts/pipeline/gmj_dispatch_cap.py (CONC-02).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_dispatch_cap.py``. Proves the deterministic offer-level
dispatch-cap query correctly derives {"dispatchable","in_flight","cap","waiting"} from a
real ``gmj_batch.py init``-produced manifest, WITHOUT ever writing to disk, and — the
Pitfall 2 regression this script exists to close — that a mid-retry offer (an
already-dispatched, still-"in_flight" run) keeps occupying a concurrency slot rather than
being mistaken for free capacity. It also proves the T-35-04 label-AND-gate double-check:
a forged/stale "delivered" label without a real recorded gate pass is NOT free capacity.

Fixtures are built via a real ``gmj_batch.py init`` subprocess call against
``tests/fixtures/batch/shortlist.thin-and-rich.json`` (2 offers), then specific runs'
``manifest.json`` ``status`` fields and/or their ``state.json`` files are hand-edited to
construct each scenario, before invoking ``gmj_dispatch_cap.py --batch <id>
--pipeline-dir <dir>`` as a subprocess and asserting on its parsed JSON stdout.

Discipline (test_check_cap.py / test_gmj_batch.py): every test asserts the exit code AND
a specific field/sentinel, and asserts ``"Traceback" not in result.stderr`` so an
unrelated crash's nonzero exit never masquerades as a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BATCH = REPO_ROOT / "scripts" / "pipeline" / "gmj_batch.py"
DISPATCH = REPO_ROOT / "scripts" / "pipeline" / "gmj_dispatch_cap.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "batch" / "shortlist.thin-and-rich.json"


def _cli(script: Path, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )


def _init(
    cwd: Path,
    select: str,
    *,
    batch_id: str = "b1",
    max_parallel_offers: int | None = None,
    pipeline_dir: str = ".pipeline",
) -> subprocess.CompletedProcess[str]:
    args = [
        "init",
        "--shortlist",
        str(FIXTURE),
        "--select",
        select,
        "--batch-id",
        batch_id,
        "--pipeline-dir",
        pipeline_dir,
    ]
    if max_parallel_offers is not None:
        args.extend(["--max-parallel-offers", str(max_parallel_offers)])
    return _cli(BATCH, args, cwd)


def _mark(
    cwd: Path, run_id: str, status: str, *, batch_id: str = "b1", pipeline_dir: str = ".pipeline"
) -> subprocess.CompletedProcess[str]:
    return _cli(
        BATCH,
        [
            "mark", "--batch", batch_id, "--run-id", run_id, "--status", status,
            "--pipeline-dir", pipeline_dir,
        ],
        cwd,
    )


def _dispatch(
    cwd: Path, *, batch_id: str = "b1", pipeline_dir: str = ".pipeline"
) -> subprocess.CompletedProcess[str]:
    return _cli(DISPATCH, ["--batch", batch_id, "--pipeline-dir", pipeline_dir], cwd)


def _manifest_path(cwd: Path, batch_id: str = "b1", pipeline_dir: str = ".pipeline") -> Path:
    return cwd / pipeline_dir / "batches" / batch_id / "manifest.json"


def _load_manifest(cwd: Path, batch_id: str = "b1", pipeline_dir: str = ".pipeline") -> dict:
    return json.loads(_manifest_path(cwd, batch_id, pipeline_dir).read_text())


def _run_ids(manifest: dict) -> dict[tuple[int, str], str]:
    """{(offer_index, artifact_key): run_id} across every per-(offer, artifact_type) run."""
    out: dict[tuple[int, str], str] = {}
    for off in manifest["offers"]:
        for key, run in off["runs"].items():
            out[(off["offer_index"], key)] = run["run_id"]
    return out


def _set_gates(
    cwd: Path, run_id: str, *, truth: str | None = None, fit: str | None = None,
    pipeline_dir: str = ".pipeline",
) -> None:
    """Stamp recorded gate_results into a per-(offer, artifact_type) state.json."""
    sp = cwd / pipeline_dir / "runs" / run_id / "state.json"
    state = json.loads(sp.read_text())
    gr: dict[str, str] = {}
    if truth is not None:
        gr["gmj-truth-verifier"] = truth
    if fit is not None:
        gr["gmj-fit-evaluator"] = fit
    state["gate_results"] = gr
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_dispatch(stdout: str) -> dict:
    return json.loads(stdout.strip())


# --- Test 1: below cap, all fresh --------------------------------------------

def test_below_cap_all_fresh_all_dispatchable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "all", max_parallel_offers=5).returncode == 0
        manifest = _load_manifest(cwd)
        rids = _run_ids(manifest)
        r = _dispatch(cwd)
        assert r.returncode == 0, f"dispatch must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        report = _parse_dispatch(r.stdout)
        assert set(report["dispatchable"]) == set(rids.values()), (
            f"every offer's 3 run_ids must be dispatchable when below cap: {report!r}"
        )
        assert report["in_flight"] == 0, report
        assert report["waiting"] == [], report
        assert report["cap"] == 5, report


# --- Test 2: at cap, remaining offers wait -----------------------------------

def test_at_cap_remaining_offers_wait() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "all", max_parallel_offers=1).returncode == 0
        manifest = _load_manifest(cwd)
        rids = _run_ids(manifest)
        r = _dispatch(cwd)
        assert r.returncode == 0, f"dispatch must exit 0: {r.stderr}"
        report = _parse_dispatch(r.stdout)
        expected_dispatchable = {rid for (idx, _key), rid in rids.items() if idx == 0}
        assert set(report["dispatchable"]) == expected_dispatchable, (
            f"only the first cap(=1) offer's run_ids are dispatchable: {report!r}"
        )
        assert report["waiting"] == [1], report
        assert report["in_flight"] == 0, report
        assert report["cap"] == 1, report


# --- Test 3: mid-retry offer counts as in_flight (Pitfall 2 regression) -----

def test_mid_retry_offer_counts_as_in_flight() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "all", max_parallel_offers=5).returncode == 0
        rids = _run_ids(_load_manifest(cwd))
        cv_run = rids[(0, "cv")]
        assert _mark(cwd, cv_run, "in_flight").returncode == 0
        r = _dispatch(cwd)
        assert r.returncode == 0, f"dispatch must exit 0: {r.stderr}"
        report = _parse_dispatch(r.stdout)
        assert report["in_flight"] >= 1, (
            f"a mid-retry (in_flight) run must count its offer as in_flight: {report!r}"
        )
        # The already-active offer's still-non-terminal run_ids (cv + its "waiting"
        # siblings) all keep advancing — they don't re-queue as fresh candidates.
        offer0_run_ids = {rids[(0, "cv")], rids[(0, "cover_letter")], rids[(0, "interview_prep")]}
        assert offer0_run_ids.issubset(set(report["dispatchable"])), (
            f"active offer's non-terminal run_ids must all remain dispatchable: {report!r}"
        )


# --- Test 4: terminal offer frees a slot -------------------------------------

def test_terminal_offer_frees_a_slot() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "all", max_parallel_offers=5).returncode == 0
        rids = _run_ids(_load_manifest(cwd))
        offer0_run_ids = [rids[(0, "cv")], rids[(0, "cover_letter")], rids[(0, "interview_prep")]]
        for rid in offer0_run_ids:
            _set_gates(cwd, rid, truth="pass", fit="pass")
            assert _mark(cwd, rid, "delivered").returncode == 0
        r = _dispatch(cwd)
        assert r.returncode == 0, f"dispatch must exit 0: {r.stderr}"
        report = _parse_dispatch(r.stdout)
        for rid in offer0_run_ids:
            assert rid not in report["dispatchable"], (
                f"a fully-terminal offer's run_ids must not be dispatchable: {report!r}"
            )
            assert rid not in report.get("waiting", []), report
        # A terminal offer contributes 0 to in_flight.
        assert report["in_flight"] == 0, report


# --- Test 5: forged delivered label without real gates is NOT free capacity --

def test_forged_delivered_label_without_gates_is_not_free_capacity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "all", max_parallel_offers=5).returncode == 0
        rids = _run_ids(_load_manifest(cwd))
        cv_run = rids[(0, "cv")]
        # No _set_gates call -> gate_results stays absent/empty in state.json.
        assert _mark(cwd, cv_run, "delivered").returncode == 0
        r = _dispatch(cwd)
        assert r.returncode == 0, f"dispatch must exit 0: {r.stderr}"
        report = _parse_dispatch(r.stdout)
        assert report["in_flight"] >= 1, (
            f"a forged 'delivered' label without a real gate pass must NOT count as "
            f"free capacity — offer must remain ACTIVE: {report!r}"
        )


# --- Test 6: PRESENT but non-int max_parallel_offers is rejected ------------

def test_non_int_manifest_cap_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1", max_parallel_offers=3).returncode == 0
        mp = _manifest_path(cwd)

        # Non-int max_parallel_offers is still a hard error -- only a MISSING field falls
        # back to a default (WR-01); a present-but-invalid value is a genuine malformed
        # manifest and must still fail closed.
        manifest = json.loads(mp.read_text())
        manifest["max_parallel_offers"] = "three"
        mp.write_text(json.dumps(manifest))
        r = _dispatch(cwd)
        assert r.returncode == 1, "non-int max_parallel_offers must exit 1"
        assert "max_parallel_offers" in r.stderr, r.stderr
        assert "Traceback" not in r.stderr, r.stderr


# --- Test 6b: MISSING max_parallel_offers falls back to a default (WR-01) ----

def test_missing_max_parallel_offers_falls_back_to_config_default() -> None:
    """``batch_manifest.schema.json`` documents that manifests written before this field
    existed "remain valid" (the field is not in ``required``). ``gmj_dispatch_cap.py`` must
    therefore fall back to the same default ``gmj_batch.py init`` itself would resolve
    (``config/pipeline.config.yaml``'s ``max_parallel_offers``, default 3) instead of
    hard-failing on a manifest that simply predates the field (WR-01 regression)."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1", max_parallel_offers=3).returncode == 0
        mp = _manifest_path(cwd)

        manifest = json.loads(mp.read_text())
        del manifest["max_parallel_offers"]
        mp.write_text(json.dumps(manifest))
        r = _dispatch(cwd)
        assert r.returncode == 0, (
            f"a manifest missing max_parallel_offers must fall back to a default, not fail "
            f"(schema's own backward-compatibility guarantee): {r.stderr}"
        )
        assert "Traceback" not in r.stderr, r.stderr
        report = _parse_dispatch(r.stdout)
        assert report["cap"] == 3, (
            f"missing field must fall back to config/pipeline.config.yaml's max_parallel_offers "
            f"(3): {report!r}"
        )


# --- Test 7: unsafe --batch ---------------------------------------------------

def test_unsafe_batch_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _dispatch(cwd, batch_id="../evil")
        assert r.returncode == 1, "unsafe --batch must exit 1"
        assert "unsafe" in r.stderr.lower(), r.stderr
        assert "Traceback" not in r.stderr, r.stderr


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
