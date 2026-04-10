# DOCX Skill Upgrade Plan — "Replace Entry-Level Staff"
*Analyst by Potomac · Backend Engineering · April 2026*

---

## Executive Summary

The current `generate_docx` tool produces valid, branded Word documents but is
limited to a single-column page layout with 8 basic section types.  Entry-level
staff at a financial firm spend 60–80 % of their time:

1. **Filling in named templates** (fact sheets, commentaries, performance reports)
2. **Formatting numbers correctly** (%, $, bps, commas)
3. **Doing conditional table formatting** (red for negative, green for positive)
4. **Assembling data from multiple sources** into one polished document
5. **Ensuring brand consistency** across every page

The upgrade has four phases, ordered by business impact.  Each phase is
independently shippable.

---

## Phase 1 — New Section Types (1–2 days)
*Expand the `_BUILDER_SCRIPT` in `docx_sandbox.py`.*

### 1a. `callout` — Highlighted Info Box
A yellow-bordered box with an optional icon for key stats, warnings, or tips.
```json
{
  "type": "callout",
  "style": "yellow",          // "yellow" | "dark" | "light"
  "icon": "⚡",               // optional emoji prefix
  "title": "KEY INSIGHT",
  "body": "Active management outperformed in 8 of the last 10 bear markets."
}
```
**How:** `docx` Table with 1 row / 1 cell, `shading: { fill: "FEF3CD" }`,
left border `{ color: YELLOW, size: 20 }`.

---

### 1b. `kpi_row` — Horizontal KPI Metrics Strip
A row of 2–4 large numbers with labels, like a dashboard header.
```json
{
  "type": "kpi_row",
  "metrics": [
    { "value": "12.4%", "label": "YTD Return",       "delta": "+2.1%", "positive": true },
    { "value": "$4.2B", "label": "AUM",               "delta": "+$0.3B" },
    { "value": "0.71",  "label": "Sharpe Ratio" },
    { "value": "−8.3%", "label": "Max Drawdown",      "positive": false }
  ]
}
```
**How:** 1-row Table, each cell has a large Rajdhani number run + small Quicksand label.
Positive deltas get green color `"2D7D46"`, negative get red `"C0392B"`.

---

### 1c. `quote_block` — Pull Quote / Testimonial
Left yellow bar accent, italic large text, attribution line.
```json
{
  "type": "quote_block",
  "quote": "Traditional diversification has entered a bear market.",
  "attribution": "— Meb Faber, Cambria Investment Management",
  "background": "light"    // "light" | "none"
}
```

---

### 1d. `highlight_table` — Conditional Color Table
Full table with per-cell color overrides for positive/negative/neutral.
```json
{
  "type": "highlight_table",
  "headers": ["Strategy", "YTD", "1Y", "3Y", "5Y"],
  "rows": [
    ["Potomac Core",      "+14.2%", "+11.8%", "+9.4%",  "+10.2%"],
    ["S&P 500",           "+12.1%", "+10.3%", "+10.7%", "+13.8%"],
    ["60/40 Benchmark",   "+6.3%",  "+4.1%",  "+5.2%",  "+6.0%"]
  ],
  "auto_color_cols": [1, 2, 3, 4],  // columns to auto-green/red by sign
  "col_alignment": ["left", "right", "right", "right", "right"],
  "summary_row": true     // last row gets bold dark-gray styling
}
```
**How:** Parse each cell value — if it starts with `+` → light green background
`"E9F5EC"`, if `−` or `-` → light red `"FDECEA"`, else white.

---

### 1e. `two_column` — Side-by-Side Text Blocks
Two text columns without using a table — rendered as a 2-column Word section.
```json
{
  "type": "two_column",
  "left": {
    "heading": "BULL CASE",
    "body": "Earnings growth remains resilient..."
  },
  "right": {
    "heading": "BEAR CASE",
    "body": "Rate sensitivity and valuation..."
  },
  "divider": true   // yellow vertical divider between columns
}
```

---

### 1f. `hyperlink` — Clickable URLs in Paragraphs
```json
{
  "type": "paragraph",
  "runs": [
    { "text": "For complete disclosures, visit " },
    { "text": "potomac.com/disclosures", "hyperlink": "https://potomac.com/disclosures",
      "color": "FEC00F", "bold": true }
  ]
}
```

---

### 1g. `footnote` — Inline Reference Numbers
```json
{
  "type": "paragraph",
  "text": "The portfolio returned 12.4%¹ over the trailing 12 months.",
  "footnotes": ["¹ Net of fees as of 12/31/2025. Past performance is not indicative of future results."]
}
```
Footnotes are collected and auto-appended at the bottom of the page.

