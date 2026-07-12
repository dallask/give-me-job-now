#!/usr/bin/env python3
"""Append one gsd-workflow-layer JSONL execution-log entry (D-01/D-03, REFLECT-01).

This is the writer half of the gsd-workflow-step-granularity capture layer. It is a
plain CLI script, invoked directly (not a Claude Code hook) — a future GSD-core-side
dispatch point (or a locally-owned wrapper) shells out to it at loop-hook boundaries
like ``execute:post``/``ship:post`` with the phase/plan/wave/outcome context already
known at the dispatch point. See ``docs/execution-log-wiring.md`` for why this script
is not wired via a ``.gsd/capabilities/`` overlay in this installation
(06-CAPABILITY-SPIKE.md VERDICT: fallback-required).

Invocation example::

    python3 scripts/gmj_execution_log_writer.py \\
        --point execute:post --phase 6 --plan 03 --wave 2 --outcome pass

Writes exactly one JSONL line to
``.planning/execution-logs/gsd-workflow-<YYYY-MM-DD>.jsonl`` (per-date sharded,
source-tagged ``gsd-workflow`` — a separate physical file from Plan 02's
``tool-calls-<date>.jsonl``, so the two independent writer layers never contend for
the same file handle; D-03's "one unified logical stream" is satisfied at
analysis/read time via glob + sort-by-``ts``, not by sharing one file).

Two distinct failure modes, by design (D-09):

- **CLI usage error** (e.g. an ``--outcome`` value outside the allowed vocabulary) is a
  caller bug, not a runtime environment failure — argparse's ``choices=`` handles this
  and exits non-zero with a stderr message. This is correct and does NOT violate D-09:
  a usage error happens before any workflow-blocking side effect, and the workflow
  caller is expected to guard the invocation (e.g. wrap it so a non-zero exit here
  never propagates as a blocking error to the caller's own control flow).
- **Runtime/environment failure** (e.g. the log directory's parent is missing or
  unwritable) must degrade gracefully: print a warning to stderr and still exit 0 —
  a logging failure must never propagate as a workflow-blocking error.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = REPO_ROOT / ".planning" / "execution-logs"

# The twelve named loop points from loop-hook-dispatch.md's point list.
LOOP_POINTS = [
    "discuss:pre",
    "discuss:post",
    "plan:pre",
    "plan:post",
    "execute:pre",
    "execute:wave:pre",
    "execute:wave:post",
    "execute:post",
    "verify:pre",
    "verify:post",
    "ship:pre",
    "ship:post",
]

OUTCOMES = ["pass", "fail", "halt", "checkpoint"]

MAX_FIELD_LEN = 2000  # DoS mitigation (T-06-03-03), mirrors Plan 02's per-field bound.


def _truncate(value: str) -> str:
    if len(value) > MAX_FIELD_LEN:
        return value[:MAX_FIELD_LEN] + "...<truncated>"
    return value


def build_entry(
    *,
    point: str,
    phase: str | None,
    plan: str | None,
    wave: str | None,
    outcome: str,
    extra_json: str | None,
) -> dict:
    """Build the JSONL entry dict. Pure function — no I/O, easy to unit test."""
    entry: dict = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "gsd-workflow",
        "point": point,
        "phase": phase,
        "plan": plan,
        "wave": wave,
        "outcome": outcome,
    }
    if extra_json:
        try:
            extra = json.loads(extra_json)
        except (json.JSONDecodeError, ValueError):
            # T-06-03-02: malformed --extra-json degrades to omitting the field
            # entirely — never crash the writer on bad input.
            extra = None
        if isinstance(extra, dict):
            entry.update(extra)
    # Bound any string field's length (DoS mitigation, T-06-03-03).
    for key, value in list(entry.items()):
        if isinstance(value, str):
            entry[key] = _truncate(value)
    return entry


def write_entry(entry: dict, log_dir: Path) -> tuple[bool, str | None]:
    """Append ``entry`` as one JSONL line under ``log_dir``.

    Returns (wrote_ok, warning_message). Never raises — a write/permission
    failure is reported via the returned warning, not an exception (D-09).
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"gsd-workflow-{date_str}.jsonl"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return True, None
    except OSError as exc:
        return False, f"gmj_execution_log_writer: could not write {log_file}: {exc}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append one gsd-workflow-layer JSONL execution-log entry."
    )
    parser.add_argument(
        "--point",
        required=True,
        choices=LOOP_POINTS,
        help="The GSD loop-hook point this entry represents (e.g. execute:post).",
    )
    parser.add_argument("--phase", default=None, help="Phase identifier (optional).")
    parser.add_argument("--plan", default=None, help="Plan identifier (optional).")
    parser.add_argument(
        "--wave",
        default=None,
        help="Wave identifier (optional, nullable — e.g. ship:post has no plan/wave).",
    )
    parser.add_argument(
        "--outcome",
        required=True,
        choices=OUTCOMES,
        help="One of pass|fail|halt|checkpoint (CONTEXT.md's required outcome vocabulary).",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=DEFAULT_LOG_DIR,
        help="Directory to write the per-date JSONL file into "
        "(default: .planning/execution-logs/).",
    )
    parser.add_argument(
        "--extra-json",
        default=None,
        help="Optional JSON string merged into the entry for point-specific extra "
        "fields (e.g. an artifacts list). Malformed input is silently ignored.",
    )
    args = parser.parse_args(argv)

    entry = build_entry(
        point=args.point,
        phase=args.phase,
        plan=args.plan,
        wave=args.wave,
        outcome=args.outcome,
        extra_json=args.extra_json,
    )
    wrote_ok, warning = write_entry(entry, args.log_dir)
    if not wrote_ok:
        print(warning, file=sys.stderr)
        # D-09: a logging failure must never propagate as a workflow-blocking
        # error to the caller — degrade gracefully, still exit 0.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
