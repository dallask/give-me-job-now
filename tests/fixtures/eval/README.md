# Phase-15 scored-eval fixtures (NOT boolean gates)

These fixtures are the labeled inputs that **Phase 15** (artifact-quality eval) will consume
as **scored evals / UAT** — richness and tone are *quality* judgments, never boolean
hard-gates. Phase 14 deliberately leaves them here without a `test_*.py` that scores them,
because quality scoring is a **locked deferred decision**: richness/tone quality is a scored
eval, never a Phase-14 boolean gate.

## Naming discipline (keeps evals OUT of the gate sweep)

The deterministic gate sweep is `python3 tests/test_*.py`. The Phase-15 eval script that
scores these fixtures **must** be named `eval_*.py` or `calibrate_*.py` (mirroring the
existing `tests/eval_truth.py` and `tests/calibrate_fit.py`) so it is **excluded** from the
`tests/test_*.py` sweep and never runs as a boolean gate. Do **not** add a `tests/test_*.py`
that scores subjective richness or tone quality.

## The two labeled pairs

### 1. Interview-prep richness

- **Draft:** [`tests/fixtures/interview_prep.rich.draft.json`](../interview_prep.rich.draft.json)
  — a multi-section interview-prep draft (`likely_questions`, `star_stories`,
  `talking_points`, `questions_to_ask`), Gate-A-clean.
- **Offer:** [`tests/fixtures/fit/offer.python-mid.sample.json`](../fit/offer.python-mid.sample.json)
- **Expected-richness label:** HIGH — the draft spans four distinct interview-prep sections
  with STAR stories carried as multiple single-span claims. The Phase-15 eval scores whether
  the composed artifact reaches this section depth; Phase 14 only proves it passes the
  existing Gate A/B (see `tests/test_artifact_depth_gates.py`).

### 2. Cover-letter tone

- **Draft:** [`tests/fixtures/cover_letter.toned.draft.json`](../cover_letter.toned.draft.json)
  — a cover-letter draft whose claim texts carry an offer-register tone while every claim
  still cites a resolving `config/candidate.yaml` span (phrasing only, no invented facts).
- **Offer register:** derived from
  [`tests/fixtures/fit/offer.python-mid.sample.json`](../fit/offer.python-mid.sample.json)
  (its `title` / `raw_text_excerpt` establish the target register).
- **Expected-tone label:** ON-REGISTER — the phrasing matches the offer's fast-moving,
  platform-reliability register without fabricating. The Phase-15 eval scores tone alignment;
  Phase 14 only proves the toned draft stays Gate-A-clean.

## What Phase 15 must NOT do

- Do not treat richness or tone as a boolean gate — they are scored evals.
- Do not run the scoring script under a `test_*.py` name — use `eval_*`/`calibrate_*`.
- Do not modify the fixtures to raise a score; they are frozen labeled inputs.
