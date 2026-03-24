---
name: potomac-docx
description: Create professional Potomac-branded Word documents (.docx files) for any business purpose. Potomac is a tactical fund manager — documents include fund fact sheets, market commentaries, performance reports, risk reports, trade rationale, investment policy statements, DDQs, advisor onboarding guides, research write-ups, legal agreements, technical docs, SOPs, invoices, marketing materials, internal memos, client proposals, and general-purpose documents. Use whenever the user requests any Word document for Potomac, regardless of type.
---

# Potomac Word Document Creator

Create professional, brand-compliant Word documents for Potomac across all 17 document types. Potomac is a **tactical fund manager** — "Built to Conquer Risk®".

---

## CRITICAL: Logo Setup (Read First)

The original PNG logos (`Potomac_Logo.png`, etc.) have a **solid black background** and must NOT be used directly in documents. Always use the **EPS-converted clean PNGs** with transparent backgrounds.

### Logo Files (Transparent — Use These)

| File | Use When |
|------|----------|
| `assets/Potomac_Logo_clean.png` | Standard — most documents (yellow icon + dark text) |
| `assets/Potomac_Logo_Black_clean.png` | Formal/legal documents (all dark) |
| `assets/Potomac_Logo_White_clean.png` | Dark background contexts (white + yellow) |

### If Clean PNGs Are Not Pre-converted

Convert from EPS using Ghostscript (always prefer this over the original PNGs):

```bash
# Install ghostscript if needed
apt-get install -y ghostscript

# Convert each EPS to transparent PNG
gs -dNOPAUSE -dBATCH -dSAFER -sDEVICE=pngalpha -r300 -dEPSCrop \
   -sOutputFile="/home/claude/Potomac_Logo_clean.png" \
   "/mnt/user-data/uploads/Potomac_Logo.eps"

gs -dNOPAUSE -dBATCH -dSAFER -sDEVICE=pngalpha -r300 -dEPSCrop \
   -sOutputFile="/home/claude/Potomac_Logo_Black_clean.png" \
   "/mnt/user-data/uploads/Potomac_Logo_Black.eps"

gs -dNOPAUSE -dBATCH -dSAFER -sDEVICE=pngalpha -r300 -dEPSCrop \
   -sOutputFile="/home/claude/Potomac_Logo_White_clean.png" \
   "/mnt/user-data/uploads/Potomac_Logo_White.eps"
```

Then load in your script:
```javascript
const logoStandard = fs.readFileSync('/home/claude/Potomac_Logo_clean.png');
const logoBlack    = fs.readFileSync('/home/claude/Potomac_Logo_Black_clean.png');
const logoWhite    = fs.readFileSync('/home/claude/Potomac_Logo_White_clean.png');
```

---

## Brand Guidelines

| Element | Spec |
|---------|------|
| **Company name** | "Potomac" — never "Potomac Fund Management" |
| **Tagline** | "Built to Conquer Risk®" (® symbol required) |
| **Primary color** | Yellow `#FEC00F` — headers, dividers, table headers, accents |
| **Text color** | Dark Gray `#212121` |
| **Header font** | Rajdhani — ALL CAPS, bold |
| **Body font** | Quicksand — 11pt (size: 22 in docx-js) |
| **H1 size** | 18pt (size: 36) |
| **H2 size** | 14pt (size: 28) |
| **H3 size** | 12pt (size: 24) |
| **Page size** | US Letter: 12240 x 15840 DXA |
| **Margins** | 1 inch all sides: 1440 DXA |

---

## The 17 Templates

All 17 templates have been built, tested, and are available in `/mnt/user-data/outputs/`. When a user asks for one of these document types, use the corresponding template as the structural reference. When building from scratch, match its section structure exactly.

### Client-Facing Documents

