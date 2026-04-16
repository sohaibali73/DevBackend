"""
PPTX Sandbox
============
Generates Potomac-branded PowerPoint presentations server-side using the
``pptxgenjs`` npm package in a Node.js subprocess.

Assets (Potomac logos) are mounted from brand-assets/logos/ directories.

Usage
-----
    from core.sandbox.pptx_sandbox import PptxSandbox
    from core.file_store import store_file

    sandbox = PptxSandbox()
    result  = sandbox.generate(spec_dict, timeout=90)
    if result.success:
        entry = store_file(result.data, result.filename, "pptx", "generate_pptx")
        download_url = f"/files/{entry.file_id}/download"

Layout
------
All slides use PptxGenJS LAYOUT_WIDE (13.333" × 7.5").
See: https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/

Every dimension inside the JS builder is derived at runtime from SLIDE_W / SLIDE_H
and the margin constants — there is no hardcoded positional math.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_SANDBOX_HOME   = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_PPTX_CACHE_DIR = _SANDBOX_HOME / "pptx_cache"

# Assets: prefer persistent Railway volume, fall back to repo copy.
_THIS_DIR          = Path(__file__).parent
_REPO_ASSETS_DIR   = _THIS_DIR.parent.parent / "ClaudeSkills" / "potomac-pptx" / "brand-assets" / "logos"
_STORAGE_ROOT      = Path(os.environ.get("STORAGE_ROOT", "/data"))
_VOLUME_ASSETS_DIR = _STORAGE_ROOT / "pptx_assets"
_ASSETS_DIR        = _VOLUME_ASSETS_DIR if _VOLUME_ASSETS_DIR.exists() else _REPO_ASSETS_DIR

_LOGO_FILES = [
    "potomac-full-logo.png",
    "potomac-icon-black.png",
    "potomac-icon-yellow.png",
]

# ── Slide Dimension Constants (documentation only — JS derives these itself) ──
SLIDE_WIDTH  = 13.333   # inches  (LAYOUT_WIDE)
SLIDE_HEIGHT = 7.5      # inches  (LAYOUT_WIDE)

# ── Brand Palette ─────────────────────────────────────────────────────────────
YELLOW        = 'FEC00F'
DARK_GRAY     = '212121'
WHITE         = 'FFFFFF'
GRAY_60       = '999999'
GRAY_20       = 'DDDDDD'
YELLOW_20     = 'FEF7D8'
SUCCESS_GREEN = '22C55E'
ALERT_RED     = 'EB2F5C'

# ── Brand Fonts ───────────────────────────────────────────────────────────────
FONT_H = 'Rajdhani'    # Headline font — ALWAYS ALL CAPS per Potomac brand
FONT_B = 'Quicksand'   # Body / caption font


# ─────────────────────────────────────────────────────────────────────────────
# Embedded Node.js presentation builder
# Every position is computed from the top-level dimension/margin constants.
# NO hardcoded coordinate numbers appear below those constants.
# ─────────────────────────────────────────────────────────────────────────────
_BUILDER_SCRIPT = r"""
'use strict';
const fs      = require('fs');
const path    = require('path');
const pptxgen = require('pptxgenjs');

// ═══════════════════════════════════════════════════════════════════════════
// SLIDE CANVAS  —  LAYOUT_WIDE  (PptxGenJS built-in, 13.333" × 7.5")
// https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/
// Every coordinate in this file is derived from these two numbers.
// ═══════════════════════════════════════════════════════════════════════════
const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

// ── Brand palette ─────────────────────────────────────────────────────────
const YELLOW    = 'FEC00F';
const DARK_GRAY = '212121';
const WHITE     = 'FFFFFF';
const GRAY_60   = '999999';
const GRAY_20   = 'DDDDDD';
const YELLOW_20 = 'FEF7D8';
const GREEN     = '22C55E';
const RED       = 'EB2F5C';

// ── Brand fonts ───────────────────────────────────────────────────────────
const FONT_H = 'Rajdhani';
const FONT_B = 'Quicksand';

// ── Margin / chrome constants (all derived from SLIDE_W / SLIDE_H) ────────
const M_LEFT   = SLIDE_W * 0.0375;   // ~0.5"
const M_RIGHT  = SLIDE_W * 0.0375;   // ~0.5"
const M_TOP    = SLIDE_H * 0.04;     // ~0.3"
const M_BOTTOM = SLIDE_H * 0.04;     // ~0.3"

// Usable content area
const CONTENT_W = SLIDE_W - M_LEFT - M_RIGHT;
const CONTENT_H = SLIDE_H - M_TOP  - M_BOTTOM;

// Logo bounding box in the top-right corner
const LOGO_X   = SLIDE_W - M_RIGHT - CONTENT_W * 0.135;
const LOGO_Y   = M_TOP;
const LOGO_MAX_W = CONTENT_W * 0.135;
const LOGO_MAX_H = SLIDE_H * 0.09;

// Standard title band
const TITLE_Y   = M_TOP + SLIDE_H * 0.013;
const TITLE_H   = SLIDE_H * 0.12;
const ULINE_H   = SLIDE_H * 0.008;
const ULINE_W   = CONTENT_W * 0.2;

// Y coordinate where body content begins (below title + underline + gap)
const BODY_Y    = TITLE_Y + TITLE_H + ULINE_H + SLIDE_H * 0.027;
const BODY_H    = SLIDE_H - BODY_Y - M_BOTTOM;

// Left accent bar
const ACCENT_W  = SLIDE_W * 0.011;

// ── Logo aspect-ratio table ────────────────────────────────────────────────
const LOGO_DIMS = {
  full:   { aspect: 3.6 },
  black:  { aspect: 1.0 },
  yellow: { aspect: 1.0 },
};

// ── Logo helpers ──────────────────────────────────────────────────────────
const assetsDir = path.join(__dirname, 'assets');
function loadLogoData(name) {
  const p = path.join(assetsDir, name);
  if (fs.existsSync(p)) return 'data:image/png;base64,' + fs.readFileSync(p).toString('base64');
  return null;
}
const LOGOS = {
  full:   loadLogoData('potomac-full-logo.png'),
  black:  loadLogoData('potomac-icon-black.png'),
  yellow: loadLogoData('potomac-icon-yellow.png'),
};

// Return {w, h} that fits inside maxW × maxH while preserving aspect ratio.
function fitDims(aspect, maxW, maxH) {
  if (maxW / maxH > aspect) {
    const h = maxH;
    return { w: h * aspect, h };
  }
  const w = maxW;
  return { w, h: w / aspect };
}

// Place a logo centered inside a bounding box, preserving aspect ratio.
function addLogo(slide, bx, by, bw, bh, variant) {
  const data = variant === 'black'  ? LOGOS.black
             : variant === 'yellow' ? LOGOS.yellow
             :                        LOGOS.full;
  const asp  = (LOGO_DIMS[variant] || LOGO_DIMS.full).aspect;
  if (data) {
    const { w, h } = fitDims(asp, bw, bh);
    slide.addImage({ data, x: bx + (bw - w) / 2, y: by + (bh - h) / 2, w, h });
  } else {
    slide.addText('POTOMAC', {
      x: bx, y: by, w: bw, h: bh,
      fontFace: FONT_H, fontSize: 14, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle',
    });
  }
}

// ── Theme resolver ────────────────────────────────────────────────────────
function getTheme(d) {
  const dark = d.background === 'dark' || d.theme === 'dark';
  return {
    dark,
    bg:      dark ? DARK_GRAY : WHITE,
    titleClr: dark ? WHITE    : DARK_GRAY,
    bodyClr:  dark ? 'CCCCCC' : DARK_GRAY,
    muted:    dark ? '888888' : GRAY_60,
    cardBg:   dark ? '323232' : 'F0F0F0',
    border:   dark ? '505050' : GRAY_20,
    logo:     dark ? 'yellow' : 'full',
  };
}

// ── Shared chrome helpers ─────────────────────────────────────────────────
// Draw the left accent bar, logo, title text, and underline that most slides share.
function addStandardChrome(slide, d, t, fontSize) {
  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: ACCENT_W, h: SLIDE_H, fill: { color: YELLOW },
  });

  // Top-right logo
  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  // Title — capped so it never reaches the logo
  const titleW = LOGO_X - M_LEFT - SLIDE_W * 0.015;
  slide.addText((d.title || '').toUpperCase(), {
    x: M_LEFT, y: TITLE_Y, w: titleW, h: TITLE_H,
    fontFace: FONT_H, fontSize: fontSize || 26, bold: true,
    color: t.titleClr, valign: 'middle',
  });

  // Yellow underline beneath the title
  slide.addShape(pres.shapes.RECTANGLE, {
    x: M_LEFT, y: TITLE_Y + TITLE_H, w: ULINE_W, h: ULINE_H,
    fill: { color: YELLOW },
  });
}

// ── Create presentation ───────────────────────────────────────────────────
const spec = JSON.parse(fs.readFileSync('spec.json', 'utf8'));
const pres  = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = spec.title || 'POTOMAC PRESENTATION';

// Use the PptxGenJS built-in LAYOUT_WIDE preset (13.333" × 7.5").
// https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/
pres.layout = 'LAYOUT_WIDE';

// ═══════════════════════════════════════════════════════════════════════════
// SLIDE BUILDERS
// Every x/y/w/h is an expression of SLIDE_W, SLIDE_H, and the margin/chrome
// constants defined above. No literal coordinate numbers are allowed.
// ═══════════════════════════════════════════════════════════════════════════

