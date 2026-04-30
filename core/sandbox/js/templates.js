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

  // ── Theme helpers ─────────────────────────────────────────────────────────

  const themeFor  = (d) => (d.theme === 'dark' || d.background === 'dark') ? 'dark' : 'light';
  const bgFor     = (theme) => theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE;
  const bodyClr   = (theme) => theme === 'dark' ? PALETTE.GRAY_40   : PALETTE.DARK_GRAY;

  // Previously always returned PALETTE.GRAY_60 for both branches — fixed.
  const mutedClr  = (theme) => theme === 'dark' ? PALETTE.GRAY_40   : PALETTE.GRAY_60;

  // ═══════════════════════════════════════════════════════════════════════════
  // TITLE SLIDE
  // ═══════════════════════════════════════════════════════════════════════════
  function title(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    prim.accentBar(slide);

    const c = engine.rects.content();

    // Centered logo at top
    const logoBoxH = engine.H * 0.20;
    const logoBoxW = engine.W * 0.20;
    const logoBox  = {
      x: (engine.W - logoBoxW) / 2,
      y: c.y,
      w: logoBoxW,
      h: logoBoxH,
    };
    prim.placeLogo(slide, logoBox, theme === 'dark' ? 'icon_yellow' : 'full');

    const s = engine.stack({
      x: c.x,
      y: logoBox.y + logoBox.h + tokens.gutter,
      w: c.w,
      gap: tokens.gutter,
    });

    // Title
    const titleBox = s.place(engine.H * 0.20);
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle',
      maxPt: 48, minPt: 20,
    });

    // Subtitle
    if (d.subtitle) {
      const subBox = s.place(engine.H * 0.12);
      prim.text(slide, d.subtitle, subBox, {
        fontFace: FONTS.BODY,
        italic: d.style === 'executive',
        color: d.style === 'executive' ? PALETTE.YELLOW : mutedClr(theme),
        align: 'center', valign: 'middle',
        maxPt: 22, minPt: 12,
      });
    }

    // Accent underline
    const lineBox = s.place(tokens.ulineH);
    prim.shape(slide, pres.shapes.RECTANGLE, lineBox, {
      fill: { color: PALETTE.YELLOW },
      line: { color: PALETTE.YELLOW, width: 0 },
    });

    // Tagline
    const tagline = d.tagline || null;
    if (tagline) {
      const tagBox = s.place(engine.H * 0.06);
      prim.text(slide, tagline, tagBox, {
        fontFace: FONTS.BODY, italic: true, color: PALETTE.YELLOW,
        align: 'center', valign: 'middle',
        maxPt: 16, minPt: 10,
      });
    }

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TITLE CARD  (inset dark card, centered on slide)
  // ═══════════════════════════════════════════════════════════════════════════
  function title_card(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.GRAY_05 };

    const cardW = engine.W * 0.50;
    const cardH = engine.H * 0.75;
    const cardX = engine.W * 0.06;
    const cardY = (engine.H - cardH) / 2;
    const cardBox = { x: cardX, y: cardY, w: cardW, h: cardH };

    prim.rect(slide, cardBox, { fill: PALETTE.DARK_GRAY });

    // Yellow left-edge bar
    prim.rect(slide,
      { x: cardX, y: cardY, w: tokens.accentBarW, h: cardH },
      { fill: PALETTE.YELLOW }
    );

    const pad   = cardW * 0.06;
    const inner = {
      x: cardX + pad, y: cardY + pad,
      w: cardW - pad * 2, h: cardH - pad * 2,
    };

    const s = engine.stack({ x: inner.x, y: inner.y, w: inner.w, gap: engine.H * 0.012 });

    // Small icon logo
    const logoBox = s.place(engine.H * 0.07);
    prim.placeLogo(slide,
      { x: inner.x, y: logoBox.y, w: engine.W * 0.06, h: logoBox.h },
      'icon_yellow'
    );

    // Divider under logo — capture the box directly instead of back-calculating
    // from s.cursor (the old code did s.place() then used s.cursor()-h, which
    // was fragile and broke if gap ever changed).
    const topDivBox = s.place(engine.H * 0.003);
    prim.rect(slide, topDivBox, { fill: PALETTE.YELLOW });

    // Title main line (white)
    const titleBox = s.place(engine.H * 0.11);
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.WHITE,
      align: 'left', valign: 'top', maxPt: 36, minPt: 18,
    });

    // Optional accent title line (yellow)
    if (d.title_accent) {
      const accBox = s.place(engine.H * 0.11);
      prim.text(slide, String(d.title_accent).toUpperCase(), accBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'left', valign: 'top', maxPt: 36, minPt: 18,
      });
    }

    // Subtitle (small caps, white)
    if (d.subtitle) {
      const subBox = s.place(engine.H * 0.055);
      prim.text(slide, String(d.subtitle).toUpperCase(), subBox, {
        fontFace: FONTS.HEADLINE, color: PALETTE.WHITE,
        align: 'left', valign: 'middle', maxPt: 18, minPt: 10,
      });
    }

    // Mid-card rule
    const midDivBox = s.place(engine.H * 0.003);
    prim.rect(slide, midDivBox, { fill: PALETTE.GRAY_60 });

    // Tagline (yellow)
    if (d.tagline) {
      const tagBox = s.place(engine.H * 0.05);
      prim.text(slide, String(d.tagline).toUpperCase(), tagBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'left', valign: 'middle', maxPt: 16, minPt: 10,
      });
    }

    // Kicker body text
    if (d.body) {
      const bodyBox = s.place(engine.H * 0.08);
      prim.text(slide, d.body, bodyBox, {
        fontFace: FONTS.BODY, color: PALETTE.WHITE,
        align: 'left', valign: 'top', maxPt: 13, minPt: 9,
      });
    }

    // Footer — anchored to the card bottom, not the stack cursor, so it never
    // collides with body text regardless of how many optional elements appear.
    if (d.footer) {
      const footH  = engine.H * 0.04;
      const footBox = {
        x: inner.x, y: cardY + cardH - pad - footH,
        w: inner.w, h: footH,
      };
      prim.text(slide, String(d.footer).toUpperCase(), footBox, {
        fontFace: FONTS.HEADLINE, color: PALETTE.GRAY_60,
        align: 'left', valign: 'bottom', maxPt: 10, minPt: 8,
      });
    }

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CONTENT  (bullets or free text)
  // ═══════════════════════════════════════════════════════════════════════════
  function content(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, subtitle: d.subtitle, theme });

    const bullets  = d.bullets || (Array.isArray(d.content) ? d.content : null);
    const textBody = d.text   || (!Array.isArray(d.content)  ? d.content : null);

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
    const g    = engine.grid(2, 1, body);

    [
      { k: 0, hdr: d.left_header,  cnt: d.left_content  ?? d.columns?.[0] },
      { k: 1, hdr: d.right_header, cnt: d.right_content ?? d.columns?.[1] },
    ].forEach(({ k, hdr, cnt }) => {
      const col = g.cell(k, 0);
      const s   = engine.stack({ x: col.x, y: col.y, w: col.w, gap: engine.H * 0.02 });

      if (hdr) {
        const hBox = s.place(engine.H * 0.06);
        prim.text(slide, String(hdr).toUpperCase(), hBox, {
          fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
          valign: 'middle', maxPt: 16, minPt: 10,
        });
      }

      const cBox = s.place(s.remaining(col.y + col.h));
      prim.text(slide, String(cnt ?? ''), cBox, {
        fontFace: FONTS.BODY, color: bodyClr(theme), valign: 'top',
        maxPt: 16, minPt: 10,
      });
    });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // THREE COLUMN
  // ═══════════════════════════════════════════════════════════════════════════
  function three_column(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });
    const g    = engine.grid(3, 1, body);

    const cols = d.columns || [];
    [0, 1, 2].forEach((k) => {
      const col  = g.cell(k, 0);
      const data = cols[k] || {};
      const hdr  = data.header ?? (k === 0 ? d.left_header : k === 2 ? d.right_header : d.center_header);
      const cnt  = data.content ?? data.text ?? '';
      const s    = engine.stack({ x: col.x, y: col.y, w: col.w, gap: engine.H * 0.02 });

      if (hdr) {
        const hBox = s.place(engine.H * 0.06);
        prim.text(slide, String(hdr).toUpperCase(), hBox, {
          fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
          valign: 'middle', maxPt: 16, minPt: 10,
        });
      }

      const cBox = s.place(s.remaining(col.y + col.h));
      prim.text(slide, String(cnt), cBox, {
        fontFace: FONTS.BODY, color: bodyClr(theme), valign: 'top',
        maxPt: 15, minPt: 10,
      });
    });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // METRICS  (KPI grid)
  // ═══════════════════════════════════════════════════════════════════════════
  function metrics(slide, d) {
    const theme      = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body       = prim.standardChrome(slide, { title: d.title, theme });

    // Renamed from `metrics` to `kpis` to avoid shadowing the function name.
    const kpis = d.metrics || [];
    if (!kpis.length) return slide;

    const perRow  = Math.min(Math.max(1, d.columns || 3), kpis.length);
    const numRows = Math.ceil(kpis.length / perRow);
    const ctxBar  = d.context ? body.h * 0.12 : 0;
    const gridArea = { x: body.x, y: body.y, w: body.w, h: body.h - ctxBar };
    const g = engine.grid(perRow, numRows, gridArea);

    kpis.forEach((m, i) => {
      const r    = Math.floor(i / perRow);
      const c    = i % perRow;
      const cell = g.cell(c, r);

      // Inset each KPI cell so adjacent values don't collide
      const pad   = Math.min(cell.w, cell.h) * 0.08;
      const inner = {
        x: cell.x + pad, y: cell.y + pad,
        w: cell.w - pad * 2, h: cell.h - pad * 2,
      };

      const valH   = inner.h * 0.55;
      const gap    = inner.h * 0.05;
      const lblH   = inner.h * 0.40;
      const valBox = { x: inner.x, y: inner.y,              w: inner.w, h: valH };
      const lblBox = { x: inner.x, y: inner.y + valH + gap, w: inner.w, h: lblH };

      const valText = String(m.value ?? '');

      // Cap pt size by BOTH height AND width so long strings (e.g. "24%")
      // never wrap character-by-character.
      const widthCapPt  = valText.length > 0
        ? Math.floor((inner.w / (valText.length * 0.52)) * 72 * 0.9)
        : 200;
      const heightCapPt = Math.floor(valH * 72 * 0.75);

      prim.text(slide, valText, valBox, {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
        align: 'center', valign: 'middle',
        maxPt: Math.max(18, Math.min(widthCapPt, heightCapPt)),
        minPt: 14,
      });
      prim.text(slide, String(m.label ?? ''), lblBox, {
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
  // STAT CARDS  (dark cards with big value + label)
  // ═══════════════════════════════════════════════════════════════════════════
  function stat_cards(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });

    const s = engine.stack({ x: body.x, y: body.y, w: body.w, gap: tokens.gutter });

    if (d.intro) {
      const introBox = s.place(body.h * 0.18);
      prim.text(slide, String(d.intro), introBox, {
        fontFace: FONTS.BODY, color: bodyClr(theme),
        align: 'left', valign: 'top', maxPt: 16, minPt: 10,
      });
    }

    const cards = d.cards || [];
    if (!cards.length) return slide;

    const cardsArea = {
      x: body.x, y: s.cursor, w: body.w,
      h: body.h - (s.cursor - body.y),
    };
    const g = engine.grid(cards.length, 1, cardsArea);

    cards.forEach((card, i) => {
      const cell      = g.cell(i, 0);
      const cardColor = card.color ? prim.hex(card.color) : PALETTE.DARK_GRAY;
      prim.rect(slide, cell, { fill: cardColor });

      // Dead headerBox + headerH variables removed — they were computed but
      // never consumed in the original.

      const inner = engine.stack({
        x: cell.x + cell.w * 0.08,
        y: cell.y + cell.h * 0.08,
        w: cell.w * 0.84,
        gap: cell.h * 0.03,
      });

      // Eyebrow label (yellow caps)
      if (card.label) {
        prim.text(slide, String(card.label).toUpperCase(), inner.place(cell.h * 0.11), {
          fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
          align: 'center', valign: 'middle',
          maxPt: 16, minPt: 9,
        });
      }

      // Big value
      const valH = cell.h * 0.30;
      prim.text(slide, String(card.value ?? card.title ?? ''), inner.place(valH), {
        fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.WHITE,
        align: 'center', valign: 'middle',
        maxPt: Math.floor(valH * 72 * 0.7), minPt: 20,
      });

      // Description
      if (card.description) {
        const bottomEdge = cell.y + cell.h - cell.h * 0.10;
        const rem        = inner.remaining(bottomEdge);
        prim.text(slide, String(card.description), inner.place(Math.max(cell.h * 0.20, rem)), {
          fontFace: FONTS.BODY, color: PALETTE.GRAY_40,
          align: 'center', valign: 'top',
          maxPt: 13, minPt: 9,
        });
      }
    });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HEX ROW  (icon tiles in a single horizontal row)
  // ═══════════════════════════════════════════════════════════════════════════
  function hex_row(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, subtitle: d.subtitle, theme });

    const tiles = d.tiles || d.items || [];
    if (!tiles.length) return slide;

    const g = engine.grid(tiles.length, 1, body);

    tiles.forEach((tile, i) => {
      prim.hexTile(slide, g.cell(i, 0), {
        fill:       PALETTE.YELLOW,
        iconKey:    tile.icon_key,
        iconData:   tile.icon_data
          ? { dataUrl: tile.icon_data, aspect: tile.icon_aspect ?? 1 }
          : null,
        label:       tile.label,
        subline:     tile.subline ?? tile.year,
        labelColor:  theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
        sublineColor: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      });
    });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TEAM TRIAD  (rounded cards with pill headers, connected by glyphs)
  // ═══════════════════════════════════════════════════════════════════════════
  function team_triad(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };

    const c       = engine.rects.content();
    const titleH  = engine.H * 0.12;
    const titleBox = { x: c.x, y: c.y, w: c.w, h: titleH };
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'left', valign: 'middle',
      maxPt: 44, minPt: 18,
    });

    const cards = d.cards || [];
    const n     = cards.length;
    if (!n) return slide;

    const bodyArea = {
      x: c.x,
      y: titleBox.y + titleBox.h + engine.H * 0.04,
      w: c.w,
      h: c.h - titleH - engine.H * 0.05,
    };

    // Replace the manual cursorX counter with engine.row() so card geometry
    // stays consistent with the rest of the layout system.
    const glyphW = bodyArea.w * 0.04;
    const gap    = bodyArea.w * 0.015;
    const cardTotalW = bodyArea.w - glyphW * (n - 1) - gap * (n - 1) * 2;
    const cardW  = cardTotalW / n;
    const pillH  = engine.H * 0.08;
    const cardH  = bodyArea.h * 0.70;
    const pillOverlap = pillH * 0.30;

    const rowCursor = engine.row({
      x: bodyArea.x,
      y: bodyArea.y,
      h: cardH,
      gap: 0,  // we manage gaps manually because glyphs sit in them
    });

    const defaultGlyphs = d.glyphs ?? ['+', '='];

    for (let i = 0; i < n; i++) {
      const card    = cards[i];
      const cardBox = rowCursor.place(cardW);
      const cardY   = bodyArea.y + pillH;

      prim.roundRect(slide, { ...cardBox, y: cardY }, {
        stroke: PALETTE.YELLOW, strokeW: 2,
        fill: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE,
        radiusFrac: 0.08,
      });

      // Yellow pill overlapping the top of the card
      const pillW   = cardW * 0.70;
      const pillBox = {
        x: cardBox.x + (cardW - pillW) / 2,
        y: bodyArea.y + pillH / 2 - pillOverlap / 2,
        w: pillW,
        h: pillH,
      };
      prim.pill(slide, pillBox, {
        fill:  PALETTE.YELLOW,
        label: card.pill ?? card.header ?? card.label ?? '',
        labelOpts: {
          fontFace: FONTS.BODY, bold: true, color: PALETTE.DARK_GRAY,
          maxPt: 20, minPt: 11,
        },
      });

      // Body text inside card, below the pill overlap zone
      const bodyBoxY = pillBox.y + pillH + engine.H * 0.02;
      const bodyBoxH = (cardY + cardH) - bodyBoxY - engine.H * 0.02;
      prim.text(slide, String(card.body ?? card.text ?? ''), {
        x: cardBox.x + cardW * 0.08, y: bodyBoxY,
        w: cardW * 0.84, h: bodyBoxH,
      }, {
        fontFace: FONTS.BODY, color: bodyClr(theme),
        align: 'center', valign: 'middle',
        maxPt: 18, minPt: 10, lineHeight: 1.3,
      });

      // Glyph between cards
      if (i < n - 1) {
        const glyphMidY = cardY + cardH / 2;
        const glyphBox  = {
          x: rowCursor.cursor + gap,
          y: glyphMidY - glyphW / 2,
          w: glyphW, h: glyphW,
        };
        prim.glyph(slide, glyphBox, defaultGlyphs[i] ?? '+', { color: PALETTE.YELLOW });
        rowCursor.skip(glyphW + gap * 2);
      }
    }

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CTA FRAMED  (full-bleed yellow border with headline + next steps)
  // ═══════════════════════════════════════════════════════════════════════════
  function cta_framed(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: theme === 'dark' ? PALETTE.DARK_GRAY : PALETTE.WHITE };

    const frame = prim.framedSlide(slide, { insetFrac: 0.04, strokeW: 3 });
    const pad   = Math.min(frame.w, frame.h) * 0.05;
    const inner = {
      x: frame.x + pad, y: frame.y + pad,
      w: frame.w - pad * 2, h: frame.h - pad * 2,
    };

    const s = engine.stack({ x: inner.x, y: inner.y, w: inner.w, gap: inner.h * 0.02 });

    // Logo icon (placed directly, not via stack — it anchors to inner.y
    // and we skip its height so the stack cursor starts below it)
    const logoH   = inner.h * 0.12;
    prim.placeLogo(slide,
      { x: inner.x, y: inner.y, w: logoH, h: logoH },
      theme === 'dark' ? 'icon_yellow' : 'icon_black'
    );
    s.skip(logoH + inner.h * 0.03);

    // Title line 1 (dark / white)
    const title1Box = s.place(inner.h * 0.15);
    prim.text(slide, String(d.title_top || 'READY TO').toUpperCase(), title1Box, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle', maxPt: 60, minPt: 24,
    });

    // Title line 2 (yellow)
    const title2Box = s.place(inner.h * 0.20);
    prim.text(slide, String(d.title_bottom || 'GET STARTED').toUpperCase(), title2Box, {
      fontFace: FONTS.HEADLINE, bold: true, color: PALETTE.YELLOW,
      align: 'center', valign: 'middle', maxPt: 72, minPt: 30,
    });

    // Yellow divider (inset 10% each side)
    const divBox = s.place(inner.h * 0.01);
    prim.rect(slide, {
      x: divBox.x + divBox.w * 0.10, y: divBox.y,
      w: divBox.w * 0.80, h: divBox.h,
    }, { fill: PALETTE.YELLOW });

    // CTA label
    const nsBox = s.place(inner.h * 0.05);
    prim.text(slide, String(d.cta_label || 'NEXT STEPS').toUpperCase(), nsBox, {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      align: 'center', valign: 'middle', maxPt: 20, minPt: 10,
    });

    // Bulleted steps
    const steps = d.steps || [];
    if (steps.length) {
      const stepsBox = s.place(inner.h * 0.22);
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
      const urlBox = s.place(inner.h * 0.08);
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

    const headers   = d.headers || [];
    const dataRows  = d.rows    || [];
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

    dataRows.forEach((r, ri) => {
      const bg = ri % 2 === 1 ? PALETTE.GRAY_10 : PALETTE.WHITE;
      tableRows.push((Array.isArray(r) ? r : [r]).map(cell => ({
        text: String(cell ?? ''),
        options: {
          color: bodyClr(theme), fill: { color: bg },
          fontSize: 11, fontFace: FONTS.BODY,
          border: { type: 'solid', color: PALETTE.GRAY_20, pt: 0.5 },
        },
      })));
    });

    if (!tableRows.length) return slide;

    const numCols = Math.max(...tableRows.map(r => r.length));
    const colW    = body.w / Math.max(numCols, 1);

    slide.addTable(tableRows, {
      x: body.x, y: body.y, w: body.w,
      colW: Array(numCols).fill(colW),
      rowH: Math.min(body.h / tableRows.length, engine.H * 0.07),
    });

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // CHART  (bar / line / pie / donut / scatter / area)
  // ═══════════════════════════════════════════════════════════════════════════
  function chart(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };
    const body = prim.standardChrome(slide, { title: d.title, theme });

    const chartType  = String(d.chart_type || 'bar').toLowerCase();
    const categories = d.categories || d.labels || [];
    const values     = d.values     || [];
    const series     = d.series     || [];

    const chartMap = {
      bar:      pres.charts.BAR,
      line:     pres.charts.LINE,
      pie:      pres.charts.PIE,
      donut:    pres.charts.DOUGHNUT,
      doughnut: pres.charts.DOUGHNUT,
      scatter:  pres.charts.SCATTER,
      area:     pres.charts.AREA,
    };
    const pptxType = chartMap[chartType] ?? pres.charts.BAR;

    const chartData = series.length
      ? series.map(s => ({ name: s.name ?? '', labels: categories, values: s.values ?? [] }))
      : [{ name: d.y_axis_label ?? 'Value', labels: categories, values }];

    slide.addChart(pptxType, chartData, {
      x: body.x, y: body.y, w: body.w, h: body.h,
      chartColors: [PALETTE.YELLOW, PALETTE.DARK_GRAY, PALETTE.GRAY_60, PALETTE.RED, PALETTE.GREEN],
      showLegend: series.length > 1,
      legendPos:  'b',
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
    const s = engine.stack({ x: c.x, y: c.y + c.h * 0.20, w: c.w, gap: c.h * 0.03 });

    // Oversized quote mark — positioned in the top-left of content,
    // independent of the stack so it doesn't push body text down.
    prim.text(slide, '\u201C', {
      x: c.x, y: c.y,
      w: c.w * 0.10, h: c.h * 0.18,
    }, {
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
      prim.text(slide, '\u2014 ' + String(d.attribution), attBox, {
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

    // Text starts after the wider accent bar; use tokens.marginH for the
    // right edge (was calling tokens.marginH() as a function in the original).
    const barW  = engine.W * 0.033 + engine.W * 0.034;
    const textX = barW;
    const textW = engine.W - textX - tokens.marginH;

    const s = engine.stack({ x: textX, y: c.y + c.h * 0.30, w: textW, gap: c.h * 0.03 });

    prim.text(slide, String(d.title || '').toUpperCase(), s.place(c.h * 0.22), {
      fontFace: FONTS.HEADLINE, bold: true,
      color: theme === 'dark' ? PALETTE.WHITE : PALETTE.DARK_GRAY,
      valign: 'middle', maxPt: 56, minPt: 24,
    });

    if (d.description) {
      prim.text(slide, String(d.description), s.place(c.h * 0.20), {
        fontFace: FONTS.BODY, color: mutedClr(theme),
        valign: 'middle', maxPt: 20, minPt: 11,
      });
    }

    return slide;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // IMAGE
  // ═══════════════════════════════════════════════════════════════════════════
  function image(slide, d) {
    const theme = themeFor(d);
    slide.background = { color: bgFor(theme) };

    const body = d.title
      ? prim.standardChrome(slide, { title: d.title, theme })
      : (() => {
          prim.cornerLogo(slide, 'tr', theme === 'dark' ? 'icon_yellow' : 'full');
          return engine.rects.content();
        })();

    if (!d.data) return slide;

    const dataUrl = `data:image/${d.format ?? 'png'};base64,${d.data}`;
    prim.image(slide, body, {
      data:   dataUrl,
      aspect: d.aspect ?? null,
      align:  d.align  ?? 'center',
    });

    if (d.caption) {
      const capH   = engine.H * 0.05;
      const capBox = { x: body.x, y: body.y + body.h - capH, w: body.w, h: capH };
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
    // Primary templates
    title,
    title_card,
    content,
    two_column,
    three_column,
    metrics,
    stat_cards,
    hex_row,
    team_triad,
    cta_framed,
    table,
    chart,
    quote,
    section_divider,
    image,

    // Aliases — map legacy / shorthand names to their canonical templates.
    // three_column previously aliased to `content` (plaintext fallback), which
    // silently produced a wrong layout; it now has its own implementation above.
    cta:               cta_framed,
    executive_summary: title_card,
    icon_grid:         hex_row,
    comparison:        two_column,
    scorecard:         table,
    image_content:     image,
    card_grid:         stat_cards,

    // The following alias to `content` as intentional text-body fallbacks.
    // Replace with dedicated templates as needed.
    agenda:      content,  // TODO: dedicated agenda template
    timeline:    content,  // TODO: dedicated timeline template
    matrix_2x2:  content,  // TODO: dedicated 2×2 matrix template
    hub_spoke:   content,  // TODO: dedicated hub-and-spoke template
    process:     content,  // TODO: dedicated process-flow template
  };

  /**
   * Look up a template by name.
   * Returns the `content` fallback for unrecognised names, and logs a warning
   * so stale or misspelled type strings don't produce silent wrong output.
   *
   * @param {string} name
   * @returns {Function}
   */
  function get(name) {
    if (registry[name]) return registry[name];
    console.warn(`[templates] Unknown template "${name}" — falling back to "content".`);
    return registry.content;
  }

  return { registry, get };
}

module.exports = { buildTemplates };