#!/usr/bin/env python3
"""E2E-01 deterministic guard-enforcement matrix + E2E-03 deterministic dry-run.

The executable proof of the first sequenced done-criterion: nothing fabricated or
off-target passes, a clean draft reaches the deliverable state, and an approved draft
renders to a real PDF on disk with zero manual authoring.

The matrix drives every gate over the *existing* Phase-5 truth and Phase-6 fit
fixtures via subprocess exit codes (the safety signal is the process exit code, never
a self-report). Three enforced properties plus one chained dry-run:

  Gate A (gmj_check_truth.py)  — a deterministic-category fabrication is hard-blocked (exit 1).
  Gate B (gmj_score_fit.py)    — an off-target draft is hard-blocked (exit 1); on-target passes (0).
  Delivery (check_delivery)— deliverable ONLY when both gate verdicts are recorded pass.
  Dry-run (E2E-02/03)      — approved sample draft -> bridge -> gmj_render_cv.py -> valid PDF.

CRITICAL scoping (Pitfall 1 / threat T-08-09): ``gmj_check_truth.py`` is only the
deterministic pre-gate. It exits 1 on ``numeric_invention`` / ``unresolved_span`` but
is NOT the arbiter of ``scope_inflation`` / ``cross_entry_merge`` — those LLM-layer
fabrications are covered by the Phase-5 ``eval_truth.py`` UAT. The pre-gate's exit code
for an llm-only fixture is incidental (e.g. ``subtle.conflation`` trips the deterministic
numeric_invention rule as a side effect). So the Gate-A exit-1 assertions are SCOPED
strictly to ``expected.jsonl`` rows tagged ``category == "deterministic"``; no llm-only
fabrication fixture is ever asserted here.

No pytest — run with ``python3 tests/test_e2e_guards.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRUTH_DIR = REPO_ROOT / "tests" / "fixtures" / "truth"
FIT_DIR = REPO_ROOT / "tests" / "fixtures" / "fit"

TRUTH_CANDIDATE = "tests/fixtures/truth/candidate.truth.sample.yaml"
FIT_OFFER = "tests/fixtures/fit/offer.python-mid.sample.json"
FIT_THRESHOLDS = "config/fit_thresholds.yaml"
SAMPLE_DRAFT = "tests/fixtures/cv.draft.sample.json"
DRYRUN_PDF = REPO_ROOT / "output" / "cv" / "e2e-dryrun-sample.pdf"


def run(script_rel: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke a repo script under test as a subprocess; exit code is the safety signal."""
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script_rel), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _seed_state(state: dict) -> Path:
    tmp = Path(tempfile.mkdtemp()) / "state.json"
    tmp.write_text(json.dumps(state) + "\n", encoding="utf-8")
    return tmp


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _truth_fixture_expectations() -> dict[str, int | None]:
    """Aggregate truth ``expected.jsonl`` per fixture, SCOPED by ``category`` (T-08-09).

    Returns fixture -> expected check_truth exit code, or ``None`` when the fixture must
    NOT be asserted here (an llm-only fabrication — Phase-5 eval UAT owns its verdict):

      * a fixture with any ``category=="deterministic"`` + ``expected_verdict=="fail"``
        row -> ``1`` (deterministic pre-gate hard-block: numeric_invention / unresolved_span).
      * a fixture whose every row is ``expected_verdict=="pass"`` (clean/good) -> ``0``.
      * otherwise (fail rows exist but only in ``category=="llm"``) -> ``None`` (skip).
    """
    rows_by_fixture: dict[str, list[dict]] = defaultdict(list)
    for row in _load_jsonl(TRUTH_DIR / "expected.jsonl"):
        rows_by_fixture[row["fixture"]].append(row)

    expectations: dict[str, int | None] = {}
    for fixture, rows in rows_by_fixture.items():
        has_deterministic_fail = any(
            r["category"] == "deterministic" and r["expected_verdict"] == "fail"
            for r in rows
        )
        all_pass = all(r["expected_verdict"] == "pass" for r in rows)
        if has_deterministic_fail:
            expectations[fixture] = 1
        elif all_pass:
            expectations[fixture] = 0
        else:
            # llm-only fabrication (scope_inflation / cross_entry_merge / subtle.conflation):
            # deterministic pre-gate exit code is incidental — assert nothing here.
            expectations[fixture] = None
    return expectations


