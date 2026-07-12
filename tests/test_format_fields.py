#!/usr/bin/env python3
"""Plain-python3 tests for scripts/artifacts/gmj_format_fields.py (PIPE-02).

Proves ``contact_lines()`` is dict/list-safe (no ``[``/``{`` container-repr can leak
into a returned line) across the phone/email/address/website/media/messengers shapes
of the ``config/candidate.yaml`` contact schema, and that the Jinja filter registration
in ``scripts/cv/gmj_render_cv.py`` is a thin wrapper around the SAME function, not a
second copy. No pytest — run with ``python3 tests/test_format_fields.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "artifacts"))
from gmj_format_fields import contact_lines, expertise_skills_text  # noqa: E402


def _no_container_repr(lines: list[str]) -> bool:
    return all("[" not in line and "{" not in line for line in lines)


def test_contact_lines_formats_phone_email_address() -> None:
    contact = {
        "phone": "+00000000000",
        "email": ["hello@example.com", "second@example.com"],
        "address": "City, Country",
    }
    lines = contact_lines(contact)
    assert lines, "expected non-empty lines"
    assert _no_container_repr(lines), lines
    assert any("Phone:" in line and "+00000000000" in line for line in lines), lines
    assert any(
        "Email:" in line and "hello@example.com" in line and "second@example.com" in line
        for line in lines
    ), lines
    assert any(line == "City, Country" for line in lines), lines


def test_contact_lines_formats_nested_website_dict() -> None:
    contact = {
        "website": {
            "personal": ["https://example.com", "https://next.example.com"],
            "company": ["https://empty.pro"],
            "portfolio": ["https://empty.pro/portfolio/"],
            "media": {
                "linkedin": "https://www.linkedin.com/in/example/",
                "github": "https://github.com/example",
            },
        },
    }
    lines = contact_lines(contact)
    assert lines, "expected non-empty lines"
    assert _no_container_repr(lines), lines
    assert "https://example.com" in lines, lines
    assert "https://next.example.com" in lines, lines
    assert "https://empty.pro" in lines, lines
    assert "https://empty.pro/portfolio/" in lines, lines
    assert "Linkedin: https://www.linkedin.com/in/example/" in lines, lines
    assert "Github: https://github.com/example" in lines, lines


def test_contact_lines_handles_missing_or_malformed_fields() -> None:
    # website entirely missing
    lines = contact_lines({"phone": "123"})
    assert _no_container_repr(lines), lines
    assert lines == ["Phone: 123"], lines

    # website is None
    lines = contact_lines({"phone": "123", "website": None})
    assert _no_container_repr(lines), lines
    assert lines == ["Phone: 123"], lines

    # website is a non-dict (e.g. bare string) — must not crash, must not be interpolated raw
    lines = contact_lines({"phone": "123", "website": "not-a-dict"})
    assert _no_container_repr(lines), lines
    assert lines == ["Phone: 123"], lines


def test_contact_lines_non_dict_contact_returns_empty() -> None:
    assert contact_lines(None) == []
    assert contact_lines([]) == []
    assert contact_lines("not-a-dict") == []
    assert contact_lines(42) == []


def test_contact_lines_strips_doubled_embedded_label_in_media_url() -> None:
    contact = {"website": {"media": {"linkedin": "LinkedIn: https://linkedin.com/in/example"}}}
    lines = contact_lines(contact)
    assert lines == ["Linkedin: https://linkedin.com/in/example"], lines


def test_contact_lines_strips_doubled_label_and_trailing_period() -> None:
    contact = {"website": {"media": {"github": "GitHub: https://github.com/dallask."}}}
    lines = contact_lines(contact)
    assert lines == ["Github: https://github.com/dallask"], lines


def test_contact_lines_already_correct_shape_unchanged() -> None:
    contact = {"website": {"media": {"linkedin": "https://www.linkedin.com/in/example/"}}}
    lines = contact_lines(contact)
    assert lines == ["Linkedin: https://www.linkedin.com/in/example/"], lines


def test_contact_lines_strips_label_case_insensitively_no_space() -> None:
    contact = {"website": {"media": {"linkedin": "linkedin:https://linkedin.com/in/example"}}}
    lines = contact_lines(contact)
    assert lines == ["Linkedin: https://linkedin.com/in/example"], lines


def test_contact_lines_messenger_labels_stripped_for_parity() -> None:
    contact = {"messengers": {"telegram": "Telegram: @example_handle."}}
    lines = contact_lines(contact)
    assert lines == ["Telegram: @example_handle"], lines


def test_expertise_skills_text_joins_well_formed_list() -> None:
    assert expertise_skills_text(["Python", "PHP", "JavaScript"]) == "Python, PHP, JavaScript"


def test_expertise_skills_text_leaves_bare_prose_string_unchanged() -> None:
    prose = "PHP frameworks expertise includes Laravel, Symfony"
    assert expertise_skills_text(prose) == prose


def test_expertise_skills_text_empty_or_none_returns_empty_string() -> None:
    assert expertise_skills_text(None) == ""
    assert expertise_skills_text([]) == ""


def test_expertise_skills_text_coerces_non_string_items_and_drops_falsy() -> None:
    assert expertise_skills_text([1, "PHP", None]) == "1, PHP"


def test_jinja_filter_produces_same_output_as_direct_call() -> None:
    from jinja2 import Environment

    contact = {
        "phone": "+00000000000",
        "email": ["hello@example.com"],
        "website": {
            "personal": ["https://example.com"],
            "media": {"linkedin": "https://linkedin.com/in/example"},
        },
    }
    env = Environment()
    env.filters["contact_lines"] = contact_lines
    tpl = env.from_string("{% for line in c | contact_lines %}{{ line }}|{% endfor %}")
    rendered = tpl.render(c=contact)

    direct = "".join(f"{line}|" for line in contact_lines(contact))
    assert rendered == direct, (rendered, direct)


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
