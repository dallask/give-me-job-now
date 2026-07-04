#!/usr/bin/env python3
"""Read-only run/batch inspector — the mirror image of the writer gmj_batch.py (ERGO-01..04).

This CLI projects run/batch status PURELY from the existing artifacts the pipeline already
writes — ``.pipeline/runs/<id>/state.json`` + per-run gate-log files +
``.pipeline/batches/<id>/manifest.json`` — with NO second datastore and ZERO write calls
(ERGO-04, load-bearing invariant). It is the read-half twin of ``gmj_batch.py``: the writer's
skeleton (module header, ``_safe_id`` path guard, canonical JSON emit, argparse dispatch) is
reused verbatim; every write path (the ``state_write``/``jsonschema`` imports, file writes,
temp-rename, and directory creation) is deleted.

Subcommands (noun -> verb): ``runs list``, ``run inspect <id>``, ``batches list``,
``batch inspect <id>``. Every subcommand takes ``--pipeline-dir`` (default ``.pipeline``) and
``--json``.

Status projection (top-down, FIRST MATCH WINS):
  1. ``delivered`` — the reused, non-bypassable ``check_delivery.blocked_reason(gate_results)``
     returns None (Gate A ``truth-verifier==pass`` AND Gate B ``fit-evaluator==pass``). Imported
     VERBATIM so ``delivered`` agrees with gmj_batch.py resume byte-for-byte — never re-derived.
  2. ``failed`` — the frozen ``retry_cap`` is an int (and not a bool) and some nested
     ``retry_counts`` counter ``>= retry_cap`` (mirrors check_cap.py's ``current >= cap`` guard).
  3. ``pending`` — no gate_results, no retry_counts, and ``current_step`` in (None,
     "artifact-composer") — the freshly-seeded signature.
  4. ``running`` — anything else.
A missing ``state.json`` SKIPS the dir; a malformed/non-dict ``state.json`` DEGRADES to an
``unknown`` row and the rest of the list still prints (one bad run never aborts the table).

Read-only invariant (ERGO-04): the module opens run files for reading only, creates no
directories, writes no temporary files, never mutates a run dir, and never resolves/stats a
run's ``offer_spec_path`` (displayed verbatim — it may be relative). Resume commands are
PRINTED, never executed. All error paths print a structured stderr message and ``return 1`` —
never a traceback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Reuse the audited Gate A ∧ Gate B delivery predicate verbatim — never re-judge a gate here
# (Pitfall 2 / T-12-04). check_delivery.py lives in this same scripts/pipeline dir, which is on
# sys.path both when this file is run as a script and when imported via a sys.path insert (tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_delivery import blocked_reason  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root

_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Newest-first ordering key: the first YYYYMMDDThhmmss substring anywhere in the run_id.
_TS_RE = re.compile(r"\d{8}T\d{6}")


def _safe_id(value: str, label: str) -> str | None:
    """Return ``value`` if it is a safe single path component, else print + return None."""
    if (
        value in (".", "..")
        or ".." in value
        or "/" in value
        or "\\" in value
        or not _ID_RE.match(value)
    ):
        print(f"Unsafe {label}: {value!r}", file=sys.stderr)  # V12, T-12-01
        return None
    return value


def _safe_component(value: object) -> bool:
    """Silent variant of ``_safe_id`` for manifest-sourced run_ids in a read-only preview.

    Returns True when ``value`` is a safe single path component. Unlike ``_safe_id`` it prints
    nothing — a crafted run_id inside a manifest simply skips the gate cross-check (the run stays
    in the resume set) instead of aborting the whole batch preview.
    """
    return (
        isinstance(value, str)
        and value not in (".", "..")
        and ".." not in value
        and "/" not in value
        and "\\" not in value
        and bool(_ID_RE.match(value))
    )


def _order_key(run_id: str) -> tuple[str, str]:
    """(first \\d{8}T\\d{6} match or "", run_id). Sort ``reverse=True`` for newest-first.

    A run_id with no timestamp substring sorts LAST under descending order (empty string is the
    smallest key); the run_id itself is the deterministic lexicographic tie-break.
    """
    m = _TS_RE.search(run_id)
    return (m.group(0) if m else "", run_id)


def _gate_results(state: dict) -> dict:
    """gate_results as a dict, or {} for any other shape (degrade, never raise)."""
    gr = state.get("gate_results")
    return gr if isinstance(gr, dict) else {}


def project_status(state: dict) -> str:
    """Project a run status from its state dict — locked TOP-DOWN, FIRST-MATCH-WINS order."""
    gate_results = _gate_results(state)
    retry_cap = state.get("retry_cap")
    rc = state.get("retry_counts")
    retry_counts = rc if isinstance(rc, dict) else {}
    current_step = state.get("current_step")

    # (1) delivered — reused, non-bypassable Gate A ∧ Gate B predicate (never re-derived).
    if blocked_reason(gate_results) is None:
        return "delivered"
    # (2) failed — a nested retry counter has reached the frozen int cap (check_cap semantics).
    if (
        isinstance(retry_cap, int)
        and not isinstance(retry_cap, bool)
        and any(
            c >= retry_cap
            for per_type in retry_counts.values()
            if isinstance(per_type, dict)
            for c in per_type.values()
            if isinstance(c, int) and not isinstance(c, bool)
        )
    ):
        return "failed"
    # (3) pending — the freshly-seeded signature.
    if not gate_results and not retry_counts and current_step in (None, "artifact-composer"):
        return "pending"
    # (4) running — anything else.
    return "running"


def _emit_json(payload: dict) -> None:
    """Canonical, byte-deterministic JSON (sorted keys, indent 2, trailing newline)."""
    sys.stdout.write(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


def _run_row(run_id: str, state: dict) -> dict:
    """Build a terse list row from a good (dict) state."""
    gr = _gate_results(state)
    return {
        "run_id": run_id,
        "status": project_status(state),
        "mode": state.get("execution_mode") or "—",
        "gate_a": gr.get("truth-verifier") or "—",
        "gate_b": gr.get("fit-evaluator") or "—",
        "ts": _order_key(run_id)[0] or "—",
    }


def _cmd_runs_list(args: argparse.Namespace) -> int:
    """List every run dir that has a state.json, newest-first, degrading malformed rows."""
    pipeline_dir = Path(args.pipeline_dir).expanduser()
    runs_dir = pipeline_dir / "runs"
    rows: list[dict] = []
    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            sp = run_dir / "state.json"
            if not sp.is_file():
                continue  # stray / gate-logs-only dir: skip, never KeyError
            try:
                state = json.loads(sp.read_text(encoding="utf-8"))
                if not isinstance(state, dict):
                    raise ValueError("state is not an object")
                rows.append(_run_row(run_dir.name, state))
            except (ValueError, OSError):
                rows.append(
                    {
                        "run_id": run_dir.name,
                        "status": "unknown",
                        "mode": "—",
                        "gate_a": "—",
                        "gate_b": "—",
                        "ts": _order_key(run_dir.name)[0] or "—",
                    }
                )
    rows.sort(key=lambda r: _order_key(r["run_id"]), reverse=True)

    if args.json_out:
        _emit_json({"kind": "runs_list", "runs": rows})
    else:
        for r in rows:
            print(
                f"{r['run_id']:<34} {r['status']:<10} {r['mode']:<18} "
                f"A:{r['gate_a']:<6} B:{r['gate_b']:<6} {r['ts']}"
            )
    return 0


def _batch_rollup(manifest: dict, fallback_id: str) -> dict:
    """Roll a manifest up to {batch_id, delivered, total} counting per-artifact-type runs."""
    delivered = 0
    total = 0
    for offer in manifest.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        runs = offer.get("runs")
        if not isinstance(runs, dict):
            continue
        for run in runs.values():
            if not isinstance(run, dict):
                continue
            total += 1
            if run.get("status") == "delivered":
                delivered += 1
    # Every batch row carries the SAME keys (incl. "status") so the JSON schema is uniform with
    # the degrade branch and symmetric with runs list — a consumer reading row["status"] to find
    # degraded batches never KeyErrors on a healthy row. "unknown" is reserved for the degrade path.
    return {
        "batch_id": manifest.get("batch_id") or fallback_id,
        "delivered": delivered,
        "total": total,
        "status": "ok",
    }


def _cmd_batches_list(args: argparse.Namespace) -> int:
    """List batches; an absent .pipeline/batches/ dir yields an empty (exit-0) result."""
    pipeline_dir = Path(args.pipeline_dir).expanduser()
    batches_dir = pipeline_dir / "batches"
    rows: list[dict] = []
    if batches_dir.is_dir():
        for batch_dir in sorted(batches_dir.iterdir()):
            if not batch_dir.is_dir():
                continue
            mp = batch_dir / "manifest.json"
            if not mp.is_file():
                continue
            try:
                manifest = json.loads(mp.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("manifest is not an object")
                rows.append(_batch_rollup(manifest, batch_dir.name))
            except (ValueError, OSError):
                rows.append({"batch_id": batch_dir.name, "delivered": 0, "total": 0, "status": "unknown"})
    rows.sort(key=lambda r: r["batch_id"], reverse=True)

    if args.json_out:
        _emit_json({"kind": "batches_list", "batches": rows})
    else:
        for r in rows:
            print(f"{r['batch_id']:<34} delivered={r['delivered']}/{r['total']}")
    return 0


def _gate_logs(run_dir: Path) -> tuple[list[str], list[str]]:
    """Return (all filenames, gate-log filenames) present in ``run_dir`` — read-only glob.

    Tolerantly matches BOTH gate-log conventions: the go-forward
    ``gate_<node>_<type>_<attempt>.json`` / advisory ``gate_c_...`` AND the legacy
    ``<type>.gateA[.retryN].json`` / ``<type>.gateB.json``. A missing/oddly-named log is
    non-fatal (it simply is not classified as an attempt).
    """
    artifacts: list[str] = []
    attempts: list[str] = []
    for f in sorted(run_dir.iterdir()):
        if not f.is_file():
            continue
        artifacts.append(f.name)
        if f.name.startswith("gate_") or re.search(r"\.gate[AB]", f.name):
            attempts.append(f.name)
    return artifacts, attempts


def _cmd_run_inspect(args: argparse.Namespace) -> int:
    """Inspect one run: verdicts, run-dir artifacts, per-attempt history, printed resume command."""
    pipeline_dir = Path(args.pipeline_dir).expanduser()
    runs_dir = pipeline_dir / "runs"
    if _safe_id(args.run_id, "run_id") is None:
        return 1
    run_dir = runs_dir / args.run_id
    # Defence in depth: the resolved run dir must stay contained under the resolved runs dir.
    resolved = run_dir.resolve()
    base = runs_dir.resolve()
    if resolved != base and base not in resolved.parents:
        print(f"Refusing to inspect outside {base}: {resolved}", file=sys.stderr)
        return 1

    sp = run_dir / "state.json"
    if not sp.is_file():
        print(f"Run state not found: {sp}", file=sys.stderr)
        return 1
    try:
        state = json.loads(sp.read_text(encoding="utf-8"))
    except ValueError as exc:  # JSONDecodeError subclasses ValueError
        print(f"Invalid state JSON at {sp}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(state, dict):
        print("State file must contain a JSON object.", file=sys.stderr)
        return 1

    gr = _gate_results(state)
    artifacts, attempts = _gate_logs(run_dir)
    # Resume is PRINTED, never executed — an existing run_id resumes via route.py (pipeline-run.md).
    resume_command = f"/pipeline-run  (resume: pass run_id={args.run_id})"

    payload = {
        "kind": "run_inspect",
        "run_id": state.get("run_id") or args.run_id,
        "status": project_status(state),
        "mode": state.get("execution_mode") or "—",
        "gate_a": gr.get("truth-verifier") or "—",
        "gate_b": gr.get("fit-evaluator") or "—",
        # offer_spec_path is displayed VERBATIM — never resolved/stat'd (it may be relative).
        "offer_spec_path": state.get("offer_spec_path"),
        "offer_spec_hash": state.get("offer_spec_hash"),
        "retry_cap": state.get("retry_cap"),
        "retry_counts": state.get("retry_counts") or {},
        "current_step": state.get("current_step"),
        "artifacts": artifacts,
        "attempts": attempts,
        "resume_command": resume_command,
    }

    if args.json_out:
        _emit_json(payload)
    else:
        print(f"run_id        {payload['run_id']}")
        print(f"status        {payload['status']}")
        print(f"mode          {payload['mode']}")
        print(f"Gate A        {payload['gate_a']}")
        print(f"Gate B        {payload['gate_b']}")
        print(f"offer_spec    {payload['offer_spec_path']}")
        print(f"offer_hash    {payload['offer_spec_hash']}")
        print(f"retry_cap     {payload['retry_cap']}")
        print(f"retry_counts  {json.dumps(payload['retry_counts'], sort_keys=True, ensure_ascii=False)}")
        print(f"current_step  {payload['current_step']}")
        print(f"artifacts     {', '.join(artifacts) or '(none)'}")
        print(f"attempts      {', '.join(attempts) or '(none)'}")
        print(f"resume        {resume_command}")
    return 0


def _cmd_batch_inspect(args: argparse.Namespace) -> int:
    """Inspect one batch: per-offer per-artifact-type run rows + printed batch resume command.

    The resume-set preview mirrors gmj_batch.py resume's label-AND-gate predicate
    (``label == "delivered" and blocked_reason(gate_results) is None`` read from each run's own
    state.json) so the preview matches the real resume — never trusting the manifest label alone.
    """
    pipeline_dir = Path(args.pipeline_dir).expanduser()
    runs_dir = pipeline_dir / "runs"
    if _safe_id(args.batch_id, "batch_id") is None:
        return 1
    batches_dir = pipeline_dir / "batches"
    manifest_path = batches_dir / args.batch_id / "manifest.json"
    # Defence in depth: the resolved manifest path must stay contained under the batches dir.
    resolved = manifest_path.resolve()
    base = batches_dir.resolve()
    if base not in resolved.parents:
        print(f"Refusing to inspect outside {base}: {resolved}", file=sys.stderr)
        return 1
    if not manifest_path.is_file():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:  # JSONDecodeError subclasses ValueError
        print(f"Invalid manifest JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print("Manifest file must contain a JSON object.", file=sys.stderr)
        return 1

    offers_out: list[dict] = []
    for offer in manifest.get("offers") or []:
        if not isinstance(offer, dict):
            continue
        offer_index = offer.get("offer_index")
        runs = offer.get("runs")
        if not isinstance(runs, dict):
            continue
        for artifact_type, run in runs.items():
            if not isinstance(run, dict):
                continue
            run_id = run.get("run_id")
            label = run.get("status")
            # Cross-check the manifest label against the run's own recorded gates (defence in
            # depth): a forged/corrupt 'delivered' label without a real gate pass is not trusted.
            gate_results: dict = {}
            if _safe_component(run_id):
                rsp = runs_dir / run_id / "state.json"
                if rsp.is_file():
                    try:
                        rstate = json.loads(rsp.read_text(encoding="utf-8"))
                    except ValueError:
                        rstate = None
                    if isinstance(rstate, dict) and isinstance(rstate.get("gate_results"), dict):
                        gate_results = rstate["gate_results"]
            delivered = label == "delivered" and blocked_reason(gate_results) is None
            offers_out.append(
                {
                    "offer_index": offer_index,
                    "artifact_type": artifact_type,
                    "run_id": run_id,
                    "status": label,
                    "in_resume_set": not delivered,
                }
            )

    # Resume is PRINTED, never executed (gmj-batch.md).
    resume_command = f"/gmj-batch --resume {args.batch_id}"
    payload = {
        "kind": "batch_inspect",
        "batch_id": manifest.get("batch_id") or args.batch_id,
        "offers": offers_out,
        "resume_command": resume_command,
    }

    if args.json_out:
        _emit_json(payload)
    else:
        for r in offers_out:
            flag = "resume" if r["in_resume_set"] else "done"
            # Coerce nullable manifest-sourced fields to a display string BEFORE the width spec:
            # a partial manifest (missing offer_index/run_id/status -> None) must degrade to a
            # readable row, never raise `f"{None:<3}"` TypeError (never-a-traceback contract).
            oi = "—" if r["offer_index"] is None else str(r["offer_index"])
            rid = "—" if r["run_id"] is None else str(r["run_id"])
            st = "—" if r["status"] is None else str(r["status"])
            print(
                f"offer_index={oi:<3} artifact_type={r['artifact_type']:<14} "
                f"run_id={rid:<28} status={st:<10} [{flag}]"
            )
        print(f"resume        {resume_command}")
    return 0


def _add_common(parser: argparse.ArgumentParser, func) -> None:
    parser.add_argument(
        "--pipeline-dir",
        default=".pipeline",
        help="Read-only pipeline root to inspect (default .pipeline).",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Emit canonical JSON instead of a terse table."
    )
    parser.set_defaults(func=func)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only run/batch inspector (runs list, run inspect, batches list, batch inspect)."
    )
    sub = parser.add_subparsers(dest="noun", required=True)

    p_runs = sub.add_parser("runs", help="Run-collection ops.")
    runs_sub = p_runs.add_subparsers(dest="verb", required=True)
    _add_common(runs_sub.add_parser("list", help="List runs newest-first."), _cmd_runs_list)

    p_run = sub.add_parser("run", help="Single-run ops.")
    run_sub = p_run.add_subparsers(dest="verb", required=True)
    p_run_inspect = run_sub.add_parser(
        "inspect", help="Inspect one run (verdicts, artifacts, attempts, resume command)."
    )
    p_run_inspect.add_argument("run_id", help="Run id (a single safe path component).")
    _add_common(p_run_inspect, _cmd_run_inspect)

    p_batches = sub.add_parser("batches", help="Batch-collection ops.")
    batches_sub = p_batches.add_subparsers(dest="verb", required=True)
    _add_common(batches_sub.add_parser("list", help="List batches with delivered/total rollup."), _cmd_batches_list)

    p_batch = sub.add_parser("batch", help="Single-batch ops.")
    batch_sub = p_batch.add_subparsers(dest="verb", required=True)
    p_batch_inspect = batch_sub.add_parser(
        "inspect", help="Inspect one batch (per-offer run rows + resume command)."
    )
    p_batch_inspect.add_argument("batch_id", help="Batch id (a single safe path component).")
    _add_common(p_batch_inspect, _cmd_batch_inspect)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
