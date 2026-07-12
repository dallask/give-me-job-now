#!/usr/bin/env python3
"""Resolve which CV template ``gmj_render_cv.py`` should use (TMPL-01, TMPL-02).

Implements the full explicit-flag > config > documented-fallback precedence (D-07), the
``default``/``random``/``all`` selection-mode semantics (D-04), per-offer/run rotation-state
reuse via an optional ``state_path`` so a Gate-B retry of the SAME offer always re-renders
with the SAME template (D-05/D-06), and never-hard-fail misconfiguration handling (D-09) --
every fallback path prints a structured stderr warning and returns
``DOCUMENTED_DEFAULT_TEMPLATE`` rather than raising.

D-06 tradeoff (documented explicitly, per plan instruction): rotation state lives inside the
SAME per-offer ``state.json`` that the rest of the pipeline already reads/writes
(``scripts/pipeline/gmj_state_write.py``'s read-modify-preserve idiom, mirrored verbatim
here) -- never a new standalone state file. The one exception is ``mode: all``'s round-robin
ordering, which needs a total order ACROSS distinct offers/runs that no single per-offer
``state.json`` can provide alone; that is resolved with ONE small shared counter file,
``state_path.parent.parent / "_cv_rotation_counter.json"`` (i.e.
``.pipeline/runs/_cv_rotation_counter.json``), colocated as a sibling of every per-run
subdirectory under the existing ``runs/`` tree -- still not a new independent state system,
just one extra small file living inside the already-trusted ``.pipeline/runs/`` directory.

Whenever ``state_path`` is provided, the FINAL resolved template filename is always recorded
into that state.json under ``cv_template_rotation.picked`` -- in EVERY mode (``default``,
``random``, ``all`` alike), not only the rotation modes. This closes RESEARCH.md's Open
Question 1: ``state.json`` is the single, universal cross-process channel a caller reads to
learn which template was actually used, including for wiring
``gmj_check_render_quality.py``'s ``--template-name`` argument accurately regardless of mode.

All error paths print a structured stderr message and return a safe fallback value -- never a
traceback (D-09, no hard-fail on misconfiguration).
"""

from __future__ import annotations

import fcntl
import json
import random
import re
import sys
from pathlib import Path

import yaml

DOCUMENTED_DEFAULT_TEMPLATE = "baxter.html"

# Mirrors gmj_batch.py's _ID_RE / _safe_id() guard class (V12 path-traversal), scoped to
# `.html` filenames: rejects "..", "/", "\\", and any non-".html" suffix in one check.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.html$")

_ROTATION_COUNTER_FILENAME = "_cv_rotation_counter.json"


def _is_safe_template_name(name: str) -> bool:
    """True when ``name`` is a safe single-component ``.html`` filename.

    Defense in depth: the regex alone would already reject a literal ".." substring (it is
    not in the allowed character class), but an explicit ".." check is kept anyway to mirror
    gmj_batch.py's _safe_id() belt-and-suspenders shape.
    """
    if not isinstance(name, str) or not name:
        return False
    if ".." in name:
        return False
    return bool(_SAFE_FILENAME_RE.match(name))


