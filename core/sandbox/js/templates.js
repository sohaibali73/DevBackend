'use strict';
/**
 * Template Library
 * ================
 * Named slide templates that the agent can use as starting points.
 * Each template is a pure function: (slide, data, ctx) => slide.
 *
 * ctx = { pres, engine, prim, brand, logos, resolveAsset }
 *
 * Templates MUST NOT contain hardcoded inch/pt measurements.  They must
 * compose boxes via engine (grid/stack/row/tokens) and render them via
 * prim (primitives).
 *
 * The agent can:
 *   • call a template by name with `data`
 *   • override per-slide with `overrides` (e.g. accent_color, theme)
 *   • run extra "customize" JS after the template (hybrid mode)
 *   • skip templates entirely and use freestyle mode
 */

function buildTemplates(ctx) {
  const { pres, engine, prim, brand } = ctx;
  const { PALETTE, FONTS } = brand;
  const { tokens } = engine;

  // ── helpers ───────────────────────────────────────────────────────────────
  const themeFor = (d) => (d.theme === 'dark' || d.background === 'dark') ? 'dark' : 'light';
  const bgFor = (theme) => theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE;
  const bodyClr = (theme) => theme === 'dark' ? PALETTE.GRAY_40 : PALETTE.DARK_GRAY;
  const mutedClr = (theme) => theme === 'dark' ? PALETTE.GRAY_60 : PALETTE.GRAY_60;

  // ═══════════════════════════════════════════════════════════════════════════
  // TITLE SLIDE
  // ═══════════════════════════════════════════════════════════════════════════
  function title(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    prim.accentBar(slide);

    const c = engine.rects.content();
    // Centered logo up top
    const logoBoxH = engine.H * 0.2;
    const logoBoxW = engine.W * 0.2;
    const logoBox = { x: (engine.W - logoBoxW) / 2, y: c.y, w: logoBoxW, h: logoBoxH };
    prim.placeLogo(slide, logoBox, theme === 'dark' ? 'icon_yellow' : 'full');

    const stack = engine.stack({
      x: c.x, y: logoBox.y + logoBox.h + tokens.gutter(), w: c.w,
      gap: tokens.gutter(),
    });

    // Title
    const titleH = engine.H * 0.2;
    const titleBox = stack.place(titleH);
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle',
      maxPt: 48, minPt: 20,
    });

    // Subtitle
    if (d.subtitle) {
      const subBox = stack.place(engine.H * 0.12);
      prim.text(slide, d.subtitle, subBox, {
        fontFace: FONTS.BODY, italic: d.style === 'executive',
        color: d.style === 'executive' ? PALETTE.YELLOW : mutedClr(theme),
        align: 'center', valign: 'middle',
        maxPt: 22, minPt: 12,
      });
    }

    // Accent line
    const lineBox = stack.place(tokens.ulineH());
    prim.shape(slide, pres.shapes.RECTANGLE, lineBox,
      { fill: { color: PALETTE.YELLOW }, line: { color: PALETTE.YELLOW, width: 0 } });

    // Tagline
    const tagline = d.tagline || (d.style === 'executive' ? 'Built to Conquer Risk' : null);
    if (tagline) {
      const tagBox = stack.place(engine.H * 0.06);
      prim.text(slide, tagline, tagBox, {
        fontFace: FONTS.BODY, italic: true, color: PALETTE.YELLOW,
        align: 'center', valign: 'middle',
        maxPt: 16, minPt: 10,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TITLE CARD (like the "Investment Strategies and Solutions" screenshot)
  // Inset dark card centered on slide.
  // ═══════════════════════════════════════════════════════════════════════════
  function title_card(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.GRAY_05 };

    const cardW = engine.W * 0.5;
    const cardH = engine.H * 0.75;
    const cardX = engine.W * 0.06;
    const cardY = (engine.H - cardH) / 2;
    const cardBox = { x: cardX, y: cardY, w: cardW, h: cardH };

    // Card fill (dark)
    prim.rect(slide, cardBox, { fill: PALETTE.DARK_GRAY });
    // Yellow bar on left of card
    const barBox = { x: cardX, y: cardY, w: engine.W * 0.011, h: cardH };
    prim.rect(slide, barBox, { fill: PALETTE.YELLOW });

    // Inner padding
    const pad = cardW * 0.06;
    const inner = {
      x: cardX + pad, y: cardY + pad,
      w: cardW - pad * 2, h: cardH - pad * 2,
    };

    const s = engine.stack({ x: inner.x, y: inner.y, w: inner.w, gap: engine.H * 0.012 });

    // Small logo at the top
    const logoH = engine.H * 0.07;
    const logoW = engine.W * 0.06;
    const logoBox = s.place(logoH);
    prim.placeLogo(slide, { x: inner.x, y: logoBox.y, w: logoW, h: logoH }, 'icon_yellow');

    // Top divider line under logo
    const divH = engine.H * 0.003;
    const divBox = s.place(divH);
    prim.rect(slide, divBox, { fill: PALETTE.YELLOW });

    // Title main line (white)
    const mainLine = String(d.title || '').toUpperCase();
    const titleH = engine.H * 0.11;
    const titleBox = s.place(titleH);
    prim.text(slide, mainLine, titleBox, {
      fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.WHITE,
      align: 'left', valign: 'top', maxPt: 36, minPt: 18,
    });

    // Title second line (yellow) — optional
    if (d.title_accent) {
      const accBox = s.place(titleH);
      prim.text(slide, String(d.title_accent).toUpperCase(), accBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'left', valign: 'top', maxPt: 36, minPt: 18,
      });
    }

    // Sub-title (small caps, white)
    if (d.subtitle) {
      const subH = engine.H * 0.055;
      const subBox = s.place(subH);
      prim.text(slide, String(d.subtitle).toUpperCase(), subBox, {
        fontFace: FONTS.HEADLINE, color: PALETTE.WHITE,
        align: 'left', valign: 'middle', maxPt: 18, minPt: 10,
      });
    }

    // Divider line
    s.place(engine.H * 0.003);
    prim.rect(slide, {
      x: inner.x, y: s.cursor() - engine.H * 0.003, w: inner.w, h: engine.H * 0.003,
    }, { fill: PALETTE.GRAY_60 });

    // Tagline (yellow)
    if (d.tagline) {
      const tagH = engine.H * 0.05;
      const tagBox = s.place(tagH);
      prim.text(slide, String(d.tagline).toUpperCase(), tagBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'left', valign: 'middle', maxPt: 16, minPt: 10,
      });
    }

    // Kicker body text
    if (d.body) {
      const bodyH = engine.H * 0.08;
      const bodyBox = s.place(bodyH);
      prim.text(slide, d.body, bodyBox, {
        fontFace: FONTS.BODY, color: PALETTE.WHITE,
        align: 'left', valign: 'top', maxPt: 13, minPt: 9,
      });
    }

    // Footer line (tiny caps)
    if (d.footer) {
      const footH = engine.H * 0.04;
      const footBox = { x: inner.x, y: cardY + cardH - pad - footH, w: inner.w, h: footH };
      prim.text(slide, String(d.footer).toUpperCase(), footBox, {
        fontFace: FONTS.HEADLINE, color: PALETTE.GRAY_60,
        align: 'left', valign: 'bottom', maxPt: 10, minPt: 8,
      });
    }

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONTENT SLIDE (bullets or text body)
  // ═══════════════════════════════════════════════════════════════════════════
  function content(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, subtitle: d.subtitle, theme });

    const bullets = d.bullets || (Array.isArray(d.content) ? d.content : null);
    const textBody = d.text || (!Array.isArray(d.content) ? d.content : null);

    if (bullets && bullets.length > 0) {
      const items = bullets.map(b => ({
        text: String(b),
        options: { bullet: { type: 'bullet' }, paraSpaceBef: 6, paraSpaceAft: 6 },
      }));
      prim.text(slide, items, body, {
        fontFace: FONTS.BODY, color: bodyClr(theme), valign: 'top',
        maxPt: 20, minPt: 11,
      });
    } else if (textBody) {
      prim.text(slide, String(textBody), body, {
        fontFace: FONTS.BODY, color: bodyClr(theme), valign: 'top',
        maxPt: 18, minPt: 11,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TWO COLUMN
  // ═══════════════════════════════════════════════════════════════════════════
  function two_column(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });
    const g = engine.grid(2, 1, body);

    [{ k: 0, hdr: d.left_header,  cnt: d.left_content  || (d.columns && d.columns[0]) },
     { k: 1, hdr: d.right_header, cnt: d.right_content || (d.columns && d.columns[1]) }]
      .forEach(({ k, hdr, cnt }) => {
        const col = g.cell(k, 0);
        const s = engine.stack({ x: col.x, y: col.y, w: col.w, gap: engine.H * 0.02 });
        if (hdr) {
          const hBox = s.place(engine.H * 0.06);
          prim.text(slide, String(hdr).toUpperCase(), hBox, {
            fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
            valign: 'middle', maxPt: 16, minPt: 10,
          });
        }
        const rem = s.remaining(col.y + col.h);
        const cBox = s.place(rem);
        prim.text(slide, String(cnt || ''), cBox, {
          fontFace: FONTS.BODY, color: bodyClr(theme), valign: 'top',
          maxPt: 16, minPt: 10,
        });
      });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // METRICS (KPI grid)
  // ═══════════════════════════════════════════════════════════════════════════
  function metrics(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });
    const metrics = d.metrics || [];
    if (!metrics.length) return slide;

    const perRow = Math.min(Math.max(1, d.columns || 3), metrics.length);
    const numRows = Math.ceil(metrics.length / perRow);
    const ctxBar = d.context ? body.h * 0.12 : 0;
    const gridArea = { x: body.x, y: body.y, w: body.w, h: body.h - ctxBar };
    const g = engine.grid(perRow, numRows, gridArea);

    metrics.forEach((m, i) => {
      const r = Math.floor(i / perRow);
      const c = i % perRow;
      const cell = g.cell(c, r);
      // Slightly inset each KPI cell so adjacent values never collide
      const pad = Math.min(cell.w, cell.h) * 0.08;
      const inner = {
        x: cell.x + pad, y: cell.y + pad,
        w: cell.w - pad * 2, h: cell.h - pad * 2,
      };
      // Use 55% for value, 35% for label, 10% gap — but cap the value pt
      // size by BOTH height AND width so long strings don't overflow and
      // wrap character-by-character (the previous "24%" → "24" "%" bug).
      const valH = inner.h * 0.55;
      const gap  = inner.h * 0.05;
      const lblH = inner.h * 0.4;
      const valBox = { x: inner.x, y: inner.y, w: inner.w, h: valH };
      const lblBox = { x: inner.x, y: inner.y + valH + gap, w: inner.w, h: lblH };

      const valText = String(m.value || '');
      // width-limited max pt: each glyph is ~0.48 em wide in Rajdhani, so
      // valText.length * 0.48 * em = inner.w  →  em = inner.w/(len*0.48)
      // em in inches → pt via *72; take 85% for safety.
      const widthCapPt = valText.length > 0
        ? Math.floor((inner.w / (valText.length * 0.52)) * 72 * 0.9)
        : 200;
      const heightCapPt = Math.floor(valH * 72 * 0.75);

      prim.text(slide, valText, valBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'center', valign: 'middle',
        maxPt: Math.max(18, Math.min(widthCapPt, heightCapPt)),
        minPt: 14,
      });
      prim.text(slide, String(m.label || ''), lblBox, {
        fontFace: FONTS.BODY, color: mutedClr(theme),
        align: 'center', valign: 'top',
        maxPt: Math.floor(lblH * 72 * 0.45),
        minPt: 9,
      });
    });

    if (d.context) {
      const ctxBox = { x: body.x, y: body.y + body.h - ctxBar, w: body.w, h: ctxBar };
      prim.text(slide, String(d.context), ctxBox, {
        fontFace: FONTS.BODY, italic: true, color: mutedClr(theme),
        align: 'center', valign: 'middle',
        maxPt: 14, minPt: 9,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STAT CARDS (like the "Who We Are" screenshot's 3 dark cards)
  // ═══════════════════════════════════════════════════════════════════════════
  function stat_cards(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });

    // Intro text (optional)
    const s = engine.stack({ x: body.x, y: body.y, w: body.w, gap: tokens.gutter() });
    if (d.intro) {
      const introH = body.h * 0.18;
      const introBox = s.place(introH);
      prim.text(slide, String(d.intro), introBox, {
        fontFace: FONTS.BODY, color: bodyClr(theme),
        align: 'left', valign: 'top', maxPt: 16, minPt: 10,
      });
    }

    const cards = d.cards || [];
    if (!cards.length) return slide;

    const cardsArea = {
      x: body.x, y: s.cursor(), w: body.w,
      h: body.h - (s.cursor() - body.y),
    };
    const g = engine.grid(cards.length, 1, cardsArea);
    cards.forEach((card, i) => {
      const cell = g.cell(i, 0);
      // Dark card fill
      const cardColor = card.color ? prim.hex(card.color) : PALETTE.DARK_GRAY;
      prim.rect(slide, cell, { fill: cardColor });

      // Header bar (yellow)
      const headerH = cell.h * 0.07;
      const headerBox = { x: cell.x, y: cell.y, w: cell.w, h: headerH };
      // (Actually screenshot shows label in yellow inside card; skip bar.)
      const inner = engine.stack({
        x: cell.x + cell.w * 0.08, y: cell.y + cell.h * 0.08,
        w: cell.w * 0.84, gap: cell.h * 0.03,
      });

      // Eyebrow label (yellow caps)
      if (card.label) {
        const labH = cell.h * 0.11;
        prim.text(slide, String(card.label).toUpperCase(), inner.place(labH), {
          fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
          align: 'center', valign: 'middle',
          maxPt: 16, minPt: 9,
        });
      }

      // Big value
      const valH = cell.h * 0.3;
      prim.text(slide, String(card.value || card.title || ''), inner.place(valH), {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.WHITE,
        align: 'center', valign: 'middle',
        maxPt: Math.floor(valH * 72 * 0.7), minPt: 20,
      });

      // Description
      if (card.description) {
        const remaining = inner.remaining(cell.y + cell.h - cell.h * 0.1);
        prim.text(slide, String(card.description), inner.place(Math.max(cell.h * 0.2, remaining)), {
          fontFace: FONTS.BODY, color: PALETTE.GRAY_40,
          align: 'center', valign: 'top',
          maxPt: 13, minPt: 9,
        });
      }
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HEX ROW (matches "Our Strategies Are Tactical..." screenshot)
  // ═══════════════════════════════════════════════════════════════════════════
  function hex_row(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, subtitle: d.subtitle, theme });

    const tiles = d.tiles || d.items || [];
    if (!tiles.length) return slide;

    // Allocate vertical space: 70% for hex tiles, rest = breathing room
    const rowArea = { x: body.x, y: body.y, w: body.w, h: body.h };
    const g = engine.grid(tiles.length, 1, rowArea);

    tiles.forEach((tile, i) => {
      const cell = g.cell(i, 0);
      prim.hexTile(slide, cell, {
        fill: PALETTE.YELLOW,
        iconKey: tile.icon_key,
        iconData: tile.icon_data ? { dataUrl: tile.icon_data, aspect: tile.icon_aspect || 1 } : null,
        label: tile.label,
        subline: tile.subline || tile.year,
        labelColor: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
        sublineColor: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      });
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TEAM TRIAD  (matches "Bringing the Team Together" screenshot)
  // Three rounded cards with pill headers and +/= glyphs between.
  // ═══════════════════════════════════════════════════════════════════════════
  function team_triad(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };

    // Title (left-aligned big)
    const c = engine.rects.content();
    const titleH = engine.H * 0.12;
    const titleBox = { x: c.x, y: c.y, w: c.w, h: titleH };
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'left', valign: 'middle',
      maxPt: 44, minPt: 18,
    });

    // Area for the three boxes + two glyphs
    const cards = d.cards || [];
    const n = cards.length;
    if (!n) return slide;

    const bodyArea = {
      x: c.x, y: titleBox.y + titleBox.h + engine.H * 0.04,
      w: c.w, h: c.h - titleBox.h - engine.H * 0.05,
    };

    // With n cards we need n cards + (n-1) glyphs
    const glyphW = bodyArea.w * 0.04;
    const gap = bodyArea.w * 0.015;
    const cardTotalW = bodyArea.w - glyphW * (n - 1) - gap * (n - 1) * 2;
    const cardW = cardTotalW / n;

    const pillH = engine.H * 0.08;
    const cardH = bodyArea.h * 0.7;
    const pillOverlap = pillH * 0.3;

    let cursorX = bodyArea.x;
    const defaultGlyphs = d.glyphs || ['+', '='];

    for (let i = 0; i < n; i++) {
      const card = cards[i];
      const cardY = bodyArea.y + pillH;
      const cardBox = { x: cursorX, y: cardY, w: cardW, h: cardH };

      // Rounded card (outline only if light, filled if dark)
      prim.roundRect(slide, cardBox, {
        stroke: PALETTE.YELLOW, strokeW: 2,
        fill: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE,
        radiusFrac: 0.08,
      });

      // Yellow pill header overlapping the top of the card
      const pillW = cardW * 0.7;
      const pillBox = {
        x: cursorX + (cardW - pillW) / 2,
        y: bodyArea.y + pillH / 2 - pillOverlap / 2,
        w: pillW,
        h: pillH,
      };
      prim.pill(slide, pillBox, {
        fill: PALETTE.YELLOW,
        label: card.pill || card.header || card.label || '',
        labelOpts: {
          fontFace: FONTS.BODY, bold: true, color: PALETTE.DARK_GRAY,
          maxPt: 20, minPt: 11,
        },
      });

      // Body text inside the card, below the pill overlap
      const bodyBoxY = pillBox.y + pillH + engine.H * 0.02;
      const bodyBoxH = cardBox.y + cardBox.h - bodyBoxY - engine.H * 0.02;
      const cardBody = {
        x: cardBox.x + cardW * 0.08, y: bodyBoxY,
        w: cardW * 0.84, h: bodyBoxH,
      };
      prim.text(slide, String(card.body || card.text || ''), cardBody, {
        fontFace: FONTS.BODY, color: bodyClr(theme),
        align: 'center', valign: 'middle',
        maxPt: 18, minPt: 10, lineHeight: 1.3,
      });

      cursorX += cardW;
      if (i < n - 1) {
        const gBox = {
          x: cursorX + gap, y: bodyArea.y + pillH + cardH / 2 - glyphW / 2,
          w: glyphW, h: glyphW,
        };
        prim.glyph(slide, gBox, defaultGlyphs[i] || '+', { color: PALETTE.YELLOW });
        cursorX += glyphW + gap * 2;
      }
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CTA FRAMED  (matches "Built to Conquer Risk" screenshot)
  // ═══════════════════════════════════════════════════════════════════════════
  function cta_framed(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE };

    // Full-bleed yellow frame
    const frame = prim.framedSlide(slide, { insetFrac: 0.04, strokeW: 3 });
    const pad = Math.min(frame.w, frame.h) * 0.05;
    const inner = {
      x: frame.x + pad, y: frame.y + pad,
      w: frame.w - pad * 2, h: frame.h - pad * 2,
    };

    const s = engine.stack({ x: inner.x, y: inner.y, w: inner.w, gap: inner.h * 0.02 });

    // Logo icon
    const logoH = inner.h * 0.12;
    const logoW = logoH * 1.0;
    const logoBox = { x: inner.x, y: inner.y, w: logoW, h: logoH };
    prim.placeLogo(slide, logoBox, theme === 'dark' ? 'icon_yellow' : 'icon_black');
    s.skip(logoH + inner.h * 0.03);

    // Title line 1 (white/dark)
    const title1H = inner.h * 0.15;
    const title1Box = s.place(title1H);
    prim.text(slide, String(d.title_top || 'BUILT TO').toUpperCase(), title1Box, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle', maxPt: 60, minPt: 24,
    });

    // Title line 2 (yellow emphasis)
    const title2H = inner.h * 0.2;
    const title2Box = s.place(title2H);
    prim.text(slide, String(d.title_bottom || 'CONQUER RISK').toUpperCase(), title2Box, {
      fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
      align: 'center', valign: 'middle', maxPt: 72, minPt: 30,
    });

    // Yellow divider
    const divH = inner.h * 0.01;
    const divBox = s.place(divH);
    prim.rect(slide, {
      x: divBox.x + divBox.w * 0.1, y: divBox.y,
      w: divBox.w * 0.8, h: divH,
    }, { fill: PALETTE.YELLOW });

    // "NEXT STEPS" caps
    const nsH = inner.h * 0.05;
    const nsBox = s.place(nsH);
    prim.text(slide, String(d.cta_label || 'NEXT STEPS').toUpperCase(), nsBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle', maxPt: 20, minPt: 10,
    });

    // Bulleted steps
    const steps = d.steps || [];
    if (steps.length) {
      const stepsH = inner.h * 0.22;
      const stepsBox = s.place(stepsH);
      const items = steps.map(st => ({
        text: String(st),
        options: { bullet: { type: 'bullet' }, paraSpaceBef: 4, paraSpaceAft: 4 },
      }));
      prim.text(slide, items, stepsBox, {
        fontFace: FONTS.BODY,
        color: theme === 'dark' ? PALETTE.GRAY_40 : PALETTE.DARK_GRAY,
        valign: 'middle', maxPt: 16, minPt: 10,
      });
    }

    // URL
    if (d.url) {
      const urlH = inner.h * 0.08;
      const urlBox = s.place(urlH);
      prim.text(slide, String(d.url), urlBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'center', valign: 'middle', maxPt: 22, minPt: 12,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TABLE
  // ═══════════════════════════════════════════════════════════════════════════
  function table(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });

    const headers = d.headers || [];
    const rows = d.rows || [];
    const tableRows = [];

    if (headers.length) {
      tableRows.push(headers.map(h => ({
        text: String(h).toUpperCase(),
        options: {
          bold: true, color: PALETTE.DARK_GRAY, fill: { color: PALETTE.YELLOW },
          align: 'center', valign: 'middle',
          fontSize: 11, fontFace: FONTS.HEADLINE,
          border: { type: 'solid', color: PALETTE.DARK_GRAY, pt: 0.5 },
        },
      })));
    }
    rows.forEach((r, ri) => {
      const bg = ri % 2 === 1 ? PALETTE.GRAY_10 : PALETTE.WHITE;
      tableRows.push((Array.isArray(r) ? r : [r]).map(cell => ({
        text: String(cell == null ? '' : cell),
        options: {
          color: bodyClr(theme), fill: { color: bg },
          fontSize: 11, fontFace: FONTS.BODY,
          border: { type: 'solid', color: PALETTE.GRAY_20, pt: 0.5 },
        },
      })));
    });

    if (!tableRows.length) return slide;
    const numCols = Math.max(...tableRows.map(r => r.length));
    const colW = body.w / Math.max(numCols, 1);

    slide.addTable(tableRows, {
      x: body.x, y: body.y, w: body.w,
      colW: Array(numCols).fill(colW),
      rowH: Math.min(body.h / tableRows.length, engine.H * 0.07),
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CHART  (bar / line / pie / donut)
  // ═══════════════════════════════════════════════════════════════════════════
  function chart(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });

    const chartType = (d.chart_type || 'bar').toLowerCase();
    const categories = d.categories || d.labels || [];
    const values = d.values || [];
    const series = d.series || [];

    const chartMap = {
      bar: pres.charts.BAR, line: pres.charts.LINE, pie: pres.charts.PIE,
      donut: pres.charts.DOUGHNUT, doughnut: pres.charts.DOUGHNUT,
      scatter: pres.charts.SCATTER, area: pres.charts.AREA,
    };
    const pptxType = chartMap[chartType] || pres.charts.BAR;

    const chartData = series.length
      ? series.map(s => ({ name: s.name || '', labels: categories, values: s.values || [] }))
      : [{ name: d.y_axis_label || 'Value', labels: categories, values }];

    slide.addChart(pptxType, chartData, {
      x: body.x, y: body.y, w: body.w, h: body.h,
      chartColors: [PALETTE.YELLOW, PALETTE.DARK_GRAY, PALETTE.GRAY_60, PALETTE.RED, PALETTE.GREEN],
      showLegend: series.length > 1, legendPos: 'b',
    });
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // QUOTE
  // ═══════════════════════════════════════════════════════════════════════════
  function quote(slide, d) {
    slide.background = { color: PALETTE.YELLOW_20 };
    prim.cornerLogo(slide, 'tr', 'full');
    const c = engine.rects.content();
    const s = engine.stack({ x: c.x, y: c.y + c.h * 0.2, w: c.w, gap: c.h * 0.03 });

    // Giant quote mark
    const qMarkH = c.h * 0.18;
    const qMarkBox = { x: c.x, y: c.y, w: c.w * 0.1, h: qMarkH };
    prim.text(slide, '"', qMarkBox, {
      fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
      align: 'center', valign: 'middle', maxPt: 120, minPt: 60,
    });

    const quoteBox = s.place(c.h * 0.35);
    prim.text(slide, String(d.quote || ''), quoteBox, {
      fontFace: FONTS.BODY, italic: true, color: PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle', maxPt: 28, minPt: 14,
    });

    if (d.attribution) {
      const attBox = s.place(c.h * 0.08);
      prim.text(slide, '— ' + String(d.attribution), attBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.GRAY_60,
        align: 'center', valign: 'middle', maxPt: 18, minPt: 10,
      });
    }
    if (d.context) {
      const ctxBox = s.place(c.h * 0.06);
      prim.text(slide, String(d.context), ctxBox, {
        fontFace: FONTS.BODY, italic: true, color: PALETTE.GRAY_60,
        align: 'center', valign: 'middle', maxPt: 14, minPt: 9,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION DIVIDER
  // ═══════════════════════════════════════════════════════════════════════════
  function section_divider(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    prim.accentBar(slide, { width: engine.W * 0.033 });
    prim.cornerLogo(slide, 'tr', theme === 'dark' ? 'icon_yellow' : 'full');

    const c = engine.rects.content();
    const barW = engine.W * 0.033 + engine.W * 0.034;
    const textX = barW;
    const textW = engine.W - textX - tokens.marginH();

    const s = engine.stack({ x: textX, y: c.y + c.h * 0.3, w: textW, gap: c.h * 0.03 });
    prim.text(slide, String(d.title || '').toUpperCase(), s.place(c.h * 0.22), {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      valign: 'middle', maxPt: 56, minPt: 24,
    });
    if (d.description) {
      prim.text(slide, String(d.description), s.place(c.h * 0.2), {
        fontFace: FONTS.BODY, color: mutedClr(theme),
        valign: 'middle', maxPt: 20, minPt: 11,
      });
    }
    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // IMAGE SLIDE
  // ═══════════════════════════════════════════════════════════════════════════
  function image(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = d.title
      ? prim.standardChrome(slide, { title: d.title, theme })
      : (() => { prim.cornerLogo(slide, 'tr', theme === 'dark' ? 'icon_yellow' : 'full'); return engine.rects.content(); })();

    if (!d.data) return slide;
    const dataUrl = 'data:image/' + (d.format || 'png') + ';base64,' + d.data;
    prim.image(slide, body, {
      data: dataUrl,
      aspect: d.aspect || null,
      align: d.align || 'center',
    });
    if (d.caption) {
      const capBox = {
        x: body.x, y: body.y + body.h - engine.H * 0.05,
        w: body.w, h: engine.H * 0.05,
      };
      prim.text(slide, String(d.caption), capBox, {
        fontFace: FONTS.BODY, italic: true, color: mutedClr(theme),
        align: d.align === 'center' ? 'center' : 'left',
        maxPt: 12, minPt: 9,
      });
    }
    return slide;
  }

  // ── Registry ──────────────────────────────────────────────────────────────
  const registry = {
    title, title_card, content, two_column, three_column: content,
    metrics, stat_cards, hex_row, team_triad, cta_framed,
    table, chart, quote, section_divider, image,

    // Aliases — map legacy type names to new templates.
    cta: cta_framed,
    executive_summary: title_card,
    icon_grid: hex_row,
    agenda: content,          // TODO: dedicated agenda template
    comparison: two_column,
    timeline: content,
    scorecard: table,
    matrix_2x2: content,
    image_content: image,
    card_grid: stat_cards,
    hub_spoke: content,
    process: content,
  };

  /**
   * Look up a template by name.  Returns the `content` fallback if name
   * is unknown.
   */
  function get(name) {
    return registry[name] || registry.content;
  }

  return { registry, get };
}

module.exports = { buildTemplates };
