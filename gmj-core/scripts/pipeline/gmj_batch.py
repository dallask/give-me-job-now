#!/usr/bin/env python3
"""Deterministic per-offer batch control-plane CLI (SELECT-01, SELECT-02, SELECT-03).

Pure files + stdout: this script holds NO ``Task``, no network, no LLM, and re-judges NO
gate/cap/delivery. It is the single producer of the per-(offer, artifact_type) run states and
the batch manifest; the ``/gmj-batch`` hub persona (12-03) drives the spokes, and the resume
path (12-02) extends this module with ``mark``/``resume`` ops.

Subcommand implemented here: ``init``.

    init --shortlist <path> --select "1,3,5" [--batch-id <id>] [--run-id-prefix <p>]
         [--config <path>] [--execution-mode ...] [--retry-cap N] [--max-parallel-offers N]
         [--pipeline-dir <dir>]

For each selected shortlist entry it:
  1. resolves the 1-indexed selection string to sorted, deduped, bounds-checked 0-based indices
     (SELECT-01),
  2. maps the coarse shortlist entry to a freeze-draft copying only the offer_content schema
     fields (title/company/location/seniority/language + trace.source_url->source_url,
     trace.excerpt->raw_text_excerpt) and dropping every non-schema key; flags ``thin`` when
     ``must_haves`` is absent/empty OR the excerpt is missing (SELECT-02),
  3. derives three per-(offer, artifact_type) run_ids ``<run_id>-cv``/``-cl``/``-ip``, freezes each
     via the existing ``gmj_state_write.py`` and seeds ``current_step: gmj-artifact-composer`` (gmj_route.py
     raises without it) — three distinct seeded ``state.json`` per offer, none at the bare run_id
     (SELECT-03),
  4. writes an offer-centric canonical manifest validated against
     ``schemas/batch_manifest.schema.json`` under ``<pipeline-dir>/batches/<batch_id>/``.

All error paths print a structured stderr message and ``return 1`` — never a traceback. Ids are
sanitized to ``^[A-Za-z0-9._-]+$`` (rejecting ``.``/``..``/``/``/``\\``) before they can become a
run-dir path component (T-12-01, V12 path-traversal); the manifest write is additionally
contained under the resolved batches dir (defence in depth, mirrors gmj_freeze_offer.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

# Reuse the audited Gate A ∧ Gate B delivery predicate verbatim — never re-judge a gate here
# (Pitfall 2 / T-12-04). gmj_check_delivery.py lives in this same scripts/pipeline dir, which is on
# sys.path both when this file is run as a script and when imported via a sys.path insert (tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_check_delivery import blocked_reason  # noqa: E402

# Reuse gmj_state_write.py's frozen-run-config helper IN-PROCESS (not via subprocess) so the seeded
# state is built and written once already containing current_step — no non-atomic window where
# gmj_route.py could observe a state without current_step (WR-02). It freezes the exact same fields
# (execution_mode, retry_cap, run_id) and prints its own structured stderr on any error.
from gmj_state_write import _freeze_run_config  # noqa: E402
from gmj_pipeline_paths import resolve_pipeline_dir  # noqa: E402  (single-sourced pipeline root)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root
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


def _reject_nan(token: str) -> float:
    """``json.loads`` ``parse_constant`` hook: refuse the non-finite JSON extensions.

    Python's ``json`` accepts the non-standard ``NaN``/``Infinity``/``-Infinity`` literals by
    default. A coarse->draft copies numeric-capable offer_content fields (e.g. ``salary_range``)
    and the draft is re-emitted with ``allow_nan=False``, so a non-finite number would otherwise
    reach an UNCAUGHT ``ValueError`` on write (a traceback, violating this module's contract).
    Reject on load instead so every malformed document fails closed with a clear stderr message
    and ``return 1`` — mirrors the Phase-11 hardening in ``gmj_merge_shortlists.py`` (WR-01).
    """
    raise ValueError(f"non-finite JSON literal not allowed: {token}")


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
    re-fields it via gmj-offer-scout single-offer intake. Thin whenever ``must_haves`` is absent/empty
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
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"), parse_constant=_reject_nan)
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
    ``batch_id`` cannot escape (defence in depth on top of ``_safe_id``; mirrors gmj_freeze_offer.py).
    """
    resolved = out.expanduser().resolve()
    base = batches_dir.expanduser().resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Refusing to write outside {base}: {resolved}")
    _validate_manifest(manifest)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    # Atomic publish: write a temp sibling then rename over the target (mirrors _seed_state's
    # tmp_path.replace(state_path) idiom) — a reader can never observe a partially-written
    # manifest.json (T-35-03).
    tmp_path = resolved.with_name(resolved.name + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(resolved)
    return resolved


def _seed_state(
    run_id: str, runs_dir: Path, config: Path, execution_mode: str | None, retry_cap: int | None
) -> int:
    """Build the frozen+seeded state IN-PROCESS and publish it in a single atomic write.

    Reuses ``state_write._freeze_run_config`` to freeze the exact same fields gmj_state_write.py
    records (execution_mode, retry_cap, run_id), sets ``current_step`` on the in-memory dict
    BEFORE writing, then publishes via a temp-file rename. There is therefore never a moment
    where ``state.json`` exists on disk without ``current_step`` (gmj_route.py:33-34) — closing the
    non-atomic double-write window and removing the per-state subprocess spawn (WR-02).

    Returns 0 on success, 1 after a structured stderr message on any failure.
    """
    state_path = runs_dir / run_id / "state.json"
    state: dict = {}
    freeze_args = argparse.Namespace(
        run_id=run_id,
        config=Path(config),
        execution_mode=execution_mode,
        retry_cap=retry_cap,
    )
    # _freeze_run_config prints its own structured stderr message and returns 1 on any error
    # (bad run_id charset, missing/invalid config, bad execution_mode/retry_cap).
    if _freeze_run_config(state, freeze_args) != 0:
        return 1
    # Seed current_step into the in-memory dict BEFORE the single write.
    state["current_step"] = "gmj-artifact-composer"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    # Atomic publish: write a temp sibling then rename over the target (no partial/no-current_step
    # state is ever visible to a concurrent gmj_route.py read).
    tmp_path = state_path.with_name(state_path.name + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(state_path)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    batches_dir = pipeline_dir / "batches"
    runs_dir = pipeline_dir / "runs"

    # Resolve + validate max_parallel_offers BEFORE any disk write (CONC-01): a CLI override
    # wins over config/pipeline.config.yaml's value, defaulting to 3 when neither is set. The
    # isinstance(int) and not bool guard + the >= 1 bound mirror gmj_state_write.py's
    # _freeze_run_config retry_cap guard exactly (T-35-02), except the bound here is < 1 (not
    # < 0) since zero concurrent offers is nonsensical.
    config_path = Path(args.config).expanduser()
    if not config_path.is_file():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"Invalid pipeline config YAML: {exc}", file=sys.stderr)
        return 1
    if not isinstance(cfg, dict):
        print("Pipeline config YAML must parse to a mapping.", file=sys.stderr)
        return 1
    max_parallel_offers = (
        args.max_parallel_offers
        if args.max_parallel_offers is not None
        else cfg.get("max_parallel_offers", 3)
    )
    if not isinstance(max_parallel_offers, int) or isinstance(max_parallel_offers, bool):
        print("max_parallel_offers must be an integer (not a bool).", file=sys.stderr)
        return 1
    if max_parallel_offers < 1:
        print("max_parallel_offers must be >= 1.", file=sys.stderr)
        return 1

    # Load the shortlist (fail-closed: is_file -> json -> isinstance guard).
    shortlist_path = Path(args.shortlist).expanduser()
    if not shortlist_path.is_file():
        print(f"Shortlist not found: {shortlist_path}", file=sys.stderr)
        return 1
    try:
        doc = json.loads(shortlist_path.read_text(encoding="utf-8"), parse_constant=_reject_nan)
    except ValueError as exc:  # JSONDecodeError subclasses ValueError; also catches _reject_nan
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
                    "cv": {"run_id": per_type["cv"], "status": "waiting"},
                    "cover_letter": {"run_id": per_type["cl"], "status": "waiting"},
                    "interview_prep": {"run_id": per_type["ip"], "status": "waiting"},
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
        "max_parallel_offers": max_parallel_offers,
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
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), parse_constant=_reject_nan)
    except ValueError as exc:  # JSONDecodeError subclasses ValueError; also catches _reject_nan
        print(f"Invalid manifest JSON: {exc}", file=sys.stderr)
        return None, manifest_path, batches_dir
    if not isinstance(manifest, dict):
        print("Manifest file must contain a JSON object.", file=sys.stderr)
        return None, manifest_path, batches_dir
    return manifest, manifest_path, batches_dir