// ── Title Slide ───────────────────────────────────────────────────────────
function buildTitleSlide(d) {
  const slide  = pres.addSlide();
  const isExec = d.style === 'executive';
  const t      = getTheme(d);
  slide.background = { color: t.bg };

  // Logo — centred in a generous box
  const lgW = SLIDE_W * 0.135;
  const lgH = SLIDE_H * 0.2;
  const lgX = (SLIDE_W - lgW) / 2;
  const lgY = SLIDE_H * 0.06;
  addLogo(slide, lgX, lgY, lgW, lgH, isExec ? 'yellow' : 'full');

  // Main title
  slide.addText((d.title || '').toUpperCase(), {
    x: M_LEFT, y: SLIDE_H * 0.32, w: CONTENT_W, h: SLIDE_H * 0.2,
    fontFace: FONT_H, fontSize: 44, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle',
  });

  // Subtitle
  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: M_LEFT, y: SLIDE_H * 0.547, w: CONTENT_W, h: SLIDE_H * 0.12,
      fontFace: FONT_B, fontSize: 20, italic: isExec,
      color: isExec ? YELLOW : GRAY_60, align: 'center', valign: 'middle',
    });
  }

  // Accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: M_LEFT, y: SLIDE_H * 0.733, w: CONTENT_W, h: SLIDE_H * 0.011,
    fill: { color: YELLOW },
  });

  // Tagline
  const tagline = d.tagline || (isExec ? 'Built to Conquer Risk' : null);
  if (tagline) {
    slide.addText(tagline, {
      x: M_LEFT, y: SLIDE_H * 0.773, w: CONTENT_W, h: SLIDE_H * 0.067,
      fontFace: FONT_B, fontSize: 15, italic: true,
      color: YELLOW, align: 'center', valign: 'middle',
    });
  }

  return slide;
}

// ── Content / Bullets Slide ───────────────────────────────────────────────
function buildContentSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 30);

  const bullets = d.bullets || (Array.isArray(d.content) ? d.content : null);
  const text    = d.text   || (!Array.isArray(d.content) ? d.content : null);

  if (bullets && bullets.length > 0) {
    const items = bullets.map(b => ({
      text: String(b),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 6, paraSpaceAft: 6 },
    }));
    slide.addText(items, {
      x: M_LEFT, y: BODY_Y, w: CONTENT_W, h: BODY_H,
      fontFace: FONT_B, fontSize: 18, color: t.bodyClr, valign: 'top',
    });
  } else if (text) {
    slide.addText(String(text), {
      x: M_LEFT, y: BODY_Y, w: CONTENT_W, h: BODY_H,
      fontFace: FONT_B, fontSize: 16, color: t.bodyClr, valign: 'top',
    });
  }

  return slide;
}

// ── Two-Column Slide ──────────────────────────────────────────────────────
function buildTwoColumnSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const gap  = CONTENT_W * 0.048;
  const colW = (CONTENT_W - gap) / 2;
  const lX   = M_LEFT;
  const rX   = lX + colW + gap;

  const hasHdrs = d.left_header || d.right_header;
  const hdrH    = SLIDE_H * 0.056;
  const hdrGap  = SLIDE_H * 0.02;

  if (d.left_header) {
    slide.addText(String(d.left_header), {
      x: lX, y: BODY_Y, w: colW, h: hdrH,
      fontFace: FONT_H, fontSize: 14, bold: true, color: YELLOW, valign: 'middle',
    });
  }
  if (d.right_header) {
    slide.addText(String(d.right_header), {
      x: rX, y: BODY_Y, w: colW, h: hdrH,
      fontFace: FONT_H, fontSize: 14, bold: true, color: YELLOW, valign: 'middle',
    });
  }

  const cy = hasHdrs ? BODY_Y + hdrH + hdrGap : BODY_Y;
  const ch = SLIDE_H - cy - M_BOTTOM;
  const lT = d.left_content  || (d.columns && d.columns[0]) || '';
  const rT = d.right_content || (d.columns && d.columns[1]) || '';

  slide.addText(String(lT), {
    x: lX, y: cy, w: colW, h: ch,
    fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top',
  });

  // Divider line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: lX + colW + gap / 2 - SLIDE_W * 0.0015, y: BODY_Y - SLIDE_H * 0.027,
    w: SLIDE_W * 0.003, h: ch + SLIDE_H * 0.027,
    fill: { color: GRAY_20 },
  });

  slide.addText(String(rT), {
    x: rX, y: cy, w: colW, h: ch,
    fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top',
  });

  return slide;
}

// ── Three-Column Slide ────────────────────────────────────────────────────
function buildThreeColumnSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 24);

  const columns = d.columns        || [];
  const headers = d.column_headers || [];
  const gap     = CONTENT_W * 0.02;
  const colW    = (CONTENT_W - gap * 2) / 3;
  const hdrH    = SLIDE_H * 0.06;
  const hdrGap  = SLIDE_H * 0.013;

  for (let i = 0; i < 3; i++) {
    const xPos = M_LEFT + i * (colW + gap);

    if (headers[i]) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: xPos, y: BODY_Y, w: colW, h: hdrH,
        fill: { color: YELLOW },
      });
      slide.addText(String(headers[i]), {
        x: xPos, y: BODY_Y, w: colW, h: hdrH,
        fontFace: FONT_H, fontSize: 13, bold: true,
        color: DARK_GRAY, align: 'center', valign: 'middle',
      });
    }

    const cY = headers[i] ? BODY_Y + hdrH + hdrGap : BODY_Y;
    const cH = SLIDE_H - cY - M_BOTTOM;
    slide.addText(String(columns[i] || ''), {
      x: xPos, y: cY, w: colW, h: cH,
      fontFace: FONT_B, fontSize: 13, color: t.bodyClr, valign: 'top',
    });
  }

  return slide;
}

// ── Metrics / KPI Slide ───────────────────────────────────────────────────
function buildMetricsSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 28);

  const metrics = d.metrics || [];
  const perRow  = Math.min(3, Math.max(1, metrics.length));
  const numRows = Math.ceil(metrics.length / perRow);
  const ctxH    = d.context ? SLIDE_H * 0.107 : 0;
  const mW      = CONTENT_W / perRow;
  const startY  = BODY_Y + SLIDE_H * 0.093;
  const mH      = (SLIDE_H - startY - M_BOTTOM - ctxH) / numRows;

  metrics.forEach((m, i) => {
    const row  = Math.floor(i / perRow);
    const col  = i % perRow;
    const xPos = M_LEFT + col * mW + CONTENT_W * 0.008;
    const yPos = startY + row * mH;
    const valH = mH * 0.55;
    const lblH = mH * 0.45;

    slide.addText(String(m.value || ''), {
      x: xPos, y: yPos, w: mW - CONTENT_W * 0.016, h: valH,
      fontFace: FONT_H, fontSize: 48, bold: true,
      color: YELLOW, align: 'center', valign: 'middle',
    });
    slide.addText(String(m.label || ''), {
      x: xPos, y: yPos + valH, w: mW - CONTENT_W * 0.016, h: lblH,
      fontFace: FONT_B, fontSize: 14, color: t.muted, align: 'center',
    });
  });

  if (d.context) {
    slide.addText(String(d.context), {
      x: M_LEFT, y: SLIDE_H - M_BOTTOM - ctxH, w: CONTENT_W, h: ctxH,
      fontFace: FONT_B, fontSize: 11, italic: true, color: t.muted, align: 'center',
    });
  }

  return slide;
}

// ── Process / Steps Slide ─────────────────────────────────────────────────
function buildProcessSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const steps = d.steps || [];
  const n     = Math.max(1, steps.length);
  const stepW = CONTENT_W / n;
  const r     = SLIDE_H * 0.04;
  const cy    = BODY_Y + SLIDE_H * 0.147;

  steps.forEach((step, i) => {
    const cx = M_LEFT + i * stepW + stepW / 2 - r;

    slide.addShape(pres.shapes.ELLIPSE, {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fill: { color: YELLOW }, line: { color: YELLOW },
    });
    slide.addText(String(i + 1), {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fontFace: FONT_H, fontSize: 16, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle',
    });

    // Connector to next step
    if (i < steps.length - 1) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: cx + r * 2, y: cy + r - SLIDE_H * 0.003,
        w: stepW - r * 2, h: SLIDE_H * 0.005,
        fill: { color: GRAY_20 },
      });
    }

    // Step title
    slide.addText(String(step.title || '').toUpperCase(), {
      x: M_LEFT + i * stepW, y: cy + r * 2 + SLIDE_H * 0.02,
      w: stepW - SLIDE_W * 0.004, h: SLIDE_H * 0.08,
      fontFace: FONT_H, fontSize: 12, bold: true,
      color: t.titleClr, align: 'center',
    });

    // Step description
    const descY = cy + r * 2 + SLIDE_H * 0.02 + SLIDE_H * 0.08 + SLIDE_H * 0.013;
    const descH = SLIDE_H - descY - M_BOTTOM;
    slide.addText(String(step.description || ''), {
      x: M_LEFT + i * stepW, y: descY,
      w: stepW - SLIDE_W * 0.004, h: descH,
      fontFace: FONT_B, fontSize: 11, color: t.muted,
      align: 'center', valign: 'top',
    });
  });

  return slide;
}

// ── Quote Slide ───────────────────────────────────────────────────────────
function buildQuoteSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: YELLOW_20 };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, 'full');

  const qMarkW = CONTENT_W * 0.09;
  const qMarkH = SLIDE_H * 0.187;
  slide.addText('"', {
    x: M_LEFT * 0.8, y: SLIDE_H * 0.147, w: qMarkW, h: qMarkH,
    fontFace: FONT_H, fontSize: 96, bold: true,
    color: YELLOW, align: 'center', valign: 'middle',
  });

  const quoteX = M_LEFT * 0.8 + qMarkW;
  const quoteW = SLIDE_W - quoteX - M_RIGHT * 0.8;
  slide.addText(String(d.quote || ''), {
    x: quoteX, y: SLIDE_H * 0.24, w: quoteW, h: SLIDE_H * 0.4,
    fontFace: FONT_B, fontSize: 22, italic: true,
    color: DARK_GRAY, align: 'center', valign: 'middle',
  });

  if (d.attribution) {
    slide.addText('— ' + String(d.attribution), {
      x: quoteX, y: SLIDE_H * 0.667, w: quoteW, h: SLIDE_H * 0.093,
      fontFace: FONT_H, fontSize: 16, bold: true,
      color: GRAY_60, align: 'center',
    });
  }

  if (d.context) {
    slide.addText(String(d.context), {
      x: quoteX, y: SLIDE_H * 0.773, w: quoteW, h: SLIDE_H * 0.067,
      fontFace: FONT_B, fontSize: 12, italic: true,
      color: GRAY_60, align: 'center',
    });
  }

  return slide;
}

