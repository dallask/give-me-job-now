#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/draft_to_cv_yaml.py (E2E-02).

Proves the span-driven bridge is a truthful, deterministic adapter:
(1) reconstruction — each claim.text lands at the CV-YAML path named by its
    source_span;
(2) out-of-range rejection — a span past the end of a list exits 1, no traceback
    (no phantom-null invention, T-08-04);
(3) ungrammatical-segment rejection — a span failing SEGMENT.fullmatch exits 1,
    no traceback (T-08-01);
(4) no-invention — every scalar leaf of the produced YAML traces to a claim.text
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


def test_out_of_range_span_rejected() -> None:
    out = _tmp_path("cv.yaml")
    result = _run(
        "--file", str(FIXTURES / "cv.draft.badspan.sample.json"), "--out", str(out)
    )
    assert result.returncode == 1, "out-of-range span must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on rejected span"


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
