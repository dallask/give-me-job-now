#!/usr/bin/env python3
"""Single source of the dashboard/child pipeline-root resolution (HON-01).

Every self-defaulting pipeline script (``gmj_runs.py``, ``gmj_batch.py``,
``gmj_merge_shortlists.py``) imports :func:`resolve_pipeline_dir` instead of hardcoding a
bare ``.pipeline`` literal, so a dashboard-launched child honors the operator's
``--pipeline-dir`` / ``GMJ_PIPELINE_DIR`` end to end. ``os.environ`` is read ONLY here — this
module is the single place the env→``.pipeline`` fallback is expressed.
"""

from __future__ import annotations

import os

ENV_VAR = "GMJ_PIPELINE_DIR"
DEFAULT_PIPELINE_DIR = ".pipeline"


def resolve_pipeline_dir(explicit: str | None = None) -> str:
    """Resolve the pipeline root: explicit arg > GMJ_PIPELINE_DIR env > '.pipeline'."""
    if explicit:
        return explicit
    return os.environ.get(ENV_VAR) or DEFAULT_PIPELINE_DIR
