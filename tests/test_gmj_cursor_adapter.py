#!/usr/bin/env python3
"""PROVIDER-02 file-transform contract for gmj-core/bin/gmj-cursor-adapter.cjs.

Mirrors tests/test_gmj_install_script.py's no-framework main()/test_* auto-collection
convention, _Result stand-in, and run() subprocess-timeout wrapper. Every test here exercises
only the generator's own deterministic file-transform logic (fixture .claude/agents/*.md in,
assert exact .cursor/agents/*.md output) — never a live `cursor-agent` CLI call or
CURSOR_API_KEY, per 39-RESEARCH.md Common Pitfalls Pitfall 5.

No pytest — run with ``python3 tests/test_gmj_cursor_adapter.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER = REPO_ROOT / "gmj-core" / "bin" / "gmj-cursor-adapter.cjs"


class _Result:
    """Minimal CompletedProcess stand-in so a TimeoutExpired reads like a failed run."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: int = 60,
) -> _Result:
    """Run a subprocess with a python-level timeout (no macOS ``timeout`` binary)."""
    try:
        cp = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or REPO_ROOT),
            env=env,
            timeout=timeout,
        )
        return _Result(cp.returncode, cp.stdout, cp.stderr)
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - defensive
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return _Result(124, out, err + "\nTIMEOUT")


def _write_fixture_agent(
    dirpath: Path, name: str, description: str, tools: str, model: str, body: str
) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\ntools: {tools}\nmodel: {model}\n"
        f"color: blue\n---\n\n{body}\n",
        encoding="utf-8",
    )


# Module-level cache so every test exercising the real 9 .claude/agents/*.md files shares one
# generated tempdir rather than re-running the generator per test.
_REAL_GEN_CACHE: dict[str, Path] = {}


def _generate_real_into_tempdir() -> Path:
    if "path" not in _REAL_GEN_CACHE:
        dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-real-"))
        result = run(["node", str(ADAPTER), "generate", "--dest", str(dest)])
        assert result.returncode == 0, (
            f"real generate must exit 0: rc={result.returncode} stderr={result.stderr.strip()[:400]}"
        )
        _REAL_GEN_CACHE["path"] = dest
    return _REAL_GEN_CACHE["path"]


# --- Test 1: fixture readonly:true for read-only tools -----------------------

def test_fixture_readonly_true_for_read_only_tools() -> None:
    src = Path(tempfile.mkdtemp(prefix="gmj-cursor-fixture-src-"))
    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-fixture-dest-"))
    _write_fixture_agent(
        src,
        "gmj-fixture-readonly",
        "A read-only fixture spoke. Does not spawn subagents.",
        "Read, Glob, Grep",
        "sonnet",
        "## Role\n\nFixture body text unique-marker-alpha.",
    )
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"

    text = (dest / "gmj-fixture-readonly.md").read_text(encoding="utf-8")
    assert "readonly: true" in text
    assert "model: inherit" in text
    assert (
        "[EXPERIMENTAL — Cursor adapter, generated from .claude/agents/gmj-fixture-readonly.md "
        "— see gmj-core/bin/CURSOR-HOOK-PARITY.md]"
    ) in text
    assert "GENERATED FILE — DO NOT HAND-EDIT" in text
    assert "Read, Glob, Grep" in text
    assert "unique-marker-alpha" in text
    assert "DO NOT INVOKE AS A SUBAGENT" not in text


# --- Test 2: fixture readonly:false for write-capable tools -------------------

def test_fixture_readonly_false_for_write_capable_tools() -> None:
    src = Path(tempfile.mkdtemp(prefix="gmj-cursor-fixture-src-"))
    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-fixture-dest-"))
    _write_fixture_agent(
        src,
        "gmj-fixture-writer",
        "A write-capable fixture spoke.",
        "Read, Write, Bash",
        "sonnet",
        "## Role\n\nFixture body.",
    )
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"

    text = (dest / "gmj-fixture-writer.md").read_text(encoding="utf-8")
    assert "readonly: false" in text
    assert "readonly: true" not in text


# --- Test 3: malformed frontmatter fails loud, never silently ----------------

def test_malformed_frontmatter_missing_field_fails_loud() -> None:
    src = Path(tempfile.mkdtemp(prefix="gmj-cursor-broken-src-"))
    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-broken-dest-"))
    src.mkdir(parents=True, exist_ok=True)
    (src / "gmj-fixture-broken.md").write_text(
        "---\nname: gmj-fixture-broken\ntools: Read\nmodel: sonnet\n---\n\nbody\n",
        encoding="utf-8",
    )
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode != 0, "a malformed fixture (missing description) must fail loud"
    assert "description" in result.stderr, f"missing-field error must name it: {result.stderr}"
    assert "Traceback" not in result.stderr, f"must be a clean thrown Error: {result.stderr}"


