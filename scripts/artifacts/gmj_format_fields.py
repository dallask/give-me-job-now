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

# Both gmj_schema_fields.py and this file live in scripts/artifacts/ — plain same-dir
# import, no sys.path insert needed within this file itself. (Callers importing THIS
# module from elsewhere are responsible for putting scripts/artifacts/ on sys.path,
# exactly as scripts/cv/gmj_render_cv.py already does for gmj_schema_fields.)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_schema_fields import CONTACT, WEBSITE_GROUPS  # noqa: E402


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
                lines.append(f"{str(label).capitalize()}: {url}")
    messengers = contact.get(messengers_key)
    messengers = messengers if isinstance(messengers, dict) else {}
    for label, handle in messengers.items():
        if handle:
            lines.append(f"{str(label).capitalize()}: {handle}")
    return lines
