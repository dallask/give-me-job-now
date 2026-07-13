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


# --- Test 5: readonly split matches the current .claude/agents/ tool grants --
#
# gmj-truth-verifier.md and gmj-fit-evaluator.md moved from the 39-RESEARCH.md table's
# readonly_true bucket to readonly_false in phase 07 (PIPEFIX-03): both gained a narrowly
# scoped Write tool for their own gate-result output files (07-04-PLAN.md).

def test_readonly_split_matches_research_table() -> None:
    dest = _generate_real_into_tempdir()
    readonly_true = set()
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


# --- Test 10: CURSOR-HOOK-PARITY.md has all four items with status tags -----

def test_cursor_hook_parity_doc_has_four_items_with_status_tags() -> None:
    parity = REPO_ROOT / "gmj-core" / "bin" / "CURSOR-HOOK-PARITY.md"
    text = parity.read_text(encoding="utf-8")
    for needle in (
        "PreToolUse",
        "SubagentStop",
        "Task-nesting",
        "readonly",
        "gmj-sources-scope-guard.sh",
        "gmj-validate-envelope.sh",
    ):
        assert needle in text, f"CURSOR-HOOK-PARITY.md missing required item marker: {needle}"
    for tag in (
        "not independently verified — reasoned from direct installed-binary source inspection",
        "open — no runtime equivalent",
        "known, permanent precision loss",
    ):
        assert tag in text, f"CURSOR-HOOK-PARITY.md missing required status tag: {tag}"


# --- Test 11: the full exact Finding-2 tag appears in BOTH the parity doc and README ---

def test_finding2_tag_present_in_parity_doc_and_readme() -> None:
    parity = REPO_ROOT / "gmj-core" / "bin" / "CURSOR-HOOK-PARITY.md"
    readme = REPO_ROOT / "gmj-core" / "bin" / "gmj-cursor-adapter.README.md"
    exact_tag = (
        "not independently verified — reasoned from direct installed-binary source "
        "inspection, needs a human's live Cursor session to confirm"
    )
    for path in (parity, readme):
        text = path.read_text(encoding="utf-8")
        assert exact_tag in text, f"{path} is missing the exact Finding-2 caveat tag"


# --- Test 12: README documents the operator prerequisite + field-translation table ---

def test_readme_documents_prerequisite_and_field_translation_table() -> None:
    readme = REPO_ROOT / "gmj-core" / "bin" / "gmj-cursor-adapter.README.md"
    text = readme.read_text(encoding="utf-8")
    assert "Cursor CLI" in text or "Cursor IDE" in text, "README missing the operator prerequisite"
    assert "readonly" in text, "README missing the readonly field in its translation table"
    assert "inherit" in text, "README missing the inherit model value in its translation table"
    assert "Task" in text and "tool" in text, (
        "README missing the Pitfall-1 Task-tool correction"
    )


# --- Test 13: new gmj-core/bin/ files stay excluded from the gmj-core/ payload census ---

def test_new_adapter_files_excluded_from_gmj_core_census() -> None:
    build_script = REPO_ROOT / "scripts" / "gmj_build_payload.py"
    payload_root = Path(tempfile.mkdtemp(prefix="gmj-core-census-"))
    env = dict(os.environ)
    env["GMJ_PAYLOAD_ROOT"] = str(payload_root)
    result = run([sys.executable, str(build_script)], cwd=REPO_ROOT, env=env, timeout=180)
    assert result.returncode == 0, (
        f"isolated payload build must exit 0: rc={result.returncode} "
        f"stderr={result.stderr.strip()[:400]}"
    )
    manifest_path = payload_root / "gmj-file-manifest.json"
    assert manifest_path.is_file(), f"manifest not found at {manifest_path}"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files"]
    for key in files:
        assert "gmj-cursor-adapter" not in key, f"census leaked adapter file: {key}"
        assert "CURSOR-HOOK-PARITY" not in key, f"census leaked parity doc: {key}"
    shutil.rmtree(payload_root, ignore_errors=True)


# --- Test 14: default Claude Code path carries zero references to this phase's tooling ---

def test_default_claude_code_path_has_no_cursor_references() -> None:
    forbidden = (".cursor/", "gmj-cursor-adapter", "CURSOR-HOOK-PARITY")
    paths = sorted((REPO_ROOT / ".claude" / "agents").glob("*.md")) + [
        REPO_ROOT / ".claude" / "commands" / "gmj-collective.md",
        REPO_ROOT / ".claude" / "commands" / "gmj-pipeline-run.md",
        REPO_ROOT / ".claude" / "settings.json",
    ]
    for path in paths:
        assert path.is_file(), f"expected default-path file missing: {path}"
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path} references this phase's new tooling: {needle}"


# --- Test 15: committed .cursor/agents/*.md files match a fresh regeneration (WR-02) ---

def test_committed_cursor_agents_match_fresh_regeneration() -> None:
    dest = _generate_real_into_tempdir()
    real = REPO_ROOT / ".cursor" / "agents"
    for name in sorted(p.name for p in dest.glob("*.md")):
        assert (dest / name).read_bytes() == (real / name).read_bytes(), (
            f"{name}: checked-in .cursor/agents/ has drifted from a fresh regeneration"
        )


# --- Test 16: stale generated file is pruned when its source is removed/renamed (WR-01) ---

def test_stale_generated_file_is_pruned_when_source_removed() -> None:
    src = Path(tempfile.mkdtemp(prefix="gmj-cursor-prune-src-"))
    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-prune-dest-"))
    _write_fixture_agent(src, "gmj-fixture-a", "fixture a", "Read", "sonnet", "body a")
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"
    (src / "gmj-fixture-a.md").unlink()  # simulate spoke removal/rename
    _write_fixture_agent(src, "gmj-fixture-b", "fixture b", "Read", "sonnet", "body b")
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"
    assert not (dest / "gmj-fixture-a.md").exists(), (
        "renamed/removed source's stale generated output must be pruned"
    )
    assert (dest / "gmj-fixture-b.md").exists()
    assert "removed stale" in result.stdout, "prune must be reported on stdout"


# --- Test 17: a non-generated .md file in destDir is never deleted by prune (CR-01) ---

def test_non_generated_file_in_dest_survives_prune() -> None:
    src = Path(tempfile.mkdtemp(prefix="gmj-cursor-prune-src-"))
    dest = Path(tempfile.mkdtemp(prefix="gmj-cursor-prune-dest-"))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "my-custom-cursor-agent.md").write_text(
        "hand-authored, not ours\n", encoding="utf-8"
    )
    _write_fixture_agent(src, "gmj-fixture-a", "fixture a", "Read", "sonnet", "body a")
    result = run(["node", str(ADAPTER), "generate", "--src", str(src), "--dest", str(dest)])
    assert result.returncode == 0, f"generate must exit 0: {result.stderr.strip()[:400]}"
    assert (dest / "my-custom-cursor-agent.md").exists(), (
        "non-generated files (no GENERATED FILE marker) must never be deleted"
    )
    assert (dest / "my-custom-cursor-agent.md").read_text(encoding="utf-8") == (
        "hand-authored, not ours\n"
    ), "surviving non-generated file's content must be untouched"
    assert "leaving non-generated file untouched" in result.stderr, (
        "skipping a non-generated file must be logged, not silent"
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
