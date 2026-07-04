#!/usr/bin/env python3
"""Behavior tests for the offer-freeze utility (INTAKE-01, INTAKE-03).

Runnable as a plain assertion script (no pytest dependency), mirroring
``tests/test_hash_artifact.py``. Proves that ``scripts/offers/gmj_freeze_offer.py``:

- wraps the fielded offer body in a ``content`` object with ``captured_at`` and
  ``offer_spec_hash`` as siblings OUTSIDE it,
- stamps ``offer_spec_hash == hash_artifact.canonical_hash(content)`` — a 64-char
  lowercase hex produced by executed code, never agent-asserted (T-03-hash),
- keeps that hash STABLE when only ``captured_at`` changes (Pitfall 1),
- validates ``content`` against ``schemas/offer_spec.schema.json#/$defs/offer_content``
  and rejects an extra key (``additionalProperties:false``),
- via the CLI, writes ``sources/offers/<slug>.offer-spec.json`` with a sanitized
  ``[a-z0-9-]`` slug and exits 0; a draft missing a required field exits 1 (validation
  before write).
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFT = REPO_ROOT / "sources" / "offers" / "sample-offer-draft.json"
FREEZER = REPO_ROOT / "scripts" / "offers" / "gmj_freeze_offer.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "offers"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
import gmj_freeze_offer as freeze_offer  # noqa: E402
import gmj_hash_artifact as hash_artifact  # noqa: E402

_HEX = set("0123456789abcdef")
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(FREEZER), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(c in _HEX for c in value)


def test_freeze_shape() -> None:
    content = _load(DRAFT)
    frozen = freeze_offer.freeze(content, "2026-07-03T10:00:00Z")
    assert frozen["schema_version"] == "1.0", "schema_version must be pinned to 1.0"
    assert frozen["kind"] == "offer_spec", "kind must be offer_spec"
    assert frozen["content"] == content, "content must pass through unchanged"
    assert frozen["captured_at"] == "2026-07-03T10:00:00Z", "captured_at is a sibling"
    assert "offer_spec_hash" in frozen, "offer_spec_hash must be present"
    # captured_at and offer_spec_hash live OUTSIDE content (excluded from hash by construction)
    assert "captured_at" not in frozen["content"]
    assert "offer_spec_hash" not in frozen["content"]


def test_hash_is_canonical_hash_of_content() -> None:
    content = _load(DRAFT)
    frozen = freeze_offer.freeze(content, "2026-07-03T10:00:00Z")
    assert frozen["offer_spec_hash"] == hash_artifact.canonical_hash(content), (
        "offer_spec_hash must equal canonical_hash(content) — executed-code computed"
    )
    assert _is_sha256_hex(frozen["offer_spec_hash"]), "hash must be 64-char lowercase hex"


def test_hash_stable_across_captured_at() -> None:
    content = _load(DRAFT)
    a = freeze_offer.freeze(content, "2026-07-03T10:00:00Z")
    b = freeze_offer.freeze(content, "2026-08-01T00:00:00Z")
    assert a["offer_spec_hash"] == b["offer_spec_hash"], (
        "a captured_at-only change must NOT move the hash (Pitfall 1)"
    )


def test_content_validates_against_defs() -> None:
    content = _load(DRAFT)
    errors = freeze_offer.validate_content(content)
    assert errors == [], f"valid fielded content must pass $defs/offer_content: {errors}"


def test_extra_key_rejected() -> None:
    content = copy.deepcopy(_load(DRAFT))
    content["__unexpected__"] = "nope"
    errors = freeze_offer.validate_content(content)
    assert errors, "an extra key in content must be rejected (additionalProperties:false)"


def test_cli_writes_sanitized_slug_path_and_exits_zero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        result = _cli(["--file", str(DRAFT), "--captured-at", "2026-07-03T10:00:00Z"], cwd=tmpdir)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        written = list((tmpdir / "sources" / "offers").glob("*.offer-spec.json"))
        assert len(written) == 1, f"exactly one frozen file expected, got {written}"
        out = written[0]
        slug = out.name[: -len(".offer-spec.json")]
        assert _SLUG_RE.match(slug), f"slug must be [a-z0-9-] only, got {slug!r}"
        assert str(out) in result.stdout, "CLI must print the written path"
        doc = _load(out)
        assert doc["kind"] == "offer_spec"
        assert doc["offer_spec_hash"] == hash_artifact.canonical_hash(doc["content"])


def test_cli_missing_required_field_exits_one() -> None:
    bad = copy.deepcopy(_load(DRAFT))
    del bad["title"]  # drop a required field
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        bad_path = tmpdir / "bad-draft.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        result = _cli(["--file", str(bad_path)], cwd=tmpdir)
        assert result.returncode == 1, "a draft missing a required field must exit 1"
        assert result.stderr.strip() != "", "validation failure must report to stderr"
        written = list((tmpdir / "sources" / "offers").glob("*.offer-spec.json"))
        assert written == [], "no file may be written when validation fails (validate before write)"


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
