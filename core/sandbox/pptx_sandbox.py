"""
PPTX Sandbox
============
Generates Potomac-branded PowerPoint presentations server-side using the
``pptxgenjs`` npm package in a Node.js subprocess.  No Claude Skills container
needed.

Assets (Potomac logos) are mounted from:
    ClaudeSkills/potomac-pptx/brand-assets/logos/

Each invocation gets an isolated temp directory; npm module resolution is
accelerated by symlinking a persistent node_modules cache
(~/.sandbox/pptx_cache/) that is installed once on first call.

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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_SANDBOX_HOME   = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_PPTX_CACHE_DIR = _SANDBOX_HOME / "pptx_cache"

# Assets: prefer persistent Railway volume, fall back to repo copy.
_THIS_DIR          = Path(__file__).parent                                # core/sandbox/
_REPO_ASSETS_DIR   = _THIS_DIR.parent.parent / "ClaudeSkills" / "potomac-pptx" / "brand-assets" / "logos"
_STORAGE_ROOT      = Path(os.environ.get("STORAGE_ROOT", "/data"))
_VOLUME_ASSETS_DIR = _STORAGE_ROOT / "pptx_assets"
_ASSETS_DIR        = _VOLUME_ASSETS_DIR if _VOLUME_ASSETS_DIR.exists() else _REPO_ASSETS_DIR

_LOGO_FILES = [
    "potomac-full-logo.png",
    "potomac-icon-black.png",
    "potomac-icon-yellow.png",
]

# ── Embedded Node.js presentation builder ────────────────────────────────────
_BUILDER_SCRIPT = r"""
'use strict';
const fs      = require('fs');
const path    = require('path');
const pptxgen = require('pptxgenjs');

// ── Brand palette ─────────────────────────────────────────────────────────────
const YELLOW    = 'FEC00F';
const DARK_GRAY = '212121';
const WHITE     = 'FFFFFF';
const GRAY_60   = '999999';
const GRAY_20   = 'DDDDDD';
const YELLOW_20 = 'FEF7D8';

// ── Spec ──────────────────────────────────────────────────────────────────────
const spec = JSON.parse(fs.readFileSync('spec.json', 'utf8'));

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

// ── Create presentation ───────────────────────────────────────────────────────
const pres = new pptxgen();
pres.author  = 'Potomac';
pres.company = 'Potomac';
pres.title   = spec.title || 'POTOMAC PRESENTATION';
// Default layout is LAYOUT_WIDE (10x7.5 inches) — no defineLayout needed

// ── Helper: add logo ──────────────────────────────────────────────────────────
function addLogo(slide, x, y, w, h, variant) {
  const data = (variant === 'black')  ? LOGOS.black  :
               (variant === 'yellow') ? LOGOS.yellow :
               LOGOS.full;
  if (data) {
    slide.addImage({ data, x, y, w, h });
  } else {
    slide.addText('POTOMAC', {
      x, y, w, h, fontFace: 'Arial', fontSize: 14, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle'
    });
  }
}

// ── Slide builders ────────────────────────────────────────────────────────────

function buildTitleSlide(d) {
  const slide  = pres.addSlide();
  const isExec = (d.style === 'executive');
  slide.background = { color: isExec ? DARK_GRAY : WHITE };

  addLogo(slide, 4.1, 0.9, 1.8, 0.73, isExec ? 'yellow' : 'full');

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 2.4, w: 9, h: 1.5,
    fontFace: 'Arial', fontSize: 44, bold: true,
    color: isExec ? WHITE : DARK_GRAY, align: 'center', valign: 'middle'
  });

  if (d.subtitle) {
    slide.addText(d.subtitle, {
      x: 0.5, y: 4.1, w: 9, h: 0.9,
      fontFace: 'Arial', fontSize: 20, italic: isExec,
      color: isExec ? YELLOW : GRAY_60, align: 'center', valign: 'middle'
    });
  }

  // Accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 5.5, w: 9, h: 0.08, fill: { color: YELLOW }
  });

  const tagline = d.tagline || (isExec ? 'Built to Conquer Risk\u00AE' : null);
  if (tagline) {
    slide.addText(tagline, {
      x: 0.5, y: 5.8, w: 9, h: 0.5,
      fontFace: 'Arial', fontSize: 15, italic: true,
      color: YELLOW, align: 'center', valign: 'middle'
    });
  }
  return slide;
}

function buildContentSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');

  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: YELLOW }
  });

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 0.4, w: 7.9, h: 0.9,
    fontFace: 'Arial', fontSize: 30, bold: true,
    color: DARK_GRAY, valign: 'middle'
  });

  // Title underline
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.3, w: 2.5, h: 0.06, fill: { color: YELLOW }
  });

  const bullets = d.bullets || (Array.isArray(d.content) ? d.content : null);
  const text    = d.text   || (!Array.isArray(d.content) ? d.content : null);

  if (bullets && bullets.length > 0) {
    const items = bullets.map(b => ({
      text: String(b),
      options: { bullet: { type: 'bullet' }, paraSpaceBef: 6, paraSpaceAft: 6 }
    }));
    slide.addText(items, {
      x: 0.5, y: 1.55, w: 9.1, h: 5.5,
      fontFace: 'Arial', fontSize: 18, color: DARK_GRAY, valign: 'top'
    });
  } else if (text) {
    slide.addText(String(text), {
      x: 0.5, y: 1.55, w: 9.1, h: 5.5,
      fontFace: 'Arial', fontSize: 16, color: DARK_GRAY, valign: 'top'
    });
  }
  return slide;
}

function buildTwoColumnSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: YELLOW } });

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 0.4, w: 7.9, h: 0.9,
    fontFace: 'Arial', fontSize: 26, bold: true, color: DARK_GRAY, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.3, w: 2.5, h: 0.06, fill: { color: YELLOW } });

  const colW    = 4.3;
  const gap     = 0.6;
  const lX      = 0.5;
  const rX      = lX + colW + gap;
  const hasHdrs = d.left_header || d.right_header;

  if (d.left_header) {
    slide.addText(String(d.left_header), {
      x: lX, y: 1.55, w: colW, h: 0.42,
      fontFace: 'Arial', fontSize: 14, bold: true, color: YELLOW, valign: 'middle'
    });
  }
  if (d.right_header) {
    slide.addText(String(d.right_header), {
      x: rX, y: 1.55, w: colW, h: 0.42,
      fontFace: 'Arial', fontSize: 14, bold: true, color: YELLOW, valign: 'middle'
    });
  }

  const cy = hasHdrs ? 2.1 : 1.6;
  const ch = hasHdrs ? 4.9 : 5.5;
  const lT = d.left_content  || (d.columns && d.columns[0]) || '';
  const rT = d.right_content || (d.columns && d.columns[1]) || '';

  slide.addText(String(lT), {
    x: lX, y: cy, w: colW, h: ch, fontFace: 'Arial', fontSize: 15, color: DARK_GRAY, valign: 'top'
  });

  // Divider
  slide.addShape(pres.shapes.RECTANGLE, {
    x: lX + colW + gap / 2 - 0.02, y: 1.6, w: 0.04, h: 5.5, fill: { color: GRAY_20 }
  });

  slide.addText(String(rT), {
    x: rX, y: cy, w: colW, h: ch, fontFace: 'Arial', fontSize: 15, color: DARK_GRAY, valign: 'top'
  });
  return slide;
}

function buildThreeColumnSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: YELLOW } });

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 0.4, w: 7.9, h: 0.9,
    fontFace: 'Arial', fontSize: 24, bold: true, color: DARK_GRAY, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.3, w: 2.5, h: 0.06, fill: { color: YELLOW } });

  const columns = d.columns || [];
  const headers = d.column_headers || [];
  const colW    = 2.85;
  const gap     = 0.25;

  for (let i = 0; i < 3; i++) {
    const xPos = 0.5 + i * (colW + gap);
    if (headers[i]) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: xPos, y: 1.55, w: colW, h: 0.45, fill: { color: YELLOW }
      });
      slide.addText(String(headers[i]), {
        x: xPos, y: 1.55, w: colW, h: 0.45,
        fontFace: 'Arial', fontSize: 13, bold: true,
        color: DARK_GRAY, align: 'center', valign: 'middle'
      });
    }
    const cY = headers[i] ? 2.1 : 1.6;
    slide.addText(String(columns[i] || ''), {
      x: xPos, y: cY, w: colW, h: 5.3,
      fontFace: 'Arial', fontSize: 13, color: DARK_GRAY, valign: 'top'
    });
  }
  return slide;
}

function buildMetricsSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: YELLOW } });

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 0.4, w: 7.9, h: 0.9,
    fontFace: 'Arial', fontSize: 28, bold: true, color: DARK_GRAY, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.3, w: 2.5, h: 0.06, fill: { color: YELLOW } });

  const metrics = d.metrics || [];
  const perRow  = Math.min(3, Math.max(1, metrics.length));
  const mW      = 8.8 / perRow;

  metrics.forEach((m, i) => {
    const row  = Math.floor(i / perRow);
    const col  = i % perRow;
    const xPos = 0.6 + col * mW;
    const yPos = 2.2 + row * 2.2;

    slide.addText(String(m.value || ''), {
      x: xPos, y: yPos, w: mW - 0.2, h: 1.2,
      fontFace: 'Arial', fontSize: 54, bold: true,
      color: YELLOW, align: 'center', valign: 'middle'
    });
    slide.addText(String(m.label || ''), {
      x: xPos, y: yPos + 1.2, w: mW - 0.2, h: 0.6,
      fontFace: 'Arial', fontSize: 14, color: GRAY_60, align: 'center'
    });
  });

  if (d.context) {
    slide.addText(String(d.context), {
      x: 0.5, y: 6.5, w: 9, h: 0.75,
      fontFace: 'Arial', fontSize: 11, italic: true, color: GRAY_60, align: 'center'
    });
  }
  return slide;
}

function buildProcessSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.15, h: 7.5, fill: { color: YELLOW } });

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 0.4, w: 7.9, h: 0.9,
    fontFace: 'Arial', fontSize: 26, bold: true, color: DARK_GRAY, valign: 'middle'
  });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.3, w: 2.5, h: 0.06, fill: { color: YELLOW } });

  const steps = d.steps || [];
  const n     = Math.max(1, steps.length);
  const stepW = 9.0 / n;
  const r     = 0.3;

  steps.forEach((step, i) => {
    const xPos = 0.5 + i * stepW;
    const cx   = xPos + stepW / 2 - r;
    const cy   = 2.5;

    slide.addShape(pres.shapes.ELLIPSE, {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fill: { color: YELLOW }, line: { color: YELLOW }
    });
    slide.addText(String(i + 1), {
      x: cx, y: cy, w: r * 2, h: r * 2,
      fontFace: 'Arial', fontSize: 16, bold: true,
      color: DARK_GRAY, align: 'center', valign: 'middle'
    });

    // Connecting line to next step
    if (i < steps.length - 1) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: cx + r * 2, y: cy + r - 0.02,
        w: stepW - r * 2, h: 0.04, fill: { color: GRAY_20 }
      });
    }

    slide.addText(String(step.title || '').toUpperCase(), {
      x: xPos, y: cy + r * 2 + 0.15, w: stepW - 0.05, h: 0.6,
      fontFace: 'Arial', fontSize: 12, bold: true, color: DARK_GRAY, align: 'center'
    });
    slide.addText(String(step.description || ''), {
      x: xPos, y: cy + r * 2 + 0.82, w: stepW - 0.05, h: 2.8,
      fontFace: 'Arial', fontSize: 11, color: GRAY_60, align: 'center', valign: 'top'
    });
  });
  return slide;
}

function buildQuoteSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: YELLOW_20 };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');

  slide.addText('\u201C', {
    x: 0.4, y: 1.1, w: 1.2, h: 1.4,
    fontFace: 'Arial', fontSize: 96, bold: true,
    color: YELLOW, align: 'center', valign: 'middle'
  });
  slide.addText(String(d.quote || ''), {
    x: 1.4, y: 1.8, w: 7.4, h: 3.0,
    fontFace: 'Arial', fontSize: 22, italic: true,
    color: DARK_GRAY, align: 'center', valign: 'middle'
  });
  if (d.attribution) {
    slide.addText('\u2014 ' + String(d.attribution), {
      x: 1.4, y: 5.0, w: 7.4, h: 0.7,
      fontFace: 'Arial', fontSize: 16, bold: true, color: GRAY_60, align: 'center'
    });
  }
  if (d.context) {
    slide.addText(String(d.context), {
      x: 1.4, y: 5.8, w: 7.4, h: 0.5,
      fontFace: 'Arial', fontSize: 12, italic: true, color: GRAY_60, align: 'center'
    });
  }
  return slide;
}

function buildSectionDividerSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: YELLOW_20 };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.45, h: 7.5, fill: { color: YELLOW }
  });
  slide.addText((d.title || '').toUpperCase(), {
    x: 0.8, y: 2.4, w: 8.0, h: 1.6,
    fontFace: 'Arial', fontSize: 42, bold: true, color: DARK_GRAY, valign: 'middle'
  });
  if (d.description) {
    slide.addText(String(d.description), {
      x: 0.8, y: 4.2, w: 8.0, h: 1.5,
      fontFace: 'Arial', fontSize: 18, color: GRAY_60, valign: 'middle'
    });
  }
  return slide;
}

function buildCtaSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 4.1, 0.7, 1.8, 0.73, 'full');

  slide.addText((d.title || '').toUpperCase(), {
    x: 0.5, y: 1.8, w: 9, h: 1.0,
    fontFace: 'Arial', fontSize: 34, bold: true,
    color: DARK_GRAY, align: 'center', valign: 'middle'
  });
  if (d.action_text) {
    slide.addText(String(d.action_text), {
      x: 0.5, y: 3.0, w: 9, h: 1.5,
      fontFace: 'Arial', fontSize: 18, color: DARK_GRAY, align: 'center', valign: 'middle'
    });
  }

  // Button
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 3.5, y: 4.8, w: 3.0, h: 0.7,
    fill: { color: YELLOW }, line: { color: YELLOW }
  });
  slide.addText((d.button_text || 'GET STARTED').toUpperCase(), {
    x: 3.5, y: 4.8, w: 3.0, h: 0.7,
    fontFace: 'Arial', fontSize: 15, bold: true,
    color: DARK_GRAY, align: 'center', valign: 'middle'
  });

  slide.addText('Built to Conquer Risk\u00AE', {
    x: 0.5, y: 5.7, w: 9, h: 0.5,
    fontFace: 'Arial', fontSize: 14, italic: true, color: YELLOW, align: 'center'
  });
  if (d.contact_info) {
    slide.addText(String(d.contact_info), {
      x: 0.5, y: 6.3, w: 9, h: 0.8,
      fontFace: 'Arial', fontSize: 12, color: GRAY_60, align: 'center'
    });
  }
  return slide;
}

function buildImageSlide(d) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };
  addLogo(slide, 8.55, 0.15, 1.25, 0.5, 'full');

  if (d.title) {
    slide.addText(d.title.toUpperCase(), {
      x: 0.5, y: 0.4, w: 7.9, h: 0.9,
      fontFace: 'Arial', fontSize: 26, bold: true, color: DARK_GRAY, valign: 'middle'
    });
  }

  if (!d.data) return slide;   // no image — Python already skips file_id-only sections

  try {
    const imgData = 'data:image/' + (d.format || 'png') + ';base64,' + d.data;
    const w    = d.width  || 6;
    const h    = d.height || Math.round(w * 0.667 * 10) / 10;
    const xOff = d.align === 'center' ? (10 - w) / 2 :
                 d.align === 'right'  ? 9.5 - w       : 0.5;
    const yOff = d.title ? 1.5 : 1.2;
    slide.addImage({ data: imgData, x: xOff, y: yOff, w, h });
    if (d.caption) {
      slide.addText(String(d.caption), {
        x: 0.5, y: yOff + h + 0.15, w: 9, h: 0.45,
        fontFace: 'Arial', fontSize: 12, italic: true, color: GRAY_60,
        align: d.align === 'center' ? 'center' : 'left'
      });
    }
  } catch (e) {
    process.stderr.write('WARN: image slide error: ' + e.message + '\n');
  }
  return slide;
}

