'use strict';
/**
 * Primitive Drawing Library
 * =========================
 * Reusable brand-consistent building blocks.  Every function accepts a box
 * (produced by the layout engine) and returns the slide for chaining.
 *
 * NO HARDCODED MEASUREMENTS.  All internal paddings/strokes are derived
 * from the provided box via fractional tokens.
 */

function buildPrimitives({ pres, engine, brand, logos, resolveAsset }) {
  const { PALETTE, FONTS } = brand;
  const { tokens, autoFit, fitAspect, centerIn, clampBox } = engine;

  // ── Internal helpers ──────────────────────────────────────────────────────
  const warn = (msg) => { process.stderr.write('WARN:primitive ' + msg + '\n'); };

  /** Coerce a color name (PALETTE key) or hex string to a pptxgenjs hex. */
  const hex = (c) => {
    if (!c) return PALETTE.DARK_GRAY;
    if (PALETTE[c]) return PALETTE[c];
    return c.replace('#', '').toUpperCase();
  };

  /** A safe addShape — clamps boxes, logs overflow */
  const shape = (slide, shapeType, box, props = {}) => {
    const { box: clamped, clipped, warning } = clampBox(box);
    if (clipped) warn(`shape clipped (${warning})`);
    slide.addShape(shapeType, { ...clamped, ...props });
    return slide;
  };

  /** A safe addText with auto-fit support */
  const text = (slide, content, box, opts = {}) => {
    const { box: clamped, clipped, warning } = clampBox(box);
    if (clipped) warn(`text clipped (${warning})`);

    const fontFace = opts.fontFace || FONTS.BODY;
    let fontSize = opts.fontSize;

    if (opts.autoFit !== false && !fontSize) {
      // choose a safe max based on box height
      const maxPt = opts.maxPt || Math.floor(clamped.h * 72 * 0.5);
      const minPt = opts.minPt || 9;
      const fit = autoFit(String(content || ''), clamped, {
        fontFace, minPt, maxPt,
        lineHeight: opts.lineHeight || 1.2,
      });
      fontSize = fit.pt;
    }
    fontSize = fontSize || 12;

    const textOpts = {
      ...clamped,
      fontFace,
      fontSize,
      color: hex(opts.color || PALETTE.DARK_GRAY),
      bold: !!opts.bold,
      italic: !!opts.italic,
      align: opts.align || 'left',
      valign: opts.valign || 'top',
      fit: opts.fit || 'shrink',  // let PptxGenJS shrink too
    };
    if (opts.bullet)     textOpts.bullet = opts.bullet;
    if (opts.paraSpaceBef) textOpts.paraSpaceBef = opts.paraSpaceBef;
    if (opts.paraSpaceAft) textOpts.paraSpaceAft = opts.paraSpaceAft;
    if (opts.charSpacing)  textOpts.charSpacing = opts.charSpacing;
    if (opts.lineSpacing)  textOpts.lineSpacing = opts.lineSpacing;
    if (opts.rotate !== undefined) textOpts.rotate = opts.rotate;

    slide.addText(content, textOpts);
    return slide;
  };

  /**
   * Rectangle (optionally filled / stroked) with optional text overlay.
   */
  const rect = (slide, box, {
    fill, stroke, strokeW, label, labelOpts = {},
  } = {}) => {
    const props = {};
    if (fill)    props.fill = { color: hex(fill) };
    if (stroke)  props.line = { color: hex(stroke), width: strokeW || 1 };
    shape(slide, pres.shapes.RECTANGLE, box, props);
    if (label) text(slide, label, box, labelOpts);
    return slide;
  };

  /**
   * Rounded-corner rectangle (pptxgenjs ROUNDED_RECTANGLE).  Radius is
   * specified as a FRACTION of the shorter side, so it scales dynamically.
   */
  const roundRect = (slide, box, {
    fill, stroke, strokeW, radiusFrac = 0.15, label, labelOpts = {},
  } = {}) => {
    const props = { rectRadius: Math.min(box.w, box.h) * radiusFrac };
    if (fill)   props.fill = { color: hex(fill) };
    if (stroke) props.line = { color: hex(stroke), width: strokeW || 1 };
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, box, props);
    if (label) text(slide, label, box, labelOpts);
    return slide;
  };

  /**
   * "Pill" = rounded rectangle with radius = h/2.  Perfect for the
   * yellow capsule badges in the target screenshot.
   */
  const pill = (slide, box, {
    fill = PALETTE.YELLOW, stroke = null, label = '', labelOpts = {},
  } = {}) => {
    const props = { rectRadius: box.h / 2 };
    props.fill = { color: hex(fill) };
    if (stroke) props.line = { color: hex(stroke), width: 1 };
    else        props.line = { color: hex(fill),   width: 0 };
    shape(slide, pres.shapes.ROUNDED_RECTANGLE, box, props);
    if (label) {
      text(slide, label, box, {
        fontFace: FONTS.BODY,
        bold: true,
        color: PALETTE.DARK_GRAY,
        align: 'center',
        valign: 'middle',
        maxPt: Math.floor(box.h * 72 * 0.5),
        ...labelOpts,
      });
    }
    return slide;
  };

  /** Ellipse / circle */
  const ellipse = (slide, box, { fill, stroke, strokeW, label, labelOpts = {} } = {}) => {
    const props = {};
    if (fill)   props.fill = { color: hex(fill) };
    if (stroke) props.line = { color: hex(stroke), width: strokeW || 1 };
    shape(slide, pres.shapes.ELLIPSE, box, props);
    if (label) text(slide, label, box, { align: 'center', valign: 'middle', ...labelOpts });
    return slide;
  };

  /**
   * Regular hexagon (PptxGenJS built-in HEXAGON shape).
   *
   * A regular pointy-top hexagon has aspect ratio w/h = sqrt(3)/2 ≈ 0.8660.
   * PptxGenJS draws the HEXAGON prstGeom to fill whatever w×h it's given, so
   * if the caller passes a non-hex-ratio box the result is stretched.
   *
   * We always shrink (never grow) the caller's box to the nearest regular
   * hex shape and center it inside.  Pass `orient:'flat'` for flat-top
   * hexagons (aspect = 2/sqrt(3) ≈ 1.1547).
   */
  const HEX_ASPECT = {
    pointy: Math.sqrt(3) / 2, // 0.8660  — taller than wide
    flat:   2 / Math.sqrt(3), // 1.1547  — wider than tall
  };
  const hexagon = (slide, box, {
    fill = PALETTE.YELLOW, stroke, orient = 'pointy', regular = true,
  } = {}) => {
    const props = { fill: { color: hex(fill) } };
    if (stroke) props.line = { color: hex(stroke), width: 1 };
    else        props.line = { color: hex(fill), width: 0 };
    let target = box;
    if (regular) {
      const aspect = HEX_ASPECT[orient] || HEX_ASPECT.pointy;
      const fit = fitAspect(aspect, box.w, box.h);
      target = centerIn(box, fit.w, fit.h);
    }
    shape(slide, pres.shapes.HEXAGON, target, props);
    return slide;
  };

  /**
   * Hex tile: hexagon + centered icon + label + optional sub-line.
   * Used for the "Our Strategies" row in the screenshot.
   */
  const hexTile = (slide, box, {
    fill = PALETTE.YELLOW, iconKey, iconData, label = '', subline = '',
    labelColor = PALETTE.WHITE, sublineColor = PALETTE.WHITE,
  } = {}) => {
    // Vertical stack inside the tile
    const labelH   = box.h * 0.15;
    const sublineH = subline ? box.h * 0.09 : 0;
    const hexH     = box.h - labelH - sublineH - box.h * 0.05;

    const hexBox = { x: box.x, y: box.y, w: box.w, h: hexH };
    hexagon(slide, hexBox, { fill });

    // Icon centered inside hex (70% of hex)
    const iconRes = iconData || (iconKey && resolveAsset && resolveAsset(iconKey));
    if (iconRes && iconRes.dataUrl) {
      const maxIconW = hexBox.w * 0.55;
      const maxIconH = hexBox.h * 0.55;
      const aspect = iconRes.aspect || 1;
      const fit = fitAspect(aspect, maxIconW, maxIconH);
      const ib = centerIn(hexBox, fit.w, fit.h);
      slide.addImage({ data: iconRes.dataUrl, ...ib });
    }

    // Label
    if (label) {
      const labelBox = { x: box.x, y: hexBox.y + hexH + box.h * 0.025, w: box.w, h: labelH };
      text(slide, label, labelBox, {
        fontFace: FONTS.BODY, bold: true, align: 'center', valign: 'top',
        color: labelColor,
        maxPt: Math.floor(labelH * 72 * 0.55),
      });
      // yellow underline beneath label
      const uH = box.h * 0.008;
      shape(slide, pres.shapes.RECTANGLE, {
        x: box.x + box.w * 0.25,
        y: labelBox.y + labelH,
        w: box.w * 0.5,
        h: uH,
      }, { fill: { color: PALETTE.YELLOW }, line: { color: PALETTE.YELLOW, width: 0 } });
    }

    // Subline
    if (subline) {
      const subBox = { x: box.x, y: box.y + box.h - sublineH, w: box.w, h: sublineH };
      text(slide, subline, subBox, {
        fontFace: FONTS.BODY, align: 'center', valign: 'middle',
        color: sublineColor,
        maxPt: Math.floor(sublineH * 72 * 0.6),
      });
    }
    return slide;
  };

  /**
   * Full-bleed yellow frame for CTA / closing slides (matches the
   * "Built to Conquer Risk" screenshot).
   */
  const framedSlide = (slide, {
    insetFrac = 0.04, strokeColor = PALETTE.YELLOW, strokeW = 3,
    fillColor = null,
  } = {}) => {
    const inset = Math.min(engine.W, engine.H) * insetFrac;
    const frame = {
      x: inset, y: inset,
      w: engine.W - inset * 2, h: engine.H - inset * 2,
    };
    const props = { line: { color: hex(strokeColor), width: strokeW } };
    if (fillColor) props.fill = { color: hex(fillColor) };
    else           props.fill = { type: 'none' };
    shape(slide, pres.shapes.RECTANGLE, frame, props);
    return frame;
  };

  /**
   * Left yellow accent bar (standard chrome).
   */
  const accentBar = (slide, { width, color = PALETTE.YELLOW } = {}) => {
    const w = width !== undefined ? width : tokens.accentBarW();
    shape(slide, pres.shapes.RECTANGLE,
      { x: 0, y: 0, w, h: engine.H },
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } },
    );
    return slide;
  };

  /**
   * Yellow underline beneath a title.  Box = title's rect; this places the
   * underline directly beneath it.
   */
  const titleUnderline = (slide, titleBox, { widthFrac = 0.2, color = PALETTE.YELLOW } = {}) => {
    const box = {
      x: titleBox.x,
      y: titleBox.y + titleBox.h,
      w: titleBox.w * widthFrac,
      h: tokens.ulineH(),
    };
    shape(slide, pres.shapes.RECTANGLE, box,
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    return slide;
  };

  /**
   * Place a logo inside a box, preserving its native aspect ratio.
   *
   * We rely on the aspect measured from the PNG header by brand.loadLogos().
   * To make PptxGenJS respect that aspect even if PowerPoint tries to stretch
   * the image later, we:
   *   1. Shrink the placement rect to fit the aspect (centerIn).
   *   2. Pass `sizing:{type:'contain', w, h}` so the underlying pic XML keeps
   *      its intrinsic ratio regardless of any container resize.
   */
  const placeLogo = (slide, box, variant = 'full') => {
    const logo = logos[variant] || logos.full || logos.icon;
    if (!logo) {
      text(slide, 'POTOMAC', box, {
        fontFace: FONTS.HEADLINE, bold: true,
        color: PALETTE.DARK_GRAY, align: 'center', valign: 'middle',
        maxPt: 18,
      });
      return slide;
    }
    const aspect = logo.aspect || 3.6;
    const fit = fitAspect(aspect, box.w, box.h);
    const placed = centerIn(box, fit.w, fit.h);
    slide.addImage({
      data: logo.dataUrl,
      ...placed,
      sizing: { type: 'contain', w: placed.w, h: placed.h },
    });
    return slide;
  };

  /**
   * Horizontal or vertical connector line.
   */
  const connector = (slide, from, to, {
    color = PALETTE.GRAY_20, thickness,
  } = {}) => {
    const t = thickness !== undefined ? thickness : engine.H * 0.003;
    const x = Math.min(from.x, to.x);
    const y = Math.min(from.y, to.y);
    const w = Math.max(Math.abs(to.x - from.x), t);
    const h = Math.max(Math.abs(to.y - from.y), t);
    shape(slide, pres.shapes.RECTANGLE, { x, y, w, h },
      { fill: { color: hex(color) }, line: { color: hex(color), width: 0 } });
    return slide;
  };

  /**
   * Glyph text (plus, equals, arrow).  Sized dynamically to fill its box.
   */
  const glyph = (slide, box, symbol, { color = PALETTE.YELLOW } = {}) => {
    text(slide, symbol, box, {
      fontFace: FONTS.HEADLINE,
      bold: true,
      color: hex(color),
      align: 'center',
      valign: 'middle',
      maxPt: Math.floor(Math.min(box.w, box.h) * 72 * 0.6),
    });
    return slide;
  };

  /**
   * Image (base64 or file) with aspect-preserving fit inside a box.
   */
  const image = (slide, box, { data, aspect, align = 'center' } = {}) => {
    if (!data) return slide;
    let b = box;
    if (aspect) {
      const fit = fitAspect(aspect, box.w, box.h);
      if (align === 'center') b = centerIn(box, fit.w, fit.h);
      else if (align === 'left') b = { x: box.x, y: box.y + (box.h - fit.h) / 2, w: fit.w, h: fit.h };
      else if (align === 'right') b = { x: box.x + box.w - fit.w, y: box.y + (box.h - fit.h) / 2, w: fit.w, h: fit.h };
    }
    slide.addImage({ data, ...b });
    return slide;
  };

  // ── High-level slide chrome ───────────────────────────────────────────────
  /**
   * Default top-right logo spot.
   */
  const cornerLogo = (slide, corner = 'tr', variant = 'full') => {
    const w = tokens.logoW(), h = tokens.logoH();
    const m = tokens.marginH(), mv = tokens.marginV();
    let x, y;
    if (corner === 'tr') { x = engine.W - m - w; y = mv; }
    else if (corner === 'tl') { x = m; y = mv; }
    else if (corner === 'br') { x = engine.W - m - w; y = engine.H - mv - h; }
    else { x = m; y = engine.H - mv - h; }
    placeLogo(slide, { x, y, w, h }, variant);
    return slide;
  };

  /**
   * Standard chrome block: accent bar + top-right logo + title + underline.
   * Returns the rect beneath the chrome (suitable for body content).
   */
  const standardChrome = (slide, { title = '', subtitle = '', theme = 'light', logoVariant } = {}) => {
    accentBar(slide);
    const isDark = theme === 'dark';
    const titleColor = isDark ? PALETTE.WHITE : PALETTE.DARK_GRAY;
    const subColor   = isDark ? PALETTE.GRAY_40 : PALETTE.GRAY_60;
    const variant = logoVariant || (isDark ? 'icon_yellow' : 'full');
    cornerLogo(slide, 'tr', variant);

    const m = tokens.marginH(), mv = tokens.marginV();
    const logoW = tokens.logoW();
    const titleW = engine.W - m - m - logoW - m * 0.2;
    const titleBox = { x: m, y: mv, w: titleW, h: tokens.titleH() };
    text(slide, String(title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true, color: titleColor,
      valign: 'middle', maxPt: 30, minPt: 14,
    });
    titleUnderline(slide, titleBox);

    if (subtitle) {
      const subBox = {
        x: m,
        y: titleBox.y + titleBox.h + tokens.ulineH() + engine.H * 0.005,
        w: titleW, h: engine.H * 0.04,
      };
      text(slide, subtitle, subBox, {
        fontFace: FONTS.BODY, italic: true, color: subColor,
        valign: 'middle', maxPt: 12, minPt: 9,
      });
    }
    // Return content area below chrome
    const chromeBottom = titleBox.y + titleBox.h + tokens.ulineH()
      + tokens.titleGap() + (subtitle ? engine.H * 0.045 : 0);
    return {
      x: m, y: chromeBottom,
      w: engine.W - m * 2, h: engine.H - chromeBottom - mv,
    };
  };

  return {
    PALETTE, FONTS,
    hex,
    shape, text, rect, roundRect, pill, ellipse,
    hexagon, hexTile, framedSlide,
    accentBar, titleUnderline,
    placeLogo, cornerLogo, standardChrome,
    connector, glyph, image,
  };
}

module.exports = { buildPrimitives };