// ── Section Divider Slide ─────────────────────────────────────────────────
function buildSectionDividerSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  const barW = SLIDE_W * 0.034;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: barW, h: SLIDE_H, fill: { color: YELLOW },
  });

  const textX = barW + SLIDE_W * 0.034;
  const textW = SLIDE_W - textX - M_RIGHT;

  slide.addText((d.title || '').toUpperCase(), {
    x: textX, y: SLIDE_H * 0.32, w: textW, h: SLIDE_H * 0.213,
    fontFace: FONT_H, fontSize: 42, bold: true,
    color: t.titleClr, valign: 'middle',
  });

  if (d.description) {
    slide.addText(String(d.description), {
      x: textX, y: SLIDE_H * 0.56, w: textW, h: SLIDE_H * 0.2,
      fontFace: FONT_B, fontSize: 18, color: t.muted, valign: 'middle',
    });
  }

  return slide;
}

// ── CTA / Call-to-Action Slide ────────────────────────────────────────────
function buildCtaSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  const lgW = CONTENT_W * 0.135;
  const lgH = SLIDE_H * 0.133;
  const lgX = (SLIDE_W - lgW) / 2;
  addLogo(slide, lgX, SLIDE_H * 0.053, lgW, lgH, 'full');

  slide.addText((d.title || '').toUpperCase(), {
    x: M_LEFT, y: SLIDE_H * 0.24, w: CONTENT_W, h: SLIDE_H * 0.133,
    fontFace: FONT_H, fontSize: 34, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle',
  });

  if (d.action_text) {
    slide.addText(String(d.action_text), {
      x: M_LEFT, y: SLIDE_H * 0.4, w: CONTENT_W, h: SLIDE_H * 0.2,
      fontFace: FONT_B, fontSize: 18,
      color: t.bodyClr, align: 'center', valign: 'middle',
    });
  }

  // Button
  const btnW = CONTENT_W * 0.225;
  const btnH = SLIDE_H * 0.093;
  const btnX = M_LEFT + (CONTENT_W - btnW) / 2;
  const btnY = SLIDE_H * 0.64;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: btnX, y: btnY, w: btnW, h: btnH,
    fill: { color: YELLOW }, line: { color: YELLOW },
  });
  slide.addText((d.button_text || 'GET STARTED').toUpperCase(), {
    x: btnX, y: btnY, w: btnW, h: btnH,
    fontFace: FONT_H, fontSize: 15, bold: true,
    color: DARK_GRAY, align: 'center', valign: 'middle',
  });

  slide.addText('Built to Conquer Risk', {
    x: M_LEFT, y: SLIDE_H * 0.76, w: CONTENT_W, h: SLIDE_H * 0.067,
    fontFace: FONT_B, fontSize: 14, italic: true,
    color: YELLOW, align: 'center',
  });

  if (d.contact_info) {
    slide.addText(String(d.contact_info), {
      x: M_LEFT, y: SLIDE_H * 0.84, w: CONTENT_W, h: SLIDE_H * 0.107,
      fontFace: FONT_B, fontSize: 12, color: t.muted, align: 'center',
    });
  }

  return slide;
}

// ── Image Slide ───────────────────────────────────────────────────────────
function buildImageSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  const hasTitle = !!d.title;
  if (hasTitle) {
    slide.addText(d.title.toUpperCase(), {
      x: M_LEFT, y: TITLE_Y, w: CONTENT_W, h: TITLE_H,
      fontFace: FONT_H, fontSize: 26, bold: true,
      color: t.titleClr, valign: 'middle',
    });
  }

  if (!d.data) return slide;

  try {
    const imgData = 'data:image/' + (d.format || 'png') + ';base64,' + d.data;
    const yOff    = hasTitle ? BODY_Y : SLIDE_H * 0.2;
    const maxH    = SLIDE_H - yOff - M_BOTTOM;
    const maxW    = CONTENT_W;

    let w = d.width  || CONTENT_W * 0.45;
    let h = d.height || w * 0.667;
    if (h > maxH) { const sc = maxH / h; h = maxH; w = w * sc; }
    if (w > maxW) { const sc = maxW / w; w = maxW; h = h * sc; }

    const xOff = d.align === 'center' ? (SLIDE_W - w) / 2
               : d.align === 'right'  ? SLIDE_W - w - M_RIGHT
               : M_LEFT;

    slide.addImage({ data: imgData, x: xOff, y: yOff, w, h });

    if (d.caption) {
      slide.addText(String(d.caption), {
        x: M_LEFT, y: yOff + h + SLIDE_H * 0.02, w: CONTENT_W, h: SLIDE_H * 0.06,
        fontFace: FONT_B, fontSize: 12, italic: true, color: t.muted,
        align: d.align === 'center' ? 'center' : 'left',
      });
    }
  } catch (e) {
    process.stderr.write('WARN: image slide error: ' + e.message + '\n');
  }

  return slide;
}

// ── Table Slide ───────────────────────────────────────────────────────────
function buildTableSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const headers   = d.headers || [];
  const rows      = d.rows    || [];
  const tableRows = [];

  if (headers.length > 0) {
    tableRows.push(headers.map(h => ({
      text: String(h).toUpperCase(),
      options: {
        bold: true, color: DARK_GRAY, fill: { color: YELLOW },
        align: 'center', valign: 'middle', fontSize: 11, fontFace: FONT_H,
        border: { type: 'solid', color: DARK_GRAY, pt: 0.5 },
      },
    })));
  }

  rows.forEach((row, ri) => {
    const bg = ri % 2 === 1 ? 'F5F5F5' : WHITE;
    tableRows.push((Array.isArray(row) ? row : [row]).map((cell, ci) => {
      const isNum = d.number_cols && d.number_cols.includes(ci + 1);
      return {
        text: String(cell === null || cell === undefined ? '' : cell),
        options: {
          color: t.bodyClr, fill: { color: bg },
          align: isNum ? 'center' : 'left', fontSize: 11, fontFace: FONT_B,
          border: { type: 'solid', color: GRAY_20, pt: 0.5 },
        },
      };
    }));
  });

  if (d.totals_row) {
    const tRow  = d.totals_row;
    const cells = tRow.values ? [tRow.label, ...tRow.values] : [tRow.label || 'TOTAL'];
    tableRows.push(cells.map(c => ({
      text: String(c || ''),
      options: {
        bold: true, color: t.titleClr, fill: { color: YELLOW_20 },
        align: 'center', fontSize: 11, fontFace: FONT_H,
        border: { type: 'solid', color: DARK_GRAY, pt: 0.5 },
      },
    })));
  }

  if (tableRows.length > 0) {
    const numCols = Math.max(...tableRows.map(r => r.length));
    const colW    = CONTENT_W / Math.max(numCols, 1);
    const tableY  = BODY_Y;
    const tableH  = SLIDE_H - tableY - M_BOTTOM * 1.5;

    slide.addTable(tableRows, {
      x: M_LEFT, y: tableY, w: CONTENT_W,
      colW: Array(numCols).fill(colW),
      rowH: Math.min(SLIDE_H * 0.056, tableH / tableRows.length),
    });
  }

  if (d.caption) {
    slide.addText(String(d.caption), {
      x: M_LEFT, y: SLIDE_H - M_BOTTOM - SLIDE_H * 0.04, w: CONTENT_W, h: SLIDE_H * 0.04,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted,
    });
  }

  return slide;
}

// ── Chart Slide ───────────────────────────────────────────────────────────
function buildChartSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const chartType  = (d.chart_type || 'bar').toLowerCase();
  const categories = d.categories || d.labels || [];
  const values     = d.values     || [];
  const seriesData = d.series     || [];
  const capH       = d.caption ? SLIDE_H * 0.053 : 0;
  const chartH     = SLIDE_H - BODY_Y - M_BOTTOM - capH;

  if (chartType === 'waterfall') {
    const n       = categories.length;
    const maxVal  = Math.max(...values.map(Math.abs)) * 1.3 || 100;
    let running   = 0;
    const baseY   = BODY_Y + chartH;
    const barMaxH = chartH * 0.85;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: M_LEFT, y: baseY, w: CONTENT_W, h: SLIDE_H * 0.003,
      fill: { color: DARK_GRAY },
    });

    categories.forEach((cat, i) => {
      const val     = values[i] || 0;
      const colFrac = CONTENT_W / n;
      const barW    = colFrac / 1.5;
      const barH    = Math.abs(val) / maxVal * barMaxH;
      const isStart = i === 0;
      const isEnd   = i === n - 1;
      const color   = isStart || isEnd ? YELLOW : (val >= 0 ? GREEN : RED);
      const barX    = M_LEFT + i * colFrac + (colFrac - barW) / 2;
      const barY    = val >= 0
        ? baseY - ((running + val) / maxVal) * barMaxH
        : baseY - (running / maxVal) * barMaxH;

      slide.addShape(pres.shapes.RECTANGLE, {
        x: barX, y: barY, w: barW, h: barH,
        fill: { color }, line: { color: WHITE, pt: 1 },
      });

      const valStr = (val >= 0 && !isStart ? '+' : '') + val;
      slide.addText(String(valStr), {
        x: barX, y: barY - SLIDE_H * 0.043, w: barW, h: SLIDE_H * 0.04,
        fontFace: FONT_B, fontSize: 10, bold: true,
        color: t.titleClr, align: 'center',
      });
      slide.addText(String(cat), {
        x: barX - colFrac * 0.07, y: baseY + SLIDE_H * 0.007, w: barW + colFrac * 0.14, h: SLIDE_H * 0.053,
        fontFace: FONT_B, fontSize: 9, color: t.titleClr, align: 'center',
      });

      if (i > 0 && i < n - 1) running += val;
    });
  } else {
    let pptxChartType;
    const chartOpts = {
      x: M_LEFT, y: BODY_Y, w: CONTENT_W, h: chartH,
      chartColors: [YELLOW, DARK_GRAY, GRAY_60, RED, GREEN],
      showLegend: seriesData.length > 1, legendPos: 'b', legendFontSize: 10,
      dataLabelFontSize: 10, dataLabelColor: t.titleClr,
    };

    switch (chartType) {
      case 'line':          pptxChartType = pres.charts.LINE;     break;
      case 'pie':           pptxChartType = pres.charts.PIE;      chartOpts.showLegend = true; break;
      case 'donut':         pptxChartType = pres.charts.DOUGHNUT; chartOpts.showLegend = true; break;
      case 'scatter':       pptxChartType = pres.charts.SCATTER;  break;
      case 'area':          pptxChartType = pres.charts.AREA;     break;
      case 'stacked_bar':   pptxChartType = pres.charts.BAR;      chartOpts.barGrouping = 'stacked';   break;
      case 'clustered_bar': pptxChartType = pres.charts.BAR;      chartOpts.barGrouping = 'clustered'; break;
      default:              pptxChartType = pres.charts.BAR;      break;
    }

    const chartData = seriesData.length > 0
      ? seriesData.map(s => ({ name: s.name || '', labels: categories, values: s.values || [] }))
      : [{ name: d.y_axis_label || 'Value', labels: categories, values }];

    slide.addChart(pptxChartType, chartData, chartOpts);
  }

  if (d.caption) {
    slide.addText(String(d.caption), {
      x: M_LEFT, y: SLIDE_H - M_BOTTOM - capH, w: CONTENT_W, h: capH,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted, align: 'center',
    });
  }

  return slide;
}

