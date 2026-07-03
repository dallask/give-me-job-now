#!/usr/bin/env python3
"""Record a gate's verdict as BOTH an audit artifact and routing state (GUARD-03).

One script does two jobs so the audit log and the routing state can never disagree
(Pattern 5, threat T-07-09):

  Job 1 (artifact): write the emitted ``gate_result`` envelope verbatim to
    ``<run-dir>/gate_<node>_<artifact-type>_<attempt>.json`` — the written file IS the
    GUARD-03 audit record, not an agent claim.
  Job 2 (state): set ``state.gate_results[<node>] = "pass"|"fail"`` so route.py can branch
    (Wiring Fact 1 — route.py RAISES on a gate node with no recorded verdict). Existing
    sibling keys (``current_step``, ``retry_counts``, ``offer_spec_hash`` …) are preserved
    on update via the read-modify-preserve body cloned from ``record_retry.py``.

Normalization (Wiring Fact 2, threat T-07-10): score_fit.py emits a ``{gate_b, gate_c}``
wrapper. When the result stdout has a top-level ``gate_b`` key it is unwrapped to
``payload["gate_b"]`` before recording, so the audit log, map_feedback.py, and the delivery
check all see a uniform gate_result envelope. Gate C is advisory (FIT-05): it is stored
separately (a sibling ``gate_c_<...>.json``) and NEVER enters ``gate_results`` or the verdict.

Security: each path component (run-dir basename, node, artifact-type, attempt) is sanitized
to ``^[A-Za-z0-9._-]+$`` with ``.`` / ``..`` rejected before the join (V12, threat T-07-08).
Malformed gate stdout (invalid JSON / missing ``content.verdict``) degrades to structured
stderr + exit 1 with no traceback (threat T-07-11).

CLI: ``record_gate.py --state <path> --node <truth-verifier|fit-evaluator>
      --result <gate-stdout.json | -> --run-dir <.pipeline/runs/<run_id>>
      --artifact-type <cv|cover_letter|interview_prep> --attempt <int>``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Gate DAG node names — MUST match the gate nodes in config/pipeline.dag.yaml exactly,
# because route.py reads state.gate_results[<this node>].
GATE_NODES = ["truth-verifier", "fit-evaluator"]
ARTIFACT_TYPES = ["cv", "cover_letter", "interview_prep"]

# Safe filesystem path component: alphanumerics plus . _ - only (V12, threat T-07-08).
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_component(value: str, label: str) -> str | None:
    """Return *value* iff it is a safe path component, else print an error and return None."""
    if value in (".", "..") or not SAFE_COMPONENT.match(value):
        print(f"Unsafe path component for {label}: {value!r}", file=sys.stderr)
        return None
    return value


def _read_result(source: str) -> dict | None:
    """Read the gate stdout JSON from a file path, or from stdin when *source* is ``-``."""
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).expanduser().read_text(
            encoding="utf-8"
        )
    except OSError as exc:
        print(f"Cannot read gate result: {exc}", file=sys.stderr)
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Invalid gate result JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, dict):
        print("Gate result must be a JSON object.", file=sys.stderr)
        return None
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a gate verdict as both an audit artifact and state.gate_results."
    )
    parser.add_argument("--state", type=Path, required=True, help="Path to state.json")
    parser.add_argument(
        "--node",
        required=True,
        choices=GATE_NODES,
        help="Gate DAG node name (must match config/pipeline.dag.yaml gate nodes).",
    )
    parser.add_argument(
        "--result",
        required=True,
        help="Path to the gate's stdout JSON, or '-' to read it from stdin.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="Run directory (.pipeline/runs/<run_id>) the artifact is written under.",
    )
    parser.add_argument(
        "--artifact-type",
        required=True,
        choices=ARTIFACT_TYPES,
        help="Artifact type (constrained to the enum; becomes a path component).",
    )
    parser.add_argument("--attempt", type=int, required=True, help="Attempt number (int).")
    args = parser.parse_args()

    # --- Read + normalize the gate stdout (Wiring Fact 2) --------------------------------
    payload = _read_result(args.result)
    if payload is None:
        return 1
    # A top-level 'gate_b' key means this is score_fit.py's {gate_b, gate_c} wrapper: unwrap
    # to the inner gate_b envelope so everything downstream sees a uniform gate_result shape.
    envelope = payload.get("gate_b") if isinstance(payload.get("gate_b"), dict) else payload
    gate_c = payload.get("gate_c") if "gate_b" in payload else None

    content = envelope.get("content") if isinstance(envelope, dict) else None
    verdict = content.get("verdict") if isinstance(content, dict) else None
    if verdict not in ("pass", "fail"):
        print(
            f"Malformed gate result: content.verdict must be 'pass' or 'fail', got {verdict!r}",
            file=sys.stderr,
        )
        return 1

    # --- Sanitize every path component before any join (V12, threat T-07-08) -------------
    run_dir = args.run_dir
    if ".." in run_dir.parts:
        print(f"Unsafe run-dir (contains '..'): {run_dir}", file=sys.stderr)
        return 1
    if _safe_component(run_dir.name, "run-dir") is None:
        return 1
    node = _safe_component(args.node, "node")
    artifact_type = _safe_component(args.artifact_type, "artifact-type")
    attempt = _safe_component(str(args.attempt), "attempt")
    if node is None or artifact_type is None or attempt is None:
        return 1

    # --- Job 1: write the normalized envelope verbatim as the audit artifact -------------
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = run_dir / f"gate_{node}_{artifact_type}_{attempt}.json"
        artifact_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # Gate C is advisory (FIT-05): store it SEPARATELY, never in the routing artifact.
        if isinstance(gate_c, dict):
            (run_dir / f"gate_c_{node}_{artifact_type}_{attempt}.json").write_text(
                json.dumps(gate_c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except OSError as exc:
        print(f"Cannot write gate artifact: {exc}", file=sys.stderr)
        return 1

    # --- Job 2: set state.gate_results[node] preserving siblings (read-modify-preserve) --
    state_path = args.state.expanduser()
    if state_path.is_file():
        try:
            state: dict = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Invalid state JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(state, dict):
            print("State file must contain a JSON object.", file=sys.stderr)
            return 1
    else:
        state = {}

    # Wiring Fact 1: this exact key is what route.py reads to branch a gate node.
    state.setdefault("gate_results", {})[node] = verdict

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Cannot write state: {exc}", file=sys.stderr)
        return 1

    print(artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
