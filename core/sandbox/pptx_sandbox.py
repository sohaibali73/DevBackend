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
from typing import Any, Dict, List, Optional, Tuple

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

# ── Slide Dimension Constants ─────────────────────────────────────────────────
# Standard PowerPoint 16:9 widescreen dimensions
SLIDE_WIDTH  = 13.333   # inches
SLIDE_HEIGHT = 7.5      # inches
SLIDE_LAYOUT = 'LAYOUT_WIDE'

# ── Brand Palette ─────────────────────────────────────────────────────────────
YELLOW     = 'FEC00F'
DARK_GRAY  = '212121'
WHITE      = 'FFFFFF'
GRAY_60    = '999999'
GRAY_20    = 'DDDDDD'
YELLOW_20  = 'FEF7D8'
SUCCESS_GREEN = '22C55E'
ALERT_RED   = 'EB2F5C'

# ── Brand Fonts ───────────────────────────────────────────────────────────────
FONT_H = 'Rajdhani'    # Headline font - ALWAYS ALL CAPS per Potomac brand
FONT_B = 'Quicksand'   # Body / caption font


# ── Embedded Node.js presentation builder ────────────────────────────────────
_BUILDER_SCRIPT = r"""
'use strict';
const fs      = require('fs');
const path    = require('path');
const pptxgen = require('pptxgenjs');

// ── Constants (from Python) ───────────────────────────────────────────────────
const SLIDE_W = 13.333;
const SLIDE_H = 7.5;

// ── Brand palette ─────────────────────────────────────────────────────────────
const YELLOW     = 'FEC00F';
const DARK_GRAY  = '212121';
const WHITE      = 'FFFFFF';
const GRAY_60    = '999999';
const GRAY_20    = 'DDDDDD';
const YELLOW_20  = 'FEF7D8';
const GREEN      = '22C55E';
const RED        = 'EB2F5C';

// ── Brand fonts ──────────────────────────────────────────────────────────────
const FONT_H = 'Rajdhani';
const FONT_B = 'Quicksand';

// ── Logos ─────────────────────────────────────────────────────────────────────
const assetsDir = path.join(__dirname, 'assets');
function loadLogoData(name) {
  const p = path.join(assetsDir, name);
  if (fs.existsSync(p)) {
    return 'data:image/png;base64,' + fs.readFileSync(p).toString('base64');
  }
  return null;
}
const LOGOS = {
  full:   loadLogoData('potomac-full-logo.png'),
  black:  loadLogoData('potomac-icon-black.png'),
  yellow: loadLogoData('potomac-icon-yellow.png'),
};

// ── Logo dimensions cache (pre-computed for each logo variant) ──────────────
const LOGO_DIMS = {
  // Store natural dimensions if available, otherwise use common ratios
  full:   { aspect: 3.6 },   // Full logo is wider
  black:  { aspect: 1.0 },   // Icon is square
  yellow: { aspect: 1.0 },   // Icon is square
};

// ── Logo helper - NEVER stretches logos ──────────────────────────────────────
// Calculate display dimensions that preserve aspect ratio
function getLogoDisplayDims(variant, maxW, maxH) {
  const dims = LOGO_DIMS[variant] || LOGO_DIMS.full;
  const aspect = dims.aspect;

  // Calculate the largest size that fits within maxW x maxH while preserving aspect ratio
  let w, h;
  if (maxW / maxH > aspect) {
    // Constrained by height
    h = maxH;
    w = h * aspect;
  } else {
    // Constrained by width
    w = maxW;
    h = w / aspect;
  }
  return { w, h };
}

function addLogo(slide, x, y, maxW, maxH, variant) {
  const data = variant === 'black'  ? LOGOS.black  :
               variant === 'yellow' ? LOGOS.yellow :
               LOGOS.full;
  if (data) {
    const { w, h } = getLogoDisplayDims(variant, maxW, maxH);
    // Center within the bounding box
    const xOff = x + (maxW - w) / 2;
    const yOff = y + (maxH - h) / 2;
    slide.addImage({ data, x: xOff, y: yOff, w, h });
  } else {
    slide.addText('POTOMAC', {
      x, y, maxW, maxH, fontFace: FONT_H, fontSize: 14, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle'
    });
  }
}

// ── Create presentation ─────────────────────────────────────────────────────
const spec = JSON.parse(fs.readFileSync('spec.json', 'utf8'));
const pres = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = spec.title || 'POTOMAC PRESENTATION';
pres.layout  = 'LAYOUT_WIDE';

// ── Theme helper ──────────────────────────────────────────────────────────────
function getTheme(d) {
  const dark = d.background === 'dark' || d.theme === 'dark';
  return {
    dark,
    bg:       dark ? DARK_GRAY : WHITE,
    titleClr: dark ? WHITE     : DARK_GRAY,
    bodyClr:  dark ? 'CCCCCC'  : DARK_GRAY,
    muted:    dark ? '888888'  : GRAY_60,
    cardBg:   dark ? '323232'  : 'F0F0F0',
    border:   dark ? '505050'  : GRAY_20,
    logo:     dark ? 'yellow'  : 'full',
  };
}

// ── Layout constants (flexible grid system) ──────────────────────────────────
const MARGIN = { left: 0.5, right: 0.5, top: 0.3, bottom: 0.3 };
const LOGO_AREA = { x: 11.5, y: 0.15, w: 1.5, h: 0.6 };
const CONTENT_W = SLIDE_W - MARGIN.left - MARGIN.right;
const TITLE_AREA_H = 0.9;
const TITLE_UNDERLINE_H = 0.06;

// ── Slide builders ────────────────────────────────────────────────────────────

// Title Slide
function buildTitleSlide(d) {
  const slide  = pres.addSlide();
  const isExec = (d.style === 'executive');
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  // Logo with proper aspect ratio preservation
  const logoBox = { x: 5.77, y: 0.45, w: 1.8, h: 1.5 };
  addLogo(slide, logoBox.x, logoBox.y, logoBox.w, logoBox.h, isExec ? 'yellow' : 'full');

  // Title
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: 2.4, w: CONTENT_W, h: 1.5,
    fontFace: FONT_H, fontSize: 44, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle'
  });

  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: MARGIN.left, y: 4.1, w: CONTENT_W, h: 0.9,
      fontFace: FONT_B, fontSize: 20, italic: isExec,
      color: isExec ? YELLOW : GRAY_60, align: 'center', valign: 'middle'
    });
  }

  // Accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.5, w: CONTENT_W, h: 0.08, fill: { color: YELLOW }
  });

  const tagline = d.tagline || (isExec ? 'Built to Conquer Risk' : null);
  if (tagline) {
    slide.addText(tagline, {
      x: MARGIN.left, y: 5.8, w: CONTENT_W, h: 0.5,
      fontFace: FONT_B, fontSize: 15, italic: true,
      color: YELLOW, align: 'center', valign: 'middle'
    });
  }
  return slide;
}

// Content Slide with bullets
function buildContentSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  // Logo
  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  // Title
  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 30, bold: true,
    color: t.titleClr, valign: 'middle'
  });

  // Title underline
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.2;
  const contentH = SLIDE_H - contentY - MARGIN.bottom;
  const bullets = d.bullets || (Array.isArray(d.content) ? d.content : null);
  const text    = d.text   || (!Array.isArray(d.content) ? d.content : null);

  if (bullets && bullets.length > 0) {
    const items = bullets.map(b => ({
      text: String(b),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 6, paraSpaceAft: 6 }
    }));
    slide.addText(items, {
      x: MARGIN.left, y: contentY, w: CONTENT_W, h: contentH,
      fontFace: FONT_B, fontSize: 18, color: t.bodyClr, valign: 'top'
    });
  } else if (text) {
    slide.addText(String(text), {
      x: MARGIN.left, y: contentY, w: CONTENT_W, h: contentH,
      fontFace: FONT_B, fontSize: 16, color: t.bodyClr, valign: 'top'
    });
  }
  return slide;
}

// Two Column Slide
function buildTwoColumnSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const gap     = 0.6;
  const colW    = (CONTENT_W - gap) / 2;
  const lX      = MARGIN.left;
  const rX      = lX + colW + gap;
  const hasHdrs = d.left_header || d.right_header;
  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.25;

  if (d.left_header) {
    slide.addText(String(d.left_header), {
      x: lX, y: contentY, w: colW, h: 0.42,
      fontFace: FONT_H, fontSize: 14, bold: true, color: YELLOW, valign: 'middle'
    });
  }
  if (d.right_header) {
    slide.addText(String(d.right_header), {
      x: rX, y: contentY, w: colW, h: 0.42,
      fontFace: FONT_H, fontSize: 14, bold: true, color: YELLOW, valign: 'middle'
    });
  }

  const cy = hasHdrs ? contentY + 0.55 : contentY;
  const ch = SLIDE_H - cy - MARGIN.bottom;
  const lT = d.left_content  || (d.columns && d.columns[0]) || '';
  const rT = d.right_content || (d.columns && d.columns[1]) || '';

  slide.addText(String(lT), {
    x: lX, y: cy, w: colW, h: ch, fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top'
  });

  // Divider
  slide.addShape(pres.shapes.RECTANGLE, {
    x: lX + colW + gap / 2 - 0.02, y: contentY - 0.2, w: 0.04, h: ch + 0.2, fill: { color: GRAY_20 }
  });

  slide.addText(String(rT), {
    x: rX, y: cy, w: colW, h: ch, fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top'
  });
  return slide;
}

// Three Column Slide
function buildThreeColumnSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 24, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const columns = d.columns || [];
  const headers = d.column_headers || [];
  const gap     = 0.25;
  const colW    = (CONTENT_W - gap * 2) / 3;
  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.25;

  for (let i = 0; i < 3; i++) {
    const xPos = MARGIN.left + i * (colW + gap);
    if (headers[i]) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: xPos, y: contentY, w: colW, h: 0.45, fill: { color: YELLOW }
      });
      slide.addText(String(headers[i]), {
        x: xPos, y: contentY, w: colW, h: 0.45,
        fontFace: FONT_H, fontSize: 13, bold: true,
        color: DARK_GRAY, align: 'center', valign: 'middle'
      });
    }
    const cY = headers[i] ? contentY + 0.55 : contentY;
    const cH = SLIDE_H - cY - MARGIN.bottom;
    slide.addText(String(columns[i] || ''), {
      x: xPos, y: cY, w: colW, h: cH,
      fontFace: FONT_B, fontSize: 13, color: t.bodyClr, valign: 'top'
    });
  }
  return slide;
}

// Metrics / KPI Slide
function buildMetricsSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 28, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const metrics = d.metrics || [];
  const perRow  = Math.min(3, Math.max(1, metrics.length));
  const mW      = CONTENT_W / perRow;
  const startY  = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.7;
  const mH      = SLIDE_H - startY - MARGIN.bottom;

  metrics.forEach((m, i) => {
    const row  = Math.floor(i / perRow);
    const col  = i % perRow;
    const xPos = MARGIN.left + col * mW + 0.1;
    const yPos = startY + row * (mH / Math.ceil(metrics.length / perRow));

    slide.addText(String(m.value || ''), {
      x: xPos, y: yPos, w: mW - 0.2, h: mH * 0.55,
      fontFace: FONT_H, fontSize: 48, bold: true,
      color: YELLOW, align: 'center', valign: 'middle'
    });
    slide.addText(String(m.label || ''), {
      x: xPos, y: yPos + mH * 0.55, w: mW - 0.2, h: mH * 0.45,
      fontFace: FONT_B, fontSize: 14, color: t.muted, align: 'center'
    });
  });

  if (d.context) {
    slide.addText(String(d.context), {
      x: MARGIN.left, y: SLIDE_H - 0.8, w: CONTENT_W, h: 0.5,
      fontFace: FONT_B, fontSize: 11, italic: true, color: t.muted, align: 'center'
    });
  }
  return slide;
}

// Process / Steps Slide
function buildProcessSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const steps = d.steps || [];
  const n     = Math.max(1, steps.length);
  const stepW = CONTENT_W / n;
  const r     = 0.3;
  const cy    = 2.5;

  steps.forEach((step, i) => {
    const xPos = MARGIN.left + i * stepW;
    const cx   = xPos + stepW / 2 - r;

    slide.addShape(pres.shapes.ELLIPSE, {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fill: { color: YELLOW }, line: { color: YELLOW }
    });
    slide.addText(String(i + 1), {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fontFace: FONT_H, fontSize: 16, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle'
    });

    if (i < steps.length - 1) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: cx + r * 2, y: cy + r - 0.02,
        w: stepW - r * 2, h: 0.04, fill: { color: GRAY_20 }
      });
    }

    slide.addText(String(step.title || '').toUpperCase(), {
      x: xPos, y: cy + r * 2 + 0.15, w: stepW - 0.05, h: 0.6,
      fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center'
    });
    slide.addText(String(step.description || ''), {
      x: xPos, y: cy + r * 2 + 0.82, w: stepW - 0.05, h: 2.8,
      fontFace: FONT_B, fontSize: 11, color: t.muted, align: 'center', valign: 'top'
    });
  });
  return slide;
}

// Quote Slide
function buildQuoteSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: YELLOW_20 };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, 'full');

  slide.addText('"', {
    x: 0.4, y: 1.1, w: 1.2, h: 1.4,
    fontFace: FONT_H, fontSize: 96, bold: true,
    color: YELLOW, align: 'center', valign: 'middle'
  });
  slide.addText(String(d.quote || ''), {
    x: 1.4, y: 1.8, w: CONTENT_W + 0.1, h: 3.0,
    fontFace: FONT_B, fontSize: 22, italic: true,
    color: DARK_GRAY, align: 'center', valign: 'middle'
  });
  if (d.attribution) {
    slide.addText('— ' + String(d.attribution), {
      x: 1.4, y: 5.0, w: CONTENT_W + 0.1, h: 0.7,
      fontFace: FONT_H, fontSize: 16, bold: true, color: GRAY_60, align: 'center'
    });
  }
  if (d.context) {
    slide.addText(String(d.context), {
      x: 1.4, y: 5.8, w: CONTENT_W + 0.1, h: 0.5,
      fontFace: FONT_B, fontSize: 12, italic: true, color: GRAY_60, align: 'center'
    });
  }
  return slide;
}

// Section Divider Slide
function buildSectionDividerSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.45, h: SLIDE_H, fill: { color: YELLOW }
  });
  slide.addText((d.title || '').toUpperCase(), {
    x: 0.8, y: 2.4, w: CONTENT_W - 0.3, h: 1.6,
    fontFace: FONT_H, fontSize: 42, bold: true, color: t.titleClr, valign: 'middle'
  });
  if (d.description) {
    slide.addText(String(d.description), {
      x: 0.8, y: 4.2, w: CONTENT_W - 0.3, h: 1.5,
      fontFace: FONT_B, fontSize: 18, color: t.muted, valign: 'middle'
    });
  }
  return slide;
}

// CTA / Call to Action Slide
function buildCtaSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  const logoBox = { x: 5.77, y: 0.4, w: 1.8, h: 1.0 };
  addLogo(slide, logoBox.x, logoBox.y, logoBox.w, logoBox.h, 'full');

  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: 1.8, w: CONTENT_W, h: 1.0,
    fontFace: FONT_H, fontSize: 34, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle'
  });
  if (d.action_text) {
    slide.addText(String(d.action_text), {
      x: MARGIN.left, y: 3.0, w: CONTENT_W, h: 1.5,
      fontFace: FONT_B, fontSize: 18, color: t.bodyClr, align: 'center', valign: 'middle'
    });
  }

  // Button
  const btnW = 3.0, btnH = 0.7;
  const btnX = MARGIN.left + (CONTENT_W - btnW) / 2;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: btnX, y: 4.8, w: btnW, h: btnH,
    fill: { color: YELLOW }, line: { color: YELLOW }
  });
  slide.addText((d.button_text || 'GET STARTED').toUpperCase(), {
    x: btnX, y: 4.8, w: btnW, h: btnH,
    fontFace: FONT_H, fontSize: 15, bold: true,
    color: DARK_GRAY, align: 'center', valign: 'middle'
  });

  slide.addText('Built to Conquer Risk', {
    x: MARGIN.left, y: 5.7, w: CONTENT_W, h: 0.5,
    fontFace: FONT_B, fontSize: 14, italic: true, color: YELLOW, align: 'center'
  });
  if (d.contact_info) {
    slide.addText(String(d.contact_info), {
      x: MARGIN.left, y: 6.3, w: CONTENT_W, h: 0.8,
      fontFace: FONT_B, fontSize: 12, color: t.muted, align: 'center'
    });
  }
  return slide;
}

// Image Slide
function buildImageSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  if (d.title) {
    const titleY = MARGIN.top + 0.1;
    slide.addText(d.title.toUpperCase(), {
      x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
      fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
    });
  }

  if (!d.data) return slide;

  try {
    const imgData = 'data:image/' + (d.format || 'png') + ';base64,' + d.data;
    const w    = d.width  || 6;
    const h    = d.height || w * 0.667;
    const xOff = d.align === 'center' ? (SLIDE_W - w) / 2 :
                 d.align === 'right'  ? SLIDE_W - w - 0.5 : MARGIN.left;
    const yOff = d.title ? 1.8 : 1.5;
    slide.addImage({ data: imgData, x: xOff, y: yOff, w, h });
    if (d.caption) {
      slide.addText(String(d.caption), {
        x: MARGIN.left, y: yOff + h + 0.15, w: CONTENT_W, h: 0.45,
        fontFace: FONT_B, fontSize: 12, italic: true, color: t.muted,
        align: d.align === 'center' ? 'center' : 'left'
      });
    }
  } catch (e) {
    process.stderr.write('WARN: image slide error: ' + e.message + '\n');
  }
  return slide;
}

// Table Slide
function buildTableSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const headers = d.headers || [];
  const rows    = d.rows    || [];
  const tableRows = [];

  if (headers.length > 0) {
    tableRows.push(headers.map(h => ({
      text: String(h).toUpperCase(),
      options: {
        bold: true, color: DARK_GRAY, fill: { color: YELLOW },
        align: 'center', valign: 'middle', fontSize: 11, fontFace: FONT_H,
        border: { type: 'solid', color: DARK_GRAY, pt: 0.5 }
      }
    })));
  }
  rows.forEach((row, ri) => {
    const isAlt = ri % 2 === 1;
    const bg    = isAlt ? 'F5F5F5' : WHITE;
    tableRows.push((Array.isArray(row) ? row : [row]).map((cell, ci) => {
      const isNum = d.number_cols && d.number_cols.includes(ci + 1);
      return {
        text: String(cell === null || cell === undefined ? '' : cell),
        options: {
          color: t.bodyClr, fill: { color: bg },
          align: isNum ? 'center' : 'left', fontSize: 11, fontFace: FONT_B,
          border: { type: 'solid', color: GRAY_20, pt: 0.5 }
        }
      };
    }));
  });
  if (d.totals_row) {
    const tRow = d.totals_row;
    const cells = tRow.values ? [tRow.label, ...tRow.values] : [tRow.label || 'TOTAL'];
    tableRows.push(cells.map(c => ({
      text: String(c || ''),
      options: {
        bold: true, color: t.titleClr, fill: { color: YELLOW_20 },
        align: 'center', fontSize: 11, fontFace: FONT_H,
        border: { type: 'solid', color: DARK_GRAY, pt: 0.5 }
      }
    })));
  }

  if (tableRows.length > 0) {
    const numCols = Math.max(...tableRows.map(r => r.length));
    const colW    = CONTENT_W / Math.max(numCols, 1);
    const tableY  = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.2;
    const tableH  = SLIDE_H - tableY - 0.5;
    slide.addTable(tableRows, {
      x: MARGIN.left, y: tableY, w: CONTENT_W,
      colW: Array(numCols).fill(colW),
      rowH: Math.min(0.42, tableH / tableRows.length)
    });
  }
  if (d.caption) {
    slide.addText(String(d.caption), {
      x: MARGIN.left, y: SLIDE_H - 0.6, w: CONTENT_W, h: 0.4,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted
    });
  }
  return slide;
}

// Chart Slide
function buildChartSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const chartType  = (d.chart_type || 'bar').toLowerCase();
  const categories = d.categories || d.labels || [];
  const values     = d.values     || [];
  const seriesData = d.series     || [];

  const chartX = MARGIN.left;
  const chartY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.2;
  const chartH = SLIDE_H - chartY - 0.6;
  const chartW = CONTENT_W;

  if (chartType === 'waterfall') {
    const n      = categories.length;
    const maxVal = Math.max(...values.map(Math.abs)) * 1.3 || 100;
    let running  = 0;
    const baseY  = chartY + chartH;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: chartX, y: baseY, w: chartW, h: 0.025, fill: { color: DARK_GRAY }
    });
    categories.forEach((cat, i) => {
      const val    = values[i] || 0;
      const barW   = chartW / (n * 1.5);
      const barH   = Math.abs(val) / maxVal * chartH * 0.85;
      const isStart = i === 0, isEnd = i === n - 1;
      const color  = isStart || isEnd ? YELLOW : (val >= 0 ? GREEN : RED);
      const barX   = chartX + i * (chartW / n) + (chartW / n - barW) / 2;
      const barY   = val >= 0 ? baseY - ((running + val) / maxVal) * chartH * 0.85
                              : baseY - (running / maxVal) * chartH * 0.85;
      slide.addShape(pres.shapes.RECTANGLE, {
        x: barX, y: barY, w: barW, h: barH,
        fill: { color }, line: { color: WHITE, pt: 1 }
      });
      const valStr = (val >= 0 && !isStart ? '+' : '') + val;
      slide.addText(String(valStr), {
        x: barX, y: barY - 0.32, w: barW, h: 0.3,
        fontFace: FONT_B, fontSize: 10, bold: true, color: t.titleClr, align: 'center'
      });
      slide.addText(String(cat), {
        x: barX - 0.1, y: baseY + 0.05, w: barW + 0.2, h: 0.4,
        fontFace: FONT_B, fontSize: 9, color: t.titleClr, align: 'center'
      });
      if (i > 0 && i < n - 1) running += val;
    });
  } else {
    let pptxChartType;
    const chartOpts = {
      x: chartX, y: chartY, w: chartW, h: chartH,
      chartColors: [YELLOW, DARK_GRAY, GRAY_60, RED, GREEN],
      showLegend: seriesData.length > 1, legendPos: 'b', legendFontSize: 10,
      dataLabelFontSize: 10, dataLabelColor: t.titleClr,
    };
    switch (chartType) {
      case 'line':          pptxChartType = pres.charts.LINE;      break;
      case 'pie':           pptxChartType = pres.charts.PIE;       chartOpts.showLegend = true; break;
      case 'donut':         pptxChartType = pres.charts.DOUGHNUT;  chartOpts.showLegend = true; break;
      case 'scatter':       pptxChartType = pres.charts.SCATTER;   break;
      case 'area':          pptxChartType = pres.charts.AREA;      break;
      case 'stacked_bar':   pptxChartType = pres.charts.BAR;       chartOpts.barGrouping = 'stacked'; break;
      case 'clustered_bar': pptxChartType = pres.charts.BAR;       chartOpts.barGrouping = 'clustered'; break;
      default:              pptxChartType = pres.charts.BAR;       break;
    }
    const chartData = seriesData.length > 0
      ? seriesData.map(s => ({ name: s.name || '', labels: categories, values: s.values || [] }))
      : [{ name: d.y_axis_label || 'Value', labels: categories, values }];
    slide.addChart(pptxChartType, chartData, chartOpts);
  }

  if (d.caption) {
    slide.addText(String(d.caption), {
      x: MARGIN.left, y: SLIDE_H - 0.4, w: CONTENT_W, h: 0.3,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted, align: 'center'
    });
  }
  return slide;
}

// Timeline Slide
function buildTimelineSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const milestones = d.milestones || [];
  const n = Math.max(1, milestones.length);
  const timelineY = 3.8;
  const lineX = 0.8;
  const lineW = SLIDE_W - lineX - 0.8;
  const r = 0.18;
  const stepW = n > 1 ? lineW / (n - 1) : lineW;

  slide.addShape(pres.shapes.RECTANGLE, {
    x: lineX, y: timelineY - 0.02, w: lineW, h: 0.04, fill: { color: YELLOW }
  });

  milestones.forEach((m, i) => {
    const xC = n === 1 ? lineX + lineW / 2 : lineX + i * stepW;
    const isDone    = (m.status || '').toLowerCase() === 'complete';
    const isCurrent = (m.status || '').toLowerCase() === 'in_progress';
    const dotFill   = isDone ? YELLOW : (isCurrent ? 'FEE896' : WHITE);
    const dotLine   = isDone ? YELLOW : DARK_GRAY;
    const textColor = isDone || isCurrent ? t.titleClr : t.muted;
    const isAbove   = i % 2 === 0;
    const labelY    = isAbove ? timelineY - r - 1.2 : timelineY + r + 0.15;
    const dateY     = isAbove ? timelineY - r - 0.55 : timelineY + r + 0.75;

    slide.addShape(pres.shapes.ELLIPSE, {
      x: xC - r, y: timelineY - r, w: r * 2, h: r * 2,
      fill: { color: dotFill }, line: { color: dotLine, pt: 1.5 }
    });
    slide.addText(String(m.label || '').toUpperCase(), {
      x: xC - 1.0, y: labelY, w: 2.0, h: 0.5,
      fontFace: FONT_H, fontSize: 11, bold: true, color: textColor, align: 'center'
    });
    slide.addText(String(m.date  || ''), {
      x: xC - 1.0, y: dateY,  w: 2.0, h: 0.35,
      fontFace: FONT_B, fontSize: 10, color: t.muted, align: 'center'
    });
    const connY1 = isAbove ? labelY + 0.5 : timelineY + r;
    const connY2 = isAbove ? timelineY - r : dateY;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: xC - 0.01, y: Math.min(connY1, connY2),
      w: 0.02, h: Math.abs(connY2 - connY1), fill: { color: dotFill }
    });
  });

  if (d.caption) {
    slide.addText(String(d.caption), {
      x: MARGIN.left, y: SLIDE_H - 0.5, w: CONTENT_W, h: 0.4,
      fontFace: FONT_B, fontSize: 10, italic: true, color: t.muted, align: 'center'
    });
  }
  return slide;
}

// Matrix 2x2 Slide
function buildMatrix2x2Slide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const matrixX = 1.0, matrixY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.3;
  const matrixW = SLIDE_W - matrixX - 0.5;
  const matrixH = SLIDE_H - matrixY - 0.5;
  const midX = matrixX + matrixW / 2;
  const midY = matrixY + matrixH / 2;

  // Quadrant backgrounds
  [
    [matrixX, matrixY, matrixW/2, matrixH/2, 'F9F9F9'],
    [midX, matrixY, matrixW/2, matrixH/2, YELLOW_20],
    [matrixX, midY, matrixW/2, matrixH/2, YELLOW_20],
    [midX, midY, matrixW/2, matrixH/2, 'F9F9F9']
  ].forEach(([x, y, w, h, bg]) => slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h, fill: { color: bg }, line: { color: t.border, pt: 1 }
  }));

  // Cross lines
  slide.addShape(pres.shapes.RECTANGLE, {
    x: matrixX, y: midY - 0.025, w: matrixW, h: 0.05, fill: { color: YELLOW }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: midX - 0.025, y: matrixY, w: 0.05, h: matrixH, fill: { color: YELLOW }
  });

  // Quadrant labels
  const qLabels = d.quadrant_labels || ['', '', '', ''];
  [
    [matrixX + 0.1, matrixY + 0.1],
    [midX + 0.1, matrixY + 0.1],
    [matrixX + 0.1, midY + 0.1],
    [midX + 0.1, midY + 0.1]
  ].forEach(([qx, qy], qi) => {
    if (qLabels[qi]) slide.addText(String(qLabels[qi]).toUpperCase(), {
      x: qx, y: qy, w: matrixW/2 - 0.2, h: 0.55,
      fontFace: FONT_H, fontSize: 9, bold: true, color: t.muted, valign: 'top'
    });
  });

  if (d.x_label) slide.addText(String(d.x_label).toUpperCase(), {
    x: matrixX, y: matrixY + matrixH + 0.1, w: matrixW, h: 0.35,
    fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr, align: 'center'
  });
  if (d.y_label) slide.addText(String(d.y_label).toUpperCase(), {
    x: 0.1, y: matrixY, w: 0.7, h: matrixH,
    fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr,
    align: 'center', valign: 'middle', rotate: 270
  });

  // Scatter items
  (d.items || []).forEach(item => {
    const px = matrixX + (item.x || 0.5) * matrixW - 0.15;
    const py = matrixY + (1 - (item.y || 0.5)) * matrixH - 0.15;
    const sz = Math.max(0.2, Math.min(0.5, (item.size || 20) / 60));
    slide.addShape(pres.shapes.ELLIPSE, {
      x: px, y: py, w: sz, h: sz,
      fill: { color: YELLOW }, line: { color: t.titleClr, pt: 1 }
    });
    slide.addText(String(item.label || ''), {
      x: px + sz + 0.06, y: py, w: 1.5, h: sz,
      fontFace: FONT_B, fontSize: 10, bold: true, color: t.titleClr, valign: 'middle'
    });
  });
  return slide;
}

// Scorecard / RAG Table Slide
function buildScorecardSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const items = d.items || [];
  const tableRows = [[
    { text: 'METRIC',  options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'STATUS',  options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, align: 'center', border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'VALUE',   options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, align: 'center', border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
    { text: 'COMMENT', options: { bold: true, color: DARK_GRAY, fill: { color: YELLOW }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: DARK_GRAY, pt: 0.5 } } },
  ]];

  items.forEach((item, ri) => {
    const bg     = ri % 2 === 1 ? 'F5F5F5' : WHITE;
    const status = (item.status || 'green').toLowerCase();
    const ragColor = status === 'green' ? GREEN : status === 'red' ? RED : YELLOW;
    const ragLabel = status === 'green' ? '● ON TRACK' : status === 'red' ? '● BREACH' : '● AT RISK';
    tableRows.push([
      { text: String(item.metric || '').toUpperCase(), options: { bold: true, color: t.titleClr, fill: { color: bg }, fontSize: 11, fontFace: FONT_H, border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: ragLabel, options: { color: ragColor, fill: { color: bg }, fontSize: 11, fontFace: FONT_H, bold: true, align: 'center', border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: String(item.value   || ''), options: { color: t.bodyClr, fill: { color: bg }, fontSize: 11, fontFace: FONT_B, align: 'center', border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
      { text: String(item.comment || ''), options: { color: t.muted,   fill: { color: bg }, fontSize: 11, fontFace: FONT_B, border: { type: 'solid', color: GRAY_20, pt: 0.5 } } },
    ]);
  });

  const tableY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.2;
  const tableH = SLIDE_H - tableY - 0.5;
  slide.addTable(tableRows, {
    x: MARGIN.left, y: tableY, w: CONTENT_W,
    colW: [CONTENT_W * 0.28, CONTENT_W * 0.20, CONTENT_W * 0.24, CONTENT_W * 0.28],
    rowH: Math.min(0.72, tableH / (items.length + 1))
  });
  return slide;
}

// Comparison Slide (A vs B)
function buildComparisonSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const rows   = d.rows   || [];
  const winner = d.winner || 'right';
  const lLabel = d.left_label  || 'OPTION A';
  const rLabel = d.right_label || 'OPTION B';
  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.3;
  const col1W = 2.5, col2W = (CONTENT_W - col1W - 0.1) / 2, col3W = col2W;

  // Header row
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: contentY, w: col1W, h: 0.52, fill: { color: GRAY_20 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left + col1W + 0.05, y: contentY, w: col2W, h: 0.52,
    fill: { color: winner === 'left' ? YELLOW : 'F5F5F5' }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left + col1W + col2W + 0.1, y: contentY, w: col3W, h: 0.52,
    fill: { color: winner === 'right' ? YELLOW : 'F5F5F5' }
  });

  slide.addText('', {
    x: MARGIN.left, y: contentY, w: col1W, h: 0.52,
    fontFace: FONT_B, fontSize: 12, color: t.titleClr, valign: 'middle'
  });
  slide.addText(String(lLabel).toUpperCase(), {
    x: MARGIN.left + col1W + 0.05, y: contentY, w: col2W, h: 0.52,
    fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center', valign: 'middle'
  });
  slide.addText(String(rLabel).toUpperCase(), {
    x: MARGIN.left + col1W + col2W + 0.1, y: contentY, w: col3W, h: 0.52,
    fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center', valign: 'middle'
  });

  // Winner indicator
  if (winner === 'right') {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left + col1W + col2W + 0.07, y: contentY, w: 0.06, h: 0.52, fill: { color: YELLOW }
    });
  } else {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left + col1W + 0.02, y: contentY, w: 0.06, h: 0.52, fill: { color: YELLOW }
    });
  }

  // Data rows
  rows.forEach((row, ri) => {
    const rowY = contentY + 0.57 + ri * 0.65;
    const bg   = ri % 2 === 1 ? 'F5F5F5' : WHITE;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left, y: rowY, w: col1W, h: 0.62, fill: { color: bg }
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left + col1W + 0.05, y: rowY, w: col2W, h: 0.62,
      fill: { color: winner === 'left' ? YELLOW_20 : bg }
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left + col1W + col2W + 0.1, y: rowY, w: col3W, h: 0.62,
      fill: { color: winner === 'right' ? YELLOW_20 : bg }
    });
    slide.addText(String(row.label || '').toUpperCase(), {
      x: MARGIN.left, y: rowY, w: col1W, h: 0.62,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.titleClr, valign: 'middle'
    });
    slide.addText(String(row.left  || ''), {
      x: MARGIN.left + col1W + 0.05, y: rowY, w: col2W, h: 0.62,
      fontFace: FONT_B, fontSize: 11, color: t.bodyClr, align: 'center', valign: 'middle'
    });
    slide.addText(String(row.right || ''), {
      x: MARGIN.left + col1W + col2W + 0.1, y: rowY, w: col3W, h: 0.62,
      fontFace: FONT_B, fontSize: 11, color: t.bodyClr, align: 'center', valign: 'middle'
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN.left, y: rowY + 0.61, w: CONTENT_W, h: 0.015, fill: { color: GRAY_20 }
    });
  });
  return slide;
}

// Icon Grid Slide
function buildIconGridSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const items = d.items || [];
  const cols  = d.columns || Math.min(4, Math.max(1, Math.ceil(Math.sqrt(items.length))));
  const rows  = Math.ceil(items.length / cols);
  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.3;
  const contentH = SLIDE_H - contentY - 0.3;
  const cellW = CONTENT_W / cols;
  const cellH = contentH / rows;
  const iconMap = {
    shield: '🛡', chart: '📊', clock: '⏱', star: '★', check: '✓',
    lock: '🔒', globe: '🌐', dollar: '$', people: '👥', trophy: '🏆',
    lightning: '⚡', target: '🎯', default: '●'
  };

  items.forEach((item, idx) => {
    const col = idx % cols, row = Math.floor(idx / cols);
    const cx  = MARGIN.left + col * cellW + 0.1;
    const cy  = contentY + row * cellH + 0.05;
    const iconChar = iconMap[item.icon] || iconMap.default;
    const iconSz = Math.min(0.7, cellW * 0.3, cellH * 0.3);
    const iconX = cx + (cellW - 0.2) / 2 - iconSz / 2;

    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: iconX, y: cy + 0.1, w: iconSz, h: iconSz,
      fill: { color: YELLOW }, line: { color: YELLOW }, rectRadius: 0.15
    });
    slide.addText(iconChar, {
      x: iconX, y: cy + 0.1, w: iconSz, h: iconSz,
      fontFace: 'Arial', fontSize: Math.round(iconSz * 30), color: DARK_GRAY,
      align: 'center', valign: 'middle'
    });
    slide.addText((item.title || '').toUpperCase(), {
      x: cx, y: cy + iconSz + 0.25, w: cellW - 0.2, h: 0.45,
      fontFace: FONT_H, fontSize: 12, bold: true, color: t.titleClr, align: 'center'
    });
    if (item.body) slide.addText(String(item.body), {
      x: cx, y: cy + iconSz + 0.75, w: cellW - 0.2, h: cellH - iconSz - 0.85,
      fontFace: FONT_B, fontSize: 11, color: t.muted, align: 'center', valign: 'top'
    });
  });
  return slide;
}

// Executive Summary Slide
function buildExecutiveSummarySlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  // Thick yellow bar for executive emphasis
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.5, h: SLIDE_H, fill: { color: YELLOW }
  });

  const contentX = 0.75;
  slide.addText((d.headline || d.title || '').toUpperCase(), {
    x: contentX, y: 1.0, w: CONTENT_W - 0.25, h: 2.5,
    fontFace: FONT_H, fontSize: 28, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: contentX, y: 3.6, w: CONTENT_W - 0.25, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const points = d.supporting_points || d.bullets || [];
  if (points.length > 0) {
    slide.addText(points.map(p => ({
      text: String(p),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 8, paraSpaceAft: 8 }
    })), {
      x: contentX, y: 3.8, w: CONTENT_W - 0.25, h: 2.8,
      fontFace: FONT_B, fontSize: 16, color: t.bodyClr, valign: 'top'
    });
  }
  if (d.call_to_action) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: contentX, y: 6.7, w: CONTENT_W - 0.25, h: 0.62, fill: { color: YELLOW_20 }
    });
    slide.addText(String(d.call_to_action), {
      x: contentX + 0.2, y: 6.7, w: CONTENT_W - 0.45, h: 0.62,
      fontFace: FONT_H, fontSize: 13, bold: true, color: t.titleClr, valign: 'middle'
    });
  }
  return slide;
}

// Image + Content Slide (side by side)
function buildImageContentSlide(d) {
  const slide = pres.addSlide();
  const t     = getTheme(d);
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: SLIDE_H, fill: { color: YELLOW }
  });

  const titleY = MARGIN.top + 0.1;
  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: titleY, w: CONTENT_W, h: TITLE_AREA_H,
    fontFace: FONT_H, fontSize: 26, bold: true, color: t.titleClr, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN.left, y: titleY + TITLE_AREA_H, w: 2.5, h: TITLE_UNDERLINE_H, fill: { color: YELLOW }
  });

  const imgSide = d.image_side === 'right' ? 'right' : 'left';
  const contentY = titleY + TITLE_AREA_H + TITLE_UNDERLINE_H + 0.3;
  const contentH = SLIDE_H - contentY - 0.3;
  const imgX = imgSide === 'left' ? MARGIN.left : MARGIN.left + CONTENT_W / 2 + 0.3;
  const textX = imgSide === 'left' ? MARGIN.left + CONTENT_W / 2 + 0.3 : MARGIN.left;
  const colW = CONTENT_W / 2 - 0.15;

  if (d.data) {
    try {
      slide.addImage({
        data: 'data:image/' + (d.format || 'png') + ';base64,' + d.data,
        x: imgX, y: contentY, w: colW, h: contentH
      });
    } catch (e) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: imgX, y: contentY, w: colW, h: contentH,
        fill: { color: YELLOW_20 }, line: { color: t.border }
      });
    }
  } else {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: imgX, y: contentY, w: colW, h: contentH,
      fill: { color: YELLOW_20 }, line: { color: YELLOW }
    });
    slide.addText(String(d.image_placeholder || 'IMAGE'), {
      x: imgX, y: contentY, w: colW, h: contentH,
      fontFace: FONT_B, fontSize: 12, italic: true, color: t.muted,
      align: 'center', valign: 'middle'
    });
  }

  const bullets = d.bullets || [];
  if (bullets.length > 0) {
    slide.addText(bullets.map(b => ({
      text: String(b),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 8, paraSpaceAft: 8 }
    })), {
      x: textX, y: contentY, w: colW, h: contentH,
      fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top'
    });
  } else if (d.text) {
    slide.addText(String(d.text), {
      x: textX, y: contentY, w: colW, h: contentH,
      fontFace: FONT_B, fontSize: 15, color: t.bodyClr, valign: 'top'
    });
  }
  return slide;
}

// Card Grid Slide (flexible N-column layout)
function buildCardGridSlide(d) {
  const t = getTheme(d);
  const slide = pres.addSlide();
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  // Section label
  if (d.section_label) {
    slide.addText(String(d.section_label).toUpperCase(), {
      x: 0.35, y: 0.2, w: 4.5, h: 0.35,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.muted
    });
  }

  const headY = d.section_label ? 0.65 : 0.8;
  if (d.title) {
    slide.addText(d.title.toUpperCase(), {
      x: MARGIN.left, y: headY, w: CONTENT_W, h: 1.5,
      fontFace: FONT_H, fontSize: 32, bold: true,
      color: t.titleClr, align: 'center', valign: 'middle'
    });
  }

  const subY = headY + 1.6;
  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: MARGIN.left, y: subY, w: CONTENT_W, h: 0.55,
      fontFace: FONT_B, fontSize: 15, italic: true,
      color: YELLOW, align: 'center', valign: 'middle'
    });
  }

  const cards  = d.cards || [];
  if (!cards.length) return slide;

  const cols   = Math.min(6, d.columns || Math.min(4, cards.length));
  const gap    = 0.16;
  const cardY  = d.subtitle ? subY + 0.8 : subY + 0.2;
  const cardH  = d.card_height || Math.max(1.8, SLIDE_H - cardY - 0.3);
  const cardW  = (CONTENT_W - gap * (cols + 1)) / cols;
  const startX = MARGIN.left;

  cards.forEach((card, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const cx  = startX + gap + col * (cardW + gap);
    const cy  = cardY + row * (cardH + 0.15);

    const raw       = (card.color || 'yellow').replace('#', '');
    const cardFill  = raw === 'yellow'  ? YELLOW      :
                      raw === 'dark'    ? DARK_GRAY   :
                      raw === 'white'   ? WHITE       :
                      raw === 'gray'    ? t.cardBg    : raw;
    const onYellow  = cardFill === YELLOW;
    const onDark    = cardFill === DARK_GRAY;
    const cardTxt   = onYellow ? DARK_GRAY : onDark ? WHITE : t.bodyClr;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cardW, h: cardH,
      fill: { color: cardFill }, line: { color: cardFill }
    });

    const px = 0.18, textH = cardH - 0.6;
    slide.addText(card.title || card.text || '', {
      x: cx + px, y: cy + 0.3, w: cardW - px * 2, h: textH,
      fontFace: FONT_B, fontSize: card.font_size || 14,
      bold: !!card.bold,
      color: cardTxt, align: 'center', valign: 'middle'
    });

    if (card.subtitle) {
      slide.addText(card.subtitle, {
        x: cx + px, y: cy + cardH - 0.5, w: cardW - px * 2, h: 0.38,
        fontFace: FONT_B, fontSize: 10,
        color: onYellow ? '555555' : YELLOW, align: 'center'
      });
    }
  });
  return slide;
}

// Hub-Spoke Slide (process / data-flow diagram)
function buildHubSpokeSlide(d) {
  const t = getTheme(d);
  const slide = pres.addSlide();
  slide.background = { color: t.bg };

  addLogo(slide, LOGO_AREA.x, LOGO_AREA.y, LOGO_AREA.w, LOGO_AREA.h, t.logo);

  if (d.section_label) {
    slide.addText(String(d.section_label).toUpperCase(), {
      x: 0.35, y: 0.2, w: 4.5, h: 0.35,
      fontFace: FONT_H, fontSize: 11, bold: true, color: t.muted
    });
  }

  slide.addText((d.title || '').toUpperCase(), {
    x: MARGIN.left, y: 0.65, w: CONTENT_W, h: 0.9,
    fontFace: FONT_H, fontSize: 24, bold: true,
    color: t.titleClr, align: 'center', valign: 'middle'
  });

  const hub       = d.hub || {};
  const rawHubClr = (hub.color || 'yellow').replace('#', '');
  const hubFill   = rawHubClr === 'yellow' ? YELLOW : rawHubClr;
  const hubTxt    = hubFill === YELLOW ? DARK_GRAY : WHITE;
  const hubX = 4.3, hubY = 1.7, hubW = 4.8, hubH = 5.3;

  slide.addShape(pres.shapes.RECTANGLE, {
    x: hubX, y: hubY, w: hubW, h: hubH,
    fill: { color: hubFill }, line: { color: hubFill }
  });

  const hubLabel = hub.label || hub.title || '';
  if (hubLabel) {
    slide.addText(hubLabel.toUpperCase(), {
      x: hubX + 0.15, y: hubY + 0.15, w: hubW - 0.3, h: 0.5,
      fontFace: FONT_H, fontSize: 13, bold: true,
      color: hubTxt, align: 'center'
    });
  }

  const hubItems = hub.items || [];
  if (hubItems.length > 0) {
    const paras = hubItems.map(it => ({
      text: String(it), options: { paraSpaceBef: 4, paraSpaceAft: 4 }
    }));
    slide.addText(paras, {
      x: hubX + 0.15, y: hubY + (hubLabel ? 0.75 : 0.3),
      w: hubW - 0.3, h: hubH - (hubLabel ? 1.0 : 0.6),
      fontFace: FONT_B, fontSize: 12.5,
      color: hubTxt, align: 'center', valign: 'middle'
    });
  }

  const spokes = d.spokes || [];
  const boxW = 3.8;
  const leftX = 0.3, rightX = hubX + hubW + 0.1;
  const slots = { left: [], right: [] };
  spokes.forEach(s => {
    (slots[(s.side || 'left').toLowerCase()] = slots[(s.side || 'left').toLowerCase()] || []).push(s);
  });

  ['left', 'right'].forEach(side => {
    const list = slots[side] || [];
    if (!list.length) return;
    const xs = side === 'left' ? leftX : rightX;
    const bH = (hubH - 0.18 * (list.length - 1)) / list.length;

    list.forEach((spoke, ri) => {
      const by    = hubY + ri * (bH + 0.18);
      const label = spoke.label || spoke.title || '';
      const items = spoke.items || [];

      slide.addShape(pres.shapes.RECTANGLE, {
        x: xs, y: by, w: boxW, h: bH,
        fill: { color: t.cardBg }, line: { color: t.border }
      });

      if (label) {
        slide.addText(label.toUpperCase(), {
          x: xs + 0.15, y: by + 0.1, w: boxW - 0.3, h: 0.42,
          fontFace: FONT_H, fontSize: 12, bold: true,
          color: t.dark ? YELLOW : t.titleClr, align: 'center'
        });
      }

      if (items.length > 0) {
        slide.addText(items.join('\n'), {
          x: xs + 0.15, y: by + (label ? 0.57 : 0.2),
          w: boxW - 0.3, h: bH - (label ? 0.75 : 0.4),
          fontFace: FONT_B, fontSize: 12, color: t.muted,
          align: 'center', valign: 'middle'
        });
      }

      // Connector line
      const arY = by + bH / 2 - 0.02;
      const connX = side === 'left' ? (xs + boxW) : (hubX);
      const connW = Math.abs(side === 'left' ? (hubX - xs - boxW) : (xs - hubX - hubW)) - 0.22;
      slide.addShape(pres.shapes.RECTANGLE, {
        x: connX, y: arY, w: connW, h: 0.04,
        fill: { color: t.border }
      });
      slide.addText(side === 'left' ? '▶' : '◀', {
        x: side === 'left' ? (hubX - 0.28) : (xs - 0.06),
        y: arY - 0.14, w: 0.28, h: 0.28,
        fontFace: FONT_B, fontSize: 11, color: t.border, align: 'center'
      });
    });
  });

  return slide;
}

// ── Build all slides ──────────────────────────────────────────────────────────
for (const s of (spec.slides || [])) {
  try {
    switch (s.type) {
      case 'title':             buildTitleSlide(s);           break;
      case 'content':           buildContentSlide(s);         break;
      case 'two_column':        buildTwoColumnSlide(s);       break;
      case 'three_column':      buildThreeColumnSlide(s);     break;
      case 'metrics':           buildMetricsSlide(s);         break;
      case 'process':           buildProcessSlide(s);         break;
      case 'quote':             buildQuoteSlide(s);           break;
      case 'section_divider':   buildSectionDividerSlide(s);  break;
      case 'cta':               buildCtaSlide(s);             break;
      case 'image':             buildImageSlide(s);           break;
      case 'table':             buildTableSlide(s);           break;
      case 'chart':             buildChartSlide(s);           break;
      case 'timeline':          buildTimelineSlide(s);        break;
      case 'matrix_2x2':        buildMatrix2x2Slide(s);       break;
      case 'scorecard':         buildScorecardSlide(s);       break;
      case 'comparison':        buildComparisonSlide(s);      break;
      case 'icon_grid':         buildIconGridSlide(s);        break;
      case 'executive_summary': buildExecutiveSummarySlide(s);break;
      case 'image_content':     buildImageContentSlide(s);    break;
      case 'card_grid':         buildCardGridSlide(s);        break;
      case 'hub_spoke':         buildHubSpokeSlide(s);        break;
      default:                  buildContentSlide(s);         break;
    }
  } catch (err) {
    process.stderr.write('WARN: slide[' + s.type + '] error: ' + err.message + '\n');
  }
}

// ── Write output ──────────────────────────────────────────────────────────────
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


# ── Embedded Node.js freestyle wrapper ───────────────────────────────────────
_FREESTYLE_WRAPPER = r"""
'use strict';
const fs      = require('fs');
const path    = require('path');
const pptxgen = require('pptxgenjs');

