#!/usr/bin/env python3
"""Deterministic offer-language detector (PIPE-10).

Detects whether an offer posting's text is Ukrainian, Russian, or English via a
Cyrillic-character-ratio + small UA/RU stopword-list heuristic. This is a
deterministic classification with NO LLM/ML fallback branch — it mirrors this
codebase's "small deterministic Python scripts decide, LLM never decides
gate/classification outcomes" architecture (Gate A, Gate B,
``scripts/pipeline/gmj_check_cap.py``).

The detected value is meant to become ``offer_spec.content.language``
(``schemas/offer_spec.schema.json``'s existing, already-required ``ua``/``ru``/``en``
enum) — this script only changes who PRODUCES that value: ``gmj-offer-scout.md``
calls this script instead of judging the language itself, so the frozen
``offer_spec`` value can never silently diverge from what downstream artifact
composition/rendering choose (the confirmed regression: a delivered CV with
Ukrainian section headers but English body content).

Algorithm (``detect_language``):
1. Compute the ratio of Cyrillic alphabetic characters to all alphabetic characters.
   Below ``CYRILLIC_RATIO_THRESHOLD`` the text is not Cyrillic-dominant enough to be
   UA/RU — return ``"en"`` (the inconclusive-default, per CONTEXT.md's locked decision).
2. Otherwise count case-insensitive whole-word hits against ``UA_STOPWORDS`` vs
   ``RU_STOPWORDS`` (small sets of UA-only vs RU-only spelling variants). Whichever
   set has strictly more hits wins; a tie (including 0-0, a Cyrillic-but-inconclusive
   text) still defaults to ``"en"`` — the codebase's full supported set is en/ua/ru
   and an absent/tied stopword signal inside Cyrillic text is not itself conclusive
   of which Slavic language it is.

Detection NEVER fails: empty/whitespace-only/missing text all degrade to ``"en"``
rather than crashing or exiting nonzero (RESEARCH.md Pattern 2 — no nonzero-exit
branch for ordinary detection input). ``main()`` always returns 0; only a genuinely
missing ``--file`` path or bad CLI args produce a nonzero exit.

CLI: ``gmj_detect_language.py (--file <path> | --stdin)`` prints exactly one of
``ua``/``ru``/``en`` to stdout and exits 0.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Minimum fraction of ALPHABETIC characters that must be Cyrillic before the text is
# even considered non-English. Below this ratio the text is treated as (mostly) Latin
# script / too short / too mixed to be conclusively Ukrainian or Russian, and detection
# degrades to "en" (CONTEXT.md's locked "inconclusive -> default to English" decision).
# 0.15 was chosen because ordinary EN job postings occasionally embed a handful of
# Cyrillic tokens (company names, city names) without being UA/RU postings; a low bar
# would misclassify those, while 0.15 still catches short-but-genuinely-Cyrillic samples.
CYRILLIC_RATIO_THRESHOLD = 0.15

# UA-only vs RU-only spelling variants (distinguishing pairs), used as a case-insensitive
# whole-word stopword signal ONLY after the text has already cleared the Cyrillic-ratio
# threshold above. Not exhaustive — just enough genuinely UA-vs-RU-distinguishing pairs to
# break the tie between the two Slavic languages once Cyrillic dominance is established.
UA_STOPWORDS = frozenset(
    {
        "і",
        "цей",
        "також",
        "будь ласка",
        "дуже",
        "зараз",
    }
)
RU_STOPWORDS = frozenset(
    {
        "также",
        "или",
        "пожалуйста",
        "этот",
        "очень",
        "сейчас",
    }
)

_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _cyrillic_ratio(text: str) -> float:
    """Fraction of alphabetic characters in *text* that are Cyrillic (0.0 if none)."""
    alpha_chars = _ALPHA_RE.findall(text)
    if not alpha_chars:
        return 0.0
    cyrillic_count = sum(1 for ch in alpha_chars if _CYRILLIC_RE.match(ch))
    return cyrillic_count / len(alpha_chars)


def _count_stopword_hits(text_lower: str, stopwords: frozenset[str]) -> int:
    """Count case-insensitive whole-word/phrase hits of *stopwords* in *text_lower*."""
    hits = 0
    for stopword in stopwords:
        if " " in stopword:
            # Multi-word phrase (e.g. "будь ласка") — simple substring containment,
            # since word-boundary regex on a phrase with an internal space still works
            # via \b on both ends.
            if re.search(rf"\b{re.escape(stopword)}\b", text_lower):
                hits += 1
        else:
            if re.search(rf"\b{re.escape(stopword)}\b", text_lower):
                hits += 1
    return hits


def detect_language(text: str) -> str:
    """Deterministically classify *text* as ``"ua"``, ``"ru"``, or ``"en"``.

    Never raises — empty/whitespace-only input returns ``"en"``. This is the sole
    classification function; no LLM/ML fallback branch exists anywhere in this module.
    """
    if not text or not text.strip():
        return "en"

    if _cyrillic_ratio(text) < CYRILLIC_RATIO_THRESHOLD:
        return "en"

    text_lower = text.lower()
    ua_hits = _count_stopword_hits(text_lower, UA_STOPWORDS)
    ru_hits = _count_stopword_hits(text_lower, RU_STOPWORDS)

    if ua_hits > ru_hits:
        return "ua"
    if ru_hits > ua_hits:
        return "ru"
    # Tie (including 0-0): Cyrillic-dominant but inconclusive between ua/ru — degrade
    # to "en" per CONTEXT.md's locked decision rather than guessing.
    return "en"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministically detect ua/ru/en for an offer posting's text "
        "(never an LLM judgment call)."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Path to a text file to classify.")
    source.add_argument("--stdin", action="store_true", help="Read the text from stdin.")
    args = parser.parse_args()

    if args.stdin:
        text = sys.stdin.read()
    else:
        path = args.file.expanduser()
        if not path.is_file():
            print(f"Not a file: {path}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8", errors="replace")

    # Detection never fails on ordinary content — always print a token and exit 0.
    print(detect_language(text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
