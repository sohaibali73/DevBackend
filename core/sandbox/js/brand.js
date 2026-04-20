'use strict';
/**
 * Potomac brand constants.
 *
 * Contains the brand palette, fonts, and logo registry.
 * No measurements — layout math lives in layout-engine.js so any slide
 * size (wide, standard, custom) can be used without rewriting this file.
 */

const fs   = require('fs');
const path = require('path');

// ── Palette ──────────────────────────────────────────────────────────────────
const PALETTE = Object.freeze({
  YELLOW:    'FEC00F',
  DARK_GRAY: '212121',
  WHITE:     'FFFFFF',
  BLACK:     '000000',
  GRAY_60:   '999999',
  GRAY_40:   'CCCCCC',
  GRAY_20:   'DDDDDD',
  GRAY_10:   'F0F0F0',
  GRAY_05:   'F8F8F8',
  YELLOW_80: 'FDD251',
  YELLOW_20: 'FEF7D8',
  YELLOW_10: 'FFFBEB',
  GREEN:     '22C55E',
  RED:       'EB2F5C',
  BLUE:      '3B82F6',
});

// ── Fonts ────────────────────────────────────────────────────────────────────
const FONTS = Object.freeze({
  HEADLINE: 'Rajdhani',   // ALL CAPS brand font
  BODY:     'Quicksand',  // body / caption
  MONO:     'Consolas',
});

// ── Logo variants and aspect ratios ──────────────────────────────────────────
// These are the FALLBACK aspect ratios used when a logo file cannot be
// measured at runtime.  The real aspect is computed from the PNG's actual
// pixel dimensions in loadLogos() below — that's what callers (placeLogo,
// fitAspect) should use to avoid stretching.
//
// Canonical source values (from ClaudeSkills/potomac-pptx/brand-assets/logos):
//   potomac-full-logo.png        1416 × 297  → 4.768
//   potomac-full-logo-black.png  1253 × 257  → 4.875
//   potomac-full-logo-white.png  1253 × 257  → 4.875
//   potomac-icon-black.png        550 × 555  → 0.991
//   potomac-icon-white.png       1673 × 1688 → 0.991
//   potomac-icon-yellow.png       533 × 538  → 0.991
const LOGO_ASPECTS = Object.freeze({
  full:       4.768,
  full_black: 4.875,
  full_white: 4.875,
  icon:       0.991,
  icon_black: 0.991,
  icon_white: 0.991,
  icon_yellow:0.991,
});

/** File-name map → absolute path is resolved at runtime from assetsDir */
const LOGO_FILES = Object.freeze({
  full:        'potomac-full-logo.png',
  full_black:  'potomac-full-logo-black.png',
  full_white:  'potomac-full-logo-white.png',
  icon:        'potomac-icon-black.png',    // default icon = black
  icon_black:  'potomac-icon-black.png',
  icon_white:  'potomac-icon-white.png',
  icon_yellow: 'potomac-icon-yellow.png',
});

/**
 * Minimal PNG header parser.
 * PNG files begin with an 8-byte signature, followed by an IHDR chunk whose
 * first 8 bytes after the "IHDR" tag are width (BE uint32) + height (BE uint32).
 * We read those to compute the real aspect ratio so the logo never stretches.
 */
function _pngDimensions(buffer) {
  try {
    // signature at 0..7, then length(4) + "IHDR"(4), then width@16, height@20
    if (buffer.length < 24) return null;
    if (buffer.toString('ascii', 12, 16) !== 'IHDR') return null;
    const w = buffer.readUInt32BE(16);
    const h = buffer.readUInt32BE(20);
    if (!w || !h) return null;
    return { w, h };
  } catch (_) { return null; }
}

/**
 * Build a logo registry by scanning an assets directory.  The aspect ratio
 * is measured from the PNG file itself (no stretching), falling back to the
 * LOGO_ASPECTS table if the file can't be parsed.
 *
 * @param {string} assetsDir  absolute path
 * @returns {Object<string,{dataUrl:string, aspect:number, px:{w,h}|null}>}
 */
function loadLogos(assetsDir) {
  const out = {};
  for (const [variant, filename] of Object.entries(LOGO_FILES)) {
    const p = path.join(assetsDir, filename);
    if (!fs.existsSync(p)) continue;
    const buf = fs.readFileSync(p);
    const dim = _pngDimensions(buf);
    const aspect = dim ? (dim.w / dim.h) : LOGO_ASPECTS[variant];
    out[variant] = {
      dataUrl: 'data:image/png;base64,' + buf.toString('base64'),
      aspect,
      px: dim,
    };
  }
  return out;
}

/**
 * Load an arbitrary named asset (icon / graphic / background) from assetsDir.
 *
 * Supports PNG, JPG, SVG.  Returns null when the file is absent.
 */
function loadAsset(assetsDir, filename) {
  try {
    const p = path.join(assetsDir, filename);
    if (!fs.existsSync(p)) return null;
    const ext = path.extname(filename).toLowerCase();
    const mime = ext === '.svg' ? 'image/svg+xml'
              : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg'
              : ext === '.gif' ? 'image/gif'
              : 'image/png';
    const data = fs.readFileSync(p);
    return {
      dataUrl: `data:${mime};base64,${data.toString('base64')}`,
      mime,
      bytes: data.length,
    };
  } catch (_) { return null; }
}

module.exports = {
  PALETTE,
  FONTS,
  LOGO_ASPECTS,
  LOGO_FILES,
  loadLogos,
  loadAsset,
};
