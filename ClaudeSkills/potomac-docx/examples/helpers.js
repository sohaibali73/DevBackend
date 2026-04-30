/**
 * Potomac Document Helpers — shared utilities for all 17 templates
 * Use these in every document generation script.
 *
 * LOGO SETUP (CRITICAL):
 *   Always use EPS-converted clean PNGs — NOT the original PNGs (black background).
 *   Convert EPS → PNG first if clean PNGs are not pre-converted:
 *
 *     gs -dNOPAUSE -dBATCH -dSAFER -sDEVICE=pngalpha -r300 -dEPSCrop \
 *        -sOutputFile="/home/claude/Potomac_Logo_clean.png" \
 *        "/path/to/Potomac_Logo.eps"
 *
 *   Then load:
 *     const logoStandard = fs.readFileSync('/home/claude/Potomac_Logo_clean.png');
 *     const logoBlack    = fs.readFileSync('/home/claude/Potomac_Logo_Black_clean.png');
 *     const logoWhite    = fs.readFileSync('/home/claude/Potomac_Logo_White_clean.png');
 */

const {
  Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle,
  WidthType, ShadingType, LevelFormat, VerticalAlign, PageNumber
} = require('docx');

// ── Brand constants ───────────────────────────────────────────────────────────
const YELLOW    = 'FEC00F';
const DARK_GRAY = '212121';
const MID_GRAY  = 'CCCCCC';
const WHITE     = 'FFFFFF';
const GREEN     = '27AE60';
const RED       = 'C0392B';

// ── Document styles ───────────────────────────────────────────────────────────
function getStyles() {
  return {
    default: { document: { run: { font: 'Quicksand', size: 22, color: DARK_GRAY } } },
    paragraphStyles: [
      { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:36, bold:true, color:DARK_GRAY, allCaps:true },
        paragraph:{ spacing:{ before:480, after:240 }, outlineLevel:0 } },
      { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:28, bold:true, color:DARK_GRAY, allCaps:true },
        paragraph:{ spacing:{ before:360, after:180 }, outlineLevel:1 } },
      { id:'Heading3', name:'Heading 3', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:24, bold:true, color:DARK_GRAY, allCaps:true },
        paragraph:{ spacing:{ before:240, after:120 }, outlineLevel:2 } },
    ]
  };
}

// ── Numbering config ──────────────────────────────────────────────────────────
function getNumbering() {
  return { config: [
    { reference:'bullets', levels:[{ level:0, format:LevelFormat.BULLET, text:'\u2022',
        alignment:AlignmentType.LEFT, style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
    { reference:'numbers', levels:[{ level:0, format:LevelFormat.DECIMAL, text:'%1.',
        alignment:AlignmentType.LEFT, style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
  ]};
}

// ── Page properties (US Letter, 1" margins) ───────────────────────────────────
function pageProps(margins = { top:1440, right:1440, bottom:1440, left:1440 }) {
  return { page:{ size:{ width:12240, height:15840 }, margin: margins } };
}

// ── Header with logo + yellow underline ───────────────────────────────────────
// logoBuffer: use logoStandard for most docs, logoBlack for formal/legal
// lineColor:  YELLOW (default) or DARK_GRAY for formal docs
function stdHeader(logoBuffer, lineColor = YELLOW) {
  return new Header({ children:[
    new Paragraph({
      children:[ new ImageRun({ data:logoBuffer, transformation:{ width:130, height:27 }, type:'png' }) ],
      border:{ bottom:{ style:BorderStyle.SINGLE, size:6, color:lineColor, space:4 } }
    })
  ]});
}

// ── Footer with page numbers ──────────────────────────────────────────────────
function stdFooter(leftText = 'Potomac  |  \u00AE') {
  return new Footer({ children:[
    new Paragraph({
      border:{ top:{ style:BorderStyle.SINGLE, size:3, color:MID_GRAY, space:4 } },
      children:[
        new TextRun({ text: leftText + '  |  Page ', font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ children:[PageNumber.CURRENT], font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ text:' of ', font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ children:[PageNumber.TOTAL_PAGES], font:'Quicksand', size:18, color:'999999' }),
      ]
    })
  ]});
}

// ── Yellow divider line ───────────────────────────────────────────────────────
function divider(color = YELLOW) {
  return new Paragraph({
    border:{ bottom:{ style:BorderStyle.SINGLE, size:12, color, space:1 } },
    spacing:{ after:240 }
  });
}

// ── Body paragraph ────────────────────────────────────────────────────────────
function body(text, opts = {}) {
  return new Paragraph({ spacing:{ after:200 }, children:[
    new TextRun({ text, font:'Quicksand', size:22,
      color: opts.color || DARK_GRAY,
      bold: opts.bold || false,
      italics: opts.italics || false })
  ]});
}

// ── Empty spacer ──────────────────────────────────────────────────────────────
function spacer(after = 240) { return new Paragraph({ spacing:{ after } }); }

// ── Standard disclosure footer block ─────────────────────────────────────────
function disclosure() {
  return [
    divider(),
    new Paragraph({ children:[new TextRun({ text:'IMPORTANT DISCLOSURES', font:'Rajdhani', size:22, bold:true, allCaps:true, color:DARK_GRAY })] }),
    new Paragraph({ spacing:{ after:0 }, children:[new TextRun({
      text:'This document is prepared by and is the property of Potomac. It is circulated for informational and educational purposes only. There is no consideration given to the specific investment needs, objectives, or tolerances of any of the recipients. Recipients should consult their own advisors before making any investment decisions. Past performance is not indicative of future results. For complete disclosures, please visit potomac.com/disclosures.',
      font:'Quicksand', size:18, color:'666666', italics:true
    })] }),
  ];
}

// ── Table cell helpers ────────────────────────────────────────────────────────
const bdr = { style:BorderStyle.SINGLE, size:1, color:MID_GRAY };
const borders = { top:bdr, bottom:bdr, left:bdr, right:bdr };

// Yellow header cell
function hCell(text, w) {
  return new TableCell({ borders, width:{ size:w, type:WidthType.DXA },
    shading:{ fill:YELLOW, type:ShadingType.CLEAR },
    margins:{ top:80, bottom:80, left:120, right:120 },
    children:[new Paragraph({ children:[new TextRun({ text, font:'Quicksand', size:20, bold:true, color:DARK_GRAY })] })]
  });
}

// Alternating white/light-gray data cell
function dCell(text, rowIndex, w, opts = {}) {
  const fill = rowIndex % 2 === 0 ? WHITE : 'F9F9F9';
  return new TableCell({ borders, width:{ size:w, type:WidthType.DXA },
    shading:{ fill, type:ShadingType.CLEAR },
    margins:{ top:80, bottom:80, left:120, right:120 },
    children:[new Paragraph({ children:[new TextRun({ text, font:'Quicksand', size:20,
      color: opts.color || DARK_GRAY, bold: opts.bold || false })] })]
  });
}

// Bullet list paragraph
function bullet(text) {
  return new Paragraph({ numbering:{ reference:'bullets', level:0 },
    children:[new TextRun({ text, font:'Quicksand', size:22, color:DARK_GRAY })] });
}

// Numbered list paragraph
function numbered(text) {
  return new Paragraph({ numbering:{ reference:'numbers', level:0 },
    children:[new TextRun({ text, font:'Quicksand', size:22, color:DARK_GRAY })] });
}

module.exports = {
  YELLOW, DARK_GRAY, MID_GRAY, WHITE, GREEN, RED,
  getStyles, getNumbering, pageProps,
  stdHeader, stdFooter, divider, body, spacer, disclosure,
  borders, hCell, dCell, bullet, numbered
};
