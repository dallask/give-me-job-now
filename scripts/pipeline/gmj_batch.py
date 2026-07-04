#!/usr/bin/env python3
"""Deterministic per-offer batch control-plane CLI (SELECT-01, SELECT-02, SELECT-03).

Pure files + stdout: this script holds NO ``Task``, no network, no LLM, and re-judges NO
gate/cap/delivery. It is the single producer of the per-(offer, artifact_type) run states and
the batch manifest; the ``/gmj-batch`` hub persona (12-03) drives the spokes, and the resume
path (12-02) extends this module with ``mark``/``resume`` ops.

Subcommand implemented here: ``init``.

    init --shortlist <path> --select "1,3,5" [--batch-id <id>] [--run-id-prefix <p>]
         [--config <path>] [--execution-mode ...] [--retry-cap N] [--pipeline-dir <dir>]

For each selected shortlist entry it:
  1. resolves the 1-indexed selection string to sorted, deduped, bounds-checked 0-based indices
     (SELECT-01),
  2. maps the coarse shortlist entry to a freeze-draft copying only the offer_content schema
     fields (title/company/location/seniority/language + trace.source_url->source_url,
     trace.excerpt->raw_text_excerpt) and dropping every non-schema key; flags ``thin`` when
     ``must_haves`` is absent/empty OR the excerpt is missing (SELECT-02),
  3. derives three per-(offer, artifact_type) run_ids ``<run_id>-cv``/``-cl``/``-ip``, freezes each
     via the existing ``state_write.py`` and seeds ``current_step: artifact-composer`` (route.py
     raises without it) — three distinct seeded ``state.json`` per offer, none at the bare run_id
     (SELECT-03),
  4. writes an offer-centric canonical manifest validated against
     ``schemas/batch_manifest.schema.json`` under ``<pipeline-dir>/batches/<batch_id>/``.

All error paths print a structured stderr message and ``return 1`` — never a traceback. Ids are
sanitized to ``^[A-Za-z0-9._-]+$`` (rejecting ``.``/``..``/``/``/``\\``) before they can become a
run-dir path component (T-12-01, V12 path-traversal); the manifest write is additionally
contained under the resolved batches dir (defence in depth, mirrors freeze_offer.py).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

# Reuse the audited Gate A ∧ Gate B delivery predicate verbatim — never re-judge a gate here
# (Pitfall 2 / T-12-04). check_delivery.py lives in this same scripts/pipeline dir, which is on
# sys.path both when this file is run as a script and when imported via a sys.path insert (tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_delivery import blocked_reason  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root
STATE_WRITE = REPO_ROOT / "scripts" / "pipeline" / "state_write.py"
SCHEMA_PATH = REPO_ROOT / "schemas" / "batch_manifest.schema.json"
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"

# (manifest run key, run_id suffix) — mirrors v1.0's cv-*/cl-*/ip-* run-dir pattern.
ARTIFACT_TYPES: tuple[tuple[str, str], ...] = (
    ("cv", "cv"),
    ("cover_letter", "cl"),
    ("interview_prep", "ip"),
)

# offer_spec.schema.json#/$defs/offer_content property allow-list. A coarse->draft copies only
# these present fields; every other shortlist key (board/canonical_key/score/mode/salary/trace)
# is dropped because offer_content is additionalProperties:false.
_OFFER_CONTENT_FIELDS = (
    "title",
    "company",
    "location",
    "seniority",
    "employment_type",
    "language",
    "must_haves",
    "nice_to_haves",
    "responsibilities",
    "salary_range",
    "source_url",
    "raw_text_excerpt",
)

_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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


def resolve_selection(sel: str, n: int) -> list[int]:
    """Resolve a 1-indexed selection string to sorted, deduped 0-based indices (SELECT-01).

    ``"all"`` -> every index. Non-numeric or out-of-range tokens raise ValueError.
    """
    if sel.strip().lower() == "all":
        return list(range(n))
    picks: set[int] = set()
    for tok in sel.split(","):
        tok = tok.strip()
        if not tok.isdigit():
            raise ValueError(f"invalid selection token: {tok!r}")
        i = int(tok)
        if not (1 <= i <= n):
            raise ValueError(f"selection {i} out of range 1..{n}")
        picks.add(i - 1)
    return sorted(picks)


def is_thin(entry: dict) -> bool:
    """True when the coarse entry cannot seed a viable freeze (SELECT-02 fallback signal).

    Thin is the PRIMARY path: a coarse shortlist entry never carries ``must_haves``, so the hub
    re-fields it via offer-scout single-offer intake. Thin whenever ``must_haves`` is absent/empty
    OR the excerpt is missing.
    """
    mh = entry.get("must_haves")
    excerpt = (entry.get("trace") or {}).get("excerpt")
    return not (isinstance(mh, list) and mh) or not excerpt


def coarse_to_draft(entry: dict) -> dict:
    """Map a coarse shortlist entry to an offer_content-shaped freeze-draft (SELECT-02).

    Copies the present offer_content schema fields, maps ``trace.source_url``->``source_url`` and
    ``trace.excerpt``->``raw_text_excerpt``, and drops every non-schema key.
    """
    draft: dict = {}
    for field in _OFFER_CONTENT_FIELDS:
        if field in entry and field not in ("source_url", "raw_text_excerpt"):
            draft[field] = entry[field]
    trace = entry.get("trace") or {}
    if isinstance(trace, dict):
        if trace.get("source_url"):
            draft["source_url"] = trace["source_url"]
        if trace.get("excerpt"):
            draft["raw_text_excerpt"] = trace["excerpt"]
    return draft


def _validate_manifest(doc: dict) -> None:
    """Validate the assembled manifest against batch_manifest.schema.json, fail closed."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        loc = "/".join(map(str, first.absolute_path)) or "<root>"
        raise ValueError(
            f"assembled manifest violates batch_manifest.schema.json at {loc}: {first.message}"
        )


