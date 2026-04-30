'use strict';

/**
 * Potomac Universal Slide Templates — fully dynamic geometry
 *
 * Every coordinate, width, height, font size, and spacing value is derived
 * from the CANVAS constants at the top of the constructor.  There are no
 * hard-coded layout numbers anywhere in this file — change W / H and every
 * slide reflows automatically.
 *
 * Presentation layout: LAYOUT_WIDE  (13.333" × 7.5")
 *
 * Slide types supported (matches DeckPlanner VALID_SLIDE_TYPES):
 *   Title:   standard_title, executive_title, section_divider
 *   Content: content, two_column, three_column, quote, metric,
 *            process, executive_summary, card_grid, icon_grid,
 *            hub_spoke, timeline, matrix_2x2, scorecard,
 *            comparison, table, chart, image_content, image
 *   Closing: closing, call_to_action
 */

const { POTOMAC_COLORS, SLIDE_PALETTES } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS }                  = require('../brand-assets/fonts/potomac-fonts.js');
const path                               = require('path');
const fs                                 = require('fs');

// ── Strip '#' that pptxgenjs does not accept ────────────────────────────────
function _c(hex) {
  if (!hex) return 'FEC00F';
  return String(hex).replace('#', '');
}

const C = POTOMAC_COLORS;
const F = POTOMAC_FONTS;

// ── Full-logo natural aspect ratio  (icon+wordmark, ~13.02 × 2.67 inches) ──
const FULL_LOGO_RATIO = 13.02 / 2.67; // ≈ 4.876  (width : height)

// ── Icon-logo natural aspect ratio  (square hexagon mark, ~4.04 × 4.01") ───
const ICON_LOGO_RATIO = 1.0;          // effectively 1 : 1

// ── Default contact info — single source so closing slides stay in sync ────
const DEFAULT_CONTACT_INFO   = 'potomac.com\n(305) 824-2702\ninfo@potomac.com';
const DEFAULT_CONTACT_INLINE = 'potomac.com | (305) 824-2702 | info@potomac.com';

// ── Watermark scale for full-bleed image slides ────────────────────────────
// Applied to WORDMARK_W / WORDMARK_H to produce a subtle top-right watermark.
const WATERMARK_SCALE = 0.34;


class PotomacSlideTemplates {

  constructor(pptxGenerator, options = {}) {
    this.pptx    = pptxGenerator;
    this.palette = SLIDE_PALETTES[options.palette || 'STANDARD'];
    this.logoDir = path.join(__dirname, '../brand-assets/logos/');

    // ── Apply widescreen layout ──────────────────────────────────────────────
    this.pptx.layout = 'LAYOUT_WIDE';

    // ── SINGLE SOURCE OF TRUTH ───────────────────────────────────────────────
    // Every geometric value in this class is derived from these two numbers.
    // Read live from the pptx instance so any layout change propagates automatically.
    const { width: W, height: H } = this.pptx.presLayout;

    // Margins
    const ML = W * 0.0375;    // left  margin  ≈ 0.5"
    const MR = W * 0.0375;    // right margin  ≈ 0.5"
    const MT = H * 0.04;      // top   margin  ≈ 0.3"
    const MB = H * 0.053;     // bottom margin ≈ 0.4"

    // Content column
    const CW  = W - ML - MR;          // content width ≈ 12.333"
    const CX  = ML;                    // content left  ≈  0.5"
    const CX2 = W - MR;               // content right ≈ 12.833"

    // Logo watermark (top-right icon)
    const LOGO_W = W * 0.0712;        // ≈ 0.95"
    const LOGO_H = LOGO_W / ICON_LOGO_RATIO;
    const LOGO_X = W - MR - LOGO_W;   // ≈ 12.083"
    const LOGO_Y = H * 0.016;         // ≈ 0.12"

    // Full wordmark for title / closing slides
    const WORDMARK_H = H * 0.129;     // ≈ 0.97"
    const WORDMARK_W = WORDMARK_H * FULL_LOGO_RATIO;  // ≈ 4.73"

    // Title row
    const TITLE_Y    = H * 0.067;     // ≈ 0.5"
    const TITLE_H    = H * 0.133;     // ≈ 1.0"
    const TITLE_FS   = Math.round(W * 2.4);  // ≈ 32pt
    const UNDERLINE_Y = TITLE_Y + TITLE_H * 0.93;  // just below title text
    const UNDERLINE_H = H * 0.007;    // ≈ 0.05"
    const UNDERLINE_W = W * 0.15;     // ≈ 2.0"

    // Content body (below title)
    const BODY_Y  = UNDERLINE_Y + UNDERLINE_H + H * 0.027;  // ≈ 1.6"
    const BODY_H  = H - BODY_Y - MB;                         // remaining height

    // Footer row
    const FOOTER_Y  = H - MB;                // ≈ 7.1"
    const FOOTER_H  = MB;
    const DISCLAIMER_W = CW * 0.96;

    // Slide-number box (bottom-right)
    const SN_W = CW * 0.057;   // ≈ 0.7"
    const SN_X = CX2 - SN_W;

    // Gap & column helpers
    const COL_GAP = W * 0.03;  // ≈ 0.4"

    // ── Store every derived value on this.cv (canvas variables) ──────────────
    this.cv = {
      W, H, ML, MR, MT, MB,
      CW, CX, CX2,
      LOGO_W, LOGO_H, LOGO_X, LOGO_Y,
      WORDMARK_W, WORDMARK_H,
      TITLE_Y, TITLE_H, TITLE_FS,
      UNDERLINE_Y, UNDERLINE_H, UNDERLINE_W,
      BODY_Y, BODY_H,
      FOOTER_Y, FOOTER_H, DISCLAIMER_W,
      SN_W, SN_X,
      COL_GAP,
    };
  }


  // ════════════════════════════════════════════════════════════════════════════
  // LOGO HELPERS
  // ════════════════════════════════════════════════════════════════════════════

  /** Returns the path of the square icon logo, or null. */
  getIconLogoPath(theme = 'light') {
    const candidates = theme === 'dark'
      ? ['potomac-icon-white.png',  'potomac-icon-yellow.png']
      : ['potomac-icon-black.png',  'potomac-icon-yellow.png'];
    for (const name of candidates) {
      const p = path.join(this.logoDir, name);
      if (fs.existsSync(p)) return p;
    }
    return null;
  }

  /** Returns the path of the full wordmark logo, or null. */
  getFullLogoPath(theme = 'light') {
    const candidates = theme === 'dark'
      ? ['potomac-full-logo-white.png', 'potomac-full-logo.png']
      : ['potomac-full-logo-black.png', 'potomac-full-logo.png'];
    for (const name of candidates) {
      const p = path.join(this.logoDir, name);
      if (fs.existsSync(p)) return p;
    }
    return null;
  }

