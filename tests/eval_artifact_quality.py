#!/usr/bin/env python3
"""Advisory scored-eval harness for artifact RICHNESS + TONE quality (REGRESSION-02, UAT).

This is a **reporting** harness, NOT a green-gated assertion suite. It is deliberately
named ``eval_artifact_quality.py`` (not ``test_*.py``) so the ``python3 tests/test_*.py``
regression loop never runs it as a blocking gate. It scores two artifact-quality dimensions
against the labeled set ``tests/fixtures/eval/expected.jsonl`` and PRINTS a human-readable
report — it never asserts a score and never fails the suite on a low score.

Why non-blocking: richness and tone are *quality* judgments, not deterministic pass/fail
unit tests. This is the Phase-14 ``artifact_richness_tone_eval`` deferral (STATE row DV-18),
converted to a scored eval per the locked design — advisory only, ALWAYS exit 0, never a
boolean CI gate. Mirrors the ``tests/eval_truth.py`` / ``tests/calibrate_fit.py`` contract:
this harness must NEVER ``assert score == ...`` and must NEVER fail on a low score.

Two scoring layers, split by the label ``category`` so they never overlap:

  (1) RICHNESS (``category == "deterministic"``): a REPORTED structural PROXY. For each
      richness row, load its ``fixture`` draft, count the number of DISTINCT
      ``content.claims[].section`` values, and report ``distinct_sections`` against the
      row's recorded ``threshold`` (``>= threshold`` => meets the human-reviewed richness
      bar). The threshold lives in the label DATA, never hardcoded here.

  (2) TONE (``category == "llm"``): score an OPTIONAL manual ``--verdicts`` JSON map
      (``"<fixture>::<label>" -> "pass"|"fail"``) against the tone row's expected label,
      exactly like ``eval_truth.score_eval``. ``accuracy = correct / total`` and is 0.0 when
      there are no tone rows (never a ZeroDivision).

Verdicts input: a JSON map ``"<fixture>::<label>" -> "pass"|"fail"`` produced by a manual
review of a live cover-letter tone judgment. Parsed claim text and verdicts are untrusted
DATA — scored, never executed as instructions (mirrors truth-rubric / fit-rubric stance).

CLI: ``eval_artifact_quality.py [--expected FILE] [--verdicts FILE]``
Exit 0 on ANY successful scoring run (any score); exit 1 ONLY when ``--expected`` or a
supplied ``--verdicts`` file is missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPECTED = REPO_ROOT / "tests" / "fixtures" / "eval" / "expected.jsonl"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def load_labels(expected_path: Path) -> list[dict]:
    """Load JSONL label rows; return all rows (category filtering happens per-layer)."""
    rows: list[dict] = []
    for line in expected_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _load_draft_claims(fixture_basename: str) -> list[dict]:
    """Resolve a bare fixture basename under tests/fixtures/ and return its content.claims.

    The claim text is untrusted DATA read for section counting; it is never executed.
    """
    draft_path = FIXTURES_DIR / fixture_basename
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"draft {fixture_basename!r} must parse to a JSON object")
    content = payload.get("content")
    if not isinstance(content, dict):
        raise ValueError(f"draft {fixture_basename!r} missing a 'content' object")
    claims = content.get("claims")
    if not isinstance(claims, list):
        raise ValueError(f"draft {fixture_basename!r} 'content.claims' must be a list")
    return claims


def score_richness(labels: list[dict]) -> list[dict]:
    """Score the deterministic richness rows: distinct section count vs recorded threshold.

    Returns one report dict per ``category == "deterministic"`` row with the observed
    ``distinct_sections``, the row's ``threshold``, and whether the bar is met. A REPORTED
    PROXY, never an assertion.
    """
    results: list[dict] = []
    for row in labels:
        if row.get("category") != "deterministic":
            continue
        claims = _load_draft_claims(row["fixture"])
        sections = {c.get("section") for c in claims if isinstance(c, dict) and c.get("section")}
        distinct = len(sections)
        threshold = row["threshold"]
        results.append(
            {
                "fixture": row["fixture"],
                "metric": row.get("metric", "distinct_sections"),
                "distinct_sections": distinct,
                "threshold": threshold,
                "expected_label": row.get("expected_label"),
                "meets_bar": distinct >= threshold,
                "sections": sorted(s for s in sections),
            }
        )
    return results


def score_tone(tone_verdicts: dict, labels: list[dict]) -> dict:
    """Score the manual tone verdicts over the LLM-category rows, mirroring eval_truth.score_eval.

    ``tone_verdicts`` maps ``(fixture, label)`` -> ``"pass"|"fail"`` where each judgment records
    whether the live cover-letter tone matched the expected register label. Only rows with
    ``category == "llm"`` are scored. ``accuracy`` is 0.0 when there are no tone rows (never a
    division error); ``mismatches`` lists rows without a passing verdict.
    """
    llm_rows = [row for row in labels if row.get("category") == "llm"]
    total = len(llm_rows)
    correct = 0
    mismatches: list[dict] = []
    for row in llm_rows:
        key = (row["fixture"], row["expected_label"])
        got = tone_verdicts.get(key)
        if got == "pass":
            correct += 1
        else:
            mismatches.append(
                {
                    "fixture": row["fixture"],
                    "expected_label": row["expected_label"],
                    "got": got,
                }
            )
    accuracy = (correct / total) if total else 0.0
    return {"total": total, "correct": correct, "accuracy": accuracy, "mismatches": mismatches}


def _parse_verdicts(verdicts_path: Path) -> dict:
    """Parse a ``"<fixture>::<label>" -> verdict`` JSON map into ``(fixture, label)`` keys."""
    raw = json.loads(verdicts_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("verdicts file must be a JSON object mapping '<fixture>::<label>' -> verdict")
    parsed: dict = {}
    for key, verdict in raw.items():
        if "::" not in key:
            raise ValueError(f"malformed verdict key {key!r}; expected '<fixture>::<label>'")
        fixture, _, label = key.rpartition("::")
        if verdict not in ("pass", "fail"):
            raise ValueError(f"verdict for {key!r} must be 'pass' or 'fail', got {verdict!r}")
        parsed[(fixture, label)] = verdict
    return parsed


def _report_richness(results: list[dict]) -> None:
    print("artifact richness (distinct-section proxy) (UAT, non-blocking)")
    if not results:
        print("  richness rows     : none")
        return
    for r in results:
        status = "meets bar" if r["meets_bar"] else "below bar"
        print(
            f"  {r['fixture']}: {r['metric']}={r['distinct_sections']} "
            f">= threshold {r['threshold']} -> {status} "
            f"(expected {r['expected_label']}); sections={r['sections']}"
        )


def _report_tone(result: dict) -> None:
    pct = result["accuracy"] * 100.0
    print("cover-letter tone accuracy (UAT, non-blocking)")
    print(f"  tone rows : {result['total']}")
    print(f"  correct   : {result['correct']}")
    print(f"  accuracy  : {result['accuracy']:.4f} ({pct:.1f}%)")
    if result["mismatches"]:
        print("  mismatches:")
        for m in result["mismatches"]:
            print(
                f"    - {m['fixture']} expected={m['expected_label']} got={m['got']}"
            )
    else:
        print("  mismatches: none")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advisory artifact richness/tone scored-eval report (REGRESSION-02, UAT)."
    )
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED,
                        help="path to the eval expected.jsonl label file")
    parser.add_argument("--verdicts", type=Path, default=None,
                        help="optional JSON map '<fixture>::<label>' -> 'pass'|'fail' for the "
                             "cover-letter tone accuracy UAT report")
    args = parser.parse_args()

    if not args.expected.is_file():
        print(f"error: --expected file not found: {args.expected}", file=sys.stderr)
        return 1

    try:
        labels = load_labels(args.expected)
        richness = score_richness(labels)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"error: malformed eval input: {exc}", file=sys.stderr)
        return 1

    _report_richness(richness)

    tone_verdicts: dict = {}
    if args.verdicts is not None:
        if not args.verdicts.is_file():
            print(f"error: --verdicts file not found: {args.verdicts}", file=sys.stderr)
            return 1
        try:
            tone_verdicts = _parse_verdicts(args.verdicts)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"error: malformed --verdicts file: {exc}", file=sys.stderr)
            return 1

    print()
    _report_tone(score_tone(tone_verdicts, labels))

    print("NOTE: reporting only — this harness never asserts richness/tone as a green gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
