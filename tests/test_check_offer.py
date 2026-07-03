#!/usr/bin/env python3
"""Behavior tests for the frozen offer-spec staleness re-check (INTAKE-02, INTAKE-03).

Runnable as a plain assertion script (no pytest dependency), mirroring
``tests/test_hash_artifact.py``. Proves that ``scripts/offers/check_offer.py``
enforces immutability by recompute-and-compare (RESEARCH Pattern 4), NOT by
filesystem permissions:

- fresh — a well-formed frozen doc whose ``offer_spec_hash`` equals
  ``canonical_hash(content)`` exits 0 and prints ``OK`` (deterministic across
  re-runs),
- stale — hand-editing one field inside ``content`` (without recomputing the
  hash) is detected and rejected (exit 1, ``STALE`` on stderr),
- captured_at-neutral — editing ONLY ``captured_at`` (a sibling OUTSIDE
  ``content``) does NOT trip staleness (Pitfall 1),
- robust — a missing file or invalid JSON exits 1 with a stderr message and no
  traceback.

The frozen docs are built INLINE here (via the audited ``canonical_hash``) so
this test stays independent of ``freeze_offer.py``.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "scripts" / "offers" / "check_offer.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
import hash_artifact  # noqa: E402


def _content() -> dict:
    """A content object conforming to ``offer_spec.schema.json#/$defs/offer_content``."""
    return {
        "title": "Розробник Python",
        "company": "Acme",
        "location": "Kyiv",
        "seniority": "senior",
        "employment_type": "full_time",
        "language": "ua",
        "must_haves": ["Python", "SQL"],
        "nice_to_haves": ["Docker"],
        "responsibilities": ["Веде команду з 5 інженерів"],
        "source_url": "https://example.com/vacancy/123",
        "raw_text_excerpt": "Шукаємо senior Python розробника у Києві.",
    }


def _frozen(content: dict, captured_at: str = "2026-07-03T00:00:00Z") -> dict:
    """Wrap *content* into a frozen offer-spec doc (hash over content only)."""
    return {
        "schema_version": "1.0",
        "kind": "offer_spec",
        "content": content,
        "captured_at": captured_at,
        "offer_spec_hash": hash_artifact.canonical_hash(content),
    }


def _write(doc: dict, tmp: Path, name: str = "offer.offer-spec.json") -> Path:
    path = tmp / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--file", str(path)],
        capture_output=True,
        text=True,
    )


def test_fresh_doc_exits_zero() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = _write(_frozen(_content()), Path(td))
        result = _cli(path)
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout


def test_fresh_doc_deterministic_across_reruns() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = _write(_frozen(_content()), Path(td))
        r1 = _cli(path)
        r2 = _cli(path)
        assert r1.returncode == 0, r1.stderr
        assert r2.returncode == 0, r2.stderr


def test_hand_edited_content_is_stale() -> None:
    with tempfile.TemporaryDirectory() as td:
        doc = _frozen(_content())
        # Mutate a field INSIDE content without recomputing the hash (deepcopy
        # pattern from test_hash_artifact.py lines 88-93).
        tampered = copy.deepcopy(doc)
        tampered["content"]["title"] = tampered["content"]["title"] + " EDITED"
        path = _write(tampered, Path(td))
        result = _cli(path)
        assert result.returncode == 1, "a hand-edited content field must be rejected"
        assert "STALE" in result.stderr


def test_captured_at_only_edit_is_neutral() -> None:
    with tempfile.TemporaryDirectory() as td:
        doc = _frozen(_content())
        # Editing ONLY captured_at (sibling outside content) must NOT trip staleness.
        doc["captured_at"] = "2099-12-31T23:59:59Z"
        path = _write(doc, Path(td))
        result = _cli(path)
        assert result.returncode == 0, (
            f"a captured_at-only change must stay neutral: {result.stderr}"
        )


def test_missing_file_exits_one_no_traceback() -> None:
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "does_not_exist.offer-spec.json"
        result = _cli(missing)
        assert result.returncode == 1, "a missing file must exit 1"
        assert result.stderr.strip() != ""
        assert "Traceback" not in result.stderr


def test_invalid_json_exits_one_no_traceback() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "broken.offer-spec.json"
        path.write_text("{ this is not valid json ", encoding="utf-8")
        result = _cli(path)
        assert result.returncode == 1, "invalid JSON must exit 1"
        assert result.stderr.strip() != ""
        assert "Traceback" not in result.stderr


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
