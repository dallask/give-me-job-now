#!/usr/bin/env python3
"""Deterministic offer-level dispatch-cap decision query (CONC-02).

Given a batch's ``manifest.json`` (its FROZEN ``max_parallel_offers`` cap, per
``gmj_batch.py init``) and each offer's 3 per-(offer, artifact_type) run entries, this
script answers: "which run_ids are dispatchable right now?" It is a pure read + stdout
query — it NEVER writes to disk, and it is not itself a pass/fail gate (unlike
``gmj_check_cap.py``'s retry-exhaustion hard-stop): a "no free capacity right now" result
is a normal, expected outcome and still exits 0. Nonzero is reserved for malformed
input/manifest-not-found.

Every offer's 3 runs (``cv``/``cover_letter``/``interview_prep``) are classified as:

- TERMINAL — the run is truly done: ``status == "delivered"`` AND the imported
  ``blocked_reason(gate_results)`` (read from that run's OWN ``state.json``, treated as
  ``{}`` if absent/unreadable/malformed) returns ``None`` — a real, double-checked
  delivered — OR ``status`` is an explicit terminal-stop label (``gate_exhausted``/
  ``error``, no state.json cross-check needed since these are hub-authored terminal
  labels, not claims of success).
- FRESH — ``status == "waiting"`` (never dispatched — the ``init``-seeded value).
- ACTIVE — anything else, including ``status == "in_flight"`` AND a ``"delivered"``
  label whose gate double-check FAILS (a stale/forged label is treated conservatively as
  still active, never as free capacity — closes T-35-04).

An OFFER is TERMINAL only when all 3 of its runs are TERMINAL; FRESH only when all 3 are
FRESH; otherwise ACTIVE — per the project's CONC-02 pitfall: "an offer that is retrying
still occupies a concurrency slot," so any single ACTIVE run (or a TERMINAL+FRESH mix
with no ACTIVE run but not all-FRESH either) still counts the whole offer as ACTIVE.

``in_flight`` = count of ACTIVE offers. ``free_slots = max(0, cap - in_flight)``.
``dispatchable`` = the union of (a) every non-TERMINAL run_id belonging to an ACTIVE
offer (already-started work always keeps its slot and keeps advancing — it never needs a
NEW slot to continue), plus (b) all 3 run_ids of the next ``free_slots`` FRESH offers,
admitted in ascending ``offer_index`` order. ``waiting`` = the FRESH offers beyond the
admitted ``free_slots``, in ascending ``offer_index`` order.

Reuses (never re-implements) ``gmj_batch._load_manifest``/``gmj_batch._safe_id`` and
``gmj_check_delivery.blocked_reason`` by import — mirrors ``_cmd_resume``'s existing
label-AND-gate double-check discipline for "is this run really terminal?"

CLI: ``gmj_dispatch_cap.py --batch <batch_id> [--pipeline-dir <dir>]`` emits ONE JSON
line to stdout: ``{"dispatchable": [...], "in_flight": <int>, "cap": <int>,
"waiting": [...]}`` (``sort_keys=True`` for determinism) and exits 0 on any well-formed
manifest; exits 1 (structured stderr, no traceback) on an unsafe ``--batch``, a missing/
invalid manifest, or a malformed/missing ``max_parallel_offers``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_batch import _load_manifest, _safe_id  # noqa: E402
from gmj_check_delivery import blocked_reason  # noqa: E402
from gmj_pipeline_paths import resolve_pipeline_dir  # noqa: E402  (single-sourced pipeline root)

ARTIFACT_TYPES = ["cv", "cover_letter", "interview_prep"]

TERMINAL = "terminal"
FRESH = "fresh"
ACTIVE = "active"


def _load_run_state(pipeline_dir: Path, run_id: str) -> dict:
    """Read a run's OWN state.json; return {} if absent/unreadable/malformed (fail-open-to-ACTIVE).

    A missing/unreadable/malformed state.json means ``blocked_reason({})`` will report
    both required gates missing, so the run is never mistaken for TERMINAL without a real
    recorded pass.
    """
    state_path = pipeline_dir / "runs" / run_id / "state.json"
    if not state_path.is_file():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    if not isinstance(state, dict):
        return {}
    return state


def _classify_run(pipeline_dir: Path, run: dict) -> str:
    """Classify one run dict as TERMINAL / FRESH / ACTIVE."""
    status = run.get("status")
    run_id = run.get("run_id")
    if status in ("gate_exhausted", "error"):
        return TERMINAL
    if status == "delivered":
        state = _load_run_state(pipeline_dir, run_id) if run_id else {}
        gate_results = state.get("gate_results")
        if not isinstance(gate_results, dict):
            gate_results = {}
        if blocked_reason(gate_results) is None:
            return TERMINAL
        return ACTIVE  # forged/stale "delivered" label — conservatively still ACTIVE (T-35-04)
    if status == "waiting":
        return FRESH
    return ACTIVE  # includes "in_flight" and any unrecognized status


def _classify_offer(run_classes: list[str]) -> str:
    """Classify an offer from its 3 runs' classifications."""
    if all(c == TERMINAL for c in run_classes):
        return TERMINAL
    if all(c == FRESH for c in run_classes):
        return FRESH
    return ACTIVE


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic offer-level dispatch-cap query: which run_ids are "
            "dispatchable right now, given the frozen cap and each offer's run states."
        )
    )
    parser.add_argument("--batch", required=True, help="batch_id whose manifest to query.")
    parser.add_argument(
        "--pipeline-dir",
        default=resolve_pipeline_dir(),
        help="Read-only pipeline root to inspect (default .pipeline).",
    )
    args = parser.parse_args()

    if _safe_id(args.batch, "batch_id") is None:
        return 1

    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    manifest, _manifest_path, _batches_dir = _load_manifest(pipeline_dir, args.batch)
    if manifest is None:
        # _load_manifest already printed a structured stderr message.
        return 1

    cap = manifest.get("max_parallel_offers")
    if not isinstance(cap, int) or isinstance(cap, bool):
        print(
            "Malformed manifest: 'max_parallel_offers' must be a frozen integer.",
            file=sys.stderr,
        )
        return 1

    offers = manifest.get("offers")
    if not isinstance(offers, list):
        offers = []

    active_run_ids: list[str] = []
    fresh_offers: list[tuple[int, list[str]]] = []  # (offer_index, [run_id, run_id, run_id])
    in_flight = 0

    for offer in offers:
        if not isinstance(offer, dict):
            continue
        offer_index = offer.get("offer_index")
        runs = offer.get("runs") or {}
        run_classes: list[str] = []
        run_ids: list[str] = []
        for artifact_type in ARTIFACT_TYPES:
            run = runs.get(artifact_type)
            if not isinstance(run, dict):
                run = {}
            run_classes.append(_classify_run(pipeline_dir, run))
            run_ids.append(run.get("run_id"))

        offer_class = _classify_offer(run_classes)
        if offer_class == ACTIVE:
            in_flight += 1
            for rc, rid in zip(run_classes, run_ids):
                if rc != TERMINAL and rid is not None:
                    active_run_ids.append(rid)
        elif offer_class == FRESH:
            fresh_offers.append((offer_index, run_ids))
        # TERMINAL offers contribute nothing to in_flight/dispatchable/waiting.

    free_slots = max(0, cap - in_flight)
    fresh_offers.sort(key=lambda item: (item[0] is None, item[0]))

    admitted = fresh_offers[:free_slots]
    remaining = fresh_offers[free_slots:]

    dispatchable = list(active_run_ids)
    for _offer_index, run_ids in admitted:
        dispatchable.extend(rid for rid in run_ids if rid is not None)

    waiting = [offer_index for offer_index, _run_ids in remaining]

    print(
        json.dumps(
            {
                "dispatchable": dispatchable,
                "in_flight": in_flight,
                "cap": cap,
                "waiting": waiting,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
