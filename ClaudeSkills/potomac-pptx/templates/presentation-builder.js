/**
 * Potomac Presentation Builder
 *
 * All slide geometry is derived from SLIDE_W and SLIDE_H at runtime —
 * zero hardcoded pixel / inch values for layout math.
 *
 * Default layout: LAYOUT_WIDE (13.3" × 7.5")
 */

"use strict";

const pptxgen = require("pptxgenjs");
const path    = require("path");
const fs      = require("fs");

// ---------------------------------------------------------------------------
// Shape and chart type constants — resolved from the module (constructor),
// not from a pres instance, so behaviour is consistent across pptxgenjs
// versions that may not expose these enums on instances.
// ---------------------------------------------------------------------------
const PPTX_SHAPES = pptxgen.shapes ?? pptxgen.ShapeType;
const PPTX_CHARTS = pptxgen.charts ?? pptxgen.ChartType;

// ---------------------------------------------------------------------------
// Layout registry — add new layouts here; everything else adapts automatically
// ---------------------------------------------------------------------------
const LAYOUTS = {
  LAYOUT_WIDE:  { w: 13.3, h: 7.5 },
  LAYOUT_16x9:  { w: 10.0, h: 5.625 },
  LAYOUT_16x10: { w: 10.0, h: 6.25 },
  LAYOUT_4x3:   { w: 10.0, h: 7.5 },
};

// ---------------------------------------------------------------------------
// Font — Calibri is the brand font but is Windows-only.
// Override FONT_FACE here (e.g. "Arial") when building on Linux/macOS CI.
// ---------------------------------------------------------------------------
const FONT_FACE = "Calibri";

// ---------------------------------------------------------------------------
// Brand palette
// ---------------------------------------------------------------------------
const PALETTE = {
  navy:      "1E2761",
  teal:      "028090",
  white:     "FFFFFF",
  offWhite:  "F4F6F8",
  charcoal:  "2B2D42",
  midGray:   "8D99AE",
  lightGray: "EDF2F4",
  accent:    "EF233C",
};

// ---------------------------------------------------------------------------
// Typography scale (as a fraction of slide height so it's layout-agnostic)
// ---------------------------------------------------------------------------
const FONT = {
  display:  (h) => Math.round(h * 7.2),   // ~54 pt on WIDE
  title:    (h) => Math.round(h * 5.6),   // ~42 pt
  heading:  (h) => Math.round(h * 3.2),   // ~24 pt
  body:     (h) => Math.round(h * 2.0),   // ~15 pt
  caption:  (h) => Math.round(h * 1.5),   // ~11 pt
};

// ---------------------------------------------------------------------------
// Margin / gutter constants (as fraction of slide dims)
// ---------------------------------------------------------------------------
const MARGIN_X_FRAC = 0.045;   // ~0.60" on WIDE
const MARGIN_Y_FRAC = 0.067;   // ~0.50" on WIDE
const GUTTER_FRAC   = 0.030;   // ~0.40" on WIDE

// ---------------------------------------------------------------------------
// Helper: shadow factory (fresh object every call — PptxGenJS mutates opts)
// ---------------------------------------------------------------------------
function makeShadow() {
  return { type: "outer", color: "000000", blur: 8, offset: 3, angle: 135, opacity: 0.12 };
}

// ---------------------------------------------------------------------------
// Helper: evenly distribute N columns across the content width
// Returns array of { x, w } objects.
// ---------------------------------------------------------------------------
function distributeColumns(count, startX, totalW, gutterW) {
  const colW = (totalW - gutterW * (count - 1)) / count;
  return Array.from({ length: count }, (_, i) => ({
    x: startX + i * (colW + gutterW),
    w: colW,
  }));
}

// ---------------------------------------------------------------------------
// Helper: parse content into bullet array regardless of input type
// ---------------------------------------------------------------------------
function toBullets(content) {
  if (!content) return [];
  if (Array.isArray(content)) return content.map(String);
  return String(content)
    .split(/\n/)
    .map((s) => s.replace(/^[-•*]\s*/, "").trim())
    .filter(Boolean);
}

// ---------------------------------------------------------------------------
// Helper: convert bullet array to PptxGenJS rich-text array
// ---------------------------------------------------------------------------
function bulletsToRichText(items, opts = {}) {
  return items.map((text, i) => ({
    text,
    options: {
      bullet: true,
      breakLine: i < items.length - 1,
      ...opts,
    },
  }));
}

// ===========================================================================
// Core renderer — every slide method computes ALL positions from W × H
// ===========================================================================
class SlideRenderer {
  constructor(pres, layout) {
    this.pres = pres;
    this.W    = layout.w;
    this.H    = layout.h;
    // Derived convenience values
    this.MX   = this.W * MARGIN_X_FRAC;
    this.MY   = this.H * MARGIN_Y_FRAC;
    this.GX   = this.W * GUTTER_FRAC;
    this.GY   = this.H * GUTTER_FRAC;
    this.CW   = this.W - 2 * this.MX;   // usable content width
    this.CH   = this.H - 2 * this.MY;   // usable content height
  }

  // ── Backgrounds ──────────────────────────────────────────────────────────

  _darkBg(slide) {
    slide.background = { color: PALETTE.navy };
  }

  _lightBg(slide) {
    slide.background = { color: PALETTE.offWhite };
  }

  _whiteBg(slide) {
    slide.background = { color: PALETTE.white };
  }

  // ── Shared footer ─────────────────────────────────────────────────────────

  _footer(slide, text = "potomac.com  |  Built to Conquer Risk®", dark = false) {
    const fh   = this.H * 0.048;
    const fy   = this.H - fh - this.H * 0.018;
    const col  = dark ? "AAAAAA" : PALETTE.midGray;
    slide.addText(text, {
      x:        this.MX,
      y:        fy,
      w:        this.CW,
      h:        fh,
      fontSize: FONT.caption(this.H),
      fontFace: FONT_FACE,
      color:    col,
      align:    "center",
      valign:   "bottom",
      margin:   0,
    });
  }

