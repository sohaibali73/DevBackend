/**
 * Potomac Visual Elements & Infographics — Phase 3 (Fixed)
 *
 * FIXES applied:
 *  - slide.addShape('ellipse'/'rect'/'line', ...) → this.pptx.ShapeType.*  (v3 API)
 *  - fontWeight: 'bold' → bold: true
 *  - _c() helper strips '#' from brand color hex strings
 */

'use strict';

const { POTOMAC_COLORS } = require('../brand-assets/colors/potomac-colors.js');
const { POTOMAC_FONTS }  = require('../brand-assets/fonts/potomac-fonts.js');

// Strip leading '#' from brand colors (pptxgenjs does not want the '#' prefix)
function _c(hex) { return hex ? String(hex).replace('#', '') : 'FEC00F'; }

const C = POTOMAC_COLORS;
const F = POTOMAC_FONTS;


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
   */
  createInvestmentProcessFlow(slide, config = {}) {
    console.log('🔄 Creating Investment Process Flow...');

    const s = { startX: 0.8, startY: 2.5, width: 8.4, height: 2.5, ...config };

    const steps = [
      { title: 'RESEARCH',  desc: 'Market Analysis\n& Due Diligence' },
      { title: 'STRATEGY',  desc: 'Portfolio Design\n& Construction' },
      { title: 'EXECUTION', desc: 'Trade Implementation\n& Monitoring' },
      { title: 'REVIEW',    desc: 'Performance Analysis\n& Optimization' },
    ];

    const stepW = s.width / steps.length;

    steps.forEach((step, idx) => {
      const cx = s.startX + idx * stepW + stepW / 2;
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

      // Step title
      slide.addText(step.title, {
        x: cx - 0.6, y: cy + R + 0.1, w: 1.2, h: 0.4,
        fontFace: F.HEADERS.family, fontSize: 14,
        bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
      });

      // Step description
      slide.addText(step.desc, {
        x: cx - 0.8, y: cy + R + 0.6, w: 1.6, h: 1,
        fontFace: F.BODY.family, fontSize: 11,
        color: _c(C.TONES.GRAY_60), align: 'center',
      });

      // Connector line (except last step)
      if (idx < steps.length - 1) {
        const lineX    = cx + R + 0.05;
        const nextCX   = s.startX + (idx + 1) * stepW + stepW / 2 - R - 0.05;
        slide.addShape(this.pptx.ShapeType.line, {
          x: lineX, y: cy, w: nextCX - lineX, h: 0,
          line: { color: _c(C.SECONDARY.TURQUOISE), width: 3 },
        });
      }
    });

    // Section title
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
   */
  createStrategyPerformanceViz(slide, data, config = {}) {
    console.log('📈 Creating Strategy Performance Visualization...');

    const s = { startX: 1, startY: 1.5, width: 8, height: 4, ...config };

    const perf = data || {
      bullMarket: { return: '+18.5%', period: '2021-2022' },
      bearMarket: { return: '+3.2%',  period: '2022-2023' },
      benchmark:  { bull: '+12.8%',  bear: '-15.6%' },
    };

    const halfW = s.width / 2 - 0.2;

    // Bull section
    slide.addShape(this.pptx.ShapeType.rect, {
      x: s.startX, y: s.startY, w: halfW, h: s.height,
      fill: { color: _c(C.SECONDARY.TURQUOISE), transparency: 20 },
      line: { color: _c(C.SECONDARY.TURQUOISE), width: 2 },
    });

    // Bear section
    slide.addShape(this.pptx.ShapeType.rect, {
      x: s.startX + s.width / 2 + 0.2, y: s.startY, w: halfW, h: s.height,
      fill: { color: _c(C.PRIMARY.YELLOW), transparency: 20 },
      line: { color: _c(C.PRIMARY.YELLOW), width: 2 },
    });

    // Bull content
    slide.addText('BULL MARKET\nPERFORMANCE', {
      x: s.startX + 0.2, y: s.startY + 0.3, w: halfW - 0.4, h: 0.8,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });
    slide.addText(perf.bullMarket.return, {
      x: s.startX + 0.2, y: s.startY + 1.4, w: halfW - 0.4, h: 1,
      fontFace: F.HEADERS.family, fontSize: 32,
      bold: true, color: _c(C.SECONDARY.TURQUOISE),
      align: 'center', valign: 'middle',
    });
    slide.addText(`Benchmark: ${perf.benchmark.bull}`, {
      x: s.startX + 0.2, y: s.startY + 2.8, w: halfW - 0.4, h: 0.4,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    // Bear content
    const bx = s.startX + s.width / 2 + 0.4;
    slide.addText('BEAR MARKET\nPERFORMANCE', {
      x: bx, y: s.startY + 0.3, w: halfW - 0.4, h: 0.8,
      fontFace: F.HEADERS.family, fontSize: 16,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });
    slide.addText(perf.bearMarket.return, {
      x: bx, y: s.startY + 1.4, w: halfW - 0.4, h: 1,
      fontFace: F.HEADERS.family, fontSize: 32,
      bold: true, color: _c(C.PRIMARY.YELLOW),
      align: 'center', valign: 'middle',
    });
    slide.addText(`Benchmark: ${perf.benchmark.bear}`, {
      x: bx, y: s.startY + 2.8, w: halfW - 0.4, h: 0.4,
      fontFace: F.BODY.family, fontSize: 10,
      color: _c(C.TONES.GRAY_60), align: 'center',
    });

    return slide;
  }


  /**
   * Communication Flow Network
   * Four-node ellipse diagram representing the advisor-client-Potomac-research network.
   */
  createCommunicationFlow(slide, config = {}) {
    console.log('💬 Creating Communication Flow Diagram...');

    const s = { startX: 1, startY: 1.8, width: 8, height: 3.5, ...config };

    const nodes = [
      { label: 'CLIENT',   x: s.startX + 1, y: s.startY + 1.5, type: 'client' },
      { label: 'ADVISOR',  x: s.startX + 4, y: s.startY + 0.5, type: 'advisor' },
      { label: 'POTOMAC',  x: s.startX + 7, y: s.startY + 1.5, type: 'potomac' },
      { label: 'RESEARCH', x: s.startX + 4, y: s.startY + 2.5, type: 'research' },
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
   */
  createFirmStructureInfographic(slide, config = {}) {
    console.log('🏗️ Creating Firm Structure Network Diagram...');

    const s = { startX: 0.5, startY: 1.5, width: 9, height: 4.5, ...config };

    const cx = s.startX + s.width / 2;
    const cy = s.startY + s.height / 2;

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

    // Satellite nodes
    const serviceNodes = [
      { label: 'INVESTMENT\nSTRATEGIES',  x: cx - 2.5, y: cy - 1.2 },
      { label: 'RESEARCH &\nANALYTICS',   x: cx + 2.5, y: cy - 1.2 },
      { label: 'TAMP\nPLATFORMS',         x: cx - 2.5, y: cy + 1.2 },
      { label: 'GUARDRAILS\nTECHNOLOGY', x: cx + 2.5, y: cy + 1.2 },
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
   */
  createOCIOTriangle(slide, config = {}) {
    console.log('🔺 Creating OCIO Triangle Visualization...');

    const s = { centerX: 5, centerY: 3.5, size: 2.5, ...config };

    const labels = [
      { text: 'INVESTMENT\nSTRATEGY',    x: s.centerX,     y: s.centerY - 1.5 },
      { text: 'RISK\nMANAGEMENT',        x: s.centerX - 2, y: s.centerY + 1   },
      { text: 'PERFORMANCE\nMONITORING', x: s.centerX + 2, y: s.centerY + 1   },
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

    slide.addText('OUTSOURCED CHIEF INVESTMENT OFFICER MODEL', {
      x: 1, y: 0.8, w: 8, h: 0.6,
      fontFace: F.HEADERS.family, fontSize: 18,
      bold: true, color: _c(C.PRIMARY.DARK_GRAY), align: 'center',
    });

    return slide;
  }
}

module.exports = { PotomacVisualElements };