// ── Timeline Slide ────────────────────────────────────────────────────────
function buildTimelineSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const milestones = d.milestones || [];
  const n          = Math.max(1, milestones.length);
  const lineX      = M_LEFT * 1.6;
  const lineW      = SLIDE_W - lineX - M_RIGHT * 1.6;
  const r          = SLIDE_H * 0.024;
  const timelineY  = SLIDE_H * 0.507;
  const stepW      = n > 1 ? lineW / (n - 1) : lineW;

  slide.addShape(pres.shapes.RECTANGLE, {
    x: lineX, y: timelineY - SLIDE_H * 0.003,
    w: lineW, h: SLIDE_H * 0.005,
    fill: { color: YELLOW },
  });

  milestones.forEach((m, i) => {
    const xC        = n === 1 ? lineX + lineW / 2 : lineX + i * stepW;
    const isDone    = (m.status || '').toLowerCase() === 'complete';
    const isCurrent = (m.status || '').toLowerCase() === 'in_progress';
    const dotFill   = isDone ? YELLOW : (isCurrent ? 'FEE896' : WHITE);
    const dotLine   = isDone ? YELLOW : DARK_GRAY;
    const textColor = isDone || isCurrent ? t.titleClr : t.muted;
    const isAbove   = i % 2 === 0;

    const labelH    = SLIDE_H * 0.067;
    const dateH     = SLIDE_H * 0.047;
    const connMin   = SLIDE_H * 0.02;
    const labelY    = isAbove ? timelineY - r - connMin - labelH - dateH
                              : timelineY + r + connMin + dateH;
    const dateY     = isAbove ? timelineY - r - connMin - dateH
                              : timelineY + r + connMin;
    const labelW    = Math.min(stepW * 0.9, SLIDE_W * 0.15);

    slide.addShape(pres.shapes.ELLIPSE, {
      x: xC - r, y: timelineY - r, w: r * 2, h: r * 2,
      fill: { color: dotFill }, line: { color: dotLine, pt: 1.5 },
    });
    slide.addText(String(m.label || '').toUpperCase(), {
      x: xC - labelW / 2, y: labelY, w: labelW, h: labelH,
      fontFace: FONT_H, fontSize: 11, bold: true,
      color: textColor, align: 'center',
    });
    slide.addText(String(m.date || ''), {
      x: xC - labelW / 2, y: dateY, w: labelW, h: dateH,
      fontFace: FONT_B, fontSize: 10, color: t.muted, align: 'center',
    });

    // Connector line
    const connY1 = isAbove ? labelY + labelH       : timelineY + r;
    const connY2 = isAbove ? timelineY - r         : dateY;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: xC - SLIDE_W * 0.0008, y: Math.min(connY1, connY2),
      w: SLIDE_W * 0.0015, h: Math.abs(connY2 - connY1),
      fill: { color: dotFill },
    });
  });

  if (d.caption) {
    slide.addText(String(d.caption), {
      x: M_LEFT, y: SLIDE_H - M_BOTTOM - SLIDE_H * 0.053,
      w: CONTENT_W, h: SLIDE_H * 0.053,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted, align: 'center',
    });
  }

  return slide;
}

// ── Matrix 2×2 Slide ──────────────────────────────────────────────────────
function buildMatrix2x2Slide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const matrixX = M_LEFT * 2;
  const matrixY = BODY_Y;
  const matrixW = SLIDE_W - matrixX - M_RIGHT * 0.75;
  const matrixH = SLIDE_H - matrixY - M_BOTTOM * 2;
  const midX    = matrixX + matrixW / 2;
  const midY    = matrixY + matrixH / 2;
  const lineT   = SLIDE_H * 0.007;

  // Quadrant fills
  [
    [matrixX,       matrixY,       matrixW / 2, matrixH / 2, 'F9F9F9'],
    [midX,          matrixY,       matrixW / 2, matrixH / 2, YELLOW_20],
    [matrixX,       midY,          matrixW / 2, matrixH / 2, YELLOW_20],
    [midX,          midY,          matrixW / 2, matrixH / 2, 'F9F9F9'],
  ].forEach(([x, y, w, h, bg]) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w, h, fill: { color: bg }, line: { color: t.border, pt: 1 },
    });
  });

  // Cross lines
  slide.addShape(pres.shapes.RECTANGLE, {
    x: matrixX, y: midY - lineT / 2, w: matrixW, h: lineT,
    fill: { color: YELLOW },
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: midX - lineT / 2, y: matrixY, w: lineT, h: matrixH,
    fill: { color: YELLOW },
  });

  // Quadrant labels
  const qLabels = d.quadrant_labels || ['', '', '', ''];
  const qPad    = matrixW * 0.015;
  const qH      = SLIDE_H * 0.073;
  [
    [matrixX + qPad, matrixY + qPad],
    [midX    + qPad, matrixY + qPad],
    [matrixX + qPad, midY    + qPad],
    [midX    + qPad, midY    + qPad],
  ].forEach(([qx, qy], qi) => {
    if (qLabels[qi]) {
      slide.addText(String(qLabels[qi]).toUpperCase(), {
        x: qx, y: qy, w: matrixW / 2 - qPad * 2, h: qH,
        fontFace: FONT_H, fontSize: 9, bold: true, color: t.muted, valign: 'top',
      });
    }
  });

  // Axis labels
  if (d.x_label) {
    slide.addText(String(d.x_label).toUpperCase(), {
      x: matrixX, y: matrixY + matrixH + SLIDE_H * 0.013,
      w: matrixW, h: SLIDE_H * 0.047,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr, align: 'center',
    });
  }
  if (d.y_label) {
    slide.addText(String(d.y_label).toUpperCase(), {
      x: M_LEFT * 0.2, y: matrixY, w: M_LEFT * 1.5, h: matrixH,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr,
      align: 'center', valign: 'middle', rotate: 270,
    });
  }

  // Scatter items
  (d.items || []).forEach(item => {
    const px  = matrixX + (item.x || 0.5) * matrixW - SLIDE_W * 0.011;
    const py  = matrixY + (1 - (item.y || 0.5)) * matrixH - SLIDE_H * 0.02;
    const sz  = Math.max(SLIDE_W * 0.015, Math.min(SLIDE_W * 0.038, (item.size || 20) / 60 * SLIDE_W * 0.038));
    slide.addShape(pres.shapes.ELLIPSE, {
      x: px, y: py, w: sz, h: sz,
      fill: { color: YELLOW }, line: { color: t.titleClr, pt: 1 },
    });
    slide.addText(String(item.label || ''), {
      x: px + sz + SLIDE_W * 0.004, y: py, w: SLIDE_W * 0.113, h: sz,
      fontFace: FONT_B, fontSize: 10, bold: true, color: t.titleClr, valign: 'middle',
    });
  });

  return slide;
}