  // ── Title bar shared element ──────────────────────────────────────────────

  _titleText(slide, title, dark = false) {
    const ty  = this.MY;
    const th  = this.H * 0.12;
    const col = dark ? PALETTE.white : PALETTE.navy;
    slide.addText(title, {
      x:        this.MX,
      y:        ty,
      w:        this.CW,
      h:        th,
      fontSize: FONT.title(this.H),
      fontFace: FONT_FACE,
      bold:     true,
      color:    col,
      align:    "left",
      valign:   "middle",
      margin:   0,
    });
    return ty + th + this.GY * 0.5; // return Y for content start
  }

  // =========================================================================
  // SLIDE TYPES
  // =========================================================================

  // ── 1. Title slide ────────────────────────────────────────────────────────
  createTitleSlide(title, subtitle = "", tagline = "") {
    const { W, H, MX, MY, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._darkBg(slide);

    // Teal accent strip — 1% of width, full-height
    const stripW = W * 0.010;
    slide.addShape(PPTX_SHAPES.RECTANGLE, {
      x: 0, y: 0, w: stripW, h: H,
      fill: { color: PALETTE.teal },
      line: { color: PALETTE.teal },
    });

    // Title
    const titleH  = H * 0.18;
    const titleY  = H * 0.30;
    slide.addText(title, {
      x:        MX + stripW + GY,
      y:        titleY,
      w:        CW - stripW - GY,
      h:        titleH,
      fontSize: FONT.display(H),
      fontFace: FONT_FACE,
      bold:     true,
      color:    PALETTE.white,
      align:    "left",
      valign:   "middle",
      margin:   0,
    });

    // Subtitle
    if (subtitle) {
      const subY = titleY + titleH + GY * 0.6;
      const subH = H * 0.08;
      slide.addText(subtitle, {
        x:        MX + stripW + GY,
        y:        subY,
        w:        CW - stripW - GY,
        h:        subH,
        fontSize: FONT.heading(H),
        fontFace: FONT_FACE,
        color:    PALETTE.teal,
        align:    "left",
        valign:   "top",
        margin:   0,
      });
    }

    // Tagline
    if (tagline) {
      const tgY = H * 0.80;
      const tgH = H * 0.06;
      slide.addText(tagline, {
        x:        MX,
        y:        tgY,
        w:        CW,
        h:        tgH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        italic:   true,
        color:    PALETTE.midGray,
        align:    "left",
        valign:   "middle",
        margin:   0,
      });
    }

    this._footer(slide, "potomac.com  |  Built to Conquer Risk®", true);
    return slide;
  }

  // ── 2. Section divider ────────────────────────────────────────────────────
  createSectionDivider(title, description = "") {
    const { W, H, MX, MY, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._darkBg(slide);

    // Full-width teal bar at 40% height
    const barH = H * 0.40;
    const barY = (H - barH) / 2;
    slide.addShape(PPTX_SHAPES.RECTANGLE, {
      x: 0, y: barY, w: W, h: barH,
      fill: { color: PALETTE.teal },
      line: { color: PALETTE.teal },
    });

    // Section title
    const titleH = barH * 0.55;
    const titleY = barY + (barH - titleH) / 2;
    slide.addText(title, {
      x:        MX,
      y:        titleY,
      w:        CW,
      h:        titleH,
      fontSize: FONT.display(H),
      fontFace: FONT_FACE,
      bold:     true,
      color:    PALETTE.white,
      align:    "center",
      valign:   "middle",
      margin:   0,
    });

    // Optional description below bar
    if (description) {
      const descY = barY + barH + GY;
      const descH = H * 0.08;
      slide.addText(description, {
        x:        MX,
        y:        descY,
        w:        CW,
        h:        descH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.midGray,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });
    }

    this._footer(slide, "potomac.com  |  Built to Conquer Risk®", true);
    return slide;
  }

  // ── 3. Content (bullets) slide ────────────────────────────────────────────
  createContentSlide(title, content) {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const contentH = H * 0.82 - contentY - H * 0.06;

    const bullets = toBullets(content);
    slide.addText(bulletsToRichText(bullets, {
      fontSize: FONT.body(H),
      fontFace: FONT_FACE,
      color:    PALETTE.charcoal,
    }), {
      x:      MX,
      y:      contentY,
      w:      CW,
      h:      contentH,
      valign: "top",
      margin: 0,
    });

    this._footer(slide);
    return slide;
  }

  // ── 4. Two-column slide ───────────────────────────────────────────────────
  createTwoColumnSlide(title, leftContent, rightContent, leftLabel = "", rightLabel = "") {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY  = this._titleText(slide, title);
    const labelH    = leftLabel || rightLabel ? H * 0.055 : 0;
    const colsY     = contentY + labelH + (labelH ? GY * 0.3 : 0);
    const colsH     = H * 0.82 - colsY - H * 0.06;
    const cols      = distributeColumns(2, MX, CW, this.GX);

    // Column accent lines
    cols.forEach((col) => {
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: col.x, y: colsY, w: col.w * 0.015, h: colsH,
        fill: { color: PALETTE.teal },
        line: { color: PALETTE.teal },
      });
    });

    // Column labels
    if (leftLabel || rightLabel) {
      [[leftLabel, cols[0]], [rightLabel, cols[1]]].forEach(([label, col]) => {
        if (!label) return;
        slide.addText(label, {
          x:        col.x,
          y:        contentY,
          w:        col.w,
          h:        labelH,
          fontSize: FONT.heading(H),
          fontFace: FONT_FACE,
          bold:     true,
          color:    PALETTE.navy,
          align:    "left",
          valign:   "middle",
          margin:   0,
        });
      });
    }

    // Column content
    const textOffsetX = cols[0].w * 0.025;
    [[leftContent, cols[0]], [rightContent, cols[1]]].forEach(([content, col]) => {
      const bullets = toBullets(content);
      slide.addText(bulletsToRichText(bullets, {
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.charcoal,
      }), {
        x:      col.x + textOffsetX,
        y:      colsY,
        w:      col.w - textOffsetX,
        h:      colsH,
        valign: "top",
        margin: 0,
      });
    });

    this._footer(slide);
    return slide;
  }

