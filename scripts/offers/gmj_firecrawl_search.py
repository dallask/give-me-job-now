#!/usr/bin/env python3
"""Firecrawl SDK CLI wrapper for gmj-offer-scout's opt-in search path (SEARCH-05/SEARCH-08).

Thin Bash-invoked CLI around ``firecrawl-py``'s ``/search`` and ``/scrape`` (schema-guided
``json`` format) calls. Used by ``gmj-offer-scout`` instead of ``WebSearch``/``WebFetch`` only
when ``config/preferences.yaml``'s ``search_provider`` key is set to ``firecrawl`` (that
branch point lives in the agent definition, not in this script).

CLI contract: ``gmj_firecrawl_search.py --mode {search,scrape} [--query STR] [--url STR]
[--limit N]`` — ``--query`` is required for ``--mode search``, ``--url`` is required for
``--mode scrape`` (enforced via an argparse mutually-exclusive... actually per-mode required
group). ``--url``/``--query`` flag names are LOCKED verbatim: Plan 02's
``gmj-firecrawl-scope-guard.sh`` regex-parses ``tool_input.command`` for these exact flags.

Exit-code contract: 0 = success, fielded JSON printed to stdout. 1 = error message printed to
stderr — including the case where ``FIRECRAWL_API_KEY`` is unset (SEARCH-06): this script
refuses to run and NEVER constructs a ``firecrawl.Firecrawl`` client in that case, overriding
the SDK's own keyless-free-tier fallback default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/offers/ -> repo root
SCHEMA_PATH = REPO_ROOT / "schemas" / "firecrawl_extract_schema.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Firecrawl SDK CLI wrapper for gmj-offer-scout (search + scrape modes)."
    )
    parser.add_argument(
        "--mode", required=True, choices=["search", "scrape"], help="Operation to perform."
    )
    parser.add_argument("--query", default=None, help="Search query (search mode).")
    parser.add_argument("--url", default=None, help="Target URL to scrape (scrape mode).")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max search results to return (search mode only; matches SDK default).",
    )
    args = parser.parse_args()

    if args.mode == "search" and not args.query:
        parser.error("--mode search requires --query")
    if args.mode == "scrape" and not args.url:
        parser.error("--mode scrape requires --url")

    # SEARCH-06: an unset FIRECRAWL_API_KEY is a clean, explicit failure — never a silent
    # fallback to the SDK's own keyless free tier. This check happens BEFORE any
    # `firecrawl.Firecrawl(...)` construction, proven by tests/test_firecrawl_search_cli.py.
    load_dotenv()
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        print(
            "FIRECRAWL_API_KEY not set; add it to .env (see .env.example)",
            file=sys.stderr,
        )
        return 1

    from firecrawl import Firecrawl

    client = Firecrawl(api_key=api_key)

    if args.mode == "search":
        try:
            result = client.search(args.query, sources=["web"], limit=args.limit)
        except Exception as exc:  # noqa: BLE001 — surface any SDK/HTTP failure uniformly
            print(f"Firecrawl call failed: {exc}", file=sys.stderr)
            return 1
        web_hits = getattr(result, "web", None) or []
        payload = {
            "web": [
                {
                    "url": getattr(item, "url", None),
                    "title": getattr(item, "title", None),
                    "description": getattr(item, "description", None),
                }
                for item in web_hits
            ]
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    # args.mode == "scrape"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        doc = client.scrape(
            args.url,
            formats=[{"type": "json", "schema": schema}],
            only_main_content=True,
        )
    except Exception as exc:  # noqa: BLE001 — surface any SDK/HTTP failure uniformly
        print(f"Firecrawl call failed: {exc}", file=sys.stderr)
        return 1
    fielded = getattr(doc, "json", None)
    print(json.dumps(fielded, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
