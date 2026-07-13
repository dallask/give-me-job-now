#!/usr/bin/env python3
"""Single owner of dict/list-safe candidate.yaml structured-field formatting (PIPE-02).

Every field that is a container in ``config/candidate.yaml`` (``contact.email`` is a
list, ``contact.website`` is a nested mapping of URL-list groups plus a label->url
``media`` dict) must never reach a rendered document as a raw Python ``repr()`` —
that leaks ``['a', 'b']``/``{'k': 'v'}`` container syntax into human-facing PDF/HTML
output. This module is the ONE place that turns those containers into plain display
strings, consumed by BOTH CV render backends in ``scripts/cv/gmj_render_cv.py``:

- ``render_reportlab()`` calls :func:`contact_lines` directly (Python call).
- ``render_weasyprint_html()`` registers :func:`contact_lines` as the Jinja filter
  ``contact_lines`` (``env.filters["contact_lines"] = contact_lines``), so every HTML
  template consumes the identical implementation — never a second, template-authored
  copy of the same formatting logic.

Field names come from the ``gmj_schema_fields`` registry (SCHEMA-06) rather than being
re-declared here, so a rename of the schema owner cannot silently drift this module
out of sync.
"""

from __future__ import annotations

from pathlib import Path
import sys

_MALFORMED_ROW_PREVIEW_LEN = 80

# Both gmj_schema_fields.py and this file live in scripts/artifacts/ — plain same-dir
# import, no sys.path insert needed within this file itself. (Callers importing THIS
# module from elsewhere are responsible for putting scripts/artifacts/ on sys.path,
# exactly as scripts/cv/gmj_render_cv.py already does for gmj_schema_fields.)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_schema_fields import CONTACT, WEBSITE_GROUPS  # noqa: E402


def _label_and_punctuation_safe(label: str, value: str) -> str:
    """Format a single ``f"{label.capitalize()}: {value}"`` line, stripping a
    pre-existing "Label: " prefix already embedded in ``value`` (case-insensitive,
    matching this same key's own synthesized label, with or without a following
    space) and at most one trailing sentence-punctuation character (``.``/``,``/
    ``;``) — but ONLY when that character is not immediately preceded by ``/``,
    which preserves real trailing-slash URLs while removing sentence-appended
    punctuation after a bare domain/path (02-UAT.md gap 3).
    """
    text = str(value).strip()
    canonical_label = str(label).capitalize()
    for prefix_label in (canonical_label, str(label)):
        prefix = f"{prefix_label}:"
        if text[: len(prefix)].casefold() == prefix.casefold():
            text = text[len(prefix):].lstrip()
            break
    if text and text[-1] in ".,;" and (len(text) < 2 or text[-2] != "/"):
        text = text[:-1]
    return f"{canonical_label}: {text}"


def contact_lines(contact: dict) -> list[str]:
    """Build contact strings by SHAPE — never by string-formatting a bare container.

    Consumes the nested v2.0 ``contact`` schema (email is a list, ``website`` is a mapping
    of ``personal``/``company``/``portfolio`` URL lists plus a ``media`` label->url dict, and
    ``messengers`` is a label->handle dict). Every access is guarded with ``or []`` / ``or {}``
    and every appended line is a plain string, so no ``[`` or ``{`` container-repr can ever
    leak into the rendered output (SCHEMA-02). Group names come from the ``WEBSITE_GROUPS``
    registry (SCHEMA-06) rather than being re-declared here.

    A non-dict ``contact`` argument (e.g. ``None``, a list) returns ``[]`` without raising.
    """
    # Field names come from the CONTACT registry (SCHEMA-06) — never re-declared as
    # bare literals here, so a rename of the schema owner cannot silently drift.
    phone_key, email_key, address_key, website_key, messengers_key = CONTACT
    lines: list[str] = []
    if not isinstance(contact, dict):
        return lines
    if contact.get(phone_key):
        lines.append(f"Phone: {contact[phone_key]}")
    emails = contact.get(email_key) or []
    if emails:
        if isinstance(emails, (list, tuple)):
            joined = ", ".join(str(e) for e in emails)
        else:
            joined = str(emails)
        if joined:
            lines.append(f"Email: {joined}")
    if contact.get(address_key):
        lines.append(str(contact[address_key]))
    web = contact.get(website_key) or {}
    if isinstance(web, dict):
        # URL-list groups (every WEBSITE_GROUPS entry except the "media" label→url dict).
        for group in WEBSITE_GROUPS:
            if group == "media":
                continue
            for url in web.get(group) or []:
                if url:
                    lines.append(str(url))
        media = web.get("media")
        media = media if isinstance(media, dict) else {}
        for label, url in media.items():
            if url:
                lines.append(_label_and_punctuation_safe(label, url))
    messengers = contact.get(messengers_key)
    messengers = messengers if isinstance(messengers, dict) else {}
    for label, handle in messengers.items():
        if handle:
            lines.append(_label_and_punctuation_safe(label, handle))
    return lines