  // ── 5. Three-column slide ─────────────────────────────────────────────────
  createThreeColumnSlide(title, columns = []) {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const colsH    = H * 0.82 - contentY - H * 0.06;
    const count    = Math.max(columns.length, 1);
    const cols     = distributeColumns(count, MX, CW, this.GX);

    cols.forEach((col, i) => {
      const colData = columns[i] || {};
      const colTitle   = typeof colData === "string" ? "" : (colData.title || "");
      const colContent = typeof colData === "string" ? colData : (colData.content || colData.text || "");

      // Card background
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: col.x, y: contentY, w: col.w, h: colsH,
        fill: { color: PALETTE.lightGray },
        line: { color: PALETTE.lightGray },
        shadow: makeShadow(),
      });

      // Top accent
      const accentH = H * 0.007;
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: col.x, y: contentY, w: col.w, h: accentH,
        fill: { color: PALETTE.teal },
        line: { color: PALETTE.teal },
      });

      const cardPad  = col.w * 0.06;
      const innerX   = col.x + cardPad;
      const innerW   = col.w - cardPad * 2;
      let   innerY   = contentY + accentH + GY * 0.5;

      // Column heading
      if (colTitle) {
        const headH = H * 0.09;
        slide.addText(colTitle, {
          x:        innerX,
          y:        innerY,
          w:        innerW,
          h:        headH,
          fontSize: FONT.heading(H),
          fontFace: FONT_FACE,
          bold:     true,
          color:    PALETTE.navy,
          align:    "left",
          valign:   "middle",
          margin:   0,
        });
        innerY += headH + GY * 0.3;
      }

      const textH = contentY + colsH - innerY - GY * 0.3;
      const bullets = toBullets(colContent);
      slide.addText(bulletsToRichText(bullets, {
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.charcoal,
      }), {
        x:      innerX,
        y:      innerY,
        w:      innerW,
        h:      textH,
        valign: "top",
        margin: 0,
      });
    });

    this._footer(slide);
    return slide;
  }

  // ── 6. Metrics / KPI slide ────────────────────────────────────────────────
  createMetricsSlide(title, metrics = [], footnote = "") {
    const { H, MX, MY, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const count    = Math.max(metrics.length, 1);
    const cols     = distributeColumns(count, MX, CW, this.GX);
    const cardH    = H * 0.82 - contentY - H * 0.06 - (footnote ? H * 0.06 : 0);

    metrics.forEach((metric, i) => {
      const col   = cols[i];
      const m     = typeof metric === "string" ? { value: metric, label: "" } : metric;
      const value = m.value || "";
      const label = m.label || "";
      const sub   = m.sub   || "";

      // Card
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: col.x, y: contentY, w: col.w, h: cardH,
        fill: { color: PALETTE.navy },
        line: { color: PALETTE.navy },
        shadow: makeShadow(),
      });

      // Value — vertically centered in top 55% of card
      const valueH = cardH * 0.45;
      const valueY = contentY + cardH * 0.10;
      slide.addText(value, {
        x:        col.x,
        y:        valueY,
        w:        col.w,
        h:        valueH,
        fontSize: FONT.display(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.teal,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });

      // Label
      const labelY = valueY + valueH;
      const labelH = cardH * 0.24;
      slide.addText(label, {
        x:        col.x,
        y:        labelY,
        w:        col.w,
        h:        labelH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.white,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });

      // Sub-label
      if (sub) {
        const subY = labelY + labelH;
        const subH = cardH - (subY - contentY) - H * 0.02;
        slide.addText(sub, {
          x:        col.x,
          y:        subY,
          w:        col.w,
          h:        subH,
          fontSize: FONT.caption(H),
          fontFace: FONT_FACE,
          color:    PALETTE.midGray,
          align:    "center",
          valign:   "top",
          margin:   0,
        });
      }
    });

    // Footnote
    if (footnote) {
      const fnY = contentY + cardH + GY * 0.4;
      const fnH = H * 0.05;
      slide.addText(footnote, {
        x:        MX,
        y:        fnY,
        w:        CW,
        h:        fnH,
        fontSize: FONT.caption(H),
        fontFace: FONT_FACE,
        italic:   true,
        color:    PALETTE.midGray,
        align:    "left",
        valign:   "middle",
        margin:   0,
      });
    }

    this._footer(slide);
    return slide;
  }

  // ── 7. Process / steps slide ──────────────────────────────────────────────
  createProcessSlide(title, steps = []) {
    const { W, H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const count    = Math.max(steps.length, 1);
    const cols     = distributeColumns(count, MX, CW, this.GX);
    const cardH    = H * 0.82 - contentY - H * 0.06;
    const arrowW   = this.GX * 0.6;

    steps.forEach((step, i) => {
      const col   = cols[i];
      const s     = typeof step === "string" ? { title: `Step ${i + 1}`, description: step } : step;
      const num   = String(i + 1);

      // Card
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: col.x, y: contentY, w: col.w, h: cardH,
        fill: { color: PALETTE.offWhite },
        line: { color: PALETTE.lightGray, width: 1 },
        shadow: makeShadow(),
      });

      // Step number circle (approximate with small rectangle + heavy font)
      const circleSize = Math.min(col.w * 0.22, H * 0.10);
      const circleX    = col.x + (col.w - circleSize) / 2;
      const circleY    = contentY + cardH * 0.08;
      slide.addShape(PPTX_SHAPES.OVAL, {
        x: circleX, y: circleY, w: circleSize, h: circleSize,
        fill: { color: PALETTE.teal },
        line: { color: PALETTE.teal },
      });
      slide.addText(num, {
        x:        circleX,
        y:        circleY,
        w:        circleSize,
        h:        circleSize,
        fontSize: FONT.heading(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.white,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });

      const textPad  = col.w * 0.07;
      const textX    = col.x + textPad;
      const textW    = col.w - textPad * 2;
      const titleY   = circleY + circleSize + GY * 0.4;
      const titleH   = H * 0.08;

      // Step title
      slide.addText(s.title || "", {
        x:        textX,
        y:        titleY,
        w:        textW,
        h:        titleH,
        fontSize: FONT.heading(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.navy,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });

      // Step description
      const descY = titleY + titleH + GY * 0.2;
      const descH = contentY + cardH - descY - H * 0.04;
      slide.addText(s.description || "", {
        x:        textX,
        y:        descY,
        w:        textW,
        h:        descH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.charcoal,
        align:    "center",
        valign:   "top",
        margin:   0,
      });

      // Arrow between cards (not after last)
      if (i < steps.length - 1) {
        const arrowX  = col.x + col.w + (this.GX - arrowW) / 2;
        const arrowY  = contentY + cardH * 0.45;
        const arrowH  = cardH * 0.10;
        slide.addText("›", {
          x:        arrowX,
          y:        arrowY,
          w:        arrowW,
          h:        arrowH,
          fontSize: FONT.title(H),
          fontFace: FONT_FACE,
          bold:     true,
          color:    PALETTE.teal,
          align:    "center",
          valign:   "middle",
          margin:   0,
        });
      }
    });

    this._footer(slide);
    return slide;
  }

  // ── 8. Quote / testimonial slide ─────────────────────────────────────────
  createQuoteSlide(quote, attribution = "", context = "") {
    const { W, H, MX, MY, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._darkBg(slide);

    // Large decorative quote mark
    const qMarkH = H * 0.30;
    const qMarkY = H * 0.04;
    slide.addText("\u201C", {
      x:        MX,
      y:        qMarkY,
      w:        W * 0.12,
      h:        qMarkH,
      fontSize: Math.round(H * 22),
      fontFace: "Georgia",
      color:    PALETTE.teal,
      align:    "left",
      valign:   "top",
      margin:   0,
    });

    // Quote text — vertically centered
    const quoteH = H * 0.42;
    const quoteY = (H - quoteH) / 2 - H * 0.04;
    slide.addText(quote, {
      x:        MX + W * 0.06,
      y:        quoteY,
      w:        CW - W * 0.06,
      h:        quoteH,
      fontSize: FONT.heading(H),
      fontFace: "Georgia",
      italic:   true,
      color:    PALETTE.white,
      align:    "left",
      valign:   "middle",
      margin:   0,
    });

    // Attribution
    if (attribution) {
      const attrY = quoteY + quoteH + GY * 0.4;
      const attrH = H * 0.07;
      slide.addText(`— ${attribution}`, {
        x:        MX + W * 0.06,
        y:        attrY,
        w:        CW - W * 0.06,
        h:        attrH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.teal,
        align:    "left",
        valign:   "middle",
        margin:   0,
      });
    }

    // Context
    if (context) {
      const ctxY = H * 0.84;
      const ctxH = H * 0.06;
      slide.addText(context, {
        x:        MX,
        y:        ctxY,
        w:        CW,
        h:        ctxH,
        fontSize: FONT.caption(H),
        fontFace: FONT_FACE,
        italic:   true,
        color:    PALETTE.midGray,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });
    }

    this._footer(slide, "potomac.com  |  Built to Conquer Risk®", true);
    return slide;
  }

  // ── 9. Call to action / closing slide ────────────────────────────────────
  createCallToActionSlide(title, actionText = "", contactInfo = "") {
    const { W, H, MX, MY, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._darkBg(slide);

    // Teal panel occupying lower 35%
    const panelH = H * 0.35;
    const panelY = H - panelH;
    slide.addShape(PPTX_SHAPES.RECTANGLE, {
      x: 0, y: panelY, w: W, h: panelH,
      fill: { color: PALETTE.teal },
      line: { color: PALETTE.teal },
    });

    // Title
    const titleH = H * 0.16;
    const titleY = H * 0.12;
    slide.addText(title, {
      x:        MX,
      y:        titleY,
      w:        CW,
      h:        titleH,
      fontSize: FONT.display(H),
      fontFace: FONT_FACE,
      bold:     true,
      color:    PALETTE.white,
      align:    "center",
      valign:   "middle",
      margin:   0,
    });

    // Action text
    if (actionText) {
      const actY = titleY + titleH + GY * 0.6;
      const actH = H * 0.10;
      slide.addText(actionText, {
        x:        MX,
        y:        actY,
        w:        CW,
        h:        actH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.midGray,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });
    }

    // Contact info in teal panel
    if (contactInfo) {
      const ciH = panelH * 0.45;
      const ciY = panelY + (panelH - ciH) / 2;
      slide.addText(contactInfo, {
        x:        MX,
        y:        ciY,
        w:        CW,
        h:        ciH,
        fontSize: FONT.heading(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.white,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });
    }

    return slide;
  }

  // ── 10. Table slide ───────────────────────────────────────────────────────
  createTableSlide(title, headers = [], rows = [], options = {}) {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const tableH   = H * 0.82 - contentY - H * 0.06;
    const colCount = Math.max(headers.length, 1);
    const colW     = CW / colCount;

    const headerRow = headers.map((h) => ({
      text: String(h),
      options: {
        bold:     true,
        color:    PALETTE.white,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        fill:     { color: PALETTE.navy },
        align:    "center",
      },
    }));

    const bodyRows = rows.map((row, ri) =>
      (Array.isArray(row) ? row : [row]).map((cell) => ({
        text: String(cell),
        options: {
          color:    PALETTE.charcoal,
          fontSize: FONT.body(H),
          fontFace: FONT_FACE,
          fill:     { color: ri % 2 === 0 ? PALETTE.white : PALETTE.lightGray },
          align:    "left",
        },
      }))
    );

    slide.addTable([headerRow, ...bodyRows], {
      x:      MX,
      y:      contentY,
      w:      CW,
      h:      tableH,
      colW:   Array(colCount).fill(colW),
      border: { pt: 0.5, color: PALETTE.lightGray },
    });

    this._footer(slide);
    return slide;
  }

  // ── 11. Chart slide ───────────────────────────────────────────────────────
  createChartSlide(title, chartType = "bar", chartData = [], chartOptions = {}) {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const chartH   = H * 0.82 - contentY - H * 0.06;

    const typeMap = {
      bar:      PPTX_CHARTS.BAR,
      column:   PPTX_CHARTS.BAR,
      line:     PPTX_CHARTS.LINE,
      pie:      PPTX_CHARTS.PIE,
      doughnut: PPTX_CHARTS.DOUGHNUT,
      area:     PPTX_CHARTS.AREA,
      scatter:  PPTX_CHARTS.SCATTER,
    };
    const pptxChartType = typeMap[chartType.toLowerCase()] || PPTX_CHARTS.BAR;

    slide.addChart(pptxChartType, chartData, {
      x:                MX,
      y:                contentY,
      w:                CW,
      h:                chartH,
      barDir:           chartType.toLowerCase() === "bar" ? "bar" : "col",
      chartColors:      [PALETTE.teal, PALETTE.navy, PALETTE.midGray, PALETTE.accent],
      chartArea:        { fill: { color: PALETTE.white }, roundedCorners: false },
      catAxisLabelColor: PALETTE.midGray,
      valAxisLabelColor: PALETTE.midGray,
      valGridLine:      { color: PALETTE.lightGray, size: 0.5 },
      catGridLine:      { style: "none" },
      showLegend:       chartData.length > 1,
      legendPos:        "b",
      showValue:        false,
      ...chartOptions,
    });

    this._footer(slide);
    return slide;
  }

  // ── 12. Image + content slide ─────────────────────────────────────────────
  createImageContentSlide(title, imagePath, content, imagePosition = "left") {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY  = this._titleText(slide, title);
    const blockH    = H * 0.82 - contentY - H * 0.06;
    const imgFrac   = 0.48;
    const imgW      = CW * imgFrac;
    const textW     = CW * (1 - imgFrac) - this.GX;

    const imgX  = imagePosition === "right" ? MX + textW + this.GX : MX;
    const textX = imagePosition === "right" ? MX : MX + imgW + this.GX;

    if (imagePath) {
      slide.addImage({
        path:   imagePath,
        x:      imgX,
        y:      contentY,
        w:      imgW,
        h:      blockH,
        sizing: { type: "cover", w: imgW, h: blockH },
      });
    } else {
      // Placeholder
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: imgX, y: contentY, w: imgW, h: blockH,
        fill: { color: PALETTE.lightGray },
        line: { color: PALETTE.midGray, width: 1 },
      });
    }

    const bullets = toBullets(content);
    slide.addText(bulletsToRichText(bullets, {
      fontSize: FONT.body(H),
      fontFace: FONT_FACE,
      color:    PALETTE.charcoal,
    }), {
      x:      textX,
      y:      contentY,
      w:      textW,
      h:      blockH,
      valign: "top",
      margin: 0,
    });

    this._footer(slide);
    return slide;
  }

  // ── 13. Timeline slide ────────────────────────────────────────────────────
  createTimelineSlide(title, milestones = []) {
    const { W, H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY = this._titleText(slide, title);
    const count    = Math.max(milestones.length, 1);

    // Horizontal spine
    const spineY  = contentY + (H * 0.82 - contentY - H * 0.06) * 0.40;
    const spineH  = H * 0.008;
    slide.addShape(PPTX_SHAPES.RECTANGLE, {
      x: MX, y: spineY, w: CW, h: spineH,
      fill: { color: PALETTE.teal },
      line: { color: PALETTE.teal },
    });

    const stepW   = CW / count;
    const dotSize = Math.min(stepW * 0.14, H * 0.055);

    milestones.forEach((ms, i) => {
      const m       = typeof ms === "string" ? { label: ms, date: "" } : ms;
      const centerX = MX + stepW * i + stepW / 2;

      // Dot
      const dotX = centerX - dotSize / 2;
      const dotY = spineY + spineH / 2 - dotSize / 2;
      slide.addShape(PPTX_SHAPES.OVAL, {
        x: dotX, y: dotY, w: dotSize, h: dotSize,
        fill: { color: PALETTE.navy },
        line: { color: PALETTE.navy },
        shadow: makeShadow(),
      });

      // Date (above spine)
      if (m.date) {
        const dateH = H * 0.06;
        const dateY = dotY - dateH - GY * 0.2;
        slide.addText(m.date, {
          x:        centerX - stepW * 0.45,
          y:        dateY,
          w:        stepW * 0.9,
          h:        dateH,
          fontSize: FONT.caption(H),
          fontFace: FONT_FACE,
          bold:     true,
          color:    PALETTE.teal,
          align:    "center",
          valign:   "middle",
          margin:   0,
        });
      }

      // Label (below spine)
      const labelY = dotY + dotSize + GY * 0.3;
      const labelH = H * 0.82 - labelY - H * 0.06;
      slide.addText(m.label || "", {
        x:        centerX - stepW * 0.45,
        y:        labelY,
        w:        stepW * 0.9,
        h:        labelH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.charcoal,
        align:    "center",
        valign:   "top",
        margin:   0,
      });
    });

    this._footer(slide);
    return slide;
  }

  // ── 14. Scorecard slide ───────────────────────────────────────────────────
  createScorecardSlide(title, metrics = [], subtitle = "") {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    let curY = this._titleText(slide, title);

    if (subtitle) {
      const subH = H * 0.055;
      slide.addText(subtitle, {
        x:        MX,
        y:        curY,
        w:        CW,
        h:        subH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        italic:   true,
        color:    PALETTE.midGray,
        align:    "left",
        valign:   "middle",
        margin:   0,
      });
      curY += subH + GY * 0.3;
    }

    const rowCount  = Math.max(metrics.length, 1);
    const availH    = H * 0.82 - curY - H * 0.06;
    const rowH      = (availH - GY * (rowCount - 1)) / rowCount;
    const labelColW = CW * 0.40;
    const valueColW = CW * 0.18;
    const barColW   = CW - labelColW - valueColW - this.GX * 2;

    metrics.forEach((m, i) => {
      const metric  = typeof m === "string" ? { label: m, value: "", score: 0 } : m;
      const rowY    = curY + i * (rowH + GY);
      const score   = Math.min(Math.max(Number(metric.score) || 0, 0), 100);
      const barFill = score >= 70 ? PALETTE.teal : score >= 40 ? "F0A500" : PALETTE.accent;

      // Row background
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: MX, y: rowY, w: CW, h: rowH,
        fill: { color: i % 2 === 0 ? PALETTE.lightGray : PALETTE.white },
        line: { color: PALETTE.lightGray, width: 0.5 },
      });

      // Label
      slide.addText(metric.label || "", {
        x:        MX + this.GX * 0.5,
        y:        rowY,
        w:        labelColW,
        h:        rowH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        color:    PALETTE.charcoal,
        align:    "left",
        valign:   "middle",
        margin:   0,
      });

      // Value
      const valX = MX + labelColW + this.GX;
      slide.addText(String(metric.value || ""), {
        x:        valX,
        y:        rowY,
        w:        valueColW,
        h:        rowH,
        fontSize: FONT.body(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.navy,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });

      // Bar track
      const barX = valX + valueColW + this.GX;
      const barH = rowH * 0.30;
      const barY = rowY + (rowH - barH) / 2;
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: barX, y: barY, w: barColW, h: barH,
        fill: { color: PALETTE.lightGray },
        line: { color: PALETTE.midGray, width: 0.5 },
      });

      // Bar fill
      if (score > 0) {
        slide.addShape(PPTX_SHAPES.RECTANGLE, {
          x: barX, y: barY, w: barColW * (score / 100), h: barH,
          fill: { color: barFill },
          line: { color: barFill },
        });
      }
    });

    this._footer(slide);
    return slide;
  }

  // ── 15. Comparison (feature matrix) slide ────────────────────────────────
  createComparisonSlide(title, leftLabel = "OPTION A", rightLabel = "OPTION B", rows = [], winner = null) {
    const { H, MX, CW, GY } = this;
    const slide = this.pres.addSlide();
    this._whiteBg(slide);

    const contentY   = this._titleText(slide, title);
    const featureW   = CW * 0.36;
    const optionW    = (CW - featureW - this.GX * 2) / 2;
    const headerH    = H * 0.08;

    // Column headers
    const leftX  = MX + featureW + this.GX;
    const rightX = leftX + optionW + this.GX;

    [{ x: leftX, label: leftLabel, isWinner: winner === "left" },
     { x: rightX, label: rightLabel, isWinner: winner === "right" }].forEach(({ x, label, isWinner }) => {
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x, y: contentY, w: optionW, h: headerH,
        fill: { color: isWinner ? PALETTE.teal : PALETTE.navy },
        line: { color: isWinner ? PALETTE.teal : PALETTE.navy },
        shadow: makeShadow(),
      });
      slide.addText(label, {
        x, y: contentY, w: optionW, h: headerH,
        fontSize: FONT.heading(H),
        fontFace: FONT_FACE,
        bold:     true,
        color:    PALETTE.white,
        align:    "center",
        valign:   "middle",
        margin:   0,
      });
    });

    const rowCount   = Math.max(rows.length, 1);
    const availH     = H * 0.82 - contentY - headerH - GY * 0.3 - H * 0.06;
    const rowH       = (availH - GY * 0.2 * (rowCount - 1)) / rowCount;
    const rowStartY  = contentY + headerH + GY * 0.3;

    rows.forEach((row, ri) => {
      const r    = typeof row === "string" ? { feature: row, left: "", right: "" } : row;
      const rowY = rowStartY + ri * (rowH + GY * 0.2);
      const bg   = ri % 2 === 0 ? PALETTE.lightGray : PALETTE.white;

      // Feature cell
      slide.addShape(PPTX_SHAPES.RECTANGLE, {
        x: MX, y: rowY, w: featureW, h: rowH,
        fill: { color: bg }, line: { color: PALETTE.lightGray, width: 0.5 },
      });
      slide.addText(r.feature || "", {
        x: MX + this.GX * 0.4, y: rowY, w: featureW - this.GX * 0.4, h: rowH,
        fontSize: FONT.body(H), fontFace: FONT_FACE,
        bold: true, color: PALETTE.navy,
        align: "left", valign: "middle", margin: 0,
      });

      // Left / right option cells
      [{ x: leftX, val: r.left }, { x: rightX, val: r.right }].forEach(({ x, val }) => {
        slide.addShape(PPTX_SHAPES.RECTANGLE, {
          x, y: rowY, w: optionW, h: rowH,
          fill: { color: bg }, line: { color: PALETTE.lightGray, width: 0.5 },
        });
        slide.addText(String(val || ""), {
          x, y: rowY, w: optionW, h: rowH,
          fontSize: FONT.body(H), fontFace: FONT_FACE,
          color: PALETTE.charcoal,
          align: "center", valign: "middle", margin: 0,
        });
      });
    });

    this._footer(slide);
    return slide;
  }
}