// ── Scorecard / RAG Table Slide ───────────────────────────────────────────
function buildScorecardSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const items     = d.items || [];
  const tableRows = [[
    { text: 'METRIC',  options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'STATUS',  options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, align: 'center', border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'VALUE',   options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, align: 'center', border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'COMMENT', options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
  ]];

  items.forEach((item, ri) => {
    const bg       = ri % 2 === 1 ? 'F5F5F5' : WHITE;
    const status   = (item.status || 'green').toLowerCase();
    const ragColor = status === 'green' ? GREEN : status === 'red' ? RED : YELLOW;
    const ragLabel = status === 'green' ? '● ON TRACK' : status === 'red' ? '● BREACH' : '● AT RISK';
    tableRows.push([
      { text: String(item.metric  || '').toUpperCase(), options: { bold: true, color: t.titleClr, fill: { color: bg }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: ragLabel,                                 options: { color: ragColor, fill: { color: bg }, fontSize: 11, fontFace: FONT_H, bold: true, align: 'center', border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: String(item.value   || ''),               options: { color: t.bodyClr, fill: { color: bg }, fontSize: 11, fontFace: FONT_B, align: 'center', border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: String(item.comment || ''),               options: { color: t.muted,   fill: { color: bg }, fontSize: 11, fontFace: FONT_B, border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
    ]);
  });

  const tableH = SLIDE_H - BODY_Y - M_BOTTOM * 1.5;
  slide.addTable(tableRows, {
    x: M_LEFT, y: BODY_Y, w: CONTENT_W,
    colW: [CONTENT_W * 0.28, CONTENT_W * 0.20, CONTENT_W * 0.24, CONTENT_W * 0.28],
    rowH: Math.min(SLIDE_H * 0.096, tableH / (items.length + 1)),
  });

  return slide;
}

// ── Comparison Slide (A vs B) ─────────────────────────────────────────────
function buildComparisonSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const rows   = d.rows        || [];
  const winner = d.winner      || 'right';
  const lLabel = d.left_label  || 'OPTION A';
  const rLabel = d.right_label || 'OPTION B';

  const col1W = CONTENT_W * 0.2;
  const colRem = CONTENT_W - col1W - CONTENT_W * 0.008;
  const col2W  = colRem / 2;
  const col3W  = colRem / 2;
  const hdrH   = SLIDE_H * 0.069;
  const rowH   = SLIDE_H * 0.083;
  const colGap = CONTENT_W * 0.004;
  const hdrY   = BODY_Y;

  // Header cells
  const col2X = M_LEFT + col1W + colGap;
  const col3X = col2X + col2W + colGap;

  slide.addShape(pres.shapes.RECTANGLE, { x: M_LEFT, y: hdrY, w: col1W, h: hdrH, fill: { color: GRAY_20 } });
  slide.addShape(pres.shapes.RECTANGLE, { x: col2X,  y: hdrY, w: col2W, h: hdrH, fill: { color: winner === 'left'  ? YELLOW : 'F5F5F5' } });
  slide.addShape(pres.shapes.RECTANGLE, { x: col3X,  y: hdrY, w: col3W, h: hdrH, fill: { color: winner === 'right' ? YELLOW : 'F5F5F5' } });

  // Winner accent stripe
  const stripeW = CONTENT_W * 0.005;
  if (winner === 'right') {
    slide.addShape(pres.shapes.RECTANGLE, { x: col3X - stripeW / 2, y: hdrY, w: stripeW, h: hdrH, fill: { color: YELLOW } });
  } else {
    slide.addShape(pres.shapes.RECTANGLE, { x: col2X - stripeW / 2, y: hdrY, w: stripeW, h: hdrH, fill: { color: YELLOW } });
  }

  slide.addText('', { x: M_LEFT, y: hdrY, w: col1W, h: hdrH, fontFace: FONT_B, fontSize: 12, color: t.titleClr, valign: 'middle' });
  slide.addText(String(lLabel).toUpperCase(), { x: col2X, y: hdrY, w: col2W, h: hdrH, fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center', valign: 'middle' });
  slide.addText(String(rLabel).toUpperCase(), { x: col3X, y: hdrY, w: col3W, h: hdrH, fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center', valign: 'middle' });

  const divH = SLIDE_H * 0.002;

  rows.forEach((row, ri) => {
    const rowY = hdrY + hdrH + SLIDE_H * 0.007 + ri * rowH;
    const bg   = ri % 2 === 1 ? 'F5F5F5' : WHITE;
    slide.addShape(pres.shapes.RECTANGLE, { x: M_LEFT, y: rowY, w: col1W, h: rowH, fill: { color: bg } });
    slide.addShape(pres.shapes.RECTANGLE, { x: col2X,  y: rowY, w: col2W, h: rowH, fill: { color: winner === 'left'  ? YELLOW_20 : bg } });
    slide.addShape(pres.shapes.RECTANGLE, { x: col3X,  y: rowY, w: col3W, h: rowH, fill: { color: winner === 'right' ? YELLOW_20 : bg } });

    slide.addText(String(row.label || '').toUpperCase(), { x: M_LEFT, y: rowY, w: col1W, h: rowH, fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr, valign: 'middle' });
    slide.addText(String(row.left  || ''),               { x: col2X,  y: rowY, w: col2W, h: rowH, fontFace: FONT_B, fontSize: 11, color: t.bodyClr, align: 'center', valign: 'middle' });
    slide.addText(String(row.right || ''),               { x: col3X,  y: rowY, w: col3W, h: rowH, fontFace: FONT_B, fontSize: 11, color: t.bodyClr, align: 'center', valign: 'middle' });
    slide.addShape(pres.shapes.RECTANGLE, { x: M_LEFT, y: rowY + rowH - divH, w: CONTENT_W, h: divH, fill: { color: GRAY_20 } });
  });

  return slide;
}

// ── Icon Grid Slide ───────────────────────────────────────────────────────
function buildIconGridSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const items   = d.items || [];
  const cols    = d.columns || Math.min(4, Math.max(1, Math.ceil(Math.sqrt(items.length))));
  const rows    = Math.ceil(items.length / cols);
  const cellW   = CONTENT_W / cols;
  const cellH   = (SLIDE_H - BODY_Y - M_BOTTOM) / rows;
  const iconMap = {
    shield: '🛡', chart: '📊', clock: '⏱', star: '★', check: '✓',
    lock: '🔒', globe: '🌐', dollar: '$', people: '👥', trophy: '🏆',
    lightning: '⚡', target: '🎯', default: '●',
  };

  items.forEach((item, idx) => {
    const col    = idx % cols;
    const row    = Math.floor(idx / cols);
    const cx     = M_LEFT + col * cellW + cellW * 0.008;
    const cy     = BODY_Y + row * cellH + cellH * 0.013;
    const iconSz = Math.min(SLIDE_W * 0.053, cellW * 0.3, cellH * 0.3);
    const iconX  = cx + (cellW - iconSz * 2 - cellW * 0.008) / 2;
    const iconChar = iconMap[item.icon] || iconMap.default;

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: iconX, y: cy + cellH * 0.013, w: iconSz, h: iconSz,
      fill: { color: YELLOW }, line: { color: YELLOW }, rectRadius: 0.15,
    });
    slide.addText(iconChar, {
      x: iconX, y: cy + cellH * 0.013, w: iconSz, h: iconSz,
      fontFace: 'Arial', fontSize: Math.round(iconSz * 30),
      color: DARK_GRAY, align: 'center', valign: 'middle',
    });

    const titleY = cy + iconSz + cellH * 0.04;
    const titleH = cellH * 0.12;
    slide.addText((item.title || '').toUpperCase(), {
      x: cx, y: titleY, w: cellW * 0.984, h: titleH,
      fontFace: FONT_H, fontSize: 12, bold: true,
      color: t.titleClr, align: 'center',
    });

    if (item.body) {
      slide.addText(String(item.body), {
        x: cx, y: titleY + titleH, w: cellW * 0.984, h: cellH - iconSz - cellH * 0.04 - titleH - cellH * 0.013,
        fontFace: FONT_B, fontSize: 11, color: t.muted,
        align: 'center', valign: 'top',
      });
    }
  });

  return slide;
}

// ── Executive Summary Slide ───────────────────────────────────────────────
function buildExecutiveSummarySlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  const barW    = SLIDE_W * 0.037;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: barW, h: SLIDE_H, fill: { color: YELLOW },
  });

  const textX  = barW + SLIDE_W * 0.034;
  const textW  = SLIDE_W - textX - M_RIGHT;
  const headY  = SLIDE_H * 0.133;
  const headH  = SLIDE_H * 0.333;
  const divY   = headY + headH;

  slide.addText((d.headline || d.title || '').toUpperCase(), {
    x: textX, y: headY, w: textW, h: headH,
    fontFace: FONT_H, fontSize: 28, bold: true,
    color: t.titleClr, valign: 'middle',
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: textX, y: divY, w: textW, h: ULINE_H,
    fill: { color: YELLOW },
  });

  const bulletY = divY + SLIDE_H * 0.027;
  const ctaH    = d.call_to_action ? SLIDE_H * 0.083 : 0;
  const bulletH = SLIDE_H - bulletY - M_BOTTOM - ctaH - SLIDE_H * 0.027;
  const points  = d.supporting_points || d.bullets || [];

  if (points.length > 0) {
    slide.addText(points.map(p => ({
      text: String(p),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 8, paraSpaceAft: 8 },
    })), {
      x: textX, y: bulletY, w: textW, h: bulletH,
      fontFace: FONT_B, fontSize: 16, color: t.bodyClr, valign: 'top',
    });
  }

  if (d.call_to_action) {
    const ctaY = SLIDE_H - M_BOTTOM - ctaH;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: textX, y: ctaY, w: textW, h: ctaH,
      fill: { color: YELLOW_20 },
    });
    slide.addText(String(d.call_to_action), {
      x: textX + textW * 0.015, y: ctaY, w: textW * 0.97, h: ctaH,
      fontFace: FONT_H, fontSize: 13, bold: true,
      color: t.titleClr, valign: 'middle',
    });
  }

  return slide;
}

// ── Image + Content Side-by-Side Slide ───────────────────────────────────
function buildImageContentSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };
  addStandardChrome(slide, d, t, 26);

  const imgSide = d.image_side === 'right' ? 'right' : 'left';
  const colGap  = CONTENT_W * 0.023;
  const colW    = (CONTENT_W - colGap) / 2;
  const imgX    = imgSide === 'left'  ? M_LEFT             : M_LEFT + colW + colGap;
  const textX   = imgSide === 'left'  ? M_LEFT + colW + colGap : M_LEFT;

  if (d.data) {
    try {
      slide.addImage({
        data: 'data:image/' + (d.format || 'png') + ';base64,' + d.data,
        x: imgX, y: BODY_Y, w: colW, h: BODY_H,
      });
    } catch (e) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: imgX, y: BODY_Y, w: colW, h: BODY_H,
        fill: { color: YELLOW_20 }, line: { color: t.border },
      });
    }
  } else {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: imgX, y: BODY_Y, w: colW, h: BODY_H,
      fill: { color: YELLOW_20 }, line: { color: YELLOW },
    });
    slide.addText(String(d.image_placeholder || 'IMAGE'), {
      x: imgX, y: BODY_Y, w: colW, h: BODY_H,
      fontFace: FONT_B, fontSize: 12, italic: true, color: t.muted,
      align: 'center', valign: 'middle',
    });
  }

  const bullets = d.bullets || [];
  if (bullets.length > 0) {
    slide.addText(bullets.map(b => ({
      text: String(b),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 8, paraSpaceAft: 8 },
    })), {
      x: textX, y: BODY_Y, w: colW, h: BODY_H,
      fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top',
    });
  } else if (d.text) {
    slide.addText(String(d.text), {
      x: textX, y: BODY_Y, w: colW, h: BODY_H,
      fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top',
    });
  }

  return slide;
}

