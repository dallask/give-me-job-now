# scripts/runtime/ — Claude Agent SDK runtime adapter (prototype)

This directory is **experimental/unsupported for autonomous runs until parity is verified**. It
is a scoped, additive prototype adapter (SDK-02) that dispatches ONE spoke through
`claude-agent-sdk`'s `query()`. It never replaces the working Claude Code CLI path — that path
remains the default and is untouched by this directory (see `tests/test_gmj_sdk_runner.py::test_default_cli_path_untouched`).

## What this actually is: a CLI wrapper, not an independent inference engine

`claude-agent-sdk` wraps the same `claude` CLI binary as a subprocess per session — it is not a
separate, independent inference engine. Concretely: `claude_agent_sdk`'s default transport
(`SubprocessCLITransport`) spawns a real `claude` CLI process (either bundled inside the SDK's
own wheel, or resolved from `PATH`/known install locations) for every `query()` call. Running a
spoke via this adapter still requires the `claude` CLI to be present on the machine; this
prototype is a different Python-orchestrated *harness* around that same CLI, not a lighter-weight
or CLI-independent replacement for it.

## Runtime-selection mechanism (documented only — not wired into any code)

This phase deliberately stops at documentation. No code in this repo reads a runtime-selection
value today. If a future build wired this adapter into `gmj-orchestrator.md`, the natural
mechanism to opt in would be an environment variable, `GMJ_RUNTIME` (e.g. `GMJ_RUNTIME=sdk`),
resolved once and threaded everywhere — mirroring `scripts/pipeline/gmj_pipeline_paths.py`'s
existing `GMJ_PIPELINE_DIR` precedent (`resolve_pipeline_dir()`: explicit arg > env var >
hardcoded default, read from `os.environ` in exactly one place). `GMJ_RUNTIME` is **not read by
any code in this repo today** — this is deliberately a documentation-only proposal per
CONTEXT.md's "not wired into `gmj-orchestrator.md`" decision; the live-detection shim itself is a
later, out-of-scope build step.

## Hook parity

See `scripts/runtime/HOOK-PARITY.md` for the full checklist: `PreToolUse` scope guard (status:
verified) and `SubagentStop` envelope validation (status: not independently verified — reasoned
from API docs).

## Usage

```bash
pip install -r scripts/contracts/requirements.txt -r scripts/runtime/requirements.txt
python3 scripts/runtime/gmj_sdk_runner.py --spoke <agent-name> --input <bounded-input-file>
```

`scripts/runtime/requirements.txt` is deliberately scoped to `claude-agent-sdk` only —
it stays the explicit, separate opt-in step for the one dependency this directory adds.
It is NOT sufficient on its own: `gmj_sdk_runner.py` unconditionally imports
`scripts/contracts/gmj_validate_envelope.py` at module load time (to re-validate every
spoke's structured_output — the actual trust boundary), which hard-requires
`jsonschema`/`referencing` from `scripts/contracts/requirements.txt`. Installing only
`scripts/runtime/requirements.txt` in a clean environment fails at import time with
`ModuleNotFoundError: No module named 'jsonschema'` before ever reaching the
SDK-not-installed error path below — install both files as shown above.

## Package legitimacy: `claude-agent-sdk` is flagged `[SUS]` — this is a false positive

The automated legitimacy heuristic (`gsd-tools query package-legitimacy check`) flags
`claude-agent-sdk` `[SUS]` with reasons `too-new` and `unknown-downloads`. This is a false
positive: `claude-agent-sdk` is Anthropic's own official Python SDK
(`https://github.com/anthropics/claude-agent-sdk-python`, confirmed org-owned repo), and its
`too-new` signal is an artifact of the heuristic checking the *latest* version's publish date on
a package with an unusually frequent (near-daily) release cadence, not a real newly-created- or
suspicious-package signal. See `.planning/phases/38-runtime-portability-claude-agent-sdk/38-RESEARCH.md`'s
"## Package Legitimacy Audit" section for the full override reasoning. Before running
`pip install -r scripts/runtime/requirements.txt` for the first time on a new machine, it is
still worth manually checking `https://pypi.org/project/claude-agent-sdk/` yourself rather than
trusting this note alone.

## Known limitation: bundled CLI binary may drift from the interactively-used CLI

`claude-agent-sdk`'s wheel bundles its own `claude` CLI binary (`_find_bundled_cli()`), which is
resolved **before** falling back to `PATH`. This means the CLI version this adapter actually
executes could silently drift from whichever `claude` CLI binary a human runs interactively on
the same machine (this host's `PATH`-resolved CLI is a separately-installed v2.1.204; the
bundled binary's version was not independently confirmed identical during the research spike).
This is a known, undocumented-until-now limitation of this prototype — non-blocking here, but
worth resolving before any future SDK-04 full build (e.g. by printing/asserting the resolved CLI
version at adapter startup).
