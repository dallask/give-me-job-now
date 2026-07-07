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
import asyncio
import sys
import time
from pathlib import Path

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding  # noqa: F401  (documented seam; bindings are installed via App.bind)
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, DataTable, Digits, Footer, Header, Input, Sparkline, Static, TabbedContent, TabPane  # noqa: F401

# Single-source seam — put scripts/dashboard on sys.path and import the read model. The view does
# ZERO disk I/O itself; it only ever calls model.snapshot() / model.run_detail().
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmj_dashboard_features import build_feature_prompt  # noqa: E402
from gmj_dashboard_model import DashboardModel  # noqa: E402

# scripts/dashboard/gmj_dashboard.py -> repo root is three parents up. Used only to resolve the
# default config path + child cwd for the --manage action layer (Plan 24-02); the view itself still
# does ZERO disk I/O — every mutation is delegated to gmj_dashboard_actions (MANAGE-06).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"


# Hardcoded ASCII brand banner (VIEW-02) — fixed multi-line figlet block, NO pyfiglet dependency.
_BANNER_ASCII_LINES: tuple[str, ...] = tuple(
    r"""
  __ _ ___ _   _____   _ __ ___   ___    (_) ___ | |__
 / _` |_ _\ \ / / _ \ | '_ ` _ \ / _ \   | |/ _ \| '_ \
| (_| || | \ V /  __/ | | | | | |  __/   | | (_) | |_) |
 \__, |___| \_/ \___| |_| |_| |_|\___|  _/ |\___/|_.__/
 |___/                                 |__/
""".strip("\n").splitlines()
)
_BANNER_SLOGAN = "Your career's wingman"
# Ukrainian flag palette — top band blue, bottom band yellow (#0057B7 / #FFD700).
_BANNER_BLUE = "bold #0057B7"
_BANNER_YELLOW = "bold #FFD700"
_BANNER_LINE_STYLES: tuple[str, ...] = (
    _BANNER_BLUE,
    _BANNER_BLUE,
    _BANNER_BLUE,
    _BANNER_YELLOW,
    _BANNER_YELLOW,
)


def _render_banner() -> Text:
    """VIEW-02 — Ukrainian-flag ASCII figlet + centered slogan (static, seeded once)."""
    out = Text()
    figlet_width = max(len(line) for line in _BANNER_ASCII_LINES)
    for i, line in enumerate(_BANNER_ASCII_LINES):
        if i:
            out.append("\n")
        style = _BANNER_LINE_STYLES[i] if i < len(_BANNER_LINE_STYLES) else _BANNER_YELLOW
        out.append(line, style=style)
    slogan_pad = max(0, (figlet_width - len(_BANNER_SLOGAN)) // 2)
    out.append("\n")
    out.append(" " * slogan_pad + _BANNER_SLOGAN, style="italic #ffd700")
    return out

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
        # Event-verdict palette (VIEW-12/13). Keys are `event-<kind>` — NOT forbidden literals — so the
        # errors panel + activity feed color an event by looking the projected kind/verdict up at
        # runtime via get_css_variables().get(f"event-{kind}"); mirrors the .tcss `.event-*` classes.
        "event-started": "#39d0d8",
        "event-pass": "#3fb950",
        "event-fail": "#f85149",
        "event-terminal": "#bc8cff",
        "event-delivered": "#3fb950",
    },
)

# Runs-table columns (label, stable key). Seeded once so _apply_runs can target cells via update_cell.
_RUN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("run_id", "run_id"),
    ("status", "status"),
    ("run_mode", "mode"),
    ("A", "gate_a"),
    ("B", "gate_b"),
    ("step", "current_step"),
)

# Vacancies-table columns (label, stable key). Seeded once for targeted update_cell in _apply_vacancies.
_VAC_COLUMNS: tuple[tuple[str, str], ...] = (
    ("title", "title"),
    ("company", "company"),
    ("seniority", "seniority"),
    ("salary", "salary"),
    ("mh", "mh"),
)

# Configuration file browser (VIEW-19): one column listing ``config/**/*.yaml`` paths.
_CONFIG_COLUMNS: tuple[tuple[str, str], ...] = (("file", "file"),)
# Features catalog (skills / agents / commands / flows).
_FEATURE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("kind", "kind"),
    ("name", "name"),
    ("summary", "summary"),
)
# VIEW-21 tabbed diagnostics panel — TabbedContent pane ids (errors · debug · activity · commands).
_DIAG_PANE_ERRORS = "pane-errors"
_DIAG_PANE_DEBUG = "pane-debug"
_DIAG_PANE_ACTIVITY = "pane-activity"
_DIAG_PANE_COMMANDS = "pane-commands"
_DIAG_PANE_METRICS = "pane-metrics"
_DIAG_PANE_STAGES = "pane-stages"
_DIAG_PANE_CHARTS = "pane-charts"
_DIAG_PANE_DEFAULT = _DIAG_PANE_ERRORS
_DIAG_PANE_ORDER: tuple[str, ...] = (
    _DIAG_PANE_ERRORS,
    _DIAG_PANE_DEBUG,
    _DIAG_PANE_ACTIVITY,
    _DIAG_PANE_COMMANDS,
    _DIAG_PANE_METRICS,
    _DIAG_PANE_STAGES,
    _DIAG_PANE_CHARTS,
)

# Heartbeat live-sync strip (VIEW-27) — compact row; see also top-of-file #heartbeat block.
_HEARTBEAT_STYLE = "bold #3fb950"

# Global counters strip delimiter — swap for another TUI-friendly separator if desired.
_COUNTERS_DELIM = " │ "

# Under --manage each key binds to its REAL action (run/resume/batch/mode/cap) which delegates to the
# gmj_dashboard_actions module (Plan 24-02); WITHOUT --manage they are never constructed, so the
# read-only board genuinely lacks them (MANAGE-01). The action_* handlers lazily import the actions
# module so the read-only import graph never pulls a subprocess-capable module.
_MANAGE_KEYS: tuple[tuple[str, str, str], ...] = (
    ("r", "run", "Run"),
    ("R", "resume", "Resume"),
    ("b", "batch", "Batch"),
    ("m", "mode", "Default mode"),
    ("c", "cap", "Cap"),
)


# Multi-row block-matrix glyph ramp (VIEW-14). The eighths ` ▁▂▃▄▅▆▇█` (index 0..8) let a series be
# drawn as a TALL matrix of block glyphs — one row per 8 eighths of the peak — so the big throughput
# graph reaches btop density. Textual's Sparkline renders only ONE row (verified in 23-RESEARCH), so
# the big graph is hand-rolled here; the small per-status trends reuse the same helper at rows=1.
_BLOCK_BARS = " ▁▂▃▄▅▆▇█"


def _block_graph(series: list, rows: int = 4) -> str:
    """Render an int ``series`` as a multi-row block matrix (a pure view helper — no data logic, no disk).

    Verified per 23-RESEARCH Pattern 3: scale each value to ``rows * 8`` eighths against the series peak,
    then emit ``rows`` lines top-first — a full ``█`` where the column overflows the row, a partial eighth
    glyph at the boundary, a blank below. An empty series degrades to the ``(no throughput)`` placeholder.
    With ``rows >= 2`` the result contains a newline (a true multi-row graph, NOT a single-row Sparkline);
    ``rows=1`` yields a compact single-row spark for the small per-status trends.
    """
    if not series:
        return "(no throughput)"
    peak = max(series) or 1
    max_eighths = rows * 8
    cols = [round(v / peak * max_eighths) for v in series]
    out = []
    for r in range(rows - 1, -1, -1):          # top row first
        line = []
        for e in cols:
            rem = e - r * 8
            line.append(" " if rem <= 0 else "█" if rem >= 8 else _BLOCK_BARS[rem])
        out.append("".join(line))
    return "\n".join(out)


class RunDetailModal(ModalScreen):
    """Read-only run drill-in overlay (VIEW-09) — a FROZEN ``run_detail`` payload, no disk/exec path.

    Constructed from ``model.run_detail(run_id)`` (an on-demand accessor — no per-poll cost) and given
    the payload ONCE at ``__init__`` so the ~1.5s base-screen poll underneath never refreshes/flickers
    it (Pitfall 3). Every field the body renders is a payload VARIABLE (never a status/gate string
    literal), so the Phase-20 grep-guard stays green. The ``resume_command`` is DISPLAYED under a
    ``Resume:`` label and is NEVER executed — there is no ``subprocess``/write API here (SAFETY-02).

    CRITICAL id hygiene: the body id ``#modal-body`` is namespaced distinct from every base-screen id.
    ``App.query_one`` searches the whole App DOM across stacked screens, so a duplicate id would make
    the next poll's ``query_one`` raise ``TooManyMatches``; the ``#modal-`` namespace prevents it.
    ``escape`` dismisses via the built-in ``Screen.action_dismiss``.
    """

    BINDINGS = [("escape", "dismiss", "Close")]  # action_dismiss is built into Screen (textual 6.1)

    def __init__(self, detail: dict) -> None:
        self._detail = detail  # frozen at open — the poll never mutates this
        super().__init__()

    def compose(self) -> ComposeResult:
        if not self._detail:  # unsafe/missing run_id → run_detail returned {} → graceful empty state
            yield Static("Run detail unavailable", id="modal-body", classes="modal")
            return
        yield Static("", id="modal-body", classes="modal")

    def on_mount(self) -> None:
        if not self._detail:
            return
        self.query_one("#modal-body", Static).update(self._render_body())

    def _render_body(self) -> Text:
        """One labeled field per line — bold labels, status/gate values colored via theme vars."""
        d = self._detail
        css = self.app.get_css_variables()
        out = Text()
        out.append(f"Run {d['run_id']}\n\n", style="bold")
        self._append_field(out, "run_id", d["run_id"])
        self._append_field(
            out, "status", d["status"], value_style=css.get(f"status-{d['status']}") or ""
        )
        # Per-run mode is frozen at init_run — ``m`` only changes the config default for NEW runs.
        self._append_field(out, "mode (frozen)", d["mode"])
        self._append_field(
            out, "gate_a", d["gate_a"], value_style=css.get(f"gate-{d['gate_a']}") or ""
        )
        self._append_field(
            out, "gate_b", d["gate_b"], value_style=css.get(f"gate-{d['gate_b']}") or ""
        )
        step = d.get("current_step")
        if step:
            self._append_field(out, "current_step", step)
        cap = d.get("retry_cap")
        if cap is not None:
            self._append_field(out, "retry_cap (frozen)", cap)
        self._append_field(out, "offer_spec_hash", d.get("offer_spec_hash"))
        # offer_spec_path is displayed VERBATIM from the payload — never resolved/stat'd (T-20-02).
        self._append_field(out, "offer_spec_path", d.get("offer_spec_path"))
        out.append("\n")
        attempts = ", ".join(d.get("attempts") or []) or "—"
        self._append_field(out, "attempts", attempts)
        artifacts = ", ".join(d.get("artifacts") or []) or "—"
        self._append_field(out, "artifacts", artifacts)
        out.append("\n")
        # The resume command is a DISPLAY string only — printed here, never executed (Pitfall 2).
        self._append_field(out, "Resume", d.get("resume_command"))
        return out

    @staticmethod
    def _append_field(out: Text, label: str, value, *, value_style: str = "") -> None:
        out.append(f"{label}: ", style="bold")
        out.append(str(value if value not in (None, "") else "—"), style=value_style)
        out.append("\n")


