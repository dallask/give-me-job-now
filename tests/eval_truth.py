#!/usr/bin/env python3
"""Scored-eval harness for the gmj-truth-verifier's LLM 4-rule accuracy (TRUTH-04, UAT).

This is a **reporting** harness, NOT a green-gated assertion suite. It is deliberately
named ``eval_truth.py`` (not ``test_*.py``) so the ``python3 tests/test_*.py`` regression
loop never runs it as a blocking gate. It computes, over the **LLM-category** labels in
``tests/fixtures/truth/expected.jsonl``, how often the gmj-truth-verifier agent's per-claim
verdict matches the expected verdict, and PRINTS a human-readable report.

Why non-blocking: the R1-R4 reframe/fabrication boundary is an agent-in-loop judgment, so
its accuracy cannot be a deterministic unit test. It is the TRUTH-04 "wired live"
precondition — Gate A is trusted live only once the adversarial set scores correctly. This
harness must NEVER ``assert accuracy == 1.0`` and must NEVER fail the suite on low accuracy;
it only reports. The human-verify checkpoint records the accuracy as the explicit precondition.

The deterministic span/numeric category (``category == "deterministic"``) is already covered
by ``tests/test_check_truth.py`` (blocking-green, Plan 05-04); this harness scores ONLY the
``category == "llm"`` rows so the two layers never overlap.

Verdicts input: a JSON map ``"<fixture>::<claim_index>" -> "pass"|"fail"`` produced by a
manual gmj-truth-verifier run over ``tests/fixtures/truth/*.draft.json``.

CLI: ``eval_truth.py [--expected FILE] --verdicts FILE``
Exit 0 on a successful scoring run (any accuracy); exit 1 only when ``--verdicts`` is
missing or malformed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPECTED = REPO_ROOT / "tests" / "fixtures" / "truth" / "expected.jsonl"


def load_labels(expected_path: Path) -> list[dict]:
    """Load JSONL label rows; return all rows (category filtering happens in score_eval)."""
    rows: list[dict] = []
    for line in expected_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def score_eval(agent_verdicts: dict, labels: list[dict]) -> dict:
    """Score the agent's per-claim verdicts over the LLM-category labels.

    ``agent_verdicts`` maps ``(fixture, claim_index)`` -> ``"pass"|"fail"``.
    Only rows with ``category == "llm"`` are scored. Returns
    ``{"total", "correct", "accuracy", "mismatches"}`` where ``accuracy`` is 0.0 when there
    are no LLM rows (never a division error), and ``mismatches`` lists the misjudged rows.
    """
    llm_rows = [row for row in labels if row.get("category") == "llm"]
    total = len(llm_rows)
    correct = 0
    mismatches: list[dict] = []
    for row in llm_rows:
        key = (row["fixture"], row["claim_index"])
        got = agent_verdicts.get(key)
        expected = row["expected_verdict"]
        if got == expected:
            correct += 1
        else:
            mismatches.append(
                {
                    "fixture": row["fixture"],
                    "claim_index": row["claim_index"],
                    "expected": expected,
                    "got": got,
                    "rule": row.get("rule"),
                }
            )
    accuracy = (correct / total) if total else 0.0
    return {"total": total, "correct": correct, "accuracy": accuracy, "mismatches": mismatches}


def _parse_verdicts(verdicts_path: Path) -> dict:
    """Parse a ``"<fixture>::<claim_index>" -> verdict`` JSON map into ``(fixture, idx)`` keys."""
    raw = json.loads(verdicts_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("verdicts file must be a JSON object mapping '<fixture>::<index>' -> verdict")
    parsed: dict = {}
    for key, verdict in raw.items():
        if "::" not in key:
            raise ValueError(f"malformed verdict key {key!r}; expected '<fixture>::<claim_index>'")
        fixture, _, idx = key.rpartition("::")
        try:
            claim_index = int(idx)
        except ValueError as exc:
            raise ValueError(f"claim_index in key {key!r} is not an integer") from exc
        if verdict not in ("pass", "fail"):
            raise ValueError(f"verdict for {key!r} must be 'pass' or 'fail', got {verdict!r}")
        parsed[(fixture, claim_index)] = verdict
    return parsed


def _report(result: dict) -> None:
    pct = result["accuracy"] * 100.0
    print("gmj-truth-verifier LLM 4-rule accuracy (UAT, non-blocking)")
    print(f"  LLM-category rows : {result['total']}")
    print(f"  correct           : {result['correct']}")
    print(f"  accuracy          : {result['accuracy']:.4f} ({pct:.1f}%)")
    if result["mismatches"]:
        print("  mismatches:")
        for m in result["mismatches"]:
            print(
                f"    - {m['fixture']} [claim {m['claim_index']}] "
                f"expected={m['expected']} got={m['got']} rule={m['rule']}"
            )
    else:
        print("  mismatches        : none")
    print("NOTE: reporting only — this harness never asserts accuracy as a green gate.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Score gmj-truth-verifier LLM 4-rule accuracy (UAT).")
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED,
                        help="path to expected.jsonl label file")
    parser.add_argument("--verdicts", type=Path, required=True,
                        help="JSON map '<fixture>::<claim_index>' -> 'pass'|'fail'")
    args = parser.parse_args()

    if not args.verdicts.is_file():
        print(f"error: --verdicts file not found: {args.verdicts}", file=sys.stderr)
        return 1
    try:
        agent_verdicts = _parse_verdicts(args.verdicts)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: malformed --verdicts file: {exc}", file=sys.stderr)
        return 1

    labels = load_labels(args.expected)
    result = score_eval(agent_verdicts, labels)
    _report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
