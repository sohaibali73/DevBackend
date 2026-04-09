"""
DOCX Sandbox
============
Generates Potomac-branded Word documents server-side using the ``docx`` npm
package in a Node.js subprocess.  No Claude Skills container needed.

Assets (Potomac logos) are mounted from:
    ClaudeSkills/potomac-docx/assets/

Each invocation gets an isolated temp directory; npm module resolution is
accelerated by symlinking a persistent node_modules cache
(~/.sandbox/docx_cache/) that is installed once on first call.

Usage
-----
    from core.sandbox.docx_sandbox import DocxSandbox
    from core.file_store import store_file

    sandbox = DocxSandbox()
    result  = sandbox.generate(spec_dict, timeout=90)
    if result.success:
        entry = store_file(result.data, result.filename, "docx", "generate_docx")
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
_DOCX_CACHE_DIR = _SANDBOX_HOME / "docx_cache"

# Assets: prefer persistent Railway volume, fall back to repo copy.
# The Dockerfile copies ClaudeSkills/ into the image so the repo path always
# works; the volume copy (populated on startup by main.py) survives redeploys
# even if the image filesystem is replaced.
_THIS_DIR         = Path(__file__).parent                           # core/sandbox/
_REPO_ASSETS_DIR  = _THIS_DIR.parent.parent / "ClaudeSkills" / "potomac-docx" / "assets"
_STORAGE_ROOT     = Path(os.environ.get("STORAGE_ROOT", "/data"))
_VOLUME_ASSETS_DIR = _STORAGE_ROOT / "docx_assets"
_ASSETS_DIR       = _VOLUME_ASSETS_DIR if _VOLUME_ASSETS_DIR.exists() else _REPO_ASSETS_DIR

_LOGO_FILES = [
    "Potomac_Logo_clean.png",
    "Potomac_Logo_Black_clean.png",
    "Potomac_Logo_White_clean.png",
]

# ── Embedded Node.js document builder ────────────────────────────────────────
# This script is written to the temp directory on every invocation.
# It reads spec.json and the logos from ./assets/ then writes output.docx.
_BUILDER_SCRIPT = r"""
'use strict';
const fs   = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun,
  Table, TableRow, TableCell,
  Header, Footer,
  AlignmentType, HeadingLevel, BorderStyle,
  WidthType, ShadingType, LevelFormat,
  PageNumber, PageBreak
} = require('docx');

// ── Brand palette ────────────────────────────────────────────────────────────
const YELLOW    = 'FEC00F';
const DARK_GRAY = '212121';
const MID_GRAY  = 'CCCCCC';
const WHITE     = 'FFFFFF';

// ── Spec ──────────────────────────────────────────────────────────────────────
const spec = JSON.parse(fs.readFileSync('spec.json', 'utf8'));

// ── Logos ──────────────────────────────────────────────────────────────────────
const assetsDir = path.join(__dirname, 'assets');
function loadLogo(name) {
  try { return fs.readFileSync(path.join(assetsDir, name)); } catch (_) { return null; }
}
const LOGOS = {
  standard : loadLogo('Potomac_Logo_clean.png'),
  black    : loadLogo('Potomac_Logo_Black_clean.png'),
  white    : loadLogo('Potomac_Logo_White_clean.png'),
};
function getLogo() {
  return LOGOS[spec.logo_variant || 'standard'] || LOGOS.standard || null;
}

// ── Header with Potomac logo + coloured underline ──────────────────────────
function makeHeader() {
  const logo      = getLogo();
  const lineColor = spec.header_line_color === 'dark' ? DARK_GRAY : YELLOW;
  if (!logo) return new Header({ children: [] });
  return new Header({ children: [
    new Paragraph({
      children : [new ImageRun({ data: logo, transformation: { width: 130, height: 27 }, type: 'png' })],
      border   : { bottom: { style: BorderStyle.SINGLE, size: 6, color: lineColor, space: 4 } }
    })
  ]});
}

