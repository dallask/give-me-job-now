#!/usr/bin/env python3
"""Advisory posting liveness/staleness verdict from an ALREADY-OBSERVED signal (GUIDE-03).

This does NOT fetch anything itself — it never performs its own network I/O. It
consumes a status/redirect signal the caller (the hub, via the scout's existing
scope-gated ``WebFetch``/Firecrawl fetch) already observed, handed in as plain CLI
arguments. Performing its own fetch here would create a new, unaudited egress path
that bypasses ``config/sources.yaml``'s domain-scope guard hooks.

``gmj_check_offer.py`` is a hash-tamper-detection fingerprint and has zero posting-
liveness concept; this script fills that gap with an explicit liveness/staleness
signal computed before freeze, so a dead/stale posting is never discovered only
after a wasted fielding+freeze round-trip.

Contract: this is advisory-only. A successful run (arguments parsed, computation
completed) ALWAYS exits 0 regardless of the live/dead verdict — the only
legitimate non-zero exit is a genuine argparse parse failure (e.g. a malformed
``--http-status`` value that isn't an int).

CLI: ``gmj_check_offer_liveness.py [--url URL] [--http-status N] [--discovered-at ISO8601]
[--max-age-days N]`` prints one line of JSON verdict to stdout and always exits 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


def compute_liveness(
    http_status: int | None,
    discovered_at: str | None,
    max_age_days: int | None,
    now: datetime | None = None,
) -> dict:
    """Compute an advisory liveness verdict from already-observed signals only."""
    reasons: list[str] = []
    age_days: int | None = None

    if http_status is None:
        reasons.append("unreachable")
    elif not (200 <= http_status <= 299):
        reasons.append(f"http_status_{http_status}")

    if max_age_days is not None:
        if discovered_at is None:
            pass
        else:
            try:
                parsed = datetime.fromisoformat(discovered_at.replace("Z", "+00:00"))
            except ValueError:
                reasons.append("discovered_at_unparseable")
            else:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                current = now if now is not None else datetime.now(timezone.utc)
                age_days = (current - parsed).days
                if age_days > max_age_days:
                    reasons.append("stale_by_age")

    return {"live": len(reasons) == 0, "reasons": reasons, "age_days": age_days}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Advisory posting liveness/staleness verdict from an already-observed signal."
    )
    parser.add_argument(
        "--url", type=str, default=None, help="Offer URL, echoed into the verdict for traceability only."
    )
    parser.add_argument(
        "--http-status",
        type=int,
        default=None,
        help="Status the caller already observed fetching --url, if any.",
    )
    parser.add_argument(
        "--discovered-at", type=str, default=None, help="ISO-8601 discovery timestamp."
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Optional staleness threshold in days; omitted = age check skipped.",
    )
    args = parser.parse_args()

    verdict = compute_liveness(
        http_status=args.http_status,
        discovered_at=args.discovered_at,
        max_age_days=args.max_age_days,
    )
    verdict["url"] = args.url
    print(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
