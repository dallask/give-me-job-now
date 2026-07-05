#!/usr/bin/env python3
"""Headless dashboard read model — the single-sourced, torn-read-tolerant projection layer.

``gmj_dashboard_model.py`` is a pure, stdlib-only read model with ZERO new dependencies. It adds
NOTHING to the safety-critical control plane: every run/batch status the dashboard ever shows is
IMPORTED from ``scripts/pipeline/gmj_runs.py`` (``project_status`` / ``_run_row`` / ``_batch_rollup``)
and passed through untouched — the model never re-derives a status, a gate verdict, or a retry-cap
comparison. An AST-scoped grep-guard test (``tests/test_gmj_dashboard_model.py``) fails the build if
any re-derived projection-status literal (delivered/failed/pending/running), either gate-node
literal (gmj-truth-verifier/gmj-fit-evaluator), or a ``>= retry_cap`` compare appears as a code
string here. The ``unknown`` degrade sentinel the model emits for a genuinely-malformed row is
PERMITTED — ``project_status`` never returns it and there is no importable sentinel to reuse.

The one genuinely-new problem this file solves is **torn-read tolerance (MODEL-03)**: the Layer-1
writers persist ``state.json`` with a non-atomic ``Path.write_text`` (truncate-then-write), so a
poll can land mid-write. ``_load_state_tolerant`` classifies a read/parse error or an empty file as
TRANSIENT (retry a couple times, then serve the cached last-good row), a valid-JSON-but-non-dict
value as GENUINELY malformed (degrade immediately — a non-object won't fix itself), and a missing
file as skip. The last-good cache is held on the ``DashboardModel`` instance (keyed by run_id) so it
survives across ``snapshot()`` polls — a stateless re-entrant function cannot serve last-good.

Read-only invariant (mirrors gmj_runs.py ERGO-04): this module opens files for reading only,
creates no directories, writes nothing, never resolves/stats a run's ``offer_spec_path``, and never
raises out of ``snapshot()`` (the never-a-traceback contract).

This is the Plan 20-01 CORE: the import seam, the tolerant loader + last-good cache, and the
runs/batches/counters/stages skeleton. The metrics panel (MODEL-04), the offer-spec/candidate/config
thin readers (MODEL-05), the DAG stage order, and the ``run_detail`` drill-in accessor land in
Plan 20-02 — their keys are present here as empty/placeholder values so the snapshot shape is stable.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml  # PyYAML — a pre-existing repo dep (scripts/cv/requirements.txt); safe_load only

# Single-source seam — mirror gmj_runs.py:46 EXACTLY: put scripts/pipeline on sys.path, then import
# the status projection. The leading underscore on the private helpers is a naming convention only;
# Python does not access-control module-level names, so the import works (test_gmj_runs.py imports
# gmj_check_delivery cross-module the same way). project_status and _TS_RE are part of the documented
# seam consumed by the Plan 20-02 metrics panel; _order_key/_run_row/_batch_rollup are used here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from gmj_runs import (  # noqa: E402
    _batch_rollup,
    _gate_logs,
    _order_key,
    _run_row,
    _safe_component,
    _safe_id,
    _TS_RE,
    project_status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/dashboard/ -> repo root

# Torn-read retry budget (Claude's discretion per 20-RESEARCH.md A3): a couple of quick retries
# absorbs the sub-millisecond truncate-then-write window without materially slowing a poll.
_RETRIES = 2
_BACKOFF_S = 0.01

# Opaque classification sentinels for the tolerant loader — deliberately NOT strings so they can
# never collide with (or be mistaken for) a projection status literal in the grep-guard.
_TRANSIENT = object()  # torn/empty read, retry budget spent -> serve last-good else degrade
_MALFORMED = object()  # valid JSON but not a dict -> degrade immediately (no retry)
_MISSING = object()    # file vanished mid-poll -> skip the dir


def _load_state_tolerant(state_path: Path):
    """Return a good state ``dict``, or a classification sentinel — never raise.

    Classification (a pure function of the file's current bytes, per 20-RESEARCH.md § Torn-Read):
      - read ``OSError`` (missing mid-poll)                 -> ``_MISSING`` (skip the dir)
      - empty/zero-byte file OR ``json.loads`` ``ValueError`` -> TRANSIENT: retry, then ``_TRANSIENT``
      - parses but is not a ``dict``                        -> ``_MALFORMED`` (degrade now, no retry)
      - parses to a ``dict``                                -> the state dict (caller updates last-good)
    """
    for _ in range(_RETRIES + 1):
        try:
            raw = state_path.read_text(encoding="utf-8")
        except OSError:
            return _MISSING
        if raw.strip() == "":  # zero-byte truncate window — writer mid-flight
            time.sleep(_BACKOFF_S)
            continue
        try:
            state = json.loads(raw)
        except ValueError:  # JSONDecodeError subclasses ValueError — a half-written file
            time.sleep(_BACKOFF_S)
            continue
        if not isinstance(state, dict):  # genuinely malformed — a valid non-object won't fix itself
            return _MALFORMED
        return state
    return _TRANSIENT  # retries spent — caller serves last-good, else the degrade row


def _sum_retries(retry_counts) -> int:
    """Sum every innermost int retry counter, excluding bool (bool is an int subclass).

    Reuses the audited nested-guard walk from ``project_status`` (gmj_runs.py:117-124) verbatim —
    iterate ``retry_counts.values()`` where the per-type value is a dict, then its ``.values()``
    where the counter is an int-and-not-bool. Never raises on a wrong shape (``or {}`` fallback).
    """
    return sum(
        c
        for per_type in (retry_counts or {}).values()
        if isinstance(per_type, dict)
        for c in per_type.values()
        if isinstance(c, int) and not isinstance(c, bool)
    )


def _degrade_row(run_id: str) -> dict:
    """Reproduce the gmj_runs.py degrade-row SHAPE (gmj_runs.py:170-178).

    This is DATA the model emits for a genuinely-malformed row, not re-derived status logic — the
    ``unknown`` sentinel is exactly what gmj_runs.py writes and is intentionally permitted by the
    grep-guard (``project_status`` never returns it, so there is no importable value to reuse).
    ``current_step`` is added (as ``None``) so a degraded row is shape-compatible with a good row.
    """
    return {
        "run_id": run_id,
        "status": "unknown",
        "mode": "—",
        "gate_a": "—",
        "gate_b": "—",
        "ts": _order_key(run_id)[0] or "—",
        "current_step": None,
    }


def _degrade_batch_row(batch_id: str) -> dict:
    """Reproduce the gmj_runs.py batch degrade-row SHAPE (gmj_runs.py:238).

    Built by asking the IMPORTED ``_batch_rollup`` for an empty-manifest rollup (which yields the
    canonical ``{batch_id, delivered, total, status}`` shape with zero counts), then flipping only
    ``status`` to the ``unknown`` degrade sentinel. This keeps the schema keys single-sourced from
    gmj_runs.py — the model never writes the ``delivered``/``total`` key literals itself.
    """
    row = _batch_rollup({}, batch_id)  # {batch_id, delivered: 0, total: 0, status: "ok"}
    row["status"] = "unknown"
    return row


class DashboardModel:
    """Stateful read-model holder. Owns the last-good cache so it survives across ``snapshot()``.

    A pure re-entrant ``snapshot()`` with no persistent state cannot serve last-good on a torn read
    (20-RESEARCH.md A2 / Pitfall 3), so the cache lives here on the instance, keyed by run_id.
    """

    def __init__(self, pipeline_dir: str = ".pipeline", *, repo_root: str | Path = REPO_ROOT) -> None:
        self.pipeline_dir = Path(pipeline_dir).expanduser()
        self.repo_root = Path(repo_root)
        self._last_good: dict[str, dict] = {}

    def _runs(self) -> tuple[list[dict], list[dict]]:
        """Walk ``<pipeline_dir>/runs/*`` (mirrors gmj_runs.py _cmd_runs_list), torn-read tolerant.

        Returns ``(rows, metric_inputs)``. ``rows`` are the panel rows (VERBATIM ``_run_row`` output
        plus ``current_step``). ``metric_inputs`` carries the raw ``retry_counts``/``retry_cap`` from
        each WELL-FORMED run (a torn/degrade row contributes none — its retry data is unreadable) so
        the metrics builder needs no second disk pass and the panel rows stay contract-shaped.
        """
        rows: list[dict] = []
        metric_inputs: list[dict] = []
        runs_dir = self.pipeline_dir / "runs"
        if runs_dir.is_dir():
            for run_dir in sorted(runs_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                run_id = run_dir.name
                # Defence in depth (T-20-01): a crafted run-dir name never becomes a trusted row.
                # Silent read-only variant (gmj_runs._safe_component) — no stderr noise on a poll.
                if not _safe_component(run_id):
                    continue
                sp = run_dir / "state.json"
                if not sp.is_file():
                    continue  # stray / gate-logs-only dir: skip (missing state.json), never KeyError
                result = _load_state_tolerant(sp)
                if isinstance(result, dict):
                    row = _run_row(run_id, result)  # status via IMPORTED project_status — never derived
                    row["current_step"] = result.get("current_step")  # _run_row omits it (stages panel)
                    self._last_good[run_id] = row
                    rows.append(row)
                    metric_inputs.append(
                        {"retry_counts": result.get("retry_counts"), "retry_cap": result.get("retry_cap")}
                    )
                elif result is _MISSING:
                    continue
                elif result is _TRANSIENT:
                    # Torn read: serve the cached last-good row; degrade ONLY if none was ever seen.
                    rows.append(self._last_good.get(run_id) or _degrade_row(run_id))
                else:  # _MALFORMED — non-dict state degrades immediately
                    rows.append(_degrade_row(run_id))
        rows.sort(key=lambda r: _order_key(r["run_id"]), reverse=True)  # newest-first
        return rows, metric_inputs

    def _batches(self) -> list[dict]:
        """Walk ``<pipeline_dir>/batches/*/manifest.json`` and roll up via imported _batch_rollup."""
        rows: list[dict] = []
        batches_dir = self.pipeline_dir / "batches"
        if batches_dir.is_dir():
            for batch_dir in sorted(batches_dir.iterdir()):
                if not batch_dir.is_dir():
                    continue
                batch_id = batch_dir.name
                if not _safe_component(batch_id):
                    continue
                mp = batch_dir / "manifest.json"
                if not mp.is_file():
                    continue
                result = _load_state_tolerant(mp)
                if isinstance(result, dict):
                    rows.append(_batch_rollup(result, batch_id))
                elif result is _MISSING:
                    continue
                else:  # torn or non-dict manifest -> degrade batch row
                    rows.append(_degrade_batch_row(batch_id))
        rows.sort(key=lambda r: r["batch_id"], reverse=True)
        return rows

    # ── thin readers (MODEL-05) — all read-only, all degrade to {}/[] on a missing/bad file ──

    def _load_yaml(self, rel: str) -> dict:
        """Read ``<repo_root>/<rel>`` via ``yaml.safe_load`` (never ``yaml.load``); {} on any failure.

        Tolerant by contract (T-20-04): a missing file (OSError), a parse error (yaml.YAMLError), or a
        non-dict top level all degrade to ``{}`` — the reader never raises out of ``snapshot()``.
        """
        p = self.repo_root / rel
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    def _vacancies(self, *, top_must: int | None = None) -> list[dict]:
        """List every frozen ``sources/offers/*.offer-spec.json`` (A1) — verbatim display fields.

        Globs the offers dir directly; NEVER follows/resolves/stats ``state.offer_spec_path``
        (Pitfall 4 / T-20-02). Sibling ``*.draft.json`` / ``*-shortlist.json`` files are excluded by
        the ``*.offer-spec.json`` glob. A malformed spec is skipped, never fatal.
        """
        out: list[dict] = []
        offers_dir = self.repo_root / "sources" / "offers"
        if not offers_dir.is_dir():
            return out
        for p in sorted(offers_dir.glob("*.offer-spec.json")):
            try:
                spec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(spec, dict):
                continue
            content = spec.get("content")
            if not isinstance(content, dict):
                content = {}
            must = content.get("must_haves")
            out.append(
                {
                    "title": content.get("title"),
                    "company": content.get("company"),
                    "location": content.get("location"),
                    "seniority": content.get("seniority"),
                    "salary_range": content.get("salary_range"),  # verbatim (may be null)
                    "n_must_haves": len(must) if isinstance(must, list) else 0,
                    "offer_spec_hash": spec.get("offer_spec_hash"),  # top level
                }
            )
        return out

    def _candidate(self, *, top_n: int = 8) -> dict:
        """Expose ONLY name/title/summary/contact/expertise_top from ``config/candidate.yaml``.

        Read-only (truthfulness invariant, T-20-05): the file is opened for reading only and never
        written. A missing/bad file degrades to ``{}``. ``expertise_top`` truncates the expertise
        list to the first ``top_n`` (the panel shows a summary, not the whole profile).
        """
        data = self._load_yaml("config/candidate.yaml")
        if not data:
            return {}
        expertise = data.get("expertise")
        contact = data.get("contact")
        return {
            "name": data.get("name"),
            "title": data.get("title"),
            "summary": data.get("summary"),
            "contact": contact if isinstance(contact, dict) else {},
            "expertise_top": expertise[:top_n] if isinstance(expertise, list) else [],
        }

    def _config(self) -> dict:
        """Read the four config knobs verbatim (sources / pipeline / fit_thresholds / preferences)."""
        sources = self._load_yaml("config/sources.yaml")
        pipeline = self._load_yaml("config/pipeline.config.yaml")
        fit = self._load_yaml("config/fit_thresholds.yaml")
        prefs = self._load_yaml("config/preferences.yaml")
        return {
            "boards": sources.get("sites") or [],       # sites -> boards
            "cities": sources.get("cities") or [],
            "languages": sources.get("languages") or [],
            "limits": sources.get("limits") or {},
            "execution_mode": pipeline.get("execution_mode"),
            "retry_cap": pipeline.get("retry_cap"),
            "fit_thresholds": fit,
            "preferences": prefs,
        }

    def _dag(self) -> list[str]:
        """Ordered pipeline step names READ from ``config/pipeline.dag.yaml`` ``steps`` (never hardcoded).

        The node names live in the config file, so no gate-node string literal appears in this module
        (the AST grep-guard stays green). Dict insertion order is preserved by ``yaml.safe_load``.
        """
        dag = self._load_yaml("config/pipeline.dag.yaml")
        steps = dag.get("steps")
        return list(steps.keys()) if isinstance(steps, dict) else []

    # ── on-demand drill-in accessor (Pitfall 5 — NOT built per-poll) ──────────────────────────

    def run_detail(self, run_id: str) -> dict:
        """Return the ``run_inspect``-shaped payload for one validated run_id, else ``{}``.

        Mirrors gmj_runs.py ``_cmd_run_inspect`` (:268-316): validates via the imported ``_safe_id``,
        applies the containment check (:275-280), tolerant-loads the state, builds the base row via the
        imported ``_run_row`` (status via the projection — never re-derived), and augments the
        ``_gate_logs`` artifacts/attempts + a PRINTED (never executed) resume command. ``offer_spec_path``
        is displayed verbatim — never resolved/stat'd (T-20-02). Returns ``{}`` for an unsafe/missing run.
        """
        if _safe_id(run_id, "run_id") is None:
            return {}
        runs_dir = self.pipeline_dir / "runs"
        run_dir = runs_dir / run_id
        # Defence in depth: the resolved run dir must stay contained under the resolved runs dir.
        resolved = run_dir.resolve()
        base = runs_dir.resolve()
        if resolved != base and base not in resolved.parents:
            return {}
        sp = run_dir / "state.json"
        if not sp.is_file():
            return {}
        state = _load_state_tolerant(sp)
        if not isinstance(state, dict):
            return {}
        row = _run_row(run_id, state)  # run_id/status/mode/gate_a/gate_b/ts — projection, never derived
        artifacts, attempts = _gate_logs(run_dir)
        return {
            "kind": "run_inspect",
            "run_id": state.get("run_id") or run_id,
            "status": row["status"],
            "mode": row["mode"],
            "gate_a": row["gate_a"],
            "gate_b": row["gate_b"],
            # offer_spec_path is displayed VERBATIM — never resolved/stat'd (it may be relative).
            "offer_spec_path": state.get("offer_spec_path"),
            "offer_spec_hash": state.get("offer_spec_hash"),
            "retry_cap": state.get("retry_cap"),
            "retry_counts": state.get("retry_counts") or {},
            "current_step": state.get("current_step"),
            "artifacts": artifacts,
            "attempts": attempts,
            # Resume is a PRINTED string, never executed (mirrors gmj_runs.py:298).
            "resume_command": f"/gmj-pipeline-run  (resume: pass run_id={run_id})",
        }

    def _metrics(self, runs: list[dict], metric_inputs: list[dict]) -> dict:
        """Aggregate domain metrics (MODEL-04) from the ALREADY-projected rows + raw retry inputs.

        Every tally is a data-derived ``Counter`` over row/field VALUES — no projection-status or
        gate-node-name literal is written here (the AST grep-guard stays green). ``retries_used`` /
        ``cap_space`` are SUM-vs-SUM figures (never a per-run ``>= retry_cap`` compare, which is
        ``project_status``'s job). ``throughput`` reuses the imported ``_order_key`` timestamp — no
        new timestamp source — and drops no-timestamp runs.
        """
        # by_status: Counter over the projected row statuses (keys are DATA-DERIVED, incl. a
        # degrade "unknown" bucket that comes from the row, never a hardcoded status literal).
        by_status = dict(Counter(r["status"] for r in runs))

        # Gate A / Gate B pass-vs-fail: tally the rows' gate fields, treating the "—" absent-fallback
        # as NEITHER pass nor fail (an absent gate is never counted as a fail). Keys ("pass"/"fail")
        # are data-derived from the recorded verdicts, so no gate-node literal appears in this file.
        gate_a = dict(Counter(r["gate_a"] for r in runs if r["gate_a"] != "—"))
        gate_b = dict(Counter(r["gate_b"] for r in runs if r["gate_b"] != "—"))

        # retries_used: sum of every innermost int retry counter across the well-formed runs.
        retries_used = sum(_sum_retries(mi.get("retry_counts")) for mi in metric_inputs)
        # cap_space: SUM of the per-run frozen retry_cap (int, excluding bool) minus retries_used —
        # a headroom figure, NOT a per-run threshold compare.
        cap_total = sum(
            mi["retry_cap"]
            for mi in metric_inputs
            if isinstance(mi.get("retry_cap"), int) and not isinstance(mi.get("retry_cap"), bool)
        )
        cap_space = cap_total - retries_used

        # throughput: bucket each timestamped run_id by day (YYYYMMDD prefix of the _order_key
        # timestamp); no-timestamp runs yield "" and are excluded. Emit a list of ints, day-ordered.
        day_counts: Counter = Counter()
        for r in runs:
            ts = _order_key(r["run_id"])[0]
            if ts:
                day_counts[ts[:8]] += 1
        throughput = [day_counts[day] for day in sorted(day_counts)]

        return {
            "by_status": by_status,
            "gate_a": gate_a,
            "gate_b": gate_b,
            "retries_used": retries_used,
            "cap_space": cap_space,
            "throughput": throughput,
        }

    def snapshot(self) -> dict:
        """Gather every panel's data in one read-only pass; return ONE JSON-serializable plain dict.

        Returns the full nine-key panel dict: ``counters`` / ``metrics`` / ``stages`` (``dag`` +
        ``active``) / ``runs`` / ``batches`` / ``vacancies`` / ``candidate`` / ``config`` /
        ``run_detail``. Every run/batch status is the IMPORTED projection, passed through untouched;
        every reader is read-only and degrades to ``{}``/``[]`` on a missing file (never raises).
        ``run_detail`` stays ``{}`` here — it is an on-demand accessor (``run_detail(run_id)``) so the
        per-poll cost stays proportional to the displayed runs (Pitfall 5).
        """
        runs, metric_inputs = self._runs()
        batches = self._batches()
        metrics = self._metrics(runs, metric_inputs)

        vacancies = self._vacancies()
        candidate = self._candidate()
        config = self._config()

        # Status buckets via Counter over the PROJECTED statuses on the rows — no hardcoded
        # status-name key ever appears in this file (single-source seam preserved).
        by_status = dict(Counter(r["status"] for r in runs))
        counters = {
            "runs": len(runs),
            "by_status": by_status,
            "offers": len(vacancies),                 # count of frozen offer-specs
            "mode": config.get("execution_mode") or "—",  # config/pipeline.config.yaml
            "retry_cap": config.get("retry_cap"),     # config/pipeline.config.yaml
        }

        stages = {
            "dag": self._dag(),  # config/pipeline.dag.yaml step order (read from disk, never hardcoded)
            "active": [
                {
                    "run_id": r["run_id"],
                    "current_step": r.get("current_step"),
                    "gate_a": r["gate_a"],
                    "gate_b": r["gate_b"],
                }
                for r in runs
            ],
        }

        return {
            "counters": counters,
            "metrics": metrics,
            "stages": stages,
            "runs": runs,
            "batches": batches,
            "vacancies": vacancies,
            "candidate": candidate,
            "config": config,
            "run_detail": {},   # on-demand: populate via run_detail(run_id), never per-poll
        }


def main() -> int:
    """Emit one snapshot — a manual read-only inspector for the model (mirrors gmj_runs.py argparse)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Headless dashboard read model — emit one snapshot() of the pipeline read state."
    )
    parser.add_argument(
        "--pipeline-dir", default=".pipeline", help="Read-only pipeline root to project (default .pipeline)."
    )
    parser.add_argument(
        "--repo-root", default=str(REPO_ROOT), help="Repo root for the thin readers (config/candidate/offers)."
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_out", help="Emit the full snapshot() as canonical JSON."
    )
    args = parser.parse_args()
    snap = DashboardModel(pipeline_dir=args.pipeline_dir, repo_root=args.repo_root).snapshot()
    if args.json_out:
        sys.stdout.write(json.dumps(snap, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    else:
        c = snap["counters"]
        print(f"runs={c['runs']} offers={c['offers']} mode={c['mode']} retry_cap={c['retry_cap']}")
        print(f"by_status     {json.dumps(c['by_status'], sort_keys=True, ensure_ascii=False)}")
        print(f"vacancies={len(snap['vacancies'])} batches={len(snap['batches'])} dag={len(snap['stages']['dag'])} steps")
        print("(pass --json for the full canonical snapshot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