// ── Footer with page numbers ───────────────────────────────────────────────
function makeFooter() {
  const leftText = spec.footer_text || 'Potomac  |  Built to Conquer Risk\u00AE';
  return new Footer({ children: [
    new Paragraph({
      border   : { top: { style: BorderStyle.SINGLE, size: 3, color: MID_GRAY, space: 4 } },
      children : [
        new TextRun({ text: leftText + '  |  Page ', font: 'Quicksand', size: 18, color: '999999' }),
        new TextRun({ children: [PageNumber.CURRENT],    font: 'Quicksand', size: 18, color: '999999' }),
        new TextRun({ text: ' of ',                      font: 'Quicksand', size: 18, color: '999999' }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], font: 'Quicksand', size: 18, color: '999999' }),
      ]
    })
  ]});
}

// ── Title page block ──────────────────────────────────────────────────────
function buildTitlePage() {
  const items = [];
  const logo  = getLogo();
  if (logo) {
    items.push(new Paragraph({
      alignment : AlignmentType.LEFT,
      children  : [new ImageRun({ data: logo, transformation: { width: 200, height: 41 }, type: 'png' })],
      spacing   : { after: 480 }
    }));
  }
  if (spec.title) {
    items.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(spec.title)] }));
  }
  if (spec.subtitle) {
    items.push(new Paragraph({
      children : [new TextRun({ text: spec.subtitle, italics: true, size: 28, font: 'Quicksand', color: DARK_GRAY })],
      spacing  : { after: 120 }
    }));
  }
  const meta = [spec.date, spec.author].filter(Boolean).join('  |  ');
  if (meta) {
    items.push(new Paragraph({
      children : [new TextRun({ text: meta, italics: true, size: 20, font: 'Quicksand', color: '666666' })],
      spacing  : { after: 480 }
    }));
  }
  return items;
}

// ── Table helpers ──────────────────────────────────────────────────────────
const BDR  = { style: BorderStyle.SINGLE, size: 1, color: MID_GRAY };
const BDRS = { top: BDR, bottom: BDR, left: BDR, right: BDR };
const MRGN = { top: 80, bottom: 80, left: 120, right: 120 };

