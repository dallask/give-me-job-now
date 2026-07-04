#!/usr/bin/env python3
"""SCOUT-05 fan-out proof: the sources-scope-guard hook never fails open under
per-board worker fan-out.

Runnable as a plain assertion script (no pytest dependency). Phase 11 makes the
hub dispatch one ``gmj-offer-scout`` worker per job board in a single turn. On Claude
Code's single-threaded event loop those "parallel" workers serialize through the
ONE globally-registered ``PreToolUse`` ``WebSearch|WebFetch`` hook
(``.claude/settings.json`` — no per-agent registration, no opt-out). This test
proves that serialization is a per-worker DOMAIN gate, not a bypassable one:

- feeding a SEQUENCE of distinct per-board worker payloads through the executed
  hook, each is independently gated (in-scope host -> exit 0, off-list -> exit 2),
- the ``config/sources.yaml`` READ is logged BEFORE the allow/block decision on
  EVERY call — fan-out never creates an unguarded or fail-open worker,
- a worker whose ``CLAUDE_PROJECT_DIR`` has no allow-list fails CLOSED (never an
  exit-0 fail-open pass).

The proof is a test over the EXECUTED hook, not an agent self-report. It adds NO
per-board scope narrowing to the hook — the invariant is "never outside
``config/sources.yaml``", already enforced globally; board assignment lives in the
Task prompt, not the safety gate.

The executed-hook harness (``_run``/``_read_payload``/
``_assert_read_logged_before_decision``) and the fixture paths
(``IN_SCOPE``/``OUT_OF_SCOPE``) are REUSED from ``test_sources_scope_guard`` rather
than re-derived — importing that module only runs its defs/constants (its ``main()``
is ``__main__``-guarded), so the import is side-effect free.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Reuse the sibling scope-guard harness helpers + fixtures (do NOT re-copy them).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sources_scope_guard as guard  # noqa: E402


def _worker_payload(url: str) -> str:
    """Build a distinct per-board WebFetch worker payload for the given board URL."""
    return json.dumps(
        {
            "tool_name": "WebFetch",
            "tool_input": {"url": url, "prompt": "Extract the job posting details"},
        }
    )


def _run_missing_sources(stdin_text: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the hook with NO ``config/sources.yaml`` reachable — fail-closed setup.

    Mirrors ``guard._run_in_dir`` but (a) never copies the allow-list and (b) points
    the subprocess ``cwd`` at the empty temp dir so the hook's cwd-relative
    ``config/sources.yaml`` fallback (sources-scope-guard.sh:66-70) also finds
    nothing — otherwise it would resolve the real repo's allow-list and the
    fail-closed assertion would be vacuous.
    """
    tmp = Path(tempfile.mkdtemp(prefix="scope-guard-fanout-"))
    (tmp / "config").mkdir(parents=True, exist_ok=True)  # config/ exists, allow-list absent
    result = subprocess.run(
        ["sh", str(guard.HOOK)],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(tmp),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp)},
    )
    return result, tmp / ".claude" / "logs" / "sources-scope.log"


def test_fanout_each_worker_independently_gated() -> None:  # SCOUT-05 never-fails-open
    # Model N parallel per-board workers as the SEQUENCE the single-threaded event
    # loop serializes them into. Each distinct board payload is fed through the ONE
    # executed hook and independently gated; the READ-before-decision invariant is
    # asserted for EVERY call, not once.
    workers = [
        (guard._read_payload(guard.IN_SCOPE), 0),                          # dou.ua (in-scope)
        (guard._read_payload(guard.OUT_OF_SCOPE), 2),                      # example.com (off-list)
        (_worker_payload("https://www.work.ua/jobs/123/"), 0),            # work.ua board worker
        (_worker_payload("https://jobs.dou.ua/vacancies/company/acme/"), 0),  # dou.ua board worker
        (_worker_payload("https://evil.example.net/scrape"), 2),          # off-list board worker
    ]
    assert len(workers) >= 2, "fan-out proof must drive >=2 distinct worker payloads"
    for stdin_text, expected in workers:
        result, log = guard._run(stdin_text)
        assert result.returncode == expected, (
            f"per-board worker must be independently gated (expected exit {expected}); "
            f"got {result.returncode}\npayload: {stdin_text}\nstderr: {result.stderr}"
        )
        # READ logged BEFORE the decision on this specific worker call (not just once).
        guard._assert_read_logged_before_decision(log)
        sentinel = "ALLOWED" if expected == 0 else "BLOCK"
        assert sentinel in log.read_text(encoding="utf-8"), (
            f"worker log must record a {sentinel} decision; got:\n"
            f"{log.read_text(encoding='utf-8')}"
        )


def test_fanout_missing_sources_fails_closed() -> None:  # SCOUT-05 fail-closed
    # A fan-out worker whose CLAUDE_PROJECT_DIR carries no config/sources.yaml must
    # NOT fail open. Using a host that WOULD be in-scope proves the block is caused
    # by the absent allow-list (fail-closed), not by the host being off-list.
    result, log = _run_missing_sources(guard._read_payload(guard.IN_SCOPE))
    assert result.returncode != 0, (
        "a worker with no config/sources.yaml must NEVER get an exit-0 fail-open pass; "
        f"got returncode {result.returncode}\nstderr: {result.stderr}"
    )
    assert result.returncode == 2, (
        f"missing allow-list must block the WebFetch (exit 2); got {result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    # Assert exit code AND the log sentinel (an unrelated nonzero crash must not pass).
    guard._assert_read_logged_before_decision(log)
    assert "BLOCK" in log.read_text(encoding="utf-8"), (
        f"fail-closed worker log must record a BLOCK decision; got:\n"
        f"{log.read_text(encoding='utf-8')}"
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