// ── Constants ────────────────────────────────────────────────────────────────
const SLIDE_W = 13.333;
const SLIDE_H = 7.5;
const CONTENT_W = SLIDE_W - 1.0;  // Accounting for margins

// ── Brand palette ─────────────────────────────────────────────────────────
const YELLOW     = 'FEC00F';
const DARK_GRAY  = '212121';
const WHITE      = 'FFFFFF';
const GRAY_60    = '999999';
const GRAY_20    = 'DDDDDD';
const YELLOW_20  = 'FEF7D8';

// ── Brand fonts ─────────────────────────────────────────────────────────────
const FONT_H = 'Rajdhani';
const FONT_B = 'Quicksand';

// ── Logos ─────────────────────────────────────────────────────────────────
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

// Logo aspect ratios (pre-computed for proper scaling)
const LOGO_DIMS = {
  full:   { aspect: 3.6 },
  black:  { aspect: 1.0 },
  yellow: { aspect: 1.0 },
};

function getLogoDisplayDims(variant, maxW, maxH) {
  const dims = LOGO_DIMS[variant] || LOGO_DIMS.full;
  const aspect = dims.aspect;
  let w, h;
  if (maxW / maxH > aspect) {
    h = maxH;
    w = h * aspect;
  } else {
    w = maxW;
    h = w / aspect;
  }
  return { w, h };
}