// ── Section content builder ─────────────────────────────────────────────────
function buildContent(sections) {
  const out = [];
  for (const item of (sections || [])) {
    switch (item.type) {

      // ── Callout ─────────────────────────────────────────────────────────
      case 'callout': {
        const bg = item.style === 'dark'   ? '333333'
                 : item.style === 'light'  ? 'F9F9F9'
                 :                          'FEF3CD'; // yellow default
        const accent = item.style === 'dark' ? DARK_GRAY : YELLOW;
        const textColor = item.style === 'dark' ? WHITE : DARK_GRAY;
        const title = item.title || '';
        const body = item.body || '';
        const icon = item.icon || '';

        const children = [];
        if (icon || title) {
          children.push(new Paragraph({
            children: [
              icon ? new TextRun({ text: icon + '  ', font: 'Quicksand', size: 24, color: accent }) : null,
              new TextRun({ text: title, font: 'Rajdhani', size: 24, bold: true, color: textColor, allCaps: true }),
            ].filter(Boolean),
            spacing: { after: 120 },
          }));
        }
        children.push(new Paragraph({
          children: [new TextRun({ text: body, font: 'Quicksand', size: 22, color: textColor })],
        }));

        out.push(new Table({
          width: { size: 9360, type: WidthType.DXA },
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders: {
                    top: BDR, bottom: BDR, left: { style: BorderStyle.SINGLE, size: 18, color: accent }, right: BDR,
                  },
                  shading: { fill: bg, type: ShadingType.CLEAR },
                  margins: { top: 160, bottom: 160, left: 240, right: 240 },
                  children,
                }),
              ],
            }),
          ],
        }));
        out.push(new Paragraph({ spacing: { after: 240 } }));
        break;
      }

      // ── KPI Row ─────────────────────────────────────────────────────────
      case 'kpi_row': {
        const metrics = item.metrics || [];
        if (metrics.length === 0) break;

        const kpiCells = metrics.map((m) => {
          const isPositive = m.positive === true;
          const isNegative = m.positive === false;
          const deltaColor = isPositive ? '2D7D46' : isNegative ? 'C0392B' : DARK_GRAY;
          const children = [];

          children.push(new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({
                text: String(m.value || ''),
                font: 'Rajdhani', size: 48, bold: true, color: DARK_GRAY,
              }),
            ],
          }));

          children.push(new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({
                text: String(m.label || ''),
                font: 'Quicksand', size: 20, color: '666666',
              }),
            ],
            spacing: { after: 40 },
          }));

          if (m.delta) {
            children.push(new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  text: isPositive ? `↑ ${m.delta}` : isNegative ? `↓ ${m.delta}` : m.delta,
                  font: 'Quicksand', size: 18, bold: true, color: deltaColor,
                }),
              ],
            }));
          }

          return new TableCell({
            borders: BDRS,
            shading: { fill: WHITE, type: ShadingType.CLEAR },
            margins: { top: 160, bottom: 160, left: 80, right: 80 },
            children,
          });
        });

        out.push(new Table({
          width: { size: 9360, type: WidthType.DXA },
          rows: [new TableRow({ children: kpiCells })],
        }));
        out.push(new Paragraph({ spacing: { after: 240 } }));
        break;
      }

      // ── Quote Block ─────────────────────────────────────────────────────
      case 'quote_block': {
        const quote = item.quote || '';
        const attribution = item.attribution || '';
        const bg = item.background === 'none' ? WHITE : 'F9F9F9';

        out.push(new Table({
          width: { size: 9360, type: WidthType.DXA },
          rows: [
            new TableRow({
              children: [
                new TableCell({
                  borders: {
                    top: BDR, bottom: BDR, left: { style: BorderStyle.SINGLE, size: 18, color: YELLOW }, right: BDR,
                  },
                  shading: { fill: bg, type: ShadingType.CLEAR },
                  margins: { top: 200, bottom: 200, left: 240, right: 240 },
                  children: [
                    new Paragraph({
                      children: [new TextRun({ text: quote, font: 'Quicksand', size: 26, italics: true, color: DARK_GRAY })],
                      spacing: { after: 120 },
                    }),
                    attribution ? new Paragraph({
                      children: [new TextRun({ text: attribution, font: 'Quicksand', size: 20, color: '666666' })],
                    }) : null,
                  ].filter(Boolean),
                }),
              ],
            }),
          ],
        }));
        out.push(new Paragraph({ spacing: { after: 240 } }));
        break;
      }

      // ── Highlight Table ─────────────────────────────────────────────────
      case 'highlight_table': {
        const headers = item.headers || [];
        const rows = item.rows || [];
        const colCount = Math.max(headers.length, rows[0] ? rows[0].length : 0);
        if (colCount === 0) break;

        const totalW = 9360;
        const colWidths = (item.col_widths && item.col_widths.length === colCount)
                        ? item.col_widths
                        : Array(colCount).fill(Math.floor(totalW / colCount));
        const autoColor = item.auto_color_cols || [];
        const alignments = item.col_alignment || Array(colCount).fill('left');
        const isSummaryRow = item.summary_row === true;

        const hdrRow = new TableRow({
          children: headers.map((h, i) => new TableCell({
            borders : BDRS,
            width   : { size: colWidths[i] || 1000, type: WidthType.DXA },
            shading : { fill: YELLOW, type: ShadingType.CLEAR },
            margins : MRGN,
            children: [new Paragraph({
              alignment: alignments[i] === 'right' ? AlignmentType.RIGHT
                       : alignments[i] === 'center' ? AlignmentType.CENTER
                       :                              AlignmentType.LEFT,
              children: [new TextRun({ text: String(h), font: 'Quicksand', size: 20, bold: true, color: DARK_GRAY })]
            })]
          }))
        });

        const dataRows = rows.map((row, ri) => {
          const isLastRow = isSummaryRow && ri === rows.length - 1;
          return new TableRow({
            children: row.map((cell, ci) => {
              const cellVal = String(cell == null ? '' : cell);
              const autoGreen = autoColor.includes(ci) && cellVal.startsWith('+');
              const autoRed   = autoColor.includes(ci) && (cellVal.startsWith('-') || cellVal.startsWith('−'));
              const fill = isLastRow ? 'EEEEEE'
                           : autoGreen ? 'E9F5EC'
                           : autoRed   ? 'FDECEA'
                           : ri % 2 === 0 ? WHITE : 'F9F9F9';
              return new TableCell({
                borders : BDRS,
                width   : { size: colWidths[ci] || 1000, type: WidthType.DXA },
                shading : { fill, type: ShadingType.CLEAR },
                margins : MRGN,
                children: [new Paragraph({
                  alignment: alignments[ci] === 'right' ? AlignmentType.RIGHT
                           : alignments[ci] === 'center' ? AlignmentType.CENTER
                           :                              AlignmentType.LEFT,
                  children: [new TextRun({
                    text: cellVal,
                    font: 'Quicksand', size: isLastRow ? 20 : 20,
                    bold: isLastRow,
                    color: DARK_GRAY
                  })]
                })]
              });
            })
          });
        });

        out.push(new Table({ width: { size: totalW, type: WidthType.DXA }, rows: [hdrRow, ...dataRows] }));
        if (item.caption) {
          out.push(new Paragraph({
            spacing : { after: 240, before: 60 },
            children : [new TextRun({
              text    : item.caption,
              font    : 'Quicksand',
              size    : 18,
              italics : true,
              color   : '666666',
            })],
          }));
        } else {
          out.push(new Paragraph({ spacing: { after: 240 } }));
        }
        break;
      }

      // ── Two Column ──────────────────────────────────────────────────────
      case 'two_column': {
        const left = item.left || {};
        const right = item.right || {};
        const showDivider = item.divider === true;

        const colWidth = Math.floor(9360 / 2);
        const leftChildren = [];
        const rightChildren = [];

        if (left.heading) leftChildren.push(new Paragraph({
          heading: HeadingLevel.HEADING_3,
          children: [new TextRun(left.heading || '')]
        }));
        if (left.body) leftChildren.push(new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({ text: left.body || '', font: 'Quicksand', size: 22, color: DARK_GRAY })]
        }));

        if (right.heading) rightChildren.push(new Paragraph({
          heading: HeadingLevel.HEADING_3,
          children: [new TextRun(right.heading || '')]
        }));
        if (right.body) rightChildren.push(new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({ text: right.body || '', font: 'Quicksand', size: 22, color: DARK_GRAY })]
        }));

        out.push(new Table({
          width: { size: 9360, type: WidthType.DXA },
          rows: [new TableRow({
            children: [
              new TableCell({
                borders: {
                  top: { style: BorderStyle.NONE },
                  bottom: { style: BorderStyle.NONE },
                  left: { style: BorderStyle.NONE },
                  right: showDivider ? { style: BorderStyle.SINGLE, size: 3, color: YELLOW } : { style: BorderStyle.NONE },
                },
                width: { size: colWidth, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: 0, right: showDivider ? 200 : 0 },
                children: leftChildren,
              }),
              new TableCell({
                borders: {
                  top: { style: BorderStyle.NONE },
                  bottom: { style: BorderStyle.NONE },
                  left: { style: BorderStyle.NONE },
                  right: { style: BorderStyle.NONE },
                },
                width: { size: colWidth, type: WidthType.DXA },
                margins: { top: 40, bottom: 40, left: showDivider ? 200 : 0, right: 0 },
                children: rightChildren,
              }),
            ],
          })],
        }));
        out.push(new Paragraph({ spacing: { after: 240 } }));
        break;
      }

      // ── Heading ─────────────────────────────────────────────────────────
      case 'heading': {
        const lvl = item.level === 2 ? HeadingLevel.HEADING_2
                  : item.level === 3 ? HeadingLevel.HEADING_3
                  :                    HeadingLevel.HEADING_1;
        out.push(new Paragraph({ heading: lvl, children: [new TextRun(item.text || '')] }));
        break;
      }

      // ── Body paragraph (plain or mixed runs) ─────────────────────────────
      case 'paragraph': {
        let runs;
        if (Array.isArray(item.runs) && item.runs.length > 0) {
          runs = item.runs.map(r => new TextRun({
            text    : r.text    || '',
            bold    : r.bold    || false,
            italics : r.italics || false,
            color   : r.color   || DARK_GRAY,
            font    : 'Quicksand',
            size    : 22,
          }));
        } else {
          runs = [new TextRun({ text: item.text || '', font: 'Quicksand', size: 22, color: DARK_GRAY })];
        }
        out.push(new Paragraph({ spacing: { after: 200 }, children: runs }));
        break;
      }

      // ── Bullet list ───────────────────────────────────────────────────────
      case 'bullets': {
        for (const b of (item.items || [])) {
          out.push(new Paragraph({
            numbering : { reference: 'bullets', level: 0 },
            children  : [new TextRun({ text: b, font: 'Quicksand', size: 22, color: DARK_GRAY })]
          }));
        }
        break;
      }

      // ── Numbered list ─────────────────────────────────────────────────────
      case 'numbered': {
        for (const n of (item.items || [])) {
          out.push(new Paragraph({
            numbering : { reference: 'numbers', level: 0 },
            children  : [new TextRun({ text: n, font: 'Quicksand', size: 22, color: DARK_GRAY })]
          }));
        }
        break;
      }

      // ── Data table ────────────────────────────────────────────────────────
      case 'table': {
        const headers  = item.headers || [];
        const rows     = item.rows    || [];
        const colCount = Math.max(headers.length, rows[0] ? rows[0].length : 0);
        if (colCount === 0) break;
        const totalW    = 9360;
        const colWidths = (item.col_widths && item.col_widths.length === colCount)
                        ? item.col_widths
                        : Array(colCount).fill(Math.floor(totalW / colCount));

        const hdrRow = new TableRow({
          children: headers.map((h, i) => new TableCell({
            borders : BDRS,
            width   : { size: colWidths[i] || 1000, type: WidthType.DXA },
            shading : { fill: YELLOW, type: ShadingType.CLEAR },
            margins : MRGN,
            children: [new Paragraph({
              children: [new TextRun({ text: String(h), font: 'Quicksand', size: 20, bold: true, color: DARK_GRAY })]
            })]
          }))
        });

        const dataRows = rows.map((row, ri) => {
          const fill = ri % 2 === 0 ? WHITE : 'F9F9F9';
          return new TableRow({
            children: row.map((cell, ci) => new TableCell({
              borders : BDRS,
              width   : { size: colWidths[ci] || 1000, type: WidthType.DXA },
              shading : { fill, type: ShadingType.CLEAR },
              margins : MRGN,
              children: [new Paragraph({
                children: [new TextRun({ text: String(cell == null ? '' : cell), font: 'Quicksand', size: 20, color: DARK_GRAY })]
              })]
            }))
          });
        });

        out.push(new Table({ width: { size: totalW, type: WidthType.DXA }, rows: [hdrRow, ...dataRows] }));
        out.push(new Paragraph({ spacing: { after: 240 } }));
        break;
      }

      // ── Yellow divider ────────────────────────────────────────────────────
      case 'divider': {
        out.push(new Paragraph({
          border  : { bottom: { style: BorderStyle.SINGLE, size: 12, color: item.color || YELLOW, space: 1 } },
          spacing : { after: 240 }
        }));
        break;
      }

      // ── Empty spacer ──────────────────────────────────────────────────────
      case 'spacer': {
        out.push(new Paragraph({ spacing: { after: item.size || 240 } }));
        break;
      }

      // ── Hard page break ───────────────────────────────────────────────────
      case 'page_break': {
        out.push(new Paragraph({ children: [new PageBreak()] }));
        break;
      }

      // ── Embedded image (base64 data resolved by Python before Node runs) ──
      // The Python layer resolves file_id → base64 before invoking Node,
      // so this case only needs to handle the inline `data` field.
      // ── Chart/Plot Injection from sandbox artifacts ────────────────────────
      // ── Table of Contents ───────────────────────────────────────────────
      case 'toc': {
        const depth = item.depth || 2;
        const title = item.title || 'TABLE OF CONTENTS';

        out.push(new Paragraph({
          heading: HeadingLevel.HEADING_2,
          children: [new TextRun(title)],
        }));

        // TOC field code with depth limit (1 = H1 only, 2 = H1+H2, 3 = H1+H2+H3)
        const tocField = `TOC \\o "${depth}-${depth}" \\h \\z \\u`;
        out.push(new Paragraph({
          spacing: { after: 360 },
          children: [
            new TextRun({ text: 'Generating table of contents...', italics: true, color: '666666' }),
            // Word will populate this on first open
          ],
        }));
        break;
      }

      // ── Chart ───────────────────────────────────────────────────────────
      case 'chart': {
        // Same logic as image, just an alias for chart artifacts from sandbox
        if (!item.data) break;
        try {
          const imgBuf = Buffer.from(item.data, 'base64');
          const width  = item.width  || 560;
          const height = item.height || Math.round(width * 0.6);
          const fmt    = (item.format || 'png').toLowerCase();
          const validFmt = ['png','jpg','jpeg','gif','bmp','svg'].includes(fmt) ? fmt : 'png';
          const imgRun = new ImageRun({
            data           : imgBuf,
            transformation : { width, height },
            type           : validFmt,
          });
          out.push(new Paragraph({
            alignment : item.align === 'center' ? AlignmentType.CENTER
                       : item.align === 'right' ? AlignmentType.RIGHT
                       :                          AlignmentType.LEFT,
            children  : [imgRun],
            spacing   : { after: item.caption ? 60 : 240 },
          }));
          if (item.caption) {
            out.push(new Paragraph({
              spacing  : { after: 240 },
              children : [new TextRun({
                text    : item.caption,
                font    : 'Quicksand',
                size    : 18,
                italics : true,
                color   : '666666',
              })],
            }));
          }
        } catch (imgErr) {
          process.stderr.write('WARN: chart section failed: ' + imgErr.message + '\n');
        }
        break;
      }

      // ── Image ─────────────────────────────────────────────────────────────
      case 'image': {
        if (!item.data) break;   // no data = silently skip
        try {
          const imgBuf = Buffer.from(item.data, 'base64');
          const width  = item.width  || 400;
          const height = item.height || Math.round(width * 0.75);  // 4:3 default
          const fmt    = (item.format || 'png').toLowerCase();
          // docx ImageRun type must be one of: png, jpg, jpeg, gif, bmp, svg
          const validFmt = ['png','jpg','jpeg','gif','bmp','svg'].includes(fmt) ? fmt : 'png';
          const imgRun = new ImageRun({
            data           : imgBuf,
            transformation : { width, height },
            type           : validFmt,
          });
          out.push(new Paragraph({
            alignment : item.align === 'center' ? AlignmentType.CENTER
                       : item.align === 'right' ? AlignmentType.RIGHT
                       :                          AlignmentType.LEFT,
            children  : [imgRun],
            spacing   : { after: item.caption ? 60 : 240 },
          }));
          // Optional caption below the image
          if (item.caption) {
            out.push(new Paragraph({
              spacing  : { after: 240 },
              children : [new TextRun({
                text    : item.caption,
                font    : 'Quicksand',
                size    : 18,
                italics : true,
                color   : '666666',
              })],
            }));
          }
        } catch (imgErr) {
          process.stderr.write('WARN: image section failed: ' + imgErr.message + '\n');
        }
        break;
      }

      default:
        // Unknown type — silently skip
        break;
    }
  }
  return out;
}

