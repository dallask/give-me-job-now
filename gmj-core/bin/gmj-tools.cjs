#!/usr/bin/env node
/**
 * gmj-tools.cjs — vendored, zero-dependency installer for the standalone gmj collective.
 *
 * Stages the gmj-core payload (built by 18-06: agents/skills/commands/hooks/scripts/schemas/config)
 * into a caller-supplied target directory, then idempotently MERGES the target's
 * .claude/settings.json without ever clobbering user- or framework-owned hook registrations.
 *
 * Design invariants (Phase 18, PACKAGE-01/02):
 *   - Pure Node builtins only (node:fs, node:path). No npm install, no transitive deps
 *     (supply-chain hardening — threat T-18-SC).
 *   - Path containment: the target dir and every manifest path are resolved absolute and
 *     asserted to stay under the install root before any write; `..` traversal and symlink
 *     escape are rejected (threat T-18-01).
 *   - App-code (agents/skills/commands/hooks/scripts/schemas + app-config) is OVERWRITE-on-install;
 *     user-data config (candidate/sources/credentials/preferences + overlays) is
 *     scaffold-if-absent — a populated profile is never clobbered (threat T-18-02).
 *   - settings.json is parsed-then-throw on malformed JSON (never silent-overwrite, threat T-18-04),
 *     merged at the inner hooks[] command level per matcher, and written only when the bytes
 *     change — a re-install is byte-identical (idempotency, threat T-18-11).
 *
 * Usage:  node gmj-core/bin/gmj-tools.cjs install <target-dir>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

// --- Layout anchors ----------------------------------------------------------
// This file lives at <src-root>/gmj-core/bin/gmj-tools.cjs; the payload manifest keys are
// relative to <src-root> (e.g. "gmj-core/agents/gmj-orchestrator.md").
const CORE_ROOT = path.resolve(__dirname, '..'); // <src-root>/gmj-core
const SRC_ROOT = path.resolve(CORE_ROOT, '..'); // <src-root>
const MANIFEST_PATH = path.join(CORE_ROOT, 'gmj-file-manifest.json');

// The two pip requirements files a fresh install must install (post-install hint).
const REQUIREMENTS_HINT = 'scripts/cv/requirements.txt scripts/contracts/requirements.txt';

// --- Path containment (threat T-18-01) --------------------------------------
function realpathIfExists(p) {
  try {
    return fs.realpathSync(p);
  } catch (_err) {
    return null;
  }
}

/**
 * Resolve `dest` and assert it stays under `realRoot`. Rejects `..` traversal (the resolved
 * path escaping the root) AND symlink escape (a pre-existing symlinked ancestor pointing out).
 * Returns the resolved absolute path.
 */
function assertContained(realRoot, dest) {
  const resolved = path.resolve(dest);
  const rel = path.relative(realRoot, resolved);
  if (rel !== '' && (rel.startsWith('..' + path.sep) || rel === '..' || path.isAbsolute(rel))) {
    throw new Error(`refusing to write outside the install root: ${dest}`);
  }
  // Symlink-escape: realpath the nearest existing ancestor and re-check containment.
  let anc = resolved;
  while (anc !== path.dirname(anc) && !realpathIfExists(anc)) {
    anc = path.dirname(anc);
  }
  const realAnc = realpathIfExists(anc);
  if (realAnc) {
    const relAnc = path.relative(realRoot, realAnc);
    if (relAnc !== '' && (relAnc.startsWith('..' + path.sep) || relAnc === '..' || path.isAbsolute(relAnc))) {
      throw new Error(`refusing to follow a symlink escaping the install root: ${dest} -> ${realAnc}`);
    }
  }
  return resolved;
}

/** Reject a manifest key that carries a `..` segment before it is ever joined to a root. */
function assertSafeManifestKey(key) {
  const segments = key.split(/[\\/]/);
  if (segments.includes('..') || path.isAbsolute(key)) {
    throw new Error(`unsafe manifest path (traversal rejected): ${key}`);
  }
}

// --- Payload mapping ---------------------------------------------------------
// A manifest key is "gmj-core/<category>/<rest>". Map it to a destination under the target dir:
//   agents|skills|commands|hooks -> <target>/.claude/<category>/<rest>
//   scripts|schemas|templates    -> <target>/<category>/<rest>
//   config                       -> <target>/config/<rest>  (user-data .sample handling below)
//   VERSION                      -> <target>/gmj-core/VERSION  (installed-version marker)
const CLAUDE_CATEGORIES = new Set(['agents', 'skills', 'commands', 'hooks']);

