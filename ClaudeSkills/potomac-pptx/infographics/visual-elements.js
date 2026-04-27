/**
 * Potomac Visual Elements & Infographics — Phase 3 (Fixed)
 *
 * FIXES applied:
 *  - slide.addShape('ellipse'/'rect'/'line', ...) → this.pptx.ShapeType.*  (v3 API)
 *  - fontWeight: 'bold' → bold: true
 *  - _c() helper strips '#' from brand color hex strings
 *  - ALL default configs and hardcoded x/w values rescaled from 10" → 13.333"
 *    canvas (LAYOUT_WIDE). Scale factor = 1.3333.
 *  - Canvas constants (MARGIN, CONTENT_W) are now consistently used in every
 *    method's default config instead of being defined and ignored.
 *  - OCIO title bar no longer uses stray literals; uses MARGIN / CONTENT_W.
 *  - Bear-side bx gap in createStrategyPerformanceViz is a named constant (COL_GAP).
 *  - Communication flow node offsets are derived from s.width, not magic numbers.
 *  - Investment flow text-box half-widths are derived from stepW, not raw literals.
 *  - Partial-data guard added to createStrategyPerformanceViz.
 *
 * CANVAS SPEC: 13.333" × 7.5"  (pptxgenjs LAYOUT_WIDE)
 *   Standard content margin: 0.5" left/right
 *   Standard content width:  12.333"
 */

'use strict';

const { POTOMAC_COLORS } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS }  = require('../brand-assets/fonts/potomac-fonts.js');

// Strip leading '#' from brand colors (pptxgenjs does not want the '#' prefix)
function _c(hex) { return hex ? String(hex).replace('#', '') : 'FEC00F'; }

const C = POTOMAC_COLORS;
const F = POTOMAC_FONTS;

// ── Canvas constants ──────────────────────────────────────────────────────────
const CANVAS_W = 13.333;              // LAYOUT_WIDE width in inches
const CANVAS_H = 7.5;                 // slide height in inches
const MARGIN   = 0.5;                 // standard left/right margin
const CONTENT_W = CANVAS_W - MARGIN * 2;  // 12.333"


class PotomacVisualElements {
  constructor(pptxGenerator, options = {}) {
    this.pptx    = pptxGenerator;
    this.options = options;

    this.elementStyles = {
      primaryIcon: {
        fill: { color: _c(C.PRIMARY.YELLOW) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2 },
      },
      secondaryIcon: {
        fill: { color: _c(C.SECONDARY.TURQUOISE) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1 },
      },
      connector: {
        line: { color: _c(C.TONES.GRAY_40), width: 2, dashType: 'solid' },
      },
      accentConnector: {
        line: { color: _c(C.PRIMARY.YELLOW), width: 3, dashType: 'solid' },
      },
    };
  }


  /**
   * Investment Process Flow
   * Visual representation of the investment methodology — 4-step horizontal flow.
   *
   * Default config uses MARGIN / CONTENT_W so the diagram always spans the
   * standard content area regardless of any future canvas changes.
   */
  createInvestmentProcessFlow(slide, config = {}) {
    console.log('🔄 Creating Investment Process Flow...');

    const s = { startX: MARGIN, startY: 2.5, width: CONTENT_W, height: 2.5, ...config };

    const steps = [
      { title: 'RESEARCH',  desc: 'Market Analysis\n& Due Diligence' },
      { title: 'STRATEGY',  desc: 'Portfolio Design\n& Construction' },
      { title: 'EXECUTION', desc: 'Trade Implementation\n& Monitoring' },
      { title: 'REVIEW',    desc: 'Performance Analysis\n& Optimization' },
    ];

    const stepW    = s.width / steps.length;  // evenly divided — adapts if steps change
    const halfStep = stepW / 2;               // reusable half-width for text centering

    steps.forEach((step, idx) => {
      const cx = s.startX + idx * stepW + halfStep;
      const cy = s.startY;
      const R  = 0.4;

      // Circle
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: cx - R, y: cy - R, w: R * 2, h: R * 2,
        fill: { color: _c(C.PRIMARY.YELLOW) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2 },
      });

      // Number
      slide.addText(String(idx + 1), {
        x: cx - R, y: cy - R, w: R * 2, h: R * 2,
        fontFace: F.HEADERS.family, fontSize: 24,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY),
        align: 'center', valign: 'middle',
      });

