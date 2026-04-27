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
 * code adds its own).
 *
 * Variables available inside the user's `code` string
 * ----------------------------------------------------
 *   slide, pres, engine, prim, data, resolveAsset
 *   PALETTE, FONTS                         (brand objects)
 *   YELLOW, DARK_GRAY, WHITE, BLACK        (palette shortcuts)
 *   GRAY_60, GRAY_40, GRAY_20, GRAY_10, GRAY_05
 *   YELLOW_80, YELLOW_20, YELLOW_10
 *   GREEN, RED, BLUE
 *   FONT_H  (= 'Rajdhani')    FONT_B  (= 'Quicksand')    FONT_M  (= 'Consolas')
 *   logos   (raw registry)
 *   LOGOS   (same registry + shorthand aliases: .black, .white, .yellow)
 *   addLogo(slide, x, y, w, h, variant='full')
 */
function runFreestyle(slide, code, data) {
  const { PALETTE, FONTS } = brand;

  // ── Individual palette constants ────────────────────────────────────────
  const YELLOW    = PALETTE.YELLOW;
  const DARK_GRAY = PALETTE.DARK_GRAY;
  const WHITE     = PALETTE.WHITE;
  const BLACK     = PALETTE.BLACK;
  const GRAY_60   = PALETTE.GRAY_60;
  const GRAY_40   = PALETTE.GRAY_40;
  const GRAY_20   = PALETTE.GRAY_20;
  const GRAY_10   = PALETTE.GRAY_10;
  const GRAY_05   = PALETTE.GRAY_05;
  const YELLOW_80 = PALETTE.YELLOW_80;
  const YELLOW_20 = PALETTE.YELLOW_20;
  const YELLOW_10 = PALETTE.YELLOW_10;
  const GREEN     = PALETTE.GREEN;
  const RED       = PALETTE.RED;
  const BLUE      = PALETTE.BLUE;

  // ── Font shorthands ─────────────────────────────────────────────────────
  const FONT_H = FONTS.HEADLINE;  // 'Rajdhani'
  const FONT_B = FONTS.BODY;      // 'Quicksand'
  const FONT_M = FONTS.MONO;      // 'Consolas'

  // ── Logo registry with convenience aliases ───────────────────────────────
  // The full logos object has keys: full, full_black, full_white, icon,
  // icon_black, icon_white, icon_yellow.  We also expose short aliases
  // (.black, .white, .yellow) so both naming styles work.
  const LOGOS = Object.assign({}, logos, {
    black:  logos.full_black  || logos.icon_black  || null,
    white:  logos.full_white  || logos.icon_white  || null,
    yellow: logos.icon_yellow || null,
  });

  // ── addLogo helper ───────────────────────────────────────────────────────
  // Mirrors prim.placeLogo() — uses the real PNG-measured aspect ratio so the
  // logo is NEVER stretched.  `w` and `h` define the bounding box; the image
  // is scaled to fit inside while preserving its aspect ratio and centred.
  function addLogo(s, x, y, w, h, variant) {
    const v = variant || 'full';
    const entry = LOGOS[v] || LOGOS['full'];
    if (!entry || !entry.dataUrl) return;

    // Real aspect ratio from PNG header (brand.loadLogos measures it).
    // Fall back to the LOGO_ASPECTS table, then to a safe wide default.
    const aspect = entry.aspect
      || brand.LOGO_ASPECTS[v]
      || brand.LOGO_ASPECTS['full']
      || 4.875;

    // Fit the logo inside the bounding box without stretching.
    let displayW, displayH;
    if (w / h >= aspect) {
      // Box is wider than the logo — constrain by height.
      displayH = h;
      displayW = h * aspect;
    } else {
      // Box is taller (relative to logo) — constrain by width.
      displayW = w;
      displayH = w / aspect;
    }

    // Centre within the caller's bounding box.
    const offsetX = (w - displayW) / 2;
    const offsetY = (h - displayH) / 2;

    s.addImage({
      data: entry.dataUrl,
      x:    x + offsetX,
      y:    y + offsetY,
      w:    displayW,
      h:    displayH,
    });
  }

  // eslint-disable-next-line no-new-func
  const fn = new Function(
    // core context
    'slide', 'pres', 'engine', 'prim', 'data', 'resolveAsset',
    // brand objects
    'PALETTE', 'FONTS',
    // palette constants
    'YELLOW', 'DARK_GRAY', 'WHITE', 'BLACK',
    'GRAY_60', 'GRAY_40', 'GRAY_20', 'GRAY_10', 'GRAY_05',
    'YELLOW_80', 'YELLOW_20', 'YELLOW_10',
    'GREEN', 'RED', 'BLUE',
    // font shorthands
    'FONT_H', 'FONT_B', 'FONT_M',
    // logo helpers
    'logos', 'LOGOS', 'addLogo',
    '"use strict";\n' + code,
  );
  try {
    fn(
      // core context
      slide, pres, engine, prim, data || {}, resolveAsset,
      // brand objects
      PALETTE, FONTS,
      // palette constants
      YELLOW, DARK_GRAY, WHITE, BLACK,
      GRAY_60, GRAY_40, GRAY_20, GRAY_10, GRAY_05,
      YELLOW_80, YELLOW_20, YELLOW_10,
      GREEN, RED, BLUE,
      // font shorthands
      FONT_H, FONT_B, FONT_M,
      // logo helpers
      logos, LOGOS, addLogo,
    );
  } catch (err) {
    process.stderr.write(`WARN:freestyle_error ${err.stack || err.message}\n`);
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
  // Declare slide outside try so the catch block can render an error
  // placeholder instead of leaving a blank slide in the presentation.
  let slide = null;
  try {
    if (n.mode === 'freestyle') {
      slide = pres.addSlide();
      // Default background
      slide.background = { color: brand.PALETTE.WHITE };
      runFreestyle(slide, n.code || '', n.data);
      continue;
    }

    // template or hybrid
    const tmplName = n.template || (n.data && n.data.type) || 'content';
    const tmpl = templates.get(tmplName);
    slide = pres.addSlide();
    const mergedData = n.overrides ? { ...n.data, ...n.overrides } : n.data;
    tmpl(slide, mergedData || {});

    if (n.mode === 'hybrid' && n.customize) {
      runFreestyle(slide, n.customize, mergedData);
    }
  } catch (err) {
    const label = n.template || n.mode || 'unknown';
    process.stderr.write(`WARN:slide[${label}] ${err.message}\n`);
    // The slide was already added — render a visible error placeholder so the
    // deck is never silently blank.  This makes the problem obvious to the user
    // rather than producing a mystery empty slide.
    if (slide) {
      try {
        slide.background = { color: brand.PALETTE.WHITE };
        slide.addText(
          `⚠ Slide rendering error [${label}]:\n${err.message}`,
          {
            x: 0.5, y: engine.H / 2 - 0.75,
            w: engine.W - 1.0, h: 1.5,
            fontSize: 14, bold: false,
            color: brand.PALETTE.DARK_GRAY,
            fontFace: brand.FONTS.BODY,
            align: 'center', valign: 'middle',
            wrap: true,
          }
        );
      } catch (_) { /* best-effort */ }
    }
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
