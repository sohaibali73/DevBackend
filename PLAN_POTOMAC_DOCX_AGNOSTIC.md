# Plan: Making potomac-docx Model Agnostic

## Current Architecture (Claude-Dependent)

```
User Request
    ↓
Claude (LLM) reads SKILL.md
    ↓
Claude writes JavaScript code using docx-js
    ↓
Claude Code Execution (Anthropic container)
    ↓
Node.js script generates .docx file
    ↓
Files API returns file_id
    ↓
Download .docx
```

### Claude-Specific Dependencies:
1. **`container=skill.to_container()`** — Anthropic's container system
2. **`CODE_EXECUTION_TOOL`** — Anthropic's code execution beta
3. **`betas=["code_execution_20250825", "files-api-2025-04-14"]`** — Anthropic beta features
4. **`SkillGateway`** — Wraps Anthropic's beta API
5. **`core.skills.py`** — Skill registry tied to Anthropic's container format

### Current Tech Stack:
- **Language:** JavaScript/Node.js
- **Library:** `docx` npm package (docx-js)
- **Logo handling:** Ghostscript EPS→PNG conversion
- **Helpers:** `examples/helpers.js` with shared utilities
- **Templates:** 17 document types, all using docx-js API

---

## Proposed Architecture (Model Agnostic)

```
User Request (any LLM: Claude, GPT, Gemini, Llama, etc.)
    ↓
LLM produces structured JSON (document plan)
    ↓
┌─────────────────────────────────────┐
│  Potomac DOCX Generator Service     │
│  (Standalone Node.js module)        │
│                                     │
│  Input:  JSON document plan         │
│  Output: .docx Buffer               │
│                                     │
│  Uses: docx-js (npm 'docx')         │
│  Brand: Embedded Potomac config     │
│  Logos: Local asset files           │
└─────────────────────────────────────┘
    ↓
File saved / returned to user
```

### Key Changes:
1. **Standalone Node.js module** — No Anthropic container needed
2. **JSON input interface** — Any LLM can produce the input
3. **Embedded brand config** — Colors, fonts, styles in code
4. **Local logo files** — Pre-converted clean PNGs (no Ghostscript at runtime)
5. **REST API endpoint** — Call from any backend

---

## Implementation Plan

### Phase 1: Core DOCX Generator Module

**File: `core/docx/generator.mjs`**

A standalone Node.js module that:
- Uses `docx` npm package (docx-js) to build documents
- Has Potomac brand guidelines hardcoded (matching helpers.js patterns exactly)
- Accepts a JSON document plan as input
- Returns .docx Buffer

```javascript
// core/docx/generator.mjs
import {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, HeadingLevel
} from 'docx';
import fs from 'fs';
import { BRAND, DOC_TYPE_FOOTERS } from './brand.mjs';
import { TEMPLATES } from './templates.mjs';

export class PotomacDocxGenerator {
  /**
   * Generate a .docx Buffer from a structured document plan.
   * 
   * @param {Object} plan - The document plan
   * @returns {Promise<Buffer>} The .docx file content
   */
  async generate(plan) {
    const sections = this._buildSections(plan);
    const logoBuffer = this._loadLogo(plan.logo_variant || 'standard');
    const footerText = plan.footer_text 
      || DOC_TYPE_FOOTERS[plan.doc_type] 
      || 'Potomac | Built to Conquer Risk®';

    const doc = new Document({
      styles: this._getStyles(),
      numbering: this._getNumbering(),
      sections: [{
        properties: {
          page: {
            size: { width: 12240, height: 15840 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
          }
        },
        headers: { default: this._stdHeader(logoBuffer) },
        footers: { default: this._stdFooter(footerText) },
        children: sections
      }]
    });

    return Packer.toBuffer(doc);
  }

  // ... helper methods matching helpers.js patterns
}
```

### Phase 2: Brand Configuration

**File: `core/docx/brand.mjs`**

Extracted from SKILL.md and helpers.js — exact same constants:

