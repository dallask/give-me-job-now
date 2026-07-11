#!/usr/bin/env python3
"""Plain-python3 end-to-end regression tests proving TMPL-01/TMPL-02/D-05/D-07/Pitfall-3
against the REAL ``gmj_render_cv.py`` CLI (not Plan 02-02's isolated ``resolve_template()``
unit tests).

Distinct from ``tests/test_cv_template_config.py`` (which unit-tests the resolver function
directly): every test here shells out to the actual ``scripts/cv/gmj_render_cv.py`` script via
``subprocess.run()``, proving the resolver is genuinely wired into the production CLI's
precedence block, not just callable in isolation.

Proves:
  * Test 1 -- the REAL committed ``config/preferences.yaml`` (``cv.default: baxter.html``,
    ``mode: default``) drives the no-flag default invocation to render with
    ``templates/cv/baxter.html`` (TMPL-01).
  * Test 2 -- an explicit ``--template`` flag always overrides ``cv.default`` (D-07).
  * Test 3 -- ``--no-template`` always forces ReportLab regardless of config (D-07).
  * Test 4 -- an absent ``config/preferences.yaml`` (or missing ``cv:`` block) falls back to
    the documented default, ``baxter.html`` (TMPL-02), proven via a temp repo-root fixture
    that mirrors ``repo_root_from_config()``'s ``CLAUDE.md``-anchor discovery.
  * Test 5 -- ``--state <path>`` threads through to ``resolve_template``'s rotation-state
    reuse (D-05): two renders against the identical ``--state`` path resolve to the same
    template, proven at the CLI level (not just the function level).
  * Test 6 -- the two independent ``baxter.html`` fallback literals
    (``gmj_cv_template_config.DOCUMENTED_DEFAULT_TEMPLATE`` and
    ``gmj_check_render_quality.DEFAULT_TEMPLATE_NAME``) have not drifted apart (Pitfall 3).

No pytest -- run with ``python3 tests/test_render_cv_template_precedence.py`` (also
pytest-collectible since every function is named ``test_*`` and takes no arguments).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_render_cv.py"
CONFIG = REPO_ROOT / "config" / "candidate.yaml"
TEMPLATES_DIR = REPO_ROOT / "templates" / "cv"

_WEASYPRINT_AVAILABLE = importlib.util.find_spec("weasyprint") is not None

# Stable, unique CSS-class markers per real template (grep-verified against the actual
# templates/cv/*.html source, not guessed) -- used to prove which template rendered without
# relying on a brittle byte-diff against the `now`-timestamp Jinja variable.
_BAXTER_MARKER = "sidebar-triangle"
_EMERALD_MARKER = "deco-circle-large"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else str(REPO_ROOT),
    )


def test_default_config_resolves_to_baxter() -> None:
    """TMPL-01: the real committed config/preferences.yaml (cv.default: baxter.html, mode:
    default) drives the no-flag default invocation to render with templates/cv/baxter.html."""
    out = Path(tempfile.mkdtemp()) / "default-cv.pdf"
    result = _run("--config", str(CONFIG), "--out", str(out))
    assert result.returncode == 0, f"default invocation must exit 0: {result.stderr}"
    html_sibling = out.with_suffix(".html")
    if _WEASYPRINT_AVAILABLE:
        assert html_sibling.is_file(), f"expected HTML sibling at {html_sibling}"
        html_text = html_sibling.read_text(encoding="utf-8")
        assert _BAXTER_MARKER in html_text, (
            f"expected baxter.html's marker {_BAXTER_MARKER!r} in rendered HTML "
            f"(TMPL-01: config-resolved default must be baxter.html)"
        )
    else:
        assert not html_sibling.is_file(), "WeasyPrint unavailable: no HTML sibling expected"
        assert "Falling back to ReportLab built-in layout." in result.stderr, (
            "graceful ReportLab degrade must still exit 0 when WeasyPrint is unavailable"
        )


def test_explicit_template_flag_overrides_config() -> None:
    """D-07: an explicit --template flag always wins over cv.default, even though the real
    config's cv.default is baxter.html."""
    out = Path(tempfile.mkdtemp()) / "explicit-cv.pdf"
    result = _run(
        "--config", str(CONFIG),
        "--template", str(TEMPLATES_DIR / "emerald.html"),
        "--out", str(out),
    )
    assert result.returncode == 0, f"explicit --template invocation must exit 0: {result.stderr}"
    html_sibling = out.with_suffix(".html")
    if _WEASYPRINT_AVAILABLE:
        assert html_sibling.is_file(), f"expected HTML sibling at {html_sibling}"
        html_text = html_sibling.read_text(encoding="utf-8")
        assert _EMERALD_MARKER in html_text, (
            f"expected emerald.html's marker {_EMERALD_MARKER!r} in rendered HTML "
            f"(explicit --template must override cv.default=baxter.html, D-07)"
        )
        assert _BAXTER_MARKER not in html_text, (
            "rendered HTML must NOT contain baxter.html's marker when --template=emerald.html "
            "was explicitly requested"
        )
    else:
        assert not html_sibling.is_file(), "WeasyPrint unavailable: no HTML sibling expected"
        assert "Falling back to ReportLab built-in layout." in result.stderr


