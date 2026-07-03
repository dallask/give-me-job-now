#!/usr/bin/env python3
"""Deterministic Gate-A pre-gate + ``gate_result`` emitter (TRUTH-01/03/04).

Proves provenance by *executed code*, never by an LLM self-report (threat T-05-11).
For every ``claim`` in a stored ``<type>.draft.json`` content-doc this CLI produces a
PER-CLAIM verdict (never a whole-document similarity score) by:

1. Resolving ``claim.source_span`` into ``candidate.yaml`` via the ONE shared
   ``yaml_path.resolve_path`` walker. A fabricated/out-of-range/empty span raises and
   becomes an automatic FAIL naming the offending ``claim_index`` + span
   (``rule_violated="unresolved_span"``, TRUTH-01/03). No second span regex exists.
2. Applying a thin numeric-invention heuristic (deterministic augment): a numeric token
   in ``claim.text`` whose digit-core is absent from the resolved span FAILs the claim
   (``rule_violated="numeric_invention"``, TRUTH-04). Word-fraction reframes ("a third")
   carry no digit token, so they never trip it. The LLM 4-rule layer (Plan 05-05) is the
   R3 semantic backstop for cases this heuristic cannot see; the deterministic layer
   marks the remaining resolved claims ``pass`` (it cannot judge scope/merge semantics).

The emitted content-doc ``{gate:"A", verdict, offending_claims:[...]}`` is validated
against ``gate_result.schema.json#/$defs/gate_a_content`` as a standalone root through a
LOCAL-ONLY registry (threat T-05-13). Malformed/oversized input degrades to structured
stderr + exit 1 with no traceback (threat T-05-12).

TRUTH-03 non-bypass (threat T-05-09): the CLI exposes ONLY ``--file``/``--candidate``/
``--schema-dir``. There is deliberately NO override, bypass, force, or mode argument — any
FAIL claim makes the artifact verdict FAIL and exits 1 unconditionally in every mode; a
clean draft exits 0. There is simply no escape path (a unit test greps this source to
prove the forbidden flag tokens are absent).

CLI: ``check_truth.py --file <draft.json> --candidate <candidate.yaml> [--schema-dir DIR]``
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

sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from yaml_path import resolve_path  # noqa: E402  promoted shared source-span resolver

DEFAULT_SCHEMA_DIR = REPO_ROOT / "schemas"
GATE_RESULT_SCHEMA = "gate_result.schema.json"

# Integer / decimal / percentage tokens (e.g. "12", "3.5", "30%", "95" in "p95").
# The digit-core (trailing '%' stripped) is what must be present in the resolved span.
NUMERIC_TOKEN = re.compile(r"\d+(?:\.\d+)?%?")


def _numeric_invention(text: str, resolved: object) -> bool:
    """Return True when a numeric token in *text* is absent from the resolved span.

    Thin deterministic augment (kept thin on purpose): stringify the resolved span and
    check each digit-core for literal presence. A word-fraction reframe such as "a third"
    yields no digit token, so it never trips (proven by the good.numeric_reframe fixture).
    Semantic numeric cases the heuristic cannot see remain the LLM R3 backstop (Plan 05-05).
    """
    span_str = str(resolved)
    for token in NUMERIC_TOKEN.findall(text):
        core = token.rstrip("%")
        if core and core not in span_str:
            return True
    return False


def verify_claims(content: dict, candidate: dict) -> list[dict]:
    """Produce a PER-CLAIM verdict list (never a whole-document score).

    Each verdict is ``{claim_index, verdict, offending_span[, rule_violated]}``. An
    unresolvable or empty span FAILs as ``unresolved_span`` (the resolver raises on the
    empty span for free); a resolved span with an invented number FAILs as
    ``numeric_invention``; otherwise the deterministic layer marks the claim ``pass``.
    """
    verdicts: list[dict] = []
    for i, claim in enumerate(content.get("claims", [])):
        is_dict = isinstance(claim, dict)
        span = claim.get("source_span", "") if is_dict else ""
        text = claim.get("text", "") if is_dict else ""
        if not isinstance(span, str):
            span = ""
        try:
            resolved = resolve_path(candidate, span)
        except (KeyError, IndexError, TypeError):
            verdicts.append(
                {
                    "claim_index": i,
                    "verdict": "fail",
                    "rule_violated": "unresolved_span",
                    "offending_span": span,
                }
            )
            continue
        if isinstance(text, str) and _numeric_invention(text, resolved):
            verdicts.append(
                {
                    "claim_index": i,
                    "verdict": "fail",
                    "rule_violated": "numeric_invention",
                    "offending_span": span,
                }
            )
            continue
        verdicts.append({"claim_index": i, "verdict": "pass", "offending_span": span})
    return verdicts


def build_gate_a_result(verdicts: list[dict]) -> dict:
    """Aggregate per-claim verdicts into a Gate-A ``gate_result`` content-doc envelope.

    Any FAIL claim makes the artifact verdict FAIL (binary hard-block). ``offending_claims``
    names each failing claim_index + rule + span so the gate "names offending lines"
    (TRUTH-03); it is empty on a clean draft.
    """
    offending = [
        {
            "claim_index": v["claim_index"],
            "rule_violated": v["rule_violated"],
            "offending_span": v["offending_span"],
        }
        for v in verdicts
        if v["verdict"] == "fail"
    ]
    content = {
        "gate": "A",
        "verdict": "fail" if offending else "pass",
        "offending_claims": offending,
    }
    return {"schema_version": "1.0", "kind": "gate_result", "content": content}


def validate_gate_a(content: dict, schema_dir: Path) -> list[str]:
    """Validate the emitted ``content`` against gate_result#/$defs/gate_a_content.

    Uses the local-only registry (threat T-05-13); the sub-schema validates as a
    standalone root. A non-empty return means the gate produced a malformed doc —
    an internal error, surfaced to stderr + exit 1 by the caller.
    """
    schema = json.loads((schema_dir / GATE_RESULT_SCHEMA).read_text(encoding="utf-8"))
    subschema = schema["$defs"]["gate_a_content"]
    registry = build_registry(schema_dir)
    validator = Draft202012Validator(subschema, registry=registry)
    return [
        f"schema: {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(content), key=lambda e: list(e.path))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic Gate-A pre-gate: resolve every claim source_span + "
        "emit a per-claim gate_result. Any FAIL exits 1 (no bypass flag exists)."
    )
    parser.add_argument(
        "--file", type=Path, required=True, help="Draft JSON content-doc to check."
    )
    parser.add_argument(
        "--candidate", type=Path, required=True, help="candidate.yaml the spans resolve into."
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help="Directory of *.schema.json files (defaults to the repo schemas/ dir).",
    )
    args = parser.parse_args()

    draft_path = args.file.expanduser().resolve()
    if not draft_path.is_file():
        print(f"Not a file: {draft_path}", file=sys.stderr)
        return 1
    candidate_path = args.candidate.expanduser().resolve()
    if not candidate_path.is_file():
        print(f"Not a file: {candidate_path}", file=sys.stderr)
        return 1

    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(draft, dict):
        print("Draft must be a JSON object.", file=sys.stderr)
        return 1
    if "content" not in draft:
        print("Malformed draft: missing 'content'.", file=sys.stderr)
        return 1
    content = draft["content"]
    if not isinstance(content, dict):
        print("Malformed draft: 'content' must be a JSON object.", file=sys.stderr)
        return 1

    candidate = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict):
        print("Candidate YAML must parse to a JSON object.", file=sys.stderr)
        return 1

    schema_dir = args.schema_dir.expanduser().resolve()
    verdicts = verify_claims(content, candidate)
    result = build_gate_a_result(verdicts)

    schema_errors = validate_gate_a(result["content"], schema_dir)
    if schema_errors:
        print("Internal error: emitted gate_result is not schema-valid:", file=sys.stderr)
        for error in schema_errors:
            print(error, file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["content"]["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