| # | Template File | Use For |
|---|--------------|---------|
| 1 | `Potomac_Fund_Fact_Sheet.docx` | Monthly/quarterly fund snapshot: AUM, performance, risk stats, top holdings, risk profile gauge |
| 2 | `Potomac_Monthly_Market_Commentary.docx` | Monthly macro + tactical positioning narrative for clients and advisors |
| 3 | `Potomac_Quarterly_Performance_Report.docx` | Formal quarterly review: PM letter, attribution, drawdown, factor exposures, outlook |
| 4 | `Potomac_Client_Proposal_Template.docx` | New business proposals: value prop, deliverables, pricing, next steps |
| 5 | `Potomac_Research_Template.docx` | Research reports, white papers, market analysis |

### Internal & Compliance Documents

| # | Template File | Use For |
|---|--------------|---------|
| 6 | `Potomac_Risk_Report.docx` | Internal risk dashboard: VaR, stress tests, factor exposure, liquidity buckets |
| 7 | `Potomac_Trade_Rationale.docx` | Trade documentation: thesis, risk/reward scenarios, stop levels, approval signatures |
| 8 | `Potomac_Investment_Policy_Statement.docx` | Client IPS: objectives, allocation ranges, risk limits, reporting cadence, signatures |
| 9 | `Potomac_Internal_Memo_Template.docx` | Internal communications with action item tracker |
| 10 | `Potomac_SOP_Template.docx` | Standard operating procedures with roles, steps, QC checkpoints |
| 11 | `Potomac_Legal_Document_Template.docx` | Agreements, NDAs, contracts with signature blocks |

### Advisor & Operations Documents

| # | Template File | Use For |
|---|--------------|---------|
| 12 | `Potomac_Due_Diligence_Questionnaire.docx` | Institutional DDQ: firm overview, strategy, risk management, operations |
| 13 | `Potomac_Advisor_Onboarding_Guide.docx` | New advisor partner guide: checklist, team contacts, strategies, platform access |
| 14 | `Potomac_Invoice_Template.docx` | Billing: line items, totals, payment terms, wire details |

### Marketing & Technical Documents

| # | Template File | Use For |
|---|--------------|---------|
| 15 | `Potomac_Marketing_Template.docx` | Campaign briefs, content calendars, KPI tracking |
| 16 | `Potomac_Technical_Template.docx` | Technical specs, system documentation, version history |

### General Purpose

| # | Template File | Use For |
|---|--------------|---------|
| 17 | `Potomac_General_Purpose_Template.docx` | Any document that doesn't fit another category — fully branded blank template |

---

## Workflow

### Step 1: Identify the document type

Match the user's request to one of the 17 templates above. If unclear, use the General Purpose template or ask.

### Step 2: Read the docx skill

```bash
view /mnt/skills/public/docx/SKILL.md
```

### Step 3: Convert logos (if not already done this session)

Check whether `/home/claude/Potomac_Logo_clean.png` exists. If not, run the Ghostscript conversion from the Logo Setup section above.

### Step 4: Build the document using docx-js

Use the shared code patterns below. Every document must use the same styles, numbering, header, footer, and disclosure block.

### Step 5: Output — save to /tmp/

**Always** save to `/tmp/` so the file is accessible via the Files API:

```javascript
const outputPath = "/tmp/Potomac_[DocumentName].docx";

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outputPath, buf);
  // The ONLY line that should appear on stdout:
  console.log("DONE:" + outputPath);
}).catch(err => {
  console.error("PACK_ERROR:", err);
  process.exit(1);
});
```

**CRITICAL — stdout discipline:** The Node.js script must **never** use
`console.log()` for anything other than the single `DONE:` sentinel above.
Use `console.error()` for all diagnostics (stderr is not captured as file
content). Any extra stdout — file-path listings, progress messages, `ls`
output, JSON dumps — will be captured and can corrupt the document returned
to callers. This means:

- No `console.log("Reading skill...")` 
- No `console.log(JSON.stringify(doc))`
- No printing directory listings to stdout
- No `process.stdout.write(...)` anywhere except the final sentinel

---

## Reusable Code Patterns

These patterns are used across all 17 templates. Copy them directly.

### Document Structure (every document)

