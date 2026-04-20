'use strict';
/**
 * Potomac PPTX Layout Engine
 * ===========================
 * A tiny dynamic-measurement runtime for pptxgenjs.
 *
 * RULE #1 — NO HARDCODED MEASUREMENTS ANYWHERE IN TEMPLATES.
 * Every position is expressed as:
 *   • a fraction of the canvas, OR
 *   • relative to a sibling element (stack cursor), OR
 *   • the output of `grid.cell()` / `autoFit()`.
 *
 * Canvas presets
 * --------------
 *   wide         : 13.333" × 7.5"   (16:9 widescreen — default)
 *   standard     : 10"     × 7.5"   (4:3 legacy)
 *   hd16_9       : 10"     × 5.625" (16:9 HD)
 *   a4_landscape : 11.69"  × 8.27"
 *   custom       : { width, height } provided by caller
 */

const CANVAS_PRESETS = Object.freeze({
  wide:         { width: 13.333, height: 7.5   },
  standard:     { width: 10.0,   height: 7.5   },
  hd16_9:       { width: 10.0,   height: 5.625 },
  a4_landscape: { width: 11.69,  height: 8.27  },
});

/**
 * Build a layout engine for a given canvas.
 *
 * @param {{preset?:string,width?:number,height?:number}} opts
 */
