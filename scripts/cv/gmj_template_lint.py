#!/usr/bin/env python3
"""Fail-closed zero-sample-strings gate for generated CV templates (TEMPLATE-02).

Doctrine: an LLM-authored ``templates/cv/<slug>.html`` is *untrusted* content. The
screenshot→template agent could hardcode the sample profile's name/company/date/email
instead of binding every value through a ``{{ candidate.* }}`` expression. This module
machine-enforces the Print Contract Data-Binding rule: **every rendered data value MUST
flow through a Jinja expression; zero literal sample-profile strings may appear in the
template source.** The gate fails closed — any leaked data-literal outside ``{{ ... }}``
(and not an allowlisted section label) rejects the template.

Two layers:
  1. Primary rule — an explicit ``--sample-tokens`` list (the names/companies/dates the
     screenshot showed; the reading agent already knows them) is substring-searched in the
     literal-only text remaining after Jinja expressions are stripped out.
  2. Backstop regexes — email (``\\S+@\\S+``), ``https?://`` URL, a bare 4-digit year, and a
     capitalized multi-word proper-noun heuristic catch leaks absent from the token list.

Section labels (``Experience`` / ``Education`` / ``Skills`` …) and every ``labels.*`` i18n
value are allowlisted so structural heading text never false-positives.

The canonical binding-key registry (``TOP_LEVEL`` / ``CONTACT`` / ``WEBSITE_GROUPS``) is
imported from the single-owner ``scripts/artifacts/schema_fields.py`` — never re-declared
here — so the field names the lint reasons about cannot drift from the schema owner.

CLI: ``gmj_template_lint.py --template templates/cv/<slug>.html [--sample-tokens "a,b,c"]``
→ exit 0 printing ``clean`` when nothing leaks; exit 1 printing the flagged literals to
stderr otherwise; malformed input exits 1 with no traceback.

Importable: ``lint_template(html, sample_tokens) -> list[str]`` (empty list == PASS).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Single-owner candidate.yaml field-name registry (SCHEMA-06). Import the binding-key
# constants rather than re-declaring literals that could drift from the schema owner.
# Same sibling-import idiom as scripts/cv/render_cv.py (scripts/artifacts on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "artifacts"))
from schema_fields import CONTACT, TOP_LEVEL, WEBSITE_GROUPS  # noqa: E402  (all three USED below)

# The binding keys the lint reasons about are exactly the schema owner's names: a value
# that should have flowed through candidate.<TOP_LEVEL> / candidate.contact.<CONTACT> /
# candidate.contact.website.<WEBSITE_GROUPS>. A ``{{ candidate.<field> }}`` binding to a
# name OUTSIDE these registries is a drift bug (e.g. legacy ``technical_expertise`` instead
# of ``expertise`` — the UI-SPEC calls this out explicitly) and is reported as a leak so the
# gate also catches mis-bindings, not only hardcoded literals.
_TOP_LEVEL = frozenset(TOP_LEVEL)
_CONTACT = frozenset(CONTACT)
_WEBSITE_GROUPS = frozenset(WEBSITE_GROUPS)

# --- Allowlist: standard section headings + i18n label values -----------------------
# Structural/label text is never sample data; loading the live labels.yaml keeps the
# allowlist in sync with the i18n contract (ua/ru headings pass too). The static set is
# the fallback so the gate never depends on YAML being importable.
_STATIC_LABELS = frozenset(
    s.lower()
    for s in (
        "Summary", "About", "About Me", "Contact", "Contact Me", "Profile",
        "Expertise", "Technical expertise", "Technical Skills", "Core skills",
        "Skills", "Languages", "Language", "Experience", "Job Experience",
        "Work Experience", "Professional Experience", "Education",
        "Independent projects", "Projects", "Certifications", "Courses",
        "Courses & certifications", "Key achievements", "Key Achievements",
    )
)


def _load_label_values() -> frozenset[str]:
    """Best-effort load of every ``labels.*`` value from config/i18n/labels.yaml.

    Returns the static heading set unioned with the live label values (all languages),
    lowercased. Any load failure degrades to the static set — the gate must never crash
    because the i18n file moved.
    """
    values: set[str] = set(_STATIC_LABELS)
    try:
        import yaml  # local import: the lint core stays dependency-free for import-only use

        labels_path = (
            Path(__file__).resolve().parent.parent.parent / "config" / "i18n" / "labels.yaml"
        )
        data = yaml.safe_load(labels_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for lang_block in data.values():
                if isinstance(lang_block, dict):
                    for v in lang_block.values():
                        if isinstance(v, str) and v.strip():
                            values.add(v.strip().lower())
    except Exception:  # noqa: BLE001  — allowlist is best-effort; never fail the gate on load
        pass
    return frozenset(values)


_ALLOWLIST = _load_label_values()

# --- Regexes ------------------------------------------------------------------------
_JINJA = re.compile(r"{{.*?}}|{%.*?%}|{#.*?#}", re.DOTALL)
# Jinja *expressions* only (output + statements), excluding ``{# comments #}`` — comment
# prose is not a live binding and must not be validated against the schema registry.
_JINJA_EXPR = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)
_STYLE_SCRIPT = re.compile(r"<(style|script)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

_EMAIL = re.compile(r"\S+@\S+\.\S+")
_URL = re.compile(r"https?://\S+")
_YEAR = re.compile(r"\b\d{4}\b")
# Capitalized multi-word proper noun (a person or company name): two+ Titlecase words
# joined by a SINGLE space. A single space keeps a genuine name ("Jane Doe") matching while
# preventing the pattern from spanning the multi-space gaps that tag-stripping leaves between
# adjacent section headings (which would otherwise glue "Experience  Education" into one hit).
_PROPER_NOUN = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b")
# A ``candidate.<field>[.<sub>...]`` dotted binding path inside a Jinja expression.
_CANDIDATE_BINDING = re.compile(r"\bcandidate\.([A-Za-z_][A-Za-z0-9_.]*)")
# Text-bearing attributes whose values are human-visible (tooltip / alt / screen-reader /
# placeholder) or leak-prone (``<meta content>``). Their values face the same sample-token +
# backstop checks as visible text, closing the fail-open gap where hardcoded sample data hid
# in an attribute. Deliberately EXCLUDES src/href/class so relative asset paths never
# false-positive. Handles both double- and single-quoted values.
_TEXT_ATTR = re.compile(
    r"\b(?:alt|title|aria-label|content|placeholder)\s*=\s*"
    r"""(?:"([^"]*)"|'([^']*)')""",
    re.IGNORECASE,
)