/**
 * Classify a manifest key into a copy plan: { destRel, userData }.
 * `destRel` is the target-relative destination; `userData` marks scaffold-if-absent config.
 * Returns null for keys the installer does not stage into the target tree.
 */
function planFor(key) {
  if (key === 'gmj-core/VERSION') {
    return { destRel: path.join('gmj-core', 'VERSION'), userData: false };
  }
  const stripped = key.replace(/^gmj-core[\\/]/, '');
  const firstSep = stripped.search(/[\\/]/);
  if (firstSep < 0) {
    return null; // top-level gmj-core file other than VERSION (e.g. the manifest itself) — skip
  }
  const category = stripped.slice(0, firstSep);
  const rest = stripped.slice(firstSep + 1);

  if (CLAUDE_CATEGORIES.has(category)) {
    return { destRel: path.join('.claude', category, rest), userData: false };
  }
  if (category === 'scripts' || category === 'schemas' || category === 'templates') {
    return { destRel: path.join(category, rest), userData: false };
  }
  if (category === 'config') {
    // User-data templates ship as *.sample and scaffold-if-absent (never clobber a real profile).
    if (rest.endsWith('.sample')) {
      return { destRel: path.join('config', rest.slice(0, -'.sample'.length)), userData: true };
    }
    // App-config (pipeline.dag, fit_thresholds, i18n/labels, ownership-manifest, ...) overwrites.
    return { destRel: path.join('config', rest), userData: false };
  }
  return null;
}