```javascript
const doc = new Document({
  styles: getStyles(),
  numbering: getNumbering(),
  sections:[{
    properties:{ page:{ size:{ width:12240, height:15840 }, margin:{ top:1440, right:1440, bottom:1440, left:1440 } } },
    headers:{ default: stdHeader(logoStandard) },
    footers:{ default: stdFooter('Potomac  |  Built to Conquer Risk\u00AE') },
    children:[ /* content */ ]
  }]
});
```

### Styles

```javascript
function getStyles() {
  return {
    default: { document: { run: { font: 'Quicksand', size: 22, color: '212121' } } },
    paragraphStyles: [
      { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:36, bold:true, color:'212121', allCaps:true },
        paragraph:{ spacing:{ before:480, after:240 }, outlineLevel:0 } },
      { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:28, bold:true, color:'212121', allCaps:true },
        paragraph:{ spacing:{ before:360, after:180 }, outlineLevel:1 } },
      { id:'Heading3', name:'Heading 3', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ font:'Rajdhani', size:24, bold:true, color:'212121', allCaps:true },
        paragraph:{ spacing:{ before:240, after:120 }, outlineLevel:2 } },
    ]
  };
}
```

### Numbering Config

```javascript
function getNumbering() {
  return { config: [
    { reference:'bullets', levels:[{ level:0, format:LevelFormat.BULLET, text:'\u2022',
        alignment:AlignmentType.LEFT,
        style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
    { reference:'numbers', levels:[{ level:0, format:LevelFormat.DECIMAL, text:'%1.',
        alignment:AlignmentType.LEFT,
        style:{ paragraph:{ indent:{ left:720, hanging:360 } } } }] },
  ]};
}
```

### Header and Footer

```javascript
// Standard header — logo + yellow underline
function stdHeader(logoBuffer, lineColor = 'FEC00F') {
  return new Header({ children:[
    new Paragraph({
      children:[ new ImageRun({ data:logoBuffer, transformation:{ width:130, height:27 }, type:'png' }) ],
      border:{ bottom:{ style:BorderStyle.SINGLE, size:6, color:lineColor, space:4 } }
    })
  ]});
}

// Standard footer — left text + page X of Y
function stdFooter(leftText = 'Potomac  |  Built to Conquer Risk\u00AE') {
  return new Footer({ children:[
    new Paragraph({
      border:{ top:{ style:BorderStyle.SINGLE, size:3, color:'CCCCCC', space:4 } },
      children:[
        new TextRun({ text: leftText + '  |  Page ', font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ children:[PageNumber.CURRENT], font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ text:' of ', font:'Quicksand', size:18, color:'999999' }),
        new TextRun({ children:[PageNumber.TOTAL_PAGES], font:'Quicksand', size:18, color:'999999' }),
      ]
    })
  ]});
}
```

### Yellow Divider

```javascript
function divider() {
  return new Paragraph({
    border:{ bottom:{ style:BorderStyle.SINGLE, size:12, color:'FEC00F', space:1 } },
    spacing:{ after:240 }
  });
}
```

### Table Pattern (Yellow headers, alternating rows)

```javascript
// CRITICAL: Always set both table width AND columnWidths AND cell width
// Always use WidthType.DXA — never PERCENTAGE
// Always use ShadingType.CLEAR — never SOLID

const bdr = { style:BorderStyle.SINGLE, size:1, color:'CCCCCC' };
const borders = { top:bdr, bottom:bdr, left:bdr, right:bdr };

// Header cell (yellow background)
function hCell(text, w) {
  return new TableCell({ borders, width:{ size:w, type:WidthType.DXA },
    shading:{ fill:'FEC00F', type:ShadingType.CLEAR },
    margins:{ top:80, bottom:80, left:120, right:120 },
    children:[new Paragraph({ children:[
      new TextRun({ text, font:'Quicksand', size:20, bold:true, color:'212121' })
    ]})]
  });
}

// Data cell (alternating white/light gray)
function dCell(text, rowIndex, w, opts = {}) {
  return new TableCell({ borders, width:{ size:w, type:WidthType.DXA },
    shading:{ fill: rowIndex % 2 === 0 ? 'FFFFFF' : 'F9F9F9', type:ShadingType.CLEAR },
    margins:{ top:80, bottom:80, left:120, right:120 },
    children:[new Paragraph({ children:[
      new TextRun({ text, font:'Quicksand', size:20,
        color: opts.color || '212121', bold: opts.bold || false })
    ]})]
  });
}

// Example 3-column table
new Table({
  width:{ size:9360, type:WidthType.DXA },
  columnWidths:[3120, 3120, 3120],  // Must sum to table width
  rows:[
    new TableRow({ children:[ hCell('Column 1', 3120), hCell('Column 2', 3120), hCell('Column 3', 3120) ] }),
    new TableRow({ children:[ dCell('Value', 0, 3120), dCell('Value', 0, 3120), dCell('Value', 0, 3120) ] }),
    new TableRow({ children:[ dCell('Value', 1, 3120), dCell('Value', 1, 3120), dCell('Value', 1, 3120) ] }),
  ]
})
```

