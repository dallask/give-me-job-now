#!/usr/bin/env python3
"""Plain-python3 harness for scripts/cv/gmj_template_lint.py (TEMPLATE-02).

Proves the fail-closed zero-sample-strings gate: a template that hardcodes sample-profile
literals (name/company/date/email) outside ``{{ }}`` is REJECTED; a template whose values
all flow through ``{{ candidate.* }}`` bindings PASSES; and section-label heading text is
never false-positived. No external fixture files — HTML is built inline, and the leaked
literals are constructed by string-concatenation at runtime so they are not present verbatim
as scannable head-comment text in this source.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cv" / "gmj_template_lint.py"
TEMPLATES_DIR = REPO_ROOT / "templates" / "cv"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "cv"))
from gmj_template_lint import lint_template  # noqa: E402


# Build leaked literals at runtime so they are not scannable verbatim in this file.
_LEAK_NAME = "Jane" + " " + "Doe"
_LEAK_COMPANY = "Acme" + " " + "Corp"
_LEAK_DATE = "20" + "19"
_LEAK_EMAIL = "someone" + "@" + "example" + ".com"


def _clean_template() -> str:
    return (
        "<html lang=\"{{ lang }}\"><body>"
        "<h1>{{ candidate.name }}</h1>"
        "<p>{{ candidate.title }}</p>"
        "<a>{{ candidate.contact.email }}</a>"
        "{% for job in candidate.professional_experience %}"
        "<div>{{ job.company }} — {{ job.duration }}</div>"
        "{% endfor %}"
        "</body></html>"
    )


def _leaked_template() -> str:
    return (
        "<html><body>"
        "<h1>" + _LEAK_NAME + "</h1>"
        "<div>" + _LEAK_COMPANY + " (" + _LEAK_DATE + ")</div>"
        "<a>" + _LEAK_EMAIL + "</a>"
        "</body></html>"
    )


def _labels_template() -> str:
    return (
        "<html><body>"
        "<h2>Experience</h2>"
        "{% for job in candidate.professional_experience %}<p>{{ job.company }}</p>{% endfor %}"
        "<h2>Education</h2>"
        "{% for e in candidate.education %}<p>{{ e.institution }}</p>{% endfor %}"
        "<h2>Skills</h2>"
        "{% for s in candidate.expertise %}<p>{{ s.resume_title }}</p>{% endfor %}"
        "</body></html>"
    )


def test_leaked_literal_fails() -> None:
    leaks = lint_template(_leaked_template(), [_LEAK_NAME, _LEAK_COMPANY, _LEAK_DATE])
    assert leaks, "leaked sample literals must produce a non-empty leak list"
    assert _LEAK_NAME in leaks, f"leaked name must be flagged; got {leaks}"
    assert any(_LEAK_EMAIL in leak for leak in leaks), f"leaked email must be flagged; got {leaks}"


def test_clean_bindings_pass() -> None:
    leaks = lint_template(
        _clean_template(), [_LEAK_NAME, _LEAK_COMPANY, _LEAK_DATE, _LEAK_EMAIL]
    )
    assert leaks == [], f"clean {{{{ candidate.* }}}} template must return []; got {leaks}"


def test_section_label_not_flagged() -> None:
    leaks = lint_template(_labels_template(), [])
    assert leaks == [], f"section-label headings must not be flagged; got {leaks}"


def test_backstop_email_flagged() -> None:
    html = "<html><body><p>Contact " + _LEAK_EMAIL + "</p></body></html>"
    leaks = lint_template(html, [])  # empty token list — backstop must still catch it
    assert any(_LEAK_EMAIL in leak for leak in leaks), f"backstop email must be flagged; got {leaks}"


def test_backstop_url_and_year_flagged() -> None:
    url = "https" + "://" + "example.com/profile"
    html = "<html><body><a>" + url + "</a><span>" + _LEAK_DATE + "</span></body></html>"
    leaks = lint_template(html, [])
    assert any(url in leak for leak in leaks), f"backstop URL must be flagged; got {leaks}"
    assert _LEAK_DATE in leaks, f"backstop 4-digit year must be flagged; got {leaks}"


def test_attribute_sample_token_flagged() -> None:
    # Fail-closed regression (WR-02): sample data hidden in a human-facing attribute value
    # (alt / title / aria-label / placeholder) must be caught, not silently stripped with
    # the tag. Previously `_visible_literal_text` discarded all attributes so this returned
    # [] — a real leak vector (visible tooltip / screen-reader text).
    leaks = lint_template("<img alt=\"" + _LEAK_NAME + "\">", [_LEAK_NAME])
    assert _LEAK_NAME in leaks, (
        f"sample token hardcoded in an alt attribute must be flagged; got {leaks}"
    )


def test_attribute_meta_email_backstop_flagged() -> None:
    # The email backstop must also reach <meta content> — a common LLM-authored leak spot
    # (author/description meta) that the old all-tags-stripped path let through.
    html = "<meta name=\"author\" content=\"" + _LEAK_EMAIL + "\">"
    leaks = lint_template(html, [])  # empty token list — backstop must still catch it
    assert any(_LEAK_EMAIL in leak for leak in leaks), (
        f"email hardcoded in <meta content> must be flagged by the backstop; got {leaks}"
    )


def test_bound_attribute_not_false_positived() -> None:
    # Guard the fix's boundary: a properly data-bound attribute value and a relative asset
    # path must NOT false-positive — only human-facing text attributes are scanned, and
    # Jinja regions inside a value are stripped first.
    html = (
        "<img alt=\"{{ candidate.name }}\" src=\"assets/photo.png\">"
        "<a href=\"templates/cv/x.html\" class=\"nav-link\">{{ candidate.title }}</a>"
    )
    leaks = lint_template(html, [_LEAK_NAME])
    assert leaks == [], (
        f"bound attribute + relative asset path must not false-positive; got {leaks}"
    )


def test_legacy_binding_flagged() -> None:
    # A mis-binding to the legacy field name (UI-SPEC: NOT technical_expertise) is a drift
    # bug the single-owner registry must catch even though no literal is hardcoded.
    html = "<html><body>{% for s in candidate.technical_expertise %}{{ s }}{% endfor %}</body></html>"
    leaks = lint_template(html, [])
    assert any("technical_expertise" in leak for leak in leaks), (
        f"legacy candidate.technical_expertise binding must be flagged; got {leaks}"
    )


# Experience-loop capture: `{% for <var> in candidate.professional_experience %}`.
# Used to detect a bare `<var>.description` company-blurb binding where the renderer now
# reads `<var>.company_description` (gmj_render_cv.py:369).
_EXPERIENCE_LOOP = re.compile(
    r"{%-?\s*for\s+(\w+)\s+in\s+candidate\.professional_experience\s*-?%}"
)


def test_real_templates_have_no_legacy_schema_bindings() -> None:
    # Standing regression guard (v2.0 milestone-audit SCHEMA seam): the prior tests only
    # lint synthetic in-test fixtures, so the 3 legacy shipped templates
    # (default/enhancv/baxter) drifted un-caught. Iterate every REAL templates/cv/*.html and
    # assert none binds the pre-migration schema: `candidate.technical_expertise` (renderer
    # reads `candidate.expertise` at :322 → Skills section silently dropped) or a bare
    # experience `.description` company blurb (renderer reads `.company_description` at :369).
    templates = sorted(TEMPLATES_DIR.glob("*.html"))
    assert templates, f"no CV templates found under {TEMPLATES_DIR}"
    offenders: list[str] = []
    for template in templates:
        # Skip the transient fixtures the CLI tests write/remove.
        if template.name.startswith("_lint_test_"):
            continue
        html = template.read_text(encoding="utf-8")

        # (1) Legacy top-level skills binding — flagged by the schema-registry lint.
        leaks = lint_template(html, [])
        if any("technical_expertise" in leak for leak in leaks):
            offenders.append(
                f"{template.name}: legacy `candidate.technical_expertise` binding "
                f"(renderer reads `candidate.expertise`)"
            )

        # (2) Bare experience `.description` where the renderer reads `.company_description`.
        for loop_var in _EXPERIENCE_LOOP.findall(html):
            if re.search(r"\b" + re.escape(loop_var) + r"\.description\b", html):
                offenders.append(
                    f"{template.name}: experience `{loop_var}.description` blurb "
                    f"(renderer reads `{loop_var}.company_description`)"
                )

    assert not offenders, (
        "shipped CV templates still bind the pre-migration schema:\n  "
        + "\n  ".join(offenders)
    )


def _write_template(name: str, html: str) -> Path:
    path = TEMPLATES_DIR / name
    path.write_text(html, encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_cli_exit_codes() -> None:
    leaked_path = _write_template("_lint_test_leaked.html", _leaked_template())
    clean_path = _write_template("_lint_test_clean.html", _clean_template())
    try:
        leaked = _run("--template", str(leaked_path), "--sample-tokens", _LEAK_NAME)
        assert leaked.returncode == 1, f"leaked template CLI must exit 1; got {leaked.returncode}"
        assert "Traceback" not in leaked.stderr, "no traceback on rejection"

        clean = _run("--template", str(clean_path))
        assert clean.returncode == 0, f"clean template CLI must exit 0; got {clean.returncode}"
        assert clean.stdout.strip() == "clean", f"clean run must print 'clean'; got {clean.stdout!r}"
    finally:
        leaked_path.unlink(missing_ok=True)
        clean_path.unlink(missing_ok=True)


def test_cli_rejects_path_traversal() -> None:
    result = _run("--template", "../../etc/passwd")
    assert result.returncode == 1, "path traversal must exit 1"
    assert "Traceback" not in result.stderr, "no traceback on traversal rejection"


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
