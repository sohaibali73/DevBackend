#!/usr/bin/env node
/**
 * Long-lived Node worker for DOCX/PPTX generation.
 *
 * Communication protocol:
 *   stdin  : one JSON request per line (NDJSON):
 *            {"id": "<uuid>", "kind": "docx"|"pptx", "spec": {...}, "workdir": "<abs path>"}
 *   stdout : one JSON response per line (NDJSON):
 *            {"id": "<uuid>", "ok": true,  "outfile": "<abs path>", "elapsed_ms": 1234}
 *            {"id": "<uuid>", "ok": false, "error": "<message>"}
 *   stderr : informational logs (free-form text)
 *
 * Module resolution strategy:
 *   The pptxgenjs / docx packages live in the sandbox cache at
 *   ``~/.sandbox/{pptx,docx}_cache/node_modules`` (installed once by the
 *   Python side). We resolve them by ABSOLUTE PATH at job time and let Node's
 *   require cache do the V8-memory caching across jobs — so the second and
 *   subsequent calls are fast even though we don't eagerly load at boot.
 *
 *   This is more robust than depending on NODE_PATH because:
 *     - NODE_PATH can be overridden by per-job process.chdir()
 *     - npm install can produce nested package roots that NODE_PATH misses
 *     - Absolute-path require always works regardless of cwd
 *
 * Lifecycle:
 *   - Workers are spawned and killed by core/sandbox/node_worker_pool.py
 *   - SIGTERM / stdin close → graceful exit
 *   - One job at a time per worker; the Python pool round-robins between them
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const os   = require('os');
const readline = require('readline');

// ── Locate the sandbox module caches ────────────────────────────────────────
const SANDBOX_HOME = process.env.SANDBOX_DATA_DIR || path.join(os.homedir(), '.sandbox');
const PPTX_NM     = path.join(SANDBOX_HOME, 'pptx_cache', 'node_modules');
const DOCX_NM     = path.join(SANDBOX_HOME, 'docx_cache', 'node_modules');

/** Resolve a package directory robustly.
 *  Returns an absolute path to the package's entry-point that ``require`` can load.
 *  Falls back to bare ``require('pkg')`` (NODE_PATH / cwd resolution) if the
 *  absolute lookup fails.
 */
function safeRequire(pkgName, candidates) {
  for (const root of candidates) {
    const candidate = path.join(root, pkgName);
    if (fs.existsSync(candidate)) {
      try {
        return require(candidate);
      } catch (e) {
        process.stderr.write(`[worker] require('${candidate}') failed: ${e.message}\n`);
      }
    }
  }
  // Last resort — bare require. May work if NODE_PATH is set correctly OR if
  // we cd'd into a workdir that has node_modules/pkg symlinked locally.
  try {
    return require(pkgName);
  } catch (e) {
    throw new Error(
      `cannot resolve '${pkgName}' from any of:\n  ${candidates.join('\n  ')}\n` +
      `bare require also failed: ${e.message}`
    );
  }
}

// ── Lazy module loaders (V8 module cache → cheap after first call) ──────────
let _docxLib = null;
function getDocxLib(workdir) {
  if (_docxLib === null) {
    const localNM = workdir ? [path.join(workdir, 'node_modules')] : [];
    _docxLib = safeRequire('docx', [...localNM, DOCX_NM]);
  }
  return _docxLib;
}

let _pptxLib = null;
function getPptxLib(workdir) {
  if (_pptxLib === null) {
    const localNM = workdir ? [path.join(workdir, 'node_modules')] : [];
    _pptxLib = safeRequire('pptxgenjs', [...localNM, PPTX_NM]);
  }
  return _pptxLib;
}

// ── DOCX job handler ─────────────────────────────────────────────────────────
async function handleDocx(spec, workdir) {
  // Force docx to load NOW (cached after first job)
  getDocxLib(workdir);

  const builderPath = path.join(workdir, 'document_builder.js');
  if (!fs.existsSync(builderPath)) {
    throw new Error('document_builder.js missing from workdir');
  }
  const prevCwd = process.cwd();
  try {
    process.chdir(workdir);
    delete require.cache[require.resolve(builderPath)];
    await new Promise((resolve, reject) => {
      try { require(builderPath); } catch (e) { reject(e); return; }
      const outName = spec.filename || 'output.docx';
      const outPath = path.join(workdir, outName);
      const deadline = Date.now() + 90000;
      const tick = () => {
        if (fs.existsSync(outPath) && fs.statSync(outPath).size > 0) {
          resolve(outPath);
        } else if (Date.now() > deadline) {
          reject(new Error('docx generation timed out'));
        } else {
          setTimeout(tick, 50);
        }
      };
      tick();
    });
  } finally {
    process.chdir(prevCwd);
  }
  const outName = spec.filename || 'output.docx';
  return path.join(workdir, outName);
}

// ── PPTX job handler ─────────────────────────────────────────────────────────
async function handlePptx(spec, workdir) {
  // Force pptxgenjs to load NOW (cached after first job)
  getPptxLib(workdir);

  const runtimePath = path.join(workdir, 'js', 'runtime.js');
  if (!fs.existsSync(runtimePath)) {
    throw new Error('js/runtime.js missing from workdir');
  }
  const prevCwd = process.cwd();
  const prevArgv = process.argv.slice();
  try {
    process.chdir(workdir);
    process.argv = [process.argv[0], runtimePath, 'spec.json'];
    delete require.cache[require.resolve(runtimePath)];
    require(runtimePath);
    const outName = spec.filename || 'output.pptx';
    const outPath = path.join(workdir, outName);
    await new Promise((resolve, reject) => {
      const deadline = Date.now() + 180000;
      const tick = () => {
        if (fs.existsSync(outPath) && fs.statSync(outPath).size > 0) {
          resolve(outPath);
        } else if (Date.now() > deadline) {
          reject(new Error('pptx generation timed out'));
        } else {
          setTimeout(tick, 50);
        }
      };
      tick();
    });
    return outPath;
  } finally {
    process.chdir(prevCwd);
    process.argv = prevArgv;
  }
}

// ── Main NDJSON loop ─────────────────────────────────────────────────────────
const rl = readline.createInterface({ input: process.stdin });

process.stderr.write(`[worker ${process.pid}] ready (PPTX_NM=${PPTX_NM}, DOCX_NM=${DOCX_NM})\n`);

rl.on('line', async (line) => {
  if (!line.trim()) return;
  let req;
  try {
    req = JSON.parse(line);
  } catch (e) {
    process.stdout.write(JSON.stringify({ id: null, ok: false, error: 'invalid JSON: ' + e.message }) + '\n');
    return;
  }
  const { id, kind, spec, workdir } = req;
  const t0 = Date.now();
  try {
    let outfile;
    if (kind === 'docx') {
      outfile = await handleDocx(spec, workdir);
    } else if (kind === 'pptx') {
      outfile = await handlePptx(spec, workdir);
    } else {
      throw new Error('unknown kind: ' + kind);
    }
    process.stdout.write(JSON.stringify({
      id, ok: true, outfile, elapsed_ms: Date.now() - t0,
    }) + '\n');
  } catch (e) {
    process.stderr.write(`[worker ${process.pid}] job ${id} (${kind}) failed: ${e.message}\n`);
    process.stdout.write(JSON.stringify({
      id, ok: false, error: String(e && e.message || e), elapsed_ms: Date.now() - t0,
    }) + '\n');
  }
});

rl.on('close', () => {
  process.stderr.write(`[worker ${process.pid}] stdin closed, exiting\n`);
  process.exit(0);
});

process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT',  () => process.exit(0));