// ── Card Grid Slide ───────────────────────────────────────────────────────
function buildCardGridSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  if (d.section_label) {
    slide.addText(String(d.section_label).toUpperCase(), {
      x: M_LEFT * 0.7, y: SLIDE_H * 0.027, w: CONTENT_W * 0.34, h: SLIDE_H * 0.047,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.muted,
    });
  }

  const headY = d.section_label ? SLIDE_H * 0.087 : SLIDE_H * 0.107;
  if (d.title) {
    slide.addText(d.title.toUpperCase(), {
      x: M_LEFT, y: headY, w: CONTENT_W, h: SLIDE_H * 0.2,
      fontFace: FONT_H, fontSize: 32, bold: true,
      color: t.titleClr, align: 'center', valign: 'middle',
    });
  }

  const subY = headY + SLIDE_H * 0.213;
  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: M_LEFT, y: subY, w: CONTENT_W, h: SLIDE_H * 0.073,
      fontFace: FONT_B, fontSize: 15, italic: true,
      color: YELLOW, align: 'center', valign: 'middle',
    });
  }

  const cards = d.cards || [];
  if (!cards.length) return slide;

  const cols  = Math.min(6, d.columns || Math.min(4, cards.length));
  const gap   = CONTENT_W * 0.013;
  const cardY = d.subtitle ? subY + SLIDE_H * 0.107 : subY + SLIDE_H * 0.027;
  const cardH = d.card_height || Math.max(SLIDE_H * 0.24, SLIDE_H - cardY - M_BOTTOM);
  const cardW = (CONTENT_W - gap * (cols + 1)) / cols;

  cards.forEach((card, idx) => {
    const col      = idx % cols;
    const row      = Math.floor(idx / cols);
    const cx       = M_LEFT + gap + col * (cardW + gap);
    const cy       = cardY + row * (cardH + SLIDE_H * 0.02);
    const raw      = (card.color || 'yellow').replace('#', '');
    const cardFill = raw === 'yellow' ? YELLOW
                   : raw === 'dark'   ? DARK_GRAY
                   : raw === 'white'  ? WHITE
                   : raw === 'gray'   ? t.cardBg : raw;
    const onYellow = cardFill === YELLOW;
    const onDark   = cardFill === DARK_GRAY;
    const cardTxt  = onYellow ? DARK_GRAY : onDark ? WHITE : t.bodyClr;
    const px       = cardW * 0.046;
    const textH    = cardH - cardH * 0.16;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cardW, h: cardH,
      fill: { color: cardFill }, line: { color: cardFill },
    });
    slide.addText(card.title || card.text || '', {
      x: cx + px, y: cy + cardH * 0.08, w: cardW - px * 2, h: textH,
      fontFace: FONT_B, fontSize: card.font_size || 14, bold: !!card.bold,
      color: cardTxt, align: 'center', valign: 'middle',
    });

    if (card.subtitle) {
      slide.addText(card.subtitle, {
        x: cx + px, y: cy + cardH - cardH * 0.13, w: cardW - px * 2, h: cardH * 0.1,
        fontFace: FONT_B, fontSize: 10,
        color: onYellow ? '555555' : YELLOW, align: 'center',
      });
    }
  });

  return slide;
}

// ── Hub-Spoke Slide ───────────────────────────────────────────────────────
function buildHubSpokeSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, t.logo);

  if (d.section_label) {
    slide.addText(String(d.section_label).toUpperCase(), {
      x: M_LEFT * 0.7, y: SLIDE_H * 0.027, w: CONTENT_W * 0.34, h: SLIDE_H * 0.047,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.muted,
    });
  }

  slide.addText((d.title || '').toUpperCase(), {
    x: M_LEFT, y: SLIDE_H * 0.087, w: CONTENT_W, h: SLIDE_H * 0.12,
    fontFace: FONT_H, fontSize: 24, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle',
  });

  // Hub rectangle: occupies middle-right third of slide
  const hubX = SLIDE_W * 0.323;
  const hubY = SLIDE_H * 0.227;
  const hubW = SLIDE_W * 0.36;
  const hubH = SLIDE_H - hubY - M_BOTTOM * 2;
  const hub  = d.hub || {};
  const rawHubClr = (hub.color || 'yellow').replace('#', '');
  const hubFill   = rawHubClr === 'yellow' ? YELLOW : rawHubClr;
  const hubTxt    = hubFill === YELLOW ? DARK_GRAY : WHITE;

  slide.addShape(pres.shapes.RECTANGLE, {
    x: hubX, y: hubY, w: hubW, h: hubH,
    fill: { color: hubFill }, line: { color: hubFill },
  });

  const hubLabel = hub.label || hub.title || '';
  const hubLblH  = SLIDE_H * 0.067;
  const hubLblPad = hubW * 0.031;
  if (hubLabel) {
    slide.addText(hubLabel.toUpperCase(), {
      x: hubX + hubLblPad, y: hubY + hubLblPad, w: hubW - hubLblPad * 2, h: hubLblH,
      fontFace: FONT_H, fontSize: 13, bold: true,
      color: hubTxt, align: 'center',
    });
  }

  const hubItems = hub.items || [];
  if (hubItems.length > 0) {
    const hubBodyY = hubY + (hubLabel ? hubLblH + hubLblPad : hubLblPad);
    const hubBodyH = hubH - (hubLabel ? hubLblH + hubLblPad * 2 : hubLblPad * 2);
    slide.addText(hubItems.map(it => ({ text: String(it), options: { paraSpaceBef: 4, paraSpaceAft: 4 } })), {
      x: hubX + hubLblPad, y: hubBodyY, w: hubW - hubLblPad * 2, h: hubBodyH,
      fontFace: FONT_B, fontSize: 12.5,
      color: hubTxt, align: 'center', valign: 'middle',
    });
  }

  // Spokes — left and right boxes
  const spokes = d.spokes || [];
  const spokeBoxW  = hubX - M_LEFT - SLIDE_W * 0.015;
  const leftX      = M_LEFT;
  const rightX     = hubX + hubW + SLIDE_W * 0.015;
  const rightBoxW  = SLIDE_W - rightX - M_RIGHT;
  const slots      = { left: [], right: [] };

  spokes.forEach(s => {
    const side = (s.side || 'left').toLowerCase();
    slots[side] = slots[side] || [];
    slots[side].push(s);
  });

  ['left', 'right'].forEach(side => {
    const list = slots[side] || [];
    if (!list.length) return;
    const bxW   = side === 'left' ? spokeBoxW : rightBoxW;
    const bxX   = side === 'left' ? leftX : rightX;
    const gapFrac = SLIDE_H * 0.024;
    const bH    = (hubH - gapFrac * (list.length - 1)) / list.length;
    const lblH  = SLIDE_H * 0.056;
    const lblPad = bxW * 0.04;

    list.forEach((spoke, ri) => {
      const by    = hubY + ri * (bH + gapFrac);
      const label = spoke.label || spoke.title || '';
      const items = spoke.items || [];

      slide.addShape(pres.shapes.RECTANGLE, {
        x: bxX, y: by, w: bxW, h: bH,
        fill: { color: t.cardBg }, line: { color: t.border },
      });

      if (label) {
        slide.addText(label.toUpperCase(), {
          x: bxX + lblPad, y: by + lblPad * 0.5, w: bxW - lblPad * 2, h: lblH,
          fontFace: FONT_H, fontSize: 12, bold: true,
          color: t.dark ? YELLOW : t.titleClr, align: 'center',
        });
      }

      if (items.length > 0) {
        const itemsY = by + (label ? lblH + lblPad : lblPad * 0.5);
        const itemsH = bH - (label ? lblH + lblPad * 1.5 : lblPad);
        slide.addText(items.join('\n'), {
          x: bxX + lblPad, y: itemsY, w: bxW - lblPad * 2, h: itemsH,
          fontFace: FONT_B, fontSize: 12, color: t.muted,
          align: 'center', valign: 'middle',
        });
      }

      // Connector arrow line
      const arY    = by + bH / 2 - SLIDE_H * 0.003;
      const connX  = side === 'left' ? bxX + bxW  : hubX;
      const connW  = side === 'left' ? hubX - bxX - bxW - SLIDE_W * 0.015
                                     : bxX - hubX - hubW - SLIDE_W * 0.015;
      slide.addShape(pres.shapes.RECTANGLE, {
        x: connX, y: arY, w: Math.abs(connW), h: SLIDE_H * 0.005,
        fill: { color: t.border },
      });
      slide.addText(side === 'left' ? '▶' : '◀', {
        x: side === 'left' ? hubX - SLIDE_W * 0.021 : bxX - SLIDE_W * 0.004,
        y: arY - SLIDE_H * 0.019, w: SLIDE_W * 0.021, h: SLIDE_H * 0.037,
        fontFace: FONT_B, fontSize: 11, color: t.border, align: 'center',
      });
    });
  });

  return slide;
}