---

### 1h. `toc` — Auto Table of Contents
```json
{ "type": "toc", "depth": 2, "title": "TABLE OF CONTENTS" }
```
Uses Word's built-in TOC field (`{TOC \o "1-2" \h \z}`).  User hits F9 in Word
to refresh.

---

### 1i. Nested Lists (2 levels)
```json
{
  "type": "bullets",
  "items": [
    "Top-level point A",
    { "text": "Top-level point B", "sub_items": ["Sub-point 1", "Sub-point 2"] },
    "Top-level point C"
  ]
}
```

---

### 1j. Table Enhancements
Add optional fields to existing `table` type:
- `col_alignment: ["left","right","right"]` — per-column text alignment
- `summary_row: true` — makes last row bold dark-gray
- `totals_label: "TOTAL"` — auto-appends a SUM row
- `cell_colors: [[null, "E9F5EC", "FDECEA"]]` — per-cell override
- `caption: "Table 1. Performance vs Benchmark"` — italic caption below table
- `row_height: 400` — force row height (twips)

---

## Phase 2 — Template Engine (2–3 days)
*Named document templates that auto-populate the `sections` structure.*

Add `template` field to `generate_docx` input.  When provided, the handler
pre-populates a full sections scaffold; the LLM only needs to supply data.

### Templates

| Template Key | Document Type | Potomac Use Case |
|---|---|---|
| `fund_fact_sheet` | 2-page fact sheet | Monthly fund summary with KPIs + table |
| `market_commentary` | 3–5 page commentary | Monthly market outlook |
| `performance_report` | 4–6 page report | Quarterly performance attribution |
| `client_letter` | 1–2 page letter | Personalized client correspondence |
| `research_report` | 5–10 page paper | White paper / research publication |
| `proposal` | 5–8 page proposal | New client investment proposal |
| `trade_rationale` | 1–2 page memo | Trade decision documentation |
| `meeting_minutes` | 1–3 page memo | Meeting record and action items |
| `onboarding_packet` | 3–5 pages | New client welcome document |
| `quarterly_review` | 4–8 pages | Quarterly portfolio review letter |

### How Templates Work

```python
# In handle_generate_docx():
template_key = tool_input.get("template")
if template_key:
    base_spec = DOCX_TEMPLATES[template_key]
    # Deep merge: template provides structure, LLM provides data
    spec = deep_merge(base_spec, tool_input)
```

Each template is a dict in `core/tools_v2/docx_templates.py` with:
- Pre-built title page layout (cover page style specific to the doc type)
- Section scaffolding (Executive Summary → Analysis → Conclusion → Disclosures)
- Document-specific disclosure text
- Suggested KPI positions (fact sheets always have a 4-up KPI row at top)
- Branded cover page image position

#### Example: `fund_fact_sheet` Template Structure
```
COVER PAGE
  → Potomac logo (large, center)
  → Fund name (H1)
  → Tagline + date
  → Yellow divider

PAGE 1
  → [kpi_row: 4 metrics — AUM, YTD, Sharpe, Max DD]
  → [two_column: Fund Overview (left) | Key Characteristics (right)]
  → [highlight_table: Performance vs Benchmark — YTD/1Y/3Y/5Y/Since Inception]
  → [table: Holdings / Allocation]

PAGE 2
  → [heading: PORTFOLIO COMMENTARY]
  → [paragraph: Monthly commentary text]
  → [callout: Key Risk Factors]
  → [footnote_paragraph: Data sources and calculation methodology]
  → DISCLOSURES
```

---

## Phase 3 — Data Integration (2–3 days)

### 3a. Auto-Number Formatting
The builder auto-detects and formats common financial values:
- Values ending in `%` → right-align, color by sign
- Values starting with `$` → right-align with 2 decimal places
- Integers > 999 → auto-comma format
- `bps` suffix → show in basis points with tooltip

Add to tool input: `auto_format: true` (default `true`)

### 3b. Excel → DOCX Table (xlsx file_id → table section)
```json
{
  "type": "table_from_xlsx",
  "file_id": "<xlsx-file-id>",
  "sheet": "PERFORMANCE",     // sheet name or index
  "range": "A1:F10",          // optional cell range
  "header_row": true,
  "auto_color": true
}
```
Python resolves the file_id → reads xlsx with openpyxl → builds a `highlight_table`
section automatically.

