'use strict';
/**
 * Potomac University Template Pack  (1:1 with the reference PPTX)
 * ===============================================================
 * Coordinates & sizes in this file are derived directly from the user's
 * reference PPTX (`Potomac_University_Template-1.pptx`) by parsing its
 * DrawingML XML and converting EMU values to inches.  The reference canvas
 * is 13.333" × 7.5"; every constant here is expressed as a FRACTION of the
 * canvas so the templates scale cleanly to any preset (wide/standard/A4).
 *
 * Templates (exact 1:1 with the 8 reference slides):
 *   university_title              — dark bg + centered shield
 *   university_yellow_cover       — yellow bg + centered title + byline + rule + wordmark
 *   university_welcome_photo      — full-bleed photo/dark + centered white headline
 *   university_trend_chart        — HISTORY eyebrow + title + chart/image + caption
 *   university_pennant            — yellow bg + left pennant w/ shield + right headline
 *   university_number_trio        — HISTORY eyebrow + title + 3 outer-ring circles w/ filled-dot numbers + labels + hints
 *   university_bullets_photo      — HISTORY eyebrow + title + left square-dot bullets + right full-bleed photo
 *   university_thank_you          — yellow bg + centered "THANK YOU!" + wordmark
 *
 * Palette (matches reference exactly):
 *   background dark : #202020
 *   yellow          : #FDC00E  (note: slightly different from brand YELLOW #FEC00F)
 *   black           : #000000
 *   white           : #FFFFFF
 *
 * NO black top/bottom bars (the screenshot letterboxing was just viewer
 * chrome — the real slides are full-bleed).
 */

