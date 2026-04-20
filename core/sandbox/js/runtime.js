'use strict';
/**
 * Potomac PPTX Runtime Entry
 * ===========================
 * Loads a spec JSON (written by the Python side) and renders a .pptx.
 *
 * Spec schema
 * -----------
 *   {
 *     "title": "...",
 *     "filename": "output.pptx",
 *     "canvas": { "preset": "wide" }           // or { width, height }
 *     "slides": [
 *       { "mode": "template", "template": "hex_row", "data": {...}, "overrides": {...} },
 *       { "mode": "hybrid", "template": "content", "data": {...}, "customize": "..." },
 *       { "mode": "freestyle", "code": "..." },
 *       // legacy: { "type": "title", ...fields... }  → mapped to template mode
 *     ],
 *     "asset_registry": { "icon_globe_fist": { "dataUrl": "...", "aspect": 1 }, ... }
 *   }
 *
 * Emits:
 *   stdout:  JSON{"status":"ok","warnings":[...]} on success
 *   stderr:  WARN:... / ERROR:... lines
 *   exit 0 on success, non-zero on error.
 */

const fs   = require('fs');
const path = require('path');
const pptxgen = require('pptxgenjs');

const brand    = require('./brand');
const { createEngine }        = require('./layout-engine');
const { buildPrimitives }     = require('./primitives');
const { attachExtraPrimitives } = require('./primitives-extra');
const { buildTemplates }      = require('./templates');
const { buildExtraTemplates } = require('./templates-extra');
const { buildUniversityTemplates } = require('./templates-university');
const { resolveTheme, THEMES } = require('./themes');

// ── Load spec ────────────────────────────────────────────────────────────────
const specPath = process.argv[2] || 'spec.json';
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));

// ── Canvas / layout engine ───────────────────────────────────────────────────
const canvasOpts = spec.canvas || { preset: 'wide' };
const engine = createEngine(canvasOpts);

// ── Presentation ─────────────────────────────────────────────────────────────
const pres = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = spec.title || 'Potomac Presentation';

// CRITICAL: define layout explicitly by POTOMAC_CUSTOM name.  This prevents
// PptxGenJS from silently falling back to LAYOUT_STANDARD (10x7.5) on some
// versions, which was the cause of "slides render the wrong size".
pres.defineLayout({ name: 'POTOMAC_CUSTOM', width: engine.W, height: engine.H });
pres.layout = 'POTOMAC_CUSTOM';

// ── Assets (logos + user manifest) ───────────────────────────────────────────
const assetsDir = path.join(__dirname, '..', 'assets');     // set by Python before exec
const actualAssetsDir = fs.existsSync(assetsDir)
  ? assetsDir
  : path.join(process.cwd(), 'assets');

const logos = brand.loadLogos(actualAssetsDir);

// Asset registry from spec (each entry is { dataUrl, aspect, mime })
const assetRegistry = spec.asset_registry || {};
function resolveAsset(key) {
  if (!key) return null;
  const hit = assetRegistry[key];
  if (hit && hit.dataUrl) return hit;
  // Fallback — try loading from actualAssetsDir by simple convention
  const candidates = [`${key}.png`, `${key}.svg`, `${key}.jpg`];
  for (const f of candidates) {
    const a = brand.loadAsset(actualAssetsDir, f);
    if (a) return { dataUrl: a.dataUrl, aspect: 1 };
  }
  return null;
}

// ── Primitives + templates ───────────────────────────────────────────────────
let prim = buildPrimitives({ pres, engine, brand, logos, resolveAsset });
// Extend prim with arrow/ribbon/star/badge/… extras
prim = attachExtraPrimitives(prim, { pres, engine, brand });

// Core named templates (title, title_card, content, hex_row, …)
const core = buildTemplates({ pres, engine, prim, brand, logos, resolveAsset });

// Extra named templates (timeline, process, swot, funnel, roadmap, …)
const extra = buildExtraTemplates({
  pres, engine, prim, brand, themes: resolveTheme,
});

// University-pack templates (university_title, university_pennant, …)
const university = buildUniversityTemplates({
  pres, engine, prim, brand, resolveAsset,
});

// Merge registries — extras & university win on name collisions
const registry = Object.assign({}, core.registry, extra, university);
const templates = {
  registry,
  get(name) { return registry[name] || core.get('content'); },
};

// ── Warnings capture ─────────────────────────────────────────────────────────
const warnings = [];
const origWrite = process.stderr.write.bind(process.stderr);
process.stderr.write = (chunk, ...rest) => {
  const s = String(chunk);
  const lines = s.split('\n');
  for (const line of lines) {
    if (line.startsWith('WARN:')) warnings.push(line.slice(5).trim());
  }
  return origWrite(chunk, ...rest);
};

// ── Freestyle sandbox ────────────────────────────────────────────────────────
/**
 * Run user-provided JS code against an existing slide (or create one if the
 * code adds its own).  The code has access to: slide, pres, engine, prim,
 * brand (palette/fonts), logos, resolveAsset, data, and the `require` is
 * omitted to prevent arbitrary module loading.
 */
function runFreestyle(slide, code, data) {
  const {
    PALETTE, FONTS,
  } = brand;
  // eslint-disable-next-line no-new-func
  const fn = new Function(
    'slide', 'pres', 'engine', 'prim', 'data',
    'PALETTE', 'FONTS', 'logos', 'resolveAsset',
    '"use strict";\n' + code,
  );
  try {
    fn(slide, pres, engine, prim, data || {}, PALETTE, FONTS, logos, resolveAsset);
  } catch (err) {
    process.stderr.write(`WARN:freestyle_error ${err.message}\n`);
  }
}

// ── Legacy spec migration ────────────────────────────────────────────────────
/**
 * Old specs use `{type: "title", ...fields}` — convert to the new
 * `{mode: "template", template: "title", data: {...}}` form.
 */
function normalizeSlideSpec(s) {
  if (s && (s.mode === 'template' || s.mode === 'hybrid' || s.mode === 'freestyle')) return s;
  if (s && s.type) {
    return { mode: 'template', template: s.type, data: s };
  }
  return { mode: 'template', template: 'content', data: s || {} };
}

// ── Slide router ─────────────────────────────────────────────────────────────
for (const raw of (spec.slides || [])) {
  const n = normalizeSlideSpec(raw);
  try {
    if (n.mode === 'freestyle') {
      const slide = pres.addSlide();
      // Default background
      slide.background = { color: brand.PALETTE.WHITE };
      runFreestyle(slide, n.code || '', n.data);
      continue;
    }

    // template or hybrid
    const tmplName = n.template || (n.data && n.data.type) || 'content';
    const tmpl = templates.get(tmplName);
    const slide = pres.addSlide();
    const mergedData = n.overrides ? { ...n.data, ...n.overrides } : n.data;
    tmpl(slide, mergedData || {});

    if (n.mode === 'hybrid' && n.customize) {
      runFreestyle(slide, n.customize, mergedData);
    }
  } catch (err) {
    process.stderr.write(`WARN:slide[${n.template || n.mode}] ${err.message}\n`);
  }
}

// ── Write file ───────────────────────────────────────────────────────────────
const outName = spec.filename || 'output.pptx';
pres.writeFile({ fileName: outName })
  .then(() => {
    process.stdout.write(JSON.stringify({
      status: 'ok',
      filename: outName,
      canvas: { width: engine.W, height: engine.H },
      warnings,
    }) + '\n');
  })
  .catch(err => {
    process.stderr.write('ERROR:' + err.message + '\n');
    process.exit(1);
  });
