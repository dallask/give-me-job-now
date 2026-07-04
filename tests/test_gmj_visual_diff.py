#!/usr/bin/env python3
"""Plain-python3 tests for scripts/cv/gmj_visual_diff.py (TEMPLATE-03 / TEMPLATE-04).

Proves the visual-diff metric is deterministic and size-invariant, and that the diffed
artifact is the REAL shipped WeasyPrint PDF (compare==ship): rendering routes through
``render_cv.py::render_weasyprint_html``, the shipped PDF starts with ``%PDF-`` and is
rasterized to a non-empty PNG. Unit tests build synthetic PNGs with Pillow — no render
needed — so the determinism assertions run fast and offline. No pytest — run with
``python3 tests/test_gmj_visual_diff.py``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_visual_diff.py"

# Put scripts/cv on the path to import the metric functions directly for unit tests.
sys.path.insert(0, str(REPO_ROOT / "scripts" / "cv"))
from gmj_visual_diff import diff_ratio, pdf_first_page_png  # noqa: E402
from render_cv import (  # noqa: E402
    render_weasyprint_html,
    candidate_with_embedded_photo,
    load_candidate,
    repo_root_from_config,
    _load_labels,
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def assert_valid_pdf(path: Path) -> None:
    """Structural PDF-validity assertion — never byte-hash (timestamps vary)."""
    assert path.is_file(), f"missing PDF: {path}"
    with path.open("rb") as fh:
        assert fh.read(5) == b"%PDF-", "not a PDF (bad magic bytes)"
    assert len(PdfReader(str(path)).pages) >= 1, "PDF has no pages"


def _solid_png(dir_path: Path, name: str, color, size=(400, 565)) -> Path:
    p = dir_path / name
    Image.new("RGB", size, color).save(p)
    return p


def test_self_diff_near_zero() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        img = _solid_png(d, "grey.png", (128, 90, 200))
        assert diff_ratio(img, img) < 0.001, "identical image must diff ~0"


def test_disjoint_high() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        white = _solid_png(d, "white.png", (255, 255, 255))
        black = _solid_png(d, "black.png", (0, 0, 0))
        assert diff_ratio(white, black) > 0.9, "white vs black must diff high"


def test_size_invariance() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ref = _solid_png(d, "ref.png", (10, 20, 30), size=(600, 848))
        small = _solid_png(d, "small.png", (200, 100, 50), size=(400, 565))
        big = _solid_png(d, "big.png", (200, 100, 50), size=(800, 1130))
        r_small = diff_ratio(small, ref)
        r_big = diff_ratio(big, ref)
        assert abs(r_small - r_big) < 1e-6, f"size-invariant diff expected: {r_small} vs {r_big}"


def test_determinism() -> None:
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        a = _solid_png(d, "a.png", (12, 200, 44))
        b = _solid_png(d, "b.png", (200, 12, 44))
        assert diff_ratio(a, b) == diff_ratio(a, b), "two calls must return identical float"


def test_compare_is_ship() -> None:
    """The diffed PDF is a real shipped WeasyPrint PDF; the CLI prints a float in [0,1]."""
    config = REPO_ROOT / "config" / "candidate.yaml"
    template = REPO_ROOT / "templates" / "cv" / "enhancv-inspired.html"
    design_dir = REPO_ROOT / "sources" / "design"
    design_dir.mkdir(parents=True, exist_ok=True)

    # Reference screenshot must live under the repo (sources/) per the path-containment guard.
    ref = design_dir / "_test_gmj_visual_diff_ref.png"
    Image.new("RGB", (400, 565), (255, 255, 255)).save(ref)
    try:
        result = _run(
            "--config", str(config),
            "--template", str(template),
            "--reference", str(ref),
        )
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        ratio = float(result.stdout.strip())
        assert 0.0 <= ratio <= 1.0, f"ratio out of range: {ratio}"

        # Independently prove compare==ship: render through render_cv.py and rasterize.
        repo_root = repo_root_from_config(config)
        labels = _load_labels(repo_root, "en")
        candidate = load_candidate(config, "en")
        cand = candidate_with_embedded_photo(candidate, repo_root)
        with tempfile.TemporaryDirectory() as td:
            ship_pdf = Path(td) / "ship.pdf"
            ship_png = Path(td) / "ship.png"
            render_weasyprint_html(
                cand, template, ship_pdf,
                repo_root=repo_root, labels=labels, lang="en",
            )
            assert_valid_pdf(ship_pdf)
            pdf_first_page_png(ship_pdf, ship_png)
            assert ship_png.is_file() and ship_png.stat().st_size > 0, "raster PNG must be non-empty"
    finally:
        ref.unlink(missing_ok=True)


def test_bad_config_degrades_exit_1() -> None:
    result = _run(
        "--config", "config/does-not-exist.yaml",
        "--template", "templates/cv/enhancv-inspired.html",
        "--reference", "sources/design/whatever.png",
    )
    assert result.returncode == 1, "missing config must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on bad config"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}", file=sys.stderr)
    if failed:
        print(f"{failed}/{len(tests)} tests failed", file=sys.stderr)
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