function buildUniversityTemplates(ctx) {
  const { pres, engine, prim, brand, resolveAsset } = ctx;
  const { PALETTE, FONTS } = brand;

  // ── Reference palette (exact colors from the PPTX) ──────────────────────
  const UNIV = {
    DARK:     '202020',
    BLACK:    '000000',
    WHITE:    'FFFFFF',
    YELLOW:   'FDC00E',
    GRAY_60:  '808080',
  };

  // Reference canvas was 13.333 × 7.5; scaling functions convert a constant
  // expressed in reference inches to a fraction of the current engine canvas.
  const REF_W = 13.333, REF_H = 7.5;
  const rx = (xIn) => (xIn / REF_W) * engine.W;
  const ry = (yIn) => (yIn / REF_H) * engine.H;

  /** Try asset via the sandbox registry (e.g. user shields). */
  function tryAsset(key) {
    if (!key) return null;
    try { return resolveAsset ? resolveAsset(key) : null; }
    catch (_) { return null; }
  }

  /** Solid-color full-bleed background. */
  function fullBg(slide, color) {
    slide.background = { color };
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 1) university_title — dark full-bleed + centered crest
  // Reference shapes:
  //   [00] dark rect 0,0 13.333×7.5 fill=202020
  //   [01] pic      4.244,1.135 4.847×5.161
  // ═══════════════════════════════════════════════════════════════════════════
  function university_title(slide, d) {
    fullBg(slide, UNIV.DARK);

    const crestBox = {
      x: rx(4.244), y: ry(1.135),
      w: rx(4.847), h: ry(5.161),
    };
    const shield = tryAsset(d.shield_key || 'potomac_shield');
    if (shield && shield.dataUrl) {
      prim.image(slide, crestBox, { data: shield.dataUrl,
        aspect: shield.aspect || (4.847 / 5.161) });
    } else {
      // Fallback: render a circular icon + arc-style caps text above/below.
      const iconSide = Math.min(crestBox.w, crestBox.h) * 0.55;
      const iconBox = {
        x: crestBox.x + (crestBox.w - iconSide) / 2,
        y: crestBox.y + (crestBox.h - iconSide) / 2,
        w: iconSide, h: iconSide,
      };
      prim.placeLogo(slide, iconBox, 'icon_yellow');
      prim.text(slide, String(d.top_text || 'POTOMAC'),
        { x: crestBox.x, y: crestBox.y, w: crestBox.w, h: crestBox.h * 0.18 },
        { fontFace: FONTS.HEADLINE, color: UNIV.WHITE, bold: true,
          align: 'center', valign: 'middle', charSpacing: 8, maxPt: 22 });
      if (d.established) {
        prim.text(slide, 'EST.  ' + d.established,
          { x: crestBox.x, y: crestBox.y + crestBox.h * 0.45,
            w: crestBox.w, h: crestBox.h * 0.08 },
          { fontFace: FONTS.HEADLINE, color: UNIV.WHITE,
            align: 'center', valign: 'middle', maxPt: 12 });
      }
      prim.text(slide, String(d.bottom_text || 'UNIVERSITY'),
        { x: crestBox.x, y: crestBox.y + crestBox.h * 0.80,
          w: crestBox.w, h: crestBox.h * 0.18 },
        { fontFace: FONTS.HEADLINE, color: UNIV.WHITE, bold: true,
          align: 'center', valign: 'middle', charSpacing: 8, maxPt: 22 });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 2) university_yellow_cover — yellow bg, centered title + byline + rule + wordmark
  // Reference shapes (inferred):
  //   Title placeholder (centered ≈ y=2.5, w=full canvas)
  //   Byline placeholder (≈ y=3.9)
  //   Black rule at (4.198, 5.302) w=4.941 h=0
  //   Wordmark at (5.156, 6.271) w=3.021 h=0.615
  // ═══════════════════════════════════════════════════════════════════════════
  function university_yellow_cover(slide, d) {
    fullBg(slide, UNIV.YELLOW);

    // Title text (centered, ≈ y=2.2)
    prim.text(slide, String(d.title || 'Title'),
      { x: rx(1.0), y: ry(2.0), w: engine.W - rx(2.0), h: ry(1.7) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'center', valign: 'middle',
        maxPt: 88, minPt: 36 });

    // Byline (centered, ≈ y=4.1)
    if (d.byline) {
      prim.text(slide, d.byline,
        { x: rx(1.0), y: ry(4.1), w: engine.W - rx(2.0), h: ry(0.7) },
        { fontFace: FONTS.BODY, color: UNIV.BLACK,
          align: 'center', valign: 'middle',
          maxPt: 22, minPt: 12 });
    }

    // Black rule (4.198, 5.302) w=4.941
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: rx(4.198), y: ry(5.302), w: rx(4.941), h: ry(0.02) },
      { fill: { color: UNIV.BLACK }, line: { color: UNIV.BLACK, width: 0 } });

    // Wordmark (5.156, 6.271) w=3.021 h=0.615
    prim.placeLogo(slide,
      { x: rx(5.156), y: ry(6.271), w: rx(3.021), h: ry(0.615) },
      'full_black');
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 3) university_welcome_photo — dark bg + full-bleed photo + big white headline
  // Reference shapes:
  //   [00] dark 13.333×7.5
  //   [01] white-text box at (1.375, 2.613) w=10.594 h=2.201 @ 65pt
  //   [02] full-bleed photo (0.002, 0.000) 13.332×7.5
  // ═══════════════════════════════════════════════════════════════════════════
  function university_welcome_photo(slide, d) {
    fullBg(slide, UNIV.DARK);

    const photo = d.image_data
      ? { dataUrl: 'data:image/' + (d.image_format || 'jpeg') + ';base64,' + d.image_data,
          aspect: d.image_aspect }
      : tryAsset(d.image_key);
    if (photo && photo.dataUrl) {
      // Full-bleed
      slide.addImage({
        data: photo.dataUrl,
        x: 0, y: 0, w: engine.W, h: engine.H,
        sizing: { type: 'cover', w: engine.W, h: engine.H },
      });
    }

    // White text block at reference (1.375, 2.613) w=10.594 h=2.201
    const box = {
      x: rx(1.375), y: ry(2.613),
      w: rx(10.594), h: ry(2.201),
    };
    prim.text(slide, String(d.title || 'WELCOME TO\nPOTOMAC UNIVERSITY').toUpperCase(),
      box,
      { fontFace: FONTS.BODY, bold: true, color: UNIV.WHITE,
        align: 'center', valign: 'middle',
        maxPt: 65, minPt: 24 });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 4) university_trend_chart
  // Reference:
  //   Title placeholder (centered top "TREND DIRECTION" at ≈ y=0.55 w=center)
  //   HISTORY (0.557, 0.557) w=1.140 h=0.328 @ 18pt
  //   Caption (5.826, 7.073) w=1.685 h=0.191 @ 9.5pt
  //   Icon (12.094, 0.490) w=0.646 h=0.646
  //   Chart image (1.741, 1.291) w=9.858 h=5.559
  // ═══════════════════════════════════════════════════════════════════════════
  function university_trend_chart(slide, d) {
    fullBg(slide, UNIV.WHITE);

    // HISTORY eyebrow (top-left)
    prim.text(slide, String(d.eyebrow || 'HISTORY').toUpperCase(),
      { x: rx(0.557), y: ry(0.557), w: rx(1.140), h: ry(0.328) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'left', valign: 'middle', charSpacing: 4, maxPt: 18 });

    // Centered title
    prim.text(slide, String(d.title || '').toUpperCase(),
      { x: rx(1.8), y: ry(0.55), w: engine.W - rx(3.6), h: ry(0.4) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'center', valign: 'middle', charSpacing: 6,
        maxPt: 28, minPt: 18 });

    // Top-right icon
    prim.placeLogo(slide,
      { x: rx(12.094), y: ry(0.490), w: rx(0.646), h: ry(0.646) },
      'icon_black');

    // Chart body area (1.741, 1.291) 9.858×5.559
    const chartArea = {
      x: rx(1.741), y: ry(1.291),
      w: rx(9.858), h: ry(5.559),
    };
    const img = d.image_data
      ? { dataUrl: 'data:image/' + (d.image_format || 'png') + ';base64,' + d.image_data,
          aspect: d.image_aspect }
      : tryAsset(d.image_key);
    if (img && img.dataUrl) {
      prim.image(slide, chartArea,
        { data: img.dataUrl, aspect: img.aspect, align: 'center' });
    } else if (d.series || d.categories) {
      const chartMap = {
        bar: pres.charts.BAR, line: pres.charts.LINE, pie: pres.charts.PIE,
        donut: pres.charts.DOUGHNUT, area: pres.charts.AREA,
      };
      const pptxType = chartMap[(d.chart_type || 'line').toLowerCase()] || pres.charts.LINE;
      const series = d.series || [{ name: 'Series', values: d.values || [] }];
      const data = series.map(s => ({
        name: s.name || '',
        labels: d.categories || d.labels || [],
        values: s.values || [],
      }));
      slide.addChart(pptxType, data, {
        ...chartArea,
        chartColors: [UNIV.BLACK, UNIV.YELLOW, UNIV.GRAY_60],
        showLegend: series.length > 1, legendPos: 'b',
      });
    }

    // Caption
    if (d.caption) {
      prim.text(slide, String(d.caption),
        { x: rx(5.826), y: ry(7.073), w: rx(1.685), h: ry(0.25) },
        { fontFace: FONTS.BODY, italic: true, color: UNIV.BLACK,
          align: 'center', valign: 'middle', maxPt: 10 });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 5) university_pennant
  // Reference:
  //   bg yellow
  //   title at (5.455, 2.551) w=6.348 h=3.287 @ 65pt
  //   pennant rect (1.125, 0.000) w=3.146 h=4.938 (white, starts at TOP of slide)
  //   shield image (1.250, 0.969) w=2.896 h=3.125
  // ═══════════════════════════════════════════════════════════════════════════
  function university_pennant(slide, d) {
    fullBg(slide, UNIV.YELLOW);

    // Pennant white body
    const pennX = rx(1.125), pennW = rx(3.146);
    const pennTotalH = ry(4.938);
    // Reference uses a plain white rect; the jpg renders a triangular notch
    // at the bottom.  We replicate that with a second DOWN triangle whose
    // tip reaches the bottom of the pennant.
    const rectH = pennTotalH * 0.82;
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: pennX, y: 0, w: pennW, h: rectH },
      { fill: { color: UNIV.WHITE }, line: { color: UNIV.WHITE, width: 0 } });
    // Swallow-tail notch using two right-triangles
    const tailH = pennTotalH - rectH;
    prim.shape(slide, pres.shapes.RIGHT_TRIANGLE,
      { x: pennX, y: rectH, w: pennW / 2, h: tailH },
      { fill: { color: UNIV.WHITE }, line: { color: UNIV.WHITE, width: 0 } });
    prim.shape(slide, pres.shapes.RIGHT_TRIANGLE,
      { x: pennX + pennW / 2, y: rectH, w: pennW / 2, h: tailH, flipH: true },
      { fill: { color: UNIV.WHITE }, line: { color: UNIV.WHITE, width: 0 } });

    // Shield image inside pennant (1.250, 0.969) w=2.896 h=3.125
    const shieldBox = {
      x: rx(1.250), y: ry(0.969),
      w: rx(2.896), h: ry(3.125),
    };
    const shield = tryAsset(d.shield_key || 'potomac_shield');
    if (shield && shield.dataUrl) {
      prim.image(slide, shieldBox,
        { data: shield.dataUrl, aspect: shield.aspect || (2.896 / 3.125) });
    } else {
      const iconSide = Math.min(shieldBox.w, shieldBox.h) * 0.65;
      prim.placeLogo(slide, {
        x: shieldBox.x + (shieldBox.w - iconSide) / 2,
        y: shieldBox.y + (shieldBox.h - iconSide) / 2,
        w: iconSide, h: iconSide,
      }, 'icon_yellow');
      prim.text(slide, 'POTOMAC',
        { x: shieldBox.x, y: shieldBox.y, w: shieldBox.w, h: shieldBox.h * 0.2 },
        { fontFace: FONTS.HEADLINE, bold: true, color: UNIV.BLACK,
          align: 'center', valign: 'middle', charSpacing: 4, maxPt: 14 });
      prim.text(slide, 'UNIVERSITY',
        { x: shieldBox.x, y: shieldBox.y + shieldBox.h * 0.8,
          w: shieldBox.w, h: shieldBox.h * 0.2 },
        { fontFace: FONTS.HEADLINE, bold: true, color: UNIV.BLACK,
          align: 'center', valign: 'middle', charSpacing: 4, maxPt: 14 });
    }

    // Headline (5.455, 2.551) w=6.348 h=3.287 @ 65pt
    prim.text(slide, String(d.title || '').toUpperCase(),
      { x: rx(5.455), y: ry(2.551), w: rx(6.348), h: ry(3.287) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'left', valign: 'middle', maxPt: 65, minPt: 24 });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 6) university_number_trio
  // Reference (three items, column centers at x≈2.68 / 6.67 / 10.66):
  //   Outer ring ≈ 2.90 × 2.88 starting x=1.224 / 5.224 / 9.214  y=2.55
  //   Inner dot   1.062 × 1.062 at    x=2.146 / 6.135 / 10.125  y=2.906
  //   Number text at ring center @30pt
  //   Label text at y≈3.17 @14pt-ish
  //   Hint italic at y≈4.55 @12.5pt
  //   HISTORY eyebrow (0.557, 0.557) 18pt
  //   Icon (12.094, 0.490)
  // ═══════════════════════════════════════════════════════════════════════════
  function university_number_trio(slide, d) {
    fullBg(slide, UNIV.WHITE);

    // Eyebrow + title + icon (same as trend_chart)
    prim.text(slide, String(d.eyebrow || 'HISTORY').toUpperCase(),
      { x: rx(0.557), y: ry(0.557), w: rx(1.140), h: ry(0.328) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'left', valign: 'middle', charSpacing: 4, maxPt: 18 });
    prim.text(slide, String(d.title || '').toUpperCase(),
      { x: rx(1.8), y: ry(0.55), w: engine.W - rx(3.6), h: ry(0.4) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'center', valign: 'middle', charSpacing: 6,
        maxPt: 28, minPt: 18 });
    prim.placeLogo(slide,
      { x: rx(12.094), y: ry(0.490), w: rx(0.646), h: ry(0.646) },
      'icon_black');

    // Default to 3 items if fewer provided
    const items = (d.items && d.items.length) ? d.items : [
      { n: 1, label: 'Label' }, { n: 2, label: 'Label' }, { n: 3, label: 'Label' },
    ];
    // Reference positions (for the first 3 items)
    const RING_X = [1.224, 5.224, 9.214];
    const RING_Y = 2.55;
    const RING_W = 2.9;
    const RING_H = 2.88;
    const DOT_X  = [2.146, 6.135, 10.125];
    const DOT_Y  = 2.906;
    const DOT_W  = 1.062;
    const DOT_H  = 1.062;

    items.forEach((it, i) => {
      const ringX = RING_X[i] !== undefined ? RING_X[i] : (1.224 + i * 4.0);
      const dotX  = DOT_X[i]  !== undefined ? DOT_X[i]  : (2.146 + i * 4.0);

      // Outer ring (yellow stroke, white fill, no fill if you prefer)
      prim.shape(slide, pres.shapes.OVAL,
        { x: rx(ringX), y: ry(RING_Y), w: rx(RING_W), h: ry(RING_H) },
        { fill: { color: UNIV.WHITE },
          line: { color: UNIV.YELLOW, width: 3 } });
      // Inner filled number dot
      prim.shape(slide, pres.shapes.OVAL,
        { x: rx(dotX), y: ry(DOT_Y), w: rx(DOT_W), h: ry(DOT_H) },
        { fill: { color: UNIV.YELLOW }, line: { color: UNIV.YELLOW, width: 0 } });
      // Number text centered in dot
      prim.text(slide, String(it.n || (i + 1)),
        { x: rx(dotX), y: ry(DOT_Y), w: rx(DOT_W), h: ry(DOT_H) },
        { fontFace: FONTS.HEADLINE, bold: true, color: UNIV.BLACK,
          align: 'center', valign: 'middle', maxPt: 30, minPt: 18 });
      // Label below dot (reference positions: x ≈ ringX + 0.82, y = 3.17, h = 1.17)
      prim.text(slide, String(it.label || ''),
        { x: rx(ringX), y: ry(3.35), w: rx(RING_W), h: ry(0.6) },
        { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
          align: 'center', valign: 'middle', maxPt: 14, minPt: 10 });
      // Hint (italic)
      if (it.hint) {
        prim.text(slide, String(it.hint),
          { x: rx(ringX), y: ry(4.25), w: rx(RING_W), h: ry(0.7) },
          { fontFace: FONTS.BODY, italic: true, color: UNIV.GRAY_60,
            align: 'center', valign: 'top', maxPt: 13, minPt: 9 });
      }
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 7) university_bullets_photo
  // Reference:
  //   Eyebrow + Title + top-right icon (same header pattern)
  //   5 square yellow dots at x=1.760, sizes 0.406×0.406,
  //     y=2.312, 3.052, 3.781, 4.510, 5.250
  //   Bullet text column starts at x=2.574, w=4.755, starts y=2.273, h≈3.362 @24pt
  //   Full-height photo at (9.771, 0) w=3.198 h=7.5
  // ═══════════════════════════════════════════════════════════════════════════
  function university_bullets_photo(slide, d) {
    fullBg(slide, UNIV.WHITE);

    // Photo column (full-height right side)
    const photoArea = {
      x: rx(9.771), y: 0,
      w: rx(3.198), h: engine.H,
    };
    const photo = d.image_data
      ? { dataUrl: 'data:image/' + (d.image_format || 'jpeg') + ';base64,' + d.image_data,
          aspect: d.image_aspect }
      : tryAsset(d.image_key);
    if (photo && photo.dataUrl) {
      slide.addImage({
        data: photo.dataUrl,
        ...photoArea,
        sizing: { type: 'cover', w: photoArea.w, h: photoArea.h },
      });
    } else {
      prim.shape(slide, pres.shapes.RECTANGLE, photoArea,
        { fill: { color: 'F0F0F0' }, line: { color: 'DDDDDD', width: 1 } });
      prim.text(slide, 'PHOTO', photoArea,
        { fontFace: FONTS.HEADLINE, color: UNIV.GRAY_60, charSpacing: 8,
          align: 'center', valign: 'middle', maxPt: 18 });
    }

    // Eyebrow
    prim.text(slide, String(d.eyebrow || 'HISTORY').toUpperCase(),
      { x: rx(0.557), y: ry(0.557), w: rx(1.140), h: ry(0.328) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'left', valign: 'middle', charSpacing: 4, maxPt: 18 });
    // Title centered over left two-thirds only (photo is on the right)
    prim.text(slide, String(d.title || '').toUpperCase(),
      { x: rx(1.8), y: ry(0.55), w: rx(6.5), h: ry(0.4) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'center', valign: 'middle', charSpacing: 6,
        maxPt: 28, minPt: 16 });

    // Bullets
    const items = d.items || d.bullets || [];
    const dotX = rx(1.760);
    const dotW = rx(0.406), dotH = ry(0.406);
    const textX = rx(2.574);
    const textW = rx(4.755);
    const firstY = 2.312;        // reference y of first dot
    const step   = 0.739;        // avg spacing between dots (2.312→3.052→3.781…)
    items.forEach((it, i) => {
      const text = typeof it === 'string' ? it : (it.text || it.label || '');
      const y = firstY + i * step;
      prim.shape(slide, pres.shapes.RECTANGLE,
        { x: dotX, y: ry(y), w: dotW, h: dotH },
        { fill: { color: UNIV.YELLOW }, line: { color: UNIV.YELLOW, width: 0 } });
      prim.text(slide, text,
        { x: textX, y: ry(y - 0.04), w: textW, h: dotH + ry(0.05) },
        { fontFace: FONTS.BODY, color: UNIV.BLACK,
          align: 'left', valign: 'middle', maxPt: 24, minPt: 14 });
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 8) university_thank_you — yellow bg + centered title + wordmark
  // Reference:
  //   yellow full-bleed
  //   title (3.755, 3.099) w=5.841 h=1.117 @ 65pt
  //   wordmark (5.156, 6.271) w=3.021 h=0.615
  // ═══════════════════════════════════════════════════════════════════════════
  function university_thank_you(slide, d) {
    fullBg(slide, UNIV.YELLOW);

    prim.text(slide, String(d.title || 'Thank You!'),
      { x: rx(3.755), y: ry(3.099), w: rx(5.841), h: ry(1.117) },
      { fontFace: FONTS.BODY, bold: true, color: UNIV.BLACK,
        align: 'center', valign: 'middle', maxPt: 65, minPt: 30 });

    prim.placeLogo(slide,
      { x: rx(5.156), y: ry(6.271), w: rx(3.021), h: ry(0.615) },
      'full_black');
    return slide;
  }

  // ── Registry ─────────────────────────────────────────────────────────────
  return {
    university_title,
    university_yellow_cover,
    university_welcome_photo,
    university_trend_chart,
    university_pennant,
    university_number_trio,
    university_bullets_photo,
    university_thank_you,
  };
}

module.exports = { buildUniversityTemplates };
