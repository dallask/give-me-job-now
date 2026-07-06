#!/usr/bin/env python3
"""Read-only catalog of gmj skills, agents, commands, and flows for the dashboard features panel.

Discovers markdown definitions under ``.claude/`` and ``docs/flows.md``, exposes param schemas for
the feature-run modal, and builds detached ``claude -p`` prompts (consumed by ``gmj_dashboard_actions``).
No disk writes, no subprocesses — discovery only.
"""

from __future__ import annotations

import re
from pathlib import Path

_KIND_ORDER: tuple[str, ...] = ("command", "agent", "skill", "flow")

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Param specs keyed by command stem (``gmj-pipeline-run``, ``gmj-pipeline/scout``, …).
_PARAM_SPECS: dict[str, list[dict]] = {
    "gmj-pipeline-run": [
        {"name": "mode", "label": "mode", "placeholder": "autonomous | human_in_the_loop", "default": "autonomous"},
        {"name": "offer", "label": "offer", "placeholder": "URL, pasted text, or offer-spec.json path", "required": True},
        {"name": "run_id", "label": "run_id", "placeholder": "optional — resume an existing run"},
    ],
    "gmj-pipeline/scout": [
        {"name": "offer", "label": "offer / search", "placeholder": "URL, text, or board-search goal", "required": True},
        {"name": "run_id", "label": "run_id", "placeholder": "optional pipeline run scope"},
    ],
    "gmj-pipeline/freeze": [
        {"name": "offer", "label": "offer draft path", "placeholder": "path to fielded offer draft", "required": True},
        {"name": "run_id", "label": "run_id", "placeholder": "optional pipeline run scope"},
    ],
    "gmj-pipeline/compose": [
        {"name": "run_id", "label": "run_id", "placeholder": "pipeline run to compose for", "required": True},
    ],
    "gmj-pipeline/verify": [
        {"name": "run_id", "label": "run_id", "placeholder": "pipeline run for Gate A", "required": True},
    ],
    "gmj-pipeline/evaluate": [
        {"name": "run_id", "label": "run_id", "placeholder": "pipeline run for Gate B", "required": True},
    ],
    "gmj-pipeline/generate": [
        {"name": "run_id", "label": "run_id", "placeholder": "pipeline run to render", "required": True},
    ],
    "gmj-batch": [
        {"name": "shortlist", "label": "shortlist", "placeholder": "path to shortlist JSON", "required": True},
        {"name": "select", "label": "select", "placeholder": "comma-separated offer indices", "required": True},
    ],
    "gmj-collective": [
        {"name": "goal", "label": "goal", "placeholder": "free-form routing goal for the hub", "required": True, "multiline": True},
    ],
    "gmj-interview": [
        {"name": "notes", "label": "notes", "placeholder": "optional context for the interviewer", "multiline": True},
    ],
    "gmj-template": [
        {"name": "design", "label": "design", "placeholder": "screenshot path or design notes", "required": True},
    ],
    "gmj-runs": [],
}

_AGENT_PARAMS: list[dict] = [
    {"name": "goal", "label": "goal", "placeholder": "input for this spoke", "required": True, "multiline": True},
]

_SKILL_PARAMS: list[dict] = [
    {"name": "instruction", "label": "instruction", "placeholder": "how to apply this skill", "required": True, "multiline": True},
]

# flows.md sections → entry slash command + param-spec key (None = read-only).
_FLOW_DEFS: tuple[tuple[str, str, str, str | None, bool], ...] = (
    ("single-offer pipeline", "single-offer pipeline", "/gmj-pipeline-run", "gmj-pipeline-run", True),
    ("per-step pipeline", "per-step pipeline", "/gmj-pipeline/scout", "gmj-pipeline/scout", True),
    ("batch (multi-offer)", "batch", "/gmj-batch", "gmj-batch", True),
    ("interview / preferences capture", "interview", "/gmj-interview", "gmj-interview", True),
    ("template creation", "template", "/gmj-template", "gmj-template", True),
    ("runs inspection", "runs inspection", "/gmj-runs", None, False),
    ("simple full-cv render", "full-cv render", "/gmj-collective", "gmj-collective", True),
    ("dashboard", "dashboard", "/gmj-dashboard", None, False),
)


def _parse_frontmatter(text: str) -> dict[str, str]:
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip()
    return out


def _first_paragraph(body: str) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            if lines:
                break
            continue
        if s.startswith("#"):
            continue
        lines.append(s)
    return " ".join(lines)[:400]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _params_for(stem: str | None, *, runnable: bool) -> list[dict]:
    if not runnable or not stem:
        return []
    if stem in _PARAM_SPECS:
        return [dict(p) for p in _PARAM_SPECS[stem]]
    return [
        {
            "name": "args",
            "label": "arguments",
            "placeholder": "key=value pairs or free-form args",
            "multiline": True,
        }
    ]


def _command_feature(repo_root: Path, path: Path, *, prefix: str | None = None) -> dict:
    rel = path.relative_to(repo_root).as_posix()
    text = _read_text(path)
    fm = _parse_frontmatter(text)
    body = _FM_RE.sub("", text, count=1) if _FM_RE.match(text) else text
    if prefix:
        stem = f"{prefix}/{path.stem}"
        slash = f"/{prefix}/{path.stem}"
        name = f"{prefix}/{path.stem}"
    else:
        stem = path.stem
        slash = f"/{path.stem}"
        name = path.stem
    desc = fm.get("description") or _first_paragraph(body)
    runnable = stem not in ("gmj-runs", "gmj-dashboard")
    return {
        "id": f"command:{stem}",
        "kind": "command",
        "name": name,
        "slash": slash,
        "summary": desc[:120],
        "description": desc,
        "params": _params_for(stem, runnable=runnable),
        "runnable": runnable,
        "source_path": rel,
    }