```javascript
// core/docx/brand.mjs
export const YELLOW    = 'FEC00F';
export const DARK_GRAY = '212121';
export const MID_GRAY  = 'CCCCCC';
export const WHITE     = 'FFFFFF';

export const BRAND = {
  company_name: 'Potomac',
  tagline: 'Built to Conquer Risk®',
  colors: {
    primary: YELLOW,
    text: DARK_GRAY,
    mid_gray: MID_GRAY,
    light_gray: 'F9F9F9',
    white: WHITE,
    green: '27AE60',
    red: 'C0392B',
  },
  fonts: {
    header: 'Rajdhani',
    body: 'Quicksand',
  },
  sizes: {
    h1: 36,   // 18pt in docx-js half-points
    h2: 28,   // 14pt
    h3: 24,   // 12pt
    body: 22, // 11pt
    small: 18,// 9pt
  },
  page: {
    width: 12240,   // US Letter
    height: 15840,
    margin: 1440,   // 1 inch
  },
  logos: {
    standard: 'assets/Potomac_Logo_clean.png',
    black: 'assets/Potomac_Logo_Black_clean.png',
    white: 'assets/Potomac_Logo_White_clean.png',
  },
  disclosures: {
    default: 'This document is prepared by and is the property of Potomac. '
      + 'It is circulated for informational and educational purposes only. '
      + 'There is no consideration given to the specific investment needs, '
      + 'objectives, or tolerances of any of the recipients. Recipients '
      + 'should consult their own advisors before making any investment '
      + 'decisions. Past performance is not indicative of future results. '
      + 'For complete disclosures, please visit potomac.com/disclosures.',
  }
};

export const DOC_TYPE_FOOTERS = {
  fund_fact_sheet:    'Potomac | For Advisor Use Only',
  market_commentary:  'Potomac | Built to Conquer Risk®',
  quarterly_report:   'Potomac | For Client Use Only',
  risk_report:        'Potomac | INTERNAL RISK REPORT',
  trade_rationale:    'Potomac | INTERNAL — TRADE DOCUMENTATION',
  ips:                'Potomac | CONFIDENTIAL',
  ddq:                'Potomac | CONFIDENTIAL — DDQ',
  legal:              'CONFIDENTIAL | Potomac',
  research_report:    'Potomac | Built to Conquer Risk®',
  client_proposal:    'Potomac | Confidential | Built to Conquer Risk®',
  sop:                'SOP | Potomac | INTERNAL USE ONLY',
  technical:          'Potomac Technical Documentation | CONFIDENTIAL',
  invoice:            'Potomac | Built to Conquer Risk®',
  general:            'Potomac | Built to Conquer Risk®',
};
```

### Phase 3: Template System

**File: `core/docx/templates.mjs`**

Pre-built section structures for all 17 document types:

```javascript
// core/docx/templates.mjs
export const TEMPLATES = {
  fund_fact_sheet: {
    sections: [
      { type: 'heading1', text: 'FUND FACT SHEET' },
      { type: 'spacer' },
      { type: 'heading2', text: 'FUND SNAPSHOT' },
      { type: 'table', headers: ['Metric', 'Value'], rows: [] },
      { type: 'spacer' },
      { type: 'heading2', text: 'PERFORMANCE SUMMARY' },
      { type: 'table', headers: ['Period', 'Fund', 'Benchmark'], rows: [] },
      { type: 'spacer' },
      { type: 'heading2', text: 'TOP HOLDINGS' },
      { type: 'table', headers: ['Ticker', 'Asset Class', 'Weight', 'Direction'], rows: [] },
      { type: 'spacer' },
      { type: 'disclosure' },
    ]
  },
  research_report: {
    sections: [
      { type: 'heading1', text: '{{title}}' },
      { type: 'paragraph', text: '{{date}}', italics: true },
      { type: 'spacer' },
      { type: 'heading2', text: 'EXECUTIVE SUMMARY' },
      { type: 'paragraph', text: '{{summary}}' },
      { type: 'spacer' },
      { type: 'heading2', text: 'KEY FINDINGS' },
      { type: 'bullet_list', items: [] },
      { type: 'spacer' },
      { type: 'heading2', text: 'CONCLUSION' },
      { type: 'paragraph', text: '{{conclusion}}' },
      { type: 'spacer' },
      { type: 'disclosure' },
    ]
  },
  // ... all 17 templates
};
```

### Phase 4: API Integration (Node.js)

**File: `api/routes/docx.mjs`**

```javascript
// api/routes/docx.mjs
import express from 'express';
import { PotomacDocxGenerator } from '../../core/docx/generator.mjs';

const router = express.Router();
const generator = new PotomacDocxGenerator();

router.post('/generate', async (req, res) => {
  try {
    const plan = req.body;
    const buffer = await generator.generate(plan);
    const filename = (plan.title || 'Document').replace(/\s+/g, '_');
    
    res.set({
      'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'Content-Disposition': `attachment; filename="${filename}.docx"`,
    });
    res.send(buffer);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

router.post('/generate-from-text', async (req, res) => {
  try {
    const { description, doc_type = 'general' } = req.body;
    
    // Step 1: Use any LLM to convert description → JSON plan
    const plan = await llmToDocumentPlan(description, doc_type);
    
    // Step 2: Generate the docx
    const buffer = await generator.generate(plan);
    
    res.set({ /* headers */ });
    res.send(buffer);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

export default router;
```

### Phase 5: LLM Integration Layer

**File: `core/docx/planner.mjs`**

This is the key model-agnostic piece — converts natural language to structured JSON:

```javascript
// core/docx/planner.mjs
import { TEMPLATES } from './templates.mjs';

export async function llmToDocumentPlan(description, docType, llmClient = null) {
  const systemPrompt = `You are a document structure planner for Potomac fund management.

Convert the user's request into a structured JSON document plan.