### Lists

```javascript
// Bullet
new Paragraph({ numbering:{ reference:'bullets', level:0 },
  children:[new TextRun({ text:'Bullet item', font:'Quicksand', size:22, color:'212121' })] })

// Numbered
new Paragraph({ numbering:{ reference:'numbers', level:0 },
  children:[new TextRun({ text:'Step 1 item', font:'Quicksand', size:22, color:'212121' })] })
```

### Disclosure Block (required on every document)

```javascript
function disclosure() {
  return [
    new Paragraph({
      border:{ bottom:{ style:BorderStyle.SINGLE, size:12, color:'FEC00F', space:1 } },
      spacing:{ after:240 }
    }),
    new Paragraph({ children:[new TextRun({ text:'IMPORTANT DISCLOSURES',
      font:'Rajdhani', size:22, bold:true, allCaps:true, color:'212121' })] }),
    new Paragraph({ children:[new TextRun({
      text:'This document is prepared by and is the property of Potomac. It is circulated for informational and educational purposes only. There is no consideration given to the specific investment needs, objectives, or tolerances of any of the recipients. Recipients should consult their own advisors before making any investment decisions. Past performance is not indicative of future results. For complete disclosures, please visit potomac.com/disclosures.',
      font:'Quicksand', size:18, color:'666666', italics:true
    })] }),
  ];
}
```

---

## Document-Type Section Structures

Use these as the canonical section structure for each document type.

### Fund Fact Sheet
- Fund Snapshot table (AUM, benchmark, fees, inception, min investment)
- Strategy Overview + Investment Objective + Risk Profile gauge (side-by-side two-column layout)
- Performance Summary table (MTD / QTD / YTD / 1Yr / 3Yr / Inception vs benchmark)
- Risk Statistics table (Sharpe, Max Drawdown, Volatility, Beta, Alpha)
- Top Holdings table (ticker, asset class, weight, direction)
- Disclosures

### Monthly Market Commentary
- Market Conditions at a Glance table (asset class, MTD return, signal, trend)
- Macro Environment (Economic Conditions / Fed Policy / Geopolitical Risks)
- Tactical Positioning + Allocation Changes table (prior weight / new weight / change / rationale)
- Fund Performance narrative
- Outlook and Forward Strategy + Key Risks bullets
- Disclosures

### Quarterly Performance Report
- Letter From the Portfolio Manager
- Performance Summary table (Q1/Q2/Q3/Q4/YTD/Inception vs benchmark + peer rank)
- Performance Attribution (Top 5 contributors + Bottom 5 detractors tables)
- Risk Review table (metrics vs policy limits, current vs prior quarter)
- Portfolio Snapshot table (asset class weights vs benchmark, active bets)
- Outlook for Next Quarter
- Disclosures

### Risk Report
- Risk Dashboard table (metric / current / limit / status / vs prior month)
- Factor Exposures table (market, size, value, momentum, quality, duration)
- Stress Test Results table (scenario / P&L impact / % impact / key driver)
- Liquidity Analysis table (T+1 / T+2-5 / T+6-30 / T+30+)
- Risk Commentary and Recommendations
- Disclosures

