'use strict';
/**
 * Potomac PPTX Layout Engine
 * ===========================
 * A dynamic-measurement runtime for pptxgenjs.
 *
 * RULE #1 — NO HARDCODED MEASUREMENTS IN TEMPLATES.
 * Every position is expressed as:
 *   • a fraction of the canvas, OR
 *   • relative to a sibling element via stack / row cursors, OR
 *   • the output of grid.cell() / autoFit().
 *
 * All units are inches, matching pptxgenjs defaults.
 *
 * Canvas presets
 * --------------
 *   wide         : 13.333" × 7.5"   (16:9 widescreen — pptxgenjs default)
 *   standard     : 10"     × 7.5"   (4:3 legacy)
 *   hd16_9       : 10"     × 5.625" (legacy PowerPoint "HD" size — NOT the
 *                                    same as wide; use wide for new decks)
 *   a4_landscape : 11.69"  × 8.27"
 *   custom       : { width, height } passed directly to createEngine()
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
 * @param {{ preset?: string, width?: number, height?: number }} opts
 * @returns {LayoutEngine}
 */
function createEngine(opts = {}) {
  let W, H;

  if (opts.width && opts.height) {
    W = opts.width;
    H = opts.height;
  } else {
    const preset = CANVAS_PRESETS[opts.preset ?? 'wide'];
    if (!preset) {
      throw new Error(
        `Unknown preset "${opts.preset}". Valid options: ${Object.keys(CANVAS_PRESETS).join(', ')}`
      );
    }
    W = preset.width;
    H = preset.height;
  }

  // ── Tokens (plain values — W and H are immutable after engine creation) ───
  //
  // Expressed as fractions of canvas dimensions so they stay proportional
  // across presets. All values are in inches.

  const tokens = Object.freeze({
    marginH:   W * 0.0375,         // left/right margin  ≈ 0.50"
    marginV:   H * 0.040,          // top/bottom margin  ≈ 0.30"
    gutter:    Math.min(W, H) * 0.025,

    accentBarW: W * 0.011,
    ulineH:     H * 0.008,

    titleH:    H * 0.12,
    titleGap:  H * 0.025,

    logoW:     W * 0.135,
    logoH:     H * 0.090,
    logoIconW: Math.min(W, H) * 0.07,
    logoIconH: Math.min(W, H) * 0.07,

    flourishW: W * 0.09,
    flourishH: H * 0.19,
  });

  // ── Base rects ────────────────────────────────────────────────────────────

  /** Full slide rect. */
  const full = () => ({ x: 0, y: 0, w: W, h: H });

  /** Slide rect inset by marginH / marginV. */
  const content = () => ({
    x: tokens.marginH,
    y: tokens.marginV,
    w: W - tokens.marginH * 2,
    h: H - tokens.marginV * 2,
  });

  /**
   * Body area below a title block.
   *
   * @param {{ titleH?: number, ulineH?: number, titleGap?: number }} [chrome]
   *   Override any chrome token. Defaults to tokens.titleH / ulineH / titleGap.
   *   Pass zeroes for slides whose header has no underline, etc.
   */
  const bodyAfterTitle = ({
    titleH  = tokens.titleH,
    ulineH  = tokens.ulineH,
    titleGap = tokens.titleGap,
  } = {}) => {
    const c = content();
    const headH = titleH + ulineH + titleGap;
    return { x: c.x, y: c.y + headH, w: c.w, h: c.h - headH };
  };

  // ── Grid ──────────────────────────────────────────────────────────────────

  /**
   * Divide an area into a cols × rows grid.
   *
   * @param {number} cols
   * @param {number} rows
   * @param {Rect}   [area]  defaults to content()
   * @param {number} [gap]   defaults to tokens.gutter
   */
  const grid = (cols, rows, area, gap) => {
    const a = area ?? content();
    const g = gap  ?? tokens.gutter;
    const cellW = (a.w - g * (cols - 1)) / cols;
    const cellH = (a.h - g * (rows - 1)) / rows;

    return {
      cellW, cellH, cols, rows, area: a, gap: g,

      /** Rect for cell (col, row) with optional span. */
      cell: (c, r, { colSpan = 1, rowSpan = 1 } = {}) => ({
        x: a.x + c * (cellW + g),
        y: a.y + r * (cellH + g),
        w: cellW * colSpan + g * (colSpan - 1),
        h: cellH * rowSpan + g * (rowSpan - 1),
      }),

      /** Full-width rect for row r with optional rowSpan. */
      row: (r, { rowSpan = 1 } = {}) => ({
        x: a.x,
        y: a.y + r * (cellH + g),
        w: a.w,
        h: cellH * rowSpan + g * (rowSpan - 1),
      }),

      /** Full-height rect for column c with optional colSpan. */
      col: (c, { colSpan = 1 } = {}) => ({
        x: a.x + c * (cellW + g),
        y: a.y,
        w: cellW * colSpan + g * (colSpan - 1),
        h: a.h,
      }),
    };
  };

  // ── Vertical stack ────────────────────────────────────────────────────────

  /**
   * Track a y-cursor and place elements top-down.
   *
   * @param {{ x?: number, y?: number, w?: number, gap?: number }} opts
   *
   * @example
   *   const s = stack({ x: marginH, y: marginV, w: W - marginH * 2 });
   *   const titleBox = s.place(tokens.titleH);
   *   const bodyBox  = s.place(s.remaining(H - marginV));
   */
  const stack = ({ x = 0, y = 0, w = W, gap } = {}) => {
    const g = gap ?? tokens.gutter;
    let cursor = y;

    return {
      /** Place a box of height h and advance the cursor. */
      place(h) {
        const box = { x, y: cursor, w, h };
        cursor += h + g;
        return box;
      },
      /** Advance the cursor without producing a box. */
      skip(h) { cursor += h; },
      /** Current cursor position. */
      get cursor() { return cursor; },
      /** Remaining height between the cursor and maxY. */
      remaining(maxY) { return Math.max(0, maxY - cursor); },
    };
  };

  // ── Horizontal row ────────────────────────────────────────────────────────

  /**
   * Track an x-cursor and place elements left-to-right.
   *
   * @param {{ x?: number, y?: number, h?: number, gap?: number }} opts
   *
   * h is required for the boxes to be complete rects; it defaults to 0
   * so callers that compute h separately (and spread the result) don't error.
   */
  const rowBuilder = ({ x = 0, y = 0, h = 0, gap } = {}) => {
    const g = gap ?? tokens.gutter;
    let cursor = x;

    return {
      /** Place a box of width w and advance the cursor. */
      place(w) {
        const box = { x: cursor, y, w, h };
        cursor += w + g;
        return box;
      },
      /** Advance the cursor without producing a box. */
      skip(w) { cursor += w; },
      /** Current cursor position. */
      get cursor() { return cursor; },
      /** Remaining width between the cursor and maxX. */
      remaining(maxX) { return Math.max(0, maxX - cursor); },
    };
  };

  // ── Text metrics ──────────────────────────────────────────────────────────

  /**
   * Approximate glyph-width ratios (average advance / em) per face.
   * PptxGenJS has no exact metrics at author-time; these are conservative
   * averages tuned for the Potomac type system.
   *
   * Note: pptxgenjs supports fit:'shrink' and fit:'resize' on addText() for
   * cases where you just need text not to overflow and don't need to know the
   * resulting pt size at author-time. Use autoFit() when you need that size
   * for positioning or other downstream calculations.
   */
  const FONT_WIDTH_RATIO = Object.freeze({
    Rajdhani:  0.48,   // condensed display
    Quicksand: 0.54,   // rounded humanist sans
    Arial:     0.55,
    Consolas:  0.60,
  });

  const ptToInch = (pt) => pt / 72;

  /**
   * Estimate wrapped-text layout inside a box.
   *
   * @param {string} text
   * @param {number} pt        Font size in points
   * @param {number} boxW      Available width in inches
   * @param {{ fontFace?: string, lineHeight?: number }} [opts]
   * @returns {{ lines: number, totalH: number, lineH: number,
   *             charW: number, maxCharsPerLine: number, overflow: number }}
   *
   * `overflow` is the excess height beyond boxH (pass boxH to get it).
   */
  const measureText = (text, pt, boxW, {
    fontFace   = 'Quicksand',
    lineHeight = 1.2,
    boxH       = Infinity,
  } = {}) => {
    const s = String(text ?? '');
    if (!s) return { lines: 0, totalH: 0, lineH: 0, charW: 0, maxCharsPerLine: 0, overflow: 0 };

    const ratio          = FONT_WIDTH_RATIO[fontFace] ?? 0.55;
    const charW          = ptToInch(pt) * ratio;
    const maxCharsPerLine = Math.max(1, Math.floor(boxW / charW));
    const lineH          = ptToInch(pt) * lineHeight;

    let lines = 0;
    for (const para of s.split('\n')) {
      lines += para.length === 0 ? 1 : Math.ceil(para.length / maxCharsPerLine);
    }

    const totalH   = lines * lineH;
    const overflow = Math.max(0, totalH - boxH);
    return { lines, totalH, lineH, charW, maxCharsPerLine, overflow };
  };

  /**
   * Binary-search for the largest pt size that fits text inside box.
   *
   * @param {string} text
   * @param {{ w: number, h: number }} box
   * @param {{ minPt?: number, maxPt?: number, fontFace?: string, lineHeight?: number }} [opts]
   * @returns {{ pt: number, lines: number, totalH: number, lineH: number,
   *             charW: number, maxCharsPerLine: number, overflow: number }}
   */
  const autoFit = (text, box, {
    minPt      = 10,
    maxPt      = 48,
    fontFace   = 'Quicksand',
    lineHeight = 1.2,
  } = {}) => {
    let lo = minPt, hi = maxPt, best = minPt;

    for (let i = 0; i < 20 && lo <= hi; i++) {
      const mid = Math.floor((lo + hi) / 2);
      const m   = measureText(text, mid, box.w, { fontFace, lineHeight, boxH: box.h });
      if (m.totalH <= box.h) { best = mid; lo = mid + 1; }
      else                   { hi = mid - 1; }
    }

    return { pt: best, ...measureText(text, best, box.w, { fontFace, lineHeight, boxH: box.h }) };
  };

  // ── Geometry helpers ──────────────────────────────────────────────────────

  /**
   * Scale an aspect-ratio object to the largest size that fits in maxW × maxH.
   *
   * @param {number} aspect  width / height
   * @param {number} maxW
   * @param {number} maxH
   * @returns {{ w: number, h: number }}
   */
  const fitAspect = (aspect, maxW, maxH) => {
    if (maxW / maxH > aspect) {
      return { w: maxH * aspect, h: maxH };
    }
    return { w: maxW, h: maxW / aspect };
  };

  /**
   * Center a sub-rect (w, h) inside an area.
   *
   * @param {{ x: number, y: number, w: number, h: number }} area
   * @param {number} w
   * @param {number} h
   * @returns {{ x: number, y: number, w: number, h: number }}
   */
  const centerIn = (area, w, h) => ({
    x: area.x + (area.w - w) / 2,
    y: area.y + (area.h - h) / 2,
    w,
    h,
  });

  /**
   * Clamp a box so it stays within the slide canvas.
   * pptxgenjs does not throw on out-of-bounds geometry — it silently clips or
   * misplaces the element. This guard surfaces the problem early.
   *
   * @param {{ x: number, y: number, w: number, h: number }} box
   * @returns {{ box: Rect, clipped: boolean, warning: string | null }}
   */
  const clampBox = (box) => {
    const b = { ...box };
    let clipped = false, warning = null;

    if (b.x < 0)           { b.w += b.x; b.x = 0;           clipped = true; warning = 'x underflows canvas'; }
    if (b.y < 0)           { b.h += b.y; b.y = 0;           clipped = true; warning = 'y underflows canvas'; }
    if (b.x + b.w > W)     { b.w = Math.max(0.01, W - b.x); clipped = true; warning = 'x+w overflows canvas width'; }
    if (b.y + b.h > H)     { b.h = Math.max(0.01, H - b.y); clipped = true; warning = 'y+h overflows canvas height'; }

    return { box: b, clipped, warning };
  };

  // ── Public API ────────────────────────────────────────────────────────────

  return Object.freeze({
    /** Canvas width in inches. */
    W,
    /** Canvas height in inches. */
    H,
    /** Canvas dimensions as a rect origin at (0, 0). */
    canvas: Object.freeze({ w: W, h: H }),

    tokens,

    rects: Object.freeze({ full, content, bodyAfterTitle }),

    grid,
    stack,
    row: rowBuilder,

    measureText,
    autoFit,
    fitAspect,
    centerIn,
    clampBox,
  });
}

module.exports = { createEngine, CANVAS_PRESETS };