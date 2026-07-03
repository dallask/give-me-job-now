#!/usr/bin/env python3
"""Deterministic-category unit tests for the score_fit.py Gate-B scorer (Plan 06-04).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. Each test proves an EXECUTED deterministic invariant of the
Gate-B coverage core — never LLM ``coverage_map`` accuracy (that is the non-blocking
``calibrate_fit.py`` report / UAT, not here). The deterministic category asserted here is:

- coverage counted from the INPUT ``coverage_map`` against ``mh-N`` index IDs (FIT-01),
- byte-identical output across repeated runs on unchanged input (SC1),
- below-threshold exits 1 and names ``why.missing_must_haves`` (FIT-02); at/above exits 0,
- the emitted ``why`` is a structured object (coverage string + missing list), never a bare
  number substituting for the reason (FIT-03),
- empty ``must_haves`` → score 1.0, exit 0, no traceback (Pitfall 6),
- Gate C polish is structurally separate and never changes the Gate B exit code (FIT-05),
- an out-of-range / negative / non-int claim_index does NOT count an mh as covered (T-06-13),
- no override/bypass/force flag exists in the source (T-06-12 non-bypass),
- the emitted Gate B content validates against gate_result.schema.json#/$defs/gate_b_content.

Only stdlib + PyYAML + jsonschema are used.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from validate_envelope import build_registry  # noqa: E402  reuse the local schema registry

SCORE_FIT = REPO_ROOT / "scripts" / "artifacts" / "score_fit.py"
FIT = FIXTURES / "fit"
SCHEMA_DIR = REPO_ROOT / "schemas"
GATE_RESULT_SCHEMA = SCHEMA_DIR / "gate_result.schema.json"

OFFER = FIT / "offer.python-mid.sample.json"
OFFER_EMPTY = FIT / "offer.empty-musthaves.sample.json"

PASS_DRAFT = FIT / "pass.draft.json"
PASS_MAP = FIT / "pass.coverage_map.json"
FAIL_DRAFT = FIT / "fail.draft.json"
FAIL_MAP = FIT / "fail.coverage_map.json"
BORDERLINE_DRAFT = FIT / "borderline.draft.json"
BORDERLINE_MAP = FIT / "borderline.coverage_map.json"
PASS_POLISH = FIT / "pass.polish.json"


def _run_fit(
    draft: Path, offer: Path, cmap: Path, polish: Path | None = None
) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(SCORE_FIT),
        "--file",
        str(draft),
        "--offer",
        str(offer),
        "--coverage-map",
        str(cmap),
    ]
    if polish is not None:
        cmd += ["--polish", str(polish)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))


def _write_tmp(obj: object) -> Path:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(obj, fh)
        return Path(fh.name)


def test_coverage_counted_from_map() -> None:
    result = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    assert result.returncode == 0, (
        f"pass fixture (0.8 >= 0.7) must exit 0, got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    content = json.loads(result.stdout)["gate_b"]["content"]
    coverage = content["coverage"]
    assert coverage["covered_ids"] == ["mh-0", "mh-1", "mh-2", "mh-3"], (
        f"coverage must be counted from the input map (4 covered), got {coverage}"
    )
    assert coverage["missing_ids"] == ["mh-4"], (
        f"mh-4 (empty mapped list) must be missing, got {coverage['missing_ids']}"
    )
    assert abs(coverage["score"] - 0.8) < 1e-9, (
        f"score must be 4/5 = 0.8, got {coverage['score']}"
    )
    assert all(cid.startswith("mh-") for cid in coverage["covered_ids"]), (
        "coverage IDs must be mh-N index IDs, never LLM-assigned"
    )


def test_reproducible_across_runs() -> None:
    first = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    second = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    assert first.returncode == second.returncode == 0, (
        f"both runs must exit 0, got {first.returncode}/{second.returncode}"
    )
    assert first.stdout == second.stdout, (
        "SC1: score_fit.py must emit byte-identical stdout across repeated runs on "
        "unchanged input (coverage_map is an input, count_coverage is pure)"
    )


def test_below_threshold_exits_1_names_missing() -> None:
    result = _run_fit(FAIL_DRAFT, OFFER, FAIL_MAP)
    assert result.returncode == 1, (
        f"fail fixture (1/5 < 0.7) must exit 1, got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    content = json.loads(result.stdout)["gate_b"]["content"]
    assert content["verdict"] == "fail", f"verdict must be fail, got {content['verdict']}"
    missing = content["why"]["missing_must_haves"]
    assert isinstance(missing, list) and missing, (
        f"why.missing_must_haves must name the missing must-haves, got {missing}"
    )
    assert all("id" in m and "text" in m for m in missing), (
        f"each missing must-have must carry {{id, text}}, got {missing}"
    )
    missing_ids = [m["id"] for m in missing]
    assert "mh-1" in missing_ids, (
        f"the uncovered must-haves must be named by index ID, got {missing_ids}"
    )


def test_pass_exits_0() -> None:
    result = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    assert result.returncode == 0, (
        f"pass fixture (0.8 >= 0.7) must exit 0, got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    content = json.loads(result.stdout)["gate_b"]["content"]
    assert content["verdict"] == "pass", f"verdict must be pass, got {content['verdict']}"


def test_structured_why_never_bare_number() -> None:
    result = _run_fit(FAIL_DRAFT, OFFER, FAIL_MAP)
    content = json.loads(result.stdout)["gate_b"]["content"]
    why = content["why"]
    assert isinstance(why, dict), f"why must be a structured object, got {type(why)}"
    assert isinstance(why.get("coverage"), str), (
        f"why.coverage must be a 'C/T' string, got {why.get('coverage')!r}"
    )
    assert isinstance(why.get("missing_must_haves"), list), (
        "why.missing_must_haves must be a list of structured entries"
    )
    assert "score" not in content, (
        "Gate B must not substitute a bare top-level 'score' for the structured why"
    )


def test_empty_must_haves_no_crash() -> None:
    empty_map = _write_tmp({})
    try:
        result = _run_fit(PASS_DRAFT, OFFER_EMPTY, empty_map)
        assert result.returncode == 0, (
            f"empty must_haves → score 1.0 → exit 0, got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        assert "Traceback" not in result.stderr, (
            f"empty must_haves must not divide-by-zero / traceback; stderr: {result.stderr}"
        )
        content = json.loads(result.stdout)["gate_b"]["content"]
        assert abs(content["coverage"]["score"] - 1.0) < 1e-9, (
            f"empty must_haves score must be 1.0, got {content['coverage']['score']}"
        )
        assert content["verdict"] == "pass"
    finally:
        empty_map.unlink(missing_ok=True)


def test_gate_c_never_blocks() -> None:
    # pass draft (coverage 0.8 >= 0.7) with a deliberately LOW-polish input:
    # poor polish must NEVER flip the coverage-derived exit.
    result = _run_fit(PASS_DRAFT, OFFER, PASS_MAP, polish=PASS_POLISH)
    assert result.returncode == 0, (
        f"low polish on a coverage-passing draft must still exit 0 (Gate C never blocks), "
        f"got {result.returncode}\nstderr: {result.stderr}"
    )
    out = json.loads(result.stdout)
    assert "gate_b" in out and "gate_c" in out, (
        "stdout must expose structurally-separate gate_b and gate_c keys"
    )
    gate_c = out["gate_c"]
    assert gate_c is not None, "gate_c must be present when --polish is supplied"
    c_content = gate_c["content"]
    assert c_content["gate"] == "C", f"gate_c content must be gate 'C', got {c_content['gate']}"
    assert c_content["advisory"] is True, "gate_c must be advisory:true"
    assert "verdict" not in c_content, (
        "Gate C must not carry a verdict — it is structurally separate from the Gate B block"
    )
    # The Gate B exit is unchanged by the poor polish.
    assert out["gate_b"]["content"]["verdict"] == "pass"


def test_gate_c_absent_is_null() -> None:
    result = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    out = json.loads(result.stdout)
    assert out["gate_c"] is None, (
        f"gate_c must be null when no --polish is supplied, got {out['gate_c']}"
    )


def test_out_of_range_index_not_covered() -> None:
    # mh-0 mapped to negative / out-of-range / non-int → NOT covering (bogus map must not
    # inflate coverage). mh-1 mapped to a valid in-range index → covering.
    bogus = _write_tmp(
        {
            "mh-0": [-1, 99, "3"],
            "mh-1": [1],
            "mh-2": [],
            "mh-3": [],
            "mh-4": [],
        }
    )
    try:
        result = _run_fit(PASS_DRAFT, OFFER, bogus)
        content = json.loads(result.stdout)["gate_b"]["content"]
        coverage = content["coverage"]
        assert "mh-0" in coverage["missing_ids"], (
            f"out-of-range/negative/non-int indices must not count mh-0 as covered, "
            f"got covered={coverage['covered_ids']}"
        )
        assert "mh-1" in coverage["covered_ids"], (
            f"a valid in-range index must still count mh-1 as covered, got {coverage}"
        )
    finally:
        bogus.unlink(missing_ok=True)


def test_no_escape_flag() -> None:
    source = SCORE_FIT.read_text(encoding="utf-8")
    for flag in ("--override", "--bypass", "--force"):
        assert flag not in source, (
            f"T-06-12 non-bypass: forbidden escape flag token {flag!r} must not appear in source"
        )
    for expected in ("--file", "--offer", "--coverage-map", "--thresholds"):
        assert expected in source, (
            f"score_fit.py must still expose its documented input {expected!r}"
        )


def test_emitted_gate_b_validates() -> None:
    result = _run_fit(PASS_DRAFT, OFFER, PASS_MAP)
    content = json.loads(result.stdout)["gate_b"]["content"]
    schema = json.loads(GATE_RESULT_SCHEMA.read_text(encoding="utf-8"))
    subschema = schema["$defs"]["gate_b_content"]
    registry = build_registry(SCHEMA_DIR)
    validator = Draft202012Validator(subschema, registry=registry)
    errors = [e.message for e in validator.iter_errors(content)]
    assert not errors, (
        f"emitted Gate B content must validate against gate_b_content; errors: {errors}"
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
