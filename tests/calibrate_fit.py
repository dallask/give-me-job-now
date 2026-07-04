#!/usr/bin/env python3
"""Non-blocking Gate-B threshold-derivation report (FIT-04, UAT).

This is a **reporting** harness, NOT a green-gated assertion suite. It is deliberately
named ``calibrate_fit.py`` (not ``test_*.py``) so the ``python3 tests/test_*.py`` regression
loop never runs it as a blocking gate. It runs ``scripts/artifacts/gmj_score_fit.py`` over the
labeled Gate-B calibration fixtures in ``tests/fixtures/fit/expected.jsonl``, tabulates each
fixture's deterministic coverage score + emitted verdict against its expected label, and
PRINTS whether the config ``coverage_threshold`` cleanly separates the labeled-pass fixtures
from the labeled-fail / borderline fixtures — the reproducible derivation evidence behind the
``coverage_threshold`` documented in the fit-rubric (FIT-04).

Why non-blocking: the threshold is a calibrated choice justified BY this separation report,
not by a deterministic pass/fail unit test. Mirrors the Phase-5 ``eval_truth.py`` contract:
this harness must NEVER ``assert accuracy == 1.0``, NEVER fail the suite on a non-separating
threshold or low accuracy — it only reports. The human reads the derivation and confirms the
``coverage_threshold`` in the human-verify checkpoint.

The deterministic coverage rows are computed by actually running ``gmj_score_fit.py`` (the same
scorer Gate B uses live), so the separation report reflects real scorer behavior, not a
re-implementation. The OPTIONAL LLM coverage_map / polish accuracy is scored from a manual
``--verdicts`` input (UAT), mirroring ``eval_truth.py``'s ``score_eval``.

Verdicts input: a JSON map ``"<fixture>::<mh_id>" | "<fixture>::<claim_index>" -> "pass"|"fail"``
produced by a manual review of a live gmj-fit-evaluator coverage_map / Gate-C polish run.

CLI: ``calibrate_fit.py [--expected FILE] [--thresholds FILE] [--verdicts FILE]``
Exit 0 on any successful reporting run (clean separation or not); exit 1 ONLY when a
required input file is missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "fit"
DEFAULT_EXPECTED = FIXTURES_DIR / "expected.jsonl"
DEFAULT_THRESHOLDS = REPO_ROOT / "config" / "fit_thresholds.yaml"
SCORE_FIT = REPO_ROOT / "scripts" / "artifacts" / "gmj_score_fit.py"


def load_labels(expected_path: Path) -> list[dict]:
    """Load JSONL label rows; return all rows (category filtering happens per-report)."""
    rows: list[dict] = []
    for line in expected_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_threshold(thresholds_path: Path) -> float:
    """Load the calibrated ``coverage_threshold`` via ``yaml.safe_load`` with a type guard."""
    cfg = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError("thresholds YAML must parse to a JSON object")
    threshold = cfg.get("coverage_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError("'coverage_threshold' must be a number")
    return float(threshold)


def run_score_fit(row: dict, thresholds_path: Path, empty_map_path: Path) -> dict:
    """Run ``gmj_score_fit.py`` for one fixture row; return the observed coverage score + verdict.

    ``gmj_score_fit.py`` exits 1 on a labeled-fail verdict — that is EXPECTED, not an error, so we
    parse its stdout JSON regardless of exit code. Only a genuinely malformed run (no parseable
    JSON on stdout) is an error, surfaced by the caller as a missing/malformed-input exit 1.
    """
    draft = FIXTURES_DIR / row["fixture"]
    offer = FIXTURES_DIR / row["offer"]
    coverage_map = row.get("coverage_map")
    # A null coverage_map (empty-must-haves offer) still needs a file argument; the scorer never
    # reads it when there are zero must-haves, so an empty ``{}`` map is a faithful stand-in.
    cmap_path = FIXTURES_DIR / coverage_map if coverage_map else empty_map_path

    proc = subprocess.run(
        [
            sys.executable,
            str(SCORE_FIT),
            "--file",
            str(draft),
            "--offer",
            str(offer),
            "--coverage-map",
            str(cmap_path),
            "--thresholds",
            str(thresholds_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(proc.stdout)
        content = payload["gate_b"]["content"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(
            f"gmj_score_fit.py produced no parseable Gate-B output for {row['fixture']!r} "
            f"(rc={proc.returncode}): {exc}\nstderr: {proc.stderr.strip()}"
        ) from exc
    return {
        "score": content["coverage"]["score"],
        "verdict": content["verdict"],
        "coverage_str": content["why"]["coverage"],
    }


def build_rows(labels: list[dict], threshold: float, thresholds_path: Path) -> list[dict]:
    """Score every fixture row and pair the observed result with its expected label."""
    results: list[dict] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        tmp.write("{}")
        empty_map_path = Path(tmp.name)
    try:
        for row in labels:
            observed = run_score_fit(row, thresholds_path, empty_map_path)
            observed_side = "pass" if observed["score"] >= threshold else "fail"
            results.append(
                {
                    "fixture": row["fixture"],
                    "category": row.get("category"),
                    "expected_coverage": row.get("expected_coverage"),
                    "observed_coverage": observed["coverage_str"],
                    "expected_verdict": row["expected_verdict"],
                    "observed_verdict": observed["verdict"],
                    "score": observed["score"],
                    # Which side of the threshold the score lands — should equal expected_verdict.
                    "threshold_side": observed_side,
                }
            )
    finally:
        empty_map_path.unlink(missing_ok=True)
    return results


def separation(results: list[dict], threshold: float) -> dict:
    """Compute the highest labeled-fail score, lowest labeled-pass score, and clean-separation.

    A ``coverage_threshold`` is a CLEAN separator iff every labeled-fail score is strictly below
    it and every labeled-pass score is at or above it: ``highest_fail < threshold <= lowest_pass``.
    """
    pass_scores = [r["score"] for r in results if r["expected_verdict"] == "pass"]
    fail_scores = [r["score"] for r in results if r["expected_verdict"] == "fail"]
    highest_fail = max(fail_scores) if fail_scores else None
    lowest_pass = min(pass_scores) if pass_scores else None
    clean = (
        (highest_fail is None or highest_fail < threshold)
        and (lowest_pass is None or lowest_pass >= threshold)
    )
    return {"highest_fail": highest_fail, "lowest_pass": lowest_pass, "clean": clean}


def score_verdicts(verdicts: dict) -> dict:
    """Score a manual LLM coverage_map / polish judgement map (UAT), mirroring eval_truth.

    ``verdicts`` maps ``(fixture, item)`` -> ``"pass"|"fail"`` where each judgement records
    whether the live gmj-fit-evaluator's coverage_map entry / Gate-C polish dimension was correct.
    Returns ``{"total", "correct", "accuracy", "mismatches"}``; accuracy is 0.0 for an empty map
    (never a division error). Reporting only — never a gate.
    """
    total = len(verdicts)
    correct = sum(1 for v in verdicts.values() if v == "pass")
    mismatches = [
        {"fixture": fixture, "item": item}
        for (fixture, item), v in verdicts.items()
        if v != "pass"
    ]
    accuracy = (correct / total) if total else 0.0
    return {"total": total, "correct": correct, "accuracy": accuracy, "mismatches": mismatches}


def _parse_verdicts(verdicts_path: Path) -> dict:
    """Parse a ``"<fixture>::<item>" -> verdict`` JSON map into ``(fixture, item)`` keys."""
    raw = json.loads(verdicts_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("verdicts file must be a JSON object mapping '<fixture>::<item>' -> verdict")
    parsed: dict = {}
    for key, verdict in raw.items():
        if "::" not in key:
            raise ValueError(f"malformed verdict key {key!r}; expected '<fixture>::<item>'")
        fixture, _, item = key.rpartition("::")
        if verdict not in ("pass", "fail"):
            raise ValueError(f"verdict for {key!r} must be 'pass' or 'fail', got {verdict!r}")
        parsed[(fixture, item)] = verdict
    return parsed


def _report_separation(results: list[dict], sep: dict, threshold: float) -> None:
    print("Gate-B coverage_threshold derivation (FIT-04, non-blocking)")
    print(f"  coverage_threshold : {threshold}")
    print("  per-fixture coverage / verdict:")
    print(
        f"    {'fixture':<34} {'cat':<13} "
        f"{'exp_cov':>8} {'obs_cov':>8} {'score':>6} "
        f"{'exp_verdict':>12} {'obs_verdict':>12} {'side_ok':>8}"
    )
    for r in results:
        verdict_ok = r["observed_verdict"] == r["expected_verdict"]
        side_ok = r["threshold_side"] == r["expected_verdict"]
        flag = "ok" if (verdict_ok and side_ok) else "MISMATCH"
        print(
            f"    {r['fixture']:<34} {str(r['category']):<13} "
            f"{str(r['expected_coverage']):>8} {str(r['observed_coverage']):>8} "
            f"{r['score']:>6.2f} {r['expected_verdict']:>12} {r['observed_verdict']:>12} "
            f"{flag:>8}"
        )
    hf = sep["highest_fail"]
    lp = sep["lowest_pass"]
    hf_str = f"{hf:.2f}" if hf is not None else "n/a"
    lp_str = f"{lp:.2f}" if lp is not None else "n/a"
    print(f"  highest labeled-fail score : {hf_str}")
    print(f"  lowest  labeled-pass score : {lp_str}")
    if sep["clean"]:
        print(
            f"  SEPARATION: CLEAN — highest-fail {hf_str} < threshold {threshold} "
            f"<= lowest-pass {lp_str}; the threshold cleanly separates pass from fail/borderline."
        )
    else:
        print(
            f"  SEPARATION: NOT CLEAN — threshold {threshold} does not sit strictly between "
            f"highest-fail {hf_str} and lowest-pass {lp_str}; revisit the coverage_threshold."
        )


def _report_verdicts(result: dict) -> None:
    pct = result["accuracy"] * 100.0
    print("LLM coverage_map / polish accuracy (UAT, non-blocking)")
    print(f"  judged items : {result['total']}")
    print(f"  correct      : {result['correct']}")
    print(f"  accuracy     : {result['accuracy']:.4f} ({pct:.1f}%)")
    if result["mismatches"]:
        print("  mismatches:")
        for m in result["mismatches"]:
            print(f"    - {m['fixture']} :: {m['item']}")
    else:
        print("  mismatches   : none")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Non-blocking Gate-B coverage_threshold derivation report (FIT-04, UAT)."
    )
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED,
                        help="path to the fit expected.jsonl label file")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS,
                        help="calibrated thresholds YAML (defaults to config/fit_thresholds.yaml)")
    parser.add_argument("--verdicts", type=Path, default=None,
                        help="optional JSON map '<fixture>::<item>' -> 'pass'|'fail' for the "
                             "LLM coverage_map / polish accuracy UAT report")
    args = parser.parse_args()

    if not args.expected.is_file():
        print(f"error: --expected file not found: {args.expected}", file=sys.stderr)
        return 1
    if not args.thresholds.is_file():
        print(f"error: --thresholds file not found: {args.thresholds}", file=sys.stderr)
        return 1
    if not SCORE_FIT.is_file():
        print(f"error: gmj_score_fit.py not found: {SCORE_FIT}", file=sys.stderr)
        return 1

    try:
        labels = load_labels(args.expected)
        threshold = load_threshold(args.thresholds)
        results = build_rows(labels, threshold, args.thresholds)
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: malformed calibration input: {exc}", file=sys.stderr)
        return 1

    sep = separation(results, threshold)
    _report_separation(results, sep, threshold)

    if args.verdicts is not None:
        if not args.verdicts.is_file():
            print(f"error: --verdicts file not found: {args.verdicts}", file=sys.stderr)
            return 1
        try:
            verdicts = _parse_verdicts(args.verdicts)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"error: malformed --verdicts file: {exc}", file=sys.stderr)
            return 1
        print()
        _report_verdicts(score_verdicts(verdicts))

    print("NOTE: reporting only — this harness never asserts separation/accuracy as a green gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