// ── Disclosure block ──────────────────────────────────────────────────────
function buildDisclosure() {
  const txt = spec.disclosure_text ||
    'This document is prepared by and is the property of Potomac. It is circulated for ' +
    'informational and educational purposes only. There is no consideration given to the ' +
    'specific investment needs, objectives, or tolerances of any of the recipients. ' +
    'Recipients should consult their own advisors before making any investment decisions. ' +
    'Past performance is not indicative of future results. For complete disclosures, please ' +
    'visit potomac.com/disclosures.';
  return [
    new Paragraph({
      border  : { bottom: { style: BorderStyle.SINGLE, size: 12, color: YELLOW, space: 1 } },
      spacing : { after: 240 }
    }),
    new Paragraph({
      children: [new TextRun({ text: 'IMPORTANT DISCLOSURES', font: 'Rajdhani', size: 22, bold: true, allCaps: true, color: DARK_GRAY })]
    }),
    new Paragraph({
      spacing : { after: 0 },
      children: [new TextRun({ text: txt, font: 'Quicksand', size: 18, color: '666666', italics: true })]
    }),
  ];
}

// ── Assemble document ─────────────────────────────────────────────────────
const bodyChildren = [
  ...buildTitlePage(),
  ...buildContent(spec.sections),
  ...(spec.include_disclosure !== false ? buildDisclosure() : []),
];

