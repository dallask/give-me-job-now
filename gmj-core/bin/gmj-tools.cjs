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
//   scripts|schemas              -> <target>/<category>/<rest>
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
  if (category === 'scripts' || category === 'schemas') {
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

  // Task 2 wires the settings.json merge here.

  process.stdout.write(
    `gmj installed into ${realRoot}\n` +
      `  app-code overwritten: ${counts.overwritten}, user-data scaffolded: ${counts.scaffolded}, ` +
      `user-data preserved: ${counts.preserved}\n` +
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

module.exports = { assertContained, assertSafeManifestKey, planFor, copyPayload };