def test_gate_a_deterministic_fabrications_blocked() -> None:
    """Gate A: deterministic-category fabrications -> exit 1; good drafts -> exit 0.

    Assertions are driven off the ``category`` tag in ``expected.jsonl`` so the exit-1
    (block) direction is only ever demanded of ``category=="deterministic"`` fail rows.
    """
    expectations = _truth_fixture_expectations()
    asserted_block = 0
    asserted_pass = 0
    for fixture, expected_exit in sorted(expectations.items()):
        if expected_exit is None:
            continue  # llm-layer fabrication — Phase-5 eval_truth.py UAT owns this verdict
        result = run(
            "scripts/artifacts/gmj_check_truth.py",
            "--file",
            f"tests/fixtures/truth/{fixture}",
            "--candidate",
            TRUTH_CANDIDATE,
        )
        assert result.returncode == expected_exit, (
            f"{fixture}: expected exit {expected_exit}, got {result.returncode}: "
            f"{result.stderr}"
        )
        if expected_exit == 1:
            assert "Traceback" not in result.stderr, (
                f"{fixture}: deterministic block must degrade without a traceback"
            )
            asserted_block += 1
        else:
            asserted_pass += 1
    # Guard the scoping itself: at least one hard-block and one clean-pass were exercised.
    assert asserted_block >= 2, (
        f"expected >=2 deterministic-category blocks, made {asserted_block}"
    )
    assert asserted_pass >= 1, (
        f"expected >=1 clean-draft pass, made {asserted_pass}"
    )


def test_gate_b_offtarget_blocked_ontarget_passes() -> None:
    """Gate B: below-threshold coverage -> exit 1; on-target -> exit 0.

    Driven off ``tests/fixtures/fit/expected.jsonl``: pass.draft (4/5) passes;
    fail.draft (1/5) and borderline.draft (3/5 < 0.7) are hard-blocked.
    """
    asserted_block = 0
    asserted_pass = 0
    for row in _load_jsonl(FIT_DIR / "expected.jsonl"):
        if row.get("coverage_map") is None:
            continue  # empty-musthaves edge needs no coverage map — out of this matrix's scope
        expected_exit = 0 if row["expected_verdict"] == "pass" else 1
        result = run(
            "scripts/artifacts/gmj_score_fit.py",
            "--file",
            f"tests/fixtures/fit/{row['fixture']}",
            "--offer",
            FIT_OFFER,
            "--coverage-map",
            f"tests/fixtures/fit/{row['coverage_map']}",
            "--thresholds",
            FIT_THRESHOLDS,
        )
        assert result.returncode == expected_exit, (
            f"{row['fixture']} ({row['expected_coverage']}): expected exit "
            f"{expected_exit}, got {result.returncode}: {result.stderr}"
        )
        if expected_exit == 1:
            assert "Traceback" not in result.stderr, (
                f"{row['fixture']}: off-target block must degrade without a traceback"
            )
            asserted_block += 1
        else:
            asserted_pass += 1
    assert asserted_block >= 1, "expected >=1 off-target block"
    assert asserted_pass >= 1, "expected >=1 on-target pass"


