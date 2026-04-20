'use strict';
/**
 * Extra Template Library
 * ======================
 * Adds many ready-to-use slide layouts on top of the base templates.
 *
 * Every template receives `(slide, data, ctx)` and composes primitives.
 * `ctx = { pres, engine, prim, brand, themes: resolveTheme }`.
 *
 * Templates consume a unified `theme` field in `data` (string name, e.g.
 * 'light', 'dark', 'midnight').  They fall back to light when omitted.
 *
 * The returned object is merged into the main templates registry by
 * runtime.js at startup.
 */

function buildExtraTemplates(ctx) {
  const { pres, engine, prim, brand } = ctx;
  const { PALETTE, FONTS } = brand;
  const { tokens } = engine;
  const T = ctx.themes; // resolveTheme fn

  // ── Shared helpers ────────────────────────────────────────────────────
  const themeFor = (d) => T(d && d.theme);

  /** Apply slide background from a theme. */
  const setBg = (slide, th) => { slide.background = { color: th.bg }; };

  /** Standard top chrome (accent bar + logo + title + underline). */
  const chrome = (slide, d, th) => {
    prim.accentBar(slide, { color: th.accent });
    // title
    const m = tokens.marginH(), mv = tokens.marginV();
    const logoW = tokens.logoW();
    const titleBox = { x: m, y: mv, w: engine.W - m * 2 - logoW, h: tokens.titleH() };
    prim.text(slide, String(d.title || '').toUpperCase(), titleBox, {
      fontFace: FONTS.HEADLINE, bold: true, color: th.onBg,
      valign: 'middle', maxPt: 32, minPt: 14,
    });
    // underline
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: titleBox.x, y: titleBox.y + titleBox.h, w: titleBox.w * 0.2, h: tokens.ulineH() },
      { fill: { color: th.accent }, line: { color: th.accent, width: 0 } });
    // corner logo
    prim.cornerLogo(slide, 'tr', th.isDark ? 'icon_yellow' : 'full');
    // optional subtitle
    if (d.subtitle) {
      const subBox = { x: m,
        y: titleBox.y + titleBox.h + tokens.ulineH() + engine.H * 0.005,
        w: titleBox.w, h: engine.H * 0.04 };
      prim.text(slide, d.subtitle, subBox, {
        fontFace: FONTS.BODY, italic: true, color: th.muted,
        valign: 'middle', maxPt: 12, minPt: 9,
      });
    }
    // content area below chrome
    const chromeBottom = titleBox.y + titleBox.h + tokens.ulineH()
      + tokens.titleGap() + (d.subtitle ? engine.H * 0.045 : 0);
    return { x: m, y: chromeBottom, w: engine.W - m * 2, h: engine.H - chromeBottom - mv };
  };

  // ══════════════════════════════════════════════════════════════════════
  // TIMELINE (horizontal)
  // ══════════════════════════════════════════════════════════════════════
  function timeline(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const events = d.events || [];
    if (!events.length) return slide;

    // horizontal axis centered vertically
    const axisY = body.y + body.h * 0.5;
    const axisX1 = body.x, axisX2 = body.x + body.w;
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: axisX1, y: axisY - engine.H * 0.002, w: body.w, h: engine.H * 0.004 },
      { fill: { color: th.accent }, line: { color: th.accent, width: 0 } });

    events.forEach((ev, i) => {
      const t = events.length === 1 ? 0.5 : i / (events.length - 1);
      const x = axisX1 + t * body.w;
      const dir = i % 2 === 0 ? 'up' : 'down';
      prim.timelineDot(slide, { x, y: axisY },
        { label: ev.label || ev.title || '', subLabel: ev.date || ev.subline || '',
          color: th.accent, direction: dir });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // PROCESS (chevron steps)
  // ══════════════════════════════════════════════════════════════════════
  function process(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const steps = d.steps || [];
    if (!steps.length) return slide;

    const g = engine.grid(steps.length, 1, body, engine.W * 0.005);
    steps.forEach((s, i) => {
      const c = g.cell(i, 0);
      const fill = i % 2 === 0 ? th.accent : th.accentSoft;
      prim.chevron(slide, { x: c.x, y: c.y + c.h * 0.3, w: c.w, h: c.h * 0.4 },
        { color: fill, label: s.label || s.title || String(i + 1),
          labelOpts: { color: i % 2 === 0 ? PALETTE.DARK_GRAY : th.onBg,
                       maxPt: 16, minPt: 9 } });
      if (s.description) prim.text(slide, s.description,
        { x: c.x, y: c.y + c.h * 0.72, w: c.w, h: c.h * 0.25 },
        { align: 'center', color: th.muted, maxPt: 12, minPt: 9, valign: 'top' });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // SWOT 2×2
  // ══════════════════════════════════════════════════════════════════════
  function swot(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const g = engine.grid(2, 2, body);
    const quads = [
      { key: 'strengths',      label: 'STRENGTHS',      color: th.accent },
      { key: 'weaknesses',     label: 'WEAKNESSES',     color: PALETTE.RED },
      { key: 'opportunities',  label: 'OPPORTUNITIES',  color: PALETTE.GREEN },
      { key: 'threats',        label: 'THREATS',        color: PALETTE.GRAY_60 },
    ];
    quads.forEach((q, i) => {
      const cell = g.cell(i % 2, Math.floor(i / 2));
      prim.rect(slide, cell, { fill: th.surface, stroke: th.stroke, strokeW: 1 });
      // header band
      const headH = cell.h * 0.18;
      prim.rect(slide, { ...cell, h: headH }, {
        fill: q.color,
        label: q.label,
        labelOpts: { bold: true, color: PALETTE.DARK_GRAY, align: 'center',
                     valign: 'middle', fontFace: FONTS.HEADLINE, maxPt: 18 },
      });
      const items = (d[q.key] || []).map(x => ({ text: String(x),
        options: { bullet: { type: 'bullet' }, paraSpaceBef: 4, paraSpaceAft: 4 } }));
      prim.text(slide, items,
        { x: cell.x + cell.w * 0.06, y: cell.y + headH + cell.h * 0.05,
          w: cell.w * 0.88, h: cell.h - headH - cell.h * 0.1 },
        { color: th.onSurface, maxPt: 14, minPt: 10 });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // MATRIX 2×2 (priority / impact / effort / Eisenhower)
  // ══════════════════════════════════════════════════════════════════════
  function matrix_2x2(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const g = engine.grid(2, 2, body, engine.W * 0.01);
    const cells = d.quadrants || [
      { label: 'HIGH / LOW',  fill: th.accent, items: d.topLeft || [] },
      { label: 'HIGH / HIGH', fill: th.accentSoft, items: d.topRight || [] },
      { label: 'LOW / LOW',   fill: th.altSurface, items: d.bottomLeft || [] },
      { label: 'LOW / HIGH',  fill: th.stroke, items: d.bottomRight || [] },
    ];
    cells.forEach((c, i) => {
      const r = g.cell(i % 2, Math.floor(i / 2));
      prim.rect(slide, r, { fill: c.fill || th.surface, stroke: th.stroke, strokeW: 1 });
      prim.text(slide, c.label, { x: r.x, y: r.y, w: r.w, h: r.h * 0.2 },
        { bold: true, align: 'center', valign: 'middle',
          color: th.isDark ? PALETTE.DARK_GRAY : PALETTE.DARK_GRAY,
          fontFace: FONTS.HEADLINE, maxPt: 16 });
      const items = (c.items || []).map(x => ({ text: String(x),
        options: { bullet: { type: 'bullet' } } }));
      if (items.length) prim.text(slide, items,
        { x: r.x + r.w * 0.06, y: r.y + r.h * 0.25, w: r.w * 0.88, h: r.h * 0.7 },
        { color: th.onSurface, maxPt: 13, minPt: 9 });
    });
    // Axis labels
    if (d.xAxis) prim.text(slide, d.xAxis,
      { x: body.x, y: body.y + body.h + engine.H * 0.005, w: body.w, h: engine.H * 0.03 },
      { align: 'center', italic: true, color: th.muted, maxPt: 10 });
    if (d.yAxis) prim.text(slide, d.yAxis,
      { x: body.x - engine.W * 0.03, y: body.y, w: engine.W * 0.03, h: body.h },
      { align: 'center', valign: 'middle', rotate: -90,
        italic: true, color: th.muted, maxPt: 10 });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // FUNNEL (stacked trapezoids approximated via pentagons)
  // ══════════════════════════════════════════════════════════════════════
  function funnel(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const stages = d.stages || [];
    if (!stages.length) return slide;
    const gap = engine.H * 0.01;
    const bandH = (body.h - gap * (stages.length - 1)) / stages.length;
    stages.forEach((st, i) => {
      const shrink = i / (stages.length - 1 || 1);
      const w = body.w * (1 - shrink * 0.45);
      const x = body.x + (body.w - w) / 2;
      const y = body.y + i * (bandH + gap);
      const tone = i === 0 ? th.accent : i % 2 === 0 ? th.accentSoft : th.altSurface;
      prim.rect(slide, { x, y, w, h: bandH }, {
        fill: tone, stroke: th.stroke, strokeW: 1,
        label: `${st.label || st.title || ''}${st.value ? '  —  ' + st.value : ''}`,
        labelOpts: { bold: true, align: 'center', valign: 'middle',
          color: i === 0 ? PALETTE.DARK_GRAY : th.onBg,
          fontFace: FONTS.HEADLINE, maxPt: 18, minPt: 10 },
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // ROADMAP (horizontal tracks, each with milestones)
  // ══════════════════════════════════════════════════════════════════════
  function roadmap(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const tracks = d.tracks || [];
    const phases = d.phases || ['Q1', 'Q2', 'Q3', 'Q4'];
    if (!tracks.length) return slide;

    // header row (phases)
    const headH = body.h * 0.08;
    const labelW = body.w * 0.18;
    const phaseW = (body.w - labelW) / phases.length;
    phases.forEach((ph, i) => {
      prim.rect(slide,
        { x: body.x + labelW + i * phaseW, y: body.y, w: phaseW, h: headH },
        { fill: th.accentSoft, label: ph,
          labelOpts: { bold: true, align: 'center', valign: 'middle',
            color: th.onBg, fontFace: FONTS.HEADLINE, maxPt: 14 } });
    });
    const rowArea = { x: body.x, y: body.y + headH + engine.H * 0.01,
                      w: body.w, h: body.h - headH - engine.H * 0.01 };
    const rowH = rowArea.h / tracks.length;

    tracks.forEach((tr, i) => {
      const y = rowArea.y + i * rowH;
      // label column
      prim.rect(slide, { x: rowArea.x, y, w: labelW, h: rowH - engine.H * 0.006 },
        { fill: th.surface, stroke: th.stroke, strokeW: 1,
          label: (tr.name || '').toUpperCase(),
          labelOpts: { bold: true, align: 'left', valign: 'middle',
            color: th.onSurface, fontFace: FONTS.HEADLINE, maxPt: 13 } });
      // phase cells
      phases.forEach((_, pi) => {
        const x = rowArea.x + labelW + pi * phaseW;
        prim.rect(slide, { x, y, w: phaseW, h: rowH - engine.H * 0.006 },
          { fill: pi % 2 === 0 ? th.bg : th.altSurface, stroke: th.stroke, strokeW: 0.5 });
      });
      // milestones
      (tr.milestones || []).forEach(ms => {
        const pi = phases.indexOf(ms.phase);
        if (pi < 0) return;
        const mx = rowArea.x + labelW + pi * phaseW + phaseW * 0.05;
        const mw = phaseW * 0.9;
        const mh = rowH * 0.45;
        const my = y + (rowH - mh) / 2;
        prim.roundRect(slide, { x: mx, y: my, w: mw, h: mh }, {
          fill: ms.color || th.accent, stroke: ms.color || th.accent, strokeW: 0,
          radiusFrac: 0.3, label: ms.label || '',
          labelOpts: { bold: true, align: 'center', valign: 'middle',
            color: PALETTE.DARK_GRAY, maxPt: 12, minPt: 8 } });
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // KPI DASHBOARD (grid of kpiCards)
  // ══════════════════════════════════════════════════════════════════════
  function kpi_dashboard(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const cards = d.cards || d.kpis || [];
    if (!cards.length) return slide;
    const cols = Math.min(Math.max(2, d.columns || 4), cards.length);
    const rows = Math.ceil(cards.length / cols);
    const g = engine.grid(cols, rows, body);
    cards.forEach((c, i) => {
      const cell = g.cell(i % cols, Math.floor(i / cols));
      prim.kpiCard(slide, cell, {
        value: c.value, label: c.label, delta: c.delta, deltaSign: c.delta_sign,
        theme: { bg: th.surface, on: th.onSurface, accent: c.color || th.accent, stroke: th.stroke },
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // PRICING TIERS (3 stacked columns, headline + features + CTA)
  // ══════════════════════════════════════════════════════════════════════
  function pricing_tiers(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const tiers = d.tiers || [];
    if (!tiers.length) return slide;
    const g = engine.grid(tiers.length, 1, body);
    tiers.forEach((tier, i) => {
      const cell = g.cell(i, 0);
      const highlighted = !!tier.highlighted;
      prim.roundRect(slide, cell, {
        fill: highlighted ? th.accentSoft : th.surface,
        stroke: highlighted ? th.accent : th.stroke, strokeW: highlighted ? 2 : 1,
        radiusFrac: 0.04,
      });
      const s = engine.stack({ x: cell.x + cell.w * 0.08,
        y: cell.y + cell.h * 0.05, w: cell.w * 0.84, gap: cell.h * 0.02 });
      // tier name
      prim.text(slide, String(tier.name || '').toUpperCase(), s.place(cell.h * 0.08),
        { bold: true, align: 'center', fontFace: FONTS.HEADLINE,
          color: highlighted ? th.accent : th.onSurface, maxPt: 16 });
      // price
      prim.text(slide, tier.price || '—', s.place(cell.h * 0.18),
        { bold: true, align: 'center', fontFace: FONTS.HEADLINE,
          color: th.onSurface, maxPt: Math.floor(cell.h * 72 * 0.16) });
      // period
      if (tier.period) prim.text(slide, tier.period, s.place(cell.h * 0.05),
        { align: 'center', color: th.muted, maxPt: 11 });
      // features list
      const features = (tier.features || []).map(f => ({ text: String(f),
        options: { bullet: { type: 'bullet' }, paraSpaceBef: 3, paraSpaceAft: 3 } }));
      if (features.length) prim.text(slide, features, s.place(cell.h * 0.48),
        { color: th.onSurface, maxPt: 13, minPt: 9 });
      // CTA pill
      if (tier.cta) {
        const pH = cell.h * 0.1;
        const pBox = { x: cell.x + cell.w * 0.15, y: cell.y + cell.h - pH - cell.h * 0.06,
                       w: cell.w * 0.7, h: pH };
        prim.pill(slide, pBox, { fill: highlighted ? th.accent : th.onSurface, label: tier.cta,
          labelOpts: { color: highlighted ? PALETTE.DARK_GRAY : th.bg } });
      }
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // TESTIMONIAL (quote + avatar + author)
  // ══════════════════════════════════════════════════════════════════════
  function testimonial(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const s = engine.stack({ x: body.x, y: body.y + body.h * 0.1,
                             w: body.w, gap: body.h * 0.03 });
    prim.text(slide, '"', { x: body.x, y: body.y, w: body.w * 0.1, h: body.h * 0.2 },
      { fontFace: FONTS.HEADLINE, bold: true, color: th.accent,
        align: 'left', valign: 'middle', maxPt: Math.floor(body.h * 72 * 0.2) });
    prim.text(slide, d.quote || '', s.place(body.h * 0.4),
      { italic: true, color: th.onBg, align: 'center', valign: 'middle',
        maxPt: 28, minPt: 14 });
    // dotted underline
    const u = s.place(engine.H * 0.008);
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: body.x + body.w * 0.25, y: u.y, w: body.w * 0.5, h: engine.H * 0.004 },
      { fill: { color: th.accent }, line: { color: th.accent, width: 0 } });
    if (d.author) prim.text(slide, '— ' + d.author, s.place(body.h * 0.07),
      { bold: true, fontFace: FONTS.HEADLINE, align: 'center', color: th.onBg,
        maxPt: 18 });
    if (d.role) prim.text(slide, d.role, s.place(body.h * 0.05),
      { italic: true, align: 'center', color: th.muted, maxPt: 12 });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // TEAM GRID (name + title + rating cards)
  // ══════════════════════════════════════════════════════════════════════
  function team_grid(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const members = d.members || [];
    if (!members.length) return slide;
    const cols = Math.min(Math.max(2, d.columns || 4), members.length);
    const rows = Math.ceil(members.length / cols);
    const g = engine.grid(cols, rows, body);
    members.forEach((m, i) => {
      const cell = g.cell(i % cols, Math.floor(i / cols));
      prim.roundRect(slide, cell, { fill: th.surface, stroke: th.stroke, strokeW: 1,
        radiusFrac: 0.08 });
      // avatar circle
      const avR = Math.min(cell.w, cell.h) * 0.22;
      const avX = cell.x + cell.w / 2 - avR;
      const avY = cell.y + cell.h * 0.08;
      prim.ellipse(slide, { x: avX, y: avY, w: avR * 2, h: avR * 2 },
        { fill: m.color || th.accent, stroke: th.stroke, strokeW: 0,
          label: (m.initials || (m.name || '?').split(' ').map(w => w[0]).join('').toUpperCase()).slice(0, 2),
          labelOpts: { bold: true, align: 'center', valign: 'middle',
            color: PALETTE.DARK_GRAY, fontFace: FONTS.HEADLINE,
            maxPt: Math.floor(avR * 72 * 0.9) } });
      // name
      prim.text(slide, m.name || '',
        { x: cell.x, y: avY + avR * 2 + cell.h * 0.03, w: cell.w, h: cell.h * 0.1 },
        { bold: true, align: 'center', fontFace: FONTS.HEADLINE,
          color: th.onSurface, maxPt: 14 });
      // title
      prim.text(slide, m.title || '',
        { x: cell.x, y: avY + avR * 2 + cell.h * 0.13, w: cell.w, h: cell.h * 0.07 },
        { align: 'center', italic: true, color: th.muted, maxPt: 11 });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // AGENDA (numbered list)
  // ══════════════════════════════════════════════════════════════════════
  function agenda(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const items = d.items || [];
    if (!items.length) return slide;
    const rowH = body.h / Math.max(items.length, 1);
    items.forEach((it, i) => {
      const y = body.y + i * rowH;
      const badgeBox = { x: body.x, y: y + rowH * 0.1, w: rowH * 0.65, h: rowH * 0.65 };
      prim.numberCircle(slide, badgeBox, { n: i + 1, color: th.accent });
      const titleBox = { x: badgeBox.x + badgeBox.w + body.w * 0.02,
        y: y + rowH * 0.1, w: body.w - badgeBox.w - body.w * 0.08, h: rowH * 0.35 };
      prim.text(slide, String(it.title || it.label || it).toUpperCase(), titleBox,
        { bold: true, valign: 'middle', fontFace: FONTS.HEADLINE,
          color: th.onBg, maxPt: 18 });
      if (it.description) {
        prim.text(slide, it.description,
          { x: titleBox.x, y: titleBox.y + titleBox.h, w: titleBox.w, h: rowH * 0.35 },
          { color: th.muted, maxPt: 12, valign: 'top' });
      }
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // BIG NUMBER HERO (one giant stat + context)
  // ══════════════════════════════════════════════════════════════════════
  function big_number(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const c = engine.rects.content();
    const s = engine.stack({ x: c.x, y: c.y + c.h * 0.15, w: c.w, gap: c.h * 0.03 });
    prim.text(slide, String(d.eyebrow || '').toUpperCase(), s.place(c.h * 0.08),
      { fontFace: FONTS.HEADLINE, bold: true, color: th.accent,
        align: 'center', maxPt: 22 });
    prim.text(slide, d.value || '', s.place(c.h * 0.5),
      { fontFace: FONTS.HEADLINE, bold: true, color: th.onBg,
        align: 'center', valign: 'middle',
        maxPt: Math.floor(c.h * 72 * 0.55) });
    prim.text(slide, d.label || '', s.place(c.h * 0.08),
      { align: 'center', fontFace: FONTS.HEADLINE, color: th.onBg, maxPt: 22 });
    if (d.context) prim.text(slide, d.context, s.place(c.h * 0.08),
      { align: 'center', italic: true, color: th.muted, maxPt: 14 });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // IMAGE LEFT / RIGHT SPLIT
  // ══════════════════════════════════════════════════════════════════════
  function split(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const c = engine.rects.content();
    const left = { x: c.x, y: c.y, w: c.w * 0.48, h: c.h };
    const right = { x: c.x + c.w * 0.52, y: c.y, w: c.w * 0.48, h: c.h };
    const textArea = d.textSide === 'left' ? left : right;
    const imgArea  = d.textSide === 'left' ? right : left;

    // image panel (fallback to accent color if no image)
    if (d.image_data) prim.image(slide, imgArea, {
      data: 'data:image/' + (d.image_format || 'png') + ';base64,' + d.image_data,
      aspect: d.image_aspect, align: 'center',
    });
    else prim.rect(slide, imgArea, { fill: th.accentSoft });

    const s = engine.stack({ x: textArea.x, y: textArea.y + textArea.h * 0.08,
      w: textArea.w, gap: textArea.h * 0.02 });
    if (d.eyebrow) prim.text(slide, String(d.eyebrow).toUpperCase(),
      s.place(textArea.h * 0.07),
      { bold: true, fontFace: FONTS.HEADLINE, color: th.accent, maxPt: 18 });
    prim.text(slide, d.title || '', s.place(textArea.h * 0.25),
      { bold: true, fontFace: FONTS.HEADLINE, color: th.onBg,
        valign: 'top', maxPt: 40, minPt: 18 });
    prim.text(slide, d.body || '', s.place(textArea.h * 0.45),
      { color: th.onBg, valign: 'top', maxPt: 16, minPt: 10 });
    if (d.cta) {
      const pH = textArea.h * 0.08;
      const pBox = { x: textArea.x, y: s.cursor(), w: textArea.w * 0.5, h: pH };
      prim.pill(slide, pBox, { fill: th.accent, label: d.cta });
    }
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // COMPARISON (side-by-side with check/cross rows)
  // ══════════════════════════════════════════════════════════════════════
  function comparison(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const cols = d.columns || [];
    if (!cols.length) return slide;
    const labels = d.rows || [];
    const headH = body.h * 0.12;
    const colW = body.w / (cols.length + 1);
    // header row
    cols.forEach((col, i) => {
      const x = body.x + colW + i * colW;
      prim.rect(slide, { x, y: body.y, w: colW, h: headH }, {
        fill: col.highlighted ? th.accent : th.surface,
        stroke: th.stroke, strokeW: 1,
        label: col.name, labelOpts: { bold: true, align: 'center', valign: 'middle',
          fontFace: FONTS.HEADLINE, color: col.highlighted ? PALETTE.DARK_GRAY : th.onSurface,
          maxPt: 16 },
      });
    });
    // data rows
    const rowH = (body.h - headH) / Math.max(labels.length, 1);
    labels.forEach((row, ri) => {
      const y = body.y + headH + ri * rowH;
      prim.rect(slide, { x: body.x, y, w: colW, h: rowH },
        { fill: ri % 2 === 0 ? th.bg : th.altSurface, stroke: th.stroke, strokeW: 0.5,
          label: row.label, labelOpts: { bold: true, align: 'left', valign: 'middle',
            color: th.onBg, fontFace: FONTS.HEADLINE, maxPt: 13 } });
      cols.forEach((col, ci) => {
        const x = body.x + colW + ci * colW;
        const val = row.values ? row.values[ci] : undefined;
        const cell = { x, y, w: colW, h: rowH };
        prim.rect(slide, cell, { fill: ri % 2 === 0 ? th.bg : th.altSurface,
          stroke: th.stroke, strokeW: 0.5 });
        if (val === true || val === 'yes' || val === '✓') {
          const s = Math.min(cell.w, cell.h) * 0.35;
          prim.checkCircle(slide, { x: cell.x + cell.w / 2 - s / 2,
            y: cell.y + cell.h / 2 - s / 2, w: s, h: s },
            { color: PALETTE.GREEN });
        } else if (val === false || val === 'no' || val === '✗') {
          prim.text(slide, '✗', cell,
            { bold: true, align: 'center', valign: 'middle',
              color: PALETTE.RED, fontFace: FONTS.HEADLINE, maxPt: 28 });
        } else if (val !== undefined && val !== null && val !== '') {
          prim.text(slide, String(val), cell,
            { align: 'center', valign: 'middle', color: th.onBg, maxPt: 13 });
        }
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // CHECKLIST (green checkmarks)
  // ══════════════════════════════════════════════════════════════════════
  function checklist(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const items = d.items || [];
    if (!items.length) return slide;
    const rowH = Math.min(body.h / items.length, engine.H * 0.09);
    items.forEach((it, i) => {
      const y = body.y + i * rowH;
      const done = typeof it === 'string' ? true : !!it.done;
      const txt  = typeof it === 'string' ? it : (it.text || it.label || '');
      const boxBox = { x: body.x, y: y + rowH * 0.15, w: rowH * 0.7, h: rowH * 0.7 };
      if (done) prim.checkCircle(slide, boxBox, { color: th.accent });
      else prim.rect(slide, boxBox, { fill: th.bg, stroke: th.stroke, strokeW: 1 });
      prim.text(slide, txt,
        { x: boxBox.x + boxBox.w + body.w * 0.02, y: y, w: body.w * 0.9, h: rowH },
        { valign: 'middle', color: th.onBg, maxPt: 16, minPt: 10 });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // VENN (2 or 3 overlapping circles)
  // ══════════════════════════════════════════════════════════════════════
  function venn(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const sets = d.sets || [];
    if (!sets.length) return slide;
    const cx = body.x + body.w / 2, cy = body.y + body.h / 2;
    const r = Math.min(body.w, body.h) * 0.25;
    const positions = sets.length === 2
      ? [{ x: cx - r * 0.6, y: cy }, { x: cx + r * 0.6, y: cy }]
      : [{ x: cx, y: cy - r * 0.5 },
         { x: cx - r * 0.7, y: cy + r * 0.4 },
         { x: cx + r * 0.7, y: cy + r * 0.4 }];
    sets.forEach((st, i) => {
      const p = positions[i];
      const c = { x: p.x - r, y: p.y - r, w: r * 2, h: r * 2 };
      prim.ellipse(slide, c, {
        fill: st.color || (i === 0 ? th.accent : i === 1 ? th.accentSoft : th.altSurface),
        stroke: th.stroke, strokeW: 1,
      });
      prim.text(slide, st.label || '',
        { x: c.x, y: c.y, w: c.w, h: c.h * 0.25 },
        { bold: true, align: 'center', valign: 'middle',
          color: PALETTE.DARK_GRAY, fontFace: FONTS.HEADLINE, maxPt: 16 });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // PILLARS (3-6 vertical columns with icon + caption)
  // ══════════════════════════════════════════════════════════════════════
  function pillars(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const items = d.pillars || [];
    if (!items.length) return slide;
    const g = engine.grid(items.length, 1, body);
    items.forEach((p, i) => {
      const cell = g.cell(i, 0);
      prim.iconBox(slide, cell, {
        icon: p.icon || '●', iconColor: p.color || th.accent,
        label: p.label || p.title || '',
        subLabel: p.description || '',
        bg: th.surface, onColor: th.onSurface,
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // CARD GRID (generic rectangular card grid)
  // ══════════════════════════════════════════════════════════════════════
  function card_grid(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const cards = d.cards || [];
    if (!cards.length) return slide;
    const cols = Math.min(Math.max(2, d.columns || 3), cards.length);
    const rows = Math.ceil(cards.length / cols);
    const g = engine.grid(cols, rows, body);
    cards.forEach((card, i) => {
      const cell = g.cell(i % cols, Math.floor(i / cols));
      prim.roundRect(slide, cell, {
        fill: card.color || th.surface, stroke: th.stroke, strokeW: 1, radiusFrac: 0.06 });
      const s = engine.stack({ x: cell.x + cell.w * 0.08, y: cell.y + cell.h * 0.08,
                               w: cell.w * 0.84, gap: cell.h * 0.03 });
      if (card.eyebrow) prim.text(slide, String(card.eyebrow).toUpperCase(), s.place(cell.h * 0.1),
        { bold: true, fontFace: FONTS.HEADLINE, color: th.accent, maxPt: 12 });
      prim.text(slide, card.title || card.label || '', s.place(cell.h * 0.18),
        { bold: true, fontFace: FONTS.HEADLINE, color: th.onSurface, maxPt: 20 });
      if (card.description) prim.text(slide, card.description,
        s.place(cell.h * 0.5),
        { color: th.onSurface, maxPt: 12, minPt: 9, valign: 'top' });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // STEPS VERTICAL (numbered list with connector line)
  // ══════════════════════════════════════════════════════════════════════
  function steps_vertical(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const steps = d.steps || [];
    if (!steps.length) return slide;
    const rowH = body.h / steps.length;
    const badgeR = Math.min(rowH * 0.5, body.w * 0.05);

    // connector line
    prim.shape(slide, pres.shapes.RECTANGLE,
      { x: body.x + badgeR - engine.W * 0.002,
        y: body.y + rowH * 0.5, w: engine.W * 0.004,
        h: rowH * (steps.length - 1) },
      { fill: { color: th.accent }, line: { color: th.accent, width: 0 } });

    steps.forEach((st, i) => {
      const y = body.y + i * rowH;
      const b = { x: body.x, y: y + rowH * 0.5 - badgeR, w: badgeR * 2, h: badgeR * 2 };
      prim.numberCircle(slide, b, { n: i + 1, color: th.accent });
      const t = { x: body.x + badgeR * 2 + body.w * 0.02,
                  y: y, w: body.w - badgeR * 2 - body.w * 0.04, h: rowH };
      prim.text(slide, st.title || st.label || '',
        { x: t.x, y: t.y + rowH * 0.1, w: t.w, h: rowH * 0.35 },
        { bold: true, fontFace: FONTS.HEADLINE, color: th.onBg, maxPt: 18 });
      if (st.description) prim.text(slide, st.description,
        { x: t.x, y: t.y + rowH * 0.45, w: t.w, h: rowH * 0.5 },
        { color: th.muted, maxPt: 12, valign: 'top' });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // THANK YOU / CLOSING
  // ══════════════════════════════════════════════════════════════════════
  function thank_you(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const c = engine.rects.content();
    prim.text(slide, String(d.title || 'THANK YOU').toUpperCase(),
      { x: c.x, y: c.y + c.h * 0.3, w: c.w, h: c.h * 0.25 },
      { fontFace: FONTS.HEADLINE, bold: true, color: th.accent,
        align: 'center', valign: 'middle', maxPt: Math.floor(c.h * 72 * 0.3) });
    if (d.subtitle) prim.text(slide, d.subtitle,
      { x: c.x, y: c.y + c.h * 0.55, w: c.w, h: c.h * 0.08 },
      { align: 'center', color: th.muted, italic: true, maxPt: 18 });
    if (d.contact) prim.text(slide, d.contact,
      { x: c.x, y: c.y + c.h * 0.68, w: c.w, h: c.h * 0.08 },
      { align: 'center', bold: true, fontFace: FONTS.HEADLINE,
        color: th.onBg, maxPt: 18 });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // CODE SLIDE (monospace block)
  // ══════════════════════════════════════════════════════════════════════
  function code(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const lang = d.language || '';
    // header pill
    if (lang) {
      const pH = body.h * 0.08;
      prim.pill(slide, { x: body.x, y: body.y, w: body.w * 0.18, h: pH },
        { fill: th.accent, label: lang.toUpperCase() });
    }
    prim.rect(slide,
      { x: body.x, y: body.y + body.h * 0.1, w: body.w, h: body.h * 0.9 },
      { fill: PALETTE.DARK_GRAY, stroke: PALETTE.DARK_GRAY, strokeW: 0 });
    prim.text(slide, String(d.code || ''),
      { x: body.x + body.w * 0.03, y: body.y + body.h * 0.13,
        w: body.w * 0.94, h: body.h * 0.85 },
      { fontFace: FONTS.MONO, color: PALETTE.YELLOW, valign: 'top',
        maxPt: 14, minPt: 8, autoFit: true });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // ORG CHART (root + children, one level)
  // ══════════════════════════════════════════════════════════════════════
  function org_chart(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const root = d.root || { label: 'CEO' };
    const children = d.children || [];

    // root box
    const rootW = body.w * 0.22, rootH = body.h * 0.18;
    const rootX = body.x + (body.w - rootW) / 2;
    const rootY = body.y;
    prim.roundRect(slide, { x: rootX, y: rootY, w: rootW, h: rootH }, {
      fill: th.accent, stroke: th.accent, strokeW: 0, radiusFrac: 0.1,
      label: root.label, labelOpts: { bold: true, color: PALETTE.DARK_GRAY,
        align: 'center', valign: 'middle', fontFace: FONTS.HEADLINE, maxPt: 20 },
    });

    if (!children.length) return slide;
    const childW = body.w / children.length * 0.85;
    const childH = body.h * 0.2;
    const childY = body.y + body.h - childH;
    // connector from root
    const rootBottomX = rootX + rootW / 2;
    const rootBottomY = rootY + rootH;
    const midY = (rootBottomY + childY) / 2;

    children.forEach((c, i) => {
      const cx = body.x + (body.w / children.length) * (i + 0.5);
      const bx = cx - childW / 2;
      prim.roundRect(slide, { x: bx, y: childY, w: childW, h: childH }, {
        fill: th.surface, stroke: th.stroke, strokeW: 1, radiusFrac: 0.1,
        label: c.label || c.name || '', labelOpts: { bold: true,
          color: th.onSurface, align: 'center', valign: 'middle',
          fontFace: FONTS.HEADLINE, maxPt: 16 } });
      // connector: root bottom -> midY -> cx -> childY
      prim.connector(slide, { x: rootBottomX, y: rootBottomY },
        { x: rootBottomX, y: midY }, { color: th.stroke });
      prim.connector(slide, { x: Math.min(rootBottomX, cx), y: midY },
        { x: Math.max(rootBottomX, cx), y: midY }, { color: th.stroke });
      prim.connector(slide, { x: cx, y: midY }, { x: cx, y: childY },
        { color: th.stroke });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // FEATURES (icon + title + body in rows)
  // ══════════════════════════════════════════════════════════════════════
  function features(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const items = d.items || [];
    if (!items.length) return slide;
    const g = engine.grid(
      Math.min(3, items.length),
      Math.ceil(items.length / 3),
      body,
    );
    items.forEach((it, i) => {
      const cell = g.cell(i % 3, Math.floor(i / 3));
      prim.iconBox(slide, cell, {
        icon: it.icon || '◆', iconColor: th.accent,
        label: it.title || it.label || '',
        subLabel: it.description || '',
        bg: th.surface, onColor: th.onSurface,
      });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // BADGE STRIP (row of colored pill tags)
  // ══════════════════════════════════════════════════════════════════════
  function badge_strip(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const tags = d.tags || [];
    if (!tags.length) return slide;
    const r = engine.row({ x: body.x, y: body.y + body.h * 0.25,
                           h: body.h * 0.12, gap: body.w * 0.015 });
    tags.forEach(t => {
      const label = typeof t === 'string' ? t : t.label;
      const color = typeof t === 'string' ? th.accent : (t.color || th.accent);
      const w = body.w * Math.min(0.2, Math.max(0.08, label.length * 0.012));
      const box = r.place(w);
      prim.pill(slide, box, { fill: color, label: label });
    });
    return slide;
  }

  // ══════════════════════════════════════════════════════════════════════
  // BEFORE / AFTER
  // ══════════════════════════════════════════════════════════════════════
  function before_after(slide, d) {
    const th = themeFor(d); setBg(slide, th);
    const body = chrome(slide, d, th);
    const cols = engine.grid(2, 1, body);
    [['before', 'BEFORE', th.altSurface, PALETTE.RED],
     ['after',  'AFTER',  th.surface,    PALETTE.GREEN]].forEach(([key, hdr, bg, strip], i) => {
      const cell = cols.cell(i, 0);
      prim.rect(slide, cell, { fill: bg, stroke: th.stroke, strokeW: 1 });
      prim.rect(slide, { ...cell, h: cell.h * 0.1 }, { fill: strip,
        label: hdr, labelOpts: { bold: true, align: 'center', valign: 'middle',
          color: PALETTE.WHITE, fontFace: FONTS.HEADLINE, maxPt: 18 } });
      const items = (d[key] || []).map(x => ({ text: String(x),
        options: { bullet: { type: 'bullet' }, paraSpaceBef: 4, paraSpaceAft: 4 } }));
      prim.text(slide, items,
        { x: cell.x + cell.w * 0.06, y: cell.y + cell.h * 0.15,
          w: cell.w * 0.88, h: cell.h * 0.8 },
        { color: th.onBg, maxPt: 16, minPt: 10 });
    });
    return slide;
  }

  // ── Registry ──────────────────────────────────────────────────────────
  return {
    timeline, process, swot, matrix_2x2, funnel, roadmap, kpi_dashboard,
    pricing_tiers, testimonial, team_grid, agenda, big_number, split,
    comparison, checklist, venn, pillars, card_grid, steps_vertical,
    thank_you, code, org_chart, features, badge_strip, before_after,
  };
}

module.exports = { buildExtraTemplates };