def test_no_template_flag_overrides_config() -> None:
    """D-07: --no-template always forces ReportLab regardless of cv.default/cv.mode."""
    out = Path(tempfile.mkdtemp()) / "no-template-cv.pdf"
    result = _run("--config", str(CONFIG), "--no-template", "--out", str(out))
    assert result.returncode == 0, f"--no-template invocation must exit 0: {result.stderr}"
    assert out.is_file(), f"missing PDF: {out}"
    html_sibling = out.with_suffix(".html")
    assert not html_sibling.is_file(), (
        f"--no-template must never write an HTML sibling regardless of config: {html_sibling}"
    )


def _build_temp_repo_root(tmp_path: Path, *, with_prefs_cv_block: bool) -> tuple[Path, Path]:
    """Build a minimal temp repo-root tree mirroring repo_root_from_config()'s CLAUDE.md-anchor
    discovery: a CLAUDE.md marker file, a templates/cv/baxter.html stub with a distinguishing
    marker, and a config/candidate.yaml. Returns (repo_root, candidate_yaml_path)."""
    (tmp_path / "CLAUDE.md").write_text("# stub repo anchor\n", encoding="utf-8")
    templates_dir = tmp_path / "templates" / "cv"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "baxter.html").write_text(
        "<!DOCTYPE html><html><body><!-- STUB: baxter -->{{ candidate.name }}</body></html>\n",
        encoding="utf-8",
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    candidate_yaml = config_dir / "candidate.yaml"
    candidate_yaml.write_text('name: "Temp Candidate"\ntitle: "Engineer"\n', encoding="utf-8")
    if with_prefs_cv_block:
        (config_dir / "preferences.yaml").write_text(
            "cv:\n  templates: [baxter.html]\n  default: baxter.html\n  mode: default\n",
            encoding="utf-8",
        )
    # else: no preferences.yaml at all (TMPL-02's fully-absent-config scenario).
    return tmp_path, candidate_yaml


def test_config_absent_falls_back_to_documented_default() -> None:
    """TMPL-02: with NO config/preferences.yaml at all under a temp repo root (built via
    repo_root_from_config()'s own CLAUDE.md-anchor discovery), the render still exits 0 and
    produces a PDF using the documented fallback (baxter.html) -- absent config never blocks
    a render."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_root, candidate_yaml = _build_temp_repo_root(tmp_path, with_prefs_cv_block=False)
        out = tmp_path / "out" / "temp-cv.pdf"
        result = _run("--config", str(candidate_yaml), "--out", str(out), cwd=repo_root)
        assert result.returncode == 0, (
            f"config-absent invocation must still exit 0 (TMPL-02): {result.stderr}"
        )
        assert out.is_file(), f"missing PDF: {out}"
        html_sibling = out.with_suffix(".html")
        if _WEASYPRINT_AVAILABLE:
            assert html_sibling.is_file(), f"expected HTML sibling at {html_sibling}"
            html_text = html_sibling.read_text(encoding="utf-8")
            assert "STUB: baxter" in html_text, (
                "config-absent fallback must resolve to the stub baxter.html "
                "(TMPL-02 documented default)"
            )
        else:
            assert not html_sibling.is_file(), "WeasyPrint unavailable: no HTML sibling expected"
            assert "Falling back to ReportLab built-in layout." in result.stderr


def test_rotation_reuses_pick_across_two_renders_of_same_state() -> None:
    """D-05 at the CLI level: with cv.mode: random (a temp preferences.yaml, since the real
    committed config uses mode: default) and an identical --state path, two separate
    gmj_render_cv.py invocations resolve to the SAME template."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "CLAUDE.md").write_text("# stub repo anchor\n", encoding="utf-8")
        templates_dir = tmp_path / "templates" / "cv"
        templates_dir.mkdir(parents=True, exist_ok=True)
        stub_names = ["stub-a.html", "stub-b.html", "stub-c.html"]
        for name in stub_names:
            (templates_dir / name).write_text(
                f"<!DOCTYPE html><html><body><!-- STUB: {name} -->"
                "{{ candidate.name }}</body></html>\n",
                encoding="utf-8",
            )
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        candidate_yaml = config_dir / "candidate.yaml"
        candidate_yaml.write_text('name: "Temp Candidate"\ntitle: "Engineer"\n', encoding="utf-8")
        templates_list = ", ".join(stub_names)
        (config_dir / "preferences.yaml").write_text(
            f"cv:\n  templates: [{templates_list}]\n  default: {stub_names[0]}\n  mode: random\n",
            encoding="utf-8",
        )

        state_path = tmp_path / "runs" / "offer-1-cv" / "state.json"

        out1 = tmp_path / "out" / "render1.pdf"
        result1 = _run(
            "--config", str(candidate_yaml), "--out", str(out1),
            "--state", str(state_path), cwd=tmp_path,
        )
        assert result1.returncode == 0, f"first rotation render must exit 0: {result1.stderr}"

        out2 = tmp_path / "out" / "render2.pdf"
        result2 = _run(
            "--config", str(candidate_yaml), "--out", str(out2),
            "--state", str(state_path), cwd=tmp_path,
        )
        assert result2.returncode == 0, f"second rotation render must exit 0: {result2.stderr}"

        assert state_path.is_file(), f"expected state.json to be written at {state_path}"
        import json
        state = json.loads(state_path.read_text(encoding="utf-8"))
        picked = state.get("cv_template_rotation", {}).get("picked")
        assert picked in stub_names, f"expected a recorded pick in {stub_names}, got {picked!r}"

        if _WEASYPRINT_AVAILABLE:
            html1 = out1.with_suffix(".html").read_text(encoding="utf-8")
            html2 = out2.with_suffix(".html").read_text(encoding="utf-8")
            marker = f"<!-- STUB: {picked} -->"
            assert marker in html1, (
                f"first render must use the recorded pick {picked!r}: marker missing from {html1!r}"
            )
            assert marker in html2, (
                f"second render must REUSE the same pick {picked!r} (D-05), "
                f"marker missing from second render's HTML"
            )


def test_hardcoded_fallback_literal_matches_qa_check_default() -> None:
    """Pitfall 3: the two independent baxter.html fallback literals
    (gmj_cv_template_config.DOCUMENTED_DEFAULT_TEMPLATE and
    gmj_check_render_quality.DEFAULT_TEMPLATE_NAME) must stay in sync."""
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "cv"))
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
    import gmj_cv_template_config as tc
    import gmj_check_render_quality as qc

    assert tc.DOCUMENTED_DEFAULT_TEMPLATE == qc.DEFAULT_TEMPLATE_NAME, (
        f"drift detected: gmj_cv_template_config.DOCUMENTED_DEFAULT_TEMPLATE="
        f"{tc.DOCUMENTED_DEFAULT_TEMPLATE!r} != "
        f"gmj_check_render_quality.DEFAULT_TEMPLATE_NAME={qc.DEFAULT_TEMPLATE_NAME!r}"
    )


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