def _mutate_manifest_with_retry(
    pipeline_dir: Path, batch_id: str, apply_fn, max_attempts: int = 5
) -> int:
    """Optimistic-concurrency read-modify-write against ``manifest.json`` (CONC-03).

    Performs up to ``max_attempts`` cycles of: load a FRESH manifest (a fresh
    ``_load_manifest`` call, giving the current ``manifest_path``/``batches_dir``), snapshot its
    on-disk bytes, call ``apply_fn(manifest)`` (mutates the in-memory dict in place), then
    re-read the on-disk bytes and compare to the snapshot. If DIFFERENT — another writer landed
    in between this call's read and its own write — ``continue`` to the next attempt, which
    re-loads the now-current content and re-applies ``apply_fn`` on top of it. If SAME, publish
    via ``write_manifest`` (atomic temp+replace) and return 0.

    A ``ValueError`` from ``write_manifest`` (a genuine schema violation, not a concurrency
    conflict) is NOT caught here — it propagates uncaught so the caller's existing
    ``except ValueError`` handles it exactly as before. Exhausting ``max_attempts`` prints a
    structured stderr message and returns 1 — never a silent partial write.
    """
    for _attempt in range(max_attempts):
        manifest, manifest_path, batches_dir = _load_manifest(pipeline_dir, batch_id)
        if manifest is None:
            # _load_manifest already printed a structured stderr message.
            return 1
        before = manifest_path.read_bytes()
        apply_fn(manifest)
        after = manifest_path.read_bytes()
        if after != before:
            continue  # another writer landed in between this read and our write; retry fresh
        write_manifest(manifest, manifest_path, batches_dir)
        return 0
    print(
        f"Manifest write error: exhausted {max_attempts} retry attempts due to concurrent writers",
        file=sys.stderr,
    )
    return 1


