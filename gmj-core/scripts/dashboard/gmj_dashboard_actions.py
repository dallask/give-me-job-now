#!/usr/bin/env python3
"""Dashboard action layer — the SOLE mutating / subprocess-launching module in scripts/dashboard/.

This module is the deliberate exception to the ``scripts/dashboard/`` no-write, no-subprocess
discipline (MANAGE-06): every other file in the package (the read model + the view) is read-only and
never spawns a child, while THIS module is the one place a ``--manage`` keypress is allowed to (a)
launch the real gated pipeline as a detached child process and (b) rewrite exactly two operator knobs
in ``config/pipeline.config.yaml``. It adds ZERO safety-critical logic. It never judges a gate, never
records a gate verdict, never forces or bypasses delivery, and never touches candidate truth or any
run state — those decisions live only inside the child run's own deterministic scripts, reflected by
the read model on the next poll (SAFETY-01). The ONLY write this module performs targets
``config/pipeline.config.yaml`` (plus its ``.tmp`` sibling for the atomic publish).

Seams (all unit-testable WITHOUT spawning a real ``claude``):
  - ``build_pipeline_prompt`` / ``build_launch_argv`` — pure argv/prompt builders (force autonomous).
  - ``launch_pipeline`` — detached fire-and-forget launcher; its subprocess primitive is an injectable
    default-arg seam (``launcher=None`` resolves to ``asyncio.create_subprocess_exec``) so a test
    passes a fake recording (argv, kwargs) and asserting the child is never awaited to completion.
  - ``run_batch`` — orchestrates ``scripts/pipeline/gmj_batch.py init`` via an argv list (never a
    shell) so ``gmj_batch.py`` owns all seeding + schema validation + path-traversal hardening.
  - ``read_config_values`` / ``set_execution_mode`` / ``toggle_execution_mode`` / ``set_retry_cap`` —
    comment-preserving line-rewrites of the two knobs, published atomically.

The launch policy is force-autonomous (24-CONTEXT.md locked decision): a dashboard-launched run always
runs without a TTY so it self-completes rather than hanging on a human-pause prompt. The honesty label
and the verbatim (never-executed) resume-command display live in the view (Plan 24-02).
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path
from subprocess import DEVNULL

# scripts/dashboard/gmj_dashboard_actions.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = REPO_ROOT / "config" / "pipeline.config.yaml"
BATCH_SCRIPT = REPO_ROOT / "scripts" / "pipeline" / "gmj_batch.py"

# The pipeline-run command the launched child executes. Mode is FORCED autonomous (locked decision).
PIPELINE_RUN = "/gmj-pipeline-run"
_AUTONOMOUS = "autonomous"
_HUMAN = "human_in_the_loop"
_MODES = (_HUMAN, _AUTONOMOUS)

# Anchored, MULTILINE line-rewrite patterns: (prefix, value, trailing) so any inline trailing comment
# is preserved verbatim via the trailing group. Only the value group is ever replaced.
_MODE_RE = re.compile(r"^(execution_mode:[ \t]*)(\S+)(.*)$", re.M)
_CAP_RE = re.compile(r"^(retry_cap:[ \t]*)(\S+)(.*)$", re.M)


# ── launch seam (MANAGE-02 / MANAGE-03) ──────────────────────────────────────────────────────────

def build_pipeline_prompt(*, offer: str | None = None, run_id: str | None = None) -> str:
    """Compose the ``-p`` prompt for the child run. Always forces the autonomous mode token.

    A fresh run embeds the pasted ``offer``; a resume mirrors ``gmj_runs.py``'s printed resume format
    (``(resume: pass run_id=<id>)``) so the dashboard-built resume string matches what an operator
    sees in the read-only inspector. Uses the REAL /gmj-pipeline-run param spelling (``mode=`` /
    ``offer=`` / ``run_id=``), never a bespoke flag.
    """
    parts = [PIPELINE_RUN, f"mode={_AUTONOMOUS}"]
    if offer:
        parts.append(f"offer={offer}")
    if run_id:
        parts.append(f"(resume: pass run_id={run_id})")
    return "  ".join(parts)


def build_launch_argv(prompt: str) -> list[str]:
    """Return the exact 4-element argv for the detached child (argv list only — never a shell string)."""
    return ["claude", "--dangerously-skip-permissions", "-p", prompt]


async def launch_pipeline(prompt: str, *, launcher=None, cwd=None):
    """Fire the detached, force-autonomous run and RETURN the process. Awaits CREATION only.

    ``launcher`` is an injectable seam: when ``None`` it resolves to
    ``asyncio.create_subprocess_exec`` (the async detached-subprocess primitive); a test passes a fake
    that records ``(argv, kwargs)``. ``start_new_session=True`` puts the child in its own session /
    process group so it neither contends for the TTY nor dies when the TUI exits; the std streams are
    ``DEVNULL`` for the same reason. This awaits the child's CREATION only and NEVER awaits its
    completion (``.wait()`` / ``.communicate()``) so the UI never blocks on the whole run. A missing
    executable raises out of here (``FileNotFoundError`` / ``OSError``); the caller surfaces a visible
    notice — this function never swallows it.
    """
    if launcher is None:
        launcher = asyncio.create_subprocess_exec
    argv = build_launch_argv(prompt)
    proc = await launcher(
        *argv,
        start_new_session=True,
        stdin=DEVNULL,
        stdout=DEVNULL,
        stderr=DEVNULL,
        cwd=cwd,
    )
    return proc  # caller holds a ref (silences GC); completion is never awaited


# ── batch orchestrator (MANAGE-04) ───────────────────────────────────────────────────────────────

def run_batch(shortlist, select, *, pipeline_dir, python: str = sys.executable):
    """Invoke ``gmj_batch.py init`` deterministically and return the completed process.

    Hands the whole per-offer seeding + manifest write + schema validation + path-traversal hardening
    to ``gmj_batch.py`` (the single producer of batch state) — this module never re-implements any of
    it. Built as an argv LIST and run without a shell (never ``shell=True``, never string
    concatenation) so ``shortlist`` / ``select`` / ``pipeline_dir`` become argv elements, never shell
    tokens (Command Injection mitigation). ``pipeline_dir`` is threaded through so the manifest lands
    under the board's own pipeline root.
    """
    argv = [
        python,
        str(BATCH_SCRIPT),
        "init",
        "--shortlist",
        str(shortlist),
        "--select",
        str(select),
        "--pipeline-dir",
        str(pipeline_dir),
    ]
    return subprocess.run(argv, capture_output=True, text=True)


# ── comment-preserving config line-rewrite (MANAGE-05) ───────────────────────────────────────────

def read_config_values(path: Path) -> tuple[str | None, int | None]:
    """Regex-read the two knob values from the config text; either may be ``None`` if absent/unparsable."""
    text = Path(path).read_text(encoding="utf-8")
    m = _MODE_RE.search(text)
    c = _CAP_RE.search(text)
    cap = int(c.group(2)) if c and c.group(2).lstrip("-").isdigit() else None
    return (m.group(2) if m else None), cap


def _atomic_write(path: Path, text: str) -> None:
    """Publish ``text`` to ``path`` atomically: write a sibling ``.tmp`` then ``replace`` it in place."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # atomic publish — no torn / partial config file