// ── Build all slides ──────────────────────────────────────────────────────────
for (const s of (spec.slides || [])) {
  try {
    switch (s.type) {
      case 'title':           buildTitleSlide(s);          break;
      case 'content':         buildContentSlide(s);        break;
      case 'two_column':      buildTwoColumnSlide(s);      break;
      case 'three_column':    buildThreeColumnSlide(s);    break;
      case 'metrics':         buildMetricsSlide(s);        break;
      case 'process':         buildProcessSlide(s);        break;
      case 'quote':           buildQuoteSlide(s);          break;
      case 'section_divider': buildSectionDividerSlide(s); break;
      case 'cta':             buildCtaSlide(s);            break;
      case 'image':           buildImageSlide(s);          break;
      default:                buildContentSlide(s);        break;
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


# =============================================================================
# Result dataclass
# =============================================================================

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


# =============================================================================
# Module-level npm cache helper
# =============================================================================

def _ensure_pptx_modules() -> Optional[Path]:
    """
    Ensure the ``pptxgenjs`` npm package is installed in the persistent cache dir.

    First call installs once (~45 s). Subsequent calls return instantly
    after confirming node_modules/pptxgenjs exists.

    Returns the ``node_modules`` Path, or ``None`` on failure.
    """
    modules  = _PPTX_CACHE_DIR / "node_modules"
    pptx_pkg = modules / "pptxgenjs"

    if pptx_pkg.exists():
        logger.debug("pptxgenjs node_modules cache hit: %s", modules)
        return modules

    logger.info("First-time pptxgenjs install — this takes ~45 s…")
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


# =============================================================================
# Image slide resolver — converts file_id → inline base64
# =============================================================================

def _resolve_image_slides(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Walk ``spec.slides`` and resolve ``{"type": "image", "file_id": "<uuid>"}``
    items to ``{"type": "image", "data": "<base64>", "format": "<ext>"}`` so
    that ``presentation_builder.js`` can embed them directly.

    Slides that already have a ``data`` field are left untouched.
    Missing / unavailable file_ids are silently skipped (JS skips items without data).

    Returns a **copy** of *spec* with the resolved slides.
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


# =============================================================================
# PptxSandbox
# =============================================================================

class PptxSandbox:
    """
    Generates Potomac-branded .pptx files from a structured spec dict.

    The spec describes all slides; no code generation by the LLM is required.
    The embedded ``_BUILDER_SCRIPT`` (Node.js / pptxgenjs) translates the spec
    into a pptxgen Presentation object and writes ``output.pptx``.

    Concurrency
    -----------
    Each call gets its own ``tempfile.mkdtemp()`` directory.
    """

    def generate(self, spec: Dict[str, Any], timeout: int = 120) -> PptxResult:
        """
        Generate a ``.pptx`` file from *spec*.

        Parameters
        ----------
        spec : dict
            Presentation specification.  Required keys: ``title``, ``slides``.
            See the ``generate_pptx`` tool schema for the full definition.
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
                return PptxResult(False, error="pptxgenjs npm package unavailable — npm install failed")

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
                logger.warning("No Potomac logo assets found at %s — slides will use text fallback", _ASSETS_DIR)

            # ── 4. Write spec + builder ────────────────────────────────────
            (temp_dir / "spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temp_dir / "presentation_builder.js").write_text(_BUILDER_SCRIPT, encoding="utf-8")
            (temp_dir / "package.json").write_text(
                json.dumps({"name": "pptx-gen", "version": "1.0.0"}), encoding="utf-8"
            )

            # ── 5. Symlink node_modules from cache (O(1)) ──────────────────
            nm_link = temp_dir / "node_modules"
            try:
                os.symlink(str(modules_path), str(nm_link))
            except OSError:
                logger.debug("symlink failed, falling back to copytree for node_modules")
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
                        error=f"Output .pptx not found. stdout={stdout!r}  stderr={stderr!r}",
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
                error="Node.js not found — ensure node is installed and on PATH",
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
