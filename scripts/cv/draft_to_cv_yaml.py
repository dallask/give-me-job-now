#!/usr/bin/env python3
"""Span-driven bridge: reconstruct an approved artifact_draft into CV-YAML (E2E-02).

This is the *write-side inverse* of ``scripts/artifacts/yaml_path.resolve_path``.
Where ``resolve_path`` walks a dotted/indexed ``source_span`` to *read* a value out
of ``candidate.yaml``, this module walks the same span to *write* each approved
claim's ``text`` into a fresh CV-YAML tree that ``scripts/cv/render_cv.py`` consumes
(Pitfall 2: the artifact_draft claims shape is NOT the CV-YAML shape).

No-invention guarantee (core value / threat T-08-04): every scalar leaf written into
the CV-YAML comes ONLY from a ``claim.text`` value that already passed Gate A. This
bridge NEVER opens or reads ``config/candidate.yaml`` (Anti-Pattern #1, Assumption
A1). List indices in a ``source_span`` are SOURCE (candidate.yaml) positions and are
legitimately sparse for a targeted CV that cherry-picks non-adjacent items (e.g.
``expertise[0].skills[0,1,9,4,7]``). Each parent list's source indices are
COMPACTED to contiguous output slots by order of first appearance — gaps are removed,
never filled with placeholders (no phantom-null padding). The no-invention guarantee is
preserved because only ``claim.text`` is ever written as a leaf; compaction reshapes
positions, it never synthesizes content. A source index seen twice maps to the same
output slot, making the reconstruction deterministic.

Complete headers, no candidate.yaml read (SCHEMA-03/04): a rendered CV needs
STRUCTURAL/HEADER fields (``name``, ``title``, ``professional_experience[i].company``,
``...position``, ``expertise[j].resume_title``) as well as the leaf content. The
composer emits those as ordinary claims traced to real spans, so this bridge assembles
a COMPLETE header-bearing CV-YAML from the draft alone — it is field-agnostic and writes
whatever span it is handed (a scalar span such as ``name``/``title`` lands at the CV-YAML
root; a nested span such as ``professional_experience[0].company`` lands in place). It
still never opens ``config/candidate.yaml``: every header value, like every leaf, is a
span-traced ``claim.text`` that already passed Gate A. This is the LOCKED fix for the
bridge-draft seam defect (repo memory ``pipeline-draft-bridge-defect``): the composer
supplies header claims rather than the bridge inventing them from the master profile.

Grammar ownership (anti-drift T-04-05 / T-08-01): the segment grammar is imported as
``SEGMENT`` from ``scripts/artifacts/yaml_path.py`` — the single owner. No second
regex is declared here. ``set_path`` reuses the read-side strictness: ``fullmatch``
each segment, walk dict-key + non-negative ``[int]`` list indices only — never
attribute-set, never a negative index, never path traversal.

Run:  python3 scripts/cv/draft_to_cv_yaml.py --file <draft.json> --out <cv.yaml>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# Single grammar owner — import, never re-declare (anti-drift T-04-05 / T-08-01).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "artifacts"))
from yaml_path import SEGMENT  # noqa: E402


def _steps(dotted: str) -> list[tuple[str, object]]:
    """Flatten a dotted/indexed span into an ordered list of walk steps.

    Each step is ``("key", name)`` or ``("idx", int)``. A segment failing
    ``SEGMENT.fullmatch`` raises KeyError (mirrors yaml_path.py:34-35). Only
    non-negative integer indices are producible (``\\[\\d+\\]`` — no sign).
    """
    steps: list[tuple[str, object]] = []
    for segment in dotted.split("."):
        match = SEGMENT.fullmatch(segment)
        if not match:
            raise KeyError(f"unparseable provenance segment: {segment!r}")
        name, indices = match.group(1), match.group(2)
        steps.append(("key", name))
        for idx in re.findall(r"\[(\d+)\]", indices):
            steps.append(("idx", int(idx)))
    return steps


def _descend(container: object, kind: str, ref: object, next_kind: str) -> object:
    """Navigate one intermediate step, creating a child container if absent.

    The child container type is dictated by the *next* step: a ``dict`` when the
    next step is a dict-key, a ``list`` when it is a list index. ``ref`` here is an
    already-COMPACTED output index (see ``set_path``), so it is contiguous by
    construction — either an existing slot (``ref < len``) or exactly the next one
    (``ref == len``). The ``ref > len`` IndexError therefore remains only as
    defense-in-depth; no phantom-null padding is ever produced (no-invention, T-08-04).
    """
    child_factory = dict if next_kind == "key" else list
    if kind == "key":
        if not isinstance(container, dict):
            raise TypeError(f"expected a mapping to hold key {ref!r}")
        if ref not in container:
            container[ref] = child_factory()
        return container[ref]
    # kind == "idx"
    if not isinstance(container, list):
        raise TypeError(f"expected a list to hold index {ref!r}")
    i = int(ref)
    if i < len(container):
        return container[i]
    if i == len(container):
        container.append(child_factory())
        return container[i]
    raise IndexError(f"list index {i} out of range (len {len(container)})")


def _assign(container: object, kind: str, ref: object, value: object) -> None:
    """Write ``value`` at the final step (dict key or contiguous list index)."""
    if kind == "key":
        if not isinstance(container, dict):
            raise TypeError(f"expected a mapping to hold key {ref!r}")
        container[ref] = value
        return
    # kind == "idx"
    if not isinstance(container, list):
        raise TypeError(f"expected a list to hold index {ref!r}")
    i = int(ref)
    if i < len(container):
        container[i] = value
    elif i == len(container):
        container.append(value)
    else:
        raise IndexError(f"list index {i} out of range (len {len(container)})")


def set_path(tree: dict, dotted: str, value: object, compaction: dict) -> None:
    """Write ``value`` into ``tree`` at the CV-YAML path named by ``dotted``.

    Strict write-side inverse of ``yaml_path.resolve_path``: unparseable segments
    raise KeyError; type mismatches raise TypeError. Never invents an intermediate
    leaf and never pads a list with None.

    List-index steps carry SOURCE (candidate.yaml) positions, which are legitimately
    sparse for a targeted CV. Each parent list's source indices are COMPACTED to
    contiguous output slots by order of first appearance via the shared ``compaction``
    map: a dict keyed by the SOURCE-index span prefix identifying each list, whose
    value is an ordered ``{source_idx: output_idx}`` slot map. Keying by the source
    prefix keeps ``expertise[0].skills``, ``expertise[1].skills``,
    and ``expertise[3].skills`` three DISTINCT lists compacted independently,
    while the top-level ``expertise`` element indices ``[0,1,3]`` compact to
    ``[0,1,2]``. The same ``compaction`` map is threaded across every claim in a draft
    so a repeated source index always maps to the same output slot (deterministic).
    Compaction only removes gaps; it never fills one (no phantom padding, T-08-04).
    """
    steps = _steps(dotted)
    if not steps:
        raise KeyError(f"empty provenance path: {dotted!r}")
    container: object = tree
    last = len(steps) - 1
    source_prefix = ""  # reproduces the original span up to (not incl.) the current token
    for i, (kind, ref) in enumerate(steps):
        next_kind = steps[i + 1][0] if i < last else None
        if kind == "key":
            if i == last:
                _assign(container, "key", ref, value)
            else:
                container = _descend(container, "key", ref, next_kind)
            source_prefix = f"{source_prefix}.{ref}" if source_prefix else str(ref)
        else:  # kind == "idx" — compact SOURCE index -> contiguous OUTPUT slot
            source_idx = int(ref)
            slot_map = compaction.setdefault(source_prefix, {})
            if source_idx not in slot_map:
                slot_map[source_idx] = len(slot_map)
            out_idx = slot_map[source_idx]
            if i == last:
                _assign(container, "idx", out_idx, value)
            else:
                container = _descend(container, "idx", out_idx, next_kind)
            source_prefix = f"{source_prefix}[{source_idx}]"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Span-driven bridge: reconstruct an approved cv artifact_draft "
        "into a render_cv.py-consumable CV-YAML by writing each claim.text at the "
        "path named by its source_span. Zero invented content; any unsafe/out-of-"
        "range span exits 1."
    )
    parser.add_argument(
        "--file",
        "--draft",
        dest="file",
        type=Path,
        required=True,
        help="Approved artifact_draft JSON (Gate A+B passed).",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Target CV-YAML path to write."
    )
    args = parser.parse_args()

    # Degrade-without-traceback (copied in spirit from check_truth.py:176-199).
    draft_path = args.file.expanduser().resolve()
    if not draft_path.is_file():
        print(f"Not a file: {draft_path}", file=sys.stderr)
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
    if "claims" not in content or not isinstance(content["claims"], list):
        print("Malformed draft: 'content.claims' must be a list.", file=sys.stderr)
        return 1

    # No-invention: leaf values come ONLY from claim.text; candidate.yaml is never read.
    # One compaction map shared across every claim so per-parent-list source indices
    # collapse to contiguous output slots deterministically (first-appearance order).
    cv_tree: dict = {}
    compaction: dict = {}
    try:
        for claim in content["claims"]:
            if not isinstance(claim, dict):
                raise TypeError("each claim must be a JSON object")
            if "source_span" not in claim or "text" not in claim:
                raise KeyError("claim missing 'source_span' or 'text'")
            # Type-guard the span before walking it: a null/numeric source_span would
            # otherwise reach dotted.split(".") on a non-string and raise a bare
            # AttributeError, breaking the degrade-without-traceback contract.
            if not isinstance(claim["source_span"], str) or not isinstance(
                claim["text"], (str, int, float)
            ):
                raise TypeError("claim 'source_span' must be a string and 'text' a scalar")
            set_path(cv_tree, claim["source_span"], claim["text"], compaction)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        print(f"Rejected span: {exc}", file=sys.stderr)
        return 1

    # Output-path safety (V5 / T-08-03): write only to the resolved --out; never
    # interpolate draft text into the path; never write config/candidate.yaml.
    out_path = args.out.expanduser().resolve()
    out_path.write_text(
        yaml.safe_dump(cv_tree, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