def _visible_literal_text(html: str) -> str:
    """Reduce template source to visible literal text with all Jinja regions removed.

    Order matters: strip Jinja expressions first (so a value inside ``{{ }}`` is never
    scanned), then drop ``<style>``/``<script>`` blocks and HTML comments (structural,
    not data), then strip tags to leave only the text a reader would see. Attribute
    values (class names, relative asset paths in ``src``/``href``) are intentionally
    discarded — the contract governs rendered data values, and legit relative asset URLs
    must not false-positive.
    """
    import html as _htmlmod

    text = _JINJA.sub(" ", html)
    text = _STYLE_SCRIPT.sub(" ", text)
    text = _HTML_COMMENT.sub(" ", text)
    text = _TAG.sub(" ", text)
    text = _htmlmod.unescape(text)
    return text


def _visible_attribute_text(html: str) -> str:
    """Extract the values of human-facing / leak-prone attributes for leak scanning.

    ``_visible_literal_text`` discards ALL attribute values (to avoid false-positives on
    relative asset paths in ``src``/``href``/``class``), but that fails OPEN: sample-profile
    data hardcoded in ``alt``/``title``/``aria-label``/``placeholder`` (a visible tooltip or
    screen-reader string) or in ``<meta content>`` (e.g. an author email) slips past BOTH the
    primary sample-token rule and the email/URL/year/proper-noun backstops. Scan a small
    allowlist of text-bearing attributes so those leaks fail closed, while still ignoring
    ``src``/``href``/``class`` so legitimate relative asset paths do not false-positive.
    Jinja regions inside a value (``alt="{{ candidate.name }}"``) are stripped first, so a
    properly data-bound attribute is never flagged.
    """
    import html as _htmlmod

    text = _JINJA.sub(" ", html)
    text = _STYLE_SCRIPT.sub(" ", text)
    text = _HTML_COMMENT.sub(" ", text)
    values = [dq or sq for dq, sq in _TEXT_ATTR.findall(text)]
    return _htmlmod.unescape(" ".join(values))


def _is_allowlisted(value: str) -> bool:
    return value.strip().lower() in _ALLOWLIST