### Trade Rationale and Order Documentation
- Trade Details table (ticker, asset class, direction, size, weight, execution type, price, settlement)
- Investment Rationale (Thesis / Supporting Evidence bullets / Risk-Reward table: bull/base/bear)
- Risk Management table (stop loss / profit target / time stop / max position)
- Compliance and Approval table (PM / Risk / CIO signatures)
- Post-Trade Notes table (fill price, slippage, commission)
- Disclosures

### Investment Policy Statement
- Client Profile table
- Investment Objectives (Primary / Return Target / Risk Constraints table)
- Asset Allocation table (min/target/max/benchmark per asset class)
- Investment Guidelines (Permitted / Prohibited investments)
- Rebalancing Policy
- Reporting and Review table
- Acknowledgment and Signatures
- Disclosures

### Due Diligence Questionnaire
- Section 1: Firm Overview (7 Q&A items with left yellow border on answers)
- Section 2: Investment Strategy (7 Q&A items)
- Section 3: Risk Management (5 Q&A items)
- Section 4: Operations and Compliance (7 Q&A items)
- Disclosures

### Advisor Onboarding Guide
- Welcome letter
- Onboarding Checklist table (task / owner / due date)
- Your Potomac Team table (role / name / email / phone)
- Strategy Overview table
- Platform and Technology (numbered steps)
- Key Policies and Compliance bullets
- Disclosures

### Research Report
- Executive Summary
- Key Findings at a Glance table
- Background and Context
- Research Methodology (numbered)
- Analysis and Findings (multiple H2 sections)
- Conclusions and Recommendations (bullets)
- Disclosures

### Legal Document
- Parties section
- Definitions (numbered)
- Terms and Conditions (Scope / Compensation / Confidentiality)
- Termination
- Limitation of Liability
- Signature table
- Disclosures

### Internal Memo
- TO / FROM / CC / DATE / RE header table
- Summary
- Background
- Key Points bullets
- Action Items table (action / owner / due date)
- Next Steps
- Internal use footer note

### Client Proposal
- "Proposal For [Client]" title
- Executive Summary
- About Potomac
- Understanding Your Needs (bullets)
- Proposed Solution + Deliverables table
- Investment/Pricing table
- Next Steps (numbered)
- Disclosures

### Marketing Brief
- Campaign Overview table (name / objective / audience / period / budget / channels)
- Value Proposition + Key Messages bullets
- Content Calendar table
- Success Metrics and KPIs table
- Disclosures

### SOP
- Document info table (SOP number / department / version / effective date / approver)
- Purpose
- Scope
- Responsibilities table
- Procedure (numbered steps with sub-phases)
- Quality Control Checkpoints
- References and Related Documents
- Disclosures

### Technical Document
- Version History table
- Overview
- System Architecture + Components bullets
- Technical Specifications table
- Implementation Details (Prerequisites / Configuration)
- Testing and Validation
- Known Issues and Limitations
- Disclosures