def write_manifest(manifest: dict, out: Path, batches_dir: Path) -> Path:
    """Validate then write the canonical byte-identical manifest, contained under ``batches_dir``.

    The containment base and the output path share the same resolved anchor, so a crafted
    ``batch_id`` cannot escape (defence in depth on top of ``_safe_id``; mirrors freeze_offer.py).
    """
    resolved = out.expanduser().resolve()
    base = batches_dir.expanduser().resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Refusing to write outside {base}: {resolved}")
    _validate_manifest(manifest)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return resolved


def _seed_state(
    run_id: str, runs_dir: Path, config: Path, execution_mode: str | None, retry_cap: int | None
) -> int:
    """Freeze run-config via state_write.py, then seed current_step (read-modify-preserve).

    Returns 0 on success, 1 after a structured stderr message on any failure.
    """
    state_path = runs_dir / run_id / "state.json"
    cmd = [
        sys.executable,
        str(STATE_WRITE),
        "--state",
        str(state_path),
        "--run-id",
        run_id,
        "--config",
        str(config),
    ]
    if execution_mode is not None:
        cmd += ["--execution-mode", execution_mode]
    if retry_cap is not None:
        cmd += ["--retry-cap", str(retry_cap)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"state_write failed for run_id {run_id!r}: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    # Read-modify-preserve: seed current_step without dropping the frozen keys (route.py:33-34).
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot re-read seeded state {state_path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(state, dict):
        print(f"Seeded state must be a JSON object: {state_path}", file=sys.stderr)
        return 1
    state["current_step"] = "artifact-composer"
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    batches_dir = pipeline_dir / "batches"
    runs_dir = pipeline_dir / "runs"

    # Load the shortlist (fail-closed: is_file -> json -> isinstance guard).
    shortlist_path = Path(args.shortlist).expanduser()
    if not shortlist_path.is_file():
        print(f"Shortlist not found: {shortlist_path}", file=sys.stderr)
        return 1
    try:
        doc = json.loads(shortlist_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid shortlist JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(doc, dict):
        print("Shortlist file must contain a JSON object.", file=sys.stderr)
        return 1
    entries = doc.get("shortlist")
    if not isinstance(entries, list) or not entries:
        print("Shortlist 'shortlist' must be a non-empty JSON array.", file=sys.stderr)
        return 1

    # Resolve the selection (SELECT-01).
    try:
        selected = resolve_selection(args.select, len(entries))
    except ValueError as exc:
        print(f"Selection error: {exc}", file=sys.stderr)
        return 1
    if not selected:
        print("Selection resolved to no offers.", file=sys.stderr)
        return 1

    # Safe batch_id (generated safe-by-construction unless overridden), then per-offer ids.
    batch_id = args.batch_id or "batch-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    if _safe_id(batch_id, "batch_id") is None:
        return 1
    prefix = args.run_id_prefix or batch_id
    if _safe_id(prefix, "run-id-prefix") is None:
        return 1

    # Pre-validate every id BEFORE any disk write (no partial writes on an unsafe id).
    plan: list[dict] = []
    for i in selected:
        base_run_id = f"{prefix}-{i:03d}"
        if _safe_id(base_run_id, "run_id") is None:
            return 1
        per_type: dict[str, str] = {}
        for _key, suffix in ARTIFACT_TYPES:
            rid = f"{base_run_id}-{suffix}"
            if _safe_id(rid, "run_id") is None:
                return 1
            per_type[suffix] = rid
        plan.append({"index": i, "base_run_id": base_run_id, "per_type": per_type})

    # Build drafts + manifest offers + seed the per-(offer, artifact_type) states.
    offers: list[dict] = []
    out_lines: list[str] = [f"batch_id={batch_id}"]
    for item in plan:
        i = item["index"]
        entry = entries[i]
        base_run_id = item["base_run_id"]
        per_type = item["per_type"]

        draft = coarse_to_draft(entry)
        thin = is_thin(entry)
        draft_path = batches_dir / batch_id / "drafts" / f"offer-{i:03d}.draft.json"
        # Contain the draft write under batches_dir too (defence in depth).
        d_resolved = draft_path.resolve()
        if batches_dir not in d_resolved.parents:
            print(f"Refusing to write draft outside {batches_dir}: {d_resolved}", file=sys.stderr)
            return 1
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(draft, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

        # Seed the three per-(offer, artifact_type) states (init is the single producer).
        for suffix in ("cv", "cl", "ip"):
            rc = _seed_state(
                per_type[suffix], runs_dir, args.config, args.execution_mode, args.retry_cap
            )
            if rc != 0:
                return rc

        offers.append(
            {
                "offer_index": i,
                "canonical_key": entry.get("canonical_key", ""),
                "offer_spec_path": "",  # filled post-freeze by the record-spec op (12-02)
                "offer_spec_hash": "",
                "runs": {
                    "cv": {"run_id": per_type["cv"], "status": "pending"},
                    "cover_letter": {"run_id": per_type["cl"], "status": "pending"},
                    "interview_prep": {"run_id": per_type["ip"], "status": "pending"},
                },
            }
        )
        out_lines.append(
            f"offer_index={i} run_id={base_run_id} thin={'true' if thin else 'false'}"
        )

    manifest = {
        "kind": "batch_manifest",
        "schema_version": "1.0",
        "batch_id": batch_id,
        "offers": offers,
    }
    manifest_path = batches_dir / batch_id / "manifest.json"
    try:
        write_manifest(manifest, manifest_path, batches_dir)
    except ValueError as exc:
        print(f"Manifest write error: {exc}", file=sys.stderr)
        return 1

    print("\n".join(out_lines))
    return 0


def _load_manifest(pipeline_dir: Path, batch_id: str) -> tuple[dict | None, Path, Path]:
    """Load a batch manifest with the fail-closed guards; return (manifest|None, path, batches_dir).

    None signals a structured stderr message was already printed and the caller must ``return 1``.
    """
    batches_dir = (pipeline_dir / "batches").resolve()
    manifest_path = pipeline_dir / "batches" / batch_id / "manifest.json"
    if not manifest_path.is_file():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return None, manifest_path, batches_dir
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid manifest JSON: {exc}", file=sys.stderr)
        return None, manifest_path, batches_dir
    if not isinstance(manifest, dict):
        print("Manifest file must contain a JSON object.", file=sys.stderr)
        return None, manifest_path, batches_dir
    return manifest, manifest_path, batches_dir


def _cmd_mark(args: argparse.Namespace) -> int:
    """Set exactly one per-(offer, artifact_type) run's status (read-modify-preserve, canonical)."""
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    if _safe_id(args.batch, "batch_id") is None:
        return 1
    manifest, manifest_path, batches_dir = _load_manifest(pipeline_dir, args.batch)
    if manifest is None:
        return 1

    matched = None
    for offer in manifest.get("offers", []):
        for run in (offer.get("runs") or {}).values():
            if isinstance(run, dict) and run.get("run_id") == args.run_id:
                matched = run
                break
        if matched is not None:
            break
    if matched is None:
        print(f"run_id not found in batch {args.batch!r}: {args.run_id!r}", file=sys.stderr)
        return 1

    matched["status"] = args.status
    try:
        write_manifest(manifest, manifest_path, batches_dir)
    except ValueError as exc:
        print(f"Manifest write error: {exc}", file=sys.stderr)
        return 1
    print(f"marked run_id={args.run_id} status={args.status}")
    return 0


def _cmd_record_spec(args: argparse.Namespace) -> int:
    """Stamp the real freeze offer_spec_path/hash into one offer entry (read-modify-preserve)."""
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    if _safe_id(args.batch, "batch_id") is None:
        return 1
    manifest, manifest_path, batches_dir = _load_manifest(pipeline_dir, args.batch)
    if manifest is None:
        return 1

    matched = None
    for offer in manifest.get("offers", []):
        if offer.get("offer_index") == args.offer_index:
            matched = offer
            break
    if matched is None:
        print(
            f"offer_index not found in batch {args.batch!r}: {args.offer_index}", file=sys.stderr
        )
        return 1

    matched["offer_spec_path"] = args.offer_spec_path
    matched["offer_spec_hash"] = args.offer_spec_hash
    try:
        write_manifest(manifest, manifest_path, batches_dir)
    except ValueError as exc:
        print(f"Manifest write error: {exc}", file=sys.stderr)
        return 1
    print(f"recorded offer_index={args.offer_index} offer_spec_hash={args.offer_spec_hash}")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    """Print the non-delivered per-(offer, artifact_type) runs (label-AND-gate, SELECT-04).

    A run counts as delivered ONLY when BOTH hold: (1) its manifest ``status`` label is
    ``"delivered"`` — set by the ``/gmj-batch`` persona via ``mark`` ONLY after the terminal
    ``cv-generator`` render+delivery completes, so the label is the render-complete signal
    (gate-pass alone is one DAG step too early — CR-01); AND (2) the reused, non-bypassable
    ``check_delivery.blocked_reason`` (Gate A ∧ Gate B) still passes on that run's own
    ``state.json`` gate_results — a cross-check so a forged/corrupt ``"delivered"`` label
    without a real gate pass is never trusted. A crash before ``mark delivered`` leaves the
    label pending/running, so the run is re-listed (re-run/re-render). Rendered-artifact
    existence stays a Manual-Only UAT check (12-VALIDATION.md); this predicate never guesses a
    rendered-PDF path (Pitfall 2, T-12-04).
    """
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    runs_dir = pipeline_dir / "runs"
    if _safe_id(args.batch, "batch_id") is None:
        return 1
    manifest, _manifest_path, _batches_dir = _load_manifest(pipeline_dir, args.batch)
    if manifest is None:
        return 1

    out_lines: list[str] = []
    for offer in manifest.get("offers", []):
        offer_index = offer.get("offer_index")
        for artifact_type, run in (offer.get("runs") or {}).items():
            if not isinstance(run, dict):
                continue
            run_id = run.get("run_id")
            if _safe_id(str(run_id), "run_id") is None:
                return 1
            label = run.get("status")
            state_path = runs_dir / run_id / "state.json"
            gate_results: dict = {}
            if state_path.is_file():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    print(f"Invalid state JSON at {state_path}: {exc}", file=sys.stderr)
                    return 1
                if isinstance(state, dict) and isinstance(state.get("gate_results"), dict):
                    gate_results = state["gate_results"]
            # Delivered ONLY when the terminal cv-generator render+delivery completed — the
            # persona sets the manifest label to 'delivered' via `mark` AFTER render, so the
            # label is the render-complete signal (gates alone are one DAG step too early,
            # CR-01) — AND the reused, non-bypassable Gate A ∧ Gate B predicate still passes
            # (cross-check: a forged/corrupt 'delivered' label without a real gate pass is
            # never trusted). Anything else stays in the resume set (re-run/re-render).
            delivered = label == "delivered" and blocked_reason(gate_results) is None
            if not delivered:
                out_lines.append(
                    f"offer_index={offer_index} artifact_type={artifact_type} run_id={run_id}"
                )

    if not out_lines:
        print("nothing to resume")
        return 0
    print("\n".join(out_lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic per-offer batch control-plane CLI (SELECT-01/02/03/04)."
    )
    sub = parser.add_subparsers(dest="op", required=True)

    p_init = sub.add_parser("init", help="Resolve a selection and seed a per-offer batch.")
    p_init.add_argument("--shortlist", required=True, help="Path to the offer shortlist JSON.")
    p_init.add_argument("--select", required=True, help="1-indexed selection string, e.g. '1,3,5' or 'all'.")
    p_init.add_argument("--batch-id", default=None, help="Override the generated batch_id.")
    p_init.add_argument("--run-id-prefix", default=None, help="Override the per-offer run_id prefix.")
    p_init.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to pipeline.config.yaml frozen into each run state.",
    )
    p_init.add_argument("--execution-mode", default=None, help="Optional CLI override for execution_mode.")
    p_init.add_argument("--retry-cap", type=int, default=None, help="Optional CLI override for retry_cap.")
    p_init.add_argument(
        "--pipeline-dir",
        default=".pipeline",
        help="Writable pipeline root (default .pipeline); resolved and used as the containment anchor.",
    )
    p_init.set_defaults(func=_cmd_init)

    p_mark = sub.add_parser(
        "mark", help="Set one per-(offer, artifact_type) run's status (read-modify-preserve)."
    )
    p_mark.add_argument("--batch", required=True, help="batch_id whose manifest to update.")
    p_mark.add_argument("--run-id", required=True, help="Exact per-artifact-type run_id to update.")
    p_mark.add_argument(
        "--status",
        required=True,
        choices=["pending", "running", "delivered", "failed"],
        help="New run status.",
    )
    p_mark.add_argument(
        "--pipeline-dir",
        default=".pipeline",
        help="Writable pipeline root (default .pipeline); resolved as the containment anchor.",
    )
    p_mark.set_defaults(func=_cmd_mark)

    p_resume = sub.add_parser(
        "resume",
        help="Print the non-delivered runs, recomputed from recorded gates (never the label).",
    )
    p_resume.add_argument("--batch", required=True, help="batch_id whose manifest to recompute.")
    p_resume.add_argument(
        "--pipeline-dir",
        default=".pipeline",
        help="Writable pipeline root (default .pipeline); resolved as the containment anchor.",
    )
    p_resume.set_defaults(func=_cmd_resume)

    p_spec = sub.add_parser(
        "record-spec",
        help="Stamp the real freeze offer_spec_path/hash into one offer entry (post-freeze).",
    )
    p_spec.add_argument("--batch", required=True, help="batch_id whose manifest to update.")
    p_spec.add_argument(
        "--offer-index", required=True, type=int, help="offer_index of the entry to stamp."
    )
    p_spec.add_argument(
        "--offer-spec-path", required=True, help="Real freeze offer_spec_path to record."
    )
    p_spec.add_argument(
        "--offer-spec-hash", required=True, help="Real freeze offer_spec_hash to record."
    )
    p_spec.add_argument(
        "--pipeline-dir",
        default=".pipeline",
        help="Writable pipeline root (default .pipeline); resolved as the containment anchor.",
    )
    p_spec.set_defaults(func=_cmd_record_spec)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