// ── Agenda Slide ──────────────────────────────────────────────────────────
// (Renders a numbered card grid: one card per agenda item.)
function buildAgendaSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: DARK_GRAY };

  // Header banner
  const bannerH = SLIDE_H * 0.2;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: SLIDE_W * 0.553, h: bannerH,
    fill: { color: DARK_GRAY },
  });
  slide.addText((d.title || 'AGENDA').toUpperCase(), {
    x: M_LEFT, y: 0, w: CONTENT_W * 0.553, h: bannerH * 0.67,
    fontFace: FONT_H, fontSize: 36, bold: true,
    color: YELLOW, valign: 'bottom',
  });
  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: M_LEFT, y: bannerH * 0.67, w: CONTENT_W * 0.553, h: bannerH * 0.33,
      fontFace: FONT_B, fontSize: 13, color: GRAY_60, valign: 'top',
    });
  }

  addLogo(slide, LOGO_X, LOGO_Y, LOGO_MAX_W, LOGO_MAX_H, 'yellow');

  const items = d.items || [];
  const cols  = d.columns || Math.min(3, Math.max(1, Math.ceil(items.length / 2)));
  const rows  = Math.ceil(items.length / cols);
  const gap   = CONTENT_W * 0.015;
  const cardW = (CONTENT_W - gap * (cols - 1)) / cols;
  const cardY = bannerH + SLIDE_H * 0.027;
  const cardH = (SLIDE_H - cardY - M_BOTTOM - gap * (rows - 1)) / rows;
  const numH  = cardH * 0.28;
  const bodyH = cardH - numH - cardH * 0.067;

  items.forEach((item, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const cx  = M_LEFT + col * (cardW + gap);
    const cy  = cardY + row * (cardH + gap);
    const num = String(idx + 1).padStart(2, '0');

    // Number badge
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cardW, h: numH,
      fill: { color: YELLOW },
    });
    slide.addText(num, {
      x: cx, y: cy, w: cardW, h: numH,
      fontFace: FONT_H, fontSize: 18, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle',
    });

    // Body card
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy + numH, w: cardW, h: cardH - numH,
      fill: { color: '2A2A2A' }, line: { color: '2A2A2A' },
    });

    const titleItem = item.title || item.label || String(item);
    slide.addText(titleItem, {
      x: cx + cardW * 0.05, y: cy + numH + cardH * 0.04,
      w: cardW * 0.9, h: bodyH * 0.45,
      fontFace: FONT_H, fontSize: 13, bold: true,
      color: WHITE, align: 'center', valign: 'middle',
    });

    if (item.description) {
      slide.addText(String(item.description), {
        x: cx + cardW * 0.05, y: cy + numH + cardH * 0.04 + bodyH * 0.45,
        w: cardW * 0.9, h: bodyH * 0.55,
        fontFace: FONT_B, fontSize: 11, color: GRAY_60,
        align: 'center', valign: 'top',
      });
    }
  });

  return slide;
}

// ═══════════════════════════════════════════════════════════════════════════
// ROUTER — dispatch each slide spec to its builder
// ═══════════════════════════════════════════════════════════════════════════
for (const s of (spec.slides || [])) {
  try {
    switch (s.type) {
      case 'title':             buildTitleSlide(s);            break;
      case 'content':           buildContentSlide(s);          break;
      case 'two_column':        buildTwoColumnSlide(s);        break;
      case 'three_column':      buildThreeColumnSlide(s);      break;
      case 'metrics':           buildMetricsSlide(s);          break;
      case 'process':           buildProcessSlide(s);          break;
      case 'quote':             buildQuoteSlide(s);            break;
      case 'section_divider':   buildSectionDividerSlide(s);   break;
      case 'cta':               buildCtaSlide(s);              break;
      case 'image':             buildImageSlide(s);            break;
      case 'table':             buildTableSlide(s);            break;
      case 'chart':             buildChartSlide(s);            break;
      case 'timeline':          buildTimelineSlide(s);         break;
      case 'matrix_2x2':        buildMatrix2x2Slide(s);        break;
      case 'scorecard':         buildScorecardSlide(s);        break;
      case 'comparison':        buildComparisonSlide(s);       break;
      case 'icon_grid':         buildIconGridSlide(s);         break;
      case 'executive_summary': buildExecutiveSummarySlide(s); break;
      case 'image_content':     buildImageContentSlide(s);     break;
      case 'card_grid':         buildCardGridSlide(s);         break;
      case 'hub_spoke':         buildHubSpokeSlide(s);         break;
      case 'agenda':            buildAgendaSlide(s);           break;
      default:                  buildContentSlide(s);          break;
    }
  } catch (err) {
    process.stderr.write('WARN: slide[' + s.type + '] error: ' + err.message + '\n');
  }
}

// ── Write output ──────────────────────────────────────────────────────────
const outName = spec.filename || 'output.pptx';
pres.writeFile({ fileName: outName })
  .then(() => {
    process.stdout.write('SUCCESS:' + outName + '\n');
  })
  .catch(err => {
    process.stderr.write('ERROR:' + err.message + '\n');
    process.exit(1);
  });
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
# Embedded Node.js freestyle wrapper
# ─────────────────────────────────────────────────────────────────────────────
_FREESTYLE_WRAPPER = r"""
'use strict';
const fs      = require('fs');
const path    = require('path');
const pptxgen = require('pptxgenjs');

// ═══════════════════════════════════════════════════════════════════════════
// SLIDE CANVAS  —  LAYOUT_WIDE  (PptxGenJS built-in, 13.333" × 7.5")
// https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/
// ═══════════════════════════════════════════════════════════════════════════
const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

// Derived layout helpers (all math relative to SLIDE_W / SLIDE_H)
const M_LEFT    = SLIDE_W * 0.0375;
const M_RIGHT   = SLIDE_W * 0.0375;
const M_TOP     = SLIDE_H * 0.04;
const M_BOTTOM  = SLIDE_H * 0.04;
const CONTENT_W = SLIDE_W - M_LEFT - M_RIGHT;
const CONTENT_H = SLIDE_H - M_TOP  - M_BOTTOM;

// ── Brand palette ──────────────────────────────────────────────────────────
const YELLOW    = 'FEC00F';
const DARK_GRAY = '212121';
const WHITE     = 'FFFFFF';
const GRAY_60   = '999999';
const GRAY_20   = 'DDDDDD';
const YELLOW_20 = 'FEF7D8';
const GREEN     = '22C55E';
const RED       = 'EB2F5C';

// ── Brand fonts ────────────────────────────────────────────────────────────
const FONT_H = 'Rajdhani';
const FONT_B = 'Quicksand';

// ── Logos ──────────────────────────────────────────────────────────────────
const assetsDir = path.join(__dirname, 'assets');
function loadLogoData(name) {
  const p = path.join(assetsDir, name);
  if (fs.existsSync(p)) return 'data:image/png;base64,' + fs.readFileSync(p).toString('base64');
  return null;
}
const LOGOS = {
  full:   loadLogoData('potomac-full-logo.png'),
  black:  loadLogoData('potomac-icon-black.png'),
  yellow: loadLogoData('potomac-icon-yellow.png'),
};

// Logo aspect-ratio constants
const LOGO_DIMS = {
  full:   { aspect: 3.6 },
  black:  { aspect: 1.0 },
  yellow: { aspect: 1.0 },
};

function fitDims(aspect, maxW, maxH) {
  if (maxW / maxH > aspect) { const h = maxH; return { w: h * aspect, h }; }
  const w = maxW; return { w, h: w / aspect };
}

// Place a logo centered inside a bounding box, preserving aspect ratio.
function addLogo(slide, bx, by, bw, bh, variant) {
  const data = variant === 'black'  ? LOGOS.black
             : variant === 'yellow' ? LOGOS.yellow
             :                        LOGOS.full;
  const asp  = (LOGO_DIMS[variant] || LOGO_DIMS.full).aspect;
  if (data) {
    const { w, h } = fitDims(asp, bw, bh);
    slide.addImage({ data, x: bx + (bw - w) / 2, y: by + (bh - h) / 2, w, h });
  } else {
    slide.addText('POTOMAC', { x: bx, y: by, w: bw, h: bh, fontFace: FONT_H, fontSize: 14, bold: true, color: DARK_GRAY, align: 'center', valign: 'middle' });
  }
}

// ── Presentation ───────────────────────────────────────────────────────────
const pres = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = __PRES_TITLE__;

// LAYOUT_WIDE is a PptxGenJS built-in preset — no defineLayout() needed.
// https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/
pres.layout = 'LAYOUT_WIDE';

// ═══════════════════════════════════════════════════════════════════════════
// LLM FREESTYLE CODE
// Available: pres, SLIDE_W, SLIDE_H, M_LEFT, M_RIGHT, M_TOP, M_BOTTOM,
//            CONTENT_W, CONTENT_H, YELLOW, DARK_GRAY, WHITE, GRAY_60,
//            GRAY_20, YELLOW_20, GREEN, RED, FONT_H, FONT_B, LOGOS, addLogo()
// Canvas: 13.333" wide × 7.5" tall  (LAYOUT_WIDE, standard 16:9 widescreen)
// ═══════════════════════════════════════════════════════════════════════════

__LLM_CODE__

// ═══════════════════════════════════════════════════════════════════════════
// END OF LLM CODE
// ═══════════════════════════════════════════════════════════════════════════

// ── Write output ───────────────────────────────────────────────────────────
const __outFile__ = __OUTPUT_FILENAME__;
pres.writeFile({ fileName: __outFile__ })
  .then(() => { process.stdout.write('SUCCESS:' + __outFile__ + '\n'); })
  .catch(err => { process.stderr.write('ERROR:' + err.message + '\n'); process.exit(1); });
""".strip()


# ── Result dataclass ──────────────────────────────────────────────────────────
class PptxResult:
    """Lightweight result container from PptxSandbox.generate()."""
    __slots__ = ("success", "data", "filename", "error", "exec_time_ms")

    def __init__(
        self,
        success: bool,
        data: Optional[bytes] = None,
        filename: Optional[str] = None,
        error: Optional[str] = None,
        exec_time_ms: float = 0.0,
    ):
        self.success      = success
        self.data         = data
        self.filename     = filename
        self.error        = error
        self.exec_time_ms = exec_time_ms