def test_delivery_requires_both_gates_recorded_pass() -> None:
    """Delivery precondition: deliverable ONLY when both recorded verdicts pass.

    An independent backstop — even a loop bug cannot ship a draft missing a gate verdict.
    """
    ok_state = _seed_state(
        {"gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "pass"}}
    )
    result = run("scripts/pipeline/gmj_check_delivery.py", "--state", str(ok_state))
    assert result.returncode == 0, f"A∧B recorded pass must be deliverable: {result.stderr}"
    assert result.stdout.strip() == "deliverable", result.stdout

    blocked_states = [
        {"gate_results": {"gmj-truth-verifier": "fail", "gmj-fit-evaluator": "pass"}},
        {"gate_results": {"gmj-truth-verifier": "pass", "gmj-fit-evaluator": "fail"}},
        {"gate_results": {"gmj-fit-evaluator": "pass"}},  # truth verdict missing
        {"gate_results": {"gmj-truth-verifier": "pass"}},  # fit verdict missing
        {"current_step": "compose"},  # gate_results absent entirely
    ]
    for state in blocked_states:
        state_path = _seed_state(state)
        result = run("scripts/pipeline/gmj_check_delivery.py", "--state", str(state_path))
        assert result.returncode == 1, f"missing/failed gate must block: {state}"
        assert result.stdout.strip() != "deliverable", f"must not signal deliverable: {state}"
        assert "Traceback" not in result.stderr, f"block must degrade cleanly: {state}"


def assert_valid_pdf(path: Path) -> None:
    """Structural PDF validity: ``%PDF-`` magic bytes + pypdf pages >= 1.

    Never byte-hash the output (Pitfall 5 / T-08-07): gmj_render_cv.py stamps a UTC
    timestamp, so a real PDF is not byte-stable across runs.
    """
    p = Path(path)
    assert p.is_file(), f"no PDF written at {p}"
    with open(p, "rb") as fh:
        assert fh.read(5) == b"%PDF-", f"missing %PDF- magic bytes at {p}"
    import pypdf

    reader = pypdf.PdfReader(str(p))
    assert len(reader.pages) >= 1, f"rendered PDF has zero pages: {p}"


def test_e2e_dryrun_sample_draft_renders_pdf() -> None:
    """Deterministic dry-run: approved sample draft -> bridge -> gmj_render_cv.py -> valid PDF.

    Proves the deterministic slice of E2E-02/E2E-03: an approved artifact_draft renders
    to a real PDF on disk with zero manual authoring. The intermediate CV-YAML is written
    to a tempdir and rendered with explicit ``--lang en`` + ``--out`` so no
    ``candidate.<lang>.yaml`` overlay merge fires and ``config/cv/`` is never polluted
    (Pitfall 3 / T-08-10).
    """
    # (a) demonstrate the sample draft is Gate-A approved (deterministic pre-gate exit 0).
    approved = run(
        "scripts/artifacts/gmj_check_truth.py",
        "--file",
        SAMPLE_DRAFT,
        "--candidate",
        TRUTH_CANDIDATE,
    )
    assert approved.returncode == 0, (
        f"sample draft must be Gate-A approved before render: {approved.stderr}"
    )

    tmp_dir = Path(tempfile.mkdtemp())
    cv_yaml = tmp_dir / "cv.yaml"

    # (b) span-driven bridge: approved claim.text -> CV-YAML (Plan-01 gmj_draft_to_cv_yaml.py).
    bridged = run(
        "scripts/cv/gmj_draft_to_cv_yaml.py",
        "--file",
        SAMPLE_DRAFT,
        "--out",
        str(cv_yaml),
    )
    assert bridged.returncode == 0, f"bridge must succeed: {bridged.stderr}"
    assert cv_yaml.is_file(), "bridge did not write the intermediate CV-YAML"

    # (c) render the bridged CV-YAML to a real PDF (no template, explicit lang + out).
    rendered = run(
        "scripts/cv/gmj_render_cv.py",
        "--config",
        str(cv_yaml),
        "--no-template",
        "--lang",
        "en",
        "--out",
        str(DRYRUN_PDF),
    )
    assert rendered.returncode == 0, f"render must succeed: {rendered.stderr}"
    assert_valid_pdf(DRYRUN_PDF)


CV_GENERATOR_AGENT = REPO_ROOT / ".claude" / "agents" / "gmj-cv-generator.md"
RUNBOOK = REPO_ROOT / "docs" / "RUNBOOK.md"


def test_cv_generator_wired_to_draft_render() -> None:
    """gmj-cv-generator.md draft-mode wires the bridge + all three renderers (E2E-02).

    Positive presence checks — the additive draft-mode branch must name the bridge
    (gmj_draft_to_cv_yaml.py) and each renderer (gmj_render_cv.py / gmj_render_cover_letter.py /
    gmj_render_interview_prep.py) so no artifact is hand-authored (T-08-11).
    """
    text = CV_GENERATOR_AGENT.read_text(encoding="utf-8")
    for token in (
        "gmj_draft_to_cv_yaml.py",
        "gmj_render_cover_letter.py",
        "gmj_render_interview_prep.py",
        "gmj_render_cv.py",
    ):
        assert token in text, f"gmj-cv-generator.md missing draft-mode wiring token: {token}"


def test_runbook_maps_done_criteria() -> None:
    """RUNBOOK.md maps E2E-01 (deterministic, done) to E2E-03 (live UAT) + setup step."""
    text = RUNBOOK.read_text(encoding="utf-8")
    for token in (
        "E2E-01",
        "E2E-03",
        "/pipeline-run",
        "pip install -r scripts/cv/requirements.txt",
    ):
        assert token in text, f"RUNBOOK.md missing required token: {token}"


def main() -> int:
    tests = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
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
