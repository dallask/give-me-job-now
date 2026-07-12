#!/usr/bin/env python3
"""Advisory optional-dependency presence probe over config/preferences.yaml (GUIDE-04).

Probes whether each optional dependency implied by ``config/preferences.yaml``'s
feature-selector keys is importable, using ``importlib.util.find_spec()`` — this
never imports the module itself (no import side effects) and never performs
network I/O. It answers "is this importable" without paying the import cost or
triggering side effects (relevant since e.g. ``weasyprint`` pulls in native
Pango/Cairo bindings), making it safe to call speculatively even for a feature
this run will not use.

``gmj_render_cv.py``'s WeasyPrint fallback and ``gmj_firecrawl_search.py``'s
inline ``from firecrawl import Firecrawl`` import both discover a missing
optional dependency only AFTER the relevant spoke has already been dispatched
and started working. This script surfaces the same information earlier, as an
upfront hint — it does NOT replace either existing per-call-site
``except ImportError:``/``FIRECRAWL_API_KEY`` guard, which remain unchanged,
final safety nets.

Contract: this is advisory-only (QA-01-style, identical to
``gmj_check_render_quality.py``'s own QA-03 exit-0-always rule). A successful
run (the preferences file was found and parsed as a mapping) ALWAYS exits 0
regardless of how many dependencies are reported missing. The only legitimate
non-zero exit is a genuine script-execution failure — ``--preferences`` not a
file, or invalid/non-mapping YAML.

CLI:
    python3 scripts/pipeline/gmj_check_dependencies.py --preferences config/preferences.yaml

Prints ``missing: <N>`` on the first stdout line, followed by one line per
finding, and always returns 0 on a successful run.

Importable API:
    check_dependencies(preferences: dict) -> list[dict]
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root


def check_dependencies(preferences: dict) -> list[dict]:
    """Return a list of {"feature", "missing", "hint"} findings for missing optional deps."""
    findings: list[dict] = []

    if preferences.get("search_provider") == "firecrawl" and importlib.util.find_spec("firecrawl") is None:
        findings.append(
            {
                "feature": "search_provider: firecrawl",
                "missing": "firecrawl-py",
                "hint": "pip install -r scripts/offers/requirements.txt",
            }
        )

    weasyprint_missing = importlib.util.find_spec("weasyprint") is None
    jinja2_missing = importlib.util.find_spec("jinja2") is None
    if weasyprint_missing or jinja2_missing:
        missing_name = "weasyprint" if weasyprint_missing else "jinja2"
        findings.append(
            {
                "feature": "CV HTML template rendering",
                "missing": missing_name,
                "hint": "pip install weasyprint  # falls back to ReportLab if skipped",
            }
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Advisory-only optional-dependency presence probe over config/preferences.yaml's "
            "feature-selector keys. Always exits 0 on a successful run, regardless of how many "
            "dependencies are missing."
        )
    )
    parser.add_argument(
        "--preferences",
        type=Path,
        default=REPO_ROOT / "config" / "preferences.yaml",
        help="Path to config/preferences.yaml (default: repo config)",
    )
    args = parser.parse_args()

    preferences_path = args.preferences.expanduser()
    if not preferences_path.is_file():
        print(f"Not a file: {preferences_path}", file=sys.stderr)
        return 1

    try:
        preferences = yaml.safe_load(preferences_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"Invalid YAML: {exc}", file=sys.stderr)
        return 1

    if not isinstance(preferences, dict):
        print("config/preferences.yaml must be a mapping.", file=sys.stderr)
        return 1

    findings = check_dependencies(preferences)
    print(f"missing: {len(findings)}")
    for finding in findings:
        print(f"{finding['feature']}: {finding['missing']} — {finding['hint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