# --- Test 4: real 9 files produce 9 valid Cursor agents -----------------------

def test_real_nine_files_produce_nine_valid_cursor_agents() -> None:
    dest = _generate_real_into_tempdir()
    produced = sorted(p.name for p in dest.glob("*.md"))
    expected = sorted(
        [
            "gmj-artifact-composer.md",
            "gmj-candidate-analyzer.md",
            "gmj-candidate-configurator.md",
            "gmj-cv-generator.md",
            "gmj-fit-evaluator.md",
            "gmj-offer-scout.md",
            "gmj-orchestrator.md",
            "gmj-template-creator.md",
            "gmj-truth-verifier.md",
        ]
    )
    assert produced == expected, f"expected exactly the 9 known source names, got {produced}"
    for name in produced:
        text = (dest / name).read_text(encoding="utf-8")
        assert text.count("---\n") >= 2, f"{name} is not structurally parseable: {text[:200]}"


# --- Test 5: readonly split matches the 39-RESEARCH.md table -----------------

def test_readonly_split_matches_research_table() -> None:
    dest = _generate_real_into_tempdir()
    readonly_true = {"gmj-truth-verifier.md", "gmj-fit-evaluator.md"}
    all_files = {
        "gmj-artifact-composer.md",
        "gmj-candidate-analyzer.md",
        "gmj-candidate-configurator.md",
        "gmj-cv-generator.md",
        "gmj-fit-evaluator.md",
        "gmj-offer-scout.md",
        "gmj-orchestrator.md",
        "gmj-template-creator.md",
        "gmj-truth-verifier.md",
    }
    for name in readonly_true:
        text = (dest / name).read_text(encoding="utf-8")
        assert "readonly: true" in text, f"{name} must resolve readonly:true"
    for name in all_files - readonly_true:
        text = (dest / name).read_text(encoding="utf-8")
        assert "readonly: false" in text, f"{name} must resolve readonly:false"


# --- Test 6: gmj-orchestrator alone gets the DO NOT INVOKE banner ------------

def test_gmj_orchestrator_gets_do_not_invoke_banner() -> None:
    dest = _generate_real_into_tempdir()
    orch_text = (dest / "gmj-orchestrator.md").read_text(encoding="utf-8")
    assert orch_text.count("DO NOT INVOKE AS A SUBAGENT") == 2, (
        "the banner must appear exactly twice (description frontmatter + header comment)"
    )
    other_text = (dest / "gmj-truth-verifier.md").read_text(encoding="utf-8")
    assert "DO NOT INVOKE AS A SUBAGENT" not in other_text, (
        "the banner must be exclusive to the hub's own translation"
    )


# --- Test 7: generator never mutates .claude/agents/*.md ---------------------

def test_generator_never_mutates_source_claude_agents_files() -> None:
    claude_agents_dir = REPO_ROOT / ".claude" / "agents"
    before = {p: p.read_bytes() for p in sorted(claude_agents_dir.glob("*.md"))}

    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-mutate-check-"))
    result = run(["node", str(ADAPTER), "generate", "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"

    after = {p: p.read_bytes() for p in sorted(claude_agents_dir.glob("*.md"))}
    assert before == after, "generator must be provably read-only w.r.t. .claude/agents/*.md"


# --- Test 8: generate twice is byte-identical (deterministic, idempotent) ----

def test_generate_twice_is_byte_identical() -> None:
    dest1 = Path(tempfile.mkdtemp(prefix="gmj-cursor-run1-"))
    dest2 = Path(tempfile.mkdtemp(prefix="gmj-cursor-run2-"))

    r1 = run(["node", str(ADAPTER), "generate", "--dest", str(dest1)])
    assert r1.returncode == 0, f"first generate must exit 0: {r1.stderr.strip()[:400]}"
    r2 = run(["node", str(ADAPTER), "generate", "--dest", str(dest2)])
    assert r2.returncode == 0, f"second generate must exit 0: {r2.stderr.strip()[:400]}"

    names1 = sorted(p.name for p in dest1.glob("*.md"))
    names2 = sorted(p.name for p in dest2.glob("*.md"))
    assert names1 == names2, f"file sets must match across runs: {names1} vs {names2}"
    for name in names1:
        b1 = (dest1 / name).read_bytes()
        b2 = (dest2 / name).read_bytes()
        assert b1 == b2, f"{name} differs across two runs — not deterministic"


# --- Test 9: EXPERIMENTAL label present in the generator's own docstring -----

def test_experimental_label_in_generator_docstring() -> None:
    text = ADAPTER.read_text(encoding="utf-8")
    assert "experimental" in text.lower(), "the module's own source must name EXPERIMENTAL"


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
