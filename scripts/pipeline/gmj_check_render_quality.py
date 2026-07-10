#!/usr/bin/env python3
"""Deterministic post-render visual + content QA pass for a rendered CV PDF (QA-02).

Detects three structural defect classes in a rendered CV PDF, using PyMuPDF (``fitz``):

1. **Missing sections** — a ``config/candidate.yaml`` top-level key with non-empty data
   whose expected rendered label never appears in the PDF's extracted text (the Phase 41
   PIPE-11 bug class: Education/Languages/Certifications sections silently dropped by a
   CSS clipping bug).
2. **Clipped content** — a text span whose bounding box extends beyond the page's cropbox,
   detected independently of the missing-sections check via ``page.get_text("dict")``
   block/line/span geometry.
3. **Empty pages / overlapping regions** — a page with zero text blocks, or two block-level
   bounding boxes that substantially overlap, both via the same geometry walk.

QA-01 (advisory-only, non-bypassable-gate boundary): this is a deterministic script, NOT a
Gate C extension, and it is never wired into ``scripts/pipeline/gmj_check_delivery.py``'s
delivery precondition — a defect finding must never silently become a hard gate.

QA-03 (exit-0-always contract): a SUCCESSFUL run of this check (the PDF opened, the YAML
parsed, all three checks completed) always exits 0, regardless of how many defects were
found. Only a genuine script-execution failure — a missing ``--pdf``/``--candidate-yaml``
path, invalid YAML, or an unopenable/corrupt PDF — is a legitimate non-zero exit.

Control flow mirrors ``scripts/pipeline/gmj_check_delivery.py`` (argparse guard-and-parse,
stderr-only error messages, no traceback). PyMuPDF usage (``import fitz``, the
``try/finally: doc.close()`` open/close discipline) mirrors ``scripts/cv/gmj_visual_diff.py``.

Section-name registry discipline (SCHEMA-06 anti-drift precedent): the missing-sections
check imports ``scripts/artifacts/gmj_schema_fields.py::TOP_LEVEL`` and reads
``config/i18n/labels.yaml`` directly — it never hand-maintains a second section-name list.

Per-template label mapping (CR-01 fix): which label string a ``candidate.yaml`` section
renders under — and whether it renders at all — depends on which render path produced the
PDF. ``scripts/cv/gmj_render_cv.py``'s actual **default** path (no ``--template``/
``--no-template`` flag) renders ``templates/cv/baxter.html`` via WeasyPrint, which uses a
different label-key mapping than the ``--no-template`` ReportLab fallback (``render_reportlab()``)
and hardcodes several section headings as English literals that never localize. An
unrecognized ``--template-name`` value falls back to the ``baxter.html`` table (same
best-effort semantics as any other unrecognized/custom template). See ``_LABEL_TABLES`` below
and pass ``--template-name`` to select the correct table (default: ``baxter.html``, matching the
renderer's own default-path precedence).

Pinned tunable constant: ``--clip-tolerance`` (points, default ``DEFAULT_CLIP_TOLERANCE``)
governs the clipped-content bbox-vs-cropbox comparison; the block-overlap-area tolerance for
the empty/overlapping check is derived from it by squaring (``DEFAULT_OVERLAP_AREA_TOLERANCE
= DEFAULT_CLIP_TOLERANCE ** 2``, points²) rather than reusing the raw linear value, since the
two checks compare against different-unit quantities (WR-01 fix).

CLI:
    python3 scripts/pipeline/gmj_check_render_quality.py \\
        --pdf output/cv/example.pdf \\
        --candidate-yaml config/candidate.yaml \\
        --lang en

Prints ``defects: <N>`` on the first stdout line, followed by one line per defect, and
always returns 0 on a successful run. Returns 1 (stderr message, no traceback) only when
``--pdf``/``--candidate-yaml`` is not a file, the candidate YAML fails to parse, or the PDF
fails to open.

Importable API:
    find_missing_sections(candidate, labels) -> list[dict]
    find_clipped_content(doc, tolerance) -> list[dict]
    find_empty_and_overlapping(doc, tolerance) -> list[dict]
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/pipeline/ -> repo root

sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from gmj_schema_fields import TOP_LEVEL  # noqa: E402  single-owner section-name registry

DEFAULT_LANG = "en"
LANGS = ("en", "ua", "ru")

# Pinned, tunable default LINEAR tolerance (points) for the clipped-content bbox-vs-cropbox
# check. 3.0pt comfortably exceeds normal sub-pixel rendering jitter while still catching a
# genuine clipping bug.
DEFAULT_CLIP_TOLERANCE = 3.0

# WR-01 fix: the block-overlap-area check (find_empty_and_overlapping) compares against an
# AREA in points^2, not a linear distance in points -- reusing DEFAULT_CLIP_TOLERANCE's raw
# value there made the overlap check far more sensitive than intended (a 3.0pt^2 area is
# only a ~1.7pt x 1.7pt overlap rectangle, smaller than a single character's kerning box).
# Squaring the linear tolerance keeps the two checks dimensionally consistent and preserves
# the "comfortably exceeds normal sub-pixel rendering jitter" intent for the overlap check.
DEFAULT_OVERLAP_AREA_TOLERANCE = DEFAULT_CLIP_TOLERANCE ** 2

# TOP_LEVEL keys with no section heading of their own (no label lookup makes sense).
_NO_LABEL_KEYS = frozenset({"name", "photo", "title", "contact"})

# A "literal" entry means the template hardcodes an English heading string rather than
# looking it up via labels.yaml (so it never localizes, and the expected string is fixed
# regardless of --lang). A ``None`` entry (or a key entirely absent from a template's table)
# means that TOP_LEVEL key is never rendered by that template at all -- e.g.
# ``independent_projects`` has no matching block in templates/cv/baxter.html -- and must be
# skipped rather than checked, or every candidate with that section would false-positive.
_LITERAL = object()

# Per-template expected-label tables (CR-01 fix). Keyed by the template name that
# gmj_render_cv.py actually used to produce the PDF (see _resolve_template_name()), each
# value maps a candidate.yaml TOP_LEVEL key to either:
#   - a labels.yaml label key (str) to look up via `labels[key]`, localized per --lang, or
#   - _LITERAL, meaning the template hardcodes an English string (see _LITERAL_TEXT_FOR), or
#   - omitted entirely, meaning that section is never rendered by this template (must not be
#     checked -- e.g. baxter.html has no independent_projects block at all).
_LABEL_TABLES: dict[str, dict[str, str | object]] = {
    # scripts/cv/gmj_render_cv.py::render_reportlab() -- the --no-template fallback path.
    # Verified against its own lbl('experience', ...) / lbl('summary', ...) / etc. calls:
    # every section key maps 1:1 to a labels.yaml key of the same or a documented alias name.
    "reportlab": {
        "summary": "summary",
        "expertise": "expertise",
        "key_achievements": "key_achievements",
        "languages": "languages",
        "professional_experience": "experience",
        "independent_projects": "independent_projects",
        "education": "education",
        "certifications": "certifications",
    },
    # templates/cv/baxter.html -- the renderer's actual DEFAULT path (no --template/
    # --no-template flag). Verified by reading the template source directly:
    #   - professional_experience renders under labels.job_experience ("Job Experience"),
    #     NOT labels.experience ("Experience") -- baxter.html:588.
    #   - summary, expertise, key_achievements, and certifications are hardcoded English
    #     literals, never looked up via labels.* at all -- baxter.html:579,633,647,537.
    #   - independent_projects has no matching block in baxter.html: never rendered, must
    #     be omitted here (not mapped to anything) so it is never checked.
    "baxter.html": {
        "summary": _LITERAL,
        "expertise": _LITERAL,
        "key_achievements": _LITERAL,
        "languages": "languages",
        "professional_experience": "job_experience",
        "education": "education",
        "certifications": _LITERAL,
        # independent_projects intentionally omitted: baxter.html never renders it.
    },
}

# English literal heading text hardcoded by a template for a _LITERAL-mapped key. These
# never localize (a known baxter.html gap on ua/ru — the template itself would need to
# switch to labels.* lookups to fix that; this table just records reality so the QA check
# doesn't false-positive on it).
_LITERAL_TEXT_FOR: dict[str, dict[str, str]] = {
    "baxter.html": {
        "summary": "About Me",
        "expertise": "Technical Expertise",
        "key_achievements": "Key Achievements",
        "certifications": "Certifications",
    },
}

DEFAULT_TEMPLATE_NAME = "baxter.html"

_TRUNCATE_LEN = 60


def _normalize(text: str) -> str:
    """NFC-normalize, casefold, and collapse whitespace for locale-safe substring comparison."""
    normalized = unicodedata.normalize("NFC", text or "")
    return " ".join(normalized.casefold().split())


def _truncate(text: str, length: int = _TRUNCATE_LEN) -> str:
    text = text.strip()
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def _is_present(value: object) -> bool:
    """A TOP_LEVEL key is "present" when its value is truthy (non-empty str/list/dict)."""
    return bool(value)


def _resolve_template_name(template_name: str | None) -> str:
    """Map an arbitrary --template-name value to a known _LABEL_TABLES key.

    Any name not recognized (a custom/unknown template, or a plain filename like
    "baxter.html") falls back to DEFAULT_TEMPLATE_NAME's table, matching
    gmj_render_cv.py's own default-path precedence (best-effort rather than a hard error,
    since an unrecognized custom template's label usage is unknowable in general).
    """
    if template_name in _LABEL_TABLES:
        return template_name
    return DEFAULT_TEMPLATE_NAME


def _expected_labels(
    candidate: dict, labels: dict, template_name: str = DEFAULT_TEMPLATE_NAME,
) -> list[tuple[str, str]]:
    """Return (candidate_key, expected_label) pairs for every present, label-bearing key
    that ``template_name`` actually renders (per-template mapping, CR-01 fix)."""
    resolved = _resolve_template_name(template_name)
    label_key_for = _LABEL_TABLES.get(resolved, _LABEL_TABLES[DEFAULT_TEMPLATE_NAME])
    literal_text_for = _LITERAL_TEXT_FOR.get(resolved, {})
    expected: list[tuple[str, str]] = []
    for key in TOP_LEVEL:
        if key in _NO_LABEL_KEYS:
            continue
        if key not in label_key_for:
            # This template never renders this section at all (e.g. baxter.html has no
            # independent_projects block) -- must not be checked, or every candidate with
            # that section would false-positive a missing_section defect.
            continue
        if not _is_present(candidate.get(key)):
            continue
        label_key = label_key_for[key]
        if label_key is _LITERAL:
            label = literal_text_for.get(key)
        else:
            label = labels.get(label_key)
        if not label:
            continue
        expected.append((key, label))
    return expected


def find_missing_sections(
    candidate: dict, labels: dict, rendered_text: str = "",
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> list[dict]:
    """Flag any expected section label absent from the rendered PDF's normalized text.

    A key is "present" (expected to render) when its ``candidate.yaml`` value is truthy.
    Each present, label-bearing key is mapped to its expected rendered label string via
    ``labels`` and ``template_name`` (a ``TOP_LEVEL`` key with no matching label entry, e.g.
    ``name``/``photo``/``title``/``contact``, or a key the template never renders at all,
    e.g. ``independent_projects`` under ``baxter.html``, is skipped). Both the expected
    label and ``rendered_text`` are normalized (NFC + casefold + whitespace collapse) before
    the substring comparison, so ua/ru Cyrillic round-trips correctly.
    """
    normalized_text = _normalize(rendered_text)
    defects: list[dict] = []
    for key, label in _expected_labels(candidate, labels, template_name):
        if _normalize(label) not in normalized_text:
            defects.append({"type": "missing_section", "key": key, "label": label})
    return defects


def find_clipped_content(doc: "fitz.Document", tolerance: float = DEFAULT_CLIP_TOLERANCE) -> list[dict]:
    """Flag any text span whose bbox extends beyond its page's cropbox by more than ``tolerance``."""
    defects: list[dict] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        cropbox = page.cropbox
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span.get("bbox")
                    if not bbox:
                        continue
                    x0, y0, x1, y1 = bbox
                    if (
                        x0 < cropbox.x0 - tolerance
                        or x1 > cropbox.x1 + tolerance
                        or y0 < cropbox.y0 - tolerance
                        or y1 > cropbox.y1 + tolerance
                    ):
                        defects.append(
                            {
                                "type": "clipped_content",
                                "page": page_index + 1,
                                "text": _truncate(span.get("text", "")),
                            }
                        )
    return defects


