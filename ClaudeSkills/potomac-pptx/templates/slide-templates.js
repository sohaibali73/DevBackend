/**
 * Potomac Universal Slide Templates — Phase 2 + Phase 3 (Consolidated)
 *
 * FIXES applied vs original:
 *  - All this.pptx.shapes.* → this.pptx.ShapeType.*  (v3 API)
 *  - All fontWeight:'700'/'600' → bold:true            (correct pptxgenjs option)
 *  - Layout set to LAYOUT_WIDE (13.333" × 7.5") via pptx.layout assignment
 *  - All element coordinates reworked for 13.333" canvas width
 *  - ARROW_RIGHT → ShapeType.rightArrow
 *  - Vertical process layout now implemented
 *  - Metric slide overflow protection added
 *  - Column headers added to 2- and 3-column layouts
 *  - YELLOW_20 color propagated from fixed colors file
 *  - Uses _c() helper to strip '#' from brand color hex strings
 *
 * NEW slide types added to match DeckPlanner VALID_SLIDE_TYPES vocabulary:
 *  card_grid, icon_grid, hub_spoke, timeline, matrix_2x2, scorecard,
 *  comparison, table, chart, executive_summary, image_content, image
 *
 * CANVAS SPEC: 13.333" × 7.5"  (pptxgenjs LAYOUT_WIDE)
 *   Left/right content margin: 0.5"
 *   Standard content width:    12.333"  (x=0.5 → x+w=12.833)
 *   Logo watermark (top-right): x=12.08, y=0.12, w=0.95, h=0.95
 */

'use strict';

const { POTOMAC_COLORS, SLIDE_PALETTES } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS } = require('../brand-assets/fonts/potomac-fonts.js');
const path = require('path');

// ── Color helper: strip leading '#' that pptxgenjs does NOT want ─────────────
function _c(hex) {
  if (!hex) return 'FEC00F';
  return String(hex).replace('#', '');
}

// ── Shortcuts ─────────────────────────────────────────────────────────────────
const C  = POTOMAC_COLORS;
const F  = POTOMAC_FONTS;


class PotomacSlideTemplates {
  constructor(pptxGenerator, options = {}) {
    this.pptx    = pptxGenerator;
    this.palette = SLIDE_PALETTES[options.palette || 'STANDARD'];
    // Store directory so we can pick the right variant per slide theme
    this.logoDir = path.join(__dirname, '../brand-assets/logos/');

    // ── Apply true widescreen layout to the pptxgenjs instance ───────────────
    this.pptx.layout = 'LAYOUT_WIDE';   // 13.333" × 7.5"

    this.config = {
      slideWidth:  13.333,
      slideHeight: 7.5,
      margins: { standard: 0.5, content: 0.75, title: 1.0 },
    };
  }


  // ══════════════════════════════════════════════════════════════════════════
  // UTILITY HELPERS
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Return the path of the standalone ICON logo (square hexagon mark).
   * Used for the small top-right watermark on every slide.
   * Real dimensions: ~4.04" × 4.01" (nearly 1:1)
   * @param {'light'|'dark'} theme
   */
  getIconLogoPath(theme = 'light') {
    const fs = require('fs');
    const candidates = theme === 'dark'
      ? ['potomac-icon-white.png', 'potomac-icon-yellow.png']
      : ['potomac-icon-black.png', 'potomac-icon-yellow.png'];
    for (const name of candidates) {
      const p = path.join(this.logoDir, name);
      if (fs.existsSync(p)) return p;
    }
    return null;
  }