// ===========================================================================
// Content classifier
// ===========================================================================
class ContentClassifier {
  classify(slideData) {
    const text  = [
      slideData.title, slideData.subtitle, slideData.content,
      slideData.leftContent, slideData.rightContent,
    ].flat().filter(Boolean).join(" ").toLowerCase();

    if (slideData.role === "title"   || slideData.isFirst)              return "title";
    if (slideData.role === "divider" || slideData.isSection)            return "sectionDivider";
    if (slideData.role === "cta"     || slideData.isClosing)            return "callToAction";
    if (slideData.type === "quote"   || slideData.quote)                return "quote";
    if (slideData.type === "metrics" || slideData.metrics)              return "metrics";
    if (slideData.type === "process" || slideData.steps)                return "process";
    if (slideData.type === "timeline"|| slideData.milestones)           return "timeline";
    if (slideData.type === "scorecard")                                 return "scorecard";
    if (slideData.type === "comparison" || slideData.rows)              return "comparison";
    if (slideData.type === "table" || (slideData.headers && slideData.rows)) return "table";
    if (slideData.type === "chart"   || slideData.chartType)            return "chart";
    if (slideData.type === "image_content" || slideData.imagePath)      return "imageContent";
    if (Array.isArray(slideData.columns) && slideData.columns.length === 3) return "threeColumn";
    if (slideData.hasComparison || (Array.isArray(slideData.columns) && slideData.columns.length === 2)
        || slideData.leftContent || slideData.rightContent)             return "twoColumn";

    return "content";
  }
}

