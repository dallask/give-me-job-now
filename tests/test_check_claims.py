#!/usr/bin/env python3
"""Deterministic COMPOSE checks for the gmj_check_claims.py provenance gate (Plan 04-04).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. Each test proves an executed invariant rather than an
agent self-report:

- valid sample draft: the gate exits 0 (every span resolves),
- bad-span fixture: the gate exits 1 AND names the offending ``source_span``
  (COMPOSE-03 — fabrication surfaces as an unresolved span),
- an unknown claim key is rejected by the ``artifact_content`` sub-schema
  (``additionalProperties:false``),
- ``draft.content.language == offer_spec.content.language`` on the samples
  (COMPOSE-05 language propagation, hermetic),
- ``gmj-artifact-composer`` frontmatter carries no WebSearch/WebFetch tool (COMPOSE-01).

Only stdlib + PyYAML are used.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

CHECK = REPO_ROOT / "scripts" / "artifacts" / "gmj_check_claims.py"
CANDIDATE = FIXTURES / "candidate.merged.sample.yaml"
VALID_DRAFT = FIXTURES / "cv.draft.sample.json"
BADSPAN_DRAFT = FIXTURES / "cv.draft.badspan.sample.json"
OFFER_SPEC = FIXTURES / "offer_spec.sample.json"
COMPOSER = REPO_ROOT / ".claude" / "agents" / "gmj-artifact-composer.md"


def _run_check(draft_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--file", str(draft_path), "--candidate", str(CANDIDATE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _agent_frontmatter_tools(path: Path) -> list[str]:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        raise AssertionError(f"{path} has no YAML frontmatter block")
    meta = yaml.safe_load(parts[1]) or {}
    raw = meta.get("tools", "")
    if isinstance(raw, list):
        return [str(t).strip() for t in raw]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def test_valid_draft_exit_0() -> None:
    result = _run_check(VALID_DRAFT)
    assert result.returncode == 0, (
        f"valid draft must exit 0, got {result.returncode}\nstderr: {result.stderr}"
    )


def test_bad_span_reported_exit_1() -> None:
    result = _run_check(BADSPAN_DRAFT)
    assert result.returncode == 1, (
        f"bad-span draft must exit 1, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "source_span" in result.stderr, (
        f"bad-span draft must name the offending source_span; stderr: {result.stderr}"
    )


def test_unknown_claim_key_rejected() -> None:
    draft = json.loads(VALID_DRAFT.read_text(encoding="utf-8"))
    draft["content"]["claims"][0]["bogus_key"] = "unexpected"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(draft, fh)
        tmp_path = Path(fh.name)
    try:
        result = _run_check(tmp_path)
        assert result.returncode == 1, (
            f"unknown claim key must be rejected (exit 1), got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_language_matches_offer() -> None:
    draft = json.loads(VALID_DRAFT.read_text(encoding="utf-8"))
    offer = json.loads(OFFER_SPEC.read_text(encoding="utf-8"))
    assert draft["content"]["language"] == offer["content"]["language"], (
        "draft language must equal the offer language (COMPOSE-05): "
        f"{draft['content']['language']!r} != {offer['content']['language']!r}"
    )


def test_composer_has_no_web_tools() -> None:
    tools = _agent_frontmatter_tools(COMPOSER)
    assert "WebSearch" not in tools and "WebFetch" not in tools, (
        f"gmj-artifact-composer must carry no web tools (COMPOSE-01); got {tools}"
    )


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
