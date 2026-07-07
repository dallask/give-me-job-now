#!/usr/bin/env python3
"""PACKAGE-03/04 GSD-removal dry-run contract (RED-first, Wave-0).

The machine-checkable acceptance contract for ``scripts/gmj_remove_gsd.py`` (built in 18-08):
a manifest-driven framework-trace REPORTER that makes ZERO deletions this milestone. This test
is EXPECTED to fail RED now — the removal script does not exist yet. It fails for the
*not-yet-built target*, never a harness error: the script-absence surfaces as a named
assertion, and every subprocess assertion also checks ``"Traceback" not in result.stderr``.

Four named checks (each a ``test_*`` so it is individually reported):
  (a) banner        — exit 0 AND a loud "NOT executed" / "run later" dry-run banner in stdout.
  (b) manifest plan — the REMOVE PLAN enumerates framework traces derived from the
                      ownership-manifest framework_globs + the enumerated trace set
                      (asserts .planning/ appears; NO app gmj-* path appears). The GSD tooling
                      tree was migrated to a global install, so .planning/ is the sole trace left.
  (c) no-delete     — the script SOURCE contains no os.remove / shutil.rmtree / Path.unlink /
                      os.unlink (comment lines stripped first, so a docstring mention can't
                      self-invalidate; the live-code count must be 0).
  (d) zero-mutation — snapshot {path: (bytes, st_mtime_ns)} for the repo file set AND the rglob
                      tree set before invocation; after running the reporter both are unchanged
                      (catches stray new/removed files as well as in-place writes).

No pytest — run with ``python3 tests/test_gmj_remove_gsd.py``. macOS has no ``timeout`` binary,
so any subprocess time limit uses ``subprocess.run(timeout=...)``, never a shell ``timeout``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOVE_SCRIPT = REPO_ROOT / "scripts" / "gmj_remove_gsd.py"
REMOVE_SCRIPT_REL = "scripts/gmj_remove_gsd.py"

# Directories excluded from the zero-mutation snapshot: volatile, generated, or huge — none of
# which the read-only reporter should touch, and which churn independently of the test.
_SNAPSHOT_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", "output", ".venv", "venv",
}

# Expected framework traces that MUST appear in the printed REMOVE PLAN.
# The GSD tooling tree (.claude/gsd-core/, gsd-* agents/commands/hooks) was migrated to a
# global install and removed from the repo, so .planning/ is the sole remaining framework trace.
EXPECTED_TRACE_TOKENS = (".planning/",)

# Live-code deletion primitives that must NOT appear anywhere in the reporter source.
DELETE_PRIMITIVES = ("os.remove", "shutil.rmtree", "Path.unlink", "os.unlink", ".unlink(")


class _Result:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(*args: str, timeout: int = 120) -> _Result:
    """Invoke the removal reporter as a subprocess; exit code + stdout are the signal."""
    try:
        cp = subprocess.run(
            [sys.executable, str(REMOVE_SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=timeout,
        )
        return _Result(cp.returncode, cp.stdout, cp.stderr)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _Result(124, out, err + "\nTIMEOUT")


# --- (a) dry-run banner ------------------------------------------------------

def test_a_dryrun_banner() -> None:
    result = run()
    assert result.returncode == 0, (
        f"reporter must exit 0 — not built yet? ({REMOVE_SCRIPT_REL}): "
        f"rc={result.returncode} stderr={result.stderr.strip()[:400]}"
    )
    assert "Traceback" not in result.stderr, f"reporter crashed: {result.stderr}"
    lowered = result.stdout.lower()
    assert "not executed" in lowered, (
        f"dry-run banner missing a loud 'NOT executed' signal: {result.stdout[:400]}"
    )
    assert "run later" in lowered or "run it later" in lowered, (
        f"dry-run banner missing a 'run later' signal: {result.stdout[:400]}"
    )


# --- (b) manifest-driven REMOVE PLAN -----------------------------------------

def test_b_manifest_driven_remove_plan() -> None:
    result = run()
    assert result.returncode == 0, (
        f"reporter must exit 0 — not built yet? rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    assert "Traceback" not in result.stderr, result.stderr
    out = result.stdout
    assert "REMOVE PLAN" in out, f"reporter must print a labelled REMOVE PLAN: {out[:400]}"
    for token in EXPECTED_TRACE_TOKENS:
        assert token in out, f"REMOVE PLAN must enumerate the framework trace {token!r}: {out[:600]}"
    # No app gmj-* path may ever appear in the plan (removal targets FRAMEWORK only).
    for line in out.splitlines():
        assert "gmj-" not in line or "gsd" in line.lower(), (
            f"REMOVE PLAN must not list any app gmj-* path: {line!r}"
        )


# --- (c) no live-delete branch in the source ---------------------------------

def test_c_no_delete_primitives_in_source() -> None:
    assert REMOVE_SCRIPT.is_file(), (
        f"removal reporter not built yet: {REMOVE_SCRIPT_REL} (Wave 3). "
        "This check gates PACKAGE-04's hard-wired dry-run (no delete branch exists)."
    )
    # Strip whole-line comments before counting so a docstring/head-comment mention of a
    # deletion primitive cannot self-invalidate the negative check.
    code_lines = [
        ln for ln in REMOVE_SCRIPT.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    found = [prim for prim in DELETE_PRIMITIVES if prim in code]
    assert not found, (
        f"removal reporter must contain NO live-code deletion primitives, found: {found}"
    )


# --- (d) zero-mutation bytes+mtime invariant ---------------------------------

def _repo_files() -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*"):
        if any(part in _SNAPSHOT_SKIP_DIRS for part in p.relative_to(REPO_ROOT).parts):
            continue
        if p.is_file():
            files.append(p)
    return files


def _tree_set() -> set[Path]:
    tree: set[Path] = set()
    for p in REPO_ROOT.rglob("*"):
        rel = p.relative_to(REPO_ROOT)
        if any(part in _SNAPSHOT_SKIP_DIRS for part in rel.parts):
            continue
        tree.add(rel)
    return tree


def test_d_zero_mutation_invariant() -> None:
    before: dict[Path, tuple[bytes, int]] = {}
    for p in _repo_files():
        st = p.stat()
        before[p] = (p.read_bytes(), st.st_mtime_ns)
    assert before, "snapshot is empty — the repo file walk is broken"
    tree_before = _tree_set()

    run()  # dry-run reporter — whether or not it exists yet, it must mutate nothing

    for p, (raw, mtime_ns) in before.items():
        assert p.is_file(), f"reporter removed a file (deletion!): {p}"
        st = p.stat()
        assert p.read_bytes() == raw, f"reporter mutated file bytes (write!): {p}"
        assert st.st_mtime_ns == mtime_ns, f"reporter changed st_mtime_ns (write!): {p}"

    tree_after = _tree_set()
    assert tree_after == tree_before, (
        "repo tree listing changed — a file/dir was added or removed (write!): "
        f"added={sorted(str(p) for p in tree_after - tree_before)} "
        f"removed={sorted(str(p) for p in tree_before - tree_after)}"
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
