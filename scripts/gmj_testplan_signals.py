#!/usr/bin/env python3
"""Verbatim-transcribed per-flow signal-table data for Phase 4 (TPGEN-07/TPGEN-08).

Sole purpose: a hand-authored, never runtime-parsed data source grounding
``scripts/gmj_testplan_gen.py``'s per-flow evaluation section in the `investigate`
workstream's already-fact-checked Signal Reference table
(``.planning/workstreams/investigate/phases/02-evaluation-criteria-grounding/02-EVALUATION-CRITERIA.md``),
per D-01. That table's own Citation Audit already cross-checked every schema field, file
path, and exit code it cites against the real codebase -- this module reuses that already-
verified prose directly rather than re-deriving/re-extracting it from ``schemas/*.schema.json``
at generation time.

**Narrow LLM-assist boundary (D-02).** Every ``pass_signal``/``fail_signal``/``signal_source``/
``semantic_caveat`` cell below is copied character-for-character from the source table's
corresponding row/column -- never paraphrased, shortened, or "cleaned up". The one structural
exception is the shared Gate A/B judgment-call caveat (flows 2/3/4/7 per the source table's
own by-reference prose, e.g. Flow 3's cell literally reads "Same Gate A/B judgment-call caveat
as Flow 2 -- <addendum>"): rather than transcribing that shorthand reference literally (which
would be meaningless once each flow's generated file is read standalone, with no adjacent
table row for context), this module resolves the reference structurally --
``_GATE_AB_JUDGMENT_CAVEAT`` holds Flow 2's full canonical caveat text once, and each of the 3
other gated rows' ``semantic_caveat`` value is that same constant plus its own row's verbatim
trailing addendum sentence, concatenated at import time with an em-dash-surrounded-by-spaces
separator between the constant and the addendum -- matching the source table's own
"Same Gate A/B judgment-call caveat as Flow 2 -- <addendum>" convention exactly, so the join
never collapses into a bare-space run-on sentence with no clause boundary (a documented,
regression-tested normalization, not an accidental omission). This is the one narrow "assist"
(structural de-duplication, not wording synthesis) this module performs; every other cell is a
direct 1:1 transcription with zero rewriting. Relatedly, any backslash-escaped-pipe Markdown-
table-cell-escape artifact copied verbatim from the source document's own escaping context is
un-escaped back to a literal ``|`` before storage here, since this module's cells are re-escaped
fresh by ``gmj_testplan_gen.py``'s ``_escape_table_cell()`` at render time -- storing a
pre-escaped pipe would be double-escaped on render.

**D-04 literal.** The 4 genuinely mechanical flows (no LLM/agent judgment component at all --
firecrawl-search, resume-flow, operator-monitoring, cleanup-wizard) render the literal string
``"None — fully mechanical"`` regardless of the source table's own (differently-worded) "None —
..." prose in that cell, per D-04's uniform-literal requirement. scheduled-runs (flow 7) is
explicitly NOT one of these 4 -- its cell inherits the shared Gate A/B caveat by reference, not
a blank/mechanical cell (see the source table's own Legend and the plan's Pitfall 2 discussion).
"""

from __future__ import annotations

_GATE_AB_JUDGMENT_CAVEAT: str = (
    "Gate A's verdict is a gmj-truth-verifier judgment call: `rule_violated` enum values (`unresolved_span`, `scope_inflation`, `numeric_invention`, `cross_entry_merge` — `schemas/gate_result.schema.json`'s `offending_claim` $def) encode a reframe-vs-fabrication line that is a judgment call, not machine-checkable. Gate B's hard-block half (`coverage.score >= coverage_threshold`, currently 0.7 in `config/fit_thresholds.yaml`) is mechanical, but the underlying coverage-map input and `why.missing_must_haves` narrative depend on an LLM composer's claim-to-must-have mapping judgment"
)

