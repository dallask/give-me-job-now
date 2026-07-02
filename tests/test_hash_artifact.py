#!/usr/bin/env python3
"""Behavior tests for the executed artifact hasher (ARCH-05).

Runnable as a plain assertion script (no pytest dependency). Proves that
``scripts/contracts/hash_artifact.py`` computes a content-integrity fingerprint
that is:

- deterministic — identical input yields the identical 64-char lowercase hex
  SHA-256 across runs (and the CLI agrees with the in-process helper),
- subset-stable — a change confined to a volatile, out-of-subset envelope field
  (``pipeline_run_id`` / a ``timestamp``) does NOT move the hash,
- content-sensitive — a change to an in-subset field DOES move the hash,
- encoding-stable for Cyrillic — ua/ru content hashes reproducibly and is
  key-order independent (``sort_keys`` + ``ensure_ascii=False``).

No agent ever asserts the hash: it is produced only by the executed code below.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = REPO_ROOT / "schemas" / "samples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
HASHER = REPO_ROOT / "scripts" / "contracts" / "hash_artifact.py"

SAMPLE = SAMPLES / "offer_spec.valid.json"
CYRILLIC = FIXTURES / "hash_cyrillic.json"
VOLATILE = FIXTURES / "hash_volatile.json"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
import hash_artifact  # noqa: E402

_HEX = set("0123456789abcdef")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cli(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HASHER), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(c in _HEX for c in value)


def test_determinism() -> None:
    h1 = hash_artifact.hash_artifact(_load(SAMPLE), "offer_spec")
    h2 = hash_artifact.hash_artifact(_load(SAMPLE), "offer_spec")
    assert h1 == h2, "identical input must hash identically"
    assert _is_sha256_hex(h1), f"expected 64-char lowercase hex, got {h1!r}"


def test_cli_matches_helper_and_is_reproducible() -> None:
    r1 = _cli(["--kind", "offer_spec", "--file", str(SAMPLE)])
    r2 = _cli(["--kind", "offer_spec", "--file", str(SAMPLE)])
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    out1 = r1.stdout.strip()
    assert out1 == r2.stdout.strip(), "two CLI runs on the same file must agree"
    assert _is_sha256_hex(out1), f"CLI must print 64-char hex, got {out1!r}"
    assert out1 == hash_artifact.hash_artifact(_load(SAMPLE), "offer_spec"), (
        "CLI output must match the in-process helper"
    )


def test_subset_stability_volatile_field_ignored() -> None:
    base = hash_artifact.hash_artifact(_load(SAMPLE), "offer_spec")
    volatile = hash_artifact.hash_artifact(_load(VOLATILE), "offer_spec")
    assert base == volatile, (
        "a change confined to volatile out-of-subset fields must not move the hash"
    )


def test_changed_subset_differs() -> None:
    base = hash_artifact.hash_artifact(_load(SAMPLE), "offer_spec")
    mutated = copy.deepcopy(_load(SAMPLE))
    mutated["notes"] = str(mutated.get("notes", "")) + " EDITED"
    assert hash_artifact.hash_artifact(mutated, "offer_spec") != base, (
        "an in-subset content change must move the hash"
    )


def test_cyrillic_reproducible_and_key_order_independent() -> None:
    h1 = hash_artifact.hash_artifact(_load(CYRILLIC), "offer_spec")
    h2 = hash_artifact.hash_artifact(_load(CYRILLIC), "offer_spec")
    assert h1 == h2, "Cyrillic content must hash reproducibly"
    assert _is_sha256_hex(h1)
    # A byte-for-byte equal logical input in a different key order must hash
    # identically — sort_keys makes ordering irrelevant.
    reordered = dict(reversed(list(_load(CYRILLIC).items())))
    assert hash_artifact.hash_artifact(reordered, "offer_spec") == h1, (
        "sort_keys must make key order irrelevant"
    )


def test_claims_kind_subset() -> None:
    payload = {
        "kind": "claims",
        "pipeline_run_id": "run-a",
        "claims": [{"id": "c1", "text": "Веде команду з 5 інженерів"}],
    }
    base = hash_artifact.hash_artifact(payload, "claims")
    assert _is_sha256_hex(base)
    volatile = copy.deepcopy(payload)
    volatile["pipeline_run_id"] = "run-b"
    assert hash_artifact.hash_artifact(volatile, "claims") == base, (
        "a volatile change must not move the claims hash"
    )
    changed = copy.deepcopy(payload)
    changed["claims"][0]["text"] = "Змінений опис"
    assert hash_artifact.hash_artifact(changed, "claims") != base, (
        "a change to the claim set must move the claims hash"
    )


def test_cli_rejects_unknown_kind() -> None:
    result = _cli(["--kind", "../etc/passwd", "--file", str(SAMPLE)])
    assert result.returncode != 0, "unknown --kind must be rejected"


def test_cli_rejects_missing_file() -> None:
    result = _cli(["--kind", "offer_spec", "--file", str(REPO_ROOT / "does_not_exist.json")])
    assert result.returncode == 1, "missing --file must exit 1"
    assert result.stderr.strip() != ""


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
