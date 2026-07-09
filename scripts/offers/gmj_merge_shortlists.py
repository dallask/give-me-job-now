#!/usr/bin/env python3
"""Deterministic, LLM-free merge authority for parallel multi-board gmj-offer-scout (SCOUT-02/04).

Unions per-board shortlist worker outputs, dedups cross-posts by a canonical key, hard
scope-filters against ``config/sources.yaml`` (fail-closed), scores every entry with ONE
pinned pure function reading ``config/preferences.yaml`` weights, then emits a byte-identical
canonical ``.pipeline/shortlist.json`` plus a job-seeker ``.pipeline/shortlist.md`` view.

Reproducibility doctrine (SCOUT-04): all order-/dedup-/scope-/rank-critical logic lives HERE,
never in an LLM. Output is ``json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`` + a
trailing newline over a total-ordered ``sorted()`` — so identical inputs yield byte-identical
bytes even across different ``PYTHONHASHSEED`` values. ``ensure_ascii=False`` is load-bearing
for Cyrillic (ua/ru) parity (same rationale as scripts/contracts/gmj_hash_artifact.py).

Normalization, subset logic, and the slug are IMPORTED from the audited helpers
(gmj_validate_preferences.py, gmj_freeze_offer.py) — never re-derived — so host normalization stays
byte-parity with the gmj-sources-scope-guard hook.

CLI: ``gmj_merge_shortlists.py (--board-file <f> ... | --stdin) [--sources config/sources.yaml]
[--preferences config/preferences.yaml] [--out .pipeline/shortlist.json]``; exit 0 + printed
path on success, exit 1 (stderr) on error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/offers/ -> repo root
sys.path.insert(0, str(REPO_ROOT / "scripts" / "preferences"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "offers"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
from gmj_validate_preferences import _norm_site, subset_offenders, load_yaml  # noqa: E402,F401
from gmj_freeze_offer import slugify  # noqa: E402  ([a-z0-9-] slug; returns "offer" when empty)
from gmj_pipeline_paths import resolve_pipeline_dir  # noqa: E402  (single-sourced pipeline root)
from jsonschema import Draft202012Validator  # noqa: E402

SHORTLIST_SCHEMA = REPO_ROOT / "schemas" / "shortlist.schema.json"

def _reject_nan(token: str):
    """``json.loads`` ``parse_constant`` hook: refuse the non-finite JSON extensions.

    Python's ``json`` accepts the non-standard ``NaN``/``Infinity``/``-Infinity`` literals by
    default. Allowing them defeats this module's contract: they re-emit as invalid RFC-8259
    JSON and make the final ``(-score, ...)`` total order input-order-dependent (every ``NaN``
    comparison is ``False``). Reject on load so a malformed board surfaces loud (SCOUT-04).
    """
    raise ValueError(f"non-finite JSON literal not allowed: {token}")


DEFAULT_SOURCES = REPO_ROOT / "config" / "sources.yaml"
DEFAULT_PREFERENCES = REPO_ROOT / "config" / "preferences.yaml"
# The pipeline root is resolved LAZILY inside main() (mirroring gmj_batch.py / gmj_runs.py), never at
# import — so a within-process GMJ_PIPELINE_DIR change is honored at call time and the module stays
# deterministically testable. Root single-sourced via resolve_pipeline_dir()
# (explicit > GMJ_PIPELINE_DIR env > .pipeline).


def _entry_source_url(entry: dict) -> str:
    """Extract a source_url from either ``trace.source_url`` or a top-level ``source_url``.

    Guards both entry shapes: the frozen contract nests provenance under ``trace`` while
    the legacy ephemeral worker output carries ``source_url`` at the top level.
    """
    trace = entry.get("trace")
    if isinstance(trace, dict):
        url = trace.get("source_url")
        if isinstance(url, str) and url:
            return url
    url = entry.get("source_url")
    return url if isinstance(url, str) else ""


def _normalize_entry(entry: dict, origin: str) -> dict:
    """Fill a raw board entry's schema-declared gaps with safe defaults, never dropping it.

    Guard-shape-A-fall-back-to-safe-default idiom (mirrors ``_entry_source_url``): a per-board
    worker output that drifted from the canonical shape (missing ``trace``/``board``/
    ``discovered_at``) is normalized here BEFORE it reaches ``merge()``, so the deterministic
    merge authority always operates on a schema-conformant entry and the whole batch never fails
    closed over one drifted entry (PIPE-03). ``discovered_at`` is filled with an empty string,
    NEVER a freshly-computed "now" timestamp -- backfilling a fake discovery time would
    misrepresent when the entry was actually found (this is a merge-time gap-fill, not a
    re-stamp) (PIPE-04, T-41-06 accept).

    If the normalized entry has neither a non-empty ``title`` nor a non-empty ``company``, it is
    genuinely unusable for a human to act on -- still kept (never dropped), but a ``stderr``
    warning names the entry's origin/board so the gap is visible.
    """
    normalized = dict(entry)

    trace = normalized.get("trace")
    if not isinstance(trace, dict) or not isinstance(trace.get("source_url"), str) or not trace.get(
        "source_url"
    ):
        normalized["trace"] = {"source_url": _entry_source_url(entry)}

    normalized["board"] = str(normalized.get("board", ""))
    normalized["discovered_at"] = str(normalized.get("discovered_at", ""))

    title = str(normalized.get("title", "")).strip()
    company = str(normalized.get("company", "")).strip()
    if not title and not company:
        print(
            f"WARNING: unusable shortlist entry (no title/company) from {origin}: {entry!r}",
            file=sys.stderr,
        )

    return normalized


def _url_path(url: str) -> str:
    """The path/query portion of a URL after the host (mirrors ``_norm_site`` scheme handling).

    Used to keep the host-only dedup fallback discriminating: two distinct postings on one
    board that both lack company/title/location must NOT collapse to the same key.
    """
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", str(url).strip().lower())
    parts = s.split("/", 1)
    return parts[1] if len(parts) > 1 else ""


def canonical_key(entry: dict) -> str:
    """Stable dedup key: slug of company+title+location, falling back to source host + path.

    Reuses ``slugify`` (returns the sentinel ``"offer"`` for an empty composite), so the URL
    fallback fires on BOTH an empty slug and that sentinel. The fallback folds the URL path
    into the key (``host::path-slug``) so two genuinely distinct postings on the same board
    that both lack company/title/location stay distinct instead of silently deduping to one
    (WR-01 data-loss guard).
    """
    slug = slugify(
        str(entry.get("company", "")),
        str(entry.get("title", "")) + "-" + str(entry.get("location", "")),
    )
    if slug and slug != "offer":
        return slug
    url = _entry_source_url(entry)
    return f"{_norm_site(url)}::{slugify('', _url_path(url))}"


def _board_host(entry: dict) -> str:
    """Normalized host for the scope-filter: the entry's ``board``, else its source host."""
    board = entry.get("board")
    return _norm_site(board if isinstance(board, str) and board else _entry_source_url(entry))


