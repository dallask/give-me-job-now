#!/usr/bin/env python3
"""Deterministic Gate-B (target-fit) scorer + ``gate_result`` emitter (FIT-01/02/03/05).

Proves offer-fit by *executed code*, never by an LLM self-report. The must-have coverage
is counted from an INPUT ``coverage_map`` (a CLI argument), never re-derived inside this
script — so given the same map + offer the output is byte-identical on every run (SC1,
threat T-06-18). For every offer must-have ``mh-N`` the scorer:

1. Reads its mapped claim-index list from ``--coverage-map`` and counts the must-have as
   covered iff that list holds >=1 integer index in range ``[0, n_claims)``. Bogus indices
   (non-int / negative / out-of-range) are silently treated as NOT covering, so a tampered
   map can never inflate coverage (threat T-06-13). ``count_coverage`` is a PURE function of
   its inputs — that purity IS the SC1 reproducibility proof.
2. Hard-blocks on a single calibrated ``coverage_threshold`` read from
   ``config/fit_thresholds.yaml`` via ``yaml.safe_load`` (threat T-06-17): coverage score
   ``>= threshold`` → ``pass`` (exit 0); below → ``fail`` (exit 1) with a structured
   ``why.missing_must_haves`` naming each uncovered ``{id, text}`` (FIT-02/03). The verdict
   is coverage-only; the thin deterministic secondary signals (keyword_alignment,
   language_match, seniority_scope_match) are REPORTED in ``why`` but NEVER gate.

The emitted Gate B content-doc is validated against
``gate_result.schema.json#/$defs/gate_b_content`` as a standalone root through a LOCAL-ONLY
registry (SSRF-safe). Malformed/oversized input degrades to structured stderr + exit 1 with
no traceback (threat T-06-16).

Gate C (polish) is OPTIONAL and STRUCTURALLY SEPARATE (FIT-05, threat T-06-14): when
``--polish`` is supplied the scorer attaches a ``{gate:"C", advisory:true, polish:{...}}``
envelope validated against ``$defs/gate_c_content``; it shares NO code with the verdict/exit
logic and can never set exit 1. When absent, the gate_c value is ``null``.

Non-bypass (threat T-06-12): the CLI exposes ONLY ``--file``/``--offer``/``--coverage-map``/
``--thresholds``/``--schema-dir``/``--polish``. There is deliberately NO override, bypass,
force, or mode argument — a below-threshold coverage exits 1 unconditionally; there is simply
no escape path (a unit test greps this source to prove the forbidden flag tokens are absent).

CLI: ``score_fit.py --file <draft.json> --offer <offer_spec.json> --coverage-map <map.json>
      [--thresholds config/fit_thresholds.yaml] [--schema-dir DIR] [--polish <polish.json>]``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/artifacts/ -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from validate_envelope import build_registry  # noqa: E402  reuse the local schema registry

DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"
DEFAULT_THRESHOLDS = REPO_ROOT / "config" / "fit_thresholds.yaml"
GATE_RESULT_SCHEMA = "gate_result.schema.json"

# Alphanumeric + a few tech-token chars (C++, C#, .NET, py3.10). Single chars dropped.
TOKEN = re.compile(r"[A-Za-z0-9+#.]+")


def assign_ids(must_haves: list) -> list[str]:
    """Stable index IDs — mh-0..mh-(N-1). Never LLM-assigned (SC1)."""
    return [f"mh-{i}" for i in range(len(must_haves))]


def count_coverage(must_haves: list, coverage_map: dict, n_claims: int) -> dict:
    """Count covered/total from the INPUT map — a PURE function of its inputs (SC1).

    A must-have is covered iff its mapped list holds >=1 integer claim_index in range
    ``[0, n_claims)``. Non-int / negative / out-of-range indices are rejected as NOT
    covering, so a bogus/tampered map can never inflate coverage (threat T-06-13).
    ``score = len(covered)/total`` (or 1.0 when there are no must-haves — nothing to miss,
    Pitfall 6 division-by-zero guard).
    """
    ids = assign_ids(must_haves)
    covered: list[str] = []
    missing: list[str] = []
    for mh_id in ids:
        mapped = coverage_map.get(mh_id, []) if isinstance(coverage_map, dict) else []
        if not isinstance(mapped, list):
            mapped = []
        valid = [
            c
            for c in mapped
            # bool is an int subclass — exclude it so True/False never counts as an index.
            if isinstance(c, int) and not isinstance(c, bool) and 0 <= c < n_claims
        ]
        (covered if valid else missing).append(mh_id)
    total = len(ids)
    score = (len(covered) / total) if total else 1.0
    return {"covered_ids": covered, "missing_ids": missing, "score": score}


def _tokens(text: str) -> set[str]:
    """Lowercased keyword tokens of length > 1 (deterministic)."""
    return {t.lower() for t in TOKEN.findall(text) if len(t) > 1}


def keyword_alignment(must_haves: list, claims: list) -> float:
    """Fraction of must-have keyword tokens that appear across the draft claim texts.

    Advisory only — reported in ``why``, never part of the hard-block.
    """
    mh_texts = [m for m in must_haves if isinstance(m, str)]
    mh_tokens: set[str] = set().union(*(_tokens(m) for m in mh_texts)) if mh_texts else set()
    claim_texts = [
        c.get("text", "") for c in claims if isinstance(c, dict) and isinstance(c.get("text"), str)
    ]
    draft_tokens: set[str] = (
        set().union(*(_tokens(t) for t in claim_texts)) if claim_texts else set()
    )
    return (len(mh_tokens & draft_tokens) / len(mh_tokens)) if mh_tokens else 1.0


def language_match(offer_content: dict, draft_content: dict) -> bool:
    """Advisory: offer content language == draft content language."""
    return offer_content.get("language") == draft_content.get("language")


def seniority_scope_match(offer_content: dict, claims: list) -> bool:
    """Advisory (thin): offer seniority token present in any claim text."""
    sen = (offer_content.get("seniority") or "").lower()
    if not sen:
        return False
    return any(
        isinstance(c, dict) and sen in str(c.get("text", "")).lower() for c in claims
    )


def build_gate_b_result(
    coverage: dict, sub: dict, offer_must_haves: list, threshold: float
) -> dict:
    """Aggregate the coverage count + advisory sub-scores into a Gate-B envelope.

    Verdict is coverage-only: ``pass`` iff ``coverage.score >= threshold`` (a binary
    hard-block). ``why.missing_must_haves`` names each uncovered ``{id, text}`` so the gate
    gives structured feedback, never a bare number (FIT-03). The secondary sub-scores are
    reported for context but never gate.
    """
    verdict = "pass" if coverage["score"] >= threshold else "fail"
    missing = [
        {"id": mid, "text": offer_must_haves[int(mid.split("-")[1])]}
        for mid in coverage["missing_ids"]
    ]
    content = {
        "gate": "B",
        "verdict": verdict,
        "coverage": coverage,
        "keyword_alignment": sub["keyword_alignment"],
        "language_match": sub["language_match"],
        "seniority_scope_match": sub["seniority_scope_match"],
        "why": {
            "coverage": f"{len(coverage['covered_ids'])}/{len(offer_must_haves)}",
            "missing_must_haves": missing,
            "keyword_alignment": sub["keyword_alignment"],
            "language_match": sub["language_match"],
            "seniority_scope_match": sub["seniority_scope_match"],
        },
    }
    return {"schema_version": "1.0", "kind": "gate_result", "content": content}


def build_gate_c_result(polish: dict) -> dict:
    """Build the STRUCTURALLY-SEPARATE advisory Gate-C envelope (FIT-05).

    Shares no code with the verdict/exit path; carries ``advisory:true`` and never a
    verdict, so it can never influence the Gate B exit code.
    """
    content = {"gate": "C", "advisory": True, "polish": polish}
    return {"schema_version": "1.0", "kind": "gate_result", "content": content}


def _validate_content(content: dict, def_name: str, schema_dir: Path) -> list[str]:
    """Validate ``content`` against gate_result#/$defs/<def_name> (local-only registry).

    The sub-schema validates as a standalone root through the absolute-URN item refs. A
    non-empty return means the gate produced a malformed doc — an internal error, surfaced
    to stderr + exit 1 by the caller.
    """
    schema = json.loads((schema_dir / GATE_RESULT_SCHEMA).read_text(encoding="utf-8"))
    subschema = schema["$defs"][def_name]
    registry = build_registry(schema_dir)
    validator = Draft202012Validator(subschema, registry=registry)
    return [
        f"schema: {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(content), key=lambda e: list(e.path))
    ]


def _load_json_object(path: Path, label: str) -> dict | None:
    """Read a JSON object from *path* or print a structured error and return None."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        print(f"Not a file: {resolved}", file=sys.stderr)
        return None
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {label}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print(f"{label} must be a JSON object.", file=sys.stderr)
        return None
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic Gate-B scorer: count must-have coverage from an input "
        "map + emit a coverage-gated gate_result. Below threshold exits 1 (no bypass flag)."
    )
    parser.add_argument(
        "--file", type=Path, required=True, help="Draft JSON content-doc to score."
    )
    parser.add_argument(
        "--offer", type=Path, required=True, help="Frozen offer_spec envelope (reads content)."
    )
    parser.add_argument(
        "--coverage-map",
        type=Path,
        required=True,
        help="JSON map of mh-N -> [claim_index, ...]; a CLI INPUT, never re-derived (SC1).",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=DEFAULT_THRESHOLDS,
        help="Calibrated thresholds YAML (defaults to config/fit_thresholds.yaml).",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="Directory of *.schema.json files (defaults to the repo schemas/ dir).",
    )
    parser.add_argument(
        "--polish",
        type=Path,
        default=None,
        help="Optional agent-authored Gate C polish JSON (five 0-5 dims). Advisory only.",
    )
    args = parser.parse_args()

    draft = _load_json_object(args.file, "draft")
    if draft is None:
        return 1
    if "content" not in draft or not isinstance(draft["content"], dict):
        print("Malformed draft: missing object 'content'.", file=sys.stderr)
        return 1
    draft_content = draft["content"]

    offer = _load_json_object(args.offer, "offer")
    if offer is None:
        return 1
    if "content" not in offer or not isinstance(offer["content"], dict):
        print("Malformed offer: missing object 'content'.", file=sys.stderr)
        return 1
    offer_content = offer["content"]
    must_haves = offer_content.get("must_haves", [])
    if not isinstance(must_haves, list):
        print("Malformed offer: 'content.must_haves' must be an array.", file=sys.stderr)
        return 1

    coverage_map = _load_json_object(args.coverage_map, "coverage-map")
    if coverage_map is None:
        return 1

    thresholds_path = args.thresholds.expanduser().resolve()
    if not thresholds_path.is_file():
        print(f"Not a file: {thresholds_path}", file=sys.stderr)
        return 1
    cfg = yaml.safe_load(thresholds_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        print("Thresholds YAML must parse to a JSON object.", file=sys.stderr)
        return 1
    threshold = cfg.get("coverage_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        print("Thresholds YAML: 'coverage_threshold' must be a number.", file=sys.stderr)
        return 1

    claims = draft_content.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    n_claims = len(claims)

    coverage = count_coverage(must_haves, coverage_map, n_claims)
    sub = {
        "keyword_alignment": keyword_alignment(must_haves, claims),
        "language_match": language_match(offer_content, draft_content),
        "seniority_scope_match": seniority_scope_match(offer_content, claims),
    }
    gate_b = build_gate_b_result(coverage, sub, must_haves, float(threshold))

    schema_dir = args.schema_dir.expanduser().resolve()
    b_errors = _validate_content(gate_b["content"], "gate_b_content", schema_dir)
    if b_errors:
        print("Internal error: emitted Gate B gate_result is not schema-valid:", file=sys.stderr)
        for error in b_errors:
            print(error, file=sys.stderr)
        return 1

    # Gate C — structurally separate, advisory, shares NO code with the verdict/exit above.
    gate_c = None
    if args.polish is not None:
        polish = _load_json_object(args.polish, "polish")
        if polish is None:
            return 1
        gate_c = build_gate_c_result(polish)
        c_errors = _validate_content(gate_c["content"], "gate_c_content", schema_dir)
        if c_errors:
            print("Internal error: emitted Gate C gate_result is not schema-valid:", file=sys.stderr)
            for error in c_errors:
                print(error, file=sys.stderr)
            return 1

    print(json.dumps({"gate_b": gate_b, "gate_c": gate_c}, indent=2, ensure_ascii=False))
    # Exit is derived SOLELY from Gate B coverage — never from Gate C or the sub-scores.
    return 0 if gate_b["content"]["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
