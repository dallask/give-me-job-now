#!/usr/bin/env python3
"""Tests for scripts/offers/gmj_merge_shortlists.py (SCOUT-04, SCOUT-02, SCOUT-01).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_merge_shortlists.py``. Proves the EXECUTED merge authority, not an
LLM, guarantees:

- byte-identical re-runs across two ``PYTHONHASHSEED`` values (SCOUT-04),
- canonical-key dedup collapses a cross-board duplicate (SCOUT-04),
- equal-score entries tie-break on ``canonical_key`` ascending (SCOUT-04),
- an out-of-scope board host is hard-filtered, and an empty allow-list drops all
  entries fail-closed (SCOUT-02),
- the deterministic soft-rank honours ``preferences.ranking`` weights (SCOUT-02),
- the job-seeker ``.md`` view never uses recruiter framing (SCOUT-01).

Discipline (test_validate_preferences.py:117-120): assert the exit code AND the specific
field/sentinel so an unrelated crash's nonzero exit never masquerades as a pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MERGER = REPO_ROOT / "scripts" / "offers" / "gmj_merge_shortlists.py"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "preferences"))
from gmj_validate_preferences import _norm_site  # noqa: E402


def _cli(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MERGER), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _write_board(path: Path, entries: list[dict]) -> Path:
    """Write a wrapped board document (the real offer-scout worker shape)."""
    doc = {"kind": "offer_shortlist", "schema_version": "1.0", "shortlist": entries}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


# --- reusable fixtures ------------------------------------------------------

_SOURCES = {
    "sites": ["https://www.work.ua/", "https://robota.ua/"],
    "cities": ["Kyiv"],
    "languages": ["ua", "en"],
}
_PREFS = {
    "salary": {"min": 3000},
    "work_conditions": {"mode": ["remote", "hybrid"]},
    "search_keywords": ["php", "laravel"],
    "ranking": {"salary_weight": 0.4, "remote_weight": 0.6},
}


def _entry(company: str, title: str, board: str, url: str, **extra: object) -> dict:
    e = {
        "board": board,
        "title": title,
        "company": company,
        "location": "Kyiv",
        "trace": {"source_url": url},
    }
    e.update(extra)
    return e


def _mixed_board() -> list[dict]:
    """Cross-post duplicate + an out-of-scope entry (main determinism fixture)."""
    return [
        # (a) same job cross-posted to two in-scope boards -> one canonical_key.
        _entry("SoftPeak", "Lead PHP Engineer", "https://www.work.ua/", "https://www.work.ua/j/1",
               salary=4000, mode="remote"),
        _entry("SoftPeak", "Lead PHP Engineer", "https://robota.ua/", "https://robota.ua/j/1",
               salary=4000, mode="remote"),
        # (c) an entry on a board host NOT in sources.yaml.
        _entry("Evil", "PHP Dev", "https://evil.example/", "https://evil.example/x",
               salary=9000, mode="remote"),
    ]


def _run_merge(cwd: Path, entries: list[dict], prefs: dict, sources: dict,
               out_name: str = "shortlist.json", env: dict[str, str] | None = None):
    board = _write_board(cwd / "board.json", entries)
    src = _write_yaml(cwd / "sources.yaml", sources)
    pref = _write_yaml(cwd / "preferences.yaml", prefs)
    out_rel = f".pipeline/{out_name}"
    result = _cli(
        ["--board-file", str(board), "--sources", str(src), "--preferences", str(pref),
         "--out", out_rel],
        cwd=cwd, env=env,
    )
    return result, cwd / out_rel


# --- tests ------------------------------------------------------------------

def test_byte_identical_reruns() -> None:  # SCOUT-04
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        r0, out0 = _run_merge(cwd, _mixed_board(), _PREFS, _SOURCES,
                              out_name="run0.json", env={"PYTHONHASHSEED": "0"})
        r1, out1 = _run_merge(cwd, _mixed_board(), _PREFS, _SOURCES,
                              out_name="run1.json", env={"PYTHONHASHSEED": "1"})
        assert r0.returncode == 0, f"run0 must exit 0: {r0.stderr}"
        assert r1.returncode == 0, f"run1 must exit 0: {r1.stderr}"
        assert out0.read_bytes() == out1.read_bytes(), (
            "merge must be byte-identical across identical re-runs under different PYTHONHASHSEED"
        )


def test_cross_board_duplicate_collapses() -> None:  # SCOUT-04 dedup
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        result, out = _run_merge(cwd, _mixed_board(), _PREFS, _SOURCES)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        keys = [e["canonical_key"] for e in json.loads(out.read_text())["shortlist"]]
        assert keys, "output must be non-empty (in-scope cross-post survives)"
        assert len(keys) == len(set(keys)), f"canonical-key dedup must collapse cross-posts: {keys}"


def test_tie_break_is_canonical_key_asc() -> None:  # SCOUT-04 tie-break
    entries = [
        _entry("Beta", "PHP Engineer", "https://www.work.ua/", "https://www.work.ua/b",
               salary=5000, mode="remote"),
        _entry("Alpha", "PHP Engineer", "https://robota.ua/", "https://robota.ua/a",
               salary=5000, mode="remote"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        result, out = _run_merge(cwd, entries, _PREFS, _SOURCES)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        shortlist = json.loads(out.read_text())["shortlist"]
        scores = {round(e["score"], 9) for e in shortlist}
        assert len(scores) == 1, f"fixture must produce equal scores to exercise tie-break: {shortlist}"
        got = [e["canonical_key"] for e in shortlist]
        assert got == sorted(got), f"equal-score entries must order by canonical_key asc: {got}"


def test_out_of_scope_entry_hard_filtered() -> None:  # SCOUT-02
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        result, out = _run_merge(cwd, _mixed_board(), _PREFS, _SOURCES)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        shortlist = json.loads(out.read_text())["shortlist"]
        allowed = {_norm_site(s) for s in _SOURCES["sites"]}
        assert shortlist, "in-scope entries must survive"
        assert all(_norm_site(e["board"]) in allowed for e in shortlist), (
            f"no output board may be outside sources.yaml: {[e['board'] for e in shortlist]}"
        )
        assert not any(_norm_site(e["board"]) == "evil.example" for e in shortlist), (
            "the out-of-scope board must be hard-filtered"
        )
        # Fail-closed: an empty allow-list drops ALL entries (never all-allowed).
        r2, out2 = _run_merge(cwd, _mixed_board(), _PREFS, {"sites": []}, out_name="closed.json")
        assert r2.returncode == 0, f"CLI must exit 0 on empty scope: {r2.stderr}"
        assert json.loads(out2.read_text())["shortlist"] == [], (
            "empty sources.yaml allow-list must drop all entries (fail-closed)"
        )


def test_soft_rank_respects_weights() -> None:  # SCOUT-02
    # A: high salary, non-preferred mode. B: low salary, preferred mode. Equal keyword overlap.
    entries = [
        _entry("Acme", "PHP Engineer", "https://www.work.ua/", "https://www.work.ua/acme",
               salary=6000, mode="onsite"),
        _entry("Boron", "PHP Engineer", "https://robota.ua/", "https://robota.ua/boron",
               salary=1500, mode="remote"),
    ]
    prefs_salary = {**_PREFS, "ranking": {"salary_weight": 0.9, "remote_weight": 0.1}}
    prefs_remote = {**_PREFS, "ranking": {"salary_weight": 0.1, "remote_weight": 0.9}}
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        rs, outs = _run_merge(cwd, entries, prefs_salary, _SOURCES, out_name="salary.json")
        rr, outr = _run_merge(cwd, entries, prefs_remote, _SOURCES, out_name="remote.json")
        assert rs.returncode == 0 and rr.returncode == 0, f"{rs.stderr}\n{rr.stderr}"
        top_salary = json.loads(outs.read_text())["shortlist"][0]["company"]
        top_remote = json.loads(outr.read_text())["shortlist"][0]["company"]
        assert top_salary == "Acme", f"salary-weighted top must be Acme, got {top_salary}"
        assert top_remote == "Boron", f"remote-weighted top must be Boron, got {top_remote}"


def test_md_view_uses_jobseeker_wording() -> None:  # SCOUT-01
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        result, out = _run_merge(cwd, _mixed_board(), _PREFS, _SOURCES)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        md = out.with_suffix(".md")
        assert md.is_file(), "a sibling .md view must be written"
        text = md.read_text().lower()
        assert "candidate" not in text, "shortlist .md must use job-seeker, not recruiter, framing"
        assert "matching vacancies for you" in text, "md must use the job-seeker header"


def test_output_schema_violation_fails_closed() -> None:  # WR-02 frozen-contract guard
    # An assembled entry lacking the required contract keys (board/trace) must fail closed:
    # the merge output is validated against shortlist.schema.json BEFORE writing.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        # In-scope by its top-level source_url host, but carries neither `board` nor `trace`
        # -> a schema-nonconforming assembled entry.
        entry = {
            "title": "PHP Engineer",
            "company": "SoftPeak",
            "location": "Kyiv",
            "source_url": "https://www.work.ua/j/9",
            "salary": 4000,
            "mode": "remote",
        }
        result, out = _run_merge(cwd, [entry], _PREFS, _SOURCES, out_name="bad.json")
        assert result.returncode == 1, (
            f"a schema-nonconforming assembled entry must fail closed (exit 1): {result.stdout}"
        )
        assert "shortlist.schema.json" in result.stderr, (
            f"stderr must name the schema it violated: {result.stderr}"
        )
        assert not out.exists(), "no shortlist must be written when the assembly violates the schema"


def test_host_fallback_keeps_distinct_offers() -> None:  # WR-01 data-loss guard
    # Two genuinely different postings on the SAME in-scope board, both lacking
    # company/title/location, must NOT collapse to one host-only key.
    entries = [
        {"board": "https://www.work.ua/", "trace": {"source_url": "https://www.work.ua/j/1001"},
         "mode": "remote", "salary": 4000},
        {"board": "https://www.work.ua/", "trace": {"source_url": "https://www.work.ua/j/2002"},
         "mode": "remote", "salary": 4000},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        result, out = _run_merge(cwd, entries, _PREFS, _SOURCES)
        assert result.returncode == 0, f"CLI must exit 0: {result.stderr}"
        shortlist = json.loads(out.read_text())["shortlist"]
        keys = [e["canonical_key"] for e in shortlist]
        assert len(shortlist) == 2, (
            f"distinct same-host offers must both survive, not dedup-collapse: {keys}"
        )
        assert len(set(keys)) == 2, f"host-fallback keys must stay distinct: {keys}"
        assert all("work.ua" in k for k in keys), f"keys must still key off the host: {keys}"


def test_nan_infinity_score_rejected() -> None:  # SCOUT-04 canonical-JSON validity
    # A raw board file carrying a non-finite numeric literal (Python's json emits bare NaN
    # by default) must be REJECTED on load, never silently re-emitted as invalid RFC-8259
    # JSON nor fed into the input-order-dependent NaN sort.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        entry = _entry("SoftPeak", "Lead PHP Engineer", "https://www.work.ua/",
                       "https://www.work.ua/j/1", salary=float("nan"), mode="remote")
        board_doc = {"kind": "offer_shortlist", "schema_version": "1.0", "shortlist": [entry]}
        board = cwd / "board.json"
        # allow_nan default True -> writes a bare `NaN` literal into the file on disk.
        board.write_text(json.dumps(board_doc), encoding="utf-8")
        assert "NaN" in board.read_text(), "fixture must contain a bare NaN literal"
        src = _write_yaml(cwd / "sources.yaml", _SOURCES)
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        out_rel = ".pipeline/nan.json"
        result = _cli(
            ["--board-file", str(board), "--sources", str(src),
             "--preferences", str(pref), "--out", out_rel],
            cwd=cwd,
        )
        assert result.returncode == 1, f"a NaN board literal must be rejected (exit 1): {result.stdout}"
        assert "non-finite" in result.stderr.lower(), (
            f"stderr must name the non-finite rejection: {result.stderr}"
        )
        assert not (cwd / out_rel).exists(), "no shortlist must be written when input is rejected"

    # Infinity must be rejected the same way.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        board = cwd / "board.json"
        board.write_text(
            '{"kind":"offer_shortlist","schema_version":"1.0","shortlist":'
            '[{"board":"https://www.work.ua/","title":"X","company":"Y","location":"Kyiv",'
            '"trace":{"source_url":"https://www.work.ua/j/2"},"salary":Infinity,"mode":"remote"}]}',
            encoding="utf-8",
        )
        src = _write_yaml(cwd / "sources.yaml", _SOURCES)
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        result = _cli(
            ["--board-file", str(board), "--sources", str(src),
             "--preferences", str(pref), "--out", ".pipeline/inf.json"],
            cwd=cwd,
        )
        assert result.returncode == 1, f"an Infinity board literal must be rejected: {result.stdout}"
        assert "non-finite" in result.stderr.lower(), f"stderr must name it: {result.stderr}"


def test_out_path_traversal_rejected() -> None:  # WR-03 containment guard
    # The --out containment guard must reject any path outside .pipeline/, both an absolute
    # escape and a ../ escape, with exit 1 and the sentinel — and write nothing outside.
    for out_arg, label in (("__ABS__", "absolute escape"), (".pipeline/../escape.json", "../ escape")):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            board = _write_board(cwd / "board.json", _mixed_board())
            src = _write_yaml(cwd / "sources.yaml", _SOURCES)
            pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
            escape_abs = cwd / "escape.json"
            out_val = str(escape_abs) if out_arg == "__ABS__" else out_arg
            result = _cli(
                ["--board-file", str(board), "--sources", str(src),
                 "--preferences", str(pref), "--out", out_val],
                cwd=cwd,
            )
            assert result.returncode == 1, f"{label} must exit 1: {result.stdout}"
            assert "Refusing to write outside" in result.stderr, (
                f"{label} must print the containment sentinel: {result.stderr}"
            )
            assert not escape_abs.exists(), f"{label} must not create a file outside .pipeline/"
            assert not (cwd / "escape.json").exists(), f"{label} must not escape .pipeline/"


def test_missing_sources_fails_closed_nonzero() -> None:  # WR-06 scope-integrity
    # A MISSING sources.yaml (as opposed to a present-but-empty allow-list) must fail closed
    # with a non-zero exit and a clear stderr notice — never a silent exit-0 empty shortlist.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        board = _write_board(cwd / "board.json", _mixed_board())
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        missing = cwd / "no-such-sources.yaml"
        assert not missing.exists(), "fixture sources.yaml must be absent"
        result = _cli(
            ["--board-file", str(board), "--sources", str(missing),
             "--preferences", str(pref), "--out", ".pipeline/out.json"],
            cwd=cwd,
        )
        assert result.returncode == 1, (
            f"missing sources.yaml must fail closed (exit 1), not silent exit 0: {result.stdout}"
        )
        assert "FAIL-CLOSED" in result.stderr and "not found" in result.stderr, (
            f"stderr must clearly report the missing allow-list: {result.stderr}"
        )
        assert not (cwd / ".pipeline/out.json").exists(), (
            "no shortlist must be written when the allow-list is missing"
        )


def test_dual_shape_loader() -> None:  # WR-04 dual-shape board loader
    # The loader accepts a wrapped {...,'shortlist':[...]} doc, a BARE top-level JSON list,
    # and a --stdin bundle; a non-list/non-object top level is the error path.
    entries = [
        _entry("SoftPeak", "Lead PHP Engineer", "https://www.work.ua/",
               "https://www.work.ua/j/1", salary=4000, mode="remote"),
    ]
    # (1) bare top-level JSON list.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        board = cwd / "bare.json"
        board.write_text(json.dumps(entries), encoding="utf-8")  # bare list, no wrapper
        src = _write_yaml(cwd / "sources.yaml", _SOURCES)
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        result = _cli(
            ["--board-file", str(board), "--sources", str(src),
             "--preferences", str(pref), "--out", ".pipeline/bare.json"],
            cwd=cwd,
        )
        assert result.returncode == 0, f"bare-list board must load (exit 0): {result.stderr}"
        shortlist = json.loads((cwd / ".pipeline/bare.json").read_text())["shortlist"]
        assert len(shortlist) == 1, f"bare-list entry must survive to output: {shortlist}"

    # (2) --stdin bundle (wrapped shape via stdin).
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        src = _write_yaml(cwd / "sources.yaml", _SOURCES)
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        board_doc = {"kind": "offer_shortlist", "schema_version": "1.0", "shortlist": entries}
        result = subprocess.run(
            [sys.executable, str(MERGER), "--stdin", "--sources", str(src),
             "--preferences", str(pref), "--out", ".pipeline/stdin.json"],
            cwd=str(cwd), capture_output=True, text=True, input=json.dumps(board_doc),
            env={**os.environ},
        )
        assert result.returncode == 0, f"--stdin bundle must load (exit 0): {result.stderr}"
        shortlist = json.loads((cwd / ".pipeline/stdin.json").read_text())["shortlist"]
        assert len(shortlist) == 1, f"--stdin entry must survive to output: {shortlist}"

    # (3) error path: a top-level JSON scalar is neither a list nor an object-with-shortlist.
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        board = cwd / "scalar.json"
        board.write_text("42", encoding="utf-8")
        src = _write_yaml(cwd / "sources.yaml", _SOURCES)
        pref = _write_yaml(cwd / "preferences.yaml", _PREFS)
        result = _cli(
            ["--board-file", str(board), "--sources", str(src),
             "--preferences", str(pref), "--out", ".pipeline/err.json"],
            cwd=cwd,
        )
        assert result.returncode == 1, f"a scalar top level must be an error (exit 1): {result.stdout}"
        assert "Invalid board input" in result.stderr, (
            f"stderr must flag the invalid board shape: {result.stderr}"
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
