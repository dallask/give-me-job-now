#!/usr/bin/env python3
"""Deterministic visual-diff for a candidate CV template (TEMPLATE-03 / TEMPLATE-04).

Determinism doctrine: DPI, diff canvas size, resample filter and colorspace are pinned
as module constants so the ≤0.10 visual-match bar is reproducible across machines and runs.

compare == ship: the diffed PDF is rendered through ``gmj_render_cv.py::render_weasyprint_html``
(the real ship path), NEVER by importing WeasyPrint's HTML class directly. A direct import
would skip the macOS DYLD fallback and the base64 photo embed and thus diverge from the
shipped artifact. The shipped PDF is rasterized (page 1) via PyMuPDF (fitz) before diffing.

CLI:
    python3 scripts/cv/gmj_visual_diff.py \\
        --config config/candidate.yaml \\
        --template templates/cv/<slug>.html \\
        --reference sources/design/<slug>.png

Prints a single float diff-ratio in [0, 1] (0.0 == identical, ~1.0 == maximally different)
and exits 0; malformed inputs exit 1 with a stderr message and no traceback.

Importable API:
    diff_ratio(ship_png, ref_png) -> float
    pdf_first_page_png(pdf_path, png_path, dpi=RASTER_DPI) -> None
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF — PDF -> PNG rasterizer
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/cv/ -> repo root

# Import the ship render from gmj_render_cv.py (same sibling-import idiom gmj_render_cv.py uses for
# schema_fields). NEVER import weasyprint directly here — compare==ship requires the exact
# ship path (DYLD fallback + embedded photo). (gmj_render_cv.py:22-23, :438-465)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/cv on path
from gmj_render_cv import (  # noqa: E402
    render_weasyprint_html,
    candidate_with_embedded_photo,
    load_candidate,
    repo_root_from_config,
    _load_labels,
    lang_from_config_path,
)

# --- Pinned determinism constants (reproducible ≤0.10 bar) -----------------------------
RASTER_DPI = 150
DIFF_SIZE = (1000, 1414)  # ~A4 210:297 aspect; pin for size-invariant reproducibility
RESAMPLE = Image.LANCZOS
DIFF_MODE = "RGB"  # pin colorspace — drop alpha so the MAE is stable

_TEMPLATES_DIR = (REPO_ROOT / "templates" / "cv").resolve()


def pdf_first_page_png(pdf_path: Path, png_path: Path, dpi: int = RASTER_DPI) -> None:
    """Rasterize page 1 of the SHIPPED pdf to PNG at a pinned DPI."""
    doc = fitz.open(str(pdf_path))
    try:
        doc[0].get_pixmap(dpi=dpi).save(str(png_path))
    finally:
        doc.close()


def diff_ratio(ship_png: Path, ref_png: Path) -> float:
    """Normalized mean-absolute-error over RGB arrays resized to DIFF_SIZE.

    0.0 == identical, ~1.0 == maximally different. Deterministic + size-invariant
    (both images are resized to DIFF_SIZE before comparison).
    """
    a = np.asarray(
        Image.open(ship_png).convert(DIFF_MODE).resize(DIFF_SIZE, RESAMPLE),
        dtype=np.float32,
    )
    b = np.asarray(
        Image.open(ref_png).convert(DIFF_MODE).resize(DIFF_SIZE, RESAMPLE),
        dtype=np.float32,
    )
    return float(np.abs(a - b).mean() / 255.0)


def _assert_under(path: Path, root: Path, what: str) -> Path:
    """Resolve ``path`` and assert it stays under ``root`` (path-traversal defence, V12)."""
    resolved = path.expanduser().resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Refusing to read {what} outside {root_resolved}: {resolved}")
    return resolved


def _validate_template(template_path: Path) -> Path:
    """Reject a --template resolving outside templates/cv/ or using path-traversal (V5/V12)."""
    raw = str(template_path)
    if ".." in Path(raw).parts:
        raise ValueError(f"Refusing --template with '..' path component: {raw}")
    resolved = template_path.expanduser().resolve()
    if _TEMPLATES_DIR not in resolved.parents:
        raise ValueError(f"Refusing --template outside {_TEMPLATES_DIR}: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Template not found: {resolved}")
    return resolved


def compute_diff_ratio(config_path: Path, template_path: Path, reference_path: Path,
                       lang: str | None = None) -> float:
    """Render the template through the ship path, rasterize it, diff against the reference."""
    template = _validate_template(template_path)
    reference = _assert_under(reference_path, REPO_ROOT, "--reference")
    if not reference.is_file():
        raise ValueError(f"Reference screenshot not found: {reference}")

    resolved_lang = lang_from_config_path(config_path, lang)
    repo_root = repo_root_from_config(config_path)
    labels = _load_labels(repo_root, resolved_lang)
    candidate = load_candidate(config_path, resolved_lang)
    cand = candidate_with_embedded_photo(candidate, repo_root)

    with tempfile.TemporaryDirectory() as td:
        ship_pdf = Path(td) / "ship.pdf"
        ship_png = Path(td) / "ship.png"
        render_weasyprint_html(
            cand, template, ship_pdf,
            repo_root=repo_root, labels=labels, lang=resolved_lang,
        )
        pdf_first_page_png(ship_pdf, ship_png)
        return diff_ratio(ship_png, reference)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic compare==ship visual-diff of a CV template vs a reference screenshot."
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to candidate YAML")
    parser.add_argument("--template", type=Path, required=True, help="templates/cv/<slug>.html")
    parser.add_argument("--reference", type=Path, required=True, help="pasted design screenshot (under sources/)")
    parser.add_argument("--lang", type=str, default=None, help="Override language (en|ua|ru)")
    args = parser.parse_args()
    try:
        if not args.config.is_file():
            raise ValueError(f"Config not found: {args.config}")
        ratio = compute_diff_ratio(args.config, args.template, args.reference, args.lang)
        print(ratio)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"gmj_visual_diff: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