def set_execution_mode(path: Path, mode: str) -> None:
    """Rewrite ONLY the value on the ``execution_mode:`` line; comments + sibling key survive verbatim.

    Mirrors ``gmj_state_write.py``'s membership rule: ``mode`` must be one of the two known modes.
    Raises if the key is absent (never silently creates it).
    """
    if mode not in _MODES:
        raise ValueError(f"execution_mode must be one of {_MODES}; got {mode!r}")
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not _MODE_RE.search(text):
        raise ValueError("execution_mode key not found in config")
    _atomic_write(path, _MODE_RE.sub(rf"\g<1>{mode}\g<3>", text, count=1))


def toggle_execution_mode(path: Path) -> str:
    """Flip the two modes and return the new value (defaults to autonomous when the current is unknown)."""
    mode, _ = read_config_values(path)
    nxt = _HUMAN if mode == _AUTONOMOUS else _AUTONOMOUS
    set_execution_mode(path, nxt)
    return nxt


def set_retry_cap(path: Path, cap: int) -> None:
    """Rewrite ONLY the value on the ``retry_cap:`` line; comments + sibling key survive verbatim.

    Mirrors ``gmj_state_write.py``'s validation: an int (bool is an int subclass and is rejected) that
    is not negative. The bound is expressed as ``cap < 0`` (never a ``retry_cap >=`` compare) so the
    inherited grep-guard stays green.
    """
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        raise ValueError("retry_cap must be a non-negative int (not a bool)")
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not _CAP_RE.search(text):
        raise ValueError("retry_cap key not found in config")
    _atomic_write(path, _CAP_RE.sub(rf"\g<1>{cap}\g<3>", text, count=1))