SIGNAL_TABLE_BY_SLUG: dict[str, dict[str, str]] = {
    'initial-configuration': {
        "pass_signal": "`config/preferences.yaml` is written and validates against `schemas/preferences.schema.json` (root `additionalProperties: false`) **and** passes `scripts/preferences/gmj_validate_preferences.py`'s shape-plus-subset-of-`sources.yaml` check",
        "fail_signal": "`gmj_validate_preferences.py` rejects the file — shape violation, or a `scope.sites`/`scope.cities`/`scope.languages` array that is not a subset of `config/sources.yaml`'s corresponding array",
        "signal_source": '`schemas/preferences.schema.json` (`scope.sites`/`scope.cities`/`scope.languages`, `additionalProperties: false`) + `scripts/preferences/gmj_validate_preferences.py` (subset-of-sources.yaml runtime check)',
        "semantic_caveat": "The interviewer's *gap-detection* judgment — asking only about real gaps in the candidate profile, one at a time — is an LLM judgment call; the validator gate only checks the resulting YAML's shape/subset-of-scope, never whether the interview asked the right questions",
    },
    'pipeline-run-hitl': {
        "pass_signal": 'Per artifact type, `.pipeline/runs/<run_id>-{cv,cl,ip}/state.json`\'s `gate_results["gmj-truth-verifier"] == "pass"` AND `gate_results["gmj-fit-evaluator"] == "pass"` — the exact predicate `gmj_check_delivery.py`\'s `blocked_reason()` checks; on pass it prints `deliverable` and exits 0. Rendered output then exists at `output/cv/*.pdf` (+ `.html` sibling for CV)',
        "fail_signal": '`gmj_check_delivery.py` prints `blocked: gmj-truth-verifier=<verdict-or-missing>, gmj-fit-evaluator=<verdict-or-missing>` to stderr and exits 1; underlying gate failure is `gmj_check_truth.py` (Gate A) or `gmj_score_fit.py` (Gate B) each independently exiting 1 on FAIL',
        "signal_source": '`.pipeline/runs/<run_id>-{cv,cl,ip}/state.json`\'s `gate_results` field + `scripts/pipeline/gmj_check_delivery.py` exit 0/1 + `schemas/gate_result.schema.json`\'s `content.verdict` enum (`["pass","fail"]`) (Gate C `polish` sub-scores are advisory-only and never gate delivery)',
        "semantic_caveat": _GATE_AB_JUDGMENT_CAVEAT,
    },
    'pipeline-run-autonomous': {
        "pass_signal": 'Identical mechanical predicate to Flow 2 (`gate_results` dual-pass via `gmj_check_delivery.py`) — `execution_mode` only gates the human pause after a gate PASS, never the gate mechanism itself',
        "fail_signal": 'Same as Flow 2, plus `gmj_check_cap.py`\'s 3-way exit contract: exit 0 (`"continue"`), exit 2 (`{"status":"propose_raise",...}` — first time `current_count == cap` and not yet raised), exit 1 (`{"status":"exhausted","failure_class":"narrow"|"systemic",...}` — final, no further retry)',
        "signal_source": "Same `state.json`/`gmj_check_delivery.py` as Flow 2, plus `scripts/pipeline/gmj_check_cap.py`'s 3-way exit code (0/1/2) and its JSON `status` (`continue`/`propose_raise`/`exhausted`) and `failure_class` (`narrow`/`systemic`) fields",
        "semantic_caveat": _GATE_AB_JUDGMENT_CAVEAT + " — " + 'autonomous mode removes only the human pause, never the machine gate, so the same reframe-vs-fabrication judgment call is present, now with no human present to catch a borderline case before the auto-approved raise or delivery',
    },
    'multi-offer-batch': {
        "pass_signal": 'Per offer, per artifact type, the same `gate_results` dual-pass predicate as Flow 2, rolled up in `batch_manifest.json`\'s per-offer `runs.{cv,cover_letter,interview_prep}` entries with `status: "delivered"`. Batch-level rollup: `gmj_runs.py`\'s `_offer_status_counts()` projects `by_offer_status` as a 5-value vocabulary count over the same statuses',
        "fail_signal": 'Any offer/type entry with `status: "gate_exhausted"` or `status: "error"` in `batch_manifest.json`\'s `runs` object — one offer\'s gate exhaustion is isolated and never stalls or corrupts a sibling offer\'s run',
        "signal_source": '`schemas/batch_manifest.schema.json`\'s `offers[].runs.{cv,cover_letter,interview_prep}.status` enum (`["waiting","in_flight","delivered","gate_exhausted","error"]`) + `.pipeline/runs/<batch_id>/batch_manifest.json` + `gmj_dispatch_cap.py`\'s frozen `max_parallel_offers` bound (default 3, `config/pipeline.config.yaml`)',
        "semantic_caveat": _GATE_AB_JUDGMENT_CAVEAT + " — " + "batching adds no new semantic-truth risk beyond the per-offer pipeline's own Gate A/B judgment calls, isolated per `retry_counts[offer][type]`",
    },
    'firecrawl-search': {
        "pass_signal": '`scripts/offers/gmj_firecrawl_search.py` is invoked only when `config/preferences.yaml`\'s `search_provider` field equals the single allowed enum value `"firecrawl"` (`schemas/preferences.schema.json` `search_provider` property, `enum: ["firecrawl"]`); a successful run produces the same shortlist/offer-spec artifacts as any other scout transport',
        "fail_signal": 'Missing `FIRECRAWL_API_KEY` env var — the script prints `FIRECRAWL_API_KEY not set; add it to .env (see .env.example)` to stderr and returns exit code 1, checked before any `firecrawl.Firecrawl(...)` client construction (confirmed by direct read of `scripts/offers/gmj_firecrawl_search.py`, lines 61-67)',
        "signal_source": "`schemas/preferences.schema.json`'s `search_provider` enum + `FIRECRAWL_API_KEY` env var presence + `scripts/offers/gmj_firecrawl_search.py` exit code 1 on the missing-key path + the same shortlist/offer-spec artifacts Flow 2 uses downstream",
        "semantic_caveat": "None — fully mechanical",
    },
    'cv-template': {
        "pass_signal": "No single pass/fail signal exists. Nearest qualitative check: `gmj_visual_diff.py`'s `diff_ratio()` returns a float in `[0,1]` (0.0 = identical) and the loop stops at <= 0.10, bounded by a cap of 5 iterations with keep-best-on-cap-reached. A separate mechanical gate runs alongside: `gmj_template_lint.py`'s `lint_template()` returns an empty list on pass — this lint IS a clean binary signal, even though the visual-match half is not",
        "fail_signal": '`gmj_template_lint.py` returns a non-empty list (leaked sample token or email/URL/proper-noun backstop match) — the template MUST be regenerated. Visual-diff side: the cap (5 iterations) is reached without ever hitting <= 0.10, but the agent still reports `status: success` with the best-kept version per its own output contract — a strict "fail" state for the visual-match half does not exist in the current contract',
        "signal_source": '`scripts/cv/gmj_visual_diff.py` (`diff_ratio` float, pinned constants `RASTER_DPI=150`, `DIFF_SIZE=(1000,1414)`, `RESAMPLE=Image.LANCZOS`) + `scripts/cv/gmj_template_lint.py` (`lint_template()` return list, empty = pass) + `.claude/commands/gmj-template.md`\'s stated cap (5, line 42: "Iteration cap `5` — never run more than 5 iterations.") + `.claude/agents/gmj-template-creator.md`\'s stated threshold (<= 0.10)',
        "semantic_caveat": 'The compare==ship visual-diff judgment of "is this close enough to the design" is bounded by a hard numeric threshold (<= 0.10), so the threshold check itself is mechanical — but the decision to accept a best-kept version at cap-exhaustion (rather than hard-failing) is a designed compare==ship judgment call the agent\'s own output contract makes explicit',
    },
    'scheduled-runs': {
        "pass_signal": 'The wrapper\'s own exit code mirrors the underlying `claude -p "/gmj-batch mode=autonomous"` invocation\'s exit code verbatim — no retry loop, ever. No overlap detected: lock acquired via `fcntl.flock(LOCK_EX | LOCK_NB)` at `.pipeline/cron.lock` (or `--lock-path` override) succeeds. Downstream pass signal is Flow 4\'s batch-manifest `delivered` rollup',
        "fail_signal": "Overlap detected — wrapper prints `gmj_cron_run: another run holds <lock_path>; exiting` to stderr and exits 1 (fail-closed, no queue, no retry). Missing `claude` on PATH — wrapper prints `gmj_cron_run: 'claude' not found on PATH; check cron/launchd PATH env` and exits non-zero. Missing `--lock-path` value or unknown argument also exits 1 with a named stderr message",
        "signal_source": "`scripts/ops/gmj_cron_run.sh` exit code (verbatim pass-through of `claude -p`'s own exit code) + `.pipeline/cron.lock` (fcntl-lock presence/absence) + operator-visible stderr text, surfaced to cron's mail-on-error or `launchd`'s `StandardErrorPath` log",
        "semantic_caveat": _GATE_AB_JUDGMENT_CAVEAT + " — " + 'this flow always drives the autonomous path, with the added operational fact that no human is present at all to observe a borderline case in real time',
    },
    'resume-flow': {
        "pass_signal": 'No single pass/fail signal exists at the inspection step itself. Nearest qualitative check: `/gmj-runs`\'s `project_status()` function returns one of exactly 4 string values via a locked top-down, first-match-wins order: `"delivered"` (gate_results dual-pass, reusing `blocked_reason()`), `"failed"` (any nested `retry_counts[...][...]` value >= the frozen `retry_cap` int), `"pending"` (empty `gate_results` AND empty `retry_counts` AND `current_step` is `None`/`"gmj-artifact-composer"`), else `"running"`. The inspector only prints the resume command — it never itself resumes; the resume flow\'s own pass signal is that same 4-value status advancing toward `"delivered"` on the next invocation of the resumed command',
        "fail_signal": 'Status stays `"failed"` after resuming (retry cap already exhausted with no further raise available) — or a resumed run\'s state file is malformed/missing, which `gmj_runs.py` degrades to `"unknown"` rather than raising',
        "signal_source": "`scripts/pipeline/gmj_runs.py`'s `project_status()` 4-value vocabulary (`delivered`/`failed`/`pending`/`running`, plus inspector-only `unknown` on read-degrade) + `.pipeline/runs/<run_id>/state.json`'s `current_step`, `gate_results`, `retry_counts`, `retry_cap` fields",
        "semantic_caveat": "None — fully mechanical",
    },
    'operator-monitoring': {
        "pass_signal": 'No single pass/fail signal exists for "monitoring" itself — it is a read-only projection, never an action with a terminal state. The nearest qualitative check is that the dashboard\'s displayed rollup values agree byte-for-byte with the same facts `/gmj-runs` would print: the dashboard is correct if and only if its `DashboardModel.snapshot()` projection matches `gmj_runs.py`\'s own read of the identical `.pipeline/runs/**/state.json` and `batch_manifest.json` files, re-read fresh from disk on each open with no stale caching and no new write path',
        "fail_signal": "No terminal fail state exists for the monitoring flow itself. The nearest observable failure would be the board falling out of sync with disk state, but per design this cannot happen since every value is re-derived fresh, nothing new; state honestly: no discrete pass/fail signal exists for this flow, the qualitative check is agreement with `/gmj-runs`'s own values on the same underlying file",
        "signal_source": "`scripts/dashboard/gmj_dashboard_model.py`'s `DashboardModel.snapshot()` + `scripts/pipeline/gmj_runs.py`'s equivalent read of the same `.pipeline/runs/**/state.json` and `.pipeline/runs/**/batch_manifest.json` files (both read-only default; `--manage` opts into a separate mutating action layer out of this flow's default scope)",
        "semantic_caveat": "None — fully mechanical",
    },
    'cleanup-wizard': {
        "pass_signal": 'The single `questionary.confirm(default=False)` prompt returns `True` — the ONLY gate to a delete action; the safety guarantee is the presence of that mandatory interactive confirm gate. Declining (Enter alone, or any non-confirm) short-circuits before the confirm prompt is ever shown, resulting in zero deletions',
        "fail_signal": 'There is no failure mode distinct from "user declined" — this is a destructive-if-confirmed flow whose only two terminal states are "confirmed -> deletions executed" and "declined/no input -> zero deletions." No `--yes`/`--force`/`-y`/`--no-confirm` bypass flag exists anywhere in the argparse surface, verified by a dedicated regression test',
        "signal_source": "`scripts/gmj_cleanup_wizard.py`'s `questionary.confirm(default=False)` return value + `tests/test_gmj_cleanup_wizard.py::test_no_bypass_flag_in_argparse` (the machine-verified absence-of-bypass regression guard) + `--repo-root` flag (testability-only, documented as not a bypass path)",
        "semantic_caveat": "None — fully mechanical",
    },
}
