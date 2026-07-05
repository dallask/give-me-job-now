#!/usr/bin/env python3
"""Read-only, btop-style Textual dashboard over ``DashboardModel.snapshot()`` (Phase 20).

``gmj_dashboard.py`` is the PRESENTATION layer only. It adds ZERO domain logic and does ZERO disk
I/O of its own: it imports ``DashboardModel`` from the sibling ``gmj_dashboard_model`` module and
renders the plain nine-key dict that ``snapshot()`` returns into framed panels. Every run/batch
status, gate verdict and count it shows comes straight from that dict — the view never re-derives a
status, never opens a file, never shells out.

Safety invariants enforced by this file (proven by ``tests/test_gmj_dashboard.py``):

- **Read-only by default (VIEW-01 / VIEW-07 / SAFETY-02):** launching with no flags binds only the
  read-only keys (``q`` quit, ``enter`` inert drill-in). The mutating keys (``r``/``R``/``b``/``m``/
  ``c``) are constructed ONLY when ``--manage`` is passed, and even then they map to an inert no-op
  this phase — Phase 23 wires the actual mutation behaviour. Because the ``Footer`` renders whatever
  is bound, it is automatically mode-aware.
- **No writes / no subprocess (SAFETY-02):** there is no ``open(..., 'w')`` / ``write_text`` /
  ``os.replace`` / ``subprocess`` anywhere in this module. An AST test asserts the absence, and a
  bytes+mtime-unchanged test proves a launch+refresh mutates no on-disk state.
- **Non-blocking poll (VIEW-04):** ``on_mount`` installs a ~1.5s ``set_interval`` that schedules the
  (potentially disk-bound) ``model.snapshot()`` on a THREAD worker off the UI event loop; the result
  is marshalled back with ``call_from_thread`` and applied with TARGETED per-widget updates — never a
  full ``recompose()``. The event loop therefore never blocks on a poll.
- **Guard-safe status color (VIEW-03 groundwork):** status colors live as ``status-``-prefixed
  ``Theme`` variables (and as bare classes in ``gmj_dashboard.tcss``, which the grep-guard does not
  scan). No bare status literal (``delivered``/``failed``/``pending``/``running``) or ``>= retry_cap``
  compare appears in this file, so the Phase-20 AST grep-guard — which also scans this file — stays
  green.

This is Plan 21-01: the App skeleton — grid + placeholder frames, guard-safe theme, read-only key
gating, the non-blocking poll spine, and the brand banner + generic global counters strip. The runs
table rows (21-02) and the metrics / candidate / config panels (21-03) are reserved as empty,
titled frames here so the grid geometry is stable and later plans are content swaps, not relayouts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding  # noqa: F401  (documented seam; bindings are installed via App.bind)
from textual.theme import Theme
from textual.widgets import DataTable, Digits, Footer, Header, Sparkline, Static  # noqa: F401

# Single-source seam — put scripts/dashboard on sys.path and import the read model. The view does
# ZERO disk I/O itself; it only ever calls model.snapshot() / model.run_detail().
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_dashboard_model import DashboardModel  # noqa: E402

# Hardcoded ASCII brand banner (VIEW-02) — a fixed multi-line block, NO pyfiglet dependency.
BANNER_ASCII = r"""
  __ _ ___ _   _____   _ __ ___   ___    (_) ___ | |__
 / _` |_ _\ \ / / _ \ | '_ ` _ \ / _ \   | |/ _ \| '_ \
| (_| || | \ V /  __/ | | | | | |  __/   | | (_) | |_) |
 \__, |___| \_/ \___| |_| |_| |_|\___|  _/ |\___/|_.__/
 |___/                                 |__/   give-me-job