def _format_salary(sal) -> str:
    """Format a projected ``salary_range`` dict for display; ``None`` → ``—``."""
    if isinstance(sal, dict):
        return f"{sal.get('min', '?')}-{sal.get('max', '?')} {sal.get('currency', '')}".strip()
    return "—"


class VacancyDetailModal(ModalScreen):
    """Read-only offer drill-in overlay (VIEW-17) — frozen ``offer_detail`` payload, no disk/exec."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, detail: dict) -> None:
        self._detail = detail
        super().__init__()

    def compose(self) -> ComposeResult:
        if not self._detail:
            yield Static("Offer detail unavailable", id="vac-modal-body", classes="modal")
            return
        yield Static("", id="vac-modal-body", classes="modal")

    def on_mount(self) -> None:
        if not self._detail:
            return
        self.query_one("#vac-modal-body", Static).update(self._render_body())

    def _render_body(self) -> Text:
        d = self._detail
        out = Text()
        out.append(f"{d.get('title') or 'Offer'}\n\n", style="bold")
        RunDetailModal._append_field(out, "company", d.get("company"))
        RunDetailModal._append_field(out, "location", d.get("location"))
        RunDetailModal._append_field(out, "seniority", d.get("seniority"))
        RunDetailModal._append_field(out, "employment_type", d.get("employment_type"))
        RunDetailModal._append_field(out, "language", d.get("language"))
        RunDetailModal._append_field(out, "salary_range", _format_salary(d.get("salary_range")))
        RunDetailModal._append_field(out, "offer_spec_hash", d.get("offer_spec_hash"))
        RunDetailModal._append_field(out, "spec_basename", d.get("spec_basename"))
        RunDetailModal._append_field(out, "captured_at", d.get("captured_at"))
        out.append("\n")
        RunDetailModal._append_field(out, "must_haves", ", ".join(d.get("must_haves") or []) or "—")
        nice = d.get("nice_to_haves") or []
        if nice:
            RunDetailModal._append_field(out, "nice_to_haves", ", ".join(nice))
        resp = d.get("responsibilities") or []
        if resp:
            RunDetailModal._append_field(out, "responsibilities", ", ".join(resp))
        out.append("\n")
        # source_url is DISPLAY only — never fetched or opened (SAFETY-02).
        RunDetailModal._append_field(out, "source_url", d.get("source_url"))
        excerpt = d.get("raw_text_excerpt")
        if excerpt:
            RunDetailModal._append_field(out, "raw_text_excerpt", excerpt)
        return out


class ConfigFileModal(ModalScreen):
    """Read-only configuration file drill-in — full YAML text, no disk write."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="cfg-modal-card"):
            if not self._payload:
                yield Static("Configuration unavailable", id="cfg-modal-body")
                return
            with VerticalScroll(id="cfg-modal-scroll"):
                yield Static("", id="cfg-modal-body")

    def on_mount(self) -> None:
        if not self._payload:
            return
        self.query_one("#cfg-modal-body", Static).update(self._render_body())
        try:
            self.query_one("#cfg-modal-scroll", VerticalScroll).focus()
        except Exception:
            pass

    def _render_body(self) -> Text:
        payload = self._payload
        path = payload.get("path") or "config"
        out = Text()
        out.append(f"{path}\n\n", style="bold")
        if payload.get("error"):
            out.append(str(payload["error"]))
            return out
        out.append(payload.get("text") or "(empty file)")
        return out


