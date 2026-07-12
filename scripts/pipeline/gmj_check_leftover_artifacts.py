#!/usr/bin/env python3
"""Leftover partial-artifact-set detection over output/artifacts/<offer-slug>/ (CLEAN-01).

Scans ``<output-dir>/artifacts/<offer-slug>/`` for offer-slug subdirectories that hold
SOME but not ALL of the three expected ``{cv,cover_letter,interview_prep}.draft.json``
files — evidence of a prior pipeline run that started composing artifacts for an offer
but never finished (or was interrupted) before a NEW ``/gmj-pipeline-run`` begins.

This script does NOT correlate against ``output/cv/``'s rendered PDFs (naming there is
inconsistent across offers) and does NOT decide whether to proceed or clean — it only
reports structured findings. A later plan (06-03) wires those findings into the hub's
``init_run`` control-loop step, which is where the actual proceed-vs-clean human choice
(human_in_the_loop mode) or deterministic default (autonomous mode) lives.

Contract DEVIATION (per 06-PATTERNS.md): unlike
``gmj_check_dependencies.py``/``gmj_check_offer_liveness.py``, this script's non-empty
findings are NOT purely advisory — they feed a genuine, blocking human-choice gate in
``human_in_the_loop`` mode (CLEAN-02). This script itself still exits 0 on ANY
successful scan (a scan that completed, regardless of how many findings it reports) and
exits 1 ONLY on a genuine script-execution failure (e.g. ``--output-dir`` resolving to a
file, not a directory) — the CHOICE/blocking behavior lives entirely in the hub's
control-loop prose (``gmj-orchestrator.md``), never in this script's exit code.

CLI:
    python3 scripts/pipeline/gmj_check_leftover_artifacts.py --output-dir output

Prints ``partial: <N>`` on the first stdout line, followed by one JSON line per
finding (``{"offer_slug": ..., "present": [...], "missing": [...]}``), and returns 0 on
any successful scan.

Importable API:
    scan_leftovers(output_dir: Path) -> list[dict]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root

ARTIFACT_TYPES = ("cv", "cover_letter", "interview_prep")


def scan_leftovers(output_dir: Path) -> list[dict]:
    """Return a list of {"offer_slug", "present", "missing"} findings for partial offer dirs.

    Pure function: only reads via Path.is_dir()/Path.is_file()/Path.iterdir() — no writes,
    no network. A fully-populated 3-of-3 slug never appears in the returned list, and an
    offer-slug dir with zero .draft.json files present (untouched/empty) is skipped too —
    only a genuine PARTIAL set (1 or 2 of 3 present) is reported.
    """
    findings: list[dict] = []

    artifacts_dir = output_dir / "artifacts"
    if not artifacts_dir.is_dir():
        return findings

    for slug_dir in sorted(artifacts_dir.iterdir(), key=lambda p: p.name):
        if not slug_dir.is_dir():
            continue

        present = {t for t in ARTIFACT_TYPES if (slug_dir / f"{t}.draft.json").is_file()}
        if not present:
            continue

        missing = set(ARTIFACT_TYPES) - present
        if missing:
            findings.append(
                {
                    "offer_slug": slug_dir.name,
                    "present": sorted(present),
                    "missing": sorted(missing),
                }
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan <output-dir>/artifacts/<offer-slug>/ for incomplete per-offer artifact-draft "
            "sets left over from a prior pipeline run. Always exits 0 on a successful scan, "
            "regardless of findings count; exits 1 only on a genuine --output-dir usage error."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "output",
        help="Path to scan for an artifacts/<offer-slug>/ tree (default: repo output/)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser()
    if output_dir.exists() and not output_dir.is_dir():
        print(f"Not a directory: {output_dir}", file=sys.stderr)
        return 1

    findings = scan_leftovers(output_dir)
    print(f"partial: {len(findings)}")
    for finding in findings:
        print(json.dumps(finding))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