  /**
   * Return the path of the FULL WORDMARK logo (icon + "POTOMAC" text, very wide).
   * Used for title slides and closing slides.
   * Real dimensions: ~13.02" × 2.67" (roughly 4.87:1)
   * @param {'light'|'dark'} theme
   */
  getFullLogoPath(theme = 'light') {
    const fs = require('fs');
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
   * Place the FULL WORDMARK logo at an explicit position (title/closing slides).
   * Uses contain-sizing so the image is never distorted.
   * @param {'light'|'dark'} theme
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
      slide.addText('POTOMAC', {
        x: position.x, y: position.y,
        w: position.w, h: position.h,
        fontFace: F.HEADERS.family, fontSize: 14, bold: true,
        color: theme === 'dark' ? _c(C.PRIMARY.WHITE) : _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });
    }
  }

  /**
   * Standard small top-right watermark — uses the ICON logo (square mark).
   *
   * In pptxgenjs 13.333"×7.5" (LAYOUT_WIDE) coordinates:
   *   x: 12.08"  (leaves ~0.283" right margin)
   *   y:  0.12"  (tight to top)
   *   w:  0.95"  h: 0.95"  (square — matches real ~1:1 aspect ratio)
   */
  addStandardLogo(slide, theme = 'light') {
    const logoPath = this.getIconLogoPath(theme);
    if (logoPath) {
      slide.addImage({
        path: logoPath,
        x: 12.08, y: 0.12, w: 0.95, h: 0.95,
        sizing: { type: 'contain', w: 0.95, h: 0.95 },
      });
    } else {
      // Text fallback — show just the wordmark abbreviated
      slide.addText('POTOMAC', {
        x: 11.583, y: 0.12, w: 1.5, h: 0.5,
        fontFace: F.HEADERS.family, fontSize: 12, bold: true,
        color: theme === 'dark' ? _c(C.PRIMARY.WHITE) : _c(C.PRIMARY.DARK_GRAY),
        align: 'right', valign: 'middle',
      });
    }
  }

  /** Yellow accent underline bar below slide title. */
  addTitleUnderline(slide, x = 0.5, y = 1.4) {
    slide.addShape(this.pptx.ShapeType.rect, {
      x, y, w: 2, h: 0.05,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });
  }

  /** Slide number indicator (bottom-right). */
  addSlideNumber(slide, current, total) {
    slide.addText(`${current} / ${total}`, {
      x: 12.433, y: 7.1, w: 0.7, h: 0.28,
      fontFace: F.BODY.family, fontSize: 9,
      color: _c(C.TONES.GRAY_40), align: 'right',
    });
  }

  /** Regulatory / performance disclaimer footer. */
  addDisclaimer(slide, text = 'Past performance does not guarantee future results. For financial professional use only.') {
    slide.addText(text, {
      x: 0.5, y: 7.1, w: 11.833, h: 0.28,
      fontFace: F.BODY.family, fontSize: 8,
      color: _c(C.TONES.GRAY_40), align: 'left', italic: true,
    });
  }


  // ══════════════════════════════════════════════════════════════════════════
  // TITLE SLIDES
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Standard Title Slide — white background, large centred title, yellow bar.
   */
  createStandardTitleSlide(title, subtitle = null, options = {}) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    // Full wordmark top-left: width ≈ 4.7" × height ≈ 0.97"
    this.addLogo(slide, { x: 0.5, y: 0.25, w: 4.7, h: 0.97 }, 'light');

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.5, w: 12.333, h: 1.5,
      fontFace: F.HEADERS.family, fontSize: 44,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });

    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.5, y: 4.2, w: 12.333, h: 0.8,
        fontFace: F.BODY.family, fontSize: 20,
        color: _c(C.TONES.GRAY_60), align: 'center', valign: 'middle',
      });
    }

    // Bottom accent bar
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5, y: 5.5, w: 12.333, h: 0.1,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });

    return slide;
  }

  /**
   * Executive Title Slide — dark background, white text, yellow tagline.
   */
  createExecutiveTitleSlide(title, subtitle = null, tagline = 'Built to Conquer Risk\u00AE') {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };
    // Full white wordmark top-left on dark background
    this.addLogo(slide, { x: 0.5, y: 0.25, w: 4.7, h: 0.97 }, 'dark');

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.2, w: 12.333, h: 1.8,
      fontFace: F.HEADERS.family, fontSize: 48,
      bold: true, color: _c(C.PRIMARY.WHITE),
      align: 'center', valign: 'middle',
    });

    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.5, y: 4.2, w: 12.333, h: 0.7,
        fontFace: F.BODY.family, fontSize: 22,
        color: _c(C.TONES.YELLOW_80), align: 'center', valign: 'middle',
      });
    }

    // Yellow accent bar
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5, y: 5.45, w: 12.333, h: 0.08,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.YELLOW), width: 0 },
    });

    slide.addText(tagline, {
      x: 0.5, y: 5.65, w: 12.333, h: 0.6,
      fontFace: F.BODY.family, fontSize: 18,
      color: _c(C.PRIMARY.YELLOW), align: 'center', valign: 'middle', italic: true,
    });

    return slide;
  }

  /**
   * Section Divider — light-yellow background, full-height left accent bar.
   */
  createSectionDividerSlide(sectionTitle, description = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(C.TONES.YELLOW_20) };
    this.addStandardLogo(slide);

    // Left accent bar (full height)
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0, y: 0, w: 0.3, h: 7.5,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });

    slide.addText(sectionTitle.toUpperCase(), {
      x: 0.8, y: 2.5, w: 12.0, h: 1.5,
      fontFace: F.HEADERS.family, fontSize: 42,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'left', valign: 'middle',
    });

    if (description) {
      slide.addText(description, {
        x: 0.8, y: 4.2, w: 12.0, h: 1.2,
        fontFace: F.BODY.family, fontSize: 18,
        color: _c(C.TONES.GRAY_60), align: 'left', valign: 'middle',
      });
    }

    return slide;
  }


  // ══════════════════════════════════════════════════════════════════════════
  // CORE CONTENT SLIDES
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Standard Content Slide — title + bullet points or paragraph.
   */
  createContentSlide(title, content, options = {}) {
    const slide = this.pptx.addSlide();
    const showBullets = options.bullets !== false;
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 11.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 32,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);

    if (Array.isArray(content) && showBullets) {
      const bulletItems = content.map(item => ({
        text: String(typeof item === 'object' ? (item.text || item) : item),
        options: {
          bullet: { code: '25AA', indent: 15 },
          color: _c(C.PRIMARY.DARK_GRAY),
          paraSpaceBefore: 6,
        },
      }));
      slide.addText(bulletItems, {
        x: 0.5, y: 1.7, w: 12.333, h: 5.3,
        fontFace: F.BODY.family, fontSize: 17,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });
    } else {
      slide.addText(Array.isArray(content) ? content.join('\n') : String(content || ''), {
        x: 0.5, y: 1.7, w: 12.333, h: 5.3,
        fontFace: F.BODY.family, fontSize: 16,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });
    }

    return slide;
  }

  /**
   * Two-Column Layout — optional per-column headers.
   * options: { leftHeader, rightHeader }
   *
   * Canvas: 13.333"  margins: 0.5" each side  available: 12.333"
   * COL_W = (12.333 - GAP) / 2 = (12.333 - 0.4) / 2 ≈ 5.967"
   */
  createTwoColumnSlide(title, leftContent, rightContent, options = {}) {
    const slide = this.pptx.addSlide();
    const COL_W = 5.967;
    const GAP   = 0.4;
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 11.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);

    const hasHeaders = options.leftHeader || options.rightHeader;
    const contentY   = hasHeaders ? 2.4 : 1.9;

    if (options.leftHeader) {
      slide.addText(options.leftHeader.toUpperCase(), {
        x: 0.5, y: 1.75, w: COL_W, h: 0.5,
        fontFace: F.HEADERS.family, fontSize: 14,
        bold: true, color: _c(this.palette.accent),
      });
    }
    if (options.rightHeader) {
      slide.addText(options.rightHeader.toUpperCase(), {
        x: 0.5 + COL_W + GAP, y: 1.75, w: COL_W, h: 0.5,
        fontFace: F.HEADERS.family, fontSize: 14,
        bold: true, color: _c(this.palette.accent),
      });
    }

    const fmtColumn = (content) => {
      if (Array.isArray(content)) {
        return content.map(item => ({
          text: String(item),
          options: { bullet: { code: '25AA', indent: 10 }, paraSpaceBefore: 4 },
        }));
      }
      return String(content || '');
    };

    slide.addText(fmtColumn(leftContent), {
      x: 0.5, y: contentY, w: COL_W, h: 7.5 - contentY - 0.3,
      fontFace: F.BODY.family, fontSize: 15,
      color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
    });

    slide.addText(fmtColumn(rightContent), {
      x: 0.5 + COL_W + GAP, y: contentY, w: COL_W, h: 7.5 - contentY - 0.3,
      fontFace: F.BODY.family, fontSize: 15,
      color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
    });

    // Subtle column separator
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5 + COL_W + GAP / 2 - 0.02, y: contentY - 0.1,
      w: 0.04, h: 7.5 - contentY - 0.2,
      fill: { color: _c(C.TONES.GRAY_20) },
      line: { color: _c(C.TONES.GRAY_20), width: 0 },
    });

    return slide;
  }

  /**
   * Three-Column Layout — optional per-column headers array.
   * options: { headers: ['Col A', 'Col B', 'Col C'] }
   *
   * Canvas: 13.333"  available: 12.333"
   * COL_W = (12.333 - 2*GAP) / 3 = (12.333 - 0.6) / 3 ≈ 3.911"
   */
  createThreeColumnSlide(title, leftContent, centerContent, rightContent, options = {}) {
    const slide = this.pptx.addSlide();
    const COL_W = 3.911;
    const GAP   = 0.3;
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 11.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 26,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);

    const headers  = options.headers || [];
    const contentY = headers.length ? 2.4 : 1.9;
    const columns  = [leftContent, centerContent, rightContent];

    columns.forEach((content, idx) => {
      const x = 0.5 + (COL_W + GAP) * idx;

      if (headers[idx]) {
        slide.addText(headers[idx].toUpperCase(), {
          x, y: 1.75, w: COL_W, h: 0.5,
          fontFace: F.HEADERS.family, fontSize: 13,
          bold: true, color: _c(this.palette.accent), align: 'center',
        });
        slide.addShape(this.pptx.ShapeType.rect, {
          x, y: 2.22, w: COL_W, h: 0.04,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(this.palette.accent), width: 0 },
        });
      }

      const fmtContent = Array.isArray(content)
        ? content.map(item => ({ text: String(item), options: { bullet: { code: '25AA', indent: 8 }, paraSpaceBefore: 3 } }))
        : String(content || '');

      slide.addText(fmtContent, {
        x, y: contentY, w: COL_W, h: 7.5 - contentY - 0.3,
        fontFace: F.BODY.family, fontSize: 13,
        color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
      });

      // Column separator (between columns only)
      if (idx < 2) {
        slide.addShape(this.pptx.ShapeType.rect, {
          x: x + COL_W + GAP / 2 - 0.015, y: 1.6,
          w: 0.03, h: 5.5,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }
    });

    return slide;
  }


  // ══════════════════════════════════════════════════════════════════════════
  // SPECIALISED CONTENT SLIDES
  // ══════════════════════════════════════════════════════════════════════════

  /** Quote / Testimonial slide. */
  createQuoteSlide(quote, attribution = null, context = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(C.TONES.YELLOW_20) };
    this.addStandardLogo(slide);

    // Opening quote mark
    slide.addText('\u201C', {
      x: 0.5, y: 1.5, w: 1, h: 1,
      fontFace: F.HEADERS.family, fontSize: 72,
      bold: true, color: _c(this.palette.accent), align: 'center',
    });

    slide.addText(quote, {
      x: 1.5, y: 2.0, w: 10.333, h: 2.8,
      fontFace: F.BODY.family, fontSize: 22,
      color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle', italic: true,
    });

    if (attribution) {
      slide.addText(`\u2014 ${attribution}`, {
        x: 1.5, y: 5.0, w: 10.333, h: 0.8,
        fontFace: F.BODY.family, fontSize: 16,
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }

    if (context) {
      slide.addText(context, {
        x: 1.5, y: 5.9, w: 10.333, h: 0.6,
        fontFace: F.BODY.family, fontSize: 12,
        color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }

    return slide;
  }

  /**
   * Metrics / KPI Slide — up to 6 large numbers in a responsive grid.
   * metrics = [{value, label, sublabel?}, ...]
   *
   * Available content width from x=0.75 → 12.583" = 11.833"
   * colW = 11.833 / cols
   */
  createMetricSlide(title, metrics, context = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 11.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 30,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);

    const safeMetrics = (Array.isArray(metrics) ? metrics : []).slice(0, 6);
    const cols     = Math.min(3, safeMetrics.length) || 1;
    const rows     = Math.ceil(safeMetrics.length / cols);
    const colW     = 11.833 / cols;
    const rowH     = rows > 1 ? 2.1 : 2.8;
    const startY   = 1.9;

    safeMetrics.forEach((metric, idx) => {
      const col  = idx % cols;
      const row  = Math.floor(idx / cols);
      const x    = 0.75 + col * colW;
      const y    = startY + row * (rowH + 0.2);

      // Card background
      slide.addShape(this.pptx.ShapeType.rect, {
        x, y, w: colW - 0.25, h: rowH,
        fill: { color: _c(C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_20), width: 0 },
      });

      // Metric value — large yellow
      slide.addText(String(metric.value), {
        x, y: y + 0.1, w: colW - 0.25, h: rowH * 0.55,
        fontFace: F.HEADERS.family,
        fontSize: cols <= 2 ? 52 : 40,
        bold: true, color: _c(this.palette.accent),
        align: 'center', valign: 'middle',
      });

      // Metric label
      slide.addText(String(metric.label || ''), {
        x, y: y + rowH * 0.6, w: colW - 0.25, h: rowH * 0.25,
        fontFace: F.BODY.family, fontSize: 13,
        color: _c(C.TONES.GRAY_60), align: 'center',
      });

      // Optional sublabel
      if (metric.sublabel) {
        slide.addText(String(metric.sublabel), {
          x, y: y + rowH * 0.85, w: colW - 0.25, h: rowH * 0.15,
          fontFace: F.BODY.family, fontSize: 10,
          color: _c(C.TONES.GRAY_40), align: 'center', italic: true,
        });
      }
    });

    if (context) {
      slide.addText(String(context), {
        x: 0.5, y: 6.8, w: 12.333, h: 0.5,
        fontFace: F.BODY.family, fontSize: 10,
        color: _c(C.TONES.GRAY_60), align: 'center', italic: true,
      });
    }

    return slide;
  }

  /**
   * Process / Timeline Slide.
   * options.layout = 'horizontal' (default) | 'vertical'
   * steps = [{title, description}, ...]
   *
   * Horizontal: stepW = 11.833 / steps.length  (from x=0.75)
   * Vertical:   full content width used for title/description text
   */
  createProcessSlide(title, steps, options = {}) {
    const slide    = this.pptx.addSlide();
    const vertical = options.layout === 'vertical';
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.5, w: 11.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide);

    const safeSteps = (steps || []).slice(0, vertical ? 6 : 5);

    if (!vertical) {
      // ── HORIZONTAL flow ──────────────────────────────────────────────────
      const stepW = 11.833 / safeSteps.length;

      safeSteps.forEach((step, idx) => {
        const cx    = 0.75 + idx * stepW + stepW / 2;
        const circY = 2.65;
        const R     = 0.35;

        // Circle
        slide.addShape(this.pptx.ShapeType.ellipse, {
          x: cx - R, y: circY - R, w: R * 2, h: R * 2,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
        });
        // Number
        slide.addText(String(idx + 1), {
          x: cx - R, y: circY - R, w: R * 2, h: R * 2,
          fontFace: F.HEADERS.family, fontSize: 18,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
          align: 'center', valign: 'middle',
        });
        // Title
        slide.addText((step.title || `Step ${idx + 1}`).toUpperCase(), {
          x: cx - stepW / 2 + 0.05, y: circY + R + 0.1, w: stepW - 0.1, h: 0.6,
          fontFace: F.HEADERS.family, fontSize: 12,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
        });
        // Description
        if (step.description) {
          slide.addText(String(step.description), {
            x: cx - stepW / 2 + 0.05, y: circY + R + 0.75, w: stepW - 0.1, h: 2.2,
            fontFace: F.BODY.family, fontSize: 11,
            color: _c(C.TONES.GRAY_60), align: 'center', valign: 'top',
          });
        }
        // Connector arrow (except last step)
        if (idx < safeSteps.length - 1) {
          const arrowX = cx + R + 0.05;
          const nextCX = 0.75 + (idx + 1) * stepW + stepW / 2 - R - 0.05;
          const lineW  = (nextCX - arrowX) * 0.7;

          slide.addShape(this.pptx.ShapeType.line, {
            x: arrowX, y: circY, w: lineW, h: 0,
            line: { color: _c(C.TONES.GRAY_40), width: 2 },
          });
          slide.addShape(this.pptx.ShapeType.rightArrow, {
            x: arrowX + lineW - 0.05, y: circY - 0.12,
            w: 0.25, h: 0.25,
            fill: { color: _c(C.TONES.GRAY_40) },
            line: { color: _c(C.TONES.GRAY_40), width: 0 },
          });
        }
      });

    } else {
      // ── VERTICAL flow ────────────────────────────────────────────────────
      const availH = 7.5 - 1.9 - 0.3;
      const stepH  = availH / safeSteps.length;

      safeSteps.forEach((step, idx) => {
        const y = 1.9 + idx * stepH;
        const R = 0.3;

        slide.addShape(this.pptx.ShapeType.ellipse, {
          x: 0.5, y, w: R * 2, h: R * 2,
          fill: { color: _c(this.palette.accent) },
          line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
        });
        slide.addText(String(idx + 1), {
          x: 0.5, y, w: R * 2, h: R * 2,
          fontFace: F.HEADERS.family, fontSize: 16,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
          align: 'center', valign: 'middle',
        });

        slide.addText((step.title || `Step ${idx + 1}`).toUpperCase(), {
          x: 1.4, y: y + 0.02, w: 11.433, h: R * 0.9,
          fontFace: F.HEADERS.family, fontSize: 13,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        });

        if (step.description) {
          slide.addText(String(step.description), {
            x: 1.4, y: y + R * 0.9, w: 11.433, h: stepH - R * 0.9 - 0.1,
            fontFace: F.BODY.family, fontSize: 11,
            color: _c(C.TONES.GRAY_60), valign: 'top',
          });
        }

        // Vertical connector
        if (idx < safeSteps.length - 1) {
          slide.addShape(this.pptx.ShapeType.line, {
            x: 0.5 + R, y: y + R * 2, w: 0, h: stepH - R * 2 - 0.05,
            line: { color: _c(C.TONES.GRAY_40), width: 2 },
          });
        }
      });
    }

    return slide;
  }


  // ══════════════════════════════════════════════════════════════════════════
  // CLOSING SLIDES
  // ══════════════════════════════════════════════════════════════════════════

  createClosingSlide(title = 'THANK YOU', contactInfo = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    // Full wordmark centred: (13.333 - 4.7) / 2 ≈ 4.317" from left
    this.addLogo(slide, { x: 4.317, y: 1.5, w: 4.7, h: 0.97 }, 'light');

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 2.8, w: 12.333, h: 1,
      fontFace: F.HEADERS.family, fontSize: 40,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText('Built to Conquer Risk\u00AE', {
      x: 0.5, y: 4, w: 12.333, h: 0.6,
      fontFace: F.BODY.family, fontSize: 18,
      color: _c(this.palette.accent), align: 'center', italic: true,
    });

    slide.addText(contactInfo || 'potomac.com\n(305) 824-2702\ninfo@potomac.com', {
      x: 0.5, y: 5.5, w: 12.333, h: 1.5,
      fontFace: F.BODY.family, fontSize: 14,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }

  createCallToActionSlide(title, actionText, contactInfo, buttonText = 'GET STARTED') {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 1.5, w: 12.333, h: 1.2,
      fontFace: F.HEADERS.family, fontSize: 34,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    slide.addText(String(actionText || ''), {
      x: 0.5, y: 3, w: 12.333, h: 1.5,
      fontFace: F.BODY.family, fontSize: 18,
      color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    // CTA button — centred on 13.333" canvas: (13.333 - 3) / 2 ≈ 5.167"
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 5.167, y: 4.8, w: 3, h: 0.8,
      fill: { color: _c(this.palette.accent) },
      line: { color: _c(this.palette.accent), width: 0 },
    });
    slide.addText(buttonText.toUpperCase(), {
      x: 5.167, y: 4.8, w: 3, h: 0.8,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.WHITE),
      align: 'center', valign: 'middle',
    });

    slide.addText(String(contactInfo || 'potomac.com | (305) 824-2702 | info@potomac.com'), {
      x: 0.5, y: 6.0, w: 12.333, h: 1,
      fontFace: F.BODY.family, fontSize: 14,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  // ══════════════════════════════════════════════════════════════════════════
  // NEW TEMPLATES — DeckPlanner VALID_SLIDE_TYPES
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Executive Summary — dark background, large headline, yellow-accented bullets.
   * Matches DeckPlanner type 'executive_summary'.
   */
  createExecutiveSummarySlide(headline, points = [], context = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };
    this.addStandardLogo(slide, 'dark');

    slide.addText((headline || 'EXECUTIVE SUMMARY').toUpperCase(), {
      x: 0.5, y: 0.4, w: 11.333, h: 1.1,
      fontFace: F.HEADERS.family, fontSize: 34,
      bold: true, color: _c(C.PRIMARY.WHITE),
    });

    // Yellow accent bar
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5, y: 1.45, w: 2.5, h: 0.07,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.YELLOW), width: 0 },
    });

    const bulletItems = (points || []).slice(0, 6).map(p => ({
      text: String(p),
      options: {
        bullet: { code: '25BA', indent: 12 },
        color: _c(C.PRIMARY.WHITE),
        paraSpaceBefore: 8,
      },
    }));

    slide.addText(bulletItems.length ? bulletItems : [{ text: '', options: {} }], {
      x: 0.5, y: 1.7, w: 12.333, h: 5.2,
      fontFace: F.BODY.family, fontSize: 18,
      color: _c(C.PRIMARY.WHITE), valign: 'top',
    });

    if (context) {
      slide.addText(String(context), {
        x: 0.5, y: 6.9, w: 12.333, h: 0.4,
        fontFace: F.BODY.family, fontSize: 9,
        color: _c(C.TONES.GRAY_60), align: 'center', italic: true,
      });
    }

    return slide;
  }

  /**
   * Card Grid — 2×2 or 1×4 coloured content cards.
   * Matches DeckPlanner type 'card_grid'.
   * cards = [{title, text, color: 'yellow'|'dark'|'white'|'turquoise'}, ...]
   *
   * 1-col: cardW = 12.333" (from startX 0.75, right edge 12.583 ≈ 12.583)
   * 2-col: 2*cardW + gapX = 12.333  →  cardW = (12.333 - 0.5) / 2 ≈ 5.917"
   */
  createCardGridSlide(title, cards = [], options = {}) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.75,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.02);

    const safeCards = (cards || []).slice(0, 4);
    const count = safeCards.length || 1;
    const cols  = count <= 2 ? count : 2;
    const rows  = Math.ceil(count / cols);

    const cardW  = cols === 1 ? 12.083 : 5.917;
    const cardH  = rows === 1 ? 4.8 : 2.25;
    const startX = cols === 1 ? 0.75 : 0.5;
    const startY = 1.35;
    const gapX   = 0.5;
    const gapY   = 0.3;

    const COLOR_MAP = {
      yellow:    { bg: _c(C.PRIMARY.YELLOW),       hdr: _c(C.PRIMARY.DARK_GRAY),  txt: _c(C.PRIMARY.DARK_GRAY) },
      dark:      { bg: _c(C.PRIMARY.DARK_GRAY),    hdr: _c(C.PRIMARY.WHITE),       txt: _c(C.PRIMARY.WHITE) },
      white:     { bg: _c(C.TONES.GRAY_20),        hdr: _c(C.PRIMARY.DARK_GRAY),  txt: _c(C.PRIMARY.DARK_GRAY) },
      turquoise: { bg: _c(C.SECONDARY.TURQUOISE),  hdr: _c(C.PRIMARY.DARK_GRAY),  txt: _c(C.PRIMARY.DARK_GRAY) },
    };
    const DEFAULT_COLORS = ['yellow', 'dark', 'white', 'turquoise'];

    safeCards.forEach((card, idx) => {
      const col    = idx % cols;
      const row    = Math.floor(idx / cols);
      const x      = startX + col * (cardW + gapX);
      const y      = startY + row * (cardH + gapY);
      const scheme = COLOR_MAP[card.color] || COLOR_MAP[DEFAULT_COLORS[idx % 4]];

      slide.addShape(this.pptx.ShapeType.rect, {
        x, y, w: cardW, h: cardH,
        fill: { color: scheme.bg },
        line: { color: scheme.bg, width: 0 },
      });

      if (card.title) {
        slide.addText(card.title.toUpperCase(), {
          x: x + 0.2, y: y + 0.15, w: cardW - 0.4, h: cardH * 0.38,
          fontFace: F.HEADERS.family, fontSize: rows > 1 ? 13 : 17,
          bold: true, color: scheme.hdr, align: 'left', valign: 'middle',
        });
      }

      if (card.text) {
        slide.addText(String(card.text), {
          x: x + 0.2, y: y + cardH * 0.42, w: cardW - 0.4, h: cardH * 0.52,
          fontFace: F.BODY.family, fontSize: rows > 1 ? 11 : 14,
          color: scheme.txt, align: 'left', valign: 'top',
        });
      }
    });

    return slide;
  }

  /**
   * Icon Grid — circular icon badges in a responsive grid.
   * Matches DeckPlanner type 'icon_grid'.
   * items = [{icon, title, description}, ...]
   *
   * itemW = 11.833 / cols  (from startX 0.75)
   */
  createIconGridSlide(title, items = [], options = {}) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.75,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.02);

    const safe = (items || []).slice(0, 6);
    const cols = Math.min(3, safe.length) || 1;
    const rows = Math.ceil(safe.length / cols);
    const itemW = 11.833 / cols;
    const itemH = rows > 1 ? 2.6 : 4.8;

    safe.forEach((item, idx) => {
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const cx  = 0.75 + col * itemW + itemW / 2;
      const y   = 1.35 + row * (itemH + 0.3);
      const R   = rows > 1 ? 0.38 : 0.55;

      // Icon circle
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: cx - R, y, w: R * 2, h: R * 2,
        fill: { color: _c(this.palette.accent) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1 },
      });
      slide.addText(String(item.icon || idx + 1), {
        x: cx - R, y, w: R * 2, h: R * 2,
        fontFace: F.HEADERS.family, fontSize: R > 0.45 ? 20 : 15,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });

      if (item.title) {
        slide.addText(item.title.toUpperCase(), {
          x: cx - itemW / 2 + 0.1, y: y + R * 2 + 0.1, w: itemW - 0.2, h: 0.5,
          fontFace: F.HEADERS.family, fontSize: 12,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
        });
      }

      if (item.description) {
        slide.addText(String(item.description), {
          x: cx - itemW / 2 + 0.1, y: y + R * 2 + 0.65, w: itemW - 0.2,
          h: itemH - R * 2 - 0.7,
          fontFace: F.BODY.family, fontSize: 11,
          color: _c(C.TONES.GRAY_60), align: 'center', valign: 'top',
        });
      }
    });

    return slide;
  }

  /**
   * Hub & Spoke — central Potomac hub with peripheral service nodes.
   * Matches DeckPlanner type 'hub_spoke'.
   * center = {title, subtitle}; nodes = [{label, description?}, ...]
   *
   * Hub centred at x=6.667 (13.333/2), y=4.1
   */
  createHubSpokeSlide(title, center = {}, nodes = []) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.7,
      fontFace: F.HEADERS.family, fontSize: 24,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    const HUB_CX = 6.667;   // true centre of 13.333" slide
    const HUB_CY = 4.1;
    const HUB_R  = 0.9;

    // Central hub
    slide.addShape(this.pptx.ShapeType.ellipse, {
      x: HUB_CX - HUB_R, y: HUB_CY - HUB_R, w: HUB_R * 2, h: HUB_R * 2,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2.5 },
    });
    slide.addText((center.title || 'POTOMAC').toUpperCase(), {
      x: HUB_CX - HUB_R, y: HUB_CY - HUB_R + 0.15, w: HUB_R * 2, h: HUB_R * 0.9,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });
    if (center.subtitle) {
      slide.addText(String(center.subtitle), {
        x: HUB_CX - HUB_R, y: HUB_CY + 0.1, w: HUB_R * 2, h: HUB_R * 0.5,
        fontFace: F.BODY.family, fontSize: 10,
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });
    }

    const safeNodes = (nodes || []).slice(0, 6);
    const SPOKE_R   = 2.6;
    const NODE_R    = 0.55;
    const NODE_COLORS = [
      _c(C.SECONDARY.TURQUOISE), _c(C.TONES.GRAY_20), _c(C.TONES.YELLOW_40),
      _c(C.SECONDARY.TURQUOISE), _c(C.TONES.GRAY_20), _c(C.TONES.YELLOW_40),
    ];

    safeNodes.forEach((node, idx) => {
      const angle = (idx / safeNodes.length) * 2 * Math.PI - Math.PI / 2;
      const nx = HUB_CX + SPOKE_R * Math.cos(angle);
      const ny = HUB_CY + SPOKE_R * Math.sin(angle);

      // Spoke line — from hub edge to node edge (drawn first so nodes render on top)
      slide.addShape(this.pptx.ShapeType.line, {
        x: HUB_CX + HUB_R * Math.cos(angle),
        y: HUB_CY + HUB_R * Math.sin(angle),
        w: (SPOKE_R - NODE_R - HUB_R) * Math.cos(angle),
        h: (SPOKE_R - NODE_R - HUB_R) * Math.sin(angle),
        line: { color: _c(C.TONES.GRAY_40), width: 1.5 },
      });

      // Node circle
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: nx - NODE_R, y: ny - NODE_R, w: NODE_R * 2, h: NODE_R * 2,
        fill: { color: NODE_COLORS[idx % NODE_COLORS.length] },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
      });
      slide.addText((node.label || `Node ${idx + 1}`).toUpperCase(), {
        x: nx - NODE_R, y: ny - NODE_R, w: NODE_R * 2, h: NODE_R * 2,
        fontFace: F.HEADERS.family, fontSize: 9,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });
    });

    return slide;
  }

  /**
   * Timeline Slide — horizontal milestone track.
   * Matches DeckPlanner type 'timeline'.
   * milestones = [{label, date, status:'complete'|'in_progress'|'pending'}, ...]
   *
   * TL_XMIN=0.8, TL_XMAX=12.5  →  TL_W=11.7"
   */
  createTimelineSlide(title, milestones = []) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.75,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.02);

    const safe    = (milestones || []).slice(0, 8);
    const TL_Y    = 3.8;
    const TL_XMIN = 0.8;
    const TL_XMAX = 12.5;
    const TL_W    = TL_XMAX - TL_XMIN;

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
      const xPos   = TL_XMIN + (TL_W * (idx + 0.5)) / safe.length;
      const MR     = 0.2;
      const isAbove = idx % 2 === 0;
      const status  = ms.status || 'pending';

      // Tick
      const tickTop = isAbove ? TL_Y - 1.6 : TL_Y;
      slide.addShape(this.pptx.ShapeType.line, {
        x: xPos, y: tickTop, w: 0, h: 1.6,
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });

      // Marker dot
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: xPos - MR, y: TL_Y - MR, w: MR * 2, h: MR * 2,
        fill: { color: STATUS_COLORS[status] || STATUS_COLORS.pending },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1.5 },
      });

      // Label
      const labelW = TL_W / safe.length * 0.9;
      const labelY = isAbove ? TL_Y - 2.1 : TL_Y + 1.65;

      slide.addText(String(ms.label || `M${idx + 1}`), {
        x: xPos - labelW / 2, y: labelY, w: labelW, h: 0.5,
        fontFace: F.HEADERS.family, fontSize: 11,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });

      if (ms.date) {
        slide.addText(String(ms.date), {
          x: xPos - labelW / 2, y: labelY + 0.5, w: labelW, h: 0.38,
          fontFace: F.BODY.family, fontSize: 10,
          color: _c(C.TONES.GRAY_60), align: 'center',
        });
      }
    });

    return slide;
  }

  /**
   * 2×2 Matrix Slide — quadrant analysis.
   * Matches DeckPlanner type 'matrix_2x2'.
   * quadrants = [{title, text, color?}, ...] top-left, top-right, bottom-left, bottom-right
   *
   * QW=5.0, GAP=0.1 → total matrix width=10.1"
   * GX = (13.333 - 10.1) / 2 ≈ 1.617"  (centred on slide)
   */
  createMatrix2x2Slide(title, xAxisLabel = '', yAxisLabel = '', quadrants = []) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.7,
      fontFace: F.HEADERS.family, fontSize: 26,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    const GX = 1.617, GY = 1.3;
    const QW = 5.0,   QH = 2.7, GAP = 0.1;

    const DEFAULT_Q = [
      { title: 'HIGH VALUE\nLOW RISK',   color: C.PRIMARY.YELLOW },
      { title: 'HIGH VALUE\nHIGH RISK',  color: C.SECONDARY.TURQUOISE },
      { title: 'LOW VALUE\nLOW RISK',    color: C.TONES.GRAY_20 },
      { title: 'LOW VALUE\nHIGH RISK',   color: C.TONES.GRAY_40 },
    ];
    const q4 = [0, 1, 2, 3].map(i => quadrants[i] || DEFAULT_Q[i]);

    [[0, 0], [1, 0], [0, 1], [1, 1]].forEach(([col, row], idx) => {
      const q = q4[idx];
      const x = GX + col * (QW + GAP);
      const y = GY + row * (QH + GAP);

      slide.addShape(this.pptx.ShapeType.rect, {
        x, y, w: QW, h: QH,
        fill: { color: _c(q.color || C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });
      if (q.title) {
        slide.addText(q.title.toUpperCase(), {
          x: x + 0.15, y: y + 0.15, w: QW - 0.3, h: 0.85,
          fontFace: F.HEADERS.family, fontSize: 13,
          bold: true, color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
        });
      }
      if (q.text) {
        slide.addText(String(q.text), {
          x: x + 0.15, y: y + 1.05, w: QW - 0.3, h: QH - 1.2,
          fontFace: F.BODY.family, fontSize: 12,
          color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
        });
      }
    });

    // Axis lines
    slide.addShape(this.pptx.ShapeType.line, {
      x: GX, y: GY + QH + GAP / 2, w: QW * 2 + GAP, h: 0,
      line: { color: _c(C.TONES.GRAY_60), width: 2 },
    });
    slide.addShape(this.pptx.ShapeType.line, {
      x: GX + QW + GAP / 2, y: GY, w: 0, h: QH * 2 + GAP,
      line: { color: _c(C.TONES.GRAY_60), width: 2 },
    });

    if (xAxisLabel) {
      slide.addText(xAxisLabel.toUpperCase(), {
        x: GX, y: GY + QH * 2 + GAP + 0.15, w: QW * 2 + GAP, h: 0.35,
        fontFace: F.HEADERS.family, fontSize: 11,
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center',
      });
    }
    if (yAxisLabel) {
      slide.addText(yAxisLabel.toUpperCase(), {
        x: 0.1, y: GY, w: 0.9, h: QH * 2,
        fontFace: F.HEADERS.family, fontSize: 11,
        bold: true, color: _c(C.TONES.GRAY_60),
        align: 'center', valign: 'middle', rotate: 270,
      });
    }

    return slide;
  }

  /**
   * Scorecard / KPI Dashboard.
   * Matches DeckPlanner type 'scorecard'.
   * metrics = [{label, value, target?, change?, status:'green'|'yellow'|'red'}, ...]
   *
   * Columns scaled to 13.333" canvas (total span 0.6 → 12.65"):
   *   S_COLS   = [0.6,  5.4,  7.5,  9.3, 11.25]
   *   S_WIDTHS = [4.7,  2.0,  1.7,  1.85, 1.4 ]
   */
  createScorecardSlide(title, metrics = [], subtitle = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.75,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.02);

    const headerY = subtitle ? 1.55 : 1.35;

    if (subtitle) {
      slide.addText(subtitle, {
        x: 0.5, y: 1.08, w: 11.833, h: 0.38,
        fontFace: F.BODY.family, fontSize: 13,
        color: _c(C.TONES.GRAY_60),
      });
    }

    const safe    = (metrics || []).slice(0, 8);
    const rowH    = Math.min(0.72, (7.5 - headerY - 0.45 - 0.4) / Math.max(safe.length, 1));
    const S_COLS   = [0.6, 5.4, 7.5, 9.3, 11.25];
    const S_WIDTHS = [4.7, 2.0, 1.7, 1.85, 1.4];
    const HDRS    = ['KPI / METRIC', 'CURRENT', 'TARGET', 'CHANGE', 'STATUS'];
    const STATUS_C = { green: _c(C.SECONDARY.TURQUOISE), yellow: _c(C.PRIMARY.YELLOW), red: _c(C.SECONDARY.PINK) };

    // Header row
    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5, y: headerY, w: 12.333, h: 0.45,
      fill: { color: _c(C.PRIMARY.DARK_GRAY) },
      line: { color: _c(C.PRIMARY.DARK_GRAY), width: 0 },
    });
    HDRS.forEach((h, i) => {
      slide.addText(h, {
        x: S_COLS[i], y: headerY + 0.03, w: S_WIDTHS[i], h: 0.39,
        fontFace: F.HEADERS.family, fontSize: 11,
        bold: true, color: _c(C.PRIMARY.WHITE),
        valign: 'middle', align: i === 0 ? 'left' : 'center',
      });
    });

    safe.forEach((m, idx) => {
      const y   = headerY + 0.45 + idx * rowH;
      const alt = idx % 2 === 1;

      if (alt) {
        slide.addShape(this.pptx.ShapeType.rect, {
          x: 0.5, y, w: 12.333, h: rowH,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }

      const fs = Math.min(12, rowH * 14);

      [
        { v: m.label || '',   x: S_COLS[0], w: S_WIDTHS[0], align: 'left',   bold: true,  color: _c(C.PRIMARY.DARK_GRAY) },
        { v: m.value || '—',  x: S_COLS[1], w: S_WIDTHS[1], align: 'center', bold: true,  color: _c(this.palette.accent) },
        { v: m.target || '—', x: S_COLS[2], w: S_WIDTHS[2], align: 'center', bold: false, color: _c(C.PRIMARY.DARK_GRAY) },
        { v: m.change || '—', x: S_COLS[3], w: S_WIDTHS[3], align: 'center', bold: false, color: _c(C.PRIMARY.DARK_GRAY) },
      ].forEach(col => {
        slide.addText(String(col.v), {
          x: col.x, y: y + 0.04, w: col.w, h: rowH - 0.08,
          fontFace: F.BODY.family, fontSize: fs,
          bold: col.bold, color: col.color,
          align: col.align, valign: 'middle',
        });
      });

      // Status indicator circle — centred in the STATUS column (x=11.25, w=1.4)
      const sc = STATUS_C[m.status] || STATUS_C.yellow;
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: 11.35 + (1.4 - rowH * 0.6) / 2, y: y + rowH * 0.2,
        w: rowH * 0.6, h: rowH * 0.6,
        fill: { color: sc }, line: { color: sc, width: 0 },
      });
    });

    return slide;
  }

  /**
   * Comparison — labelled side-by-side A vs B.
   * Matches DeckPlanner type 'comparison'.
   * rows = [{label, left, right}, ...]
   * winner = 'left' | 'right' | null
   *
   * Canvas 13.333":  COL_W=5.5  CENTER_X=6.667
   *   Left  col: x=0.5,              w=5.5  → right edge 6.0
   *   Right col: x=CENTER_X+0.2=6.867, w=5.5 → right edge 12.367
   */
  createComparisonSlide(title, leftLabel = 'OPTION A', rightLabel = 'OPTION B', rows = [], winner = null) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.7,
      fontFace: F.HEADERS.family, fontSize: 26,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });

    const COL_W    = 5.5;
    const CENTER_X = 6.667;
    const HDR_Y    = 1.15;
    const safeRows = (rows || []).slice(0, 8);
    const rowH     = Math.min(0.72, (7.5 - HDR_Y - 0.6 - 0.4) / Math.max(safeRows.length, 1));

    // Header colours
    const lWin = winner === 'left';
    const rWin = winner === 'right';
    const leftHdrColor  = lWin ? _c(C.PRIMARY.YELLOW) : _c(C.PRIMARY.DARK_GRAY);
    const rightHdrColor = rWin ? _c(C.PRIMARY.YELLOW) : _c(C.PRIMARY.DARK_GRAY);
    const leftTxtColor  = lWin ? _c(C.PRIMARY.DARK_GRAY) : _c(C.PRIMARY.WHITE);
    const rightTxtColor = rWin ? _c(C.PRIMARY.DARK_GRAY) : _c(C.PRIMARY.WHITE);

    slide.addShape(this.pptx.ShapeType.rect, {
      x: 0.5, y: HDR_Y, w: COL_W, h: 0.6,
      fill: { color: leftHdrColor }, line: { color: leftHdrColor, width: 0 },
    });
    slide.addText(leftLabel.toUpperCase(), {
      x: 0.5, y: HDR_Y, w: COL_W, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 14,
      bold: true, color: leftTxtColor, align: 'center', valign: 'middle',
    });

    slide.addShape(this.pptx.ShapeType.rect, {
      x: CENTER_X + 0.2, y: HDR_Y, w: COL_W, h: 0.6,
      fill: { color: rightHdrColor }, line: { color: rightHdrColor, width: 0 },
    });
    slide.addText(rightLabel.toUpperCase(), {
      x: CENTER_X + 0.2, y: HDR_Y, w: COL_W, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 14,
      bold: true, color: rightTxtColor, align: 'center', valign: 'middle',
    });

    // VS divider label
    slide.addText('VS', {
      x: CENTER_X - 0.25, y: HDR_Y + 0.1, w: 0.5, h: 0.4,
      fontFace: F.HEADERS.family, fontSize: 12,
      bold: true, color: _c(C.TONES.GRAY_40), align: 'center',
    });

    safeRows.forEach((row, idx) => {
      const y   = HDR_Y + 0.6 + idx * rowH;
      const alt = idx % 2 === 1;

      if (alt) {
        slide.addShape(this.pptx.ShapeType.rect, {
          x: 0.5, y, w: 12.333, h: rowH,
          fill: { color: _c(C.TONES.GRAY_20) },
          line: { color: _c(C.TONES.GRAY_20), width: 0 },
        });
      }

      const fs = Math.min(12, rowH * 13);

      // Row label (centre column)
      slide.addText(String(row.label || `Point ${idx + 1}`), {
        x: CENTER_X - 0.3, y: y + 0.05, w: 0.6, h: rowH - 0.1,
        fontFace: F.HEADERS.family, fontSize: 10,
        bold: true, color: _c(C.TONES.GRAY_60), align: 'center', valign: 'middle',
      });
      slide.addText(String(row.left || '—'), {
        x: 0.6, y: y + 0.05, w: COL_W - 0.2, h: rowH - 0.1,
        fontFace: F.BODY.family, fontSize: fs,
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center', valign: 'middle',
      });
      slide.addText(String(row.right || '—'), {
        x: CENTER_X + 0.3, y: y + 0.05, w: COL_W - 0.2, h: rowH - 0.1,
        fontFace: F.BODY.family, fontSize: fs,
        color: _c(C.PRIMARY.DARK_GRAY), align: 'center', valign: 'middle',
      });
    });

    return slide;
  }

  /**
   * Table Slide — branded data table.
   * Matches DeckPlanner type 'table'.
   */
  createTableSlide(title, headers = [], rows = [], options = {}) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.75,
      fontFace: F.HEADERS.family, fontSize: 28,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.02);

    if (!headers.length || !rows.length) {
      slide.addText('No data provided', {
        x: 0.5, y: 2, w: 12.333, h: 1,
        fontFace: F.BODY.family, fontSize: 16,
        color: _c(C.TONES.GRAY_60), align: 'center',
      });
      return slide;
    }

    const highlightCol = options.highlightColumn !== undefined ? options.highlightColumn : headers.length - 1;

    const tableRows = [
      headers.map((h, ci) => ({
        text: String(h).toUpperCase(),
        options: {
          bold: true, align: 'center', valign: 'middle',
          fontFace: F.HEADERS.family, fontSize: 12,
          color: _c(C.PRIMARY.DARK_GRAY),
          fill: { color: ci === highlightCol ? _c(C.SECONDARY.TURQUOISE) : _c(C.PRIMARY.YELLOW) },
        },
      })),
      ...rows.slice(0, 10).map((row, ri) => {
        const alt = ri % 2 === 1;
        return (Array.isArray(row) ? row : [row]).map((cell, ci) => ({
          text: String(cell),
          options: {
            fontFace: F.BODY.family, fontSize: 11,
            align: ci === 0 ? 'left' : 'center', valign: 'middle',
            bold: ci === highlightCol,
            color: ci === highlightCol ? _c(C.SECONDARY.TURQUOISE) : _c(C.PRIMARY.DARK_GRAY),
            fill: { color: alt ? _c(C.TONES.YELLOW_20) : _c(C.PRIMARY.WHITE) },
          },
        }));
      }),
    ];

    const tblH = Math.min(5.5, (rows.length + 1) * 0.5);
    slide.addTable(tableRows, {
      x: 0.5, y: 1.35, w: 12.333, h: tblH,
      border: { pt: 0.5, color: _c(C.TONES.GRAY_40) },
      margin: 0.05,
    });

    if (options.disclaimer) {
      this.addDisclaimer(slide, options.disclaimer);
    }

    return slide;
  }

  /**
   * Chart Slide — native PptxGenJS chart.
   * Matches DeckPlanner type 'chart'.
   * chartType: 'bar' | 'line' | 'pie' | 'doughnut' | 'area'
   * chartData = [{name, labels: [...], values: [...]}, ...]
   */
  createChartSlide(title, chartType = 'bar', chartData = [], options = {}) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.72,
      fontFace: F.HEADERS.family, fontSize: 26,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.0);

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
      x: 0.5, y: 1.1, w: 12.333, h: 5.5,
      showLegend: options.showLegend !== false,
      legendPos:  options.legendPos || 'b',
      showValue:  options.showValue || false,
      showPercent: isPie,
      chartColors: options.chartColors || [
        _c(C.PRIMARY.YELLOW), _c(C.SECONDARY.TURQUOISE), _c(C.TONES.GRAY_60), _c(C.TONES.GRAY_40),
      ],
      dataLabelColor: _c(C.PRIMARY.DARK_GRAY),
    });

    if (options.source) {
      slide.addText(`Source: ${options.source}`, {
        x: 0.5, y: 6.9, w: 9, h: 0.35,
        fontFace: F.BODY.family, fontSize: 9,
        color: _c(C.TONES.GRAY_60), italic: true,
      });
    }

    return slide;
  }

  /**
   * Image + Content — image left/right with text on the other side.
   * Matches DeckPlanner type 'image_content'.
   *
   * Canvas 13.333":  each pane w=6.0", gap≈0.333"
   *   Left pane:  x=0.5  (image or text)
   *   Right pane: x=6.833 (text or image)
   */
  createImageContentSlide(title, imagePath, content, imagePosition = 'left') {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(this.palette.background) };
    this.addStandardLogo(slide);

    slide.addText(title.toUpperCase(), {
      x: 0.5, y: 0.3, w: 11.333, h: 0.72,
      fontFace: F.HEADERS.family, fontSize: 26,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
    });
    this.addTitleUnderline(slide, 0.5, 1.0);

    const PANE_W = 6.0;
    const imgX   = imagePosition === 'left' ? 0.5   : 6.833;
    const txtX   = imagePosition === 'left' ? 6.833 : 0.5;
    const fs     = require('fs');

    if (imagePath && fs.existsSync(imagePath)) {
      slide.addImage({ path: imagePath, x: imgX, y: 1.3, w: PANE_W, h: 5.8 });
    } else {
      slide.addShape(this.pptx.ShapeType.rect, {
        x: imgX, y: 1.3, w: PANE_W, h: 5.8,
        fill: { color: _c(C.TONES.GRAY_20) },
        line: { color: _c(C.TONES.GRAY_40), width: 1 },
      });
      slide.addText('IMAGE', {
        x: imgX, y: 1.3, w: PANE_W, h: 5.8,
        fontFace: F.HEADERS.family, fontSize: 24,
        color: _c(C.TONES.GRAY_40), align: 'center', valign: 'middle',
      });
    }

    const txtContent = Array.isArray(content)
      ? content.map(item => ({ text: String(item), options: { bullet: { code: '25AA', indent: 12 }, paraSpaceBefore: 6 } }))
      : String(content || '');

    slide.addText(txtContent, {
      x: txtX, y: 1.3, w: PANE_W, h: 5.8,
      fontFace: F.BODY.family, fontSize: 15,
      color: _c(C.PRIMARY.DARK_GRAY), valign: 'top',
    });

    return slide;
  }

  /**
   * Full-bleed Image Slide.
   * Matches DeckPlanner type 'image'.
   *
   * Image fills the full 13.333"×7.5" canvas.
   */
  createImageSlide(imagePath, title = null, overlay = true) {
    const slide = this.pptx.addSlide();
    slide.background = { color: _c(C.PRIMARY.DARK_GRAY) };

    const fs = require('fs');
    if (imagePath && fs.existsSync(imagePath)) {
      // Full-bleed: width=13.333", height=7.5"
      slide.addImage({ path: imagePath, x: 0, y: 0, w: 13.333, h: 7.5 });
    }

    if (overlay && title) {
      slide.addShape(this.pptx.ShapeType.rect, {
        x: 0, y: 5.5, w: 13.333, h: 2,
        fill: { color: _c(C.PRIMARY.DARK_GRAY), transparency: 35 },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 0 },
      });
      slide.addText(title.toUpperCase(), {
        x: 0.5, y: 5.7, w: 12.333, h: 1.2,
        fontFace: F.HEADERS.family, fontSize: 36,
        bold: true, color: _c(C.PRIMARY.WHITE),
        align: 'center', valign: 'middle',
      });
    }

    // Dark slide — use white logo variant; x=11.5 keeps it clear of the right edge
    this.addLogo(slide, { x: 11.5, y: 0.22, w: 1.6, h: 0.55 }, 'dark');
    return slide;
  }


  // ══════════════════════════════════════════════════════════════════════════
  // SLIDE MASTER DEFINITIONS
  // ══════════════════════════════════════════════════════════════════════════

  /**
   * Define the three Potomac slide masters on the presentation instance.
   * Call ONCE before creating any slides:
   *   PotomacSlideTemplates.defineAllMasters(pptxInstance)
   *
   * Logo watermark placed at x=12.08 to match addStandardLogo() on 13.333" canvas.
   */
  static defineAllMasters(pptxInstance, palette = 'STANDARD') {
    const pal     = SLIDE_PALETTES[palette] || SLIDE_PALETTES.STANDARD;
    const logoDir = path.join(__dirname, '../brand-assets/logos/');
    const fs      = require('fs');

    // Slide masters use the ICON logo (square hexagon mark) in the top-right corner,
    // matching addStandardLogo(). This is the small watermark present on every slide.
    const getIconPath = (theme) => {
      const candidates = theme === 'dark'
        ? ['potomac-icon-white.png', 'potomac-icon-yellow.png']
        : ['potomac-icon-black.png', 'potomac-icon-yellow.png'];
      for (const name of candidates) {
        const p = path.join(logoDir, name);
        if (fs.existsSync(p)) return p;
      }
      return null;
    };

    // Square bounding box (0.95"×0.95") at x=12.08 — matches 13.333" canvas watermark
    const makeLogo = (theme, fallbackColor) => {
      const logoPath = getIconPath(theme);
      return logoPath
        ? { image: { path: logoPath, x: 12.08, y: 0.12, w: 0.95, h: 0.95,
                     sizing: { type: 'contain', w: 0.95, h: 0.95 } } }
        : { text: { text: 'POTOMAC', options: {
              x: 11.583, y: 0.12, w: 1.5, h: 0.5,
              fontSize: 12, bold: true, color: fallbackColor,
              fontFace: F.HEADERS.family, align: 'right',
            } } };
    };

    pptxInstance.defineSlideMaster({
      title: 'POTOMAC_LIGHT',
      background: { color: _c(pal.background) },
      objects: [ makeLogo('light', _c(C.PRIMARY.DARK_GRAY)) ],
    });

    pptxInstance.defineSlideMaster({
      title: 'POTOMAC_DARK',
      background: { color: _c(C.PRIMARY.DARK_GRAY) },
      objects: [ makeLogo('dark', 'FFFFFF') ],
    });

    pptxInstance.defineSlideMaster({
      title: 'POTOMAC_ACCENT',
      background: { color: _c(C.TONES.YELLOW_20) },
      objects: [ makeLogo('light', _c(C.PRIMARY.DARK_GRAY)) ],
    });
  }


  // ══════════════════════════════════════════════════════════════════════════
  // METADATA
  // ══════════════════════════════════════════════════════════════════════════

  getTemplateMetadata() {
    return {
      title: [
        { name: 'Standard Title',    method: 'createStandardTitleSlide',    use: 'General presentations' },
        { name: 'Executive Title',   method: 'createExecutiveTitleSlide',   use: 'Dark high-impact presentations' },
        { name: 'Section Divider',   method: 'createSectionDividerSlide',   use: 'Major section breaks' },
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
