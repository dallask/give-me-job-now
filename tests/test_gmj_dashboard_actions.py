#!/usr/bin/env python3
"""Tests for scripts/dashboard/gmj_dashboard_actions.py (MANAGE-02/03/04/05 + SAFETY-01, Plan 24-01).

Plain-python3 self-running harness (NO pytest) — run with
``python3 tests/test_gmj_dashboard_actions.py``. Mirrors the idiom of
``tests/test_gmj_dashboard.py`` / ``tests/test_gmj_dashboard_model.py``: module-level ``REPO_ROOT``,
the ``sys.path.insert`` import seam, a ``main()`` that runs every ``test_*`` and returns 1 on any
failure, and the never-a-traceback discipline (a stray crash can never masquerade as a pass).

No test spawns a REAL ``claude``: the launch path is exercised through an injected fake launcher that
records ``(argv, kwargs)`` and returns a fake process whose ``.wait`` / ``.communicate`` are spies —
proving the launch is fire-and-forget (never awaited to completion). The config edit runs over a COPY
of ``config/pipeline.config.yaml`` inside a ``TemporaryDirectory``; the batch integration runs the
real ``gmj_batch.py init`` into a temp pipeline-dir.

Requirement coverage:
- MANAGE-02  ``test_prompt_forces_autonomous`` / ``test_launch_not_awaited`` / ``test_launch_failure_propagates``
- MANAGE-03  ``test_prompt_resume_carries_run_id``
- MANAGE-04  ``test_run_batch_writes_manifest``
- MANAGE-05  ``test_config_toggle_preserves_comments`` / ``test_set_retry_cap_validation``
- SAFETY-01  ``test_safety01_no_gate_or_delivery_write`` (AST negative scan of scripts/dashboard/*.py
             with an inline positive control proving the detector fires on a real gate-verdict write)

This test file lives under ``tests/`` (NOT scanned by the SAFETY-03 grep-guard), so it may name the
forbidden literals it asserts against freely. It composes with — never duplicates — the existing
SAFETY-03 grep-guard (``tests/test_gmj_dashboard_model.py``) which already scans this dir for
re-derived status/gate-node literals; the view+model no-write AST proof lives in Plan 24-02.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from subprocess import DEVNULL

REPO_ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = REPO_ROOT / "scripts" / "dashboard"
PIPELINE_DIR = REPO_ROOT / "scripts" / "pipeline"
CONFIG_SRC = REPO_ROOT / "config" / "pipeline.config.yaml"
SHORTLIST = REPO_ROOT / "tests" / "fixtures" / "batch" / "shortlist.thin-and-rich.json"

sys.path.insert(0, str(DASH_DIR))
sys.path.insert(0, str(PIPELINE_DIR))
import gmj_dashboard_actions as actions  # noqa: E402
import gmj_runs  # noqa: E402  (source of the _safe_component path-safety gate)


# ── fakes ────────────────────────────────────────────────────────────────────────────────────────

class _FakeProc:
    """A stand-in for an asyncio subprocess: its ``.wait`` / ``.communicate`` are spy callables."""

    def __init__(self) -> None:
        self.wait_calls = 0
        self.communicate_calls = 0
        self.pid = os.getpid()  # Plan 28-03 launch path reads proc.pid for the sidecar

    async def wait(self) -> int:
        self.wait_calls += 1
        return 0

    async def communicate(self):
        self.communicate_calls += 1
        return (b"", b"")


class _RecordingLauncher:
    """A fake launcher that records ``(argv, kwargs)`` and returns a fresh ``_FakeProc``."""

    def __init__(self) -> None:
        self.argv: tuple = ()
        self.kwargs: dict = {}
        self.calls = 0
        self.proc = _FakeProc()

    async def __call__(self, *argv, **kwargs):
        self.calls += 1
        self.argv = argv
        self.kwargs = kwargs
        return self.proc


# ── MANAGE-02/03: prompt + argv builders ──────────────────────────────────────────────────────────

def test_prompt_forces_autonomous() -> None:
    prompt = actions.build_pipeline_prompt(offer="https://work.ua/jobs/7890/")
    assert "mode=autonomous" in prompt, f"a fresh run must force the autonomous mode token: {prompt!r}"
    assert "offer=https://work.ua/jobs/7890/" in prompt, f"a fresh run must carry the offer: {prompt!r}"
    assert "run_id=" not in prompt, f"a fresh (non-resume) run must not carry a run_id: {prompt!r}"
    assert actions.build_launch_argv(prompt) == [
        "claude",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
    ], "build_launch_argv must be the exact 4-element argv list"


def test_prompt_embeds_pipeline_dir() -> None:
    # HON-01 carrier: a pipeline_dir stamps a readable pipeline-dir=<dir> token into the prompt while
    # mode=autonomous stays FIRST and unconditional (locked v3.0 force-autonomous decision).
    prompt = actions.build_pipeline_prompt(offer="https://work.ua/jobs/7890/", pipeline_dir="/DIR")
    assert "pipeline-dir=/DIR" in prompt, f"prompt must embed the operator pipeline dir: {prompt!r}"
    assert prompt.startswith(f"{actions.PIPELINE_RUN}  mode=autonomous"), (
        f"mode=autonomous must stay first and unconditional: {prompt!r}"
    )
    assert prompt.index("mode=autonomous") < prompt.index("pipeline-dir="), (
        f"force-autonomous must precede the pipeline-dir token: {prompt!r}"
    )


def test_prompt_omits_pipeline_dir_when_absent() -> None:
    # Unchanged behavior: with no pipeline_dir the prompt carries no pipeline-dir token.
    prompt = actions.build_pipeline_prompt(offer="https://work.ua/jobs/7890/")
    assert "pipeline-dir=" not in prompt, f"no dir → no pipeline-dir token: {prompt!r}"


def test_prompt_resume_carries_run_id() -> None:
    run_id = "20260705T120000-abcd"
    prompt = actions.build_pipeline_prompt(run_id=run_id)
    assert "mode=autonomous" in prompt, f"a resume must also force autonomous: {prompt!r}"
    assert f"run_id={run_id}" in prompt, f"a resume must embed run_id=<id> (mirrors gmj_runs.py): {prompt!r}"


# ── MANAGE-02: fire-and-forget launch contract ─────────────────────────────────────────────────────

def test_launch_not_awaited() -> None:
    launcher = _RecordingLauncher()

    async def _go():
        return await actions.launch_pipeline("PROMPT-X", launcher=launcher, cwd="/tmp")

    proc = asyncio.run(_go())
    assert launcher.calls == 1, "the launcher must be awaited exactly once (creation only)"
    assert launcher.argv == (
        "claude",
        "--dangerously-skip-permissions",
        "-p",
        "PROMPT-X",
    ), f"the launched argv must be the exact 4-element list: {launcher.argv!r}"
    assert launcher.kwargs.get("start_new_session") is True, "the child must be detached (start_new_session=True)"
    assert launcher.kwargs.get("stdin") is DEVNULL, "stdin must be DEVNULL"
    assert launcher.kwargs.get("stdout") is DEVNULL, "stdout must be DEVNULL"
    assert launcher.kwargs.get("stderr") is DEVNULL, "stderr must be DEVNULL"
    assert launcher.kwargs.get("cwd") == "/tmp", "cwd must be threaded through"
    assert proc is launcher.proc, "launch_pipeline must return the launcher's process"
    # Fire-and-forget: the returned process is NEVER awaited to completion.
    assert proc.wait_calls == 0, "launch_pipeline must never call .wait() (would block the UI)"
    assert proc.communicate_calls == 0, "launch_pipeline must never call .communicate() (would block the UI)"


def test_launch_env_carries_pipeline_dir() -> None:
    # HON-01 authoritative carrier: a pipeline_dir builds the child env from a COPY of os.environ
    # (GMJ_PIPELINE_DIR set, PATH preserved) — never a bare dict that would strip PATH.
    launcher = _RecordingLauncher()

    async def _go():
        return await actions.launch_pipeline(
            "PROMPT-X", launcher=launcher, cwd="/tmp", pipeline_dir="/DIR"
        )

    asyncio.run(_go())
    env = launcher.kwargs.get("env")
    assert env is not None, "a pipeline_dir must produce a child env (never inherit)"
    assert env.get("GMJ_PIPELINE_DIR") == "/DIR", f"child env must carry the operator dir: {env!r}"
    assert "PATH" in env, "env must be a COPY of os.environ (child keeps PATH — no bare dict)"


def test_launch_env_inherits_when_no_pipeline_dir() -> None:
    # No pipeline_dir → env inherits (env=None), so the existing fire-and-forget contract is unchanged.
    launcher = _RecordingLauncher()

    async def _go():
        return await actions.launch_pipeline("PROMPT-X", launcher=launcher, cwd="/tmp")

    asyncio.run(_go())
    assert launcher.kwargs.get("env") is None, "no pipeline_dir → env inherits (None)"


def test_launch_failure_propagates() -> None:
    async def _boom(*argv, **kwargs):
        raise FileNotFoundError("claude not on PATH")

    async def _go():
        return await actions.launch_pipeline("PROMPT", launcher=_boom)

    raised = False
    try:
        asyncio.run(_go())
    except FileNotFoundError:
        raised = True
    assert raised, "a launch failure must propagate out of launch_pipeline (the view converts it to a notice)"


# ── MANAGE-05: comment-preserving config edit ──────────────────────────────────────────────────────

def test_config_toggle_preserves_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cp = Path(tmp) / "pipeline.config.yaml"
        shutil.copy(CONFIG_SRC, cp)
        before = cp.read_text(encoding="utf-8")

        mode0, cap0 = actions.read_config_values(cp)
        assert mode0 == "human_in_the_loop", f"seed mode must read verbatim: {mode0!r}"
        assert cap0 == 2, f"seed retry_cap must read verbatim: {cap0!r}"

        nxt = actions.toggle_execution_mode(cp)
        assert nxt == "autonomous", f"toggle must flip human_in_the_loop -> autonomous: {nxt!r}"

        after = cp.read_text(encoding="utf-8")
        mode1, cap1 = actions.read_config_values(cp)
        assert mode1 == "autonomous", "the on-disk mode must be flipped"
        assert cap1 == 2, "the sibling retry_cap line must be untouched by a mode toggle"
        assert "# FREEZE CONTRACT" in after, "the freeze-contract comment block must survive the edit"
        # The retry_cap line itself is byte-identical before/after a mode-only edit.
        assert "retry_cap: 2" in after, "the retry_cap line must survive byte-for-byte"
        # Only the execution_mode value line changed.
        assert before.replace("execution_mode: human_in_the_loop", "execution_mode: autonomous") == after, (
            "a mode toggle must change ONLY the execution_mode value, nothing else"
        )


def test_set_retry_cap_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cp = Path(tmp) / "pipeline.config.yaml"
        shutil.copy(CONFIG_SRC, cp)

        actions.set_retry_cap(cp, 5)
        assert actions.read_config_values(cp)[1] == 5, "set_retry_cap must rewrite the cap value"
        assert "# FREEZE CONTRACT" in cp.read_text(encoding="utf-8"), "comments survive a cap edit too"
        assert actions.read_config_values(cp)[0] == "human_in_the_loop", "the sibling mode line is untouched"

        # bool is an int subclass — must be rejected; negatives and non-ints too.
        for bad in (True, False, -1, 2.5, "3"):
            rejected = False
            try:
                actions.set_retry_cap(cp, bad)  # type: ignore[arg-type]
            except ValueError:
                rejected = True
            assert rejected, f"set_retry_cap must reject {bad!r}"
        # A rejected write leaves the last good value intact.
        assert actions.read_config_values(cp)[1] == 5, "a rejected cap edit must not corrupt the file"


# ── MANAGE-04: batch orchestration writes a manifest ──────────────────────────────────────────────

def test_run_batch_writes_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        completed = actions.run_batch(str(SHORTLIST), "1", pipeline_dir=tmp)
        assert completed.returncode == 0, (
            f"gmj_batch.py init must succeed: rc={completed.returncode} stderr={completed.stderr!r}"
        )
        manifests = list(Path(tmp).glob("batches/*/manifest.json"))
        assert manifests, f"a batch manifest must be written under the target pipeline-dir: {tmp}"


# ── RELOAD-01: launch-sidecar writer + safe id generator ──────────────────────────────────────────

def test_write_launch_sidecar_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        launch_id = actions.write_launch_sidecar(
            tmp, kind="template", label="gmj-template", pid=os.getpid(), cmd="claude -p /gmj-template"
        )
        sidecar = Path(tmp) / "launches" / f"{launch_id}.json"
        assert sidecar.is_file(), f"a sidecar must be published under launches/: {sidecar}"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert set(data) == {"launch_id", "kind", "label", "pid", "launched_at", "cmd"}, (
            f"the payload must carry exactly the six keys: {sorted(data)}"
        )
        assert data["launch_id"] == launch_id, "the payload launch_id must match the return value"
        assert data["kind"] == "template", "a known kind must round-trip verbatim"
        assert data["pid"] == os.getpid(), "the pid must round-trip"
        assert data["label"] == "gmj-template", "the label must round-trip"
        assert data["cmd"] == "claude -p /gmj-template", "the cmd must round-trip"


def test_write_launch_sidecar_clamps_kind() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        launch_id = actions.write_launch_sidecar(
            tmp, kind="bogus", label="x", pid=os.getpid(), cmd="claude"
        )
        data = json.loads((Path(tmp) / "launches" / f"{launch_id}.json").read_text(encoding="utf-8"))
        assert data["kind"] == "collective", f"an unknown kind must clamp to collective: {data['kind']!r}"


def test_generate_launch_id_is_path_safe() -> None:
    for _ in range(20):
        lid = actions._generate_launch_id()
        assert gmj_runs._safe_component(lid), f"generated id must pass _safe_component: {lid!r}"
        assert "/" not in lid and ".." not in lid, f"generated id must have no traversal: {lid!r}"


# ── SAFETY-01: no dashboard code path writes a gate verdict / forces delivery ──────────────────────

# Write sinks: a forbidden path literal is only an offence when it is the TARGET of a WRITE, so a
# read-only mention of state.json / candidate.yaml (which the read model legitimately reads) is NOT
# flagged. This is the meaningful negative-test: it catches a WRITE to a gate/run-state/candidate
# target while allowing the one config write.
_WRITE_METHODS = {"write_text", "write_bytes", "replace", "rename", "unlink", "touch", "mkdir", "dump"}
_FORBIDDEN_IMPORTS = {"gmj_record_gate"}
_FORBIDDEN_WRITE_SUBSTR = ("gate_", "candidate.yaml", "state.json", "/runs/", "gate_results")
_ALLOWED_WRITE_SUBSTR = ("pipeline.config.yaml", ".tmp")


def _write_target_offenders(node: ast.Call, src_name: str) -> list[str]:
    """Collect forbidden write-target literals reachable inside a single write-call expression."""
    out: list[str] = []
    for c in ast.walk(node):
        if isinstance(c, ast.Constant) and isinstance(c.value, str):
            v = c.value
            if any(s in v for s in _FORBIDDEN_WRITE_SUBSTR) and not any(a in v for a in _ALLOWED_WRITE_SUBSTR):
                out.append(f"{src_name}: forbidden write-target literal {v!r}")
    return out


def _scan_source_for_offences(tree: ast.AST, src_name: str) -> list[str]:
    """AST-scan one module: forbidden gmj_record_gate import, a record_gate name/attr, or a WRITE to a
    gate/run-state/candidate target. The single ``pipeline.config.yaml`` (+ ``.tmp``) write is allowed."""
    offenders: list[str] = []
    for node in ast.walk(tree):
        # (a) forbidden import: gmj_record_gate anywhere.
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", None) or ""
            names = {a.name for a in node.names}
            if mod in _FORBIDDEN_IMPORTS or names & _FORBIDDEN_IMPORTS:
                offenders.append(f"{src_name}: import {mod or names}")
        # (b) forbidden name/attr: record_gate (the gate-write verb).
        if isinstance(node, ast.Name) and "record_gate" in node.id:
            offenders.append(f"{src_name}: name {node.id}")
        if isinstance(node, ast.Attribute) and "record_gate" in node.attr:
            offenders.append(f"{src_name}: attr {node.attr}")
        # (c) a WRITE call whose target is a forbidden gate/run-state/candidate path.
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _WRITE_METHODS:
                offenders.extend(_write_target_offenders(node, src_name))
            elif isinstance(func, ast.Name) and func.id == "open":
                mode = ""
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = node.args[1].value or ""
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = kw.value.value or ""
                if any(m in mode for m in ("w", "a", "x", "+")):
                    offenders.extend(_write_target_offenders(node, src_name))
    return offenders


def test_safety01_no_gate_or_delivery_write() -> None:
    # Positive control: the detector MUST fire on a real gate-verdict write + a gmj_record_gate import.
    offending_sample = (
        "import gmj_record_gate\n"
        "from pathlib import Path\n"
        "def forge(run_dir):\n"
        "    (run_dir / 'gate_A.json').write_text('{\"verdict\": \"pass\"}')\n"
        "    (run_dir / 'state.json').write_text('{}')\n"
    )
    control = _scan_source_for_offences(ast.parse(offending_sample), "SAMPLE")
    assert any("import" in o for o in control), f"detector must catch a gmj_record_gate import: {control}"
    assert any("gate_A.json" in o for o in control), f"detector must catch a gate-verdict write: {control}"
    assert any("state.json" in o for o in control), f"detector must catch a run-state write: {control}"

    # And the allowed config write must NOT trip the detector.
    allowed_sample = (
        "from pathlib import Path\n"
        "def edit(p):\n"
        "    tmp = Path('config/pipeline.config.yaml.tmp')\n"
        "    tmp.write_text('execution_mode: autonomous')\n"
        "    tmp.replace(Path('config/pipeline.config.yaml'))\n"
    )
    assert not _scan_source_for_offences(ast.parse(allowed_sample), "ALLOWED"), (
        "the config write (pipeline.config.yaml + .tmp) must be allowed"
    )

    # Real scan: every scripts/dashboard/*.py must be clean.
    sources = sorted(DASH_DIR.glob("*.py"))
    assert sources, f"the dashboard package must have at least one .py file: {DASH_DIR}"
    offenders: list[str] = []
    for src in sources:
        tree = ast.parse(src.read_text(encoding="utf-8"), filename=str(src))
        offenders.extend(_scan_source_for_offences(tree, src.name))
    assert not offenders, f"SAFETY-01: dashboard must never write a gate verdict / force delivery: {offenders}"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        buf = io.StringIO()
        try:
            with contextlib.redirect_stderr(buf):
                test()
            assert "Traceback" not in buf.getvalue(), f"{test.__name__} leaked a traceback: {buf.getvalue()}"
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