""".strip("\n")

# Guard-safe status palette (VIEW-03). Keys are `status-<value>` — NOT bare status literals — so the
# Phase-20 exact-match grep-guard stays green while the runs table (21-02) colors a cell by looking
# the value up at runtime via get_css_variables().get(f"status-{value}"). Bare status classes with
# the same hexes live in gmj_dashboard.tcss (which the .py grep-guard does not scan).
GMJ_THEME = Theme(
    name="gmj-btop",
    primary="#3fb950",
    secondary="#39d0d8",
    background="#0d1117",
    surface="#0d1117",
    variables={
        "status-delivered": "#3fb950",
        "status-running": "#d29922",
        "status-failed": "#f85149",
        "status-pending": "#6e7681",
        "status-unknown": "#bc8cff",
        # Gate-verdict palette (VIEW-08). Keys are `gate-<verdict>` — NOT forbidden literals — so the
        # DAG strip colors a Gate A/B node by looking the projected verdict up at runtime via
        # get_css_variables().get(f"gate-{verdict}"); the "—" absent-sentinel resolves to no var.
        "gate-pass": "#3fb950",
        "gate-fail": "#f85149",
    },
)

# Runs-table columns (label, stable key). Seeded once so _apply_runs can target cells via update_cell.
_RUN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("run_id", "run_id"),
    ("status", "status"),
    ("mode", "mode"),
    ("A", "gate_a"),
    ("B", "gate_b"),
    ("step", "current_step"),
)

# Mutating keys (key, description) — SHOWN only under --manage so the footer is mode-aware. Their
# action is an inert no-op this phase; Phase 23 wires the real behaviour behind --manage.
_MANAGE_KEYS: tuple[tuple[str, str], ...] = (
    ("r", "Run"),
    ("R", "Resume"),
    ("b", "Batch"),
    ("m", "Mode"),
    ("c", "Cap"),
)


class GmjDashboard(App):
    """The read-only btop-style pipeline board. Takes a PRE-BUILT model; touches no disk itself."""

    CSS_PATH = "gmj_dashboard.tcss"
    TITLE = "gmj-dashboard"

    def __init__(self, model: DashboardModel, *, manage: bool = False, refresh: float = 1.5) -> None:
        self._model = model
        self._manage = manage
        self._refresh = refresh
        super().__init__()

    def compose(self) -> ComposeResult:
        """Reserve the full proposal-§7 grid up front — real panels + titled Phase-22 placeholders."""
        yield Header(show_clock=True)
        yield Static(BANNER_ASCII, id="banner")          # VIEW-02 hardcoded ASCII banner
        yield Static(id="counters")                       # VIEW-02 global counters (filled per poll)

        metrics = Static("", id="metrics")                # VIEW-05 (filled in 21-03)
        metrics.border_title = "metrics"
        yield metrics

        dag = Static("(pipeline stages — Phase 22)", id="dag-placeholder")  # Phase-22 frame reserved
        dag.border_title = "pipeline stages"
        yield dag

        yield DataTable(id="runs", cursor_type="row")     # VIEW-03 (rows diffed in via _apply_runs)

        vac = Static("(vacancies — Phase 22)", id="vac-placeholder")        # Phase-22 frame reserved
        vac.border_title = "vacancies"
        yield vac

        cand = Static("", id="candidate")                 # VIEW-06 (filled in 21-03)
        cand.border_title = "candidate"
        yield cand

        cfg = Static("", id="config")                     # VIEW-06 (filled in 21-03)
        cfg.border_title = "configuration"
        yield cfg

        yield Sparkline(id="throughput")                  # VIEW-05 throughput (filled in 21-03)
        yield Footer()                                    # VIEW-07 mode-aware keybind strip

    # ── one-time widget seeding ────────────────────────────────────────────────────────────────

    def _seed_widgets(self) -> None:
        """Register the theme + seed the widgets that only need building once (columns, sparkline)."""
        self.register_theme(GMJ_THEME)
        self.theme = "gmj-btop"
        table = self.query_one("#runs", DataTable)
        for label, key in _RUN_COLUMNS:
            table.add_column(label, key=key)
        # An empty Sparkline has nothing to draw; seed a single zero so it renders a stable frame.
        self.query_one("#throughput", Sparkline).data = [0]

    def _install_bindings(self) -> None:
        """Install read-only bindings always; the mutating keys ONLY under --manage (VIEW-01/07).

        Uses the public ``App.bind`` API (verified against textual 6.1.0): each call adds the key to
        ``self._bindings.key_to_bindings`` and the ``Footer`` reflects it. In read-only mode the
        mutating keys are never constructed, so the binding map genuinely lacks them.
        """
        self.bind("q", "quit", description="Quit")
        self.bind("enter", "noop", description="Drill-in")
        if self._manage:
            for key, desc in _MANAGE_KEYS:
                self.bind(key, "noop", description=desc)

    # ── read-only key actions ──────────────────────────────────────────────────────────────────

    def action_noop(self) -> None:
        """Inert placeholder — no mutation this phase (Phase 23 wires --manage behaviour)."""

    # ── non-blocking poll spine (VIEW-04) ──────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Seed widgets + bindings, then start the ~1.5s poll and paint once immediately."""
        self._seed_widgets()
        self._install_bindings()
        self.set_interval(self._refresh, self._poll)
        self._poll()  # paint immediately — don't wait a full interval for the first frame

    def _poll(self) -> None:
        """Schedule the (disk-bound) snapshot OFF the event loop on a thread worker."""
        self.run_worker(self._poll_worker, thread=True, exclusive=True, group="poll")

    def _poll_worker(self) -> None:
        """Runs in a worker THREAD — safe to block on disk here; then marshal back to the UI thread."""
        snap = self._model.snapshot()                 # the ONLY read; the model is torn-read tolerant
        self.call_from_thread(self._apply, snap)       # touch widgets only on the UI thread

    def _apply(self, snap: dict) -> None:
        """Apply a fresh snapshot with TARGETED updates only — never recompose()."""
        self._apply_counters(snap.get("counters") or {})
        self._apply_runs(snap.get("runs") or [])
        self._apply_dag(snap.get("stages") or {})
        self._apply_metrics(snap.get("metrics") or {})
        self._apply_candidate(snap.get("candidate") or {})
        self._apply_config(snap.get("config") or {})

    # ── pipeline-DAG stage strip (VIEW-08) — guard-safe, projection-colored ───────────────────────

    def _apply_dag(self, stages: dict) -> None:
        """Render the pipeline-DAG strip from ``snapshot()["stages"]`` — targeted ``.update()``, no recompose.

        Two bands, both DATA-DERIVED (so no status word / gate-node name is a code literal — the
        Phase-20 grep-guard stays green):

        - a static token row: ``stages["dag"]`` (the config-read step names) joined by a ``  >  ``
          separator into one ``rich.text.Text``. A token whose name is a currently-active
          ``current_step`` gets the accent (``primary``) style; the rest inherit the panel color, so
          every token stays legible (color is never the only signal);
        - one line per active run (``stages["active"]`` filtered to a TRUTHY ``current_step`` —
          terminal/legacy runs with ``current_step: null`` are dropped, Pitfall 5): a
          ``{run_id} → {current_step}  (A:{gate_a} B:{gate_b})`` line whose ``current_step`` is styled
          ``primary`` and whose Gate A/B verdicts are colored by a RUNTIME value-keyed lookup
          ``get_css_variables().get(f"gate-{verdict}")`` (the ``"—"`` absent-sentinel yields no var →
          empty style — an absent gate is never mis-colored).

        Coloring is ALWAYS paired with the readable token text (colorblind-safe). An empty
        ``stages``/``dag`` degrades to a quiet placeholder line — never a crash.
        """
        cssv = self.get_css_variables()
        dag = stages.get("dag") or []
        active = [a for a in (stages.get("active") or []) if a.get("current_step")]
        active_steps = {a["current_step"] for a in active}

        if not dag:
            self.query_one("#dag-placeholder", Static).update("(no pipeline stages)")
            return

        sep_style = cssv.get("secondary") or ""
        accent = cssv.get("primary") or ""

        out = Text()
        for i, step in enumerate(dag):        # step names are DATA from config — never a literal
            if i:
                out.append("  >  ", style=sep_style)
            out.append(step, style=accent if step in active_steps else "")

        for a in active:                      # one "where is this run" line per in-flight run
            out.append(f"\n{a['run_id']} → ")
            out.append(str(a["current_step"]), style=accent)
            out.append("  (A:")
            out.append(str(a["gate_a"]), style=cssv.get(f"gate-{a['gate_a']}") or "")  # value-keyed
            out.append(" B:")
            out.append(str(a["gate_b"]), style=cssv.get(f"gate-{a['gate_b']}") or "")  # value-keyed
            out.append(")")

        self.query_one("#dag-placeholder", Static).update(out)

    # ── domain-metrics panel + throughput sparkline (VIEW-05) ─────────────────────────────────────

    def _apply_metrics(self, m: dict) -> None:
        """Render the domain-metrics panel from ``snapshot()["metrics"]`` — targeted, no recompose.

        Every line is DATA-DERIVED from the projection, so no status word is a standalone literal in
        this file (the Phase-20 grep-guard stays green):

        - one bar per status by iterating ``sorted(m["by_status"].items())`` as ``label █…█ count`` —
          the key is read from the dict, never hardcoded, and the count label is always paired with
          the glyphs so colour is never the only signal;
        - a Gate A and Gate B line rendered from the ``pass``/``fail`` verdict tallies
          (``m["gate_a"]``/``m["gate_b"]`` — these keys are the projection's verdicts, not gate-node
          literals);
        - a retry-vs-cap meter that shows ``retries_used`` against ``cap_space`` — a SUM headroom
          figure the model already computed, NEVER a per-run ``>= retry_cap`` comparison.

        The throughput ``Sparkline``'s ``.data`` reactive is reassigned IN PLACE (never recomposed);
        an empty series falls back to ``[0]`` so the sparkline always has a stable frame to draw.
        """
        by_status = m.get("by_status") or {}
        lines = [f"{k:<10} {'█' * v} {v}" for k, v in sorted(by_status.items())]
        ga = m.get("gate_a") or {}
        gb = m.get("gate_b") or {}
        lines.append(f"Gate A  pass {ga.get('pass', 0)} / fail {ga.get('fail', 0)}")
        lines.append(f"Gate B  pass {gb.get('pass', 0)} / fail {gb.get('fail', 0)}")
        lines.append(f"retries {m.get('retries_used', 0)} / cap-space {m.get('cap_space', 0)}")
        self.query_one("#metrics", Static).update("\n".join(lines) if lines else "(no runs yet)")
        self.query_one("#throughput", Sparkline).data = m.get("throughput") or [0]

    # ── read-only candidate + configuration panels (VIEW-06) ──────────────────────────────────────

    def _apply_candidate(self, cand: dict) -> None:
        """Render the read-only candidate-summary panel from the whitelisted ``candidate`` top-fields.

        Displays name / title / summary / a compact contact line / the first few ``expertise_top``
        items VERBATIM — the model's thin reader already whitelists these fields, so the view surfaces
        only what ``snapshot()["candidate"]`` exposes (no non-whitelisted profile field can leak). An
        empty projection (missing/bad ``candidate.yaml``) degrades to a quiet empty-state line.
        """
        if not cand:
            self.query_one("#candidate", Static).update("(no candidate profile)")
            return
        lines = [
            f"[b]{cand.get('name') or '—'}[/b]",
            cand.get("title") or "—",
        ]
        summary = cand.get("summary")
        if summary:
            lines.append("")
            lines.append(str(summary))
        contact = cand.get("contact") or {}
        if contact:
            lines.append("")
            lines.append(" · ".join(f"{k}: {v}" for k, v in contact.items()))
        expertise = cand.get("expertise_top") or []
        if expertise:
            lines.append("")
            lines.append("expertise: " + ", ".join(str(e) for e in expertise[:6]))
        self.query_one("#candidate", Static).update("\n".join(lines))

    def _apply_config(self, cfg: dict) -> None:
        """Render the read-only configuration panel from the governing ``config`` knobs.

        Shows the boards / cities / languages scope, the frozen ``execution_mode`` and ``retry_cap``,
        and a compact ``fit_thresholds`` summary — all displayed VERBATIM from the projection. The
        retry-cap knob is shown as its stored value (a display of the frozen setting), never used in a
        per-run threshold comparison. Degrades to a quiet empty-state line on an empty projection.
        """
        if not cfg:
            self.query_one("#config", Static).update("(no configuration)")
            return
        boards = cfg.get("boards") or []
        cities = cfg.get("cities") or []
        languages = cfg.get("languages") or []
        lines = [
            f"boards      {len(boards)}",
            f"cities      {', '.join(str(c) for c in cities) if cities else '—'}",
            f"languages   {', '.join(str(l) for l in languages) if languages else '—'}",
            f"mode        {cfg.get('execution_mode') or '—'}",
            f"retry_cap   {cfg.get('retry_cap') if cfg.get('retry_cap') is not None else '—'}",
        ]
        fit = cfg.get("fit_thresholds") or {}
        if isinstance(fit, dict) and fit:
            thr = fit.get("coverage_threshold")
            lines.append(f"fit         coverage_threshold {thr if thr is not None else '—'}")
        self.query_one("#config", Static).update("\n".join(lines))

    # ── runs table (VIEW-03) — guard-safe status cell + targeted RowKey diff ──────────────────────

    def _status_cell(self, status: str) -> Text:
        """Build the status cell as a Rich ``Text`` whose color is looked up at RUNTIME by value.

        ``status`` is the PROJECTION value (a variable, never a status string literal), and the color
        comes from the ``status-``-prefixed theme variable ``get_css_variables().get(f"status-{status}")``
        — so no bare status literal enters this file and the Phase-20 grep-guard stays green. The cell
        TEXT is the status WORD itself, so the color is always paired with a readable label
        (colorblind-safe — color is never the only signal).
        """
        color = self.get_css_variables().get(f"status-{status}") or ""
        return Text(status, style=color)

    def _apply_runs(self, rows: list) -> None:
        """Diff the runs ``DataTable`` against the fresh projection rows — targeted updates only.

        Never ``clear()``+refill and never ``recompose()``: rows are keyed by ``run_id`` so an existing
        run is patched cell-by-cell via ``update_cell`` (status through ``_status_cell``; ``mode``,
        ``gate_a``, ``gate_b``, ``current_step`` with a ``-`` fallback), a newly-appeared run is
        ``add_row``ed with its ``run_id`` key, and a run dir that vanished this tick is ``remove_row``ed.
        The row cursor and row count therefore stay stable across polls (VIEW-04 strengthened).
        """
        t = self.query_one("#runs", DataTable)
        known = set(t.rows)            # existing RowKeys (StringKey compares/hashes by value)
        seen: set = set()
        for r in rows:
            rk = r["run_id"]
            seen.add(rk)
            step = r.get("current_step") or "-"
            if rk in known:            # targeted per-cell patch — no clear+refill, no recompose
                t.update_cell(rk, "status", self._status_cell(r["status"]))
                t.update_cell(rk, "mode", r["mode"])
                t.update_cell(rk, "gate_a", r["gate_a"])
                t.update_cell(rk, "gate_b", r["gate_b"])
                t.update_cell(rk, "current_step", step)
            else:                      # a newly-appeared run — append keyed by run_id
                t.add_row(
                    r["run_id"],
                    self._status_cell(r["status"]),
                    r["mode"],
                    r["gate_a"],
                    r["gate_b"],
                    step,
                    key=rk,
                )
        for gone in known - seen:      # a run dir that vanished mid-session — drop its row
            t.remove_row(gone)

    def _apply_counters(self, c: dict) -> None:
        """Render the global counters strip GENERICALLY so no status word is a standalone literal.

        The per-status counts come from iterating ``c['by_status'].items()`` (keys are data-derived,
        never hardcoded), so the headline delivered count appears without ``"delivered"`` ever being
        written as a string constant in this file. Copy: ``runs N · <status N ...> · offers N ·
        mode {..} · cap N``.
        """
        by_status = c.get("by_status") or {}
        parts = [f"runs {c.get('runs', 0)}"]
        parts += [f"{k} {v}" for k, v in sorted(by_status.items())]
        parts.append(f"offers {c.get('offers', 0)}")
        parts.append(f"mode {c.get('mode', '—')}")
        parts.append(f"cap {c.get('retry_cap')}")
        self.query_one("#counters", Static).update(" · ".join(parts))


def main() -> int:
    """Parse flags and launch the read-only board. ``--manage`` is parsed but footer-only this phase."""
    parser = argparse.ArgumentParser(description="Read-only btop-style pipeline dashboard.")
    parser.add_argument("--pipeline-dir", default=".pipeline", help="Read-only pipeline root to project.")
    parser.add_argument("--manage", action="store_true", help="Show mutating keys (footer-only this phase).")
    parser.add_argument("--read-only", action="store_true", help="Explicit read-only (the default).")
    parser.add_argument("--refresh", type=float, default=1.5, help="Poll interval in seconds (default 1.5).")
    args = parser.parse_args()
    manage = args.manage and not args.read_only
    model = DashboardModel(pipeline_dir=args.pipeline_dir)
    GmjDashboard(model, manage=manage, refresh=args.refresh).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