def _agent_feature(repo_root: Path, path: Path) -> dict:
    rel = path.relative_to(repo_root).as_posix()
    text = _read_text(path)
    fm = _parse_frontmatter(text)
    body = _FM_RE.sub("", text, count=1) if _FM_RE.match(text) else text
    name = fm.get("name") or path.stem
    desc = fm.get("description") or _first_paragraph(body)
    return {
        "id": f"agent:{name}",
        "kind": "agent",
        "name": name,
        "slash": "/gmj-collective",
        "summary": desc[:120],
        "description": desc,
        "params": [dict(p) for p in _AGENT_PARAMS],
        "runnable": True,
        "source_path": rel,
    }


def _skill_feature(repo_root: Path, path: Path) -> dict:
    rel = path.relative_to(repo_root).as_posix()
    text = _read_text(path)
    fm = _parse_frontmatter(text)
    body = _FM_RE.sub("", text, count=1) if _FM_RE.match(text) else text
    name = fm.get("name") or path.parent.name
    desc = fm.get("description") or _first_paragraph(body)
    return {
        "id": f"skill:{name}",
        "kind": "skill",
        "name": name,
        "slash": "/gmj-collective",
        "summary": desc[:120],
        "params": [dict(p) for p in _SKILL_PARAMS],
        "runnable": True,
        "source_path": rel,
    }


def _flow_features(repo_root: Path) -> list[dict]:
    flows_path = repo_root / "docs" / "flows.md"
    if not flows_path.is_file():
        return []
    text = _read_text(flows_path)
    rel = flows_path.relative_to(repo_root).as_posix()
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower()
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()

    out: list[dict] = []
    for section_key, display, slash, param_key, runnable in _FLOW_DEFS:
        body = sections.get(section_key, "")
        desc = _first_paragraph(body) or f"Runtime flow — entry {slash}"
        if "**Entry:**" in body:
            entry = body.split("**Entry:**", 1)[1].split("\n", 1)[0].strip()
            if entry:
                desc = entry[:400]
        stem = param_key or display.replace(" ", "-")
        out.append(
            {
                "id": f"flow:{stem}",
                "kind": "flow",
                "name": display,
                "slash": slash,
                "summary": desc[:120],
                "description": desc,
                "params": _params_for(param_key, runnable=runnable) if param_key else [],
                "runnable": runnable,
                "source_path": rel,
            }
        )
    return out


def discover_features(repo_root: Path) -> list[dict]:
    """Return sorted feature summaries (one dict per command/agent/skill/flow)."""
    root = Path(repo_root)
    features: list[dict] = []

    commands_dir = root / ".claude" / "commands"
    if commands_dir.is_dir():
        for path in sorted(commands_dir.glob("gmj*.md")):
            if path.is_file():
                features.append(_command_feature(root, path))
        pipe_dir = commands_dir / "gmj-pipeline"
        if pipe_dir.is_dir():
            for path in sorted(pipe_dir.glob("*.md")):
                features.append(_command_feature(root, path, prefix="gmj-pipeline"))

    agents_dir = root / ".claude" / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("gmj-*.md")):
            features.append(_agent_feature(root, path))

    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        for path in sorted(skills_dir.glob("gmj-*/SKILL.md")):
            features.append(_skill_feature(root, path))

    features.extend(_flow_features(root))

    kind_rank = {k: i for i, k in enumerate(_KIND_ORDER)}
    return sorted(features, key=lambda f: (kind_rank.get(f["kind"], 99), f["name"].lower()))


def feature_by_id(repo_root: Path, feature_id: str, cache: list[dict] | None = None) -> dict:
    """Look up a full feature record by stable ``id`` (``command:…``, ``agent:…``, …)."""
    items = cache if cache is not None else discover_features(repo_root)
    for item in items:
        if item["id"] == feature_id:
            return dict(item)
    return {}


def build_feature_prompt(feature: dict, values: dict[str, str]) -> str:
    """Compose a ``claude -p`` prompt for the selected feature + collected field values."""
    kind = feature.get("kind") or ""
    slash = feature.get("slash") or ""
    name = feature.get("name") or ""
    cleaned = {k: (v or "").strip() for k, v in values.items() if (v or "").strip()}

    if kind == "agent":
        goal = cleaned.get("goal", "")
        return f"{slash}  mode=autonomous\n\nDelegate to Task({name}) with this input:\n{goal}"

    if kind == "skill":
        instruction = cleaned.get("instruction", "")
        return (
            f"{slash}  mode=autonomous\n\n"
            f"Follow the skill `{name}` (see {feature.get('source_path', '.claude/skills')}):\n{instruction}"
        )

    if kind in ("command", "flow"):
        parts = [slash]
        for key, val in cleaned.items():
            if key == "args":
                parts.append(val)
            elif key == "goal" or key == "notes" or key == "instruction" or key == "design":
                parts.append(f"{key}={val}")
            else:
                parts.append(f"{key}={val}")
        return "  ".join(parts)

    return slash