def _cmd_mark(args: argparse.Namespace) -> int:
    """Set exactly one per-(offer, artifact_type) run's status (read-modify-preserve, canonical)."""
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    if _safe_id(args.batch, "batch_id") is None:
        return 1
    manifest, _manifest_path, _batches_dir = _load_manifest(pipeline_dir, args.batch)
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

    run_id = args.run_id
    status = args.status

    def _apply(m: dict) -> None:
        for offer in m.get("offers", []):
            for run in (offer.get("runs") or {}).values():
                if isinstance(run, dict) and run.get("run_id") == run_id:
                    run["status"] = status
                    return
        # Defensive only: run_ids are never removed by another process in this codebase.
        raise LookupError(run_id)

    try:
        rc = _mutate_manifest_with_retry(pipeline_dir, args.batch, _apply)
    except LookupError:
        print(f"run_id not found in batch {args.batch!r}: {args.run_id!r}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Manifest write error: {exc}", file=sys.stderr)
        return 1
    if rc != 0:
        return rc
    print(f"marked run_id={args.run_id} status={args.status}")
    return 0


def _cmd_record_spec(args: argparse.Namespace) -> int:
    """Stamp the real freeze offer_spec_path/hash into one offer entry (read-modify-preserve)."""
    pipeline_dir = Path(args.pipeline_dir).expanduser().resolve()
    if _safe_id(args.batch, "batch_id") is None:
        return 1
    manifest, _manifest_path, _batches_dir = _load_manifest(pipeline_dir, args.batch)
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

    offer_index = args.offer_index
    offer_spec_path = args.offer_spec_path
    offer_spec_hash = args.offer_spec_hash

    def _apply(m: dict) -> None:
        for offer in m.get("offers", []):
            if offer.get("offer_index") == offer_index:
                offer["offer_spec_path"] = offer_spec_path
                offer["offer_spec_hash"] = offer_spec_hash
                return
        # Defensive only: offer_index entries are never removed by another process.
        raise LookupError(offer_index)

    try:
        rc = _mutate_manifest_with_retry(pipeline_dir, args.batch, _apply)
    except LookupError:
        print(
            f"offer_index not found in batch {args.batch!r}: {args.offer_index}", file=sys.stderr
        )
        return 1
    except ValueError as exc:
        print(f"Manifest write error: {exc}", file=sys.stderr)
        return 1
    if rc != 0:
        return rc
    print(f"recorded offer_index={args.offer_index} offer_spec_hash={args.offer_spec_hash}")
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    """Print the non-delivered per-(offer, artifact_type) runs (label-AND-gate, SELECT-04).

    A run counts as delivered ONLY when BOTH hold: (1) its manifest ``status`` label is
    ``"delivered"`` — set by the ``/gmj-batch`` persona via ``mark`` ONLY after the terminal
    ``gmj-cv-generator`` render+delivery completes, so the label is the render-complete signal
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
                    state = json.loads(
                        state_path.read_text(encoding="utf-8"), parse_constant=_reject_nan
                    )
                except ValueError as exc:  # JSONDecodeError subclasses ValueError; also _reject_nan
                    print(f"Invalid state JSON at {state_path}: {exc}", file=sys.stderr)
                    return 1
                if isinstance(state, dict) and isinstance(state.get("gate_results"), dict):
                    gate_results = state["gate_results"]
            # Delivered ONLY when the terminal gmj-cv-generator render+delivery completed — the
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
        "--max-parallel-offers",
        type=int,
        default=None,
        help="Optional CLI override for max_parallel_offers (frozen into manifest.json, CONC-01).",
    )
    p_init.add_argument(
        "--pipeline-dir",
        default=resolve_pipeline_dir(),
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
        choices=["waiting", "in_flight", "delivered", "gate_exhausted", "error"],
        help="New run status.",
    )
    p_mark.add_argument(
        "--pipeline-dir",
        default=resolve_pipeline_dir(),
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
        default=resolve_pipeline_dir(),
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
        default=resolve_pipeline_dir(),
        help="Writable pipeline root (default .pipeline); resolved as the containment anchor.",
    )
    p_spec.set_defaults(func=_cmd_record_spec)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