### Invoice
- Logo + "INVOICE" side-by-side header (invoice #, date, due date)
- FROM / BILL TO side-by-side two-column layout
- Line Items table (description / qty / unit price / amount)
- Totals block (subtotal / tax / total due)
- Payment Terms
- Disclosures

### General Purpose
- Document Information table (purpose / audience / version / related docs)
- Sections 1-5 with placeholder content (paragraphs, bullets, table, numbered steps)
- Optional signature block
- Disclosures

---

## Logo and Footer Selection by Document Type

| Document Type | Logo | Header Line | Footer Text |
|--------------|------|-------------|-------------|
| Fund Fact Sheet | `logoStandard` | Yellow | `Potomac  \|  For Advisor Use Only` |
| Market Commentary | `logoStandard` | Yellow | `Potomac  \|  Built to Conquer Risk®` |
| Quarterly Report | `logoStandard` | Yellow | `Potomac  \|  For Client Use Only` |
| Risk Report | `logoStandard` | Yellow | `Potomac  \|  INTERNAL RISK REPORT` |
| Trade Rationale | `logoStandard` | Yellow | `Potomac  \|  INTERNAL — TRADE DOCUMENTATION` |
| IPS | `logoBlack` | Dark Gray `212121` | `Potomac  \|  CONFIDENTIAL` |
| DDQ | `logoBlack` | Dark Gray `212121` | `Potomac  \|  CONFIDENTIAL — DDQ` |
| Legal Document | `logoBlack` | Dark Gray `212121` | `CONFIDENTIAL  \|  Potomac` |
| Advisor Onboarding | `logoStandard` | Yellow | `Potomac  \|  Built to Conquer Risk®` |
| Research Report | `logoStandard` | Yellow | `Potomac  \|  Built to Conquer Risk®` |
| Client Proposal | `logoStandard` | Yellow | `Potomac  \|  Confidential  \|  Built to Conquer Risk®` |
| Marketing Brief | `logoStandard` | Yellow | `Potomac  \|  Built to Conquer Risk®` |
| SOP | `logoStandard` | Yellow | `SOP  \|  Potomac  \|  INTERNAL USE ONLY` |
| Technical Doc | `logoStandard` | Yellow | `Potomac Technical Documentation  \|  CONFIDENTIAL` |
| Invoice | `logoStandard` (body only) | N/A | Custom tagline footer |
| Internal Memo | `logoStandard` | Yellow | (no footer needed) |
| General Purpose | `logoStandard` | Yellow | `Potomac  \|  Built to Conquer Risk®` |

---

## Critical Rules (Never Violate)

1. **NEVER use the original PNG logos** — they have solid black backgrounds. Always use `*_clean.png` converted from EPS via Ghostscript.
2. **NEVER use `WidthType.PERCENTAGE`** in tables — it breaks in Google Docs. Always `WidthType.DXA`.
3. **NEVER use `ShadingType.SOLID`** — always `ShadingType.CLEAR`.
4. **NEVER use unicode bullets directly** (`• text`) — always use `LevelFormat.BULLET` in numbering config.
5. **NEVER use `\n` for line breaks** — use separate `Paragraph` elements.
6. **Always set BOTH** `columnWidths` on the table AND `width` on each cell (values must match).
7. **Always include disclosures** at the end of every document.
8. **Always use US Letter** page size: `width: 12240, height: 15840`.
9. **Company name is "Potomac"** — never "Potomac Fund Management" or any other variant.
10. **Past performance disclaimer** must be included in all investment-related documents.

---

## Quality Checklist

Before presenting any document:

- [ ] Clean transparent logo loaded — not original PNG (no black box)
- [ ] All headings: Rajdhani, ALL CAPS, bold
- [ ] Body text: Quicksand, 11pt
- [ ] Company name: "Potomac" throughout
- [ ] Yellow #FEC00F used for dividers, table headers, accents
- [ ] All tables: DXA widths, CLEAR shading, dual width spec (table + cell)
- [ ] Lists: numbering config used (no raw unicode bullets)
- [ ] Disclosures present at end
- [ ] Page size: US Letter (12240 x 15840)
- [ ] Footer text matches document type from table above
- [ ] File saved to `/mnt/user-data/outputs/Potomac_[Name].docx`

---

## Strategy Write-Up (Legacy Template Workflow)

For trading/investment strategy write-ups, if the user uploads `Potomac_WriteUp_Template_Final.docx`:

```bash
# Copy and unpack
cp /mnt/user-data/uploads/Potomac_WriteUp_Template_Final.docx /home/claude/working_document.docx
python scripts/office/unpack.py /home/claude/working_document.docx /home/claude/unpacked/
```

Gather these 9 sections from the user:
1. Strategy Title
2. Inspiration / Source
3. Core Thesis
4. Buy/Sell Parameters
5. AFL File Path
6. Excel Optimization File Path
7. Performance Statistics
8. The Call (viable / needs work / reject)
9. Risks & Limitations

Then use `str_replace` to fill in the XML and repack:

```bash
python scripts/office/pack.py /home/claude/unpacked/ /mnt/user-data/outputs/Strategy_WriteUp.docx --original /home/claude/working_document.docx
```