Document Type: ${docType}

Available section types:
- heading1, heading2, heading3 (text required)
- paragraph (text required, optional: bold, italics)
- bullet_list (items: array of strings)
- numbered_list (items: array of strings)
- table (headers: array, rows: array of arrays)
- spacer
- disclosure (auto-generates Potomac disclosures)

Return ONLY valid JSON matching this schema:
{
  "doc_type": "${docType}",
  "title": "Document Title",
  "subtitle": "Optional",
  "footer_text": "auto" or custom,
  "logo_variant": "standard" | "black" | "white",
  "sections": [...]
}`;

  if (llmClient) {
    const response = await llmClient.generate({
      system: systemPrompt,
      user: description,
      responseFormat: 'json',
    });
    return JSON.parse(response);
  }

  // Fallback: return template with placeholders
  return TEMPLATES[docType] || TEMPLATES.general;
}
```

---

## File Structure

```
core/docx/
├── generator.mjs          # Main generator class (docx-js)
├── brand.mjs              # Potomac brand constants
├── templates.mjs          # 17 document type templates
├── planner.mjs            # LLM → JSON plan converter
└── helpers.mjs            # Shared utilities (tables, headers, etc.)

assets/
├── Potomac_Logo_clean.png
├── Potomac_Logo_Black_clean.png
└── Potomac_Logo_White_clean.png

api/routes/
└── docx.mjs               # REST API endpoints
```

---

## Usage Examples

### From any LLM (Claude, GPT, Gemini, etc.):

```javascript
// LLM produces this JSON (any model can do this)
const documentPlan = {
  doc_type: "research_report",
  title: "Bear Market in Diversification",
  subtitle: "February 2026",
  logo_variant: "standard",
  sections: [
    { type: "heading1", text: "BEAR MARKET IN DIVERSIFICATION" },
    { type: "paragraph", text: "February 2026", italics: true },
    { type: "spacer" },
    { type: "heading2", text: "EXECUTIVE SUMMARY" },
    { type: "paragraph", text: "The most recent 10-15 years have been a historic run..." },
    { type: "spacer" },
    { type: "heading2", text: "KEY FINDINGS" },
    { type: "bullet_list", items: [
      "10-year rolling returns for S&P 500 are at historic peaks",
      "Traditional diversifiers have severely underperformed",
      "Historical patterns suggest future returns will be challenging"
    ]},
    { type: "spacer" },
    { type: "heading2", text: "PERFORMANCE DATA" },
    { type: "table",
      headers: ["Asset", "10-Year", "15-Year", "Max DD"],
      rows: [
        ["S&P 500", "11.10%", "11.76%", "-33.92%"],
        ["Gold (GLD)", "-1.26%", "-0.42%", "-23.31%"],
        ["Bonds (AGG)", "-1.14%", "2.63%", "-48.35%"]
      ]},
    { type: "spacer" },
    { type: "heading2", text: "CONCLUSION" },
    { type: "paragraph", text: "Tactical strategies that actively manage risk may provide..." },
    { type: "disclosure" }
  ]
};

// Generate the docx
const generator = new PotomacDocxGenerator();
const buffer = await generator.generate(documentPlan);

// Save
fs.writeFileSync('output.docx', buffer);
```

### Via REST API:

```bash
curl -X POST http://localhost:8000/docx/generate \
  -H "Content-Type: application/json" \
  -d @document_plan.json \
  --output document.docx
```

---

## Migration Path

1. **Keep existing Claude skill working** — Don't break current functionality
2. **Add standalone generator** — New `core/docx/generator.mjs`
3. **Add API endpoint** — New `/docx/generate` route
4. **Update tools.py** — Add `generate_docx` tool that uses the standalone generator
5. **Test with multiple LLMs** — Verify JSON → DOCX works with Claude, GPT, Gemini
6. **Deprecate Claude-specific path** — Once stable, remove container dependency

---

## Benefits

| Aspect | Before (Claude-only) | After (Model Agnostic) |
|--------|---------------------|----------------------|
| LLM Support | Claude only | Any LLM |
| Code Execution | Anthropic container | Not needed |
| API Dependencies | Anthropic betas | None |
| Deployment | Claude Code | Any server |
| Cost | Anthropic API + container | docx-js only |
| Speed | ~30-60s (LLM writes code) | ~1-2s (direct generation) |
| Reliability | Depends on LLM code quality | Deterministic |

---

## Dependencies

```json
// package.json additions
{
  "dependencies": {
    "docx": "^9.1.0"
  }
}
```

---

## Testing Strategy

1. **Unit tests** for each document type template
2. **Brand compliance tests** — Verify colors, fonts, sizes match SKILL.md
3. **Cross-LLM tests** — Same JSON plan, same output regardless of LLM
4. **Performance tests** — Generate 100 documents, measure time
5. **Visual regression** — Compare generated docs against reference templates from SKILL.md