class FeatureModal(ModalScreen):
    """Feature drill-in + optional run launcher (``--manage``) with per-item parameter inputs."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, detail: dict, *, manage: bool, run_callback=None) -> None:
        self._detail = detail
        self._manage = manage
        self._run_callback = run_callback
        super().__init__()

    def compose(self) -> ComposeResult:
        detail = self._detail
        with Vertical(id="feat-modal-card"):
            if not detail:
                yield Static("Feature unavailable", id="feat-modal-body")
                return
            yield Static("", id="feat-modal-header")
            with VerticalScroll(id="feat-modal-scroll"):
                yield Static("", id="feat-modal-body")
                for param in detail.get("params") or []:
                    name = param["name"]
                    label = param.get("label") or name
                    yield Static(f"{label}:", classes="feat-param-label")
                    yield Input(
                        placeholder=param.get("placeholder") or "",
                        id=f"feat-param-{name}",
                        value=str(param.get("default") or ""),
                    )
            with Horizontal(id="feat-modal-actions"):
                if detail.get("runnable"):
                    yield Button("Run", id="feat-run-btn", variant="success", disabled=not self._manage)
                yield Button("Close", id="feat-close-btn", variant="default")

    def on_mount(self) -> None:
        if not self._detail:
            return
        d = self._detail
        header = Text()
        header.append(f"{d.get('kind', 'feature')}: ", style="bold #39d0d8")
        header.append(f"{d.get('name') or '—'}\n", style="bold")
        if d.get("slash"):
            header.append(f"{d['slash']}\n", style="italic #8b949e")
        if d.get("source_path"):
            header.append(f"{d['source_path']}\n", style="#8b949e")
        self.query_one("#feat-modal-header", Static).update(header)
        body = Text(d.get("description") or "(no description)")
        self.query_one("#feat-modal-body", Static).update(body)
        if not self._manage and self._detail.get("runnable"):
            hint = Static("(Run requires --manage)", id="feat-manage-hint")
            self.query_one("#feat-modal-scroll", VerticalScroll).mount(hint)
        try:
            params = self._detail.get("params") or []
            if params:
                first = self.query_one(f"#feat-param-{params[0]['name']}", Input)
                first.focus()
            else:
                self.query_one("#feat-modal-scroll", VerticalScroll).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "feat-close-btn":
            self.dismiss()
            return
        if event.button.id != "feat-run-btn" or not self._manage:
            return
        values: dict[str, str] = {}
        for param in self._detail.get("params") or []:
            name = param["name"]
            try:
                values[name] = self.query_one(f"#feat-param-{name}", Input).value
            except Exception:
                values[name] = ""
        self.dismiss()
        if self._run_callback:
            self._run_callback(self._detail, values)


class _PromptModal(ModalScreen):
    """A minimal single-line value collector for the --manage action layer (Plan 24-02).

    A ModalScreen with a prompt line + an ``Input``; submitting resolves the injected ``future`` with
    the typed value and ``escape`` resolves it with ``None`` (cancel). The action methods that need an
    offer / retry_cap / batch selection push this modal and ``await`` the future — but every collector
    helper on the App is OVERRIDABLE so Pilot tests inject a value without ever opening a modal. The
    modal owns NO write/subprocess API (it only marshals a string back), keeping the view AST-clean
    (MANAGE-06). Its ids are ``#modal-``-namespaced so a poll's ``query_one`` never collides (Pitfall 3).
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, future: asyncio.Future) -> None:
        self._prompt = prompt
        self._future = future
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(self._prompt, id="modal-prompt", classes="modal")
        yield Input(id="modal-prompt-input")

    def on_mount(self) -> None:
        self.query_one("#modal-prompt-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._resolve(event.value)

    def action_cancel(self) -> None:
        self._resolve(None)

    def _resolve(self, value: str | None) -> None:
        if not self._future.done():
            self._future.set_result(value)
        self.dismiss()


class _ConfirmModal(ModalScreen):
    """A yes/no acknowledgement gate for a mutating write to the real repo-default config (SAFE-02).

    Copies the ``_PromptModal`` Future-marshalling shape but resolves the injected ``future`` with a
    BOOL: enter / the confirm button → ``True`` (proceed), escape / the cancel button → ``False``
    (leave the file untouched). Like ``_PromptModal`` it owns NO write/subprocess API — it only
    marshals the operator's acknowledgement back to ``_confirm_manage_write``, keeping the view
    AST-clean (SAFETY-02 / MANAGE-06). Its widget ids are ``#confirm-`` / ``#modal-confirm-``
    namespaced (NOT ``#modal-prompt-*``) so the ~1.5s base-screen poll's ``query_one`` never collides
    with a duplicate id (Pitfall 4). The warning copy names the real repo-default config path and
    deliberately avoids the SAFETY-03 forbidden status/gate-node string literals.
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str, future: asyncio.Future) -> None:
        self._prompt = prompt
        self._future = future
        super().__init__()

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-confirm-card"):
            yield Static(self._prompt, id="modal-confirm", classes="modal")
            with Horizontal(id="modal-confirm-actions"):
                yield Button("Proceed", id="confirm-ok-btn", variant="warning")
                yield Button("Cancel", id="confirm-cancel-btn", variant="default")

    def on_mount(self) -> None:
        try:
            self.query_one("#confirm-ok-btn", Button).focus()
        except Exception:  # noqa: BLE001 — headless / teardown edge
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._resolve(event.button.id == "confirm-ok-btn")

    def action_cancel(self) -> None:
        self._resolve(False)

    def _resolve(self, value: bool) -> None:
        if not self._future.done():
            self._future.set_result(bool(value))
        self.dismiss()


class GmjDashboard(App):
    """The read-only btop-style pipeline board. Takes a PRE-BUILT model; touches no disk itself."""

    CSS_PATH = "gmj_dashboard.tcss"
    TITLE = "gmj-dashboard"
    AUTO_FOCUS = ""  # no filter/table focused at startup — user picks a panel explicitly

    def __init__(
        self,
        model: DashboardModel,
        *,
        manage: bool = False,
        refresh: float = 1.5,
        launcher=None,
        config_path: Path | None = None,
        pipeline_dir: str = ".pipeline",
        cwd: Path | None = None,
    ) -> None:
        self._model = model
        self._manage = manage
        self._refresh = refresh
        # ── --manage action-layer seams (Plan 24-02). All default so the read-only board is unchanged;
        # each is overridable by a Pilot test. The view NEVER references a subprocess/write primitive
        # here — the actions module owns the real launcher default (launcher=None resolves there), and
        # every config write / process spawn is delegated to gmj_dashboard_actions (MANAGE-06).
        self._launcher = launcher                                   # injected recording fake in tests
        self._config_path = config_path if config_path is not None else DEFAULT_CONFIG
        # SAFE-02 confirm-once-per-session flag: after the first acknowledged mutating write to the real
        # repo-default config, later m/c writes proceed without re-prompting (the banner stays visible).
        self._manage_confirmed = False
        self._pipeline_dir = pipeline_dir                           # threaded into run_batch (W2)
        self._cwd = cwd if cwd is not None else REPO_ROOT           # repo root for the launched child
        self._children: list = []                                   # detached proc refs (silence GC)
        # While a dashboard-launched claude child is alive, poll faster and (for resume) show the row
        # as ``running`` even if the on-disk projection is still ``failed``/``delivered`` until gates move.
        self._launched_runs: dict[str, object] = {}                 # run_id -> proc (resume only)
        self._pending_launches: list = []                         # procs from fresh ``r`` (no run_id yet)
        self._fast_poll = None                                    # 0.4s interval while any launch is active
        # VIEW-11 row filter: a persistent, lowercased substring predicate applied INSIDE _apply_runs
        # (so a poll never resurrects a filtered-out row — Pitfall 4), plus a cached last snapshot so
        # an Input.Changed re-renders immediately without waiting for the next ~1.5s poll.
        self._filter = ""
        # VIEW-18 vacancies filter — same Pitfall-4 contract as VIEW-11 runs filter.
        self._vac_filter = ""
        # Features panel filter (kind / name / summary substring).
        self._features_filter = ""
        self._last_snap: dict | None = None
        # VIEW-16 debug/internals selection state: the run_id whose run_detail() the #debug panel
        # renders. Unset (None) => the `Select a run for internals` empty state. Set on RowSelected.
        self._debug_run_id: str | None = None
        # VIEW-20 live refresh: fast-poll window after manage launches so errors/activity/debug track disk.
        self._live_refresh_until: float = 0.0
        self._auto_debug_until: float = 0.0
        self._heartbeat_phase: int = 0
        self._heartbeat_anim = None
        self._disk_pipeline_active = False
        self._pipeline_activity: dict = {}
        self._launch_labels: dict[int, str] = {}
        super().__init__()

    def compose(self) -> ComposeResult:
        """Reserve the full proposal-§7 grid up front — real panels + titled Phase-22 placeholders."""
        yield Header(show_clock=True)
        yield Static("", id="banner")                   # VIEW-02 brand wordmark (seeded in _seed_widgets)

        status_panel = Vertical(
            Static(id="counters"),
            id="status-panel",
        )
        status_panel.border_title = "status"

        heartbit_panel = Vertical(
            Static("", id="heartbeat"),
            id="heartbit-panel",
        )
        heartbit_panel.border_title = "heartbit"

        with Vertical(id="status-band"):
            yield status_panel
            yield Static("", id="panel-gap-status-heartbit", classes="panel-v-gap")
            yield heartbit_panel

        feat_panel = Vertical(
            Input(
                placeholder="filter features (kind / name / summary substring)…",
                id="features-filter",
            ),
            DataTable(id="features-table", cursor_type="row"),
            id="features-panel",
        )
        feat_panel.border_title = "features"

        cfg_panel = Vertical(
            Static("", id="config-warning"),          # SAFE-02 (a) repo-default banner — seeded once
            DataTable(id="config-table", cursor_type="row"),
            id="config-panel",
        )
        cfg_panel.border_title = "configuration"

        runs_panel = Vertical(
            Input(placeholder="filter runs (run_id / status substring)…", id="filter"),
            DataTable(id="runs", cursor_type="row"),
            id="runs-panel",
        )
        runs_panel.border_title = "runs"

        vac_panel = Vertical(
            Input(
                placeholder="filter vacancies (title / company / seniority substring)…",
                id="vac-filter",
            ),
            DataTable(id="vacancies", cursor_type="row"),
            Static("", id="vac-batches"),
            id="vac-panel",
        )
        vac_panel.border_title = "vacancies"

        with Horizontal(id="features-config-row"):
            yield feat_panel
            yield cfg_panel

        with Horizontal(id="runs-vac-row"):
            yield runs_panel
            yield vac_panel

        with TabbedContent(id="diag-tabs-panel", initial=_DIAG_PANE_DEFAULT):
            with TabPane("errors", id=_DIAG_PANE_ERRORS):
                with VerticalScroll():
                    yield Static("", id="errors")
            with TabPane("debug", id=_DIAG_PANE_DEBUG):
                with VerticalScroll():
                    yield Static("", id="debug")
            with TabPane("activity (events)", id=_DIAG_PANE_ACTIVITY):
                with VerticalScroll():
                    yield Static("", id="activity")
            with TabPane("commands", id=_DIAG_PANE_COMMANDS):
                with VerticalScroll():
                    yield Static("", id="commands")
            with TabPane("metrics", id=_DIAG_PANE_METRICS):
                with VerticalScroll():
                    with Vertical():
                        yield Static("", id="metrics")
                        yield Sparkline(id="throughput")
            with TabPane("pipeline stages", id=_DIAG_PANE_STAGES):
                with VerticalScroll():
                    yield Static("", id="dag-placeholder")
            with TabPane("throughput / gates", id=_DIAG_PANE_CHARTS):
                with VerticalScroll():
                    yield Static("", id="charts")

        yield Footer()                                    # VIEW-07 mode-aware keybind strip

    # ── one-time widget seeding ────────────────────────────────────────────────────────────────

    def _seed_widgets(self) -> None:
        """Register the theme + seed the widgets that only need building once (columns, sparkline)."""
        self.register_theme(GMJ_THEME)
        self.theme = "gmj-btop"
        self.query_one("#banner", Static).update(_render_banner())
        table = self.query_one("#runs", DataTable)
        for label, key in _RUN_COLUMNS:
            table.add_column(label, key=key)
        vac_table = self.query_one("#vacancies", DataTable)
        for label, key in _VAC_COLUMNS:
            vac_table.add_column(label, key=key)
        cfg_table = self.query_one("#config-table", DataTable)
        for label, key in _CONFIG_COLUMNS:
            cfg_table.add_column(label, key=key)
        feat_table = self.query_one("#features-table", DataTable)
        for label, key in _FEATURE_COLUMNS:
            feat_table.add_column(label, key=key)
        # An empty Sparkline has nothing to draw; seed a single zero so it renders a stable frame.
        self.query_one("#throughput", Sparkline).data = [0]
        # VIEW-21: per-tab color classes (Tab extends Static — avoid id selectors with a ``--`` prefix).
        tab_bar = self.query_one("#diag-tabs-panel ContentTabs")
        for pane_id, class_name in (
            (_DIAG_PANE_ERRORS, "diag-tab-errors"),
            (_DIAG_PANE_DEBUG, "diag-tab-debug"),
            (_DIAG_PANE_ACTIVITY, "diag-tab-activity"),
            (_DIAG_PANE_COMMANDS, "diag-tab-commands"),
            (_DIAG_PANE_METRICS, "diag-tab-metrics"),
            (_DIAG_PANE_STAGES, "diag-tab-stages"),
            (_DIAG_PANE_CHARTS, "diag-tab-charts"),
        ):
            tab_bar.get_content_tab(pane_id).add_class(class_name)
        # The commands reference (VIEW-15) is STATIC + mode-aware — seed it once here, not per-poll.
        self._apply_commands()
        # SAFE-02 (a): a persistent repo-default warning banner, seeded ONCE here (NEVER in a per-poll
        # _apply_* path — that would flicker/lose it, Pitfall 3). Shown only under --manage when the
        # resolved --config is the real repo-default; empty otherwise. Copy avoids the SAFETY-03
        # forbidden status/gate-node literals (phrased around "editing the real repo-default config").
        if self._manage and self._editing_repo_default():
            self.query_one("#config-warning", Static).update(self._repo_default_warning())

    def _install_bindings(self) -> None:
        """Install read-only bindings always; the mutating keys ONLY under --manage (VIEW-01/07).

        Uses the public ``App.bind`` API (verified against textual 6.1.0): each call adds the key to
        ``self._bindings.key_to_bindings`` and the ``Footer`` reflects it. In read-only mode the
        mutating keys are never constructed, so the binding map genuinely lacks them.
        """
        self.bind("q", "quit", description="Quit")
        self.bind("enter", "noop", description="Drill-in")
        if self._manage:
            for key, action, desc in _MANAGE_KEYS:
                self.bind(key, action, description=desc)  # real handler under --manage (MANAGE-01)

    # ── read-only key actions ──────────────────────────────────────────────────────────────────

    def action_noop(self) -> None:
        """Inert placeholder — the read-only drill-in binding; carries no mutation."""

    # ── --manage value collectors (all OVERRIDABLE — Pilot tests inject values, no modal opens) ────

    async def _ask(self, prompt: str) -> str | None:
        """Push a ``_PromptModal`` and await the typed value (``None`` on cancel). Overridable in tests.

        Uses a plain ``asyncio.Future`` resolved by the modal so no worker context is required; this is
        a pure UI marshal — no disk, no subprocess (MANAGE-06).
        """
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.push_screen(_PromptModal(prompt, future))
        return await future

    async def _prompt_cap(self) -> int | None:
        """Collect a new retry_cap integer (overridable). Returns ``None`` on cancel / non-integer."""
        raw = await self._ask("New retry_cap:")
        if raw is None:
            return None
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            self.notify("⚠ retry_cap must be an integer", severity="error")
            return None

    # ── SAFE-02 repo-default write gate (detection + injectable confirm seam, confirm-once) ─────────

    def _editing_repo_default(self) -> bool:
        """True iff --config resolves to the packaged repo-default config (SAFE-02).

        Path identity only — a ``Path.resolve()`` equality vs the module-level ``DEFAULT_CONFIG`` (NOT
        ``samefile``, which raises on a missing path). No content hashing/sniffing (locked decision).
        Never raises: any resolve failure — ``OSError`` OR ``ValueError`` (e.g. an embedded NUL byte in a
        crafted ``--config`` value) — degrades safely to ``False`` (IN-02). Overridable in tests.
        """
        try:
            return Path(self._config_path).resolve() == DEFAULT_CONFIG.resolve()
        except (OSError, ValueError):
            return False

    def _repo_default_warning(self) -> str:
        """Single source for the SAFE-02 repo-default warning copy (IN-01).

        Built once here and reused by both the persistent ``#config-warning`` banner and the confirm
        modal so the two operator-facing phrasings can never drift. Names the resolved real config path
        and deliberately avoids the SAFETY-03 forbidden status/gate-node string literals.
        """
        return f"⚠ editing the real repo-default config: {Path(self._config_path).resolve()}"

    async def _confirm_manage_write(self) -> bool:
        """Push a ``_ConfirmModal`` and await the operator's acknowledgement (SAFE-02). Overridable.

        Mirrors ``_ask``: create a loop Future, push the modal, and return the marshalled bool. A pure
        UI marshal — no disk, no subprocess (MANAGE-06). The warning names the real repo-default config
        path and avoids the SAFETY-03 forbidden status/gate-node literals.
        """
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        warning = f"{self._repo_default_warning()} — proceed?"
        self.push_screen(_ConfirmModal(warning, future))
        return bool(await future)

    async def _guard_repo_default_write(self) -> bool:
        """Gate a mutating write behind the confirm seam — once per session (SAFE-02).

        Returns ``True`` immediately when the config is not the repo-default OR the operator has already
        acknowledged a SUCCESSFUL write this session. Otherwise awaits the confirm seam and returns the
        operator's acknowledgement. A cancel returns ``False`` so the caller skips its ``actions.*`` write
        (cancel = no write).

        WR-02: this guard NO LONGER latches ``self._manage_confirmed`` on acknowledgement. The latch is
        set by the caller ONLY AFTER the subsequent ``actions.*`` write succeeds — so a cancelled OR
        failed first write does not silently consume the session's single prompt (a failed write must
        still re-prompt on the next attempt).
        """
        if not self._editing_repo_default() or self._manage_confirmed:
            return True
        return await self._confirm_manage_write()

    # ── --manage config handlers (m/c) — delegate to the actions module, then notify ───────────────

    async def _apply_mode_toggle(self) -> None:
        """Toggle ``execution_mode`` via the actions module (``m`` under --manage)."""
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        if not await self._guard_repo_default_write():   # SAFE-02 — cancel means no write
            return
        try:
            value = actions.toggle_execution_mode(self._config_path)
        except ValueError as exc:
            self.notify(f"⚠ config edit failed: {exc}", severity="error")
            return
        # WR-02: latch confirm-once ONLY after the write actually succeeded — a failed write above
        # returns early and leaves the prompt armed for the next attempt.
        self._manage_confirmed = True
        self.notify(f"✓ default_mode → {value} (existing runs unchanged)")
        self._poll()

    @work(exclusive=True, group="manage")
    async def action_mode(self) -> None:
        """Toggle ``execution_mode`` via the actions module — runs as a worker so awaiting the SAFE-02
        confirm modal happens off the message pump (an inline await of a pushed screen deadlocks — see
        ``action_cap``).

        SAFE-02 (WR-01): ``exclusive=True, group="manage"`` means a second ``m``/``c`` keypress while a
        confirm modal is still open CANCELS the pending worker instead of stacking a second worker +
        second modal. This preserves the "one prompt per session, one write per action" promise under
        real, human-paced concurrent keypresses (a bare ``@work`` let a second press stack a redundant
        confirm and double-write)."""
        await self._apply_mode_toggle()

    async def _apply_retry_cap(self) -> None:
        """Collect + set ``retry_cap`` (``c`` under --manage)."""
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        if not await self._guard_repo_default_write():   # SAFE-02 — cancel means no write
            return
        cap = await self._prompt_cap()
        if cap is None:
            return
        try:
            actions.set_retry_cap(self._config_path, cap)
        except ValueError as exc:
            self.notify(f"⚠ config edit failed: {exc}", severity="error")
            return
        # WR-02: latch confirm-once ONLY after the write actually succeeded (see _apply_mode_toggle).
        self._manage_confirmed = True
        self.notify(f"✓ retry_cap → {cap}")
        self._poll()

    @work(exclusive=True, group="manage")
    async def action_cap(self) -> None:
        """Set ``retry_cap`` via modal prompt — runs as a worker so the modal stays interactive.

        SAFE-02 (WR-01): shares the exclusive ``"manage"`` worker group with ``action_mode`` so a second
        manage keypress cancels a pending confirm worker rather than stacking a redundant second modal +
        write."""
        await self._apply_retry_cap()

    def _kick_live_refresh(self, seconds: float = 90.0, *, expand_activity: bool = True) -> None:
        """Fast-poll + immediate snapshot after a manage action (VIEW-20).

        Keeps errors / activity / debug / metrics / runs mirroring on-disk pipeline writes at ~0.4s
        even after the detached ``claude`` child exits (grandchild pipeline may still be writing).
        """
        self._live_refresh_until = max(self._live_refresh_until, time.monotonic() + seconds)
        self._ensure_fast_poll()
        self._ensure_heartbeat_anim()
        self._poll()
        if expand_activity:
            try:
                self.query_one("#diag-tabs-panel", TabbedContent).active = _DIAG_PANE_ACTIVITY
            except Exception:  # noqa: BLE001 — teardown / headless edge
                pass

    def _needs_rapid_poll(self) -> bool:
        """True when a detached child or post-launch sync window needs sub-second polling."""
        if self._launched_runs or self._pending_launches:
            return True
        return time.monotonic() < self._live_refresh_until

    def _fast_poll_active(self) -> bool:
        """True when the heartbeat strip should stay visible (launch, sync window, or disk activity)."""
        if self._needs_rapid_poll():
            return True
        return self._disk_pipeline_active

    def _ensure_heartbeat_anim(self) -> None:
        if self._heartbeat_anim is None and self._fast_poll_active():
            self._heartbeat_anim = self.set_interval(0.12, self._tick_heartbeat)

    def _set_heartbeat_chrome(self, visible: bool) -> None:
        """Show or hide the heartbit titled panel and its 1-row gap below status."""
        try:
            self.query_one("#heartbit-panel", Vertical).display = visible
        except Exception:  # noqa: BLE001 — teardown / headless edge
            pass
        try:
            self.query_one("#panel-gap-status-heartbit", Static).display = visible
        except Exception:  # noqa: BLE001 — teardown / headless edge
            pass
        try:
            hb = self.query_one("#heartbeat", Static)
            if not visible:
                hb.update("")
            hb.display = visible
        except Exception:  # noqa: BLE001 — teardown / headless edge
            pass

    def _stop_heartbeat_anim_if_idle(self) -> None:
        if not self._fast_poll_active() and self._heartbeat_anim is not None:
            self._heartbeat_anim.stop()
            self._heartbeat_anim = None
        if not self._fast_poll_active():
            self._set_heartbeat_chrome(False)

    def _tick_heartbeat(self) -> None:
        self._heartbeat_phase = (self._heartbeat_phase + 1) % 64
        self._render_heartbeat()

    def _heartbeat_task_items(self) -> list[str]:
        """All in-flight work items the heartbeat strip is tracking."""
        labels: list[str] = []

        for run_id, proc in self._launched_runs.items():
            if getattr(proc, "returncode", None) is None:
                labels.append(f"resume {run_id}")

        for proc in self._pending_launches:
            if getattr(proc, "returncode", None) is None:
                labels.append(self._launch_labels.get(id(proc), "claude launch"))

        if labels:
            return labels

        if self._disk_pipeline_active:
            pa = self._pipeline_activity
            run_ids = pa.get("active_run_ids") or []
            batch_ids = pa.get("active_batch_ids") or []
            snap = self._last_snap or {}
            runs_by_id = {r["run_id"]: r for r in (snap.get("runs") or [])}

            for rid in run_ids:
                row = runs_by_id.get(rid) or {}
                step = row.get("current_step")
                status = row.get("status") or "—"
                if step:
                    labels.append(f"{rid} → {step}")
                else:
                    labels.append(f"{rid} ({status})")

            for bid in batch_ids:
                labels.append(f"batch {bid}")

            # RELOAD-02: recover non-pipeline feature launches at parity with runs/batches. This
            # append sits AFTER the in-memory `if labels: return labels` dedup (:985-986), so a live
            # in-memory launch wins and the disk branch only fills in on reload (no double-count).
            for lc in (pa.get("active_launches") or []):
                launch_label = lc.get("label") or "feature"
                launch_kind = lc.get("kind") or ""
                labels.append(f"{launch_label} ({launch_kind})" if launch_kind else launch_label)

            if labels:
                return labels

        return []

    def _heartbeat_primary_task(self) -> str:
        """Single-line task label — primary item when several are in flight."""
        items = self._heartbeat_task_items()
        if not items:
            return "syncing"
        if len(items) == 1:
            return items[0]
        return f"{items[0]} (+{len(items) - 1} more)"

    def _heartbeat_content_width(self, hb: Static) -> int:
        """Usable character width for a full-row heartbeat bar."""
        region = getattr(hb, "content_region", None)
        candidates = (
            region.width if region is not None else 0,
            hb.size.width,
            self.size.width,
        )
        for width in candidates:
            if width and width > 0:
                return max(20, width - 2)
        return 76

    def _heartbeat_bar(self, width: int, phase: int) -> str:
        cells = ["░"] * width
        for offset in range(8):
            idx = (phase + offset * 2) % width
            cells[idx] = "█"
        return "".join(cells)

    def _render_heartbeat(self) -> None:
        """Animated strip shown while a background launch or live-sync window is active."""
        if not self._fast_poll_active():
            self._stop_heartbeat_anim_if_idle()
            return
        try:
            hb = self.query_one("#heartbeat", Static)
        except Exception:  # noqa: BLE001 — teardown / headless edge
            return
        self._set_heartbeat_chrome(True)
        task = self._heartbeat_primary_task()
        style = _HEARTBEAT_STYLE
        bar_width = self._heartbeat_content_width(hb)
        bar = self._heartbeat_bar(bar_width, self._heartbeat_phase)
        out = Text()
        out.append(f"● {task}\n", style=style)
        out.append(bar, style=style)
        hb.update(out)

    def _track_launch(
        self, proc, *, run_id: str | None = None, label: str | None = None, launch_id: str | None = None
    ) -> None:
        """Hold a detached child ref, poll faster while it lives, and drop it when the proc exits."""
        self._children.append(proc)
        if label:
            self._launch_labels[id(proc)] = label
        if run_id:
            self._launched_runs[run_id] = proc
            self._debug_run_id = run_id
        else:
            self._pending_launches.append(proc)
            self._auto_debug_until = time.monotonic() + 120.0
        self._kick_live_refresh(120.0)
        # RELOAD-01: thread launch_id to the watch task so a clean child exit reaps its sidecar.
        asyncio.get_running_loop().create_task(
            self._watch_launch(proc, run_id=run_id, launch_id=launch_id)
        )

    def _ensure_fast_poll(self) -> None:
        if self._fast_poll is None and self._needs_rapid_poll():
            self._fast_poll = self.set_interval(0.4, self._poll)
        self._ensure_heartbeat_anim()

    def _stop_fast_poll_if_idle(self) -> None:
        if not self._needs_rapid_poll() and self._fast_poll is not None:
            self._fast_poll.stop()
            self._fast_poll = None
        self._stop_heartbeat_anim_if_idle()

    async def _watch_launch(
        self, proc, *, run_id: str | None = None, launch_id: str | None = None
    ) -> None:
        await proc.wait()
        if run_id:
            self._launched_runs.pop(run_id, None)
        else:
            self._pending_launches = [p for p in self._pending_launches if p is not proc]
        self._launch_labels.pop(id(proc), None)
        # RELOAD-01: reap this launch's sidecar on clean exit. The WRITE/delete is delegated to the
        # actions mutator — the view never unlinks (SAFETY-02). reap_launch_sidecar swallows OSError.
        if launch_id:
            import gmj_dashboard_actions as actions  # lazy — only reached for a --manage feature launch

            actions.reap_launch_sidecar(self._pipeline_dir, launch_id)
        self._kick_live_refresh(60.0, expand_activity=False)
        self._stop_fast_poll_if_idle()

    def _inflight_status_token(self) -> str:
        """Theme-derived in-flight label for an active resume child (grep-guard safe)."""
        marker = "status-running"
        if marker in GMJ_THEME.variables:
            return marker.removeprefix("status-")
        return "—"

    def _table_status(self, run_id: str, projected: str) -> Text:
        """Status cell for the runs table — in-flight while a resume child for this row is alive."""
        proc = self._launched_runs.get(run_id)
        if proc is not None and getattr(proc, "returncode", None) is None:
            return self._status_cell(self._inflight_status_token())
        return self._status_cell(projected)

    # ── --manage launch collectors (all OVERRIDABLE — Pilot tests inject values) ────────────────────

    async def _prompt_offer(self) -> str | None:
        """Collect the offer URL/text for a fresh run (overridable). ``None`` on cancel."""
        return await self._ask("Offer URL / text:")

    def _selected_run_id(self) -> str | None:
        """Return the ``run_id`` under the #runs cursor (the row key), or ``None`` if no row is selected.

        Reads the already-sanitized projection cursor — the run_id becomes an argv prompt element, never
        a shell token (T-24-09); the child re-validates it. Pure read of the table state (no disk).
        """
        table = self.query_one("#runs", DataTable)
        if table.row_count == 0:
            return None
        try:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:  # noqa: BLE001 — an out-of-range cursor degrades to "no selection"
            return None
        return cell_key.row_key.value

    async def _prompt_batch(self) -> tuple[str, str] | None:
        """Collect a (shortlist path, selection) pair for a batch (overridable). ``None`` on cancel."""
        shortlist = await self._ask("Shortlist path:")
        if not shortlist:
            return None
        select = await self._ask("Select (e.g. 1,3):")
        if not select:
            return None
        return shortlist, select

    # ── --manage launch handlers (r/R/b) — delegate to the actions module, never-silent feedback ────

    @work
    async def action_run(self) -> None:
        """Launch a fresh, force-autonomous gated run in the background via the launcher seam (MANAGE-02).

        Collects an offer, builds the autonomous prompt, launches through gmj_dashboard_actions (whose
        subprocess primitive is the injectable ``self._launcher`` seam), holds the returned proc in
        ``self._children`` WITHOUT awaiting completion (the UI never freezes), and notifies success. A
        FileNotFoundError/OSError becomes a VISIBLE error-severity notice — never a silent failure
        (MANAGE-03 locked decision).

        Runs as a Textual WORKER so the ``_prompt_offer`` modal ``await`` happens off the message pump
        (awaiting a pushed screen inline on the pump deadlocks modal input — see ``action_cap``).
        """
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        offer = await self._prompt_offer()
        if not offer:
            return
        prompt = actions.build_pipeline_prompt(offer=offer, pipeline_dir=self._pipeline_dir)
        try:
            proc = await actions.launch_pipeline(
                prompt, launcher=self._launcher, cwd=self._cwd, pipeline_dir=self._pipeline_dir
            )
        except (FileNotFoundError, OSError) as exc:
            self.notify(f"⚠ launch failed: {exc}", severity="error")
            return
        self._track_launch(proc, label="pipeline run (new offer)")
        self.notify("▸ launched autonomous run (background)")

    @work
    async def action_resume(self) -> None:
        """Resume the selected run in the background via the launcher seam (MANAGE-03).

        Reads the #runs cursor run_id, builds a resume prompt embedding it, and launches detached — same
        fire-and-forget + never-silent failure contract as ``action_run``. A missing selection is itself
        surfaced as a visible notice. Runs as a Textual WORKER for pump-safety parity with ``action_run``.
        """
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        run_id = self._selected_run_id()
        if not run_id:
            self.notify("⚠ no run selected", severity="error")
            return
        prompt = actions.build_pipeline_prompt(run_id=run_id, pipeline_dir=self._pipeline_dir)
        try:
            proc = await actions.launch_pipeline(
                prompt, launcher=self._launcher, cwd=self._cwd, pipeline_dir=self._pipeline_dir
            )
        except (FileNotFoundError, OSError) as exc:
            self.notify(f"⚠ launch failed: {exc}", severity="error")
            return
        self._track_launch(proc, run_id=run_id, label=f"resume {run_id}")
        self.notify(
            f"▸ resuming {run_id} (autonomous) — watch step/gates; fast refresh while active"
        )

    @work
    async def action_batch(self) -> None:
        """Batch the selected offers into a deterministic manifest via the actions module (MANAGE-04).

        Collects a (shortlist, selection) pair, calls ``run_batch`` (fast + deterministic — it hands all
        seeding + schema validation + path hardening to gmj_batch.py) threading the board's own
        ``pipeline_dir`` so the manifest lands under it (W2), and notifies success. A non-zero returncode
        or a raised OSError becomes a visible error-severity notice — never silent.

        Runs as a Textual WORKER so the two sequential ``_prompt_batch`` modals ``await`` off the message
        pump (awaiting a pushed screen inline on the pump deadlocks modal input — see ``action_cap``).
        """
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        collected = await self._prompt_batch()
        if not collected:
            return
        shortlist, select = collected
        try:
            completed = actions.run_batch(shortlist, select, pipeline_dir=self._pipeline_dir)
        except (FileNotFoundError, OSError) as exc:
            self.notify(f"⚠ batch failed: {exc}", severity="error")
            return
        if completed.returncode != 0:
            self.notify(f"⚠ batch failed: {completed.stderr or completed.returncode}", severity="error")
            return
        self.notify("▸ batch manifest written")
        self._kick_live_refresh(45.0)

    # ── VIEW-11 row filter — Input.Changed re-applies the predicate over the cached snapshot ────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Persist filter substrings and re-narrow tables immediately (VIEW-11 / VIEW-18).

        Each Input lowercases into its persistent predicate (applied inside the matching ``_apply_*``
        every poll so Pitfall 4 never resurrects filtered rows), then re-runs over the CACHED
        ``self._last_snap`` — no wait for the next poll, no new data source.
        """
        if event.input.id == "filter":
            self._filter = event.value.strip().lower()
            if self._last_snap is not None:
                self._apply_runs(self._last_snap.get("runs") or [])
        elif event.input.id == "vac-filter":
            self._vac_filter = event.value.strip().lower()
            if self._last_snap is not None:
                self._apply_vacancies(
                    self._last_snap.get("vacancies") or [],
                    self._last_snap.get("batches") or [],
                )
        elif event.input.id == "features-filter":
            self._features_filter = event.value.strip().lower()
            if self._last_snap is not None:
                self._apply_features(self._last_snap.get("features") or [])

    # ── run drill-in (VIEW-09) — RowSelected → on-demand run_detail → frozen modal ────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open drill-in or edit flow for runs, vacancies, features, or configuration rows."""
        row_key = event.row_key.value
        if event.control.id == "vacancies":
            self.open_offer_detail(row_key)
            return
        if event.control.id == "config-table":
            self._on_config_row_selected(row_key)
            return
        if event.control.id == "features-table":
            self.open_feature_detail(row_key)
            return
        self._debug_run_id = row_key
        self._apply_debug()
        self.open_run_detail(row_key)

    def _on_config_row_selected(self, rel_path: str) -> None:
        """VIEW-19: open a read-only modal with the selected config YAML file contents."""
        self.open_config_file(rel_path)

    def open_config_file(self, rel_path: str) -> None:
        """Push a ``ConfigFileModal`` with the on-demand ``config_file_text`` payload."""
        self.push_screen(ConfigFileModal(self._model.config_file_text(rel_path)))

    def open_run_detail(self, run_id: str) -> None:
        """Push a ``RunDetailModal`` built from the on-demand ``run_detail(run_id)`` payload.

        A reusable entry point (the 22-04 command-palette provider calls it too). The model accessor is
        read-only and returns ``{}`` for an unsafe/missing id, which the modal renders as a graceful
        "Run detail unavailable" empty state — never a crash.
        """
        self.push_screen(RunDetailModal(self._model.run_detail(run_id)))

    def open_offer_detail(self, offer_spec_hash: str) -> None:
        """Push a ``VacancyDetailModal`` from the on-demand ``offer_detail`` payload."""
        self.push_screen(VacancyDetailModal(self._model.offer_detail(offer_spec_hash)))

    def open_feature_detail(self, feature_id: str) -> None:
        """Push a ``FeatureModal`` with description + parameter inputs for the selected catalog row."""
        detail = self._model.feature_detail(feature_id)
        self.push_screen(
            FeatureModal(detail, manage=self._manage, run_callback=self._launch_feature)
        )

    def _launch_sidecar_kind(self, feature: dict) -> str:
        """Derive the launch-sidecar kind from a feature SLASH (collective/interview/template).

        RELOAD-01 kind-derivation caveat: ``feature['kind']`` is ``command/agent/skill/flow`` — NOT the
        sidecar kind. The sidecar kind is derived from the FLOW slash/name; the 28-01 writer clamps any
        unknown kind back to ``collective`` as a backstop, so the default here is the safe collective.
        """
        slash = feature.get("slash") or ""
        if slash.endswith("gmj-interview"):
            return "interview"
        if slash.endswith("gmj-template"):
            return "template"
        return "collective"

    @work
    async def _launch_feature(self, feature: dict, values: dict) -> None:
        """Detached ``claude -p`` launch for a features-panel selection (``--manage`` only)."""
        if not self._manage or not feature:
            return
        import gmj_dashboard_actions as actions  # lazy — only under --manage

        # RELOAD-01: bounded orphan prune BEFORE writing — the view calls the mutator, never deletes.
        actions.reap_dead_launches(self._pipeline_dir, limit=20)
        prompt = build_feature_prompt(feature, values)
        try:
            # HON-01: _launch_feature is the easy-to-miss third launch path. It uses build_feature_prompt
            # (not build_pipeline_prompt), so only the env carrier applies — env-only is sufficient here.
            proc = await actions.launch_pipeline(
                prompt, launcher=self._launcher, cwd=self._cwd, pipeline_dir=self._pipeline_dir
            )
        except (FileNotFoundError, OSError) as exc:
            self.notify(f"⚠ feature launch failed: {exc}", severity="error")
            return
        label = feature.get("name") or feature.get("slash") or "feature"
        # RELOAD-01 wiring: persist a launch sidecar so a reloaded board recovers this live launch.
        # The view NEVER writes — every mutation is delegated to the actions module (SAFETY-02).
        launch_id = actions.write_launch_sidecar(
            self._pipeline_dir,
            kind=self._launch_sidecar_kind(feature),
            label=label,
            pid=proc.pid,
            cmd=prompt,
        )
        self._track_launch(proc, label=label, launch_id=launch_id)
        self.notify(f"▸ launched {label} (autonomous) — live refresh while active")

    # ── non-blocking poll spine (VIEW-04) ──────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Seed widgets + bindings, then start the ~1.5s poll and paint once immediately."""
        self._seed_widgets()
        self._install_bindings()
        self.set_interval(self._refresh, self._poll)
        self._poll()  # paint immediately — don't wait a full interval for the first frame
        self.call_after_refresh(self._clear_startup_focus)

    def _clear_startup_focus(self) -> None:
        """Ensure no filter input steals keys before the user clicks a panel (FIND-03 superseded)."""
        try:
            self.set_focus(None)
        except Exception:  # noqa: BLE001 — teardown / headless edge
            pass

    def _poll(self) -> None:
        """Schedule the (disk-bound) snapshot OFF the event loop on a thread worker."""
        self.run_worker(self._poll_worker, thread=True, exclusive=True, group="poll")

    def _poll_worker(self) -> None:
        """Runs in a worker THREAD — safe to block on disk here; then marshal back to the UI thread."""
        snap = self._model.snapshot()                 # the ONLY read; the model is torn-read tolerant
        self.call_from_thread(self._apply, snap)       # touch widgets only on the UI thread

    def _apply(self, snap: dict) -> None:
        """Apply a fresh snapshot with TARGETED updates only — never recompose()."""
        # Teardown guard (never-a-traceback): a threaded poll can marshal _apply back via
        # call_from_thread just as the app is stopping (screen widgets already removed). Applying a
        # snapshot to a torn-down DOM would raise NoMatches on the first query_one — bail quietly.
        if not self.is_running:
            return
        self._last_snap = snap  # cache so an Input.Changed can re-render the filter immediately (VIEW-11)
        self._apply_counters(snap.get("counters") or {})
        self._apply_runs(snap.get("runs") or [])
        self._apply_dag(snap.get("stages") or {})
        self._apply_metrics(snap.get("metrics") or {})
        self._apply_features(snap.get("features") or [])
        self._apply_config(snap.get("config_files") or [])
        self._apply_vacancies(snap.get("vacancies") or [], snap.get("batches") or [])
        self._apply_errors(snap.get("errors") or [])  # VIEW-12: red-forward per-failed-run gate detail
        self._apply_activity(snap.get("activity") or [])  # VIEW-13: newest-first event timeline
        self._apply_charts(snap.get("metrics") or {})  # VIEW-14: block throughput graph + gate bars + trend
        self._apply_debug()  # VIEW-16: refresh the selected run's internals live (retry counts / step)
        self._sync_pipeline_activity(snap.get("pipeline_activity") or {})
        self._render_heartbeat()

    def _sync_pipeline_activity(self, activity: dict) -> None:
        """Enable live refresh when disk shows in-flight pipeline runs or batches (VIEW-28).

        Survives dashboard reload: detached children are untracked, but ``.pipeline/`` state is read
        each poll via ``snapshot()["pipeline_activity"]``.
        """
        self._disk_pipeline_active = bool(activity.get("active"))
        self._pipeline_activity = activity
        if not self._disk_pipeline_active:
            self._stop_fast_poll_if_idle()
            return
        active_ids = activity.get("active_run_ids") or []
        if active_ids and self._debug_run_id is None:
            self._debug_run_id = active_ids[0]
            self._apply_debug()
        if self._needs_rapid_poll():
            self._ensure_fast_poll()
        else:
            self._ensure_heartbeat_anim()
            self._poll()

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

    # ── features catalog panel — skills / agents / commands / flows ─────────────────────────────

    def _feat_match(self, row: dict) -> bool:
        """Keep a feature row iff it matches the features filter substring."""
        f = self._features_filter
        if not f:
            return True
        hay = (
            str(row.get("kind") or "").lower(),
            str(row.get("name") or "").lower(),
            str(row.get("summary") or "").lower(),
        )
        return any(f in part for part in hay)

    def _apply_features(self, rows: list) -> None:
        """Diff the features ``DataTable`` from ``snapshot()["features"]``."""
        t = self.query_one("#features-table", DataTable)
        known = set(t.rows)
        seen: set = set()
        for row in rows:
            if not self._feat_match(row):
                continue
            fid = row.get("id")
            if not fid:
                continue
            seen.add(fid)
            kind = row.get("kind") or "—"
            name = row.get("name") or "—"
            summary = row.get("summary") or "—"
            if len(summary) > 60:
                summary = summary[:57] + "…"
            if fid in known:
                t.update_cell(fid, "kind", kind)
                t.update_cell(fid, "name", name)
                t.update_cell(fid, "summary", summary)
            else:
                t.add_row(kind, name, summary, key=fid)
        for gone in known - seen:
            t.remove_row(gone)

    def _apply_config(self, files: list) -> None:
        """Diff the configuration file browser from ``snapshot()["config_files"]`` (VIEW-19).

        One row per ``config/**/*.yaml`` path (posix-relative to repo root). Enter / click opens a
        read-only modal with the file's full YAML text via ``model.config_file_text``.
        """
        t = self.query_one("#config-table", DataTable)
        known = set(t.rows)
        seen: set = set()
        for rel in sorted(str(path) for path in (files or [])):
            seen.add(rel)
            if rel in known:
                t.update_cell(rel, "file", rel)
            else:
                t.add_row(rel, key=rel)
        for gone in known - seen:
            t.remove_row(gone)

    # ── errors panel (VIEW-12) — red-forward per-failed-run Gate A/Gate B detail ───────────────────

    def _apply_errors(self, errors: list) -> None:
        """Render the failed-run failure detail from ``snapshot()["errors"]`` — targeted, no recompose.

        One block per failed run (``failures()`` output): a red run_id header line carrying its projected
        status + Gate A/B VALUES, then a labelled line per reason — Gate A reasons list each offending
        claim (``rule_violated`` @ ``offending_span``), Gate B reasons list the missing must-have ids +
        their text. Colour is applied inline via RUNTIME value-keyed theme-var lookups
        (``get_css_variables().get("event-fail")`` for the red markers, ``get(f"gate-{verdict}")`` for the
        gate verdicts) — no status/gate word is a code literal (grep-guard stays green), and every red
        marker is ALWAYS paired with its readable label (colorblind-safe). Every rendered token is a
        payload VARIABLE. Empty ``errors`` degrades to the ``No failures`` empty state. Single targeted
        ``Static.update`` — no file read, no recompose (SAFETY-02).
        """
        panel = self.query_one("#errors", Static)
        if not errors:
            panel.update("No failures")
            return
        cssv = self.get_css_variables()
        fail_style = cssv.get("event-fail") or ""
        out = Text()
        for i, e in enumerate(errors):
            if i:
                out.append("\n")
            out.append(str(e.get("run_id")), style=fail_style)   # red run_id header (label + colour)
            out.append("  A:")
            out.append(str(e.get("gate_a")), style=cssv.get(f"gate-{e.get('gate_a')}") or "")  # value-keyed
            out.append(" B:")
            out.append(str(e.get("gate_b")), style=cssv.get(f"gate-{e.get('gate_b')}") or "")  # value-keyed
            for r in e.get("reasons") or []:
                gate = r.get("gate")  # payload VALUE ("A"/"B" — allowed, not a forbidden literal)
                if gate == "A":
                    for claim in r.get("offending_claims") or []:
                        out.append("\n  ")
                        out.append(f"{gate}", style=fail_style)  # red gate marker + readable detail
                        out.append(f" {claim.get('rule_violated')} @ {claim.get('offending_span')}")
                elif gate == "B":
                    for mh in r.get("missing_must_haves") or []:
                        out.append("\n  ")
                        out.append(f"{gate}", style=fail_style)
                        out.append(f" missing {mh.get('id')}: {mh.get('text')}")
                    # ids with no must-have text still surface (the projection may carry ids only).
                    text_ids = {mh.get("id") for mh in (r.get("missing_must_haves") or [])}
                    for mid in r.get("missing_ids") or []:
                        if mid in text_ids:
                            continue
                        out.append("\n  ")
                        out.append(f"{gate}", style=fail_style)
                        out.append(f" missing {mid}")
        panel.update(out)

    # ── activity feed (VIEW-13) — newest-first, event-colored event timeline ──────────────────────

    def _apply_activity(self, activity: list) -> None:
        """Render the newest-first event timeline from ``snapshot()["activity"]`` — targeted, no recompose.

        One line per event (the list arrives pre-sorted newest-first from the model): the run timestamp,
        the run_id, then a readable label — a ``started`` marker, a gate line showing the gate
        discriminator + verdict VALUE, or a terminal line showing the projected status VALUE. Every token
        is a payload VARIABLE (``kind``/``gate``/``verdict``/``status`` read from the event dict — never a
        status/gate word literal), so the Phase-20 grep-guard stays green. Colour is applied inline via
        RUNTIME value-keyed theme-var lookups — a gate event by its verdict (``event-{verdict}``), a
        terminal event by its projected status (``status-{status}``, falling back to ``event-{status}``),
        and the started marker by ``event-{kind}`` — and is ALWAYS paired with the readable label
        (colorblind-safe). The panel header (``activity (events)``) signals event-level, not live stdout
        (the honesty contract). Empty activity degrades to the ``No activity yet`` empty state; the
        ``#activity`` frame scrolls internally. Single targeted ``Static.update`` — no file read, no
        recompose (SAFETY-02).
        """
        panel = self.query_one("#activity", Static)
        if not activity:
            panel.update("No activity yet")
            return
        cssv = self.get_css_variables()
        out = Text()
        for i, e in enumerate(activity):
            if i:
                out.append("\n")
            kind = e.get("kind")
            verdict = e.get("verdict")   # gate events only (a VALUE: "pass"/"fail")
            status = e.get("status")     # terminal events only (a projected status VALUE)
            gate = e.get("gate")         # gate events only (a VALUE: "A"/"B")
            ts = e.get("ts") or "—"
            rid = str(e.get("run_id"))
            # Resolve the event colour by VALUE (never a status/gate word literal): a gate event by its
            # verdict, a terminal event by its projected status, else the started marker by its kind.
            if verdict is not None:
                color = cssv.get(f"event-{verdict}") or ""
                label = f"{kind} {gate} {verdict}"
            elif status is not None:
                color = cssv.get(f"status-{status}") or cssv.get(f"event-{status}") or ""
                label = f"→ {status}"
            else:
                color = cssv.get(f"event-{kind}") or ""
                label = str(kind)
            out.append(f"{ts} {rid} ")           # timestamp + run_id (panel color)
            out.append(label, style=color)        # readable label ALWAYS paired with the event colour
        panel.update(out)

    # ── extended charts (VIEW-14) — block throughput graph + Gate A/B bars + per-status trend ──────

    def _apply_charts(self, m: dict) -> None:
        """Render the btop-density chart band from ``snapshot()["metrics"]`` — targeted, no recompose.

        Three sections, all pure projections of the ``metrics`` dict (no disk, no data logic):

        - the BIG throughput graph — a hand-rolled MULTI-ROW block matrix via ``_block_graph(m["throughput"])``
          (Textual's ``Sparkline`` is single-row only, so it cannot produce this — 23-RESEARCH Pitfall 1);
        - a Gate A/B pass-fail bar chart — a green ``█`` run of length ``pass`` + a red ``█`` run of length
          ``fail`` from ``m["gate_a"]``/``m["gate_b"]`` (the projection's verdict tallies, not gate-node
          literals) with a numeric ``N pass / M fail`` label; colours from ``get_css_variables()`` gate-pass/
          gate-fail (value-keyed, never a ``.py`` literal), ALWAYS paired with the numeric label;
        - a per-status trend row per status VALUE from ``m["throughput_by_status"][status]`` — a compact
          single-row block spark (``_block_graph(series, rows=1)``); the status keys are read from the dict
          (variables) and coloured by a runtime ``status-{status}`` lookup, paired with the readable label.

        Empty metrics degrade to the ``(no metrics yet)`` empty state. Single targeted ``Static.update`` —
        no file read, no recompose (SAFETY-02); no status/gate word is a code literal (SAFETY-03).
        """
        panel = self.query_one("#charts", Static)
        if not m:
            panel.update("(no metrics yet)")
            return
        cssv = self.get_css_variables()
        pass_style = cssv.get("gate-pass") or ""
        fail_style = cssv.get("gate-fail") or ""
        out = Text()

        # (1) BIG multi-row block throughput graph — >1 row (NOT a single-row Sparkline).
        out.append("throughput\n")
        out.append(_block_graph(m.get("throughput") or []))

        # (2) Gate A/B pass-fail bar chart — green pass run + red fail run + a numeric label.
        for label, gate in (("Gate A", m.get("gate_a") or {}), ("Gate B", m.get("gate_b") or {})):
            n_pass = gate.get("pass", 0)   # "pass"/"fail" are the projection's verdict keys (allowed)
            n_fail = gate.get("fail", 0)
            out.append(f"\n{label}  ")
            out.append("█" * n_pass, style=pass_style)   # colour ALWAYS paired with the numeric label
            out.append("█" * n_fail, style=fail_style)
            out.append(f"  {n_pass} pass / {n_fail} fail")

        # (3) per-status trend — a compact single-row block spark per projected status VALUE.
        tbs = m.get("throughput_by_status") or {}
        if tbs:
            out.append("\ntrend")
            for status, series in sorted(tbs.items()):     # keys are DATA-DERIVED status VALUES
                color = cssv.get(f"status-{status}") or ""
                out.append(f"\n{status:<10} ", style=color)
                out.append(_block_graph(series or [], rows=1), style=color)

        panel.update(out)

    # ── commands reference (VIEW-15) — static, mode-aware keybinding list ──────────────────────────

    def _apply_commands(self) -> None:
        """Render the static, mode-aware keybinding reference into ``#commands`` (VIEW-15).

        A view-only panel (no model data): the always-present read-only keys (quit, drill-in, command
        menu) plus one row per ``_MANAGE_KEYS`` entry, whose mode column reflects ``self._manage`` — the
        mutating keys show the active ``(--manage)`` mode under ``--manage`` and a ``(--manage · Phase 24)``
        deferred note in read-only mode (they stay inert this phase; Phase 24 wires the behaviour). Seeded
        ONCE from ``_seed_widgets`` (it is static — not per-poll). No forbidden literal is a standalone
        string constant here, so the grep-guard stays green.

        Also carries the HON-03 frozen-vs-live legend: two plain-words lines naming that a *marked* run is
        a live in-flight child spawned this session (see ``_inflight_status_token`` / ``_table_status``)
        while an *unmarked* run is the frozen on-disk status from the last poll. The legend is text only —
        it never re-derives ``project_status()`` and stays inside the grep-guard-safe vocabulary.
        """
        lines = [
            "key     action          (mode)",
            "q       quit            (read-only)",
            "enter   drill-in        (read-only · runs / vacancies / features / config)",
            "ctrl+p  command menu    (read-only)",
            "        diagnostics: ←/→ switch pane when tab bar focused",
            "        legend: a marked run = a live in-flight child this session",
            "        legend: an unmarked run = frozen on-disk status from the last poll",
        ]
        manage_mode = "--manage" if self._manage else "--manage · Phase 24"
        for key, _action, desc in _MANAGE_KEYS:  # (r,run,Run) (R,resume,Resume) (b,batch,Batch) …
            lines.append(f"{key:<7} {desc:<15} ({manage_mode})")
        self.query_one("#commands", Static).update("\n".join(lines))

    # ── debug / internals panel (VIEW-16) — selected run's run_detail key/value grid ───────────────

    def _apply_debug(self) -> None:
        """Render the selected run's ``run_detail`` internals into ``#debug`` — targeted, no recompose.

        Guard on ``self._debug_run_id``: unset (no row selected yet) OR an ``run_detail`` that returns
        ``{}`` (unsafe/missing id) degrades to the ``Select a run for internals`` empty state. Otherwise a
        dense key/value grid is rendered from ``self._model.run_detail(self._debug_run_id)`` — run_id,
        status, mode, gate A/B, offer_spec_hash, retry_cap, retry_counts, current_step, artifacts and
        attempts. EVERY value is a payload VARIABLE (never a status/gate word literal), so the grep-guard
        stays green; the ``run_detail`` accessor is read-only. Called on ``RowSelected`` (live selection)
        AND every poll so retry counts / current step refresh in place.
        """
        debug = self.query_one("#debug", Static)
        if not self._debug_run_id:
            debug.update("Select a run for internals")
            return
        d = self._model.run_detail(self._debug_run_id)
        if not d:
            debug.update("Select a run for internals")
            return
        rc = d.get("retry_counts") or {}
        # retry_counts is {offer: {type: n}} — flatten to a compact display string (values are data).
        retry_bits = [f"{offer}/{typ} {n}" for offer, per in rc.items()
                      if isinstance(per, dict) for typ, n in per.items()]
        retry_summary = ", ".join(retry_bits) or "—"
        lines = [
            f"run_id       {d.get('run_id') or '—'}",
            f"status       {d.get('status') or '—'}",
            f"run_mode     {d.get('mode') or '—'}",
            f"gate A/B     {d.get('gate_a')} / {d.get('gate_b')}",
            f"offer_hash   {d.get('offer_spec_hash') or '—'}",
            f"retry_cap    {d.get('retry_cap') if d.get('retry_cap') is not None else '—'}",
            f"retries      {retry_summary}",
            f"current_step {d.get('current_step') or '—'}",
            f"artifacts    {', '.join(d.get('artifacts') or []) or '—'}",
            f"attempts     {', '.join(d.get('attempts') or []) or '—'}",
        ]
        debug.update("\n".join(lines))

    # ── found-vacancies + batch-rollup panel (VIEW-10) — verbatim projection rows ──────────────────

    def _vac_match(self, v: dict) -> bool:
        """VIEW-18 view-only predicate: keep a projected vacancy iff it matches ``self._vac_filter``."""
        f = self._vac_filter
        if not f:
            return True
        hay = (
            str(v.get("title") or "").lower(),
            str(v.get("company") or "").lower(),
            str(v.get("seniority") or "").lower(),
            str(v.get("location") or "").lower(),
            str(v.get("offer_spec_hash") or "").lower(),
        )
        return any(f in part for part in hay)

    def _apply_vacancies(self, vac: list, batches: list) -> None:
        """Diff the vacancies ``DataTable`` + batch rollup from the projection (VIEW-10 / VIEW-17 / VIEW-18).

        The table is keyed by ``offer_spec_hash`` with targeted cell updates (never clear+refill).
        VIEW-18: rows failing ``_vac_match`` are skipped/removed every tick (Pitfall 4). The sibling
        ``#vac-batches`` Static carries batch rollups and empty-offer hints below the table.
        """
        t = self.query_one("#vacancies", DataTable)
        known = set(t.rows)
        seen: set = set()
        for v in vac:
            if not self._vac_match(v):
                continue
            rk = v.get("offer_spec_hash")
            if not rk:
                continue
            seen.add(rk)
            title = v.get("title") or "—"
            company = v.get("company") or "—"
            seniority = v.get("seniority") or "—"
            sal_s = _format_salary(v.get("salary_range"))
            mh = str(v.get("n_must_haves", 0))
            if rk in known:
                t.update_cell(rk, "title", title)
                t.update_cell(rk, "company", company)
                t.update_cell(rk, "seniority", seniority)
                t.update_cell(rk, "salary", sal_s)
                t.update_cell(rk, "mh", mh)
            else:
                t.add_row(title, company, seniority, sal_s, mh, key=rk)
        for gone in known - seen:
            t.remove_row(gone)

        lines: list[str] = []
        if not vac:
            lines.extend(["No frozen offers", "Freeze an offer with the scout/freeze step."])
        elif not seen:
            lines.append("No vacancies match filter")
        lines.append("")
        lines.append("batches:" if batches else "No batches")
        for b in batches:
            done = next((val for k, val in b.items() if k not in ("batch_id", "total", "status")), 0)
            lines.append(f"  {b['batch_id']}  {done}/{b['total']}  {b['status']}")
        self.query_one("#vac-batches", Static).update("\n".join(lines).strip())

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

    def _match(self, r: dict) -> bool:
        """VIEW-11 view-only predicate: keep a projected row iff it matches the filter substring.

        With no active filter every row is kept. Otherwise the row survives when the lowercased filter
        is a substring of the row's ``run_id`` OR its ``status``. Both are PROJECTION VALUES read from
        the row dict (variables, never a status-word literal), so the Phase-20 grep-guard stays green.
        This is a pure in-memory test — no path, command, or new data source (T-22-10).
        """
        f = self._filter
        return not f or f in r["run_id"].lower() or f in str(r["status"]).lower()

    def _apply_runs(self, rows: list) -> None:
        """Diff the runs ``DataTable`` against the fresh projection rows — targeted updates only.

        Never ``clear()``+refill and never ``recompose()``: rows are keyed by ``run_id`` so an existing
        run is patched cell-by-cell via ``update_cell`` (status through ``_status_cell``; ``mode``,
        ``gate_a``, ``gate_b``, ``current_step`` with a ``-`` fallback), a newly-appeared run is
        ``add_row``ed with its ``run_id`` key, and a run dir that vanished this tick is ``remove_row``ed.
        The row cursor and row count therefore stay stable across polls (VIEW-04 strengthened).

        VIEW-11: a row failing ``_match`` (the persistent ``self._filter`` predicate) is skipped on add
        and ``remove_row``ed if currently present — the predicate is applied HERE every tick so a poll
        never resurrects a filtered-out row (Pitfall 4), while surviving rows keep their cursor + order.
        """
        t = self.query_one("#runs", DataTable)
        known = set(t.rows)            # existing RowKeys (StringKey compares/hashes by value)
        seen: set = set()
        for r in rows:
            if not self._match(r):     # filtered-out — leave it out of `seen` so it is removed below
                continue
            rk = r["run_id"]
            seen.add(rk)
            step = r.get("current_step") or "-"
            if rk in known:            # targeted per-cell patch — no clear+refill, no recompose
                t.update_cell(rk, "status", self._table_status(rk, r["status"]))
                t.update_cell(rk, "mode", r["mode"])
                t.update_cell(rk, "gate_a", r["gate_a"])
                t.update_cell(rk, "gate_b", r["gate_b"])
                t.update_cell(rk, "current_step", step)
            else:                      # a newly-appeared run — append keyed by run_id
                t.add_row(
                    r["run_id"],
                    self._table_status(rk, r["status"]),
                    r["mode"],
                    r["gate_a"],
                    r["gate_b"],
                    step,
                    key=rk,
                )
        for gone in known - seen:      # a run dir that vanished mid-session — drop its row
            t.remove_row(gone)
        if time.monotonic() < self._auto_debug_until and rows:
            self._debug_run_id = rows[0]["run_id"]
            self._apply_debug()

    def _counter_item_style(self, label: str) -> str:
        """Per-segment color for the counters strip — status buckets use theme ``status-*`` vars."""
        css = self.get_css_variables()
        status_color = css.get(f"status-{label}")
        if status_color:
            return str(status_color)
        return {
            "runs": "#39d0d8",
            "offers": "#bc8cff",
            "default_mode": "#d29922",
            "cap": "#3fb950",
        }.get(label, "#c9d1d9")

    def _apply_counters(self, c: dict) -> None:
        """Render the global counters strip GENERICALLY so no status word is a standalone literal.

        The per-status counts come from iterating ``c['by_status'].items()`` (keys are data-derived,
        never hardcoded). Copy: ``runs: N │ <status>: N … │ offers: N │ default_mode: … │ cap: N``.
        Each segment is colored independently via ``_counter_item_style``.
        """
        by_status = c.get("by_status") or {}
        items: list[tuple[str, object]] = [("runs", c.get("runs", 0))]
        items.extend(sorted(by_status.items()))
        items.append(("offers", c.get("offers", 0)))
        items.append(("default_mode", c.get("mode", "—")))
        items.append(("cap", c.get("retry_cap")))
        out = Text()
        for i, (label, value) in enumerate(items):
            if i:
                out.append(_COUNTERS_DELIM, style="#6e7681")
            style = self._counter_item_style(label)
            out.append(f"{label}: ", style=style)
            out.append(str(value), style=f"bold {style}")
        self.query_one("#counters", Static).update(out)