def _num(value: object) -> float | None:
    """Coerce a bool-free numeric to float, else None (missing sub-signals default to 0)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _entry_salary(entry: dict) -> float | None:
    """Best-effort numeric salary from an entry (``salary``, ``salary_min``, or range.min)."""
    for key in ("salary", "salary_min"):
        val = _num(entry.get(key))
        if val is not None:
            return val
    rng = entry.get("salary_range")
    if isinstance(rng, dict):
        return _num(rng.get("min"))
    return None


def score_entry(entry: dict, prefs: dict) -> float:
    """ONE pinned pure soft-rank function (SCOUT-02) — never an LLM.

    Combines a salary-fit sub-score (entry salary vs ``preferences.salary.min``, clamped 0..1),
    a work-mode-fit sub-score (entry ``mode`` in ``preferences.work_conditions.mode`` → 1 else
    0), and a keyword-overlap fraction (entry text vs ``preferences.search_keywords``), weighted
    by ``preferences.ranking.salary_weight`` and ``remote_weight``. Missing sub-signals
    contribute 0 (never invented). Keeping the whole formula in this single function lets the
    determinism test pin it.
    """
    ranking = prefs.get("ranking") if isinstance(prefs.get("ranking"), dict) else {}
    salary_weight = _num(ranking.get("salary_weight")) or 0.0
    remote_weight = _num(ranking.get("remote_weight")) or 0.0

    # salary-fit sub-score (0..1).
    salary_cfg = prefs.get("salary") if isinstance(prefs.get("salary"), dict) else {}
    salary_min = _num(salary_cfg.get("min"))
    entry_salary = _entry_salary(entry)
    if salary_min and salary_min > 0 and entry_salary is not None:
        salary_fit = max(0.0, min(1.0, entry_salary / salary_min))
    else:
        salary_fit = 0.0

    # work-mode-fit sub-score (0 or 1).
    wc = prefs.get("work_conditions") if isinstance(prefs.get("work_conditions"), dict) else {}
    modes = {str(m).strip().lower() for m in (wc.get("mode") or [])}
    entry_mode = str(entry.get("mode", "")).strip().lower()
    mode_fit = 1.0 if entry_mode and entry_mode in modes else 0.0

    # keyword-overlap fraction (0..1).
    keywords = [str(k).strip().lower() for k in (prefs.get("search_keywords") or []) if str(k).strip()]
    if keywords:
        text = " ".join(
            str(entry.get(field, ""))
            for field in ("title", "company", "location", "seniority", "description", "raw_text_excerpt")
        ).lower()
        overlap = sum(1 for kw in keywords if kw in text)
        keyword_fraction = overlap / len(keywords)
    else:
        keyword_fraction = 0.0

    return salary_weight * salary_fit + remote_weight * mode_fit + keyword_fraction


def merge(board_entries: list[dict], prefs: dict, sources: dict) -> list[dict]:
    """Scope-filter → dedup → total-order sort. The deterministic authority (SCOUT-02/04).

    Hard scope-filter FIRST (drop any entry whose board host is not in the normalized
    sources.yaml ``sites`` set; a missing/empty set drops all — fail-closed, never "all
    allowed"). Then union into a dict keyed by ``canonical_key`` keeping the best-scoring /
    lower-board representative. Finally return a ``(-score, canonical_key)`` total-ordered list
    — NEVER emitted from dict/set iteration order (PYTHONHASHSEED-independent).
    """
    allow_sites = {_norm_site(s) for s in (sources.get("sites") or [])}

    groups: dict[str, dict] = {}
    for entry in board_entries:
        if _board_host(entry) not in allow_sites:  # fail-closed: empty allow_sites drops all
            continue
        key = canonical_key(entry)
        scored = {**entry, "canonical_key": key, "score": score_entry(entry, prefs)}
        cur = groups.get(key)
        if cur is None or (scored["score"], cur.get("board", "")) > (
            cur["score"],
            scored.get("board", ""),
        ):
            groups[key] = scored

    return sorted(groups.values(), key=lambda e: (-e["score"], e["canonical_key"]))


def render_md(ranked: list[dict]) -> str:
    """Deterministic job-seeker ``.md`` view (SCOUT-01) — no recruiter framing.

    Header/labels are candidate-perspective ("Matching vacancies for you"); the string
    "candidate" never appears so the SCOUT-01 wording check is assertable.
    """
    lines = [
        "# Matching vacancies for you",
        "",
        f"{len(ranked)} matching vacancies for you, ranked by fit.",
        "",
    ]
    for idx, entry in enumerate(ranked, start=1):
        title = str(entry.get("title", entry.get("canonical_key", "")))
        company = str(entry.get("company", ""))
        location = str(entry.get("location", ""))
        board = str(entry.get("board", ""))
        score = entry.get("score", 0.0)
        source_url = _entry_source_url(entry)
        lines.append(f"## {idx}. {title}")
        if company:
            lines.append(f"- Role: {title} at {company}")
        if location:
            lines.append(f"- Location: {location}")
        lines.append(f"- Board: {board}")
        lines.append(f"- Fit score: {float(score):.4f}")
        if source_url:
            lines.append(f"- Link: {source_url}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _validate_against_schema(doc: dict) -> None:
    """Validate the assembled shortlist against ``schemas/shortlist.schema.json``, fail closed.

    The schema is the frozen contract Phase 12 consumes: every entry MUST carry
    ``canonical_key``, ``board``, ``score``, and ``trace.source_url``. An entry that arrived
    in the legacy top-level-``source_url`` shape (no ``trace``/``board``) would otherwise be
    emitted verbatim and silently break the contract. Raise ``ValueError`` (caught in ``main``
    → exit 1) so a non-conforming assembly never lands on disk (WR-02).
    """
    schema = json.loads(SHORTLIST_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        loc = "/".join(map(str, first.absolute_path)) or "<root>"
        raise ValueError(
            f"assembled shortlist violates shortlist.schema.json at {loc}: {first.message}"
        )


def write_shortlist(ranked: list[dict], out: Path, pipeline_dir: Path) -> Path:
    """Write the canonical byte-identical JSON + sibling job-seeker ``.md`` under the pipeline root.

    Asserts the resolved output path stays under ``pipeline_dir`` before writing (path-traversal
    defence in depth, mirrors gmj_freeze_offer.py containment). ``pipeline_dir`` is resolved FRESH at
    the call site (never a frozen import-time constant), so a relative-vs-absolute or env change is
    honored at write time.
    """
    resolved = out.expanduser().resolve()
    base = pipeline_dir.expanduser().resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Refusing to write outside {base}: {resolved}")

    resolved.parent.mkdir(parents=True, exist_ok=True)
    doc = {"kind": "offer_shortlist", "schema_version": "1.0", "shortlist": ranked}
    _validate_against_schema(doc)
    resolved.write_text(
        # allow_nan=False: a stray non-finite value fails loud, never corrupts the artifact
        # into invalid RFC-8259 JSON (mirrors the _reject_nan load guard) (SCOUT-04).
        json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    md_path = resolved.with_suffix(".md")
    md_path.write_text(render_md(ranked), encoding="utf-8")
    return resolved


def _entries_from_doc(doc: object, origin: str) -> list[dict]:
    """Extract the entry list from a loaded board document, normalizing each entry.

    Accepts BOTH the wrapped ``{..., "shortlist": [<entry>, ...]}`` document that the real
    gmj-offer-scout per-board worker emits (and that shortlist.sample.json is) AND a bare JSON list
    of entry objects. Any other top-level type is an error. Every dict entry is passed through
    ``_normalize_entry()`` (fills schema-declared gaps with safe defaults, never drops) here --
    BEFORE entries reach ``merge()`` -- so ``merge()``'s ``canonical_key``/``score`` computation
    always operates on a normalized entry, with ``origin`` available for the unusable-entry
    warning (PIPE-03/04).
    """
    if isinstance(doc, list):
        entries = doc
    elif isinstance(doc, dict):
        entries = doc.get("shortlist", [])
    else:
        raise ValueError(f"{origin}: top-level JSON must be a list or an object with 'shortlist'")
    if not isinstance(entries, list):
        raise ValueError(f"{origin}: 'shortlist' must be a JSON array")
    return [_normalize_entry(e, origin) for e in entries if isinstance(e, dict)]


def load_board_entries(board_files: list[Path] | None, use_stdin: bool) -> list[dict]:
    """Load and concatenate board entries from ``--board-file`` paths or ``--stdin``."""
    entries: list[dict] = []
    if use_stdin:
        doc = json.loads(sys.stdin.read(), parse_constant=_reject_nan)
        entries.extend(_entries_from_doc(doc, "<stdin>"))
        return entries
    for path in board_files or []:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Not a file: {resolved}")
        doc = json.loads(resolved.read_text(encoding="utf-8"), parse_constant=_reject_nan)
        entries.extend(_entries_from_doc(doc, str(resolved)))
    return entries


def main() -> int:
    # Resolve the pipeline root LAZILY (mirrors gmj_batch.py / gmj_runs.py) at parser-construction
    # time — AFTER any parent has stamped GMJ_PIPELINE_DIR into the child env — never at import.
    pipeline_root = Path(resolve_pipeline_dir())
    default_out = pipeline_root / "shortlist.json"
    parser = argparse.ArgumentParser(
        description="Deterministically merge/dedup/scope-filter/rank per-board shortlists."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--board-file",
        type=Path,
        action="append",
        help="A per-board shortlist JSON (repeatable). Wrapped {...,'shortlist':[...]} or a bare list.",
    )
    source.add_argument("--stdin", action="store_true", help="Read one board bundle from stdin.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES, help="sources.yaml allow-list.")
    parser.add_argument(
        "--preferences", type=Path, default=DEFAULT_PREFERENCES, help="preferences.yaml ranking signals."
    )
    parser.add_argument("--out", type=Path, default=default_out, help="Output shortlist JSON path.")
    args = parser.parse_args()

    # Load board entries.
    try:
        board_entries = load_board_entries(args.board_file, args.stdin)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid board input: {exc}", file=sys.stderr)
        return 1

    # Load preferences (soft-rank signals). Absent → empty (scores degrade to 0); unparsable → exit 1.
    prefs: dict = {}
    prefs_path = args.preferences.expanduser().resolve()
    if prefs_path.is_file():
        try:
            prefs = load_yaml(prefs_path)
        except Exception as exc:  # noqa: BLE001  fail-soft: ranking signals only
            print(f"Unparsable preferences.yaml: {exc}", file=sys.stderr)
            return 1

    # Load sources allow-list. FAIL-CLOSED: missing/unparsable => empty scope => drop all.
    sources: dict = {}
    sources_path = args.sources.expanduser().resolve()
    if sources_path.is_file():
        try:
            sources = load_yaml(sources_path)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL-CLOSED: unparsable sources.yaml: {exc}", file=sys.stderr)
            return 1
    else:
        # A MISSING allow-list is a misconfiguration, not "no matches": exit non-zero so an
        # operator/orchestrator can tell "scope config missing" from a legitimate empty run
        # (mirrors gmj_validate_preferences.py's missing-sources fail-closed) (WR-06).
        print(
            f"FAIL-CLOSED: sources.yaml not found: {sources_path} "
            "(a missing allow-list means no scope is defined, never all-allowed)",
            file=sys.stderr,
        )
        return 1

    ranked = merge(board_entries, prefs, sources)

    try:
        written = write_shortlist(ranked, args.out, pipeline_root)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
