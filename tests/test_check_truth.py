#!/usr/bin/env python3
"""Deterministic-category unit tests for the check_truth.py Gate-A pre-gate (Plan 05-04).

Runnable as a plain assertion script (no pytest), matching the repo convention of
``python3 tests/test_*.py``. Each test proves an EXECUTED deterministic invariant — never
LLM 4-rule accuracy (Pitfall 2: the semantic R1/R3 judgments belong to the LLM eval in
Plan 05-05, not here). The deterministic category asserted here is:

- a resolvable span passes the deterministic layer (good.vocab_swap exits 0),
- an unresolvable / out-of-range span FAILs, naming the offending claim_index + span,
- an empty source_span auto-FAILs,
- the thin numeric-invention heuristic FAILs an invented number AND does NOT false-positive
  on a word-fraction reframe,
- the verdict is PER-CLAIM (offending_claims list), never a whole-document score,
- no override/bypass/force flag exists in the source (TRUTH-03 non-bypass),
- the emitted content validates against gate_result.schema.json#/$defs/gate_a_content.

Only stdlib + PyYAML + jsonschema are used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "contracts"))
from validate_envelope import build_registry  # noqa: E402  reuse the local schema registry

CHECK = REPO_ROOT / "scripts" / "artifacts" / "check_truth.py"
TRUTH = FIXTURES / "truth"
CANDIDATE = TRUTH / "candidate.truth.sample.yaml"
SCHEMA_DIR = REPO_ROOT / "schemas"
GATE_RESULT_SCHEMA = SCHEMA_DIR / "gate_result.schema.json"

VOCAB_SWAP = TRUTH / "good.vocab_swap.draft.json"
NUMERIC_REFRAME = TRUTH / "good.numeric_reframe.draft.json"
UNRESOLVED_SPAN = TRUTH / "bad.unresolved_span.draft.json"
NUMERIC_INVENTION = TRUTH / "bad.numeric_invention.draft.json"


def _run_truth(draft_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--file", str(draft_path), "--candidate", str(CANDIDATE)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _run_truth_in_mode(draft_path: Path, execution_mode: str) -> subprocess.CompletedProcess:
    """Run Gate-A with an ambient run-scoped state recording ``execution_mode``.

    The gate takes NO mode input (Pitfall 1: mode must never gate the gate). We nonetheless
    make the recorded ``execution_mode`` *available* to the invocation — via a run-scoped
    ``.pipeline/runs/<run_id>/state.json`` payload on disk AND an ``EXECUTION_MODE`` env var —
    so the ONLY difference between a human-in-the-loop run and an autonomous run is that mode
    signal. If the gate's exit code and emitted verdict are byte-identical across the two, the
    gate is provably indistinguishable between modes: it never reads either signal.
    """
    run_dir = Path(tempfile.mkdtemp())
    state_dir = run_dir / ".pipeline" / "runs" / "run-modeparity"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {"run_id": "run-modeparity", "execution_mode": execution_mode},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["EXECUTION_MODE"] = execution_mode
    try:
        return subprocess.run(
            [sys.executable, str(CHECK), "--file", str(draft_path), "--candidate", str(CANDIDATE)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
    finally:
        for leaf in (
            state_dir / "state.json",
            state_dir,
            run_dir / ".pipeline" / "runs",
            run_dir / ".pipeline",
            run_dir,
        ):
            try:
                leaf.unlink() if leaf.is_file() else leaf.rmdir()
            except OSError:
                pass


def test_good_vocab_swap_span_resolves_exit_0() -> None:
    result = _run_truth(VOCAB_SWAP)
    assert result.returncode == 0, (
        "good.vocab_swap span resolves; deterministic layer must exit 0, got "
        f"{result.returncode}\nstderr: {result.stderr}"
    )


def test_unresolved_span_fails_and_names_it() -> None:
    result = _run_truth(UNRESOLVED_SPAN)
    assert result.returncode == 1, (
        f"bad.unresolved_span must exit 1, got {result.returncode}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "certifications[0].credentials[9]" in combined, (
        f"gate must name the offending source_span; output: {combined}"
    )
    verdict = json.loads(result.stdout)
    indices = [c["claim_index"] for c in verdict["content"]["offending_claims"]]
    assert 1 in indices, (
        f"gate must name offending claim_index 1 (per-claim), got {indices}"
    )


def test_empty_span_fails() -> None:
    draft = {
        "schema_version": "1.0",
        "kind": "artifact_draft",
        "content": {
            "artifact_type": "cv",
            "language": "en",
            "claims": [
                {"text": "Empty span claim", "source_span": "", "section": "header"}
            ],
        },
    }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(draft, fh)
        tmp_path = Path(fh.name)
    try:
        result = _run_truth(tmp_path)
        assert result.returncode == 1, (
            f"empty source_span must auto-FAIL (exit 1), got {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        verdict = json.loads(result.stdout)
        rules = [c["rule_violated"] for c in verdict["content"]["offending_claims"]]
        assert "unresolved_span" in rules, (
            f"empty span must FAIL as unresolved_span, got {rules}"
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def test_numeric_invention_fails() -> None:
    result = _run_truth(NUMERIC_INVENTION)
    assert result.returncode == 1, (
        f"bad.numeric_invention must exit 1, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "numeric_invention" in (result.stdout + result.stderr), (
        f"gate must name rule numeric_invention; output: {result.stdout}{result.stderr}"
    )


def test_numeric_reframe_passes() -> None:
    result = _run_truth(NUMERIC_REFRAME)
    assert result.returncode == 0, (
        "good.numeric_reframe is a word-fraction reframe (no digit token); the heuristic "
        f"must not false-positive, expected exit 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_verdict_is_per_claim_not_whole_doc() -> None:
    result = _run_truth(UNRESOLVED_SPAN)
    verdict = json.loads(result.stdout)
    content = verdict["content"]
    assert isinstance(content.get("offending_claims"), list), (
        "verdict must expose a per-claim offending_claims list, not a whole-doc score"
    )
    assert content["offending_claims"], "the failing fixture must name at least one claim"
    assert all("claim_index" in c for c in content["offending_claims"]), (
        "each offending entry must name its claim_index (per-claim verdict)"
    )
    assert "score" not in content, (
        "Gate-A must not emit a whole-document similarity score field"
    )


def test_no_bypass_flag() -> None:
    source = CHECK.read_text(encoding="utf-8")
    for flag in ("--override", "--bypass", "--force"):
        assert flag not in source, (
            f"TRUTH-03 non-bypass: forbidden flag token {flag!r} must not appear in source"
        )
    assert "--file" in source and "--candidate" in source, (
        "check_truth.py must still expose its --file/--candidate inputs"
    )


def test_gate_exposes_no_mode_or_bypass_flag() -> None:
    # Pitfall 1 (mode must never gate the gate): the gate CLI must expose NONE of the
    # tokens below in its argparse — execution_mode lives only in state, never as an input
    # to a gate. Strengthens the no-bypass idiom with the --mode token.
    source = CHECK.read_text(encoding="utf-8")
    for flag in ("--mode", "--force", "--bypass", "--override"):
        assert flag not in source, (
            f"Pitfall 1: forbidden token {flag!r} must not appear in the gate source — "
            "mode/bypass can never reach Gate-A"
        )


def test_mode_parity_fabricated_draft_blocks_identically() -> None:
    # A known-fabricated draft (out-of-range source_span) must be blocked IDENTICALLY whether
    # the ambient run records execution_mode="human_in_the_loop" or "autonomous". The gate
    # takes no mode input, so the exit code and emitted verdict must be byte-identical.
    human = _run_truth_in_mode(UNRESOLVED_SPAN, "human_in_the_loop")
    auto = _run_truth_in_mode(UNRESOLVED_SPAN, "autonomous")
    assert human.returncode == 1 and auto.returncode == 1, (
        "fabricated draft must be blocked (exit 1) in both modes, got "
        f"human={human.returncode} auto={auto.returncode}"
    )
    assert human.returncode == auto.returncode, (
        "mode must never change the gate exit code (Pitfall 1)"
    )
    assert human.stdout == auto.stdout, (
        "the emitted Gate-A verdict must be byte-identical across execution modes — mode is "
        "never an argument to the gate, so the two runs are provably indistinguishable"
    )


def test_emitted_gate_result_validates() -> None:
    result = _run_truth(UNRESOLVED_SPAN)
    verdict = json.loads(result.stdout)
    schema = json.loads(GATE_RESULT_SCHEMA.read_text(encoding="utf-8"))
    subschema = schema["$defs"]["gate_a_content"]
    registry = build_registry(SCHEMA_DIR)
    validator = Draft202012Validator(subschema, registry=registry)
    errors = [e.message for e in validator.iter_errors(verdict["content"])]
    assert not errors, (
        f"emitted content must validate against gate_a_content; errors: {errors}"
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
