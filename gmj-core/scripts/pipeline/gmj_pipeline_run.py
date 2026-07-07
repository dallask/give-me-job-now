#!/usr/bin/env python3
"""Deterministic single-offer artifact-type resolver + run_id deriver (ARTF-03).

Groundwork for the single-offer `/gmj-pipeline-run` path's default artifact-set expansion
(ARTF-01/ARTF-04, wired in later 32-xx plans). Per 32-RESEARCH.md Pitfall 1, this MUST be a
small deterministic script — not hub-persona prose alone — so the per-artifact-type isolation
guarantee is structurally enforced and testable, mirroring `gmj_batch.py`'s already-proven
`ARTIFACT_TYPES` + `_safe_id` + validate-fully-before-any-write pattern exactly.

This script holds NO ``Task``, no network, no LLM, and re-judges NO gate — it only validates an
operator's ``--artifact-types`` narrowing flag against the canonical 3-item enum and derives the
per-type run_ids (``<run_id>-cv``/``-cl``/``-ip``) the hub then uses to seed/dispatch per type.

Reuses ``ARTIFACT_TYPES`` and ``_safe_id`` from ``gmj_batch.py`` verbatim — this file declares no
new copy of the artifact-type enum (already duplicated 3x elsewhere in-repo per 32-RESEARCH.md's
"Don't Hand-Roll" table).

CLI: ``gmj_pipeline_run.py --run-id <id> [--artifact-types cv,cover_letter,interview_prep]``
prints one ``<key>=<derived_run_id>`` line per requested type (canonical ``ARTIFACT_TYPES`` order)
and exits 0, or hard-fails (exit 1, no partial stdout) on any invalid ``--artifact-types`` token,
an empty resolved list, or an unsafe ``--run-id``/derived id.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reuse the audited artifact-type enum + safe-id charset check verbatim — never re-declare a 4th
# copy of the 3-item (cv, cover_letter, interview_prep) enum (32-RESEARCH.md "Don't Hand-Roll").
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_batch import ARTIFACT_TYPES, _safe_id  # noqa: E402

_VALID_KEYS = tuple(key for key, _suffix in ARTIFACT_TYPES)
_DEFAULT_ARTIFACT_TYPES = ",".join(_VALID_KEYS)


def resolve_artifact_types(raw: str) -> list[tuple[str, str]] | None:
    """Validate + resolve a comma-list ``--artifact-types`` value against ``ARTIFACT_TYPES``.

    Returns the matching ``(key, suffix)`` pairs in ``ARTIFACT_TYPES``'s own canonical order
    (never the caller's input order), restricted to the requested subset. Returns ``None`` (after
    printing a structured stderr message) when the filtered token list is empty, or when any token
    is not one of ``ARTIFACT_TYPES``'s keys — naming every invalid token plus the sorted valid set.
    """
    tokens = [tok.strip() for tok in raw.split(",")]
    tokens = [tok for tok in tokens if tok]
    if not tokens:
        print(
            f"--artifact-types resolved to no types; valid set: {sorted(_VALID_KEYS)}",
            file=sys.stderr,
        )
        return None

    invalid = sorted({tok for tok in tokens if tok not in _VALID_KEYS})
    if invalid:
        print(
            f"Invalid --artifact-types value(s): {invalid}; valid set: {sorted(_VALID_KEYS)}",
            file=sys.stderr,
        )
        return None

    requested = set(tokens)
    return [(key, suffix) for key, suffix in ARTIFACT_TYPES if key in requested]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a single-offer --artifact-types narrowing flag and derive the "
            "per-(artifact_type) run_ids (ARTF-03)."
        )
    )
    parser.add_argument("--run-id", required=True, help="Base run_id for this single-offer run.")
    parser.add_argument(
        "--artifact-types",
        default=_DEFAULT_ARTIFACT_TYPES,
        help=(
            "Comma-separated subset of the artifact types to produce "
            f"(default: all {_DEFAULT_ARTIFACT_TYPES})."
        ),
    )
    args = parser.parse_args()

    if _safe_id(args.run_id, "run_id") is None:
        return 1

    resolved = resolve_artifact_types(args.artifact_types)
    if resolved is None:
        return 1

    # Pre-validate EVERY derived id before printing anything (mirrors gmj_batch.py's
    # pre-validate-every-id-before-any-write discipline) — no partial stdout on an unsafe id.
    derived_ids: list[tuple[str, str]] = []
    for key, suffix in resolved:
        derived_id = f"{args.run_id}-{suffix}"
        if _safe_id(derived_id, "run_id") is None:
            return 1
        derived_ids.append((key, derived_id))

    for key, derived_id in derived_ids:
        print(f"{key}={derived_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
