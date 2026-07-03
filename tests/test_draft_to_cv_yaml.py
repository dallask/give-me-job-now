#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/draft_to_cv_yaml.py (E2E-02).

Proves the span-driven bridge is a truthful, deterministic adapter:
(1) reconstruction — each claim.text lands at the CV-YAML path named by its
    source_span;
(2) compaction — non-contiguous SOURCE list indices (a targeted CV cherry-picking
    non-adjacent items) collapse to contiguous OUTPUT slots by first-appearance order,
    per parent list, deterministically, with NO phantom/null leaf (T-08-04);
(3) type-mismatch rejection — a span that descends into a scalar exits 1, no
    traceback (T-08-01);
(4) ungrammatical-segment rejection — a span failing SEGMENT.fullmatch exits 1,
    no traceback (T-08-01);
(5) no-invention — every scalar leaf of the produced YAML traces to a claim.text
    (the bridge added nothing).

No pytest — run with ``python3 tests/test_draft_to_cv_yaml.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "draft_to_cv_yaml.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _tmp_path(name: str) -> Path:
    return Path(tempfile.mkdtemp()) / name


def _scalar_leaves(node: object) -> list:
    """Collect every scalar (non dict/list) leaf value in a nested structure."""
    if isinstance(node, dict):
        leaves: list = []
        for value in node.values():
            leaves.extend(_scalar_leaves(value))
        return leaves
    if isinstance(node, list):
        leaves = []
        for item in node:
            leaves.extend(_scalar_leaves(item))
        return leaves
    return [node]


def test_span_reconstruction() -> None:
    out = _tmp_path("cv.yaml")
    result = _run("--file", str(FIXTURES / "cv.draft.sample.json"), "--out", str(out))
    assert result.returncode == 0, f"happy path must exit 0: {result.stderr}"
    tree = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert tree["name"] == "Alex Fictional", tree
    assert tree.get("summary"), "summary must be present"
    assert tree["education"][0]["program"] == "BSc Sample Engineering", tree
    assert (
        tree["certifications"][0]["credentials"][0] == "Certified Sample Practitioner"
    ), tree


def test_compaction_of_noncontiguous_spans() -> None:
    """Sparse SOURCE indices compact to contiguous OUTPUT slots, per parent list.

    Mirrors the real E2E-03 cherry-pick: technical_expertise elements [0,3,1] (in
    first-appearance order) compact to blocks [0,1,2]; each block's ``skills`` list
    compacts its own sparse source indices independently and deterministically.
    """
    out = _tmp_path("cv.yaml")
    result = _run(
        "--file", str(FIXTURES / "cv.draft.compaction.sample.json"), "--out", str(out)
    )
    assert result.returncode == 0, f"non-contiguous spans must compact, not fail: {result.stderr}"
    tree = yaml.safe_load(out.read_text(encoding="utf-8"))

    # technical_expertise elements source [0,3,1] -> 3 contiguous blocks [0,1,2].
    te = tree["technical_expertise"]
    assert len(te) == 3, f"3 blocks expected (source elems 0,3,1 compacted): {te}"

    # Each parent list compacted independently, by first-appearance of its source idx.
    # Block 0 <- te[0].skills source [0,1,21,23,9]
    assert te[0]["skills"] == [
        "Alpha-Skill-A0",
        "Alpha-Skill-A1",
        "Alpha-Skill-A21",
        "Alpha-Skill-A23",
        "Alpha-Skill-A9",
    ], te[0]["skills"]
    # Block 1 <- te[3].skills source [11,12,2,0]
    assert te[1]["skills"] == [
        "Gamma-Skill-G11",
        "Gamma-Skill-G12",
        "Gamma-Skill-G2",
        "Gamma-Skill-G0",
    ], te[1]["skills"]
    # Block 2 <- te[1].skills source [0,4,6,7]
    assert te[2]["skills"] == [
        "Beta-Skill-B0",
        "Beta-Skill-B4",
        "Beta-Skill-B6",
        "Beta-Skill-B7",
    ], te[2]["skills"]
    assert [len(b["skills"]) for b in te] == [5, 4, 4], [len(b["skills"]) for b in te]

    # professional_experience[0].achievements source [4,8] -> contiguous [0,1].
    ach = tree["professional_experience"][0]["achievements"]
    assert len(ach) == 2 and ach[0].startswith("Delivered"), ach

    # No phantom/null leaf anywhere, and every leaf traces to an approved claim.text.
    draft = json.loads(
        (FIXTURES / "cv.draft.compaction.sample.json").read_text(encoding="utf-8")
    )
    claim_texts = {c["text"] for c in draft["content"]["claims"]}
    leaves = _scalar_leaves(tree)
    assert None not in leaves, f"no null/None leaf may be invented by compaction: {leaves}"
    for leaf in leaves:
        assert leaf in claim_texts, f"compacted leaf not traceable to a claim.text: {leaf!r}"


def test_type_mismatch_rejected() -> None:
    """A span descending into a scalar (contact -> contact.email) raises TypeError.

    Under compaction a lone out-of-range list index legitimately compacts to slot 0,
    so out-of-range no longer proves a hard-fail. A genuine TYPE MISMATCH still must:
    the first claim writes a scalar at ``contact``, the second tries to walk into it.
    """
    draft = {
        "schema_version": "1.0",
        "kind": "artifact_draft",
        "content": {
            "artifact_type": "cv",
            "language": "en",
            "claims": [
                {"text": "scalar-here", "source_span": "contact", "section": "header"},
                {"text": "x@example.com", "source_span": "contact.email", "section": "header"},
            ],
        },
    }
    draft_path = _tmp_path("typemismatch.json")
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    out = _tmp_path("cv.yaml")
    result = _run("--file", str(draft_path), "--out", str(out))
    assert result.returncode == 1, "type-mismatch span must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on type-mismatch span"


def test_ungrammatical_span_rejected() -> None:
    draft = {
        "schema_version": "1.0",
        "kind": "artifact_draft",
        "content": {
            "artifact_type": "cv",
            "language": "en",
            # "a-b" genuinely fails SEGMENT.fullmatch (the '-' is not a word char).
            "claims": [{"text": "x", "source_span": "a-b", "section": "header"}],
        },
    }
    draft_path = _tmp_path("bad.json")
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    out = _tmp_path("cv.yaml")
    result = _run("--file", str(draft_path), "--out", str(out))
    assert result.returncode == 1, "ungrammatical span must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on ungrammatical span"


def test_no_invention() -> None:
    out = _tmp_path("cv.yaml")
    result = _run("--file", str(FIXTURES / "cv.draft.sample.json"), "--out", str(out))
    assert result.returncode == 0, result.stderr
    tree = yaml.safe_load(out.read_text(encoding="utf-8"))
    draft = json.loads((FIXTURES / "cv.draft.sample.json").read_text(encoding="utf-8"))
    claim_texts = {c["text"] for c in draft["content"]["claims"]}
    for leaf in _scalar_leaves(tree):
        assert leaf in claim_texts, f"invented leaf not traceable to a claim.text: {leaf!r}"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