const doc = new Document({
  styles: {
    default: { document: { run: { font: 'Quicksand', size: 22, color: DARK_GRAY } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Rajdhani', size: 36, bold: true, color: DARK_GRAY, allCaps: true },
        paragraph: { spacing: { before: 480, after: 240 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Rajdhani', size: 28, bold: true, color: DARK_GRAY, allCaps: true },
        paragraph: { spacing: { before: 360, after: 180 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Rajdhani', size: 24, bold: true, color: DARK_GRAY, allCaps: true },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: 'bullets',
        levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: 'numbers',
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    properties: {
      page: {
        size   : { width: 12240, height: 15840 },
        margin : { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    headers : { default: makeHeader() },
    footers : { default: makeFooter() },
    children: bodyChildren,
  }]
});

Packer.toBuffer(doc)
  .then(buf => {
    const outName = spec.filename || 'output.docx';
    fs.writeFileSync(outName, buf);
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

class DocxResult:
    """Lightweight result container from DocxSandbox.generate()."""
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

def _ensure_docx_modules() -> Optional[Path]:
    """
    Ensure the ``docx`` npm package is installed in the persistent cache dir.

    First call installs once (takes ~30 s). Subsequent calls return instantly
    after confirming the ``node_modules/docx`` directory exists.

    Returns the ``node_modules`` Path, or ``None`` on failure.
    """
    modules   = _DOCX_CACHE_DIR / "node_modules"
    docx_pkg  = modules / "docx"

    if docx_pkg.exists():
        logger.debug("docx node_modules cache hit: %s", modules)
        return modules

    logger.info("First-time docx install — this takes ~30 s…")
    _DOCX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pkg = {"name": "docx-cache", "version": "1.0.0", "dependencies": {"docx": "^8.5.0"}}
    (_DOCX_CACHE_DIR / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    proc = subprocess.run(
        ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
        cwd=str(_DOCX_CACHE_DIR),
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0:
        logger.error(
            "npm install (docx) failed (rc=%d): %s",
            proc.returncode, proc.stderr.decode(errors="replace").strip(),
        )
        return None

    logger.info("docx package installed → %s", modules)
    return modules


# =============================================================================
# Image section resolver — converts file_id → inline base64
# =============================================================================

def _resolve_image_sections(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Walk all sections and resolve ``{"type": "image", "file_id": "<uuid>"}``
    items to ``{"type": "image", "data": "<base64>", "format": "<ext>"}`` so
    that ``document_builder.js`` can embed them directly.

    Sections that already have a ``data`` field are left untouched.
    Sections with an unknown / unavailable ``file_id`` are silently skipped
    (the image case in JS will skip items without ``data``).

    Also handles sections from user-uploaded files retrieved via the upload
    route — these may use ``/upload/files/{file_id}/download`` IDs which map
    to the same ``file_store`` lookup path.

    Returns a **copy** of *spec* with the resolved sections.
    """
    import base64
    import copy

    spec = copy.deepcopy(spec)
    sections = spec.get("sections", [])
    if not sections:
        return spec

    needs_resolve = any(
        (s.get("type") == "image" or s.get("type") == "chart") and "file_id" in s and "data" not in s
        for s in sections
    )
    if not needs_resolve:
        return spec

    try:
        from core.file_store import get_file
    except ImportError:
        logger.warning("file_store unavailable — image sections with file_id will be skipped")
        return spec

    for section in sections:
        if section.get("type") not in ("image", "chart"):
            continue
        if "data" in section:
            continue  # already has inline base64 — no lookup needed
        file_id = section.get("file_id", "").strip()
        if not file_id:
            continue

        try:
            entry = get_file(file_id)
            if entry and entry.data:
                section["data"]   = base64.b64encode(entry.data).decode("ascii")
                section["format"] = entry.file_type or (
                    entry.filename.rsplit(".", 1)[-1].lower() if "." in entry.filename else "png"
                )
                logger.info(
                    "Resolved image file_id %s → %s (%.1f KB)",
                    file_id, entry.filename, entry.size_kb,
                )
            else:
                logger.warning("Image file_id %s not found in file_store — section will be skipped", file_id)
        except Exception as exc:
            logger.warning("Could not resolve image file_id %s: %s", file_id, exc)

    spec["sections"] = sections
    return spec


# =============================================================================
# DocxSandbox
# =============================================================================

class DocxSandbox:
    """
    Generates Potomac-branded .docx files from a structured spec dict.

    The spec describes the entire document layout; no code generation by the
    LLM is required.  The embedded ``_BUILDER_SCRIPT`` (a self-contained
    Node.js program) translates the spec into a ``docx`` Document object and
    writes ``output.docx``.

    Concurrency
    -----------
    Each call gets its own ``tempfile.mkdtemp()`` directory, so multiple
    concurrent invocations are safe.  The ``node_modules`` cache is read-only
    from the point of view of each invocation (symlinked, not copied).
    """

    def generate(self, spec: Dict[str, Any], timeout: int = 90) -> DocxResult:
        """
        Generate a ``.docx`` file from *spec*.

        Parameters
        ----------
        spec : dict
            Document specification.  Required keys: ``title``, ``sections``.
            See the ``generate_docx`` tool schema for the full definition.
        timeout : int
            Maximum seconds allowed for Node.js execution (default 90).

        Returns
        -------
        DocxResult
        """
        start    = time.time()
        temp_dir : Optional[Path] = None

        try:
            # ── 0. Resolve image file_id → base64 before touching temp dir ─
            spec = _resolve_image_sections(spec)

            # ── 1. npm cache ───────────────────────────────────────────────
            modules_path = _ensure_docx_modules()
            if modules_path is None:
                return DocxResult(False, error="docx npm package unavailable — npm install failed")

            # ── 2. Isolated temp workspace ─────────────────────────────────
            temp_dir    = Path(tempfile.mkdtemp(prefix="docx_gen_"))
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
                logger.warning("No Potomac logo assets found at %s — document will have no logo", _ASSETS_DIR)

            # ── 4. Write spec + builder ────────────────────────────────────
            (temp_dir / "spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temp_dir / "document_builder.js").write_text(_BUILDER_SCRIPT, encoding="utf-8")
            (temp_dir / "package.json").write_text(
                json.dumps({"name": "docx-gen", "version": "1.0.0"}), encoding="utf-8"
            )

            # ── 5. Symlink node_modules from cache (O(1)) ──────────────────
            nm_link = temp_dir / "node_modules"
            try:
                os.symlink(str(modules_path), str(nm_link))
            except OSError:
                # Cross-device or permission error → fall back to copying
                logger.debug("symlink failed, falling back to copytree for node_modules")
                shutil.copytree(str(modules_path), str(nm_link))

            # ── 6. Execute Node.js ─────────────────────────────────────────
            proc = subprocess.run(
                ["node", "document_builder.js"],
                cwd=str(temp_dir),
                capture_output=True,
                timeout=timeout,
            )

            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()

            if proc.returncode != 0:
                return DocxResult(
                    False,
                    error=f"Node.js builder failed: {stderr or stdout}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )

            # ── 7. Retrieve generated file ─────────────────────────────────
            filename = spec.get("filename") or "output.docx"
            out_path = temp_dir / filename

            if not out_path.exists():
                docx_files = sorted(temp_dir.glob("*.docx"))
                if docx_files:
                    out_path = docx_files[0]
                    filename = out_path.name
                else:
                    return DocxResult(
                        False,
                        error=f"Output .docx not found. stdout={stdout!r}  stderr={stderr!r}",
                        exec_time_ms=round((time.time() - start) * 1000, 2),
                    )

            data    = out_path.read_bytes()
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "DocxSandbox ✓  %s  (%.1f KB, %.0f ms)",
                filename, len(data) / 1024, elapsed,
            )
            return DocxResult(True, data=data, filename=filename, exec_time_ms=elapsed)

        except subprocess.TimeoutExpired:
            return DocxResult(
                False,
                error=f"Node.js timed out after {timeout} s",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except FileNotFoundError:
            return DocxResult(
                False,
                error="Node.js not found — ensure node is installed and on PATH",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as exc:
            logger.error("DocxSandbox error: %s", exc, exc_info=True)
            return DocxResult(
                False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