function copyFileEnsuringDir(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

/** sha256 hex of a file (streamed, so large fonts don't buffer whole into memory). */
function sha256File(src) {
  return crypto.createHash('sha256').update(fs.readFileSync(src)).digest('hex');
}

/**
 * Verify a payload file's on-disk bytes against the sha256 the manifest ships. The manifest
 * advertises itself as "tamper-detectable", so a drifted/modified payload file must be caught
 * at install time rather than staged silently (threat: payload tampering).
 */
function assertPayloadIntegrity(key, src, expectedHash) {
  if (typeof expectedHash !== 'string' || !expectedHash) {
    throw new Error(`payload manifest has no sha256 for ${key} — cannot verify integrity`);
  }
  const actual = sha256File(src);
  if (actual !== expectedHash) {
    throw new Error(
      `payload integrity check failed for ${key}: manifest sha256 ${expectedHash} != actual ${actual}`
    );
  }
}

/**
 * Copy every manifest-enumerated payload file into the target. App-code overwrites; user-data
 * config is scaffolded only if the target path is absent. Returns per-bucket counts.
 */
function copyPayload(manifest, realRoot) {
  const files = manifest && manifest.files;
  if (!files || typeof files !== 'object') {
    throw new Error(`payload manifest has no "files" map: ${MANIFEST_PATH}`);
  }
  const counts = { overwritten: 0, scaffolded: 0, preserved: 0, skipped: 0 };

  for (const key of Object.keys(files)) {
    assertSafeManifestKey(key);
    const plan = planFor(key);
    if (!plan) {
      counts.skipped += 1;
      continue;
    }
    const src = path.join(SRC_ROOT, key);
    if (!fs.existsSync(src)) {
      throw new Error(`payload file missing from gmj-core (manifest lists it): ${key}`);
    }
    // Tamper/drift detection: the on-disk payload bytes must match the manifest sha256.
    assertPayloadIntegrity(key, src, files[key]);
    const dest = assertContained(realRoot, path.join(realRoot, plan.destRel));

    if (plan.userData) {
      if (fs.existsSync(dest)) {
        counts.preserved += 1; // never clobber a populated user profile (T-18-02)
        continue;
      }
      copyFileEnsuringDir(src, dest);
      counts.scaffolded += 1;
    } else {
      copyFileEnsuringDir(src, dest);
      counts.overwritten += 1;
    }
  }
  return counts;
}

// --- settings.json merge (threats T-18-04, T-18-11) -------------------------
// The target .claude/settings.json uses Claude Code's nested shape:
//   hooks.{SessionStart,PreToolUse,PostToolUse,SubagentStop} = [ {matcher, hooks:[{type,command}]} ]
// We mirror gsd-core's reconcileCursorHooksJson (managed-marker -> filter -> re-append -> byte-
// compare -> no-op-if-unchanged), adapted to dedup at the inner hooks[] command level PER matcher.

const HOOK_CMD = (name) => `$CLAUDE_PROJECT_DIR/.claude/hooks/${name}`;

// The exact 8-registration managed set the installer owns (mirrors .claude/settings.json).
const MANAGED_EVENTS = ['SessionStart', 'PreToolUse', 'PostToolUse', 'SubagentStop'];
const MANAGED = {
  SessionStart: [
    { matcher: 'startup', hooks: [{ type: 'command', command: HOOK_CMD('gmj-session-bootstrap.sh') }] },
    { matcher: 'resume', hooks: [{ type: 'command', command: HOOK_CMD('gmj-session-bootstrap.sh') }] },
    { matcher: 'clear', hooks: [{ type: 'command', command: HOOK_CMD('gmj-session-bootstrap.sh') }] },
  ],
  PreToolUse: [
    { matcher: 'Bash', hooks: [{ type: 'command', command: HOOK_CMD('gmj-block-destructive-commands.sh') }] },
    {
      matcher: 'WebSearch|WebFetch',
      hooks: [{ type: 'command', command: HOOK_CMD('gmj-sources-scope-guard.sh') }],
    },
  ],
  PostToolUse: [
    { matcher: 'Task', hooks: [{ type: 'command', command: HOOK_CMD('gmj-collective-handoff-contract.sh') }] },
  ],
  SubagentStop: [
    {
      matcher: '.*',
      hooks: [
        { type: 'command', command: HOOK_CMD('gmj-subagent-stop-quality-reminder.sh') },
        { type: 'command', command: HOOK_CMD('gmj-validate-envelope.sh') },
      ],
    },
  ],
};

// The exact set of hook basenames the installer owns, derived from MANAGED (not a
// `gmj-` prefix). A prefix test over-claims the namespace and would evict a user- or
// third-party-authored `gmj-`named hook (e.g. gmj-my-audit.sh) on install without
// restoring it — data loss. Only these exact basenames are evicted-and-re-appended.
const MANAGED_BASENAMES = new Set(
  Object.values(MANAGED).flatMap((regs) =>
    regs.flatMap((r) => r.hooks.map((h) => h.command.slice(h.command.lastIndexOf('/') + 1)))
  )
);

/**
 * The "managed" test: a hook command under `.claude/hooks/` whose basename is one of the
 * installer's OWN shipped hooks (MANAGED_BASENAMES). Only these are evicted-and-re-appended;
 * user-, gsd-, and any other `gmj-`named user hooks survive untouched.
 */
function isManagedHookCommand(command) {
  if (typeof command !== 'string') return false;
  const norm = command.replace(/\\/g, '/');
  const base = norm.slice(norm.lastIndexOf('/') + 1);
  return norm.includes('.claude/hooks/') && MANAGED_BASENAMES.has(base);
}

/**
 * Merge one event's registrations. For each existing registration (per matcher) strip prior
 * managed commands out of its inner hooks[] (keeping user/gsd commands), then re-append the
 * current managed commands into the matching matcher (or create a new registration). Idempotent:
 * a second pass strips the same managed commands and re-appends them in the same order/position.
 */
function mergeEventRegistrations(existingRegs, managedRegs) {
  const existing = Array.isArray(existingRegs) ? existingRegs : [];

  // Step 1: strip managed commands from every existing registration, preserving order + user hooks.
  const result = existing.map((reg) => {
    if (!reg || typeof reg !== 'object') return reg;
    const hooksArr = Array.isArray(reg.hooks) ? reg.hooks : [];
    const userHooks = hooksArr.filter((h) => !(h && isManagedHookCommand(h.command)));
    return { ...reg, hooks: userHooks };
  });

  // Step 2: re-append managed commands into the same-matcher registration, else create one.
  for (const mreg of managedRegs) {
    const idx = result.findIndex((r) => r && typeof r === 'object' && r.matcher === mreg.matcher);
    const managedHooks = mreg.hooks.map((h) => ({ ...h }));
    if (idx >= 0) {
      const cur = Array.isArray(result[idx].hooks) ? result[idx].hooks : [];
      result[idx] = { ...result[idx], hooks: [...cur, ...managedHooks] };
    } else {
      result.push({ matcher: mreg.matcher, hooks: managedHooks });
    }
  }

  // Step 3: drop registrations left with an empty hooks[] (a user reg that held only managed
  // commands and received no managed re-append) so re-installs stay stable.
  return result.filter((r) => !(r && typeof r === 'object' && Array.isArray(r.hooks) && r.hooks.length === 0));
}

/**
 * Idempotently merge the managed hook set into the target settings.json. Parses-then-throws on
 * malformed JSON (never silent-overwrite), byte-compares, and writes only when changed.
 */
function mergeSettings(settingsPath) {
  let parsed = {};
  let currentContent = null;
  if (fs.existsSync(settingsPath)) {
    const raw = fs.readFileSync(settingsPath, 'utf8');
    currentContent = raw;
    if (raw.trim()) {
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        throw new Error(
          `settings.json parse failed (${settingsPath}): ${err && err.message ? err.message : String(err)}`
        );
      }
    }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) parsed = {};

  // A truthy non-object `hooks` (array, string, number, ...) is a malformed/legacy shape.
  // Silently replacing it with {} would discard the user's existing value — the same
  // silent-overwrite failure the JSON-parse path throws on. Surface it instead (T-18-04).
  const existingHooks = parsed.hooks;
  if (
    existingHooks !== undefined &&
    existingHooks !== null &&
    !(typeof existingHooks === 'object' && !Array.isArray(existingHooks))
  ) {
    throw new Error(
      `settings.json has a non-object "hooks" value (${settingsPath}): ${JSON.stringify(existingHooks).slice(0, 120)} — ` +
        `refusing to overwrite it; fix or remove it manually`
    );
  }
  if (!parsed.hooks) parsed.hooks = {};
  const hookTable = parsed.hooks;

  for (const event of MANAGED_EVENTS) {
    const merged = mergeEventRegistrations(hookTable[event], MANAGED[event] || []);
    if (merged.length > 0) {
      hookTable[event] = merged;
    } else {
      delete hookTable[event];
    }
  }

  const nextContent = `${JSON.stringify(parsed, null, 2)}\n`;
  const changed = currentContent !== nextContent;
  const shouldWrite = changed && (currentContent !== null || Object.keys(parsed).length > 0);
  if (shouldWrite) {
    fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
    fs.writeFileSync(settingsPath, nextContent, 'utf8');
  }
  return { changed, wrote: shouldWrite };
}