def _bbox_overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection area of two (x0, y0, x1, y1) rectangles; 0.0 when they don't overlap."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return (ix1 - ix0) * (iy1 - iy0)


def _block_text(block: dict) -> str:
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
    return "".join(parts)


def find_empty_and_overlapping(
    doc: "fitz.Document", tolerance: float = DEFAULT_OVERLAP_AREA_TOLERANCE,
) -> list[dict]:
    """Flag zero-block pages (empty_page) and pairs of substantially-overlapping blocks.

    ``tolerance`` here is an AREA in points^2 (WR-01 fix) -- NOT the same unit as
    ``find_clipped_content``'s linear-points ``tolerance`` parameter of the same name.
    Callers deriving both from a single CLI knob should square the linear value (see
    ``DEFAULT_OVERLAP_AREA_TOLERANCE``); the parameter name is kept as ``tolerance`` for
    call-site compatibility, but its unit differs from ``find_clipped_content``'s.
    """
    defects: list[dict] = []
    for page_index in range(doc.page_count):
        page = doc[page_index]
        page_dict = page.get_text("dict")
        blocks = page_dict.get("blocks", [])
        if not blocks:
            defects.append({"type": "empty_page", "page": page_index + 1})
            continue

        for i in range(len(blocks)):
            bbox_i = blocks[i].get("bbox")
            if not bbox_i:
                continue
            for j in range(i + 1, len(blocks)):
                bbox_j = blocks[j].get("bbox")
                if not bbox_j:
                    continue
                if _bbox_overlap_area(tuple(bbox_i), tuple(bbox_j)) > tolerance:
                    defects.append(
                        {
                            "type": "overlapping_regions",
                            "page": page_index + 1,
                            "text_a": _truncate(_block_text(blocks[i])),
                            "text_b": _truncate(_block_text(blocks[j])),
                        }
                    )
    return defects