// ===========================================================================
// Main builder class
// ===========================================================================
class PotomacPresentationBuilder {
  /**
   * @param {object} options
   * @param {string} [options.title]         - Presentation title
   * @param {string} [options.subtitle]      - Presentation subtitle
   * @param {string} [options.author]        - Author name
   * @param {string} [options.company]       - Company name
   * @param {string} [options.layout]        - One of: LAYOUT_WIDE (default), LAYOUT_16x9, LAYOUT_16x10, LAYOUT_4x3
   * @param {string} [options.outputDir]     - Output directory (default: same dir as this file)
   */
  constructor(options = {}) {
    this.pres    = new pptxgen();
    this.options = {
      title:     options.title     || "POTOMAC PRESENTATION",
      subtitle:  options.subtitle  || "Built to Conquer Risk\u00ae",
      author:    options.author    || "Potomac",
      company:   options.company   || "Potomac",
      layout:    options.layout    || "LAYOUT_WIDE",
      outputDir: options.outputDir || __dirname,
      ...options,
    };

    // Resolve layout dimensions
    const layoutDims = LAYOUTS[this.options.layout] || LAYOUTS.LAYOUT_WIDE;

    // Configure pptxgenjs
    this.pres.layout  = this.options.layout;
    this.pres.author  = this.options.author;
    this.pres.company = this.options.company;
    this.pres.title   = this.options.title;
    this.pres.subject = this.options.title;

    // Instantiate renderer and classifier with resolved dims
    this.renderer   = new SlideRenderer(this.pres, layoutDims);
    this.classifier = new ContentClassifier();
    this.slideStack = [];
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Add a slide. The type is inferred automatically from the data shape,
   * or forced via `slideData.type`.
   */
  addSlide(slideData) {
    const type  = slideData.type || this.classifier.classify(slideData);
    const slide = this._render(type, slideData);
    this.slideStack.push({ type, data: slideData, slide });
    console.log(`[slide ${this.slideStack.length}] type="${type}" title="${slideData.title || '(none)'}"`);
    return slide;
  }

  /**
   * Save the presentation.
   * @param {string} filename  e.g. "report.pptx"
   * @returns {Promise<string>} resolved absolute path
   */
  async save(filename) {
    const outputPath = path.join(this.options.outputDir, filename);
    try {
      fs.mkdirSync(path.dirname(outputPath), { recursive: true });
      await this.pres.writeFile({ fileName: outputPath });
      console.log(`Saved: ${outputPath}`);
      return outputPath;
    } catch (err) {
      throw new Error(`Failed to save presentation to "${outputPath}": ${err.message}`);
    }
  }

  /** Summary of slide types used (useful for logging) */
  getSlideStats() {
    const tally = {};
    this.slideStack.forEach(({ type }) => { tally[type] = (tally[type] || 0) + 1; });
    return tally;
  }

  // ---------------------------------------------------------------------------
  // Pre-built presentation generators
  // ---------------------------------------------------------------------------

  generateResearchPresentation(data = {}) {
    this.addSlide({ role: "title", isFirst: true,
      title:    data.title    || this.options.title,
      subtitle: data.subtitle || "Investment Research & Analysis" });

    this.addSlide({ title: "Executive Summary",
      content: data.executiveSummary || [
        "Market conditions remain challenging",
        "Opportunities exist in selected sectors",
        "Risk management is paramount",
        "Strategic positioning recommended",
      ] });

    if (data.keyFindings?.length) {
      this.addSlide({ title: "Key Findings", type: "metrics", metrics: data.keyFindings });
    }

    this.addSlide({ title: "Market Analysis",
      hasComparison:  true,
      leftLabel:      "Current Environment",
      rightLabel:     "Our Outlook",
      leftContent:    data.currentEnvironment || [
        "Market volatility elevated",
        "Economic uncertainty persists",
        "Sector rotation continuing",
      ],
      rightContent:   data.outlook || [
        "Selective opportunities emerging",
        "Defensive positioning preferred",
        "Active management advantage",
      ] });

    this.addSlide({ title: "Investment Implications",
      content: data.implications || [
        "Maintain diversified portfolio approach",
        "Focus on quality companies with strong fundamentals",
        "Consider defensive sectors for stability",
        "Monitor interest rate environment closely",
      ] });

    this.addSlide({ role: "cta", isClosing: true,
      title:       "Questions & Discussion",
      actionText:  data.ctaText    || "Ready to discuss how these insights can benefit your portfolio?",
      contactInfo: data.contactInfo || "potomac.com  |  (305) 824-2702  |  info@potomac.com",
    });

    return this;
  }

  generateClientPitch(data = {}) {
    this.addSlide({ role: "title", isFirst: true,
      title:    data.title    || "Potomac Investment Solutions",
      subtitle: data.subtitle || "Your Partner in Conquering Risk",
    });

    this.addSlide({ title: "Our Proven Approach", type: "process",
      steps: data.approach || [
        { title: "Listen",      description: "Understanding your unique goals and constraints" },
        { title: "Analyze",     description: "Comprehensive risk assessment and opportunity identification" },
        { title: "Design",      description: "Custom strategy tailored to your objectives" },
        { title: "Execute",     description: "Professional implementation and ongoing management" },
      ] });

    this.addSlide({ title: "Why Choose Potomac",
      columns: data.valueProps || [
        { title: "Experience",  content: ["Proven track record", "Seasoned professionals", "Institutional-quality research"] },
        { title: "Innovation",  content: ["Cutting-edge technology", "Advanced risk management", "Systematic approach"] },
        { title: "Service",     content: ["Personal attention", "Transparent reporting", "Ongoing communication"] },
      ] });

    if (data.results?.length) {
      this.addSlide({ title: "Client Results", type: "metrics",
        metrics: data.results,
        footnote: "Past performance does not guarantee future results.",
      });
    }

    this.addSlide({ role: "cta", isClosing: true,
      title:       "Let\u2019s Get Started",
      actionText:  data.ctaText    || "Ready to experience the Potomac difference? Let\u2019s schedule a consultation.",
      contactInfo: data.contactInfo || "potomac.com  |  (305) 824-2702  |  info@potomac.com",
    });

    return this;
  }

  generateMarketOutlook(data = {}) {
    this.addSlide({ role: "title", isFirst: true,
      title:    data.title    || "Market Outlook",
      subtitle: data.subtitle || "Navigating Uncertainty with Confidence",
    });

    this.addSlide({ title: "Current Market Environment",
      hasComparison: true,
      leftLabel:     "Key Challenges",
      rightLabel:    "Emerging Opportunities",
      leftContent:   data.challenges || [
        "Persistent inflation concerns",
        "Geopolitical tensions",
        "Rate environment uncertainty",
        "Supply chain disruptions",
      ],
      rightContent:  data.opportunities || [
        "Sector rotation continues",
        "Value over growth themes",
        "International diversification",
        "Alternative investments",
      ] });

    if (data.indicators?.length) {
      this.addSlide({ title: "Key Economic Indicators", type: "metrics", metrics: data.indicators });
    }

    this.addSlide({ title: "Our Strategic Response",
      content: data.strategy || [
        "Maintain defensive positioning while seeking selective opportunities",
        "Focus on quality companies with pricing power",
        "Diversify across asset classes and geographies",
        "Active risk management and regular portfolio rebalancing",
      ] });

    this.addSlide({ role: "cta", isClosing: true,
      title:       "Built to Conquer Risk\u00ae",
      actionText:  data.ctaText    || "Contact us to learn how our strategies can help navigate these markets.",
      contactInfo: data.contactInfo || "potomac.com  |  (305) 824-2702  |  info@potomac.com",
    });

    return this;
  }

  // ---------------------------------------------------------------------------
  // Internal dispatcher
  // ---------------------------------------------------------------------------

  _render(type, d) {
    const r = this.renderer;
    try {
      switch (type) {
        case "title":
          return r.createTitleSlide(d.title, d.subtitle, d.tagline);

        case "sectionDivider":
          return r.createSectionDivider(d.title, d.description);

        case "callToAction":
          return r.createCallToActionSlide(
            d.title,
            d.actionText  || d.content,
            d.contactInfo || "potomac.com  |  (305) 824-2702",
          );

        case "quote":
          return r.createQuoteSlide(d.quote || d.content, d.attribution, d.context);

        case "metrics":
          return r.createMetricsSlide(
            d.title,
            d.metrics || [],
            d.footnote || d.context || "",
          );

        case "process":
          return r.createProcessSlide(d.title, d.steps || []);

        case "timeline":
          return r.createTimelineSlide(d.title, d.milestones || d.steps || []);

        case "scorecard":
          return r.createScorecardSlide(d.title, d.metrics || [], d.subtitle);

        case "comparison":
          return r.createComparisonSlide(
            d.title,
            d.leftLabel  || d.left_label  || "OPTION A",
            d.rightLabel || d.right_label || "OPTION B",
            d.rows  || [],
            d.winner || null,
          );

        case "table":
          return r.createTableSlide(
            d.title,
            d.headers || d.table_headers || [],
            d.rows    || d.table_rows    || [],
            d.options || {},
          );

        case "chart":
          return r.createChartSlide(
            d.title,
            d.chartType  || d.chart_type  || "bar",
            d.chartData  || d.chart_data  || [],
            d.chartOptions || d.chart_options || {},
          );

        case "imageContent":
          return r.createImageContentSlide(
            d.title,
            d.imagePath || d.image_path || null,
            d.content   || d.bullets    || "",
            d.imagePosition || d.image_position || "left",
          );

        case "twoColumn":
          return r.createTwoColumnSlide(
            d.title,
            d.leftContent  || d.columns?.[0] || "",
            d.rightContent || d.columns?.[1] || "",
            d.leftLabel    || "",
            d.rightLabel   || "",
          );

        case "threeColumn":
          return r.createThreeColumnSlide(d.title, d.columns || []);

        default:
          return r.createContentSlide(d.title, d.content);
      }
    } catch (err) {
      console.error(`Error rendering slide type="${type}": ${err.message}`);
      return r.createContentSlide(d.title || "Error", `Could not render slide: ${err.message}`);
    }
  }
}

// ===========================================================================
// Exports
// ===========================================================================
module.exports = {
  PotomacPresentationBuilder,
  SlideRenderer,
  ContentClassifier,
  LAYOUTS,
  PALETTE,
  FONT,
};