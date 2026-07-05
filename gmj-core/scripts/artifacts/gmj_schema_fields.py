#!/usr/bin/env python3
"""Single owner of the candidate.yaml field-name schema (SCHEMA-06).

This module is the *one* place that names every top-level and nested-contact field
of ``config/candidate.yaml``. It mirrors the anti-drift discipline of
``scripts/artifacts/gmj_yaml_path.py`` (the single owner of the source-span *grammar*):
a module docstring that declares single-owner intent, followed by module-level
UPPERCASE tuple constants. Consumers — the renderer (``scripts/cv/gmj_render_cv.py``)
and the migration validators — import these constants rather than re-declaring key
literals, so a divergent second copy of the field names can no longer drift out of
sync (Pitfall 1 / threat T-09-02).

This is a pure name registry: no functions, no I/O, no schema loading. The strings
below are the field NAMES only; the *grammar* for walking them lives in
``yaml_path.resolve_path`` and is never re-implemented here.
"""

from __future__ import annotations

# Top-level candidate.yaml keys, in the order they appear in the live file.
TOP_LEVEL = (
    "name",
    "photo",
    "title",
    "summary",
    "contact",
    "expertise",
    "key_achievements",
    "languages",
    "professional_experience",
    "independent_projects",
    "education",
    "certifications",
)

# Fields nested under the top-level ``contact`` mapping.
CONTACT = ("phone", "email", "address", "website", "messengers")

# Grouping keys under ``contact.website``.
WEBSITE_GROUPS = ("personal", "company", "portfolio", "media")

# Fields of a single ``professional_experience[]`` item.
EXPERIENCE_FIELDS = (
    "company",
    "position",
    "role_progression",
    "location",
    "duration",
    "company_description",
    "linkedin",
    "achievements",
)