def _format_defect(defect: dict) -> str:
    kind = defect["type"]
    if kind == "missing_section":
        return f"missing_section: {defect['key']} ({defect['label']})"
    if kind == "clipped_content":
        return f'clipped_content: page {defect["page"]}: "{defect["text"]}"'
    if kind == "empty_page":
        return f"empty_page: page {defect['page']}"
    if kind == "overlapping_regions":
        return f'overlapping_regions: page {defect["page"]}: "{defect["text_a"]}" / "{defect["text_b"]}"'
    return f"unknown_defect: {defect}"  # pragma: no cover — defensive


def run_checks(
    pdf_path: Path, candidate_yaml_path: Path, labels_path: Path, lang: str, tolerance: float,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> tuple[list[dict], str | None]:
    """Run all three checks. Returns (defects, error_message). error_message set only on
    a genuine script-execution failure (bad YAML, unopenable PDF, or a missing labels file
    that isn't the intentional all-literal-only case -- see WR-02)."""
    try:
        candidate = yaml.safe_load(candidate_yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [], f"Invalid candidate YAML: {exc}"
    if not isinstance(candidate, dict):
        return [], "Candidate YAML root must be a mapping."

    all_labels: dict = {}
    if labels_path.is_file():
        try:
            all_labels = yaml.safe_load(labels_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            return [], f"Invalid labels YAML: {exc}"
    else:
        # WR-02: a missing (not just malformed) labels_path silently degraded the
        # missing-sections check to a total no-op (every TOP_LEVEL key skipped because
        # labels.get(...) is always falsy), while still printing "defects: 0" as if the
        # check ran successfully. Since this check's entire purpose is catching
        # silently-dropped sections, treat a missing labels file as a script-execution
        # failure rather than a quiet no-op -- an operator with a bad --labels override
        # gets a loud error instead of a false "all clear".
        return [], f"Labels file not found: {labels_path}"
    labels = all_labels.get(lang) or all_labels.get(DEFAULT_LANG) or {}
    if not labels:
        print(
            f"Warning: no '{lang}'/'{DEFAULT_LANG}' labels found in {labels_path} -- "
            "the missing-sections check may under-report for every section that only has "
            "a labels.yaml-backed (non-literal) heading.",
            file=sys.stderr,
        )

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 — fitz raises FileDataError/RuntimeError, not OSError
        return [], f"Could not open PDF: {exc}"

    try:
        full_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
        defects: list[dict] = []
        defects.extend(find_missing_sections(candidate, labels, full_text, template_name))
        defects.extend(find_clipped_content(doc, tolerance))
        # WR-01: area_tolerance is in points^2, not the same unit as the linear `tolerance`
        # (points) -- square it here rather than passing the raw linear value through.
        defects.extend(find_empty_and_overlapping(doc, tolerance ** 2))
        return defects, None
    finally:
        doc.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Advisory-only deterministic post-render QA check for a rendered CV PDF "
            "(missing sections, clipped content, empty/overlapping regions). Always exits 0 "
            "on a successful check run, regardless of defect count (QA-01/QA-03)."
        )
    )
    parser.add_argument("--pdf", type=Path, required=True, help="Path to the rendered CV PDF")
    parser.add_argument(
        "--candidate-yaml", type=Path, required=True,
        help="Path to the candidate YAML used for this render",
    )
    parser.add_argument(
        "--labels", type=Path, default=REPO_ROOT / "config" / "i18n" / "labels.yaml",
        help="Path to config/i18n/labels.yaml (default: repo config)",
    )
    parser.add_argument("--lang", default=DEFAULT_LANG, choices=list(LANGS), help="Output language")
    parser.add_argument(
        "--clip-tolerance", type=float, default=DEFAULT_CLIP_TOLERANCE,
        help=(
            "Linear tolerance in points for the bbox-vs-cropbox clipped-content check "
            f"(default: {DEFAULT_CLIP_TOLERANCE}). The block-overlap-area check derives its "
            "own points^2 tolerance by squaring this value (WR-01)."
        ),
    )
    parser.add_argument(
        "--template-name", default=DEFAULT_TEMPLATE_NAME,
        help=(
            "Which render path produced --pdf, for missing-sections label mapping (CR-01): "
            "'baxter.html' (default, matches gmj_render_cv.py's own default HTML template "
            "path) or 'reportlab' (the --no-template fallback path). An unrecognized value "
            f"falls back to the {DEFAULT_TEMPLATE_NAME!r} table."
        ),
    )
    args = parser.parse_args()

    pdf_path = args.pdf.expanduser()
    if not pdf_path.is_file():
        print(f"Not a file: {pdf_path}", file=sys.stderr)
        return 1

    candidate_yaml_path = args.candidate_yaml.expanduser()
    if not candidate_yaml_path.is_file():
        print(f"Not a file: {candidate_yaml_path}", file=sys.stderr)
        return 1

    defects, error = run_checks(
        pdf_path, candidate_yaml_path, args.labels.expanduser(), args.lang, args.clip_tolerance,
        args.template_name,
    )
    if error is not None:
        print(error, file=sys.stderr)
        return 1

    print(f"defects: {len(defects)}")
    for defect in defects:
        print(_format_defect(defect))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