// --- Install command ---------------------------------------------------------
function loadManifest() {
  if (!fs.existsSync(MANIFEST_PATH)) {
    throw new Error(`payload manifest not found (build it in 18-06): ${MANIFEST_PATH}`);
  }
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8'));
  } catch (err) {
    throw new Error(`payload manifest parse failed: ${err && err.message ? err.message : String(err)}`);
  }
  return manifest;
}

function cmdInstall(targetArg) {
  if (!targetArg) {
    throw new Error('install requires a target directory: install <target-dir>');
  }
  const targetAbs = path.resolve(targetArg);
  fs.mkdirSync(targetAbs, { recursive: true });
  const realRoot = fs.realpathSync(targetAbs);

  const manifest = loadManifest();
  const counts = copyPayload(manifest, realRoot);

  const settingsPath = assertContained(realRoot, path.join(realRoot, '.claude', 'settings.json'));
  const settingsResult = mergeSettings(settingsPath);

  process.stdout.write(
    `gmj installed into ${realRoot}\n` +
      `  app-code overwritten: ${counts.overwritten}, user-data scaffolded: ${counts.scaffolded}, ` +
      `user-data preserved: ${counts.preserved}\n` +
      `  settings.json: ${settingsResult.wrote ? 'merged' : 'unchanged (idempotent)'}\n` +
      `\nNext: install the Python dependencies:\n` +
      `  pip install -r ${REQUIREMENTS_HINT}\n`
  );
  return 0;
}

// --- CLI entry ---------------------------------------------------------------
function main(argv) {
  const [cmd, ...rest] = argv;
  switch (cmd) {
    case 'install':
      return cmdInstall(rest[0]);
    default:
      process.stderr.write(
        `unknown command: ${cmd || '(none)'}\nusage: node gmj-core/bin/gmj-tools.cjs install <target-dir>\n`
      );
      return 2;
  }
}

if (require.main === module) {
  try {
    process.exit(main(process.argv.slice(2)));
  } catch (err) {
    process.stderr.write(`gmj-tools: ${err && err.message ? err.message : String(err)}\n`);
    process.exit(1);
  }
}

module.exports = {
  assertContained,
  assertSafeManifestKey,
  planFor,
  copyPayload,
  isManagedHookCommand,
  mergeEventRegistrations,
  mergeSettings,
};