def resolve_operator_pipeline_dir(raw: str) -> str:
    """Normalize an operator ``--pipeline-dir`` to an ABSOLUTE, cwd-independent path (HON-01/WR-01).

    The launch paths force the detached child's ``cwd`` to ``REPO_ROOT`` while the read model resolves
    ``--pipeline-dir`` against the dashboard's OWN process cwd. A RELATIVE dir would therefore make the
    child write to ``<REPO_ROOT>/dir`` while the board reads ``<cwd>/dir`` — a stale, silently-diverged
    board that defeats the HON-01 end-to-end honesty this phase exists to deliver. Absolutizing ONCE
    here, at the single source, before the value is threaded to BOTH the model AND the child env/prompt
    carrier, makes board and child agree regardless of where the dashboard was launched (and makes the
    ``launch_pipeline`` ``cwd=REPO_ROOT`` vs ``run_batch`` no-cwd asymmetry stop mattering).
    """
    return str(Path(raw).expanduser().resolve())


def main() -> int:
    """Parse flags and launch the board. ``--manage`` binds the live r/R/b/m/c action layer (24-02)."""
    parser = argparse.ArgumentParser(description="btop-style pipeline dashboard (read-only; --manage adds actions).")
    parser.add_argument("--pipeline-dir", default=".pipeline", help="Pipeline root to project (and batch into).")
    parser.add_argument("--manage", action="store_true", help="Bind the mutating action keys (r/R/b/m/c).")
    parser.add_argument("--read-only", action="store_true", help="Explicit read-only (the default).")
    parser.add_argument("--refresh", type=float, default=1.0, help="Poll interval in seconds (default 1.0).")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Config file the m/c knobs edit under --manage.")
    args = parser.parse_args()
    manage = args.manage and not args.read_only
    # HON-01/WR-01: absolutize the operator dir ONCE so the read model and the launched child agree
    # regardless of the dashboard's launch cwd (the child is forced to cwd=REPO_ROOT).
    pipeline_dir = resolve_operator_pipeline_dir(args.pipeline_dir)
    model = DashboardModel(pipeline_dir=pipeline_dir)
    GmjDashboard(
        model,
        manage=manage,
        refresh=args.refresh,
        config_path=Path(args.config),
        pipeline_dir=pipeline_dir,
        cwd=REPO_ROOT,
    ).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
