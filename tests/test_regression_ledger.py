#!/usr/bin/env python3
"""Completeness gate for the STATE.md Deferred Verification -> REGRESSION-LEDGER.md conversion.

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_regression_ledger.py``. This IS a real gate in the ``tests/test_*.py``
glob (``docs/HUMAN-TESTING-PLAN.md:42``). It asserts REGRESSION-03: every ``## Deferred
Verification`` row in ``.planning/STATE.md`` carries a stable ``DV-ID`` and has a matching
disposition in ``.planning/REGRESSION-LEDGER.md`` (a new un-dispositioned deferral FAILS here,
so the ledger cannot silently rot into a drifting checklist).

HARD CONSTRAINT (anti-circular — RESEARCH Pitfall 1): this gate performs PURE FILE PARSING +
structural checks only. It contains ZERO subprocess execution of any eval and ZERO assertion on
any accuracy/score — it never runs an eval and never judges an LLM. It only proves that each
deferral is *dispositioned*, that every cited test/eval file *exists on disk*, and that every
re-defer *reason* is concrete (non-placeholder, substantive). The ``subprocess`` module is
never imported here.

Design invariants:
- Keys on the stable ``DV-ID`` (NOT ``(Phase, State)``, which collides on duplicate slugs and
  drifts on ``03.1`` vs ``3.1``). Every STATE data row MUST carry a ``DV-`` id or the parser
  fails loudly.
- COUNT-AGNOSTIC: N is derived from the parsed STATE table; there is no hardcoded 17/18. A new
  row simply becomes a new DV-ID that must appear in the ledger.
- Every assert names the DV-ID / missing file / placeholder reason that failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE = REPO_ROOT / ".planning" / "STATE.md"
LEDGER = REPO_ROOT / ".planning" / "REGRESSION-LEDGER.md"

# Disposition kinds whose target is a repo-relative file that must resolve on disk.
_FILE_KINDS = ("scored_eval", "regression_test")
# Re-defer reasons may not be one of these placeholders (and must be substantive).
_PLACEHOLDER = {"", "todo", "tbd", "tba", "n/a", "pending", "fixme"}


def _deferred_rows(text: str) -> list[dict[str, str]]:
    """Parse the STATE.md ## Deferred Verification table into DV-ID-keyed rows.

    Slices the section from ``## Deferred Verification`` to the NEXT top-level ``## `` heading
    (whatever it is named) or EOF — NOT bound to a hardcoded sibling heading — drops the
    blockquote (``>``) and header/separator lines, splits each data row on ``|``, and REQUIRES
    every data row's first cell to start with ``DV-`` (fails loudly if the column is missing).
    """
    if "## Deferred Verification" not in text:
        raise AssertionError("STATE.md has no '## Deferred Verification' section")
    after = text.split("## Deferred Verification", 1)[1]
    # Bound to the next top-level "## " heading generically (or EOF), so inserting, renaming,
    # or reordering a later section does not spuriously break or mis-scope the gate.
    body = re.split(r"(?m)^## ", after, maxsplit=1)[0]
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if s.startswith("|--") or s.startswith("| DV-ID") or s.startswith("| Phase"):
            continue  # separator / header
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or not cells[0].startswith("DV-"):
            raise AssertionError(
                f"Deferred Verification data row missing a DV-ID first cell: {s!r}"
            )
        rows.append({"id": cells[0], "phase": cells[1] if len(cells) > 1 else ""})
    return rows


def _ledger_entries(text: str) -> dict[str, dict[str, str]]:
    """Parse the REGRESSION-LEDGER.md disposition table into DV-ID -> {kind, target}.

    Only rows whose first cell is a real ``DV-<number>`` id are disposition rows; the header
    row (first cell ``DV-ID``), the REGRESSION-01 audit subsection, and prose lines are ignored.
    The last cell is ``kind:value`` (split on the first ``:``): for file kinds ``value`` is a
    repo-relative target; for ``re_defer`` it is the recorded reason.
    """
    entries: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("| DV-"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5 or not re.fullmatch(r"DV-\d+", cells[0]):
            continue
        dv_id = cells[0]
        kind, _, value = cells[4].partition(":")
        entries[dv_id] = {"kind": kind.strip(), "value": value.strip()}
    return entries


def _orphan_ledger_ids(state_ids: set[str], ledger_text: str) -> list[str]:
    """DV-IDs that have a ledger disposition ROW but NO matching STATE row (ledger rot).

    Reverse of the STATE->ledger completeness check: a stale/renamed/typo'd disposition id
    (e.g. ``DV-99`` with no STATE row, or ``DV-8`` where STATE has ``DV-08``) surfaces here.
    Keyed on the structured row parse (``_ledger_entries``), NOT a loose prose regex.
    """
    return sorted(set(_ledger_entries(ledger_text)) - state_ids)


def test_every_deferred_row_is_dispositioned() -> None:
    """Count-agnostic completeness: every STATE DV-ID appears in the ledger."""
    state_ids = {r["id"] for r in _deferred_rows(STATE.read_text(encoding="utf-8"))}
    assert state_ids, "no DV-ID rows parsed from STATE.md — Deferred Verification shape changed"
    ledger_text = LEDGER.read_text(encoding="utf-8")
    ledger_ids = set(re.findall(r"\bDV-\d+\b", ledger_text))
    missing = sorted(state_ids - ledger_ids)
    assert not missing, f"Deferred rows with NO ledger disposition: {missing}"


def test_no_orphan_ledger_dispositions() -> None:
    """Reverse completeness: every ledger disposition row has a matching STATE DV-ID.

    Without this, an orphan/mistyped ledger id (e.g. ``DV-99`` with no STATE row) passes
    silently — the exact 'ledger rots into a drifting checklist' failure the gate prevents.
    """
    state_ids = {r["id"] for r in _deferred_rows(STATE.read_text(encoding="utf-8"))}
    orphans = _orphan_ledger_ids(state_ids, LEDGER.read_text(encoding="utf-8"))
    assert not orphans, f"Ledger disposition rows with NO matching STATE DV-ID: {orphans}"


def test_orphan_ledger_disposition_is_detected_red() -> None:
    """Negative proof: an injected orphan ledger DV-ID makes the reverse check go RED."""
    state_ids = {"DV-01"}
    ledger_text = (
        "| DV-ID | Phase | State | Notes | Disposition |\n"
        "|-------|-------|-------|-------|-------------|\n"
        "| DV-01 | 1 | done | ok | regression_test:tests/test_regression_ledger.py |\n"
        "| DV-99 | 9 | done | ok | regression_test:tests/test_regression_ledger.py |\n"
    )
    orphans = _orphan_ledger_ids(state_ids, ledger_text)
    assert orphans == ["DV-99"], f"orphan DV-99 not flagged by reverse check: {orphans}"


def test_dispositions_are_concrete_and_resolvable() -> None:
    """Structural + cited-file-existence check — never runs an eval, never asserts a score."""
    state_ids = {r["id"] for r in _deferred_rows(STATE.read_text(encoding="utf-8"))}
    entries = _ledger_entries(LEDGER.read_text(encoding="utf-8"))
    for dv_id in sorted(state_ids):
        assert dv_id in entries, f"{dv_id} has no parseable disposition row in the ledger"
        e = entries[dv_id]
        kind, value = e["kind"], e["value"]
        if kind in _FILE_KINDS:
            # Ledger stores repo-relative targets WITH the tests/ prefix (e.g.
            # tests/eval_truth.py). Resolve REPO_ROOT/target — do NOT prepend an extra
            # "tests/" (that would double to tests/tests/... and go RED).
            target = value.split("::", 1)[0]
            assert target, f"{dv_id} {kind} disposition has an empty target"
            f = REPO_ROOT / target
            assert f.is_file(), f"{dv_id} cites missing {kind} file: {target}"
        elif kind == "re_defer":
            reason = value
            assert reason.strip().lower() not in _PLACEHOLDER and len(reason) > 15, (
                f"{dv_id} re-defer reason is a placeholder, not a recorded reason: {reason!r}"
            )
        else:
            raise AssertionError(
                f"{dv_id} has an unknown disposition kind {kind!r} "
                f"(expected one of scored_eval / regression_test / re_defer)"
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
