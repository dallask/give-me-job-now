#!/usr/bin/env node
/**
 * gmj-cursor-adapter.cjs — EXPERIMENTAL Cursor roster generator (PROVIDER-02).
 *
 * Translates this repo's 9 `.claude/agents/*.md` files into Cursor's `.cursor/agents/*.md`
 * subagent format. See `gmj-core/bin/CURSOR-HOOK-PARITY.md` for the documented enforcement
 * gaps this generated roster does NOT close on its own.
 *
 * Design invariants:
 *   - Pure Node builtins only (node:fs, node:path). No npm install, no transitive deps,
 *     mirroring gmj-tools.cjs's own supply-chain-hardening invariant (T-18-SC).
 *   - Read-only with respect to .claude/agents/*.md — never mutates a source file.
 *   - Every generated file's own `description` field carries an EXPERIMENTAL badge naming
 *     CURSOR-HOOK-PARITY.md.
 *   - The gmj-orchestrator translation additionally carries a "DO NOT INVOKE AS A SUBAGENT"
 *     banner (it is the hub's own definition, ported for reference/documentation only).
 *
 * Usage:  node gmj-core/bin/gmj-cursor-adapter.cjs generate [--src <dir>] [--dest <dir>]
 *         Defaults: --src .claude/agents, --dest .cursor/agents (both resolved relative to
 *         the repo root).
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

// --- Layout anchors ----------------------------------------------------------
// This file lives at <src-root>/gmj-core/bin/gmj-cursor-adapter.cjs.
const CORE_ROOT = path.resolve(__dirname, '..'); // <src-root>/gmj-core
const SRC_ROOT = path.resolve(CORE_ROOT, '..'); // <src-root>
const DEFAULT_SRC = path.join(SRC_ROOT, '.claude', 'agents');
const DEFAULT_DEST = path.join(SRC_ROOT, '.cursor', 'agents');

// Every one of the 9 source files carries exactly these 4 frontmatter fields plus `color`
// (confirmed this session) — `color` has no Cursor equivalent and is intentionally dropped,
// never required.
const REQUIRED_FIELDS = ['name', 'description', 'tools', 'model'];

// The exact set whose presence in a source agent's `tools:` list forces `readonly: false` on
// the Cursor side, per 39-RESEARCH.md Pattern 2's table (this set correctly classifies all 9:
// only gmj-truth-verifier and gmj-fit-evaluator, both `tools: Read, Glob, Grep`, contain none
// of these four and resolve readonly:true; every other agent's `tools:` list contains at least
// one of Write/Edit/Bash/Task and resolves readonly:false).
const WRITE_CAPABLE_TOOLS = new Set(['Write', 'Edit', 'Bash', 'Task']);

// The one `name:` value that triggers the extra DO NOT INVOKE banner.
const ORCHESTRATOR_NAME = 'gmj-orchestrator';

/**
 * Parse a flat frontmatter block (`---\nkey: value\n...\n---\n<body>`). No nested YAML
 * structures anywhere across the 9 source files, so a hand-rolled splitter suffices — mirrors
 * gmj-tools.cjs's own zero-transitive-dep philosophy (no js-yaml dependency).
 */
function parseAgentFile(text, label) {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  if (lines[0] !== '---') {
    throw new Error(`${label}: expected frontmatter to open with "---" on line 1`);
  }
  let closeIdx = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i] === '---') {
      closeIdx = i;
      break;
    }
  }
  if (closeIdx === -1) {
    throw new Error(`${label}: frontmatter never closes with a second "---"`);
  }
  const fields = {};
  for (const line of lines.slice(1, closeIdx)) {
    if (line.trim() === '') continue;
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) {
      throw new Error(`${label}: malformed frontmatter line (no colon): ${JSON.stringify(line)}`);
    }
    fields[line.slice(0, colonIdx).trim()] = line.slice(colonIdx + 1).trim();
  }
  for (const req of REQUIRED_FIELDS) {
    if (!(req in fields)) {
      throw new Error(`${label}: missing required frontmatter field "${req}"`);
    }
  }
  const body = lines.slice(closeIdx + 1).join('\n');
  return { fields, body };
}

/** A spoke is readonly:true on the Cursor side exactly when none of its Claude Code tools are
 * write-capable. */
function isReadonly(toolsField) {
  const toolList = toolsField
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  return !toolList.some((t) => WRITE_CAPABLE_TOOLS.has(t));
}

