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
 * Why this exists:
 *   Spawning a new Node process + ``require("pptxgenjs")`` per generation
 *   costs ~800-2500 ms. Keeping pptxgenjs + docx require'd in memory and
 *   reusing the same Node process drops it to ~150-400 ms.
 *
 * Lifecycle:
 *   - Workers are spawned and killed by core/sandbox/node_worker_pool.py
 *   - SIGTERM / stdin close → graceful exit
 *   - One job at a time per worker; the Python pool round-robins between them
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const readline = require('readline');

// ── Lazy-loaded modules (paid once at worker startup) ────────────────────────
let _docxLib = null;
function getDocxLib() {
  if (_docxLib === null) {
    _docxLib = require('docx');
  }
  return _docxLib;
}

let _pptxLib = null;
function getPptxLib() {
  if (_pptxLib === null) {
    _pptxLib = require('pptxgenjs');
  }
  return _pptxLib;
}

// ── DOCX job handler ─────────────────────────────────────────────────────────
async function handleDocx(spec, workdir) {
  // The full builder script lives inside the workdir on disk; we require it
  // dynamically. It pulls in the `docx` library lazily through getDocxLib()
  // by reading from node_modules (which is symlinked into workdir).
  const builderPath = path.join(workdir, 'document_builder.js');
  if (!fs.existsSync(builderPath)) {
    throw new Error('document_builder.js missing from workdir');
  }
  // Set cwd so the builder reads spec.json + assets/ correctly.
  const prevCwd = process.cwd();
  try {
    process.chdir(workdir);
    // Clear require cache so each invocation gets a fresh builder run.
    delete require.cache[require.resolve(builderPath)];
    // The builder is async (uses Packer.toBuffer().then) — wait for the
    // output file to exist. We poll because the builder writes its own
    // exit-style messages to stdout/stderr.
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
  // Delegate to the existing runtime.js in workdir/js/ — it expects the spec
  // to live at workdir/spec.json (already written by the Python side).
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
    // runtime.js writes the output file synchronously inside its top-level
    // async function and prints a JSON ack to stdout. Run it and wait for
    // the output .pptx to appear.
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

// Warm modules so the first job is also fast.
try { getDocxLib(); } catch (e) { /* ignore — docx may not be installed yet */ }
try { getPptxLib(); } catch (e) { /* ignore — pptxgenjs may not be installed yet */ }

process.stderr.write(`[worker ${process.pid}] ready\n`);

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