function createEngine(opts = {}) {
  let width, height;
  if (opts.width && opts.height) {
    width = opts.width; height = opts.height;
  } else {
    const preset = CANVAS_PRESETS[opts.preset || 'wide'];
    width = preset.width; height = preset.height;
  }

  const W = width, H = height;

  // ── Tokens (derived scalars) ──────────────────────────────────────────────
  const tokens = {
    // margins
    marginH: () => W * 0.0375,       // left/right ≈ 0.5"
    marginV: () => H * 0.04,         // top/bottom ≈ 0.3"
    gutter:  () => Math.min(W, H) * 0.025,

    // chrome
    accentBarW: () => W * 0.011,
    ulineH:     () => H * 0.008,

    // title
    titleH:     () => H * 0.12,
    titleGap:   () => H * 0.025,

    // logo
    logoW:      () => W * 0.135,
    logoH:      () => H * 0.09,
    logoIconW:  () => Math.min(W, H) * 0.07,
    logoIconH:  () => Math.min(W, H) * 0.07,

    // corner flourish (e.g. dashed-arc graphic in top-right)
    flourishW:  () => W * 0.09,
    flourishH:  () => H * 0.19,
  };

  // ── Rects ─────────────────────────────────────────────────────────────────
  const full = () => ({ x: 0, y: 0, w: W, h: H });
  const content = () => {
    const mh = tokens.marginH(), mv = tokens.marginV();
    return { x: mh, y: mv, w: W - mh * 2, h: H - mv * 2 };
  };
  const bodyAfterTitle = () => {
    const c = content();
    const head = tokens.titleH() + tokens.ulineH() + tokens.titleGap();
    return { x: c.x, y: c.y + head, w: c.w, h: c.h - head };
  };

  // ── Grid (cols × rows inside an area) ─────────────────────────────────────
  /**
   * @param {number} cols
   * @param {number} rows
   * @param {object} [area] defaults to content()
   * @param {number} [gap]  defaults to tokens.gutter()
   */
  const grid = (cols, rows, area, gap) => {
    const a = area || content();
    const g = gap !== undefined ? gap : tokens.gutter();
    const cellW = (a.w - g * (cols - 1)) / cols;
    const cellH = (a.h - g * (rows - 1)) / rows;
    return {
      cellW, cellH, cols, rows, area: a, gap: g,
      /**
       * Return the rect for cell (c, r) with optional span.
       */
      cell: (c, r, { colSpan = 1, rowSpan = 1 } = {}) => ({
        x: a.x + c * (cellW + g),
        y: a.y + r * (cellH + g),
        w: cellW * colSpan + g * (colSpan - 1),
        h: cellH * rowSpan + g * (rowSpan - 1),
      }),
      /** Row rect across all columns */
      row: (r, { rowSpan = 1 } = {}) => ({
        x: a.x,
        y: a.y + r * (cellH + g),
        w: a.w,
        h: cellH * rowSpan + g * (rowSpan - 1),
      }),
      /** Column rect across all rows */
      col: (c, { colSpan = 1 } = {}) => ({
        x: a.x + c * (cellW + g),
        y: a.y,
        w: cellW * colSpan + g * (colSpan - 1),
        h: a.h,
      }),
    };
  };

  // ── Vertical stack (places elements top-down) ─────────────────────────────
  /**
   * Create a stack that tracks a y-cursor.
   *
   *   const s = stack({ y: 1, x: 0.5, w: 12 });
   *   const titleBox = s.place(0.9);        // 0.9" tall
   *   const bodyBox  = s.place('auto', h);  // compute height from remaining
   */
  const stack = ({ x = 0, y = 0, w = W, gap } = {}) => {
    const g = gap !== undefined ? gap : tokens.gutter();
    let cursor = y;
    return {
      place(h) {
        const box = { x, y: cursor, w, h };
        cursor += h + g;
        return box;
      },
      skip(h) { cursor += h; },
      cursor() { return cursor; },
      remaining(maxY) { return Math.max(0, maxY - cursor); },
    };
  };

  // ── Horizontal row (places elements left-to-right) ────────────────────────
  const row = ({ x = 0, y = 0, h, gap } = {}) => {
    const g = gap !== undefined ? gap : tokens.gutter();
    let cursor = x;
    return {
      place(w) {
        const box = { x: cursor, y, w, h };
        cursor += w + g;
        return box;
      },
      skip(w) { cursor += w; },
      cursor() { return cursor; },
    };
  };

  // ── Text metrics & auto-fit ───────────────────────────────────────────────
  /**
   * Rough character-width estimator.  PptxGenJS has no exact metrics at
   * author-time; this is a conservative average that works for Rajdhani
   * (condensed) and Quicksand (humanist sans).
   *
   * One point = 1/72 inch.  Ratio is an avg (width / em) per font.
   */
  const FONT_WIDTH_RATIO = {
    Rajdhani:   0.48,   // condensed
    Quicksand:  0.54,   // rounded sans
    Arial:      0.55,
    Consolas:   0.60,
  };

  const ptToInch = (pt) => pt / 72;

  /**
   * Estimate wrapped-text layout inside a box.
   * Returns {lines, totalH, overflow} where overflow > 0 if clipped.
   */
  const measureText = (text, pt, boxW, {
    fontFace = 'Quicksand',
    lineHeight = 1.2,
  } = {}) => {
    const s = String(text || '');
    if (!s) return { lines: 0, totalH: 0, overflow: 0 };
    const ratio = FONT_WIDTH_RATIO[fontFace] || 0.55;
    const charW = ptToInch(pt) * ratio;
    const maxCharsPerLine = Math.max(1, Math.floor(boxW / charW));
    const paragraphs = s.split(/\n/);
    let lines = 0;
    for (const para of paragraphs) {
      if (!para.length) { lines += 1; continue; }
      lines += Math.max(1, Math.ceil(para.length / maxCharsPerLine));
    }
    const lineH = ptToInch(pt) * lineHeight;
    return { lines, totalH: lines * lineH, lineH, charW, maxCharsPerLine };
  };

  /**
   * Pick the largest pt size that fits `text` inside `box` without clipping.
   * Binary-searches [minPt, maxPt]. Returns { pt, lines, totalH }.
   */
  const autoFit = (text, box, {
    minPt = 10,
    maxPt = 48,
    fontFace = 'Quicksand',
    lineHeight = 1.2,
  } = {}) => {
    let lo = minPt, hi = maxPt, best = minPt, bestMeas = null;
    // ensure at least one iteration even if maxPt<=minPt
    for (let i = 0; i < 20 && lo <= hi; i++) {
      const mid = Math.floor((lo + hi) / 2);
      const m = measureText(text, mid, box.w, { fontFace, lineHeight });
      if (m.totalH <= box.h) {
        best = mid;
        bestMeas = m;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (!bestMeas) bestMeas = measureText(text, best, box.w, { fontFace, lineHeight });
    return { pt: best, ...bestMeas };
  };

  /**
   * Fit an arbitrary aspect-ratio object into a bounding box.
   */
  const fitAspect = (aspect, maxW, maxH) => {
    if (maxW / maxH > aspect) {
      const h = maxH;
      return { w: h * aspect, h };
    }
    const w = maxW;
    return { w, h: w / aspect };
  };

  /** Clamp a box inside the slide.  Returns {box, clipped:bool, warning:string|null} */
  const clampBox = (box) => {
    const b = { ...box };
    let clipped = false, warning = null;
    if (b.x < 0)         { b.w += b.x; b.x = 0;            clipped = true; warning = 'x<0'; }
    if (b.y < 0)         { b.h += b.y; b.y = 0;            clipped = true; warning = 'y<0'; }
    if (b.x + b.w > W)   { b.w = Math.max(0.01, W - b.x);  clipped = true; warning = 'x+w>W'; }
    if (b.y + b.h > H)   { b.h = Math.max(0.01, H - b.y);  clipped = true; warning = 'y+h>H'; }
    return { box: b, clipped, warning };
  };

  /**
   * Center a sub-rect (w,h) inside the given area.
   */
  const centerIn = (area, w, h) => ({
    x: area.x + (area.w - w) / 2,
    y: area.y + (area.h - h) / 2,
    w, h,
  });

  return {
    W, H,
    canvas: { w: W, h: H },
    tokens,
    rects: { full, content, bodyAfterTitle },
    grid,
    stack,
    row,
    measureText,
    autoFit,
    fitAspect,
    clampBox,
    centerIn,
  };
}

module.exports = { createEngine, CANVAS_PRESETS };