/** Translate one parsed .claude/agents/<name>.md into the .cursor/agents/<name>.md content. */
function renderCursorAgent(fields, body) {
  const { name, description, tools, model } = fields;
  const readonly = isReadonly(tools);
  // Pattern 3 — translate the literal string "sonnet" to "inherit" (Cursor's own "use whatever
  // the parent/session is using" value); pass any other value through unchanged as a defensive
  // fallback, though all 9 current source files use `sonnet` uniformly.
  const cursorModel = model === 'sonnet' ? 'inherit' : model;

  const expBadge = `[EXPERIMENTAL — Cursor adapter, generated from .claude/agents/${name}.md — see gmj-core/bin/CURSOR-HOOK-PARITY.md]`;
  let cursorDescription = `${description} ${expBadge}`;

  let orchestratorHeaderLine = '';
  if (name === ORCHESTRATOR_NAME) {
    const doNotInvoke =
      "DO NOT INVOKE AS A SUBAGENT — this is the hub's own definition, ported for reference/documentation only.";
    cursorDescription += ` [${doNotInvoke}]`;
    orchestratorHeaderLine = `     ${doNotInvoke}\n`;
  }

  const header =
    `<!-- GENERATED FILE — DO NOT HAND-EDIT.\n` +
    `     Source: .claude/agents/${name}.md\n` +
    `     Generated by: gmj-core/bin/gmj-cursor-adapter.cjs (EXPERIMENTAL — see gmj-core/bin/CURSOR-HOOK-PARITY.md)\n` +
    `     Original Claude Code tools grant (coarser here as readonly:${readonly} — precision loss documented in CURSOR-HOOK-PARITY.md): ${tools}\n` +
    orchestratorHeaderLine +
    `-->\n`;

  const frontmatter =
    `---\n` +
    `name: ${name}\n` +
    `description: ${cursorDescription}\n` +
    `model: ${cursorModel}\n` +
    `readonly: ${readonly}\n` +
    `---\n`;

  return `${frontmatter}\n${header}\n${body}`;
}

/** Parse `--src <dir>` / `--dest <dir>` flags from a rest-args array. */
function parseFlags(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--src') {
      out.src = argv[++i];
    } else if (argv[i] === '--dest') {
      out.dest = argv[++i];
    }
  }
  return out;
}

/** Generate .cursor/agents/*.md from .claude/agents/*.md (or the given --src/--dest override). */
function cmdGenerate(opts) {
  const srcDir = opts.src ? path.resolve(opts.src) : DEFAULT_SRC;
  const destDir = opts.dest ? path.resolve(opts.dest) : DEFAULT_DEST;

  if (!fs.existsSync(srcDir) || !fs.statSync(srcDir).isDirectory()) {
    throw new Error(`source agents directory not found: ${srcDir}`);
  }
  const files = fs
    .readdirSync(srcDir)
    .filter((f) => f.endsWith('.md'))
    .sort();
  if (files.length === 0) {
    throw new Error(`no .md files found under ${srcDir}`);
  }
  fs.mkdirSync(destDir, { recursive: true });

  // Prune stale destDir/*.md files whose source no longer exists (a spoke deleted or renamed
  // in srcDir must not leave a ghost .cursor/agents/<old-name>.md behind indefinitely).
  const existing = fs.readdirSync(destDir).filter((f) => f.endsWith('.md'));
  for (const stale of existing) {
    if (!files.includes(stale)) {
      fs.rmSync(path.join(destDir, stale));
      process.stdout.write(`gmj-cursor-adapter: removed stale ${path.join(destDir, stale)} (no matching source file)\n`);
    }
  }

  let count = 0;
  for (const file of files) {
    const text = fs.readFileSync(path.join(srcDir, file), 'utf8');
    const { fields, body } = parseAgentFile(text, file);
    const out = renderCursorAgent(fields, body);
    fs.writeFileSync(path.join(destDir, file), out, 'utf8');
    count += 1;
  }

  process.stdout.write(
    `gmj-cursor-adapter: generated ${count} .cursor/agents/*.md file(s) from ${srcDir} into ${destDir}\n`
  );
  return 0;
}

// --- CLI entry ---------------------------------------------------------------
function main(argv) {
  const [cmd, ...rest] = argv;
  switch (cmd) {
    case 'generate':
      return cmdGenerate(parseFlags(rest));
    default:
      process.stderr.write(
        `unknown command: ${cmd || '(none)'}\nusage: node gmj-core/bin/gmj-cursor-adapter.cjs generate [--src <dir>] [--dest <dir>]\n`
      );
      return 2;
  }
}

if (require.main === module) {
  try {
    process.exit(main(process.argv.slice(2)));
  } catch (err) {
    process.stderr.write(`gmj-cursor-adapter: ${err && err.message ? err.message : String(err)}\n`);
    process.exit(1);
  }
}

module.exports = { parseAgentFile, isReadonly, renderCursorAgent, parseFlags, cmdGenerate };