# ── Module-level npm cache helper ─────────────────────────────────────────────
def _ensure_pptx_modules() -> Optional[Path]:
    """
    Ensure the ``pptxgenjs`` npm package is installed in the persistent cache dir.
    Returns the path to node_modules on success, or None on failure.
    """
    modules  = _PPTX_CACHE_DIR / "node_modules"
    pptx_pkg = modules / "pptxgenjs"

    if pptx_pkg.exists():
        logger.debug("pptxgenjs node_modules cache hit: %s", modules)
        return modules

    logger.info("First-time pptxgenjs install")
    _PPTX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pkg = {"name": "pptx-cache", "version": "1.0.0", "dependencies": {"pptxgenjs": "^3.12.0"}}
    (_PPTX_CACHE_DIR / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    proc = subprocess.run(
        ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
        cwd=str(_PPTX_CACHE_DIR),
        capture_output=True,
        timeout=240,
    )
    if proc.returncode != 0:
        logger.error(
            "npm install (pptxgenjs) failed (rc=%d): %s",
            proc.returncode, proc.stderr.decode(errors="replace").strip(),
        )
        return None

    logger.info("pptxgenjs package installed → %s", modules)
    return modules


# ── Image slide resolver ──────────────────────────────────────────────────────
def _resolve_image_slides(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Walk ``spec.slides`` and resolve ``{"type": "image", "file_id": "<uuid>"}``
    items to ``{"type": "image", "data": "<base64>", "format": "<ext>"}``.
    """
    import base64
    import copy

    spec   = copy.deepcopy(spec)
    slides = spec.get("slides", [])
    if not slides:
        return spec

    needs_resolve = any(
        s.get("type") == "image" and "file_id" in s and "data" not in s
        for s in slides
    )
    if not needs_resolve:
        return spec

    try:
        from core.file_store import get_file
    except ImportError:
        logger.warning("file_store unavailable — image slides with file_id will be skipped")
        return spec

    for slide in slides:
        if slide.get("type") != "image":
            continue
        if "data" in slide:
            continue
        file_id = slide.get("file_id", "").strip()
        if not file_id:
            continue

        try:
            entry = get_file(file_id)
            if entry and entry.data:
                slide["data"]   = base64.b64encode(entry.data).decode("ascii")
                slide["format"] = entry.file_type or (
                    entry.filename.rsplit(".", 1)[-1].lower() if "." in entry.filename else "png"
                )
                logger.info(
                    "Resolved image file_id %s → %s (%.1f KB)",
                    file_id, entry.filename, entry.size_kb,
                )
            else:
                logger.warning("Image file_id %s not found in file_store — slide skipped", file_id)
        except Exception as exc:
            logger.warning("Could not resolve image file_id %s: %s", file_id, exc)

    spec["slides"] = slides
    return spec


# ── PptxSandbox ───────────────────────────────────────────────────────────────
class PptxSandbox:
    """
    Generates Potomac-branded .pptx files from a structured spec dict.

    All slides are rendered using LAYOUT_WIDE (13.333" × 7.5", standard 16:9).
    See: https://gitbrent.github.io/PptxGenJS/docs/usage-pres-options/

    The spec describes all slides; no code generation by the LLM is required.
    """

    def generate(self, spec: Dict[str, Any], timeout: int = 120) -> PptxResult:
        """
        Generate a ``.pptx`` file from *spec*.

        Parameters
        ----------
        spec : dict
            Presentation specification. Required keys: ``title``, ``slides``.
        timeout : int
            Maximum seconds allowed for Node.js execution (default 120).

        Returns
        -------
        PptxResult
        """
        start    = time.time()
        temp_dir: Optional[Path] = None

        try:
            # ── 0. Resolve image file_id → base64 ─────────────────────────
            spec = _resolve_image_slides(spec)

            # ── 1. npm cache ───────────────────────────────────────────────
            modules_path = _ensure_pptx_modules()
            if modules_path is None:
                return PptxResult(False, error="pptxgenjs npm package unavailable")

            # ── 2. Isolated temp workspace ─────────────────────────────────
            temp_dir    = Path(tempfile.mkdtemp(prefix="pptx_gen_"))
            assets_temp = temp_dir / "assets"
            assets_temp.mkdir()

            # ── 3. Mount Potomac logos ─────────────────────────────────────
            logos_found = 0
            for logo_file in _LOGO_FILES:
                src = _ASSETS_DIR / logo_file
                if src.exists():
                    shutil.copy2(src, assets_temp / logo_file)
                    logos_found += 1
                else:
                    logger.debug("Logo not found (skipped): %s", src)
            if logos_found == 0:
                logger.warning("No Potomac logo assets found at %s", _ASSETS_DIR)

            # ── 4. Write spec + builder ────────────────────────────────────
            (temp_dir / "spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temp_dir / "presentation_builder.js").write_text(
                _BUILDER_SCRIPT, encoding="utf-8"
            )
            (temp_dir / "package.json").write_text(
                json.dumps({"name": "pptx-gen", "version": "1.0.0"}), encoding="utf-8"
            )

            # ── 5. Symlink node_modules from cache ─────────────────────────
            nm_link = temp_dir / "node_modules"
            try:
                os.symlink(str(modules_path), str(nm_link))
            except OSError:
                logger.debug("symlink failed, falling back to copytree")
                shutil.copytree(str(modules_path), str(nm_link))

            # ── 6. Execute Node.js ─────────────────────────────────────────
            proc = subprocess.run(
                ["node", "presentation_builder.js"],
                cwd=str(temp_dir),
                capture_output=True,
                timeout=timeout,
            )

            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()

            if proc.returncode != 0:
                return PptxResult(
                    False,
                    error=f"Node.js builder failed: {stderr or stdout}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )

            # ── 7. Retrieve generated file ─────────────────────────────────
            filename = spec.get("filename") or "output.pptx"
            out_path = temp_dir / filename

            if not out_path.exists():
                pptx_files = sorted(temp_dir.glob("*.pptx"))
                if pptx_files:
                    out_path = pptx_files[0]
                    filename = out_path.name
                else:
                    return PptxResult(
                        False,
                        error=f"Output .pptx not found. stdout={stdout!r}",
                        exec_time_ms=round((time.time() - start) * 1000, 2),
                    )

            data    = out_path.read_bytes()
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "PptxSandbox ✓  %s  (%.1f KB, %.0f ms)",
                filename, len(data) / 1024, elapsed,
            )
            return PptxResult(True, data=data, filename=filename, exec_time_ms=elapsed)

        except subprocess.TimeoutExpired:
            return PptxResult(
                False,
                error=f"Node.js timed out after {timeout} s",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except FileNotFoundError:
            return PptxResult(
                False,
                error="Node.js not found — ensure node is installed",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as exc:
            logger.error("PptxSandbox error: %s", exc, exc_info=True)
            return PptxResult(
                False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def generate_freestyle(
        self,
        code: str,
        title: str = "Potomac Presentation",
        filename: str = "output.pptx",
        timeout: int = 120,
    ) -> PptxResult:
        """
        Generate a .pptx from raw pptxgenjs JavaScript code.

        The caller supplies the slide-building logic.  All brand constants,
        layout helpers, logo loader, and the ``addLogo()`` function are pre-injected
        so freestyle code can reference them directly.
        """
        import json as _json

        start    = time.time()
        temp_dir: Optional[Path] = None

        try:
            # ── 1. npm cache ────────────────────────────────────────────
            modules_path = _ensure_pptx_modules()
            if modules_path is None:
                return PptxResult(False, error="pptxgenjs npm package unavailable")

            # ── 2. Isolated temp workspace ──────────────────────────────
            temp_dir    = Path(tempfile.mkdtemp(prefix="pptx_free_"))
            assets_temp = temp_dir / "assets"
            assets_temp.mkdir()

            # ── 3. Mount Potomac logos ──────────────────────────────────
            for logo_file in _LOGO_FILES:
                src = _ASSETS_DIR / logo_file
                if src.exists():
                    shutil.copy2(src, assets_temp / logo_file)

            # ── 4. Build script ─────────────────────────────────────────
            safe_fn = filename if filename.lower().endswith(".pptx") else filename + ".pptx"
            script  = _FREESTYLE_WRAPPER
            script  = script.replace("__PRES_TITLE__",      _json.dumps(title))
            script  = script.replace("__OUTPUT_FILENAME__", _json.dumps(safe_fn))
            script  = script.replace("__LLM_CODE__",        code)

            (temp_dir / "freestyle_builder.js").write_text(script, encoding="utf-8")
            (temp_dir / "package.json").write_text(
                _json.dumps({"name": "pptx-free", "version": "1.0.0"}),
                encoding="utf-8",
            )

            # ── 5. Symlink node_modules from cache ─────────────────────
            nm_link = temp_dir / "node_modules"
            try:
                os.symlink(str(modules_path), str(nm_link))
            except OSError:
                shutil.copytree(str(modules_path), str(nm_link))

            # ── 6. Execute Node.js ─────────────────────────────────────
            proc = subprocess.run(
                ["node", "freestyle_builder.js"],
                cwd=str(temp_dir),
                capture_output=True,
                timeout=timeout,
            )

            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()

            if proc.returncode != 0:
                return PptxResult(
                    False,
                    error=f"Node.js freestyle builder failed:\n{stderr or stdout}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )

            # ── 7. Retrieve generated file ─────────────────────────────
            out_path = temp_dir / safe_fn
            if not out_path.exists():
                pptx_files = sorted(temp_dir.glob("*.pptx"))
                if pptx_files:
                    out_path = pptx_files[0]
                    safe_fn  = out_path.name
                else:
                    return PptxResult(
                        False,
                        error="Output .pptx not found",
                        exec_time_ms=round((time.time() - start) * 1000, 2),
                    )

            data    = out_path.read_bytes()
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "PptxSandbox.freestyle ✓  %s  (%.1f KB, %.0f ms)",
                safe_fn, len(data) / 1024, elapsed,
            )
            return PptxResult(True, data=data, filename=safe_fn, exec_time_ms=elapsed)

        except subprocess.TimeoutExpired:
            return PptxResult(
                False,
                error=f"Node.js timed out after {timeout} s",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except FileNotFoundError:
            return PptxResult(
                False,
                error="Node.js not found",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as exc:
            logger.error("PptxSandbox.freestyle error: %s", exc, exc_info=True)
            return PptxResult(
                False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)