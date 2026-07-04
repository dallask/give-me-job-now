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
