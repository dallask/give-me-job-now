"""Assert the dashboard dependency pin (PKG-02).

Plain-``python3`` self-running harness (NO pytest, per project convention): resolves the
repo root, reads ``scripts/dashboard/requirements.txt``, and proves the ``textual`` pin is
the tested, capped-major range and that no transitive console-render package is listed as a
top-level pin.

Pin decision (D-25): ``textual>=6.1,<7`` — floor ``6.1`` is the installed+fully-tested
version; cap ``<7`` excludes the next major (Textual ships breaking changes across majors,
only 6.x is exercised). ``rich`` arrives transitively via ``textual`` and must NOT be pinned
here (duplicating a transitive pin).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "scripts" / "dashboard" / "requirements.txt"

# Transitive console-render package that textual already declares — must not be a top-level pin.
TRANSITIVE_RENDER_PKG = "rich"


def _dependency_lines() -> list[str]:
    """Return non-blank, non-comment dependency lines from the requirements file."""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def test_requirements_file_exists() -> None:
    assert REQUIREMENTS.is_file(), f"missing {REQUIREMENTS}"


def test_single_dependency_line() -> None:
    lines = _dependency_lines()
    assert len(lines) == 1, f"expected exactly one dependency line, got {lines!r}"


def test_textual_pin_floor_and_cap() -> None:
    lines = _dependency_lines()
    textual_lines = [ln for ln in lines if re.match(r"^textual\b", ln, re.IGNORECASE)]
    assert len(textual_lines) == 1, f"expected exactly one textual pin, got {textual_lines!r}"
    pin = textual_lines[0]
    assert ">=6.1" in pin, f"textual pin missing floor '>=6.1': {pin!r}"
    assert "<7" in pin, f"textual pin missing capped major '<7': {pin!r}"


def test_no_transitive_render_pin() -> None:
    lines = _dependency_lines()
    offenders = [ln for ln in lines if re.match(rf"^{TRANSITIVE_RENDER_PKG}\b", ln, re.IGNORECASE)]
    assert not offenders, f"transitive package {TRANSITIVE_RENDER_PKG!r} must not be a top-level pin: {offenders!r}"


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
