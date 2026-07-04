#!/usr/bin/env python3
"""Tests for scripts/pipeline/gmj_batch.py (SELECT-01, SELECT-02, SELECT-03 + path-traversal).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_batch.py``. Proves the EXECUTED deterministic batch engine (not an
LLM) guarantees:

- a selection string (`1,2` / `all`) resolves to the correct 0-based offer indices; out-of-range,
  non-numeric, empty, and duplicate tokens are rejected or deduped deterministically (SELECT-01),
- a coarse shortlist entry maps to a freeze-draft copying only the schema-present fields
  (title/company/location/seniority/language + source_url/raw_text_excerpt), dropping the
  non-schema keys (board/canonical_key/score/mode/salary); a `thin` flag is emitted (SELECT-02),
- each selected offer produces three distinct per-(offer, artifact_type) run_ids
  (`<run_id>-cv`/`-cl`/`-ip`) and three distinct seeded `state.json` files — no shared state file
  across offers OR artifact types; each seeded with `current_step: artifact-composer` (SELECT-03),
- the batch manifest validates against schemas/batch_manifest.schema.json and is byte-identical
  across two PYTHONHASHSEED values (SELECT-03),
- a `batch_id` containing `..`/`/`/`\\` is rejected (exit 1) and writes no file outside
  `.pipeline/batches/` (T-12-01 path-traversal).

Discipline (test_merge_shortlists.py:16-17): every test asserts the exit code AND a specific
field/sentinel, and asserts ``"Traceback" not in result.stderr`` so an unrelated crash's nonzero
exit never masquerades as a pass.
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
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "batch" / "shortlist.thin-and-rich.json"
SCHEMA = REPO_ROOT / "schemas" / "batch_manifest.schema.json"

# In-repo helpers reused by the idempotency test (mirrors test_merge_shortlists.py's
# sys.path-insert import idiom): coarse_to_draft from gmj_batch + freeze from freeze_offer.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "offers"))
import gmj_batch  # noqa: E402
import freeze_offer  # noqa: E402


def _cli(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BATCH), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _init(
    cwd: Path,
    select: str,
    *,
    batch_id: str = "b1",
    shortlist: Path | None = None,
    pipeline_dir: str = ".pipeline",
    extra: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        "init",
        "--shortlist",
        str(shortlist or FIXTURE),
        "--select",
        select,
        "--batch-id",
        batch_id,
        "--pipeline-dir",
        pipeline_dir,
    ]
    if extra:
        args.extend(extra)
    return _cli(args, cwd, env=env)


def _parse_offers(stdout: str) -> tuple[str, list[dict]]:
    """Parse the init stdout contract into (batch_id, [{offer_index, run_id, thin}, ...])."""
    batch_id = ""
    offers: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = dict(tok.split("=", 1) for tok in line.split() if "=" in tok)
        if "batch_id" in fields and "offer_index" not in fields:
            batch_id = fields["batch_id"]
        elif "offer_index" in fields:
            offers.append(
                {
                    "offer_index": int(fields["offer_index"]),
                    "run_id": fields["run_id"],
                    "thin": fields["thin"] == "true",
                }
            )
    return batch_id, offers


# --- SELECT-01: selection resolution -----------------------------------------

def test_select_explicit_indices() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        _, offers = _parse_offers(r.stdout)
        idxs = sorted(o["offer_index"] for o in offers)
        assert idxs == [0, 1], f"select '1,2' must resolve to offer_index 0 and 1: {idxs}"


def test_select_all() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "all")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        _, offers = _parse_offers(r.stdout)
        idxs = sorted(o["offer_index"] for o in offers)
        assert idxs == [0, 1], f"select 'all' must select every entry: {idxs}"


def test_select_out_of_range_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "9")
        assert r.returncode == 1, f"select '9' must exit 1: {r.stdout}"
        assert "out of range" in r.stderr.lower(), f"stderr must name out-of-range: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr


def test_select_non_numeric_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "abc")
        assert r.returncode == 1, f"select 'abc' must exit 1: {r.stdout}"
        assert "invalid selection token" in r.stderr.lower(), (
            f"stderr must name the invalid token: {r.stderr}"
        )
        assert "Traceback" not in r.stderr, r.stderr


def test_select_dedup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1,1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        _, offers = _parse_offers(r.stdout)
        idxs = sorted(o["offer_index"] for o in offers)
        assert idxs == [0, 1], f"'1,1,2' must dedup to offer_index 0 and 1 once each: {idxs}"


# --- SELECT-02: coarse->draft mapping + too-thin flag ------------------------

def test_coarse_map_copies_present_fields_drops_non_schema() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "2")  # the enriched entry (offer_index 1)
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        draft_path = cwd / ".pipeline" / "batches" / "b1" / "drafts" / "offer-001.draft.json"
        assert draft_path.is_file(), f"a freeze-draft must be written for the offer: {draft_path}"
        draft = json.loads(draft_path.read_text())
        # present schema fields copied
        for k in ("title", "company", "location", "seniority", "language"):
            assert k in draft, f"draft must copy present schema field {k!r}: {draft}"
        # trace.source_url -> source_url, trace.excerpt -> raw_text_excerpt
        assert draft.get("source_url") == "https://robota.ua/company/softpeak/vacancy/325215", (
            f"draft must map trace.source_url -> source_url: {draft}"
        )
        assert "raw_text_excerpt" in draft and draft["raw_text_excerpt"], (
            f"draft must map trace.excerpt -> raw_text_excerpt: {draft}"
        )
        # non-schema keys dropped
        for k in ("board", "canonical_key", "score", "mode", "salary", "trace"):
            assert k not in draft, f"draft must drop non-schema key {k!r}: {draft}"


def test_thin_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        _, offers = _parse_offers(r.stdout)
        by_idx = {o["offer_index"]: o for o in offers}
        assert by_idx[0]["thin"] is True, f"the thin entry (idx 0) must print thin: true: {offers}"
        assert by_idx[1]["thin"] is False, (
            f"the enriched entry (idx 1) must print thin: false: {offers}"
        )


# --- SELECT-03: per-offer run isolation + manifest ---------------------------

def test_per_offer_run_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        _, offers = _parse_offers(r.stdout)
        assert len(offers) == 2, f"two selected offers expected: {offers}"
        runs_dir = cwd / ".pipeline" / "runs"
        state_paths = []
        for o in offers:
            base = o["run_id"]
            # NO state.json at the bare offer run_id
            assert not (runs_dir / base / "state.json").is_file(), (
                f"no state.json may exist at the bare offer run_id {base}"
            )
            for suffix in ("cv", "cl", "ip"):
                sp = runs_dir / f"{base}-{suffix}" / "state.json"
                assert sp.is_file(), f"per-(offer, artifact_type) state.json missing: {sp}"
                state = json.loads(sp.read_text())
                assert state.get("current_step") == "artifact-composer", (
                    f"seeded state must set current_step=artifact-composer: {sp} -> {state}"
                )
                state_paths.append(sp.resolve())
        # six distinct state.json dirs (2 offers x 3 artifact types)
        assert len(state_paths) == 6, f"expected 6 seeded states, got {len(state_paths)}"
        assert len(set(state_paths)) == 6, f"all six state paths must be distinct: {state_paths}"


def test_manifest_validates() -> None:
    from jsonschema import Draft202012Validator

    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1,2")
        assert r.returncode == 0, f"init must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        manifest_path = cwd / ".pipeline" / "batches" / "b1" / "manifest.json"
        assert manifest_path.is_file(), f"manifest must be written: {manifest_path}"
        schema = json.loads(SCHEMA.read_text())
        doc = json.loads(manifest_path.read_text())
        errs = list(Draft202012Validator(schema).iter_errors(doc))
        assert not errs, f"manifest must validate against batch_manifest.schema.json: {errs}"


def test_manifest_byte_identical_two_hashseeds() -> None:
    with tempfile.TemporaryDirectory() as tmp0, tempfile.TemporaryDirectory() as tmp1:
        cwd0, cwd1 = Path(tmp0), Path(tmp1)
        r0 = _init(cwd0, "1,2", env={"PYTHONHASHSEED": "0"})
        r1 = _init(cwd1, "1,2", env={"PYTHONHASHSEED": "1"})
        assert r0.returncode == 0, f"run0 must exit 0: {r0.stderr}"
        assert r1.returncode == 0, f"run1 must exit 0: {r1.stderr}"
        assert "Traceback" not in r0.stderr and "Traceback" not in r1.stderr
        m0 = (cwd0 / ".pipeline" / "batches" / "b1" / "manifest.json").read_bytes()
        m1 = (cwd1 / ".pipeline" / "batches" / "b1" / "manifest.json").read_bytes()
        assert m0 == m1, "manifest must be byte-identical across PYTHONHASHSEED 0 and 1"


# --- security: path traversal ------------------------------------------------

def test_unsafe_batch_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r = _init(cwd, "1", batch_id="../evil")
        assert r.returncode == 1, f"'../evil' batch_id must exit 1: {r.stdout}"
        assert "unsafe" in r.stderr.lower(), f"stderr must name the unsafe id: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        # no file written outside .pipeline/batches/
        assert not (cwd / "evil").exists(), "no file may be written outside .pipeline/batches/"
        assert not (cwd.parent / "evil").exists(), "no escape above the temp cwd"


# --- SELECT-04 / SELECT-03 status-lifecycle: mark, resume, record-spec --------
#
# Delivery truth here is label-AND-gate (CR-01): a run is delivered ONLY when its manifest
# `status` label == "delivered" (set by the persona via `mark` AFTER the terminal cv-generator
# render — the render-complete signal; gate-pass alone is one DAG step too early) AND the
# recorded gate verdict still passes — each per-(offer, artifact_type) run's `state.json`
# `gate_results` re-checked via check_delivery.blocked_reason (Gate A ∧ Gate B), a cross-check
# so a forged/corrupt "delivered" label without a real gate pass is never trusted. NEVER a
# rendered-PDF path convention (state.json records no artifact path; renderers emit timestamped
# non-run-keyed filenames; interview_prep is a .md; render_cv prunes older PDFs — a PDF conjunct
# would spuriously re-run delivered offers). Rendered-artifact existence is a Manual-Only UAT
# check (12-VALIDATION.md), never part of this automated resume predicate.


def _mark(
    cwd: Path, run_id: str, status: str, *, batch_id: str = "b1", pipeline_dir: str = ".pipeline"
) -> subprocess.CompletedProcess[str]:
    return _cli(
        ["mark", "--batch", batch_id, "--run-id", run_id, "--status", status,
         "--pipeline-dir", pipeline_dir],
        cwd,
    )


def _resume(
    cwd: Path, *, batch_id: str = "b1", pipeline_dir: str = ".pipeline"
) -> subprocess.CompletedProcess[str]:
    return _cli(["resume", "--batch", batch_id, "--pipeline-dir", pipeline_dir], cwd)


def _record_spec(
    cwd: Path, offer_index: int, path: str, spec_hash: str, *,
    batch_id: str = "b1", pipeline_dir: str = ".pipeline",
) -> subprocess.CompletedProcess[str]:
    return _cli(
        ["record-spec", "--batch", batch_id, "--offer-index", str(offer_index),
         "--offer-spec-path", path, "--offer-spec-hash", spec_hash, "--pipeline-dir", pipeline_dir],
        cwd,
    )


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
    """Stamp recorded gate_results into a per-(offer, artifact_type) state.json (the resume truth)."""
    sp = cwd / pipeline_dir / "runs" / run_id / "state.json"
    state = json.loads(sp.read_text())
    gr: dict[str, str] = {}
    if truth is not None:
        gr["truth-verifier"] = truth
    if fit is not None:
        gr["fit-evaluator"] = fit
    state["gate_results"] = gr
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_resume(stdout: str) -> list[dict]:
    """Parse resume stdout into [{offer_index, artifact_type, run_id}, ...]."""
    runs: list[dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        f = dict(tok.split("=", 1) for tok in line.split() if "=" in tok)
        if "run_id" in f and "offer_index" in f:
            runs.append(
                {
                    "offer_index": int(f["offer_index"]),
                    "artifact_type": f.get("artifact_type"),
                    "run_id": f["run_id"],
                }
            )
    return runs


def _canonical(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def test_mark_preserves_siblings() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1,2").returncode == 0
        before = _load_manifest(cwd)
        target = _run_ids(before)[(0, "cv")]
        r = _mark(cwd, target, "delivered")
        assert r.returncode == 0, f"mark must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        after = _load_manifest(cwd)
        assert after["offers"][0]["runs"]["cv"]["status"] == "delivered", (
            f"targeted run status must become delivered: {after}"
        )
        expected = json.loads(json.dumps(before))
        expected["offers"][0]["runs"]["cv"]["status"] = "delivered"
        assert after == expected, "ONLY the targeted run's status may change — no sibling key dropped"


def test_mark_reemits_canonical() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1").returncode == 0
        target = _run_ids(_load_manifest(cwd))[(0, "interview_prep")]
        r = _mark(cwd, target, "failed")
        assert r.returncode == 0, f"mark must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        raw = _manifest_path(cwd).read_text()
        assert raw == _canonical(json.loads(raw)), (
            "manifest after mark must be byte-identical to a canonical re-serialization of itself"
        )


def test_mark_unknown_run_id_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1").returncode == 0
        before = _manifest_path(cwd).read_bytes()
        r = _mark(cwd, "nonexistent-run", "delivered")
        assert r.returncode == 1, f"unknown run_id must exit 1: {r.stdout}"
        assert "not found" in r.stderr.lower(), f"stderr must say not found: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        assert _manifest_path(cwd).read_bytes() == before, "no change may be written on unknown run_id"


def test_resume_skips_delivered() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1,2").returncode == 0
        rids = _run_ids(_load_manifest(cwd))
        # offer 0 cv: BOTH gates pass AND the terminal render marked the label 'delivered'
        # (label-AND-gate) -> delivered (blocked_reason None) -> omitted from resume set.
        _set_gates(cwd, rids[(0, "cv")], truth="pass", fit="pass")
        assert _mark(cwd, rids[(0, "cv")], "delivered").returncode == 0
        # every other run keeps its init-seeded state (pending, no gate_results) -> non-delivered.
        r = _resume(cwd)
        assert r.returncode == 0, f"resume must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        out_ids = {x["run_id"] for x in _parse_resume(r.stdout)}
        assert rids[(0, "cv")] not in out_ids, (
            "a genuinely-delivered run (label 'delivered' AND gates pass) must be skipped (omitted)"
        )
        assert rids[(0, "cover_letter")] in out_ids, "a non-delivered run must be re-listed"


def test_resume_running_label_not_delivered_even_with_passing_gates() -> None:
    # CR-01: gate-pass is one render-step too early. cv-generator (the terminal DAG node)
    # renders AFTER both gates, so a 'running' (non-'delivered') label means the artifact was
    # never rendered/delivered even though BOTH gates recorded pass. The run MUST appear in the
    # resume set so it is re-run/re-rendered — the exact deliverable-loss this feature prevents.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1").returncode == 0
        target = _run_ids(_load_manifest(cwd))[(0, "cv")]
        # recorded gates BOTH pass...
        _set_gates(cwd, target, truth="pass", fit="pass")
        # ...but a crash before cv-generator left the label at 'running' (never 'delivered').
        assert _mark(cwd, target, "running").returncode == 0
        r = _resume(cwd)
        assert r.returncode == 0, f"resume must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        out_ids = {x["run_id"] for x in _parse_resume(r.stdout)}
        assert target in out_ids, (
            "gates pass but label != 'delivered' => render never completed => run must be resumed"
        )


def test_resume_delivered_label_but_gate_failed_is_not_delivered() -> None:
    # CR-01 cross-check: a forged/corrupt 'delivered' label without a real gate pass must NOT be
    # trusted. Label-AND-gate keeps the run in the resume set when a recorded gate has failed.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1").returncode == 0
        target = _run_ids(_load_manifest(cwd))[(0, "cv")]
        # Gate B recorded FAIL, yet the manifest label claims 'delivered'.
        _set_gates(cwd, target, truth="pass", fit="fail")
        assert _mark(cwd, target, "delivered").returncode == 0
        r = _resume(cwd)
        assert r.returncode == 0, f"resume must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        out_ids = {x["run_id"] for x in _parse_resume(r.stdout)}
        assert target in out_ids, (
            "a 'delivered' label with a FAILED gate is not trustworthy -> run must be resumed"
        )


def test_resume_recomputes_pending_when_gate_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1").returncode == 0
        rids = _run_ids(_load_manifest(cwd))
        # cv: Gate B recorded FAIL -> blocked_reason not None -> included.
        _set_gates(cwd, rids[(0, "cv")], truth="pass", fit="fail")
        # cl: init-seeded, gate_results entirely absent (crash before Gate A) -> included.
        r = _resume(cwd)
        assert r.returncode == 0, f"resume must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        out_ids = {x["run_id"] for x in _parse_resume(r.stdout)}
        assert rids[(0, "cv")] in out_ids, "a recorded FAILED gate must be recomputed as pending"
        assert rids[(0, "cover_letter")] in out_ids, "an absent gate_results must be recomputed as pending"


def test_record_spec_writes_hash() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        assert _init(cwd, "1,2").returncode == 0
        before = _load_manifest(cwd)
        spec_path = "sources/offers/softpeak.offer-spec.json"
        spec_hash = "a" * 64
        r = _record_spec(cwd, 0, spec_path, spec_hash)
        assert r.returncode == 0, f"record-spec must exit 0: {r.stderr}"
        assert "Traceback" not in r.stderr, r.stderr
        after = _load_manifest(cwd)
        assert after["offers"][0]["offer_spec_path"] == spec_path, "offer_spec_path must be written"
        assert after["offers"][0]["offer_spec_hash"] == spec_hash, "offer_spec_hash must be written"
        expected = json.loads(json.dumps(before))
        expected["offers"][0]["offer_spec_path"] = spec_path
        expected["offers"][0]["offer_spec_hash"] = spec_hash
        assert after == expected, "ONLY offer 0's spec fields may change — runs statuses untouched"
        raw = _manifest_path(cwd).read_text()
        assert raw == _canonical(json.loads(raw)), "manifest must re-emit byte-identical canonical JSON"
        # unknown offer-index rejected
        r2 = _record_spec(cwd, 99, spec_path, spec_hash)
        assert r2.returncode == 1, f"unknown offer-index must exit 1: {r2.stdout}"
        assert "not found" in r2.stderr.lower(), f"stderr must say not found: {r2.stderr}"
        assert "Traceback" not in r2.stderr, r2.stderr


def test_refreeze_idempotent_hash() -> None:
    # Re-running an already-delivered offer is safe: re-freezing the same coarse entry yields
    # the same offer_spec_hash (freeze is hash-stable across captured_at — mirrors
    # test_freeze_offer.py:test_hash_stable_across_captured_at).
    entries = json.loads(FIXTURE.read_text())["shortlist"]
    enriched = entries[1]  # the must_haves+excerpt entry
    draft = gmj_batch.coarse_to_draft(enriched)
    a = freeze_offer.freeze(draft, "2026-07-03T10:00:00Z")
    b = freeze_offer.freeze(draft, "2026-08-01T00:00:00Z")
    assert a["offer_spec_hash"] == b["offer_spec_hash"], (
        "re-freezing the same coarse entry must yield the same offer_spec_hash (idempotent resume)"
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