### 3c. Chart/Plot Injection from sandbox
```json
{
  "type": "chart",
  "source": "matplotlib",     // "matplotlib" | "plotly" | "base64"
  "artifact_id": "<artifact-id>",   // from a prior sandbox execution
  "width": 460,
  "height": 260,
  "caption": "Figure 1. Rolling 12-Month Returns vs Benchmark"
}
```
Python resolves the artifact → embeds as a PNG ImageRun.

### 3d. `generate_docx_revision` — Edit an Existing DOCX
New tool that takes an existing `file_id` (a previously generated docx) and
applies structured changes:
```json
{
  "file_id": "<existing-docx-id>",
  "changes": [
    { "operation": "replace_text",  "find": "Q3 2025",  "replace": "Q4 2025" },
    { "operation": "update_table",  "table_index": 0,   "rows": [[...new data...]] },
    { "operation": "append_section", "section": { "type": "paragraph", "text": "..." } }
  ]
}
```
Engine: Python `python-docx` (not Node.js) for reading; Node.js for final re-render.

### 3e. Mail Merge Mode
```json
{
  "template": "client_letter",
  "mail_merge": true,
  "records": [
    { "client_name": "John Smith",  "account_value": "$1,245,000", "ytd": "+11.2%" },
    { "client_name": "Jane Doe",    "account_value": "$842,500",   "ytd": "+9.8%" }
  ]
}
```
Returns multiple file_ids, one per record.  The LLM describes the template once;
the handler stamps it N times with each record's data.

---

## Phase 4 — Document Intelligence (3–5 days)

### 4a. `generate_docx_from_text`
New tool: takes raw unstructured text → GPT auto-structures it → generates docx.
```json
{
  "name": "generate_docx_from_text",
  "raw_text": "The market has been volatile...[2000 words]...",
  "template": "research_report",
  "auto_structure": true    // Claude chunks into heading + paragraph sections
}
```

### 4b. `enhance_docx`
Takes an existing docx file_id → extracts text → re-renders with full Potomac
brand + improvements applied. Useful for "rebrand this document."

### 4c. `generate_docx_from_url`
Fetches a URL, strips HTML, extracts content, generates a Potomac-branded report.
```json
{
  "name": "generate_docx_from_url",
  "url": "https://federalreserve.gov/monetarypolicy/files/...",
  "template": "research_report"
}
```

### 4d. Document Comparison
```json
{
  "name": "compare_documents",
  "file_id_a": "<docx-id>",
  "file_id_b": "<docx-id>",
  "output": "redlined_docx"    // or "summary_text"
}
```

---

## Implementation Order (Recommended)

```
Week 1
  [x] Phase 1a–1j  — New section types (callout, kpi_row, highlight_table,
                       two_column, hyperlink, footnote, toc, nested bullets,
                       table enhancements)
  
Week 2
  [ ] Phase 2       — Template engine + 10 named templates
                      (fund_fact_sheet, market_commentary, performance_report,
                       client_letter, research_report, proposal, trade_rationale,
                       meeting_minutes, onboarding_packet, quarterly_review)

Week 3
  [ ] Phase 3a–3c   — Auto-number formatting, xlsx→table, chart injection
  [ ] Phase 3d      — generate_docx_revision tool
  
Week 4
  [ ] Phase 3e      — Mail merge mode
  [ ] Phase 4a–4b   — generate_docx_from_text, enhance_docx
  [ ] Phase 4c–4d   — URL ingestion, document comparison
```

---

## Files to Create / Modify

| File | Change |
|---|---|
| `core/sandbox/docx_sandbox.py` | Expand `_BUILDER_SCRIPT` with 8 new section types |
| `core/tools_v2/document_tools.py` | Update `GENERATE_DOCX_TOOL_DEF` schema with new section types |
| `core/tools_v2/docx_templates.py` | NEW — 10 named template scaffolds |
| `core/tools_v2/xlsx_to_table.py` | NEW — xlsx file_id → highlight_table section |
| `api/routes/document_tools.py` | NEW — `generate_docx_revision`, `generate_docx_from_text` endpoints |
| `core/tools.py` | Register new tools in dispatch table |
| `Documentation/DOCX_TOOL_GUIDE.md` | Update with all new features |

---

## Success Metrics (Entry-Level Staff Replacement)

| Task | Before | After |
|---|---|---|
| Monthly fund fact sheet | 45 min manual Word work | 30 sec tool call |
| Market commentary with KPIs | 30 min + formatting | 15 sec |
| Client letter (mail merge, 50 clients) | 2 hours | 60 sec |
| Performance report with charts | 90 min | 45 sec |
| Research paper with TOC + footnotes | 2 hours | 60 sec |
| Branded proposal from raw notes | 1 hour | 30 sec |
| Rebrand existing document | 30 min | 20 sec |