// ── Logo helper - preserves aspect ratio, never stretches ─────────────────
function addLogo(slide, x, y, maxW, maxH, variant) {
  const data = variant === 'black'  ? LOGOS.black  :
               variant === 'yellow' ? LOGOS.yellow :
               LOGOS.full;
  if (data) {
    const { w, h } = getLogoDisplayDims(variant, maxW, maxH);
    const xOff = x + (maxW - w) / 2;
    const yOff = y + (maxH - h) / 2;
    slide.addImage({ data, x: xOff, y: yOff, w, h });
  } else {
    slide.addText('POTOMAC', {
      x, y, maxW, maxH, fontFace: FONT_H, fontSize: 14, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle'
    });
  }
}

// ── Presentation ──────────────────────────────────────────────────────────
const pres = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = __PRES_TITLE__;
pres.layout  = 'LAYOUT_WIDE';

// ═══════════════════════════════════════════════════════════════════════════
// LLM FREESTYLE CODE
// Available: pres, YELLOW, DARK_GRAY, WHITE, GRAY_60, GRAY_20, YELLOW_20,
//            FONT_H, FONT_B, LOGOS, addLogo(), SLIDE_W, SLIDE_H, CONTENT_W
// Canvas: 13.333" wide × 7.5" tall (LAYOUT_WIDE = standard PowerPoint 16:9).
// ═══════════════════════════════════════════════════════════════════════════

__LLM_CODE__

// ═══════════════════════════════════════════════════════════════════════════
// END OF LLM CODE
// ═══════════════════════════════════════════════════════════════════════════

// ── Write output ──────────────────────────────────────────────────────────
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

    spec = copy.deepcopy(spec)
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

        The caller supplies the slide-building logic.
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

            # ── 4. Build script ───────────────────────────────────────
            safe_fn = filename if filename.lower().endswith(".pptx") else filename + ".pptx"
            script  = _FREESTYLE_WRAPPER
            script  = script.replace("__PRES_TITLE__",     _json.dumps(title))
            script  = script.replace("__OUTPUT_FILENAME__", _json.dumps(safe_fn))
            script  = script.replace("__LLM_CODE__",       code)

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
                        error=f"Output .pptx not found",
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