      // Step title — centred within the step column
      const titleW = halfStep * 1.6;   // 80% of stepW, centred on cx
      slide.addText(step.title, {
        x: cx - titleW / 2, y: cy + R + 0.1, w: titleW, h: 0.4,
        fontFace: F.HEADERS.family, fontSize: 14,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });

      // Step description — slightly wider than the title box
      const descW = stepW * 0.76;      // 76% of stepW gives comfortable text wrap
      slide.addText(step.desc, {
        x: cx - descW / 2, y: cy + R + 0.6, w: descW, h: 1,
        fontFace: F.BODY.family, fontSize: 11,
        color: _c(C.TONES.GRAY_60), align: 'center',
      });

      // Connector line (except last step)
      if (idx < steps.length - 1) {
        const lineX  = cx + R + 0.05;
        const nextCX = s.startX + (idx + 1) * stepW + halfStep - R - 0.05;
        slide.addShape(this.pptx.ShapeType.line, {
          x: lineX, y: cy, w: nextCX - lineX, h: 0,
          line: { color: _c(C.SECONDARY.TURQUOISE), width: 3 },
        });
      }
    });

    // Section title — spans the full content width
    slide.addText('POTOMAC INVESTMENT PROCESS', {
      x: s.startX, y: s.startY - 1, w: s.width, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 20,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Strategy Performance Visualization
   * Bull vs Bear market performance comparison side-by-side boxes.
   *
   * Default config uses MARGIN / CONTENT_W.
   * COL_GAP is the explicit space between the two columns (was opaque 0.533).
   */
  createStrategyPerformanceViz(slide, data, config = {}) {
    console.log('📈 Creating Strategy Performance Visualization...');

    const s = { startX: MARGIN, startY: 1.5, width: CONTENT_W, height: 4, ...config };

    // Merge supplied data with safe defaults; guard against partial objects
    const defaultPerf = {
      bullMarket: { return: '+18.5%', period: '2021-2022' },
      bearMarket: { return: '+3.2%',  period: '2022-2023' },
      benchmark:  { bull: '+12.8%',  bear: '-15.6%' },
    };
    const perf = {
      bullMarket: { ...defaultPerf.bullMarket, ...(data && data.bullMarket) },
      bearMarket: { ...defaultPerf.bearMarket, ...(data && data.bearMarket) },
      benchmark:  { ...defaultPerf.benchmark,  ...(data && data.benchmark)  },
    };

    const COL_GAP = 0.4;                         // explicit gap between the two panels
    const halfW   = (s.width - COL_GAP) / 2;    // each panel's width

    // ── Bull panel ────────────────────────────────────────────────────────────
    const bullX = s.startX;
    slide.addShape(this.pptx.ShapeType.rect, {
      x: bullX, y: s.startY, w: halfW, h: s.height,
      fill: { color: _c(C.SECONDARY.TURQUOISE), transparency: 20 },
      line: { color: _c(C.SECONDARY.TURQUOISE), width: 2 },
    });

    const bullInnerX = bullX + 0.2;
    const bullInnerW = halfW - 0.4;

    slide.addText('BULL MARKET\nPERFORMANCE', {
      x: bullInnerX, y: s.startY + 0.3, w: bullInnerW, h: 0.8,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });
    slide.addText(perf.bullMarket.return, {
      x: bullInnerX, y: s.startY + 1.4, w: bullInnerW, h: 1,
      fontFace: F.HEADERS.family, fontSize: 32,
      bold: true, color: _c(C.SECONDARY.TURQUOISE),
      align: 'center', valign: 'middle',
    });
    slide.addText(`Benchmark: ${perf.benchmark.bull}`, {
      x: bullInnerX, y: s.startY + 2.8, w: bullInnerW, h: 0.4,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    // ── Bear panel ────────────────────────────────────────────────────────────
    const bearX      = s.startX + halfW + COL_GAP;   // derived, not a magic literal
    const bearInnerX = bearX + 0.2;
    const bearInnerW = halfW - 0.4;

    slide.addShape(this.pptx.ShapeType.rect, {
      x: bearX, y: s.startY, w: halfW, h: s.height,
      fill: { color: _c(C.PRIMARY.YELLOW), transparency: 20 },
      line: { color: _c(C.PRIMARY.YELLOW), width: 2 },
    });

    slide.addText('BEAR MARKET\nPERFORMANCE', {
      x: bearInnerX, y: s.startY + 0.3, w: bearInnerW, h: 0.8,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });
    slide.addText(perf.bearMarket.return, {
      x: bearInnerX, y: s.startY + 1.4, w: bearInnerW, h: 1,
      fontFace: F.HEADERS.family, fontSize: 32,
      bold: true, color: _c(C.PRIMARY.YELLOW),
      align: 'center', valign: 'middle',
    });
    slide.addText(`Benchmark: ${perf.benchmark.bear}`, {
      x: bearInnerX, y: s.startY + 2.8, w: bearInnerW, h: 0.4,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  /**
   * Communication Flow Network
   * Four-node ellipse diagram representing the advisor-client-Potomac-research network.
   *
   * Default config uses MARGIN / CONTENT_W.
   * Node x-offsets are derived from s.width fractions (¼, ½, ¾ points), so the
   * layout reflows correctly if startX or width is overridden via config.
   */
  createCommunicationFlow(slide, config = {}) {
    console.log('💬 Creating Communication Flow Diagram...');

    const s = { startX: MARGIN, startY: 1.8, width: CONTENT_W, height: 3.5, ...config };

    // Derive named positional anchors from s.width — no magic offsets.
    const quarterX = s.startX + s.width * (1 / 8);   // left satellite
    const centreX  = s.startX + s.width / 2;          // horizontal midpoint
    const threeQX  = s.startX + s.width * (7 / 8);   // right satellite

    const nodes = [
      { label: 'CLIENT',   x: quarterX, y: s.startY + 1.5, type: 'client'   },
      { label: 'ADVISOR',  x: centreX,  y: s.startY + 0.5, type: 'advisor'  },
      { label: 'POTOMAC',  x: threeQX,  y: s.startY + 1.5, type: 'potomac'  },
      { label: 'RESEARCH', x: centreX,  y: s.startY + 2.5, type: 'research' },
    ];

    nodes.forEach(node => {
      const nodeColor = node.type === 'potomac'  ? _c(C.PRIMARY.YELLOW)
                      : node.type === 'advisor'  ? _c(C.SECONDARY.TURQUOISE)
                      : _c(C.TONES.GRAY_60);

      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: node.x - 0.5, y: node.y - 0.4, w: 1, h: 0.8,
        fill: { color: nodeColor },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2 },
      });

      slide.addText(node.label, {
        x: node.x - 0.5, y: node.y - 0.4, w: 1, h: 0.8,
        fontFace: F.HEADERS.family, fontSize: 10,
        bold: true,
        color: node.type === 'potomac' ? _c(C.PRIMARY.DARK_GRAY) : _c(C.PRIMARY.WHITE),
        align: 'center', valign: 'middle',
      });
    });

    slide.addText('COMMUNICATION & COLLABORATION NETWORK', {
      x: s.startX, y: s.startY - 0.8, w: s.width, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * Firm Structure Network Diagram
   * Central Potomac hub surrounded by four service ellipses.
   *
   * Default config uses MARGIN / CONTENT_W.
   * Satellite offsets are derived from s.width, not hard-wired literals.
   */
  createFirmStructureInfographic(slide, config = {}) {
    console.log('🏗️ Creating Firm Structure Network Diagram...');

    const s = { startX: MARGIN, startY: 1.5, width: CONTENT_W, height: 4.5, ...config };

    const cx = s.startX + s.width / 2;    // true horizontal centre of the diagram
    const cy = s.startY + s.height / 2;

    // Satellite orbit radius — 27% of diagram width, centred on cx
    const ORBIT_X = s.width * 0.27;

    // Central hub
    slide.addShape(this.pptx.ShapeType.ellipse, {
      x: cx - 0.8, y: cy - 0.6, w: 1.6, h: 1.2,
      fill: { color: _c(C.PRIMARY.YELLOW) },
      line: { color: _c(C.PRIMARY.DARK_GRAY), width: 3 },
    });
    slide.addText('POTOMAC', {
      x: cx - 0.8, y: cy - 0.6, w: 1.6, h: 1.2,
      fontFace: F.HEADERS.family, fontSize: 14,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });

    // Satellite nodes — offset ±ORBIT_X from centre
    const serviceNodes = [
      { label: 'INVESTMENT\nSTRATEGIES',  x: cx - ORBIT_X, y: cy - 1.2 },
      { label: 'RESEARCH &\nANALYTICS',   x: cx + ORBIT_X, y: cy - 1.2 },
      { label: 'TAMP\nPLATFORMS',         x: cx - ORBIT_X, y: cy + 1.2 },
      { label: 'GUARDRAILS\nTECHNOLOGY', x: cx + ORBIT_X, y: cy + 1.2 },
    ];

    serviceNodes.forEach(node => {
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: node.x - 0.6, y: node.y - 0.5, w: 1.2, h: 1,
        fill: { color: _c(C.SECONDARY.TURQUOISE) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 2 },
      });
      slide.addText(node.label, {
        x: node.x - 0.6, y: node.y - 0.5, w: 1.2, h: 1,
        fontFace: F.HEADERS.family, fontSize: 9,
        bold: true, color: _c(C.PRIMARY.WHITE),
        align: 'center', valign: 'middle',
      });
    });

    slide.addText('POTOMAC FIRM STRUCTURE & CAPABILITIES', {
      x: s.startX, y: s.startY - 0.8, w: s.width, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 24,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }


  /**
   * OCIO Triangle Visualization
   * Three service nodes around a central OCIO label.
   *
   * Default config uses MARGIN / CONTENT_W throughout — including the title bar,
   * which previously used stray literals (x: 1.333, w: 10.667).
   * Node offsets are derived from s.width so they reflow with any config override.
   */
  createOCIOTriangle(slide, config = {}) {
    console.log('🔺 Creating OCIO Triangle Visualization...');

    const s = {
      startX:  MARGIN,
      width:   CONTENT_W,
      centerX: MARGIN + CONTENT_W / 2,   // true horizontal centre of content area
      centerY: 3.5,
      size:    2.5,
      ...config,
    };

    // Horizontal spread of the two lower nodes — 21% of content width each side
    const SPREAD_X = s.width * 0.21;

    const labels = [
      { text: 'INVESTMENT\nSTRATEGY',    x: s.centerX,            y: s.centerY - 1.5 },
      { text: 'RISK\nMANAGEMENT',        x: s.centerX - SPREAD_X, y: s.centerY + 1   },
      { text: 'PERFORMANCE\nMONITORING', x: s.centerX + SPREAD_X, y: s.centerY + 1   },
    ];

    labels.forEach(label => {
      slide.addShape(this.pptx.ShapeType.ellipse, {
        x: label.x - 0.6, y: label.y - 0.4, w: 1.2, h: 0.8,
        fill: { color: _c(C.SECONDARY.TURQUOISE) },
        line: { color: _c(C.PRIMARY.DARK_GRAY), width: 1 },
      });
      slide.addText(label.text, {
        x: label.x - 0.6, y: label.y - 0.4, w: 1.2, h: 0.8,
        fontFace: F.HEADERS.family, fontSize: 10,
        bold: true, color: _c(C.PRIMARY.WHITE),
        align: 'center', valign: 'middle',
      });
    });

    // Centre label
    slide.addText('OCIO', {
      x: s.centerX - 0.5, y: s.centerY - 0.3, w: 1, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 20,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY),
      align: 'center', valign: 'middle',
    });

    // Title bar — uses s.startX / s.width, not stray literals
    slide.addText('OUTSOURCED CHIEF INVESTMENT OFFICER MODEL', {
      x: s.startX, y: 0.8, w: s.width, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }
}

module.exports = { PotomacVisualElements };