def _lint_bindings(html: str) -> list[str]:
    """Flag ``{{ candidate.<field> }}`` bindings to names outside the schema registry.

    Uses the single-owner ``schema_fields`` registry (``TOP_LEVEL`` / ``CONTACT`` /
    ``WEBSITE_GROUPS``) to catch the legacy-drift failure the UI-SPEC warns about — e.g. a
    template binding ``candidate.technical_expertise`` instead of ``candidate.expertise``.
    Only the leading path segments that MUST match the candidate schema are validated:
    the first segment against ``TOP_LEVEL``; under ``contact`` the second against
    ``CONTACT``; under ``contact.website`` the third against ``WEBSITE_GROUPS``. Deeper
    segments (list-item fields) are not the candidate schema and are left alone.
    """
    bad: list[str] = []
    seen: set[str] = set()
    # Scan ONLY inside real Jinja ``{{ }}`` / ``{% %}`` expressions — a bare mention of
    # "candidate.yaml" in prose or a ``{# comment #}`` is not a binding and must not flag.
    jinja_regions = " ".join(_JINJA_EXPR.findall(html))
    for path in _CANDIDATE_BINDING.findall(jinja_regions):
        segments = path.split(".")
        top = segments[0]
        if top not in _TOP_LEVEL:
            key = f"candidate.{top}"
        elif top == "contact" and len(segments) >= 2 and segments[1] not in _CONTACT:
            key = f"candidate.contact.{segments[1]}"
        elif (
            top == "contact"
            and len(segments) >= 3
            and segments[1] == "website"
            and segments[2] not in _WEBSITE_GROUPS
        ):
            key = f"candidate.contact.website.{segments[2]}"
        else:
            continue
        if key not in seen:
            seen.add(key)
            bad.append(key)
    return bad


def lint_template(html: str, sample_tokens: list[str] | None = None) -> list[str]:
    """Return the list of leaked literal strings in ``html`` (empty list == PASS).

    A leak is sample-profile data that appears in the template's visible literal text
    (outside every ``{{ ... }}`` / ``{% ... %}`` region) and is not an allowlisted
    section label. Detection is the union of the explicit ``sample_tokens`` primary rule
    and the email/URL/year/proper-noun backstop regexes. Both rule layers scan the visible
    tag text AND the values of human-facing / leak-prone attributes (``alt``, ``title``,
    ``aria-label``, ``content``, ``placeholder``), so hardcoded sample data hidden in an
    attribute fails closed instead of slipping through.
    """
    text = _visible_literal_text(html) + " \n " + _visible_attribute_text(html)
    leaks: list[str] = []
    seen: set[str] = set()

    def _flag(value: str) -> None:
        value = value.strip()
        if not value or value in seen:
            return
        seen.add(value)
        leaks.append(value)

    # (1) Primary rule: explicit sample tokens are known screenshot data — flag on
    # presence in the literal text (they should have been bound, never hardcoded).
    for token in sample_tokens or []:
        token = (token or "").strip()
        if token and token in text:
            _flag(token)

    # (2) Backstop regexes over the same literal-only text. Emails and URLs are always
    # leaks (no legitimate hardcoded email/URL belongs in a data-bound template).
    for m in _EMAIL.findall(text):
        _flag(m)
    for m in _URL.findall(text):
        _flag(m)
    for m in _YEAR.findall(text):
        if not _is_allowlisted(m):
            _flag(m)
    for m in _PROPER_NOUN.findall(text):
        if not _is_allowlisted(m):
            _flag(m)

    # (3) Binding-key validation via the single-owner schema registry: a
    # ``{{ candidate.<field> }}`` bound to a name outside TOP_LEVEL/CONTACT/WEBSITE_GROUPS
    # is a drift mis-binding (legacy field) — report it so the gate covers both hardcoded
    # literals AND wrong bindings.
    for key in _lint_bindings(html):
        _flag(key)

    return leaks


def _resolve_template_path(raw: str) -> Path:
    """Resolve ``--template`` and reject path traversal outside ``templates/cv/`` (T-13-01).

    Rejects any ``..`` component and any path that does not resolve inside the repo's
    ``templates/cv/`` directory.
    """
    if ".." in Path(raw).parts:
        raise ValueError(f"--template rejected: path traversal component in {raw!r}")
    repo_root = Path(__file__).resolve().parent.parent.parent
    templates_dir = (repo_root / "templates" / "cv").resolve()
    candidate = Path(raw)
    resolved = candidate if candidate.is_absolute() else (repo_root / candidate)
    resolved = resolved.resolve()
    if resolved != templates_dir and templates_dir not in resolved.parents:
        raise ValueError(f"--template rejected: {raw!r} is outside templates/cv/")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed zero-sample-strings gate for generated CV templates (TEMPLATE-02)."
    )
    parser.add_argument("--template", type=str, required=True, help="Path under templates/cv/")
    parser.add_argument(
        "--sample-tokens",
        type=str,
        default="",
        help="Comma-separated literal sample strings the screenshot showed (optional).",
    )
    args = parser.parse_args(argv)

    try:
        template_path = _resolve_template_path(args.template)
        html = template_path.read_text(encoding="utf-8")
        tokens = [t.strip() for t in args.sample_tokens.split(",") if t.strip()]
        leaks = lint_template(html, tokens)
    except Exception as exc:  # noqa: BLE001  — fail closed, no traceback to the caller
        print(f"gmj_template_lint error: {exc}", file=sys.stderr)
        return 1

    if leaks:
        print(f"Template rejected — literal sample text: {leaks}", file=sys.stderr)
        return 1
    print("clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
