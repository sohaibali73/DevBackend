'use strict';
/**
 * Extra Primitives
 * ================
 * Extends the core primitive set with arrows, ribbons, tabs, stars, chevrons,
 * sticky notes, speech bubbles, badges, timeline markers, callouts, progress
 * bars, etc.  Every function returns the slide for chaining and uses only
 * engine tokens / box math — NO hardcoded inch values.
 *
 * Usage: call `attachExtraPrimitives(prim, { pres, engine, brand })` to
 * receive an extended set of methods on `prim`.
 */

function attachExtraPrimitives(prim, { pres, engine, brand }) {
  const { PALETTE, FONTS } = brand;
  const { fitAspect, centerIn } = engine;
  const hex = prim.hex;

  // ── Helpers ────────────────────────────────────────────────────────────
  const addShape = (slide, type, box, props = {}) => {
    slide.addShape(type, { ...box, ...props });
    return slide;
  };

  const applyFill = (color, gradient) => {
    if (gradient) return { fill: { type: 'solid', color: hex(color) } }; // pptxgenjs solid only
    return { fill: { color: hex(color) } };
  };

  // ── Arrows ─────────────────────────────────────────────────────────────
  const arrow = (slide, box, { color = PALETTE.YELLOW, dir = 'right', stroke } = {}) => {
    const shapes = {
      right: pres.shapes.RIGHT_ARROW, left: pres.shapes.LEFT_ARROW,
      up: pres.shapes.UP_ARROW,       down: pres.shapes.DOWN_ARROW,
      bent: pres.shapes.BENT_ARROW,   uturn: pres.shapes.UTURN_ARROW,
      pentagon: pres.shapes.PENTAGON, chevron: pres.shapes.CHEVRON,
    };
    const props = { fill: { color: hex(color) },
                    line: { color: hex(stroke || color), width: stroke ? 1 : 0 } };
    addShape(slide, shapes[dir] || shapes.right, box, props);
    return slide;
  };

  // ── Chevron (step) ─────────────────────────────────────────────────────
  const chevron = (slide, box, { color = PALETTE.YELLOW, label, labelOpts = {} } = {}) => {
    addShape(slide, pres.shapes.CHEVRON, box,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    if (label) prim.text(slide, label, box, {
      bold: true, align: 'center', valign: 'middle',
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── Ribbon (banner) ────────────────────────────────────────────────────
  const ribbon = (slide, box, { color = PALETTE.YELLOW, label = '', labelOpts = {} } = {}) => {
    addShape(slide, pres.shapes.RIBBON, box,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    if (label) prim.text(slide, label, box, {
      bold: true, align: 'center', valign: 'middle',
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── Star / burst ───────────────────────────────────────────────────────
  const star = (slide, box, { points = 5, color = PALETTE.YELLOW, label, labelOpts = {} } = {}) => {
    const map = {
      4: pres.shapes.STAR_4, 5: pres.shapes.STAR_5, 6: pres.shapes.STAR_6,
      7: pres.shapes.STAR_7, 8: pres.shapes.STAR_8, 10: pres.shapes.STAR_10,
      12: pres.shapes.STAR_12, 16: pres.shapes.STAR_16, 24: pres.shapes.STAR_24,
      32: pres.shapes.STAR_32,
    };
    const shp = map[points] || pres.shapes.STAR_5;
    // regular star fits best in a square box
    const s = Math.min(box.w, box.h);
    const placed = centerIn(box, s, s);
    addShape(slide, shp, placed,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    if (label) prim.text(slide, label, placed, {
      bold: true, align: 'center', valign: 'middle',
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── Badge (circle with number / letter) ────────────────────────────────
  const badge = (slide, box, { label = '1', color = PALETTE.YELLOW, labelOpts = {} } = {}) => {
    const s = Math.min(box.w, box.h);
    const placed = centerIn(box, s, s);
    addShape(slide, pres.shapes.OVAL, placed,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    prim.text(slide, String(label), placed, {
      bold: true, align: 'center', valign: 'middle',
      fontFace: FONTS.HEADLINE,
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── Sticky note (rotated rounded rectangle) ───────────────────────────
  const sticky = (slide, box, { color = PALETTE.YELLOW, label = '', rotate = -2, labelOpts = {} } = {}) => {
    const props = {
      fill: { color: hex(color) }, line: { color: hex(color), width: 0 },
      rectRadius: Math.min(box.w, box.h) * 0.05, rotate,
    };
    addShape(slide, pres.shapes.ROUNDED_RECTANGLE, box, props);
    if (label) prim.text(slide, label, box, {
      align: 'center', valign: 'middle', color: PALETTE.DARK_GRAY,
      rotate, ...labelOpts,
    });
    return slide;
  };

  // ── Speech bubble ──────────────────────────────────────────────────────
  const speech = (slide, box, { color = PALETTE.WHITE, stroke = PALETTE.DARK_GRAY, label, labelOpts = {} } = {}) => {
    addShape(slide, pres.shapes.WEDGE_ROUND_RECT_CALLOUT, box,
      { fill: { color: hex(color) }, line: { color: hex(stroke), width: 1 } });
    if (label) prim.text(slide, label, box, {
      align: 'center', valign: 'middle', color: PALETTE.DARK_GRAY,
      ...labelOpts,
    });
    return slide;
  };

  // ── Tab (top-rounded) ──────────────────────────────────────────────────
  const tab = (slide, box, { color = PALETTE.YELLOW, label = '', labelOpts = {} } = {}) => {
    addShape(slide, pres.shapes.ROUND_SAME_SIDE_RECT, box,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    if (label) prim.text(slide, label, box, {
      bold: true, align: 'center', valign: 'middle',
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── Progress bar ───────────────────────────────────────────────────────
  const progressBar = (slide, box, {
    pct = 0.5, color = PALETTE.YELLOW, trackColor = PALETTE.GRAY_20,
    label, labelOpts = {},
  } = {}) => {
    const track = { ...box };
    const fill = { x: box.x, y: box.y, w: box.w * Math.max(0, Math.min(1, pct)), h: box.h };
    const radius = box.h / 2;
    addShape(slide, pres.shapes.ROUNDED_RECTANGLE, track,
      { fill: { color: hex(trackColor) }, line: { color: hex(trackColor), width: 0 },
        rectRadius: radius });
    if (fill.w > 0) {
      addShape(slide, pres.shapes.ROUNDED_RECTANGLE, fill,
        { fill: { color: hex(color) }, line: { color: hex(color), width: 0 },
          rectRadius: radius });
    }
    if (label) prim.text(slide, label, box, {
      bold: true, align: 'center', valign: 'middle',
      color: PALETTE.DARK_GRAY, ...labelOpts,
    });
    return slide;
  };

  // ── KPI card (value + label + delta) ───────────────────────────────────
  const kpiCard = (slide, box, {
    value = '', label = '', delta = '', deltaSign = 'up',
    theme = { bg: PALETTE.WHITE, on: PALETTE.DARK_GRAY, accent: PALETTE.YELLOW },
  } = {}) => {
    // background
    addShape(slide, pres.shapes.ROUNDED_RECTANGLE, box,
      { fill: { color: hex(theme.bg) }, line: { color: hex(theme.stroke || theme.accent), width: 1 },
        rectRadius: Math.min(box.w, box.h) * 0.06 });
    const s = engine.stack({ x: box.x + box.w * 0.08, y: box.y + box.h * 0.1,
                             w: box.w * 0.84, gap: box.h * 0.03 });
    const valH = box.h * 0.45;
    const lblH = box.h * 0.18;
    const dltH = box.h * 0.18;
    prim.text(slide, value, s.place(valH), {
      bold: true, align: 'center', valign: 'middle',
      fontFace: FONTS.HEADLINE, color: theme.accent,
      maxPt: Math.floor(valH * 72 * 0.7), minPt: 20,
    });
    prim.text(slide, label, s.place(lblH), {
      align: 'center', valign: 'middle', color: theme.on, maxPt: 16, minPt: 9,
    });
    if (delta) {
      const sign = deltaSign === 'up' ? '▲' : deltaSign === 'down' ? '▼' : '●';
      const color = deltaSign === 'up' ? PALETTE.GREEN
                 : deltaSign === 'down' ? PALETTE.RED : PALETTE.GRAY_60;
      prim.text(slide, sign + ' ' + delta, s.place(dltH), {
        bold: true, align: 'center', valign: 'middle',
        color, maxPt: 14, minPt: 9,
      });
    }
    return slide;
  };

  // ── Timeline marker (dot + line + caption) ─────────────────────────────
  const timelineDot = (slide, { x, y }, {
    label = '', subLabel = '', color = PALETTE.YELLOW, radius, direction = 'up',
  } = {}) => {
    const r = radius || engine.H * 0.02;
    addShape(slide, pres.shapes.OVAL,
      { x: x - r, y: y - r, w: r * 2, h: r * 2 },
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    if (label) {
      const w = engine.W * 0.14, h = engine.H * 0.05;
      const lx = x - w / 2;
      const ly = direction === 'up' ? (y - r - h - engine.H * 0.01)
                                    : (y + r + engine.H * 0.01);
      prim.text(slide, label, { x: lx, y: ly, w, h }, {
        bold: true, align: 'center', valign: 'middle',
        color: PALETTE.DARK_GRAY, maxPt: 12, minPt: 8,
      });
      if (subLabel) {
        const sly = direction === 'up' ? ly - h * 0.8 : ly + h;
        prim.text(slide, subLabel, { x: lx, y: sly, w, h: h * 0.8 }, {
          align: 'center', valign: 'middle',
          color: PALETTE.GRAY_60, maxPt: 10, minPt: 8,
        });
      }
    }
    return slide;
  };

  // ── Rating stars row ───────────────────────────────────────────────────
  const ratingStars = (slide, { x, y, h, gap }, {
    rating = 5, total = 5, color = PALETTE.YELLOW, muted = PALETTE.GRAY_20,
  } = {}) => {
    const g = gap !== undefined ? gap : h * 0.15;
    for (let i = 0; i < total; i++) {
      const cx = x + i * (h + g);
      const filled = i < Math.round(rating);
      addShape(slide, pres.shapes.STAR_5,
        { x: cx, y, w: h, h },
        { fill: { color: hex(filled ? color : muted) },
          line: { color: hex(filled ? color : muted), width: 0 } });
    }
    return slide;
  };

  // ── Callout box (small pop with arrow) ─────────────────────────────────
  const callout = (slide, box, {
    color = PALETTE.YELLOW_20, stroke = PALETTE.YELLOW, label = '', labelOpts = {},
  } = {}) => {
    addShape(slide, pres.shapes.ROUNDED_RECTANGLE, box,
      { fill: { color: hex(color) }, line: { color: hex(stroke), width: 1 },
        rectRadius: Math.min(box.w, box.h) * 0.15 });
    if (label) prim.text(slide, label, box, {
      align: 'center', valign: 'middle', color: PALETTE.DARK_GRAY,
      ...labelOpts,
    });
    return slide;
  };

  // ── Number circle (for numbered lists) ─────────────────────────────────
  const numberCircle = (slide, box, { n = 1, color = PALETTE.YELLOW, onColor = PALETTE.DARK_GRAY } = {}) => {
    return badge(slide, box, { label: String(n), color,
                               labelOpts: { color: onColor, fontFace: FONTS.HEADLINE } });
  };

  // ── Key-value pair (right-aligned label, left value) ───────────────────
  const keyValue = (slide, box, { label = '', value = '', accent = PALETTE.YELLOW } = {}) => {
    const labelW = box.w * 0.45;
    const valW = box.w - labelW;
    prim.text(slide, String(label).toUpperCase(),
      { x: box.x, y: box.y, w: labelW, h: box.h },
      { fontFace: FONTS.HEADLINE, bold: true, align: 'right', valign: 'middle',
        color: PALETTE.GRAY_60, maxPt: 12, minPt: 8 });
    prim.text(slide, String(value),
      { x: box.x + labelW + box.w * 0.03, y: box.y, w: valW - box.w * 0.03, h: box.h },
      { bold: true, align: 'left', valign: 'middle',
        color: accent, maxPt: 16, minPt: 9, fontFace: FONTS.HEADLINE });
    return slide;
  };

  // ── Checkmark circle ───────────────────────────────────────────────────
  const checkCircle = (slide, box, { color = PALETTE.GREEN } = {}) => {
    const r = Math.min(box.w, box.h) / 2;
    const placed = centerIn(box, r * 2, r * 2);
    addShape(slide, pres.shapes.OVAL, placed,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    prim.text(slide, '✓', placed, {
      bold: true, align: 'center', valign: 'middle',
      fontFace: FONTS.HEADLINE, color: PALETTE.WHITE,
      maxPt: Math.floor(placed.h * 72 * 0.7),
    });
    return slide;
  };

  // ── Icon box (icon placeholder with label below) ──────────────────────
  const iconBox = (slide, box, {
    icon = '●', iconColor = PALETTE.YELLOW, label = '', subLabel = '',
    bg = null, onColor = PALETTE.DARK_GRAY,
  } = {}) => {
    if (bg) addShape(slide, pres.shapes.ROUNDED_RECTANGLE, box,
      { fill: { color: hex(bg) }, line: { color: hex(bg), width: 0 },
        rectRadius: Math.min(box.w, box.h) * 0.08 });
    const iconH = box.h * 0.5;
    const lblH  = box.h * 0.25;
    const subH  = subLabel ? box.h * 0.2 : 0;
    prim.text(slide, icon,
      { x: box.x, y: box.y + box.h * 0.05, w: box.w, h: iconH },
      { bold: true, align: 'center', valign: 'middle',
        color: iconColor, fontFace: FONTS.HEADLINE,
        maxPt: Math.floor(iconH * 72 * 0.8) });
    if (label) prim.text(slide, label,
      { x: box.x, y: box.y + box.h * 0.05 + iconH, w: box.w, h: lblH },
      { bold: true, align: 'center', valign: 'middle',
        color: onColor, maxPt: 14, minPt: 9, fontFace: FONTS.HEADLINE });
    if (subLabel) prim.text(slide, subLabel,
      { x: box.x, y: box.y + box.h * 0.05 + iconH + lblH, w: box.w, h: subH },
      { align: 'center', valign: 'middle',
        color: PALETTE.GRAY_60, maxPt: 11, minPt: 8 });
    return slide;
  };

  // ── Gradient-feel band (two-tone horizontal band) ─────────────────────
  const band = (slide, box, { colorA = PALETTE.YELLOW, colorB = PALETTE.DARK_GRAY, split = 0.5 } = {}) => {
    const wA = box.w * Math.max(0, Math.min(1, split));
    addShape(slide, pres.shapes.RECTANGLE, { ...box, w: wA },
      { fill: { color: hex(colorA) }, line: { color: hex(colorA), width: 0 } });
    addShape(slide, pres.shapes.RECTANGLE,
      { x: box.x + wA, y: box.y, w: box.w - wA, h: box.h },
      { fill: { color: hex(colorB) }, line: { color: hex(colorB), width: 0 } });
    return slide;
  };

  // ── Attach everything to prim ──────────────────────────────────────────
  return Object.assign(prim, {
    arrow, chevron, ribbon, star, badge, sticky, speech, tab,
    progressBar, kpiCard, timelineDot, ratingStars, callout,
    numberCircle, keyValue, checkCircle, iconBox, band,
  });
}

module.exports = { attachExtraPrimitives };