  /**
   * Place the full WORDMARK at an explicit bounding box.
   * Uses contain-sizing so the image is never distorted.
   */
  addLogo(slide, position, theme = 'light') {
    const logoPath = this.getFullLogoPath(theme);
    if (logoPath) {
      slide.addImage({
        path: logoPath,
        x: position.x, y: position.y,
        w: position.w, h: position.h,
        sizing: { type: 'contain', w: position.w, h: position.h },
      });
    } else {
      const { cv } = this;
      slide.addText('POTOMAC', {
        x: position.x, y: position.y, w: position.w, h: position.h,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.87),
        bold: true, align: 'center', valign: 'middle',
        color: theme === 'dark' ? _c(C.PRIMARY.WHITE) : _c(C.PRIMARY.DARK_GRAY),
      });
    }
  }

  /**
   * Small icon-logo watermark — top-right on every content slide.
   * Dimensions and position are derived from cv (canvas variables).
   */
  addStandardLogo(slide, theme = 'light') {
    const { cv } = this;
    const logoPath = this.getIconLogoPath(theme);
    if (logoPath) {
      slide.addImage({
        path: logoPath,
        x: cv.LOGO_X, y: cv.LOGO_Y, w: cv.LOGO_W, h: cv.LOGO_H,
        sizing: { type: 'contain', w: cv.LOGO_W, h: cv.LOGO_H },
      });
    } else {
      slide.addText('POTOMAC', {
        x: cv.LOGO_X - cv.LOGO_W * 0.6, y: cv.LOGO_Y,
        w: cv.LOGO_W * 1.6, h: cv.LOGO_H,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.6),
        bold: true, align: 'right', valign: 'middle',
        color: theme === 'dark' ? _c(C.PRIMARY.WHITE) : _c(C.PRIMARY.DARK_GRAY),
      });
    }
  }


  // ════════════════════════════════════════════════════════════════════════════
  // CHROME HELPERS  (underline, disclaimer, slide number)
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Accent underline bar below the slide title.
   * x and y default to the standard title position; pass overrides for custom layouts.
   */
  addTitleUnderline(slide, x, y) {
    const { cv } = this;
    slide.addShape(this.pptx.ShapeType.rect, {
      x: x !== undefined ? x : cv.CX,
      y: y !== undefined ? y : cv.UNDERLINE_Y,
      w: cv.UNDERLINE_W, h: cv.UNDERLINE_H,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });
  }

  /** Regulatory / performance disclaimer (bottom-left footer). */
  addDisclaimer(slide, text) {
    const { cv } = this;
    const msg = text || 'Past performance does not guarantee future results. For financial professional use only.';
    slide.addText(msg, {
      x: cv.CX, y: cv.FOOTER_Y, w: cv.DISCLAIMER_W, h: cv.FOOTER_H,
      fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.07),
      color: _c(C.TONES.GRAY_40), align: 'left', italic: true,
    });
  }

  /** Slide-number indicator (bottom-right). */
  addSlideNumber(slide, current, total) {
    const { cv } = this;
    slide.addText(`${current} / ${total}`, {
      x: cv.SN_X, y: cv.FOOTER_Y, w: cv.SN_W, h: cv.FOOTER_H,
      fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.2),
      color: _c(C.TONES.GRAY_40), align: 'right',
    });
  }

  /**
   * Render a standard slide title + accent underline.
   * Returns { titleRight } for callers that need to know available x after logo gap.
   */
  _addSlideTitle(slide, titleText, opts = {}) {
    const { cv } = this;
    const fs = opts.fontSize || Math.round(cv.TITLE_FS * (opts.fsScale || 1));
    const w  = opts.w        || cv.CW - cv.LOGO_W - cv.COL_GAP;  // leave room for logo
    slide.addText(titleText.toUpperCase(), {
      x: cv.CX, y: cv.TITLE_Y, w, h: cv.TITLE_H,
      fontFace: F.HEADERS.family, fontSize: fs,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);
    return { titleRight: cv.CX + w };
  }


  // ════════════════════════════════════════════════════════════════════════════
  // COLUMN GEOMETRY HELPERS
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Returns { colW, gaps } for an n-column layout within the content area.
   * All math derived from cv.CW and cv.COL_GAP.
   */
  _colGeometry(n) {
    const { cv } = this;
    const totalGap = cv.COL_GAP * (n - 1);
    const colW     = (cv.CW - totalGap) / n;
    return { colW, gap: cv.COL_GAP };
  }

  /** Returns the left x-position of column `idx` (0-based) in an n-col layout. */
  _colX(idx, colW, gap) {
    const { cv } = this;
    return cv.CX + idx * (colW + gap);
  }

  /**
   * Format an array or string for bullet-point text blocks.
   * Returns a pptxgenjs text array (bullets) or plain string.
   * bulletIndent and paraSpace default to values proportional to the canvas width/height
   * so bullet rhythm scales automatically with any layout change.
   */
  _fmtContent(content, bulletIndent, paraSpace) {
    const { cv } = this;
    const indent = bulletIndent !== undefined ? bulletIndent : Math.round(cv.W * 0.9);
    const space  = paraSpace  !== undefined ? paraSpace  : Math.round(cv.H * 0.67);
    if (Array.isArray(content)) {
      return content.map(item => ({
        text: String(typeof item === 'object' ? (item.text || item) : item),
        options: {
          bullet:        { code: '25AA', indent },
          paraSpaceBefore: space,
        },
      }));
    }
    return String(content || '');
  }


  // ════════════════════════════════════════════════════════════════════════════
  // TITLE SLIDES
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Standard Title Slide — white background, centred title, bottom accent bar.
   */
  createStandardTitleSlide(title, subtitle = null, options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };

    // Full wordmark – top left
    this.addLogo(slide, { x: cv.CX, y: cv.MT, w: cv.WORDMARK_W, h: cv.WORDMARK_H }, 'light');

    // Centred main title — occupy the middle 60 % of the slide height
    const titleY = cv.H * 0.33;
    const titleH = cv.H * 0.2;
    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: titleY, w: cv.CW, h: titleH,
      fontFace: F.HEADERS.family,
      fontSize: Math.round(cv.W * 3.3),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });

    if (subtitle) {
      const subtitleY = titleY + titleH + cv.H * 0.04;
      slide.addText(subtitle, {
        x: cv.CX, y: subtitleY, w: cv.CW, h: cv.H * 0.107,
        fontFace: F.BODY.family,
        fontSize: Math.round(cv.W * 1.5),
        color: _c(C.TONES.GRAY_60),
        align: 'center', valign: 'middle',
      });
    }

    // Bottom accent bar
    const barH = cv.H * 0.013;
    const barY = cv.H * 0.733;
    slide.addShape(this.pptx.ShapeType.rect, {
      x: cv.CX, y: barY, w: cv.CW, h: barH,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });

    return slide;
  }

  /**
   * Executive Title Slide — dark background, white title, yellow tagline.
   */
  createExecutiveTitleSlide(title, subtitle = null, tagline = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };

    this.addLogo(slide, { x: cv.CX, y: cv.MT, w: cv.WORDMARK_W, h: cv.WORDMARK_H }, 'dark');

    const titleY = cv.H * 0.293;
    const titleH = cv.H * 0.24;
    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: titleY, w: cv.CW, h: titleH,
      fontFace: F.HEADERS.family,
      fontSize: Math.round(cv.W * 3.6),
      bold: true, color: _c(C.PRIMARY.WHITE),
      align: 'center', valign: 'middle',
    });

    if (subtitle) {
      const subtitleY = titleY + titleH + cv.H * 0.027;
      slide.addText(subtitle, {
        x: cv.CX, y: subtitleY, w: cv.CW, h: cv.H * 0.093,
        fontFace: F.BODY.family,
        fontSize: Math.round(cv.W * 1.65),
        color: _c(C.TONES.YELLOW_80),
        align: 'center', valign: 'middle',
      });
    }

    const accentY = cv.H * 0.727;
    const accentH = cv.H * 0.011;
    slide.addShape(this.pptx.ShapeType.rect, {
      x: cv.CX, y: accentY, w: cv.CW, h: accentH,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.YELLOW), width: 0 },
    });

    if (tagline) {
      slide.addText(tagline, {
        x: cv.CX, y: accentY + accentH + cv.H * 0.013, w: cv.CW, h: cv.H * 0.08,
        fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.35),
        color: _c(C.PRIMARY.YELLOW), align: 'center', valign: 'middle', italic: true,
      });
    }

    return slide;
  }

  /**
   * Section Divider — light-yellow background, full-height left accent bar.
   */
  createSectionDividerSlide(sectionTitle, description = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(C.TONES.YELLOW_20) };
    this.addStandardLogo(slide);

    const barW = cv.W * 0.0225;   // ≈ 0.3"
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0, y: 0, w: barW, h: cv.H,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });

    const titleX = barW + cv.ML * 0.6;
    const titleW = cv.W - titleX - cv.MR;
    slide.addText(sectionTitle.toUpperCase(), {
      x: titleX, y: cv.H * 0.333, w: titleW, h: cv.H * 0.2,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 3.15),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'left', valign: 'middle',
    });

    if (description) {
      slide.addText(description, {
        x: titleX, y: cv.H * 0.56, w: titleW, h: cv.H * 0.16,
        fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.35),
        color: _c(C.TONES.GRAY_60), align: 'left', valign: 'middle',
      });
    }

    return slide;
  }


  // ════════════════════════════════════════════════════════════════════════════
  // CORE CONTENT SLIDES
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Standard Content Slide — title + bullet list or paragraph body.
   */
  createContentSlide(title, content, options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title);

    const bodyFS   = Math.round(cv.H * 2.27);
    const showBullets = options.bullets !== false;

    if (Array.isArray(content) && showBullets) {
      slide.addText(this._fmtContent(content, 15, 6), {
        x: cv.CX, y: cv.BODY_Y, w: cv.CW, h: cv.BODY_H,
        fontFace: F.BODY.family, fontSize: bodyFS,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });
    } else {
      slide.addText(Array.isArray(content) ? content.join('\n') : String(content || ''), {
        x: cv.CX, y: cv.BODY_Y, w: cv.CW, h: cv.BODY_H,
        fontFace: F.BODY.family, fontSize: Math.round(bodyFS * 0.94),
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });
    }

    return slide;
  }

  /**
   * Two-Column Layout.
   * options: { leftHeader, rightHeader }
   */
  createTwoColumnSlide(title, leftContent, rightContent, options = {}) {
    const { cv }       = this;
    const slide        = this.pptx.addSlide();
    const { colW, gap } = this._colGeometry(2);
    slide.background   = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    const hasHeaders = options.leftHeader || options.rightHeader;
    const hdrY       = cv.BODY_Y;
    const hdrH       = cv.H * 0.067;
    const contentY   = hasHeaders ? hdrY + hdrH + cv.H * 0.013 : cv.BODY_Y;
    const contentH   = cv.H - contentY - cv.MB;
    const bodyFS     = Math.round(cv.H * 2.0);
    const hdrFS      = Math.round(cv.H * 1.87);

    [options.leftHeader, options.rightHeader].forEach((hdr, idx) => {
      if (!hdr) return;
      const x = this._colX(idx, colW, gap);
      slide.addText(hdr.toUpperCase(), {
        x, y: hdrY, w: colW, h: hdrH,
        fontFace: F.HEADERS.family, fontSize: hdrFS,
        bold: true, color: _c(this.palette.accent),
      });
    });

    [leftContent, rightContent].forEach((col, idx) => {
      const x = this._colX(idx, colW, gap);
      slide.addText(this._fmtContent(col, 10, 4), {
        x, y: contentY, w: colW, h: contentH,
        fontFace: F.BODY.family, fontSize: bodyFS,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });
    });

    // Subtle column separator
    const sepX = cv.CX + colW + gap / 2 - cv.W * 0.0015;
    const sepW = cv.W * 0.003;
    slide.addShape(this.pptx.ShapeType.rect, {
      x: sepX, y: contentY - cv.H * 0.013, w: sepW, h: contentH + cv.H * 0.013,
      fill: { color: _c(C.TONES.GRAY_20) },
      line: { color: _c(C.TONES.GRAY_20), width: 0 },
    });

    return slide;
  }

  /**
   * Three-Column Layout.
   * options: { headers: ['A', 'B', 'C'] }
   */
  createThreeColumnSlide(title, leftContent, centerContent, rightContent, options = {}) {
    const { cv }        = this;
    const slide         = this.pptx.addSlide();
    const { colW, gap } = this._colGeometry(3);
    slide.background    = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.8125 });

    const headers    = options.headers || [];
    const hasHeaders = headers.some(Boolean);
    const hdrY       = cv.BODY_Y;
    const hdrH       = cv.H * 0.067;
    const contentY   = hasHeaders ? hdrY + hdrH + cv.H * 0.013 : cv.BODY_Y;
    const contentH   = cv.H - contentY - cv.MB;
    const bodyFS     = Math.round(cv.H * 1.73);
    const hdrFS      = Math.round(cv.H * 1.73);
    const sepH       = cv.H * 0.733;
    const sepW       = cv.W * 0.00225;

    const columns = [leftContent, centerContent, rightContent];

    columns.forEach((content, idx) => {
      const x = this._colX(idx, colW, gap);

      if (headers[idx]) {
        slide.addText(headers[idx].toUpperCase(), {
          x, y: hdrY, w: colW, h: hdrH,
          fontFace: F.HEADERS.family, fontSize: hdrFS,
          bold: true, color: _c(this.palette.accent), align: 'center',
        });
        slide.addShape(this.pptx.ShapeType.rect, {
          x, y: hdrY + hdrH, w: colW, h: cv.H * 0.0053,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(this.palette.accent), width: 0 },
        });
      }

      slide.addText(this._fmtContent(content, 8, 3), {
        x, y: contentY, w: colW, h: contentH,
        fontFace: F.BODY.family, fontSize: bodyFS,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });

      // Separator between columns (not after last)
      if (idx < 2) {
        const sepX = x + colW + gap / 2 - sepW / 2;
        slide.addShape(this.pptx.ShapeType.rect, {
          x: sepX, y: cv.BODY_Y - cv.H * 0.027, w: sepW, h: sepH,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }
    });

    return slide;
  }

  /**
   * Quote / Testimonial Slide — light-yellow background.
   */
  createQuoteSlide(quote, attribution = null, context = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(C.TONES.YELLOW_20) };
    this.addStandardLogo(slide);

    const markX = cv.CX;
    const markW = cv.W * 0.075;
    const markY = cv.H * 0.2;
    const markH = cv.H * 0.133;
    slide.addText('\u201C', {
      x: markX, y: markY, w: markW, h: markH,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 9.6),
      bold: true, color: _c(this.palette.accent), align: 'center',
    });

    const quoteX = cv.CX + markW + cv.W * 0.015;
    const quoteW = cv.CW - markW - cv.W * 0.015;
    const quoteY = cv.H * 0.267;
    const quoteH = cv.H * 0.373;
    slide.addText(quote, {
      x: quoteX, y: quoteY, w: quoteW, h: quoteH,
      fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.65),
      color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle', italic: true,
    });

    if (attribution) {
      const attrY = quoteY + quoteH + cv.H * 0.04;
      slide.addText(`\u2014 ${attribution}`, {
        x: quoteX, y: attrY, w: quoteW, h: cv.H * 0.107,
        fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.2),
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }

    if (context) {
      const ctxY = cv.H * 0.787;
      slide.addText(context, {
        x: quoteX, y: ctxY, w: quoteW, h: cv.H * 0.08,
        fontFace: F.BODY.family, fontSize: Math.round(cv.W * 0.9),
        color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }

    return slide;
  }

  /**
   * Metrics / KPI Slide — up to 6 large stat cards in a responsive grid.
   * metrics = [{ value, label, sublabel? }, ...]
   */
  createMetricSlide(title, metrics, context = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.9375 });

    const safe   = (Array.isArray(metrics) ? metrics : []).slice(0, 6);
    const cols   = Math.min(3, safe.length) || 1;
    const rows   = Math.ceil(safe.length / cols);
    const colW   = cv.CW / cols;
    const pad    = cv.W * 0.019;

    // Vertical space available for cards
    const cardsTop = cv.BODY_Y;
    const cardsBot = context ? cv.H - cv.MB - cv.H * 0.093 : cv.H - cv.MB;
    const totalH   = cardsBot - cardsTop;
    const rowGap   = cv.H * 0.027;
    const cardH    = (totalH - rowGap * (rows - 1)) / rows;

    safe.forEach((metric, idx) => {
      const col   = idx % cols;
      const row   = Math.floor(idx / cols);
      const cardX = cv.CX + col * colW;
      const cardY = cardsTop + row * (cardH + rowGap);
      const cW    = colW - pad;

      slide.addShape(this.pptx.ShapeType.rect, {
        x: cardX, y: cardY, w: cW, h: cardH,
        fill: { color: _c(C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_20), width: 0 },
      });

      const valueFS = cols <= 2 ? Math.round(cv.W * 3.9) : Math.round(cv.W * 3.0);
      slide.addText(String(metric.value), {
        x: cardX, y: cardY + cardH * 0.08, w: cW, h: cardH * 0.52,
        fontFace: F.HEADERS.family, fontSize: valueFS,
        bold: true, color: _c(this.palette.accent),
        align: 'center', valign: 'middle',
      });

      slide.addText(String(metric.label || ''), {
        x: cardX, y: cardY + cardH * 0.62, w: cW, h: cardH * 0.22,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.73),
        color: _c(C.TONES.GRAY_60), align: 'center',
      });

      if (metric.sublabel) {
        slide.addText(String(metric.sublabel), {
          x: cardX, y: cardY + cardH * 0.84, w: cW, h: cardH * 0.14,
          fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.33),
          color: _c(C.TONES.GRAY_40), align: 'center', italic: true,
        });
      }
    });

    if (context) {
      const ctxY = cardsBot + cv.H * 0.013;
      slide.addText(String(context), {
        x: cv.CX, y: ctxY, w: cv.CW, h: cv.H * 0.08,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.33),
        color: _c(C.TONES.GRAY_60), align: 'center', italic: true,
      });
    }

    return slide;
  }

  /**
   * Process / Workflow Slide.
   * options.layout = 'horizontal' (default) | 'vertical'
   * steps = [{ title, description }, ...]
   */
  createProcessSlide(title, steps, options = {}) {
    const { cv }   = this;
    const slide    = this.pptx.addSlide();
    const vertical = options.layout === 'vertical';
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    const safeSteps = (steps || []).slice(0, vertical ? 6 : 5);

    if (!vertical) {
      // ── HORIZONTAL ────────────────────────────────────────────────────────
      const stepW   = cv.CW / safeSteps.length;
      const circleY = cv.H * 0.427;
      const R       = cv.H * 0.0467;   // circle radius ≈ 0.35"

      safeSteps.forEach((step, idx) => {
        const cx = cv.CX + idx * stepW + stepW / 2;

        slide.addShape(this.pptx.ShapeType.ellipse, {
          x: cx - R, y: circleY - R, w: R * 2, h: R * 2,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
        });

        slide.addText(String(idx + 1), {
          x: cx - R, y: circleY - R, w: R * 2, h: R * 2,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 2.4),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
          align: 'center', valign: 'middle',
        });

        const labelY = circleY + R + cv.H * 0.013;
        const labelW = stepW - cv.W * 0.008;
        const labelX = cx - stepW / 2 + cv.W * 0.004;

        slide.addText((step.title || `Step ${idx + 1}`).toUpperCase(), {
          x: labelX, y: labelY, w: labelW, h: cv.H * 0.08,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.6),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
        });

        if (step.description) {
          slide.addText(String(step.description), {
            x: labelX, y: labelY + cv.H * 0.093, w: labelW, h: cv.H * 0.293,
            fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.47),
            color: _c(C.TONES.GRAY_60), align: 'center', valign: 'top',
          });
        }

        // Arrow connector between steps
        if (idx < safeSteps.length - 1) {
          const nextCX = cv.CX + (idx + 1) * stepW + stepW / 2;
          const arrowX = cx + R + cv.W * 0.004;
          const lineW  = (nextCX - R - cv.W * 0.004 - arrowX) * 0.75;
          const arrowW = cv.W * 0.019;

          slide.addShape(this.pptx.ShapeType.line, {
            x: arrowX, y: circleY, w: lineW, h: 0,
            line: { color: _c(C.TONES.GRAY_40), width: 2 },
          });
          slide.addShape(this.pptx.ShapeType.rightArrow, {
            x: arrowX + lineW - arrowW / 2, y: circleY - cv.H * 0.016,
            w: arrowW, h: cv.H * 0.033,
            fill: { color: _c(C.TONES.GRAY_40) },
            line: { color: _c(C.TONES.GRAY_40), width: 0 },
          });
        }
      });

    } else {
      // ── VERTICAL ──────────────────────────────────────────────────────────
      const availH = cv.H - cv.BODY_Y - cv.MB;
      const stepH  = availH / safeSteps.length;
      const R      = cv.H * 0.04;   // circle radius ≈ 0.3"
      const lineX  = cv.CX + R;
      const textX  = cv.CX + R * 2 + cv.W * 0.008;
      const textW  = cv.CW - R * 2 - cv.W * 0.008;

      safeSteps.forEach((step, idx) => {
        const y = cv.BODY_Y + idx * stepH;

        slide.addShape(this.pptx.ShapeType.ellipse, {
          x: cv.CX, y, w: R * 2, h: R * 2,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
        });
        slide.addText(String(idx + 1), {
          x: cv.CX, y, w: R * 2, h: R * 2,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 2.13),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
          align: 'center', valign: 'middle',
        });

        slide.addText((step.title || `Step ${idx + 1}`).toUpperCase(), {
          x: textX, y: y + cv.H * 0.003, w: textW, h: R * 0.9,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.73),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        });

        if (step.description) {
          slide.addText(String(step.description), {
            x: textX, y: y + R * 0.9, w: textW, h: stepH - R * 0.9 - cv.H * 0.013,
            fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.47),
            color: _c(C.TONES.GRAY_60), valign: 'top',
          });
        }

        if (idx < safeSteps.length - 1) {
          slide.addShape(this.pptx.ShapeType.line, {
            x: lineX, y: y + R * 2, w: 0, h: stepH - R * 2 - cv.H * 0.007,
            line: { color: _c(C.TONES.GRAY_40), width: 2 },
          });
        }
      });
    }

    return slide;
  }


  // ════════════════════════════════════════════════════════════════════════════
  // CLOSING SLIDES
  // ════════════════════════════════════════════════════════════════════════════

  createClosingSlide(title = 'THANK YOU', contactInfo = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };

    // Centred full wordmark
    const markX = (cv.W - cv.WORDMARK_W) / 2;
    this.addLogo(slide, { x: markX, y: cv.H * 0.2, w: cv.WORDMARK_W, h: cv.WORDMARK_H }, 'light');

    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: cv.H * 0.373, w: cv.CW, h: cv.H * 0.133,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 3.0),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText(contactInfo || DEFAULT_CONTACT_INFO, {
      x: cv.CX, y: cv.H * 0.733, w: cv.CW, h: cv.H * 0.2,
      fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.05),
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }

  createCallToActionSlide(title, actionText, contactInfo, buttonText = 'GET STARTED') {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: cv.H * 0.2, w: cv.CW, h: cv.H * 0.16,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 2.55),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText(String(actionText || ''), {
      x: cv.CX, y: cv.H * 0.4, w: cv.CW, h: cv.H * 0.2,
      fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.35),
      color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    // CTA button — centred horizontally
    const btnW = cv.CW * 0.225;   // ≈ 2.75" at standard CW
    const btnH = cv.H * 0.107;    // ≈ 0.8"
    const btnX = (cv.W - btnW) / 2;
    const btnY = cv.H * 0.64;

    slide.addShape(this.pptx.ShapeType.rect, {
      x: btnX, y: btnY, w: btnW, h: btnH,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });
    slide.addText(buttonText.toUpperCase(), {
      x: btnX, y: btnY, w: btnW, h: btnH,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 1.2),
      bold: true, color: _c(C.PRIMARY.WHITE),
      align: 'center', valign: 'middle',
    });

    slide.addText(String(contactInfo || DEFAULT_CONTACT_INLINE), {
      x: cv.CX, y: cv.H * 0.8, w: cv.CW, h: cv.H * 0.133,
      fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.05),
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  // ════════════════════════════════════════════════════════════════════════════
  // EXTENDED SLIDE TYPES
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Executive Summary — dark background, large headline, yellow-accented bullets.
   */
  createExecutiveSummarySlide(headline, points = [], context = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };
    this.addStandardLogo(slide, 'dark');

    slide.addText((headline || 'EXECUTIVE SUMMARY').toUpperCase(), {
      x: cv.CX, y: cv.H * 0.053, w: cv.CW - cv.LOGO_W - cv.COL_GAP, h: cv.H * 0.147,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 2.55),
      bold: true, color: _c(C.PRIMARY.WHITE),
    });

    slide.addShape(this.pptx.ShapeType.rect, {
      x: cv.CX, y: cv.H * 0.193, w: cv.CW * 0.187, h: cv.H * 0.009,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.YELLOW), width: 0 },
    });

    const bulletItems = (points || []).slice(0, 6).map(p => ({
      text: String(p),
      options: {
        bullet:          { code: '25BA', indent: 12 },
        color:           _c(C.PRIMARY.WHITE),
        paraSpaceBefore: 8,
      },
    }));

    slide.addText(bulletItems.length ? bulletItems : [{ text: '', options: {} }], {
      x: cv.CX, y: cv.H * 0.227, w: cv.CW, h: cv.H * 0.693,
      fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.35),
      color: _c(C.PRIMARY.WHITE), valign: 'top',
    });

    if (context) {
      slide.addText(String(context), {
        x: cv.CX, y: cv.H * 0.92, w: cv.CW, h: cv.H * 0.053,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.2),
        color: _c(C.TONES.GRAY_60), align: 'center', italic: true,
      });
    }

    return slide;
  }

  /**
   * Card Grid — 2×2 or 1×4 coloured content cards.
   * cards = [{ title, text, color: 'yellow'|'dark'|'white'|'turquoise' }, ...]
   */
  createCardGridSlide(title, cards = [], options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    const safe  = (cards || []).slice(0, 4);
    const count = safe.length || 1;
    const cols  = count <= 2 ? count : 2;
    const rows  = Math.ceil(count / cols);

    const gapX   = cv.W * 0.0375;
    const gapY   = cv.H * 0.04;
    const cardW  = cols === 1 ? cv.CW : (cv.CW - gapX * (cols - 1)) / cols;
    const cardsH = cv.H - cv.BODY_Y - cv.MB;
    const cardH  = (cardsH - gapY * (rows - 1)) / rows;

    const COLOR_MAP = {
      yellow:    { bg: _c(C.PRIMARY.YELLOW),      hdr: _c(C.PRIMARY.DARK_GRAY), txt: _c(C.PRIMARY.DARK_GRAY) },
      dark:      { bg: _c(C.PRIMARY.DARK_GRAY),   hdr: _c(C.PRIMARY.WHITE),     txt: _c(C.PRIMARY.WHITE) },
      white:     { bg: _c(C.TONES.GRAY_20),       hdr: _c(C.PRIMARY.DARK_GRAY), txt: _c(C.PRIMARY.DARK_GRAY) },
      turquoise: { bg: _c(C.SECONDARY.TURQUOISE), hdr: _c(C.PRIMARY.DARK_GRAY), txt: _c(C.PRIMARY.DARK_GRAY) },
    };
    const DEFAULT_ORDER = ['yellow', 'dark', 'white', 'turquoise'];

    safe.forEach((card, idx) => {
      const col    = idx % cols;
      const row    = Math.floor(idx / cols);
      const x      = cv.CX + col * (cardW + gapX);
      const y      = cv.BODY_Y + row * (cardH + gapY);
      const scheme = COLOR_MAP[card.color] || COLOR_MAP[DEFAULT_ORDER[idx % 4]];
      const padX   = cardW * 0.033;
      const padY   = cardH * 0.067;

      slide.addShape(this.pptx.ShapeType.rect, {
        x, y, w: cardW, h: cardH,
        fill: { color: scheme.bg },
        line: { color: scheme.bg, width: 0 },
      });

      if (card.title) {
        const hdrFS = rows > 1 ? Math.round(cv.H * 1.73) : Math.round(cv.H * 2.27);
        slide.addText(card.title.toUpperCase(), {
          x: x + padX, y: y + padY, w: cardW - padX * 2, h: cardH * 0.35,
          fontFace: F.HEADERS.family, fontSize: hdrFS,
          bold: true, color: scheme.hdr, align: 'left', valign: 'middle',
        });
      }

      if (card.text) {
        const bodyFS = rows > 1 ? Math.round(cv.H * 1.47) : Math.round(cv.H * 1.87);
        slide.addText(String(card.text), {
          x: x + padX, y: y + cardH * 0.42, w: cardW - padX * 2, h: cardH * 0.5,
          fontFace: F.BODY.family, fontSize: bodyFS,
          color: scheme.txt, align: 'left', valign: 'top',
        });
      }
    });

    return slide;
  }

  /**
   * Icon Grid — circular icon badges in a responsive grid.
   * items = [{ icon, title, description }, ...]
   */
  createIconGridSlide(title, items = [], options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    const safe  = (items || []).slice(0, 6);
    const cols  = Math.min(3, safe.length) || 1;
    const rows  = Math.ceil(safe.length / cols);
    const itemW = cv.CW / cols;
    const gapY  = cv.H * 0.04;
    const itemH = (cv.H - cv.BODY_Y - cv.MB - gapY * (rows - 1)) / rows;

    safe.forEach((item, idx) => {
      const col  = idx % cols;
      const row  = Math.floor(idx / cols);
      const cx   = cv.CX + col * itemW + itemW / 2;
      const y    = cv.BODY_Y + row * (itemH + gapY);
      const R    = rows > 1 ? cv.H * 0.05 : cv.H * 0.073;  // circle radius

      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: cx - R, y, w: R * 2, h: R * 2,
        fill: { color: _c(this.palette.accent) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1 },
      });
      slide.addText(String(item.icon || idx + 1), {
        x: cx - R, y, w: R * 2, h: R * 2,
        fontFace: F.HEADERS.family, fontSize: R > cv.H * 0.06 ? Math.round(cv.H * 2.67) : Math.round(cv.H * 2.0),
        bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });

      if (item.title) {
        slide.addText(item.title.toUpperCase(), {
          x: cx - itemW / 2 + cv.W * 0.008, y: y + R * 2 + cv.H * 0.013,
          w: itemW - cv.W * 0.015, h: cv.H * 0.067,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.6),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
        });
      }

      if (item.description) {
        const descY = y + R * 2 + cv.H * 0.013 + cv.H * 0.08;
        slide.addText(String(item.description), {
          x: cx - itemW / 2 + cv.W * 0.008, y: descY,
          w: itemW - cv.W * 0.015, h: itemH - R * 2 - cv.H * 0.1,
          fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.47),
          color: _c(C.TONES.GRAY_60), align: 'center', valign: 'top',
        });
      }
    });

    return slide;
  }

  /**
   * Hub & Spoke — central hub with up to 6 peripheral nodes.
   * center = { title, subtitle };  nodes = [{ label, description? }, ...]
   */
  createHubSpokeSlide(title, center = {}, nodes = []) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: cv.TITLE_Y, w: cv.CW - cv.LOGO_W - cv.COL_GAP, h: cv.TITLE_H,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.TITLE_FS * 0.75),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    // Hub centre — vertically below title, horizontally centred
    const HUB_CX = cv.W / 2;
    const HUB_CY = cv.BODY_Y + (cv.H - cv.BODY_Y - cv.MB) * 0.55;
    const HUB_R  = cv.H * 0.12;   // ≈ 0.9"

    slide.addShape(this.pptx.ShapeType.ellipse, {
      x: HUB_CX - HUB_R, y: HUB_CY - HUB_R, w: HUB_R * 2, h: HUB_R * 2,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2.5 },
    });
    slide.addText((center.title || 'POTOMAC').toUpperCase(), {
      x: HUB_CX - HUB_R, y: HUB_CY - HUB_R + cv.H * 0.02, w: HUB_R * 2, h: HUB_R * 0.9,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 2.13),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });
    if (center.subtitle) {
      slide.addText(String(center.subtitle), {
        x: HUB_CX - HUB_R, y: HUB_CY + HUB_R * 0.1, w: HUB_R * 2, h: HUB_R * 0.5,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.33),
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });
    }

    const safeNodes = (nodes || []).slice(0, 6);
    const SPOKE_R   = cv.H * 0.347;   // ≈ 2.6"
    const NODE_R    = cv.H * 0.0733;  // ≈ 0.55"
    const NODE_COLORS = [
      _c(C.SECONDARY.TURQUOISE), _c(C.TONES.GRAY_20),   _c(C.TONES.YELLOW_40),
      _c(C.SECONDARY.TURQUOISE), _c(C.TONES.GRAY_20),   _c(C.TONES.YELLOW_40),
    ];

    safeNodes.forEach((node, idx) => {
      const angle = (idx / safeNodes.length) * 2 * Math.PI - Math.PI / 2;
      const nx    = HUB_CX + SPOKE_R * Math.cos(angle);
      const ny    = HUB_CY + SPOKE_R * Math.sin(angle);

      // Spoke line from hub edge to node edge
      slide.addShape(this.pptx.ShapeType.line, {
        x: HUB_CX + HUB_R  * Math.cos(angle),
        y: HUB_CY + HUB_R  * Math.sin(angle),
        w: (SPOKE_R - NODE_R - HUB_R) * Math.cos(angle),
        h: (SPOKE_R - NODE_R - HUB_R) * Math.sin(angle),
        line: { color: _c(C.TONES.GRAY_40), width: 1.5 },
      });

      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: nx - NODE_R, y: ny - NODE_R, w: NODE_R * 2, h: NODE_R * 2,
        fill: { color: NODE_COLORS[idx % NODE_COLORS.length] },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
      });
      slide.addText((node.label || `Node ${idx + 1}`).toUpperCase(), {
        x: nx - NODE_R, y: ny - NODE_R, w: NODE_R * 2, h: NODE_R * 2,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.2),
        bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });
    });

    return slide;
  }

  /**
   * Timeline Slide — horizontal milestone track.
   * milestones = [{ label, date, status: 'complete'|'in_progress'|'pending' }, ...]
   */
  createTimelineSlide(title, milestones = []) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    const safe    = (milestones || []).slice(0, 8);
    const TL_XMIN = cv.CX + cv.CW * 0.02;
    const TL_XMAX = cv.CX + cv.CW * 0.98;
    const TL_W    = TL_XMAX - TL_XMIN;
    const TL_Y    = cv.H * 0.507;    // ≈ 3.8"
    const tickH   = cv.H * 0.213;    // ≈ 1.6"
    const MR      = cv.H * 0.027;    // marker radius ≈ 0.2"

    // Baseline
    slide.addShape(this.pptx.ShapeType.line, {
      x: TL_XMIN, y: TL_Y, w: TL_W, h: 0,
      line: { color: _c(C.TONES.GRAY_40), width: 2.5 },
    });

    const STATUS_COLORS = {
      complete:    _c(C.PRIMARY.YELLOW),
      in_progress: _c(C.SECONDARY.TURQUOISE),
      pending:     _c(C.TONES.GRAY_40),
    };

    safe.forEach((ms, idx) => {
      const xPos    = TL_XMIN + (TL_W * (idx + 0.5)) / safe.length;
      const isAbove = idx % 2 === 0;
      const status  = ms.status || 'pending';
      const tickTop = isAbove ? TL_Y - tickH : TL_Y;
      const labelW  = (TL_W / safe.length) * 0.9;
      const labelY  = isAbove ? TL_Y - tickH - cv.H * 0.08 : TL_Y + tickH + cv.H * 0.027;

      // Tick
      slide.addShape(this.pptx.ShapeType.line, {
        x: xPos, y: tickTop, w: 0, h: tickH,
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });

      // Marker dot
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: xPos - MR, y: TL_Y - MR, w: MR * 2, h: MR * 2,
        fill: { color: STATUS_COLORS[status] || STATUS_COLORS.pending },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
      });

      // Label
      slide.addText(String(ms.label || `M${idx + 1}`), {
        x: xPos - labelW / 2, y: labelY, w: labelW, h: cv.H * 0.067,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.47),
        bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });

      if (ms.date) {
        slide.addText(String(ms.date), {
          x: xPos - labelW / 2, y: labelY + cv.H * 0.067, w: labelW, h: cv.H * 0.051,
          fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.33),
          color: _c(C.TONES.GRAY_60), align: 'center',
        });
      }
    });

    return slide;
  }

  /**
   * 2×2 Matrix Slide — quadrant analysis.
   * quadrants order: top-left, top-right, bottom-left, bottom-right
   * quadrants = [{ title, text, color? }, ...]
   */
  createMatrix2x2Slide(title, xAxisLabel = '', yAxisLabel = '', quadrants = []) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: cv.TITLE_Y, w: cv.CW - cv.LOGO_W - cv.COL_GAP, h: cv.TITLE_H,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.TITLE_FS * 0.8),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    // Matrix occupies the content area; leave room for y-axis label
    const yLabelW = cv.W * 0.075;
    const axisLabelH = cv.H * 0.047;
    const matrixX    = cv.CX + yLabelW;
    const matrixBot  = cv.H - cv.MB - axisLabelH;
    const matrixTop  = cv.BODY_Y;
    const matrixH    = matrixBot - matrixTop;
    const matrixW    = cv.CW - yLabelW;

    const GAP = cv.W * 0.0075;
    const QW  = (matrixW - GAP) / 2;
    const QH  = (matrixH - GAP) / 2;

    const DEFAULT_Q = [
      { title: 'HIGH VALUE\nLOW RISK',  color: C.PRIMARY.YELLOW },
      { title: 'HIGH VALUE\nHIGH RISK', color: C.SECONDARY.TURQUOISE },
      { title: 'LOW VALUE\nLOW RISK',   color: C.TONES.GRAY_20 },
      { title: 'LOW VALUE\nHIGH RISK',  color: C.TONES.GRAY_40 },
    ];
    const q4 = [0, 1, 2, 3].map(i => quadrants[i] || DEFAULT_Q[i]);

    [[0, 0], [1, 0], [0, 1], [1, 1]].forEach(([col, row], idx) => {
      const q   = q4[idx];
      const qx  = matrixX + col * (QW + GAP);
      const qy  = matrixTop + row * (QH + GAP);
      const padX = QW * 0.03;
      const padY = QH * 0.056;

      slide.addShape(this.pptx.ShapeType.rect, {
        x: qx, y: qy, w: QW, h: QH,
        fill: { color: _c(q.color || C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });

      if (q.title) {
        slide.addText(q.title.toUpperCase(), {
          x: qx + padX, y: qy + padY, w: QW - padX * 2, h: QH * 0.315,
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.73),
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
        });
      }

      if (q.text) {
        slide.addText(String(q.text), {
          x: qx + padX, y: qy + QH * 0.38, w: QW - padX * 2, h: QH * 0.56,
          fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.6),
          color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
        });
      }
    });

    // Centre axis lines
    const axisX = matrixX + QW + GAP / 2;
    const axisY = matrixTop + QH + GAP / 2;
    slide.addShape(this.pptx.ShapeType.line, {
      x: matrixX, y: axisY, w: matrixW, h: 0,
      line: { color: _c(C.TONES.GRAY_60), width: 2 },
    });
    slide.addShape(this.pptx.ShapeType.line, {
      x: axisX, y: matrixTop, w: 0, h: matrixH,
      line: { color: _c(C.TONES.GRAY_60), width: 2 },
    });

    if (xAxisLabel) {
      slide.addText(xAxisLabel.toUpperCase(), {
        x: matrixX, y: matrixBot + cv.H * 0.013, w: matrixW, h: axisLabelH,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.47),
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }

    if (yAxisLabel) {
      slide.addText(yAxisLabel.toUpperCase(), {
        x: cv.CX, y: matrixTop, w: yLabelW, h: matrixH,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.47),
        bold: true, color: _c(C.TONES.GRAY_60),
        align: 'center', valign: 'middle', rotate: 270,
      });
    }

    return slide;
  }

  /**
   * Scorecard / KPI Dashboard.
   * metrics = [{ label, value, target?, change?, status: 'green'|'yellow'|'red' }, ...]
   */
  createScorecardSlide(title, metrics = [], subtitle = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    if (subtitle) {
      slide.addText(subtitle, {
        x: cv.CX, y: cv.BODY_Y - cv.H * 0.04, w: cv.CW * 0.9, h: cv.H * 0.051,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.73),
        color: _c(C.TONES.GRAY_60),
      });
    }

    const safe      = (metrics || []).slice(0, 8);
    const headerY   = subtitle ? cv.BODY_Y + cv.H * 0.013 : cv.BODY_Y;
    const headerH   = cv.H * 0.06;
    const available = cv.H - headerY - headerH - cv.MB;
    const rowH      = Math.min(cv.H * 0.096, available / Math.max(safe.length, 1));

    // Column x-positions and widths as fractions of CW — all derived, none fixed
    const colDefs = [
      { frac: 0.0,   wFrac: 0.381 },  // KPI label
      { frac: 0.381, wFrac: 0.162 },  // CURRENT
      { frac: 0.543, wFrac: 0.138 },  // TARGET
      { frac: 0.681, wFrac: 0.15 },   // CHANGE
      { frac: 0.831, wFrac: 0.113 },  // STATUS
    ];
    const HDRS    = ['KPI / METRIC', 'CURRENT', 'TARGET', 'CHANGE', 'STATUS'];
    const STATUS_C = {
      green:  _c(C.SECONDARY.TURQUOISE),
      yellow: _c(C.PRIMARY.YELLOW),
      red:    _c(C.SECONDARY.PINK),
    };

    // Header row
    slide.addShape(this.pptx.ShapeType.rect, {
      x: cv.CX, y: headerY, w: cv.CW, h: headerH,
      fill: { color: _c(C.PRIMARY.DARK_GRAY) },
      line: { color: _c(C.PRIMARY.DARK_GRAY), width: 0 },
    });

    HDRS.forEach((h, i) => {
      const { frac, wFrac } = colDefs[i];
      slide.addText(h, {
        x: cv.CX + cv.CW * frac, y: headerY + headerH * 0.067,
        w: cv.CW * wFrac, h: headerH * 0.867,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.47),
        bold: true, color: _c(C.PRIMARY.WHITE),
        valign: 'middle', align: i === 0 ? 'left' : 'center',
      });
    });

    safe.forEach((m, idx) => {
      const y   = headerY + headerH + idx * rowH;
      const alt = idx % 2 === 1;
      const fs  = Math.min(Math.round(cv.H * 1.6), rowH * 14);

      if (alt) {
        slide.addShape(this.pptx.ShapeType.rect, {
          x: cv.CX, y, w: cv.CW, h: rowH,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }

      const cells = [
        { v: m.label  || '',  ci: 0, bold: true,  color: _c(C.PRIMARY.DARK_GRAY), align: 'left' },
        { v: m.value  || '—', ci: 1, bold: true,  color: _c(this.palette.accent), align: 'center' },
        { v: m.target || '—', ci: 2, bold: false, color: _c(C.PRIMARY.DARK_GRAY), align: 'center' },
        { v: m.change || '—', ci: 3, bold: false, color: _c(C.PRIMARY.DARK_GRAY), align: 'center' },
      ];

      cells.forEach(cell => {
        const { frac, wFrac } = colDefs[cell.ci];
        slide.addText(String(cell.v), {
          x: cv.CX + cv.CW * frac, y: y + rowH * 0.053, w: cv.CW * wFrac, h: rowH * 0.893,
          fontFace: F.BODY.family, fontSize: fs,
          bold: cell.bold, color: cell.color,
          align: cell.align, valign: 'middle',
        });
      });

      // Status circle in the last column
      const sc     = STATUS_C[m.status] || STATUS_C.yellow;
      const circR  = rowH * 0.3;
      const { frac, wFrac } = colDefs[4];
      const circCX = cv.CX + cv.CW * frac + (cv.CW * wFrac) / 2;
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: circCX - circR, y: y + rowH / 2 - circR, w: circR * 2, h: circR * 2,
        fill: { color: sc }, line: { color: sc, width: 0 },
      });
    });

    return slide;
  }

  /**
   * Comparison — labelled side-by-side A vs B.
   * rows = [{ label, left, right }, ...]
   * winner = 'left' | 'right' | null
   */
  createComparisonSlide(title, leftLabel = 'OPTION A', rightLabel = 'OPTION B', rows = [], winner = null) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: cv.CX, y: cv.TITLE_Y, w: cv.CW - cv.LOGO_W - cv.COL_GAP, h: cv.TITLE_H,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.TITLE_FS * 0.8),
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    // Each option column: (CW - VS_width) / 2
    const VS_W  = cv.CW * 0.04;
    const COL_W = (cv.CW - VS_W) / 2;
    const HDR_Y = cv.BODY_Y;
    const HDR_H = cv.H * 0.08;

    const safeRows = (rows || []).slice(0, 8);
    const available = cv.H - HDR_Y - HDR_H - cv.MB;
    const rowH      = Math.min(cv.H * 0.096, available / Math.max(safeRows.length, 1));

    const lX = cv.CX;
    const rX = cv.CX + COL_W + VS_W;
    const vsX = cv.CX + COL_W;

    const lWin           = winner === 'left';
    const rWin           = winner === 'right';
    const leftHdrFill    = lWin ? _c(C.PRIMARY.YELLOW)    : _c(C.PRIMARY.DARK_GRAY);
    const rightHdrFill   = rWin ? _c(C.PRIMARY.YELLOW)    : _c(C.PRIMARY.DARK_GRAY);
    const leftHdrText    = lWin ? _c(C.PRIMARY.DARK_GRAY) : _c(C.PRIMARY.WHITE);
    const rightHdrText   = rWin ? _c(C.PRIMARY.DARK_GRAY) : _c(C.PRIMARY.WHITE);

    slide.addShape(this.pptx.ShapeType.rect, {
      x: lX, y: HDR_Y, w: COL_W, h: HDR_H,
      fill: { color: leftHdrFill }, line: { color: leftHdrFill, width: 0 },
    });
    slide.addText(leftLabel.toUpperCase(), {
      x: lX, y: HDR_Y, w: COL_W, h: HDR_H,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.87),
      bold: true, color: leftHdrText, align: 'center', valign: 'middle',
    });

    slide.addShape(this.pptx.ShapeType.rect, {
      x: rX, y: HDR_Y, w: COL_W, h: HDR_H,
      fill: { color: rightHdrFill }, line: { color: rightHdrFill, width: 0 },
    });
    slide.addText(rightLabel.toUpperCase(), {
      x: rX, y: HDR_Y, w: COL_W, h: HDR_H,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.87),
      bold: true, color: rightHdrText, align: 'center', valign: 'middle',
    });

    slide.addText('VS', {
      x: vsX, y: HDR_Y + HDR_H * 0.125, w: VS_W, h: HDR_H * 0.75,
      fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.6),
      bold: true, color: _c(C.TONES.GRAY_40), align: 'center',
    });

    safeRows.forEach((row, idx) => {
      const y   = HDR_Y + HDR_H + idx * rowH;
      const alt = idx % 2 === 1;
      const fs  = Math.min(Math.round(cv.H * 1.6), rowH * 13);

      if (alt) {
        slide.addShape(this.pptx.ShapeType.rect, {
          x: cv.CX, y, w: cv.CW, h: rowH,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }

      const cellPad = cv.W * 0.008;
      slide.addText(String(row.label || `Point ${idx + 1}`), {
        x: vsX, y: y + rowH * 0.067, w: VS_W, h: rowH * 0.867,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.33),
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center', valign: 'middle',
      });
      slide.addText(String(row.left  || '—'), {
        x: lX + cellPad, y: y + rowH * 0.067, w: COL_W - cellPad * 2, h: rowH * 0.867,
        fontFace: F.BODY.family, fontSize: fs,
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center', valign: 'middle',
      });
      slide.addText(String(row.right || '—'), {
        x: rX + cellPad, y: y + rowH * 0.067, w: COL_W - cellPad * 2, h: rowH * 0.867,
        fontFace: F.BODY.family, fontSize: fs,
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center', valign: 'middle',
      });
    });

    return slide;
  }

  /**
   * Table Slide — branded data table.
   * options: { highlightColumn, disclaimer }
   */
  createTableSlide(title, headers = [], rows = [], options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.875 });

    if (!headers.length || !rows.length) {
      slide.addText('No data provided', {
        x: cv.CX, y: cv.H * 0.267, w: cv.CW, h: cv.H * 0.133,
        fontFace: F.BODY.family, fontSize: Math.round(cv.W * 1.2),
        color: _c(C.TONES.GRAY_60), align: 'center',
      });
      return slide;
    }

    const highlightCol = options.highlightColumn !== undefined ? options.highlightColumn : headers.length - 1;
    const safeRows     = rows.slice(0, 10);
    const tblH         = Math.min(cv.H - cv.BODY_Y - cv.MB, (safeRows.length + 1) * cv.H * 0.067);

    const tableData = [
      headers.map((h, ci) => ({
        text: String(h).toUpperCase(),
        options: {
          bold: true, align: 'center', valign: 'middle',
          fontFace: F.HEADERS.family, fontSize: Math.round(cv.H * 1.6),
          color: _c(C.PRIMARY.DARK_GRAY),
          fill: { color: ci === highlightCol ? _c(C.SECONDARY.TURQUOISE) : _c(C.PRIMARY.YELLOW) },
        },
      })),
      ...safeRows.map((row, ri) => {
        const alt = ri % 2 === 1;
        return (Array.isArray(row) ? row : [row]).map((cell, ci) => ({
          text: String(cell),
          options: {
            fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.47),
            align: ci === 0 ? 'left' : 'center', valign: 'middle',
            bold:  ci === highlightCol,
            color: ci === highlightCol ? _c(C.SECONDARY.TURQUOISE) : _c(C.PRIMARY.DARK_GRAY),
            fill:  { color: alt ? _c(C.TONES.YELLOW_20) : _c(C.PRIMARY.WHITE) },
          },
        }));
      }),
    ];

    slide.addTable(tableData, {
      x: cv.CX, y: cv.BODY_Y, w: cv.CW, h: tblH,
      border: { pt: 0.5, color: _c(C.TONES.GRAY_40) },
      margin: cv.H * 0.007,
    });

    if (options.disclaimer) this.addDisclaimer(slide, options.disclaimer);

    return slide;
  }

  /**
   * Chart Slide — native PptxGenJS chart.
   * chartType: 'bar' | 'line' | 'pie' | 'doughnut' | 'area'
   * chartData = [{ name, labels: [...], values: [...] }, ...]
   */
  createChartSlide(title, chartType = 'bar', chartData = [], options = {}) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.8125 });

    const TYPE_MAP = {
      bar:      this.pptx.ChartType.bar,
      bar3d:    this.pptx.ChartType.bar3D,
      line:     this.pptx.ChartType.line,
      pie:      this.pptx.ChartType.pie,
      doughnut: this.pptx.ChartType.doughnut,
      area:     this.pptx.ChartType.area,
    };
    const pptxType = TYPE_MAP[chartType] || this.pptx.ChartType.bar;
    const isPie    = chartType === 'pie' || chartType === 'doughnut';

    const safeData = (chartData && chartData.length > 0) ? chartData : [
      { name: 'Fund',      labels: ['Q1', 'Q2', 'Q3', 'Q4'], values: [3.2, 1.8, 4.1, 2.9] },
      { name: 'Benchmark', labels: ['Q1', 'Q2', 'Q3', 'Q4'], values: [2.1, 1.5, 3.2, 2.4] },
    ];

    slide.addChart(pptxType, safeData, {
      x: cv.CX, y: cv.BODY_Y, w: cv.CW, h: cv.BODY_H,
      showLegend:  options.showLegend !== false,
      legendPos:   options.legendPos || 'b',
      showValue:   options.showValue || false,
      showPercent: isPie,
      chartColors: options.chartColors || [
        _c(C.PRIMARY.YELLOW), _c(C.SECONDARY.TURQUOISE),
        _c(C.TONES.GRAY_60),  _c(C.TONES.GRAY_40),
      ],
      dataLabelColor: _c(C.PRIMARY.DARK_GRAY),
    });

    if (options.source) {
      slide.addText(`Source: ${options.source}`, {
        x: cv.CX, y: cv.FOOTER_Y, w: cv.CW * 0.675, h: cv.FOOTER_H,
        fontFace: F.BODY.family, fontSize: Math.round(cv.H * 1.2),
        color: _c(C.TONES.GRAY_60), italic: true,
      });
    }

    return slide;
  }

  /**
   * Image + Content — image on one side, bullet text on the other.
   * imagePosition: 'left' (default) | 'right'
   */
  createImageContentSlide(title, imagePath, content, imagePosition = 'left') {
    const { cv }        = this;
    const slide         = this.pptx.addSlide();
    const { colW, gap } = this._colGeometry(2);
    slide.background    = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);
    this._addSlideTitle(slide, title, { fsScale: 0.8125 });

    const imgX  = imagePosition === 'left' ? cv.CX            : cv.CX + colW + gap;
    const txtX  = imagePosition === 'left' ? cv.CX + colW + gap : cv.CX;
    const paneH = cv.H - cv.BODY_Y - cv.MB;

    if (imagePath && fs.existsSync(imagePath)) {
      slide.addImage({ path: imagePath, x: imgX, y: cv.BODY_Y, w: colW, h: paneH });
    } else {
      slide.addShape(this.pptx.ShapeType.rect, {
        x: imgX, y: cv.BODY_Y, w: colW, h: paneH,
        fill: { color: _c(C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });
      slide.addText('IMAGE', {
        x: imgX, y: cv.BODY_Y, w: colW, h: paneH,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 1.8),
        color: _c(C.TONES.GRAY_40), align: 'center', valign: 'middle',
      });
    }

    slide.addText(this._fmtContent(content, 12, 6), {
      x: txtX, y: cv.BODY_Y, w: colW, h: paneH,
      fontFace: F.BODY.family, fontSize: Math.round(cv.H * 2.0),
      color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
    });

    return slide;
  }

  /**
   * Full-bleed Image Slide.
   */
  createImageSlide(imagePath, title = null, overlay = true) {
    const { cv } = this;
    const slide  = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };

    if (imagePath && fs.existsSync(imagePath)) {
      slide.addImage({ path: imagePath, x: 0, y: 0, w: cv.W, h: cv.H });
    }

    if (overlay && title) {
      const overlayH = cv.H * 0.267;
      const overlayY = cv.H - overlayH;
      slide.addShape(this.pptx.ShapeType.rect, {
        x: 0, y: overlayY, w: cv.W, h: overlayH,
        fill: { color: _c(C.PRIMARY.DARK_GRAY), transparency: 35 },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 0 },
      });
      slide.addText(title.toUpperCase(), {
        x: cv.CX, y: overlayY + overlayH * 0.1, w: cv.CW, h: overlayH * 0.8,
        fontFace: F.HEADERS.family, fontSize: Math.round(cv.W * 2.7),
        bold: true, color: _c(C.PRIMARY.WHITE),
        align: 'center', valign: 'middle',
      });
    }

    // White wordmark on dark full-bleed slide — top-right, sized to match standard logo footprint
    this.addLogo(slide, {
      x: cv.W - cv.WORDMARK_W - cv.MR,
      y: cv.MT,
      w: cv.WORDMARK_W * WATERMARK_SCALE,  // smaller — this is a watermark, not a title treatment
      h: cv.WORDMARK_H * WATERMARK_SCALE,
    }, 'dark');

    return slide;
  }


  // ════════════════════════════════════════════════════════════════════════════
  // SLIDE MASTER DEFINITIONS
  // ════════════════════════════════════════════════════════════════════════════

  /**
   * Define the three Potomac slide masters on the presentation instance.
   * Call ONCE before creating any slides.
   *
   * Reads W and H from pptxInstance.presLayout — the same source of truth used
   * by the constructor — so master geometry stays in sync with any layout change.
   */
  static defineAllMasters(pptxInstance, palette = 'STANDARD') {
    const pal     = SLIDE_PALETTES[palette] || SLIDE_PALETTES.STANDARD;
    const logoDir = path.join(__dirname, '../brand-assets/logos/');

    // Read live from the pptx instance — same source of truth as the constructor.
    const { width: W, height: H } = pptxInstance.presLayout;
    const MR     = W * 0.0375;
    const LOGO_W = W * 0.0712;
    const LOGO_H = LOGO_W;       // icon is square
    const LOGO_X = W - MR - LOGO_W;
    const LOGO_Y = H * 0.016;

    const getIconPath = (theme) => {
      const candidates = theme === 'dark'
        ? ['potomac-icon-white.png',  'potomac-icon-yellow.png']
        : ['potomac-icon-black.png',  'potomac-icon-yellow.png'];
      for (const name of candidates) {
        const p = path.join(logoDir, name);
        if (fs.existsSync(p)) return p;
      }
      return null;
    };

    const makeLogo = (theme, fallbackColor) => {
      const logoPath = getIconPath(theme);
      return logoPath
        ? { image: { path: logoPath, x: LOGO_X, y: LOGO_Y, w: LOGO_W, h: LOGO_H,
                     sizing: { type: 'contain', w: LOGO_W, h: LOGO_H } } }
        : { text: { text: 'POTOMAC', options: {
              x: LOGO_X - LOGO_W * 0.6, y: LOGO_Y, w: LOGO_W * 1.6, h: LOGO_H,
              fontSize: Math.round(H * 1.6), bold: true, color: fallbackColor,
              fontFace: F.HEADERS.family, align: 'right',
            } } };
    };

    pptxInstance.defineSlideMaster({
      title:      'POTOMAC_LIGHT',
      background: { color: _c(pal.background) },
      objects:    [ makeLogo('light', _c(C.PRIMARY.DARK_GRAY)) ],
    });

    pptxInstance.defineSlideMaster({
      title:      'POTOMAC_DARK',
      background: { color: _c(C.PRIMARY.DARK_GRAY) },
      objects:    [ makeLogo('dark', 'FFFFFF') ],
    });

    pptxInstance.defineSlideMaster({
      title:      'POTOMAC_ACCENT',
      background: { color: _c(C.TONES.YELLOW_20) },
      objects:    [ makeLogo('light', _c(C.PRIMARY.DARK_GRAY)) ],
    });
  }


  // ════════════════════════════════════════════════════════════════════════════
  // METADATA
  // ════════════════════════════════════════════════════════════════════════════

  getTemplateMetadata() {
    return {
      title: [
        { name: 'Standard Title',  method: 'createStandardTitleSlide',  use: 'General presentations' },
        { name: 'Executive Title', method: 'createExecutiveTitleSlide', use: 'Dark high-impact presentations' },
        { name: 'Section Divider', method: 'createSectionDividerSlide', use: 'Major section breaks' },
      ],
      content: [
        { name: 'Content',           method: 'createContentSlide',          use: 'Basic bullets or paragraph' },
        { name: 'Two Column',        method: 'createTwoColumnSlide',        use: 'Side-by-side comparison' },
        { name: 'Three Column',      method: 'createThreeColumnSlide',      use: 'Triple-category layout' },
        { name: 'Quote',             method: 'createQuoteSlide',            use: 'Testimonials, important quotes' },
        { name: 'Metrics',           method: 'createMetricSlide',           use: 'Key statistics, KPIs' },
        { name: 'Process',           method: 'createProcessSlide',          use: 'Step-by-step workflows' },
        { name: 'Executive Summary', method: 'createExecutiveSummarySlide', use: 'Dark headline + bullets' },
        { name: 'Card Grid',         method: 'createCardGridSlide',         use: '2×2 or 1×4 content cards' },
        { name: 'Icon Grid',         method: 'createIconGridSlide',         use: 'Icon + title + description grid' },
        { name: 'Hub & Spoke',       method: 'createHubSpokeSlide',         use: 'Centre hub + peripheral nodes' },
        { name: 'Timeline',          method: 'createTimelineSlide',         use: 'Horizontal milestone timeline' },
        { name: '2×2 Matrix',        method: 'createMatrix2x2Slide',        use: 'Quadrant analysis' },
        { name: 'Scorecard',         method: 'createScorecardSlide',        use: 'KPI scorecard with status' },
        { name: 'Comparison',        method: 'createComparisonSlide',       use: 'A vs B with winner indicator' },
        { name: 'Table',             method: 'createTableSlide',            use: 'Branded data table' },
        { name: 'Chart',             method: 'createChartSlide',            use: 'Native bar/line/pie/doughnut chart' },
        { name: 'Image + Content',   method: 'createImageContentSlide',     use: 'Photo + text side-by-side' },
        { name: 'Image',             method: 'createImageSlide',            use: 'Full-bleed image slide' },
      ],
      closing: [
        { name: 'Closing',        method: 'createClosingSlide',      use: 'Thank you + contact info' },
        { name: 'Call to Action', method: 'createCallToActionSlide', use: 'Next steps + CTA button' },
      ],
    };
  }
}

module.exports = { PotomacSlideTemplates };