def languages_rows(languages: object) -> list[dict]:
    """Guard candidate.languages by SHAPE — never iterate a non-list-of-dicts value.

    ``config/candidate.yaml``'s ``languages`` field is documented as a list of
    ``{language, proficiency}`` dicts, but real composer-emitted drafts have shown up
    as a bare prose string (TMPL-04, ``03-VERIFICATION.md``'s failed Truth #2 /
    ``03-REVIEW.md``'s CR-01) — a shape that, iterated naively, explodes character by
    character into the rendered output. This is the single choke point both
    ``render_reportlab()`` (direct Python call, mirroring how it already calls
    :func:`contact_lines`) and every Jinja CV template (via the ``languages_rows``
    filter, mirroring ``env.filters["contact_lines"]``) route through.

    Any input that is not a ``list`` (a bare string, ``None``, or a single ``dict``)
    returns ``[]`` — a dict is iterable but iterating it yields its keys as strings,
    the same character/key-explosion risk as the bare-string case, so the guard is
    ``isinstance(languages, list)`` specifically, not merely "is not str". Within an
    otherwise-valid list, any non-dict entries are silently dropped (mirrors
    ``render_reportlab()``'s existing ``isinstance(row, dict)`` guard for the
    already-correct case). A well-formed ``list[dict]`` is returned unchanged — same
    dicts, same order, same length — zero data loss for the already-correct shape.
    """
    if not isinstance(languages, list):
        return []
    return [row for row in languages if isinstance(row, dict)]


def expertise_skills_text(skills: object) -> str:
    """Guard ``candidate.expertise[N].skills`` by SHAPE — never iterate a bare string.

    ``config/candidate.yaml``'s per-block ``expertise[N].skills`` field is documented as
    a list of short term strings, but a real composer-emitted draft has shown up as a
    single already-display-ready prose string (e.g. "PHP frameworks expertise includes
    Laravel, Symfony, ..." — 02-UAT.md gap 4/TMPL-04-adjacent). Jinja's ``join`` filter
    iterates any string character-by-character, exploding it into an unreadable
    single-letter-comma-joined mess. This is the SINGLE shared choke point both render
    backends route through: the Jinja/WeasyPrint template path (``baxter.html``) via the
    ``expertise_skills_text`` filter, and ``render_reportlab()`` (``scripts/cv/gmj_render_cv.py``)
    via a direct call — mirroring how :func:`languages_rows` is the shared shape-guard for
    ``candidate.languages``. ``render_reportlab()`` previously had its own inline
    ``isinstance(skills, list)`` check that silently dropped bare-string skills instead of
    splitting them character-by-character (a narrower symptom of the same defect class,
    caught by code review and closed by routing it through this same helper).

    A ``list`` input is joined with ``", "`` after coercing each item with ``str()`` and
    dropping falsy entries — parity with ``render_reportlab()``'s pre-existing
    ``", ".join(str(s) for s in skills)`` list-rendering behavior. A
    non-empty string input (the real defect shape) is returned UNCHANGED as a single
    value — it is already display-ready text, not a container to iterate. Any other
    input (``None``, ``{}``, an empty string, other types) returns ``""`` — the same
    "no crash, no garbage" contract as this module's other helpers.
    """
    if isinstance(skills, list):
        return ", ".join(str(s) for s in skills if s)
    if isinstance(skills, str) and skills:
        return skills
    return ""


def education_rows(education: object) -> list[dict]:
    """Guard ``candidate.education`` by SHAPE — never treat a malformed row as a record.

    ``config/candidate.yaml``'s ``education`` field is documented as a list of
    ``{institution, program, duration, location}`` dicts, but the draft-to-CV-YAML
    bridge (``gmj_draft_to_cv_yaml.py``) has been shown to write a BARE STRING as a
    list element when a composer citation targets a whole-object ``source_span`` like
    ``education[0]`` instead of a specific field within it (PIPEFIX-02, per
    07-RESEARCH.md's confirmed root-cause reproduction) — the entire claim-text string
    becomes the list item, so ``education`` becomes a list of strings, not dicts. This
    is the SINGLE shared choke point both render backends route through, mirroring
    :func:`languages_rows`'s existing single-owner shape-guard pattern:

    - ``render_reportlab()`` (``scripts/cv/gmj_render_cv.py``) calls this directly,
      replacing its previous inline
      ``[row for row in edu if isinstance(row, dict) and (row.get('institution') or
      row.get('program'))]`` list comprehension (same filtering predicate, now with
      the added warning side effect below).
    - The Jinja/``baxter.html`` render path consumes this indirectly: it is called as
      a Python pre-filter inside ``candidate_for_template()`` BEFORE the candidate
      dict reaches the Jinja template render call, so ``baxter.html``'s existing
      ``edu.institution``/``edu.program`` guards become a redundant second layer
      rather than the only line of defense.

    Unlike :func:`languages_rows` (which silently drops malformed rows with zero
    signal), a REJECTED row here is not silent: every non-dict value, or a dict
    missing both ``institution`` and ``program``, is dropped AND a single structured
    warning is printed to stderr naming the row's index and a truncated preview of its
    actual value — the "loud warning on malformed row shape" hardening this task
    implements (T-07-10, 07-RESEARCH.md's Open Question 2). This never raises; the
    render must still exit 0.

    A non-``list`` input (``None``, a bare string, a dict) returns ``[]`` without
    warning — the field is simply absent/not-a-list, not a malformed-row-within-a-list
    case, mirroring :func:`languages_rows`'s top-level guard.
    """
    if not isinstance(education, list):
        return []
    rows: list[dict] = []
    for idx, row in enumerate(education):
        if isinstance(row, dict) and (row.get("institution") or row.get("program")):
            rows.append(row)
            continue
        preview = repr(row)
        if len(preview) > _MALFORMED_ROW_PREVIEW_LEN:
            preview = preview[:_MALFORMED_ROW_PREVIEW_LEN] + "..."
        print(
            f"Warning: skipping malformed education row at index {idx} "
            f"(expected a dict with 'institution' or 'program', got {type(row).__name__}: "
            f"{preview})",
            file=sys.stderr,
        )
    return rows