def _load_cv_config(prefs_path: Path) -> dict:
    """Return the ``cv:`` sub-dict of ``prefs_path``, or ``{}`` on any non-fatal problem.

    Never raises: a missing file, unreadable file, unparsable YAML, non-dict root, missing
    ``cv`` key, or non-dict ``cv`` value all degrade to ``{}`` (D-09). Uses ``yaml.safe_load``
    only, per this codebase's untrusted-input doctrine.
    """
    try:
        if not prefs_path.is_file():
            return {}
        raw = yaml.safe_load(prefs_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(raw, dict):
        return {}
    cv_cfg = raw.get("cv")
    if not isinstance(cv_cfg, dict):
        return {}
    return cv_cfg


def _effective_pool(cv_cfg: dict, templates_dir: Path) -> list[str]:
    """Filter ``cv_cfg['templates']`` to safe entries that exist under ``templates_dir``.

    Prints one stderr warning per rejected entry (unsafe name, or safe name but no matching
    file on disk) -- mirrors Test 12's traversal-filtering expectation and D-09's
    never-hard-fail contract.
    """
    raw_templates = cv_cfg.get("templates") or []
    if not isinstance(raw_templates, list):
        print(
            f"cv.templates must be a list; got {raw_templates!r}; treating as empty.",
            file=sys.stderr,
        )
        return []
    pool: list[str] = []
    for entry in raw_templates:
        if not _is_safe_template_name(entry):
            print(f"Rejecting unsafe cv.templates entry: {entry!r}", file=sys.stderr)
            continue
        if not (templates_dir / entry).is_file():
            print(
                f"cv.templates entry not found under {templates_dir}: {entry!r}",
                file=sys.stderr,
            )
            continue
        pool.append(entry)
    return pool


def _read_json_dict(path: Path) -> dict:
    """Read-modify-preserve idiom: return the JSON object at ``path``, or ``{}`` on any
    non-fatal problem (missing file, corrupt JSON, non-dict root)."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_json_dict(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_resolved_template(state_path: Path | None, chosen: str) -> None:
    """Persist ``chosen`` into ``state_path``'s ``cv_template_rotation.picked`` key.

    Read-modify-preserve: loads the full state dict, mutates only
    ``cv_template_rotation.picked`` (creating the sub-dict if absent, preserving any other
    keys already inside it, e.g. an ``all``-mode marker, and every sibling top-level key),
    writes the full dict back. No-op when ``state_path`` is ``None``. This is the SAME
    persistence call used by every mode (default/random/all) -- the single code path that
    ever writes ``cv_template_rotation.picked``.
    """
    if state_path is None:
        return
    state = _read_json_dict(state_path)
    rotation = state.get("cv_template_rotation")
    if not isinstance(rotation, dict):
        rotation = {}
    rotation["picked"] = chosen
    state["cv_template_rotation"] = rotation
    _write_json_dict(state_path, state)


def _pick_rotation(pool: list[str], mode: str, state_path: Path | None) -> str:
    """Resolve a rotation pick for ``mode in ("random", "all")`` against a non-empty ``pool``.

    D-05 reuse: with a ``state_path``, if a prior pick is already recorded AND still a member
    of ``pool``, return it unchanged -- checked BEFORE touching the shared "all"-mode counter,
    so a Gate-B retry of an already-assigned offer never advances the counter.
    """
    if state_path is not None:
        state = _read_json_dict(state_path)
        rotation = state.get("cv_template_rotation")
        if isinstance(rotation, dict):
            previously_picked = rotation.get("picked")
            if previously_picked in pool:
                return previously_picked

    if mode == "all":
        if state_path is None:
            chosen = random.choice(pool)
            return chosen
        counter_path = state_path.parent.parent / _ROTATION_COUNTER_FILENAME
        counter_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = counter_path.with_suffix(".json.lock")
        # Exclusive fcntl.flock for the ENTIRE read-modify-write critical section, same
        # idiom gmj_batch.py uses for its own shared manifest.json (CONC-03) — this counter
        # is genuinely concurrently written under parallel offer fan-out (02-REVIEW.md CR-02).
        with open(lock_path, "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            try:
                counter = _read_json_dict(counter_path)
                next_index = counter.get("next_index")
                if not isinstance(next_index, int) or isinstance(next_index, bool) or next_index < 0:
                    next_index = 0
                chosen = pool[next_index % len(pool)]
                _write_json_dict(counter_path, {"next_index": next_index + 1})
            finally:
                fcntl.flock(lockf, fcntl.LOCK_UN)
        _record_resolved_template(state_path, chosen)
        return chosen

    # mode == "random"
    chosen = random.choice(pool)
    _record_resolved_template(state_path, chosen)
    return chosen


def resolve_template(
    *,
    explicit_template: Path | None,
    no_template: bool,
    prefs_path: Path,
    state_path: Path | None = None,
    templates_dir: Path,
) -> str | None:
    """Resolve the CV template to use, per the explicit > config > fallback precedence.

    Precedence:
      1. ``no_template`` -> ``None`` (caller explicitly wants the ReportLab fallback).
      2. ``explicit_template is not None`` -> that path, unchanged (caller wins, D-07).
      3. Else resolve from ``config/preferences.yaml``'s ``cv:`` block per ``cv.mode``:
         - ``default`` -> ``cv.default`` if safe + present under ``templates_dir``, else
           ``DOCUMENTED_DEFAULT_TEMPLATE`` with a stderr warning.
         - ``random``/``all`` -> pick from the filtered, safe ``cv.templates`` pool, reusing
           the same pick for the same ``state_path`` (D-05); an empty/misconfigured pool
           falls back to ``DOCUMENTED_DEFAULT_TEMPLATE`` with a stderr warning.
      4. Whenever ``state_path`` is given, the final resolved name is ALWAYS recorded into
         that state.json's ``cv_template_rotation.picked`` key -- in every mode, not only
         random/all (RESEARCH.md Open Question 1).

    Never raises on misconfiguration or path-traversal input (D-09).
    """
    if no_template:
        return None
    if explicit_template is not None:
        return explicit_template

    cv_cfg = _load_cv_config(prefs_path)
    mode = cv_cfg.get("mode") or "default"

    if mode == "default":
        default_name = cv_cfg.get("default")
        if (
            isinstance(default_name, str)
            and _is_safe_template_name(default_name)
            and (templates_dir / default_name).is_file()
        ):
            chosen = default_name
        else:
            print(
                f"cv.default not usable ({default_name!r}); "
                f"falling back to {DOCUMENTED_DEFAULT_TEMPLATE!r}.",
                file=sys.stderr,
            )
            chosen = DOCUMENTED_DEFAULT_TEMPLATE
        _record_resolved_template(state_path, chosen)
        return chosen

    if mode in ("random", "all"):
        pool = _effective_pool(cv_cfg, templates_dir)
        if not pool:
            print(
                f"cv.templates is empty or entirely misconfigured for mode={mode!r}; "
                f"falling back to {DOCUMENTED_DEFAULT_TEMPLATE!r}.",
                file=sys.stderr,
            )
            chosen = DOCUMENTED_DEFAULT_TEMPLATE
            _record_resolved_template(state_path, chosen)
            return chosen
        return _pick_rotation(pool, mode, state_path)

    # Unrecognized mode value -- treat as "default" semantics via the same fallback path.
    print(f"Unrecognized cv.mode {mode!r}; falling back to {DOCUMENTED_DEFAULT_TEMPLATE!r}.",
          file=sys.stderr)
    chosen = DOCUMENTED_DEFAULT_TEMPLATE
    _record_resolved_template(state_path, chosen)
    return chosen
