#!/usr/bin/env python3
"""Single owner of the candidate.yaml dotted/indexed source-span grammar (COMPOSE-03).

This module is the *one* parser for the provenance/source-span path grammar first
established by the Phase 3.1 provenance sidecar (``tests/test_candidate_ingestion.py``)
and reused by ``gmj_check_claims.py`` (Plan 04) and the Phase 5 truth-verifier. Keeping a
single importable owner is the anti-drift guarantee (Pitfall 1 / threat T-04-05): a
divergent second regex can no longer exist because every consumer imports from here.

The grammar is intentionally strict (threat T-04-04): a segment is a bare word key
``[A-Za-z_][A-Za-z0-9_]*`` optionally followed by one or more ``[<int>]`` list
indices, matched with ``re.fullmatch``. There is no ``eval``, no attribute access,
no quoted keys, negative indices, or wildcards — only dict-key and list-index
walking. An unparseable or unresolvable segment raises (KeyError/IndexError/
TypeError); it never executes. A span is untrusted composer-authored text, so this
strictness is a security boundary, not a convenience.
"""

from __future__ import annotations

import re

SEGMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)")


def resolve_path(data: object, dotted: str) -> object:
    """Walk a dotted/indexed key (e.g. ``education[0].credentials[1]``) into ``data``.

    Raises KeyError/IndexError/TypeError if any segment does not resolve.
    """
    node = data
    for segment in dotted.split("."):
        match = SEGMENT.fullmatch(segment)
        if not match:
            raise KeyError(f"unparseable provenance segment: {segment!r}")
        name, indices = match.group(1), match.group(2)
        node = node[name]
        for idx in re.findall(r"\[(\d+)\]", indices):
            node = node[int(idx)]
    return node
