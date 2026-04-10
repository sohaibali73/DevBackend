# Potomac Office Tools — Complete Integration Guide

Server-side document generation and intelligence tools. Zero Claude Skills containers. Zero API cost per document. All tools return branded, production-ready files in milliseconds.

---

## Architecture Overview

```
User Request
    │
    ▼
Claude (AI) selects tool
    │
    ▼
handle_tool_call() in core/tools.py
    │
    ├── generate_pptx  → PptxSandbox.generate()  → Node.js + pptxgenjs  → .pptx bytes
    ├── analyze_pptx   → PptxAnalyzer.analyze()  → python-pptx           → JSON profile
    ├── revise_pptx    → PptxReviser.revise()     → python-pptx           → .pptx bytes
    ├── generate_xlsx  → XlsxSandbox.generate()  → openpyxl              → .xlsx bytes
    ├── analyze_xlsx   → XlsxAnalyzer.analyze()  → pandas                → JSON profile
    ├── transform_xlsx → XlsxTransformer.transform() → pandas            → .xlsx bytes
    └── generate_docx  → DocxSandbox.generate()  → Node.js + docx npm   → .docx bytes
          │
          ▼
    store_file() → Railway volume + Supabase Storage
          │
          ▼
    /files/{uuid}/download   ← permanent download URL
```

**All files persist permanently** on Railway volume (fast) and Supabase Storage (backup). The download URL never expires.

---

## Download URL System

Every tool returns a `download_url` in the format `/files/{uuid}/download`.

The backend API route `GET /files/{file_id}/download` streams the file directly from Railway volume or Supabase. The Next.js frontend constructs the full URL:

```typescript
const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`
// e.g. https://your-railway-app.up.railway.app/files/550e8400-e29b-41d4-a716-446655440000/download
```

---

## Tool 1 — `generate_pptx`

**What it does:** Generates complete Potomac-branded PowerPoint presentations with 19 slide types.

**Performance:** 2–8 seconds (Node.js + pptxgenjs, first call installs npm ~45s once then cached)

**Files involved:**
- `core/sandbox/pptx_sandbox.py` — JS builder + Python orchestration
- `core/tools_v2/document_tools.py` — handler + tool def

### Tool Input Schema

```json
{
  "title": "POTOMAC Q2 2026 MARKET OUTLOOK",
  "filename": "Potomac_Q2_2026.pptx",
  "slides": [
    {
      "type": "title",
      "title": "Q2 2026 Market Outlook",
      "subtitle": "Navigating Uncertainty",
      "tagline": "Built to Conquer Risk®",
      "style": "executive"
    },
    {
      "type": "executive_summary",
      "headline": "POTOMAC OUTPERFORMED BY 420 BPS WITH 40% LOWER DRAWDOWN",
      "supporting_points": [
        "Strategy returned +12.4% vs. benchmark +8.2%",
        "Maximum drawdown -6.1% vs. benchmark -10.3%"
      ],
      "call_to_action": "Increase allocation ahead of Q3 volatility"
    },
    {
      "type": "table",
      "title": "Comparable Company Analysis",
      "headers": ["COMPANY", "EV/EBITDA", "P/E", "REV GROWTH"],
      "rows": [
        ["Apple Inc", "18.2x", "28.4x", "+8.3%"],
        ["Microsoft", "22.1x", "31.7x", "+11.2%"]
      ],
      "totals_row": {"label": "MEDIAN", "values": ["20.2x", "30.1x", "+9.8%"]},
      "number_cols": [2, 3, 4]
    },
    {
      "type": "chart",
      "title": "Revenue Bridge FY2024 → FY2025",
      "chart_type": "waterfall",
      "categories": ["FY2024", "Organic", "M&A", "FX", "FY2025"],
      "values": [100, 18, 12, -4, 126],
      "caption": "$ in millions"
    },
    {
      "type": "timeline",
      "title": "Transaction Timeline",
      "milestones": [
        {"date": "Jan 2026", "label": "LOI Signed", "status": "complete"},
        {"date": "Feb 2026", "label": "Due Diligence", "status": "in_progress"},
        {"date": "Mar 2026", "label": "Final Bid", "status": "upcoming"}
      ]
    },
    {
      "type": "scorecard",
      "title": "Project Health Dashboard",
      "items": [
        {"metric": "Budget", "status": "green", "value": "$2.1M / $2.5M", "comment": "On track"},
        {"metric": "Timeline", "status": "yellow", "value": "2 weeks behind", "comment": "Risk"},
        {"metric": "Scope", "status": "red", "value": "3 items added", "comment": "Escalation needed"}
      ]
    },
    {
      "type": "comparison",
      "title": "Why Potomac vs. Traditional Advisors",
      "left_label": "TRADITIONAL ADVISORS",
      "right_label": "POTOMAC",
      "winner": "right",
      "rows": [
        {"label": "Approach", "left": "Buy and hold", "right": "Tactical, risk-managed"},
        {"label": "Downside Protection", "left": "None", "right": "Active stops + hedges"}
      ]
    },
    {
      "type": "matrix_2x2",
      "title": "Strategic Portfolio Assessment",
      "x_label": "Market Share",
      "y_label": "Growth Rate",
      "quadrant_labels": ["Cash Cows", "Stars", "Dogs", "Question Marks"],
      "items": [
        {"label": "Product A", "x": 0.8, "y": 0.9, "size": 30},
        {"label": "Product B", "x": 0.2, "y": 0.3, "size": 15}
      ]
    },
    {
      "type": "icon_grid",
      "title": "Our Competitive Advantages",
      "columns": 3,
      "items": [
        {"icon": "shield", "title": "RISK MANAGEMENT", "body": "Proprietary drawdown controls"},
        {"icon": "chart", "title": "DATA-DRIVEN", "body": "Quantitative signal generation"},
        {"icon": "clock", "title": "REAL-TIME", "body": "Intraday portfolio monitoring"}
      ]
    },
    {
      "type": "cta",
      "title": "Let's Build Your Strategy",
      "action_text": "Ready to position your portfolio for the opportunities ahead?",
      "button_text": "SCHEDULE A CONSULTATION",
      "contact_info": "potomac.com  |  (305) 824-2702"
    }
  ]
}
```

### All 19 Slide Types

| Type | Key Fields | Use Case |
|---|---|---|
| `title` | title, subtitle, tagline, style (standard\|executive) | Opening slide |
| `content` | title, bullets:[str] or text:str | Bullet point slide |
| `two_column` | title, left_header, right_header, left_content, right_content | Side-by-side |
| `three_column` | title, column_headers:[str], columns:[str] | Triple layout |
| `metrics` | title, metrics:[{value,label}], context | KPI numbers |
| `process` | title, steps:[{title,description}] | Step flow |
| `quote` | quote, attribution, context | Pull quote |
| `section_divider` | title, description | Section break |
| `cta` | title, action_text, button_text, contact_info | Closing slide |
| `image` | file_id or data(base64), format, width, align, caption | Full image |
| `table` | title, headers, rows, number_cols, totals_row, caption | Data table |
| `chart` | title, chart_type, categories, values or series, caption | Native chart |
| `timeline` | title, milestones:[{date,label,status}], caption | Milestone timeline |
| `matrix_2x2` | title, x_label, y_label, quadrant_labels, items | BCG matrix |
| `scorecard` | title, items:[{metric,status,value,comment}] | RAG dashboard |
| `comparison` | title, left_label, right_label, winner, rows | Vs. table |
| `icon_grid` | title, items:[{icon,title,body}], columns | Feature grid |
| `executive_summary` | headline, supporting_points, call_to_action | So-what slide |
| `image_content` | title, image_side, file_id or image_search, bullets | Image + text |

**Chart types:** `bar`, `line`, `pie`, `donut`, `waterfall`, `clustered_bar`, `stacked_bar`, `area`, `scatter`

**Icon names:** `shield`, `chart`, `clock`, `star`, `check`, `lock`, `globe`, `dollar`, `people`, `trophy`, `lightning`, `target`

### Tool Output (JSON)

```json
{
  "status": "success",
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "Potomac_Q2_2026.pptx",
  "size_kb": 847.3,
  "download_url": "/files/550e8400-e29b-41d4-a716-446655440000/download",
  "exec_time_ms": 3240,
  "message": "✅ Presentation 'Potomac_Q2_2026.pptx' generated (847.3 KB, 10 slides).",
  "_tool_time_ms": 3241
}
```

### Next.js Frontend Component

```tsx
interface PptxResult {
  status: "success" | "error";
  file_id: string;
  filename: string;
  size_kb: number;
  download_url: string;
  exec_time_ms: number;
  message: string;
}

function PptxDownloadCard({ result }: { result: PptxResult }) {
  if (result.status !== "success") return null;
  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 bg-yellow-50 border border-yellow-200 rounded-xl">
      <div className="text-3xl">📊</div>
      <div className="flex-1">
        <p className="font-semibold text-gray-900">{result.filename}</p>
        <p className="text-sm text-gray-500">
          PowerPoint · {result.size_kb.toFixed(1)} KB · {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a
        href={downloadUrl}
        download={result.filename}
        className="px-4 py-2 bg-yellow-400 hover:bg-yellow-500 text-gray-900 font-semibold rounded-lg text-sm"
      >
        Download .pptx
      </a>
    </div>
  );
}
```

---

## Tool 2 — `analyze_pptx`

**What it does:** Reads any uploaded .pptx and returns a full structural profile + brand compliance score. Call this before revising an existing deck.

**Performance:** 50–300ms (pure python-pptx, no subprocess)

### Tool Input

```json
{
  "file_id": "uuid-of-uploaded-pptx"
}
```

### Tool Output

```json
{
  "status": "success",
  "file_id": "uuid-of-uploaded-pptx",
  "filename": "Potomac_Q1_2026.pptx",
  "exec_time_ms": 87.4,
  "profile": {
    "filename": "Potomac_Q1_2026.pptx",
    "slide_count": 24,
    "all_text": "Q1 2026 MARKET OUTLOOK | Executive Summary | Key Market Themes | ...",
    "slides": [
      {
        "index": 1,
        "title": "Q1 2026 MARKET OUTLOOK",
        "text_blocks": ["Q1 2026 MARKET OUTLOOK", "Navigating Uncertainty", "Built to Conquer Risk®"],
        "has_images": true,
        "has_tables": false,
        "table_data": [],
        "shape_count": 7
      },
      {
        "index": 2,
        "title": "EXECUTIVE SUMMARY",
        "text_blocks": ["EXECUTIVE SUMMARY", "Portfolio returned +12.4%", "Sharpe ratio 1.42"],
        "has_images": false,
        "has_tables": false,
        "table_data": [],
        "shape_count": 5
      }
    ],
    "brand_compliance": {
      "score": 92,
      "violations": [
        {"slide": 8, "issue": "Off-brand font color #FF0000", "shape": "TextBox 12"},
        {"slide": 15, "issue": "Off-brand fill color #336699", "shape": "Rectangle 3"}
      ]
    }
  },
  "message": "✅ Presentation analyzed. 24 slides found. Brand compliance: 92%."
}
```

### Next.js Usage Pattern

```tsx
// After user uploads a .pptx file, call analyze_pptx to understand its structure
// Then Claude can intelligently revise, extend, or reformat it

function PptxAnalysisCard({ profile }: { profile: any }) {
  return (
    <div className="p-4 border rounded-xl">
      <h3 className="font-bold">{profile.filename}</h3>
      <p>{profile.slide_count} slides · Brand compliance: {profile.brand_compliance.score}%</p>
      {profile.brand_compliance.violations.length > 0 && (
        <div className="mt-2 text-red-600 text-sm">
          {profile.brand_compliance.violations.length} brand violations found
        </div>
      )}
      <div className="mt-3 space-y-1">
        {profile.slides.slice(0, 5).map((slide: any) => (
          <div key={slide.index} className="text-sm text-gray-600">
            Slide {slide.index}: {slide.title}
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Tool 3 — `revise_pptx`

**What it does:** Apply targeted revisions to an existing .pptx in < 500ms. The single biggest time saver — IB analysts spend 80% of their time updating numbers in decks.

**Performance:** 100–500ms (python-pptx, instant for find_replace operations)

### Tool Input

```json
{
  "file_id": "uuid-of-existing-pptx",
  "output_filename": "Potomac_Q2_2026_Update.pptx",
  "revisions": [
    {
      "type": "find_replace",
      "find": "Q1 2025",
      "replace": "Q2 2025"
    },
    {
      "type": "find_replace",
      "find": "+8.2%",
      "replace": "+11.4%"
    },
    {
      "type": "find_replace",
      "find": "$2.1B AUM",
      "replace": "$2.4B AUM"
    },
    {
      "type": "update_table",
      "slide_index": 7,
      "row": 2,
      "col": 3,
      "value": "14.2x"
    },
    {
      "type": "delete_slide",
      "slide_index": 11
    },
    {
      "type": "reorder_slides",
      "order": [0, 1, 2, 5, 3, 4, 6, 7]
    },
    {
      "type": "append_slides",
      "slides": [
        {
          "type": "chart",
          "title": "Q2 2025 Performance",
          "chart_type": "bar",
          "categories": ["Jan", "Feb", "Mar"],
          "values": [0.052, 0.038, 0.061]
        }
      ]
    }
  ]
}
```

### Supported Operations

| Operation | Fields | Description |
|---|---|---|
| `find_replace` | find, replace | Replace ALL occurrences across entire deck (text + tables) |
| `update_slide` | slide_index, slide:{type,...} | Replace slide content with new spec |
| `append_slides` | slides:[{type,...}] | Add new slides to end of deck |
| `delete_slide` | slide_index | Remove a slide (0-based index) |
| `reorder_slides` | order:[int,...] | Reorder slides by new index array |
| `update_table` | slide_index, row, col, value | Update single table cell |

### Tool Output

```json
{
  "status": "success",
  "file_id": "new-uuid-for-revised-deck",
  "filename": "Potomac_Q2_2026_Update.pptx",
  "size_kb": 891.2,
  "download_url": "/files/new-uuid/download",
  "operations_applied": 7,
  "replacements_made": 43,
  "exec_time_ms": 312.4,
  "message": "✅ Presentation revised. 7 operations, 43 text replacements."
}
```

### Next.js Usage — Quarterly Update Pattern

```tsx
// Quarterly update: upload last quarter's deck, apply find_replace for all changed numbers
// This takes < 500ms instead of 3+ hours manually

async function quarterlyUpdate(fileId: string, updates: Record<string, string>) {
  const revisions = Object.entries(updates).map(([find, replace]) => ({
    type: "find_replace",
    find,
    replace,
  }));

  // This goes through Claude tool call which returns the result
  // The AI builds the revisions array from user's "update Q1 to Q2" instruction
}

function RevisionResultCard({ result }: { result: any }) {
  if (result.status !== "success") return null;
  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl">
      <div className="text-3xl">✏️</div>
      <div className="flex-1">
        <p className="font-semibold">{result.filename}</p>
        <p className="text-sm text-gray-500">
          {result.operations_applied} operations · {result.replacements_made} replacements · {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a href={downloadUrl} download={result.filename} className="px-4 py-2 bg-green-500 text-white rounded-lg text-sm">
        Download Revised
      </a>
    </div>
  );
}
```

---

## Tool 4 — `generate_xlsx`

**What it does:** Generates Potomac-branded Excel workbooks with charts, conditional formatting, Excel Tables, and formulas.

**Performance:** 50–300ms (pure Python openpyxl, no subprocess)

### Tool Input

```json
{
  "title": "POTOMAC PORTFOLIO TRACKER",
  "subtitle": "As of March 31, 2026",
  "filename": "Potomac_Portfolio_Q1_2026.xlsx",
  "sheets": [
    {
      "name": "PERFORMANCE",
      "tab_color": "FEC00F",
      "columns": ["MONTH", "STRATEGY RETURN", "BENCHMARK RETURN", "ALPHA", "AUM ($MM)"],
      "col_widths": [14, 18, 20, 12, 14],
      "rows": [
        ["January 2026",  0.052, 0.031, 0.021, 142.3],
        ["February 2026", 0.038, 0.022, 0.016, 148.1],
        ["March 2026",    0.061, 0.044, 0.017, 157.2]
      ],
      "number_formats": {
        "2": "0.0%",
        "3": "0.0%",
        "4": "0.0%",
        "5": "$#,##0.0"
      },
      "formulas": [
        {"cell": "B6", "formula": "=AVERAGE(B5:B7)"},
        {"cell": "C6", "formula": "=AVERAGE(C5:C7)"},
        {"cell": "D6", "formula": "=B6-C6"},
        {"cell": "E6", "formula": "=AVERAGE(E5:E7)"}
      ],
      "as_table": true,
      "table_name": "PerformanceData",
      "totals_row": {"2": "average", "3": "average"},
      "conditional_formats": [
        {"type": "color_scale", "range": "B5:D7"},
        {"type": "highlight_negatives", "range": "D5:D7"},
        {"type": "data_bars", "range": "E5:E7", "color": "FEC00F"}
      ],
      "charts": [
        {
          "type": "line_chart",
          "title": "Monthly Returns vs Benchmark",
          "x_col": 1,
          "y_cols": [2, 3],
          "series_labels": ["Strategy", "S&P 500"],
          "anchor": "G5",
          "width": 15,
          "height": 10
        }
      ],
      "freeze_panes": "A5",
      "include_footer": true
    }
  ],
  "include_disclosures": true
}
```

### Sheet Properties

| Property | Type | Description |
|---|---|---|
| `name` | string | Tab name (auto-uppercased, max 31 chars) |
| `tab_color` | hex string | Tab color e.g. `"FEC00F"` |
| `columns` | string[] | Column headers |
| `col_widths` | number[] | Column widths in Excel char units |
| `rows` | any[][] | Data rows |
| `number_formats` | `{"col_idx": "format"}` | 1-based column → Excel format string |
| `formulas` | `[{cell, formula}]` | Formula overrides per cell |
| `as_table` | boolean | Convert to Excel Table with auto-filter |
| `table_name` | string | Excel Table name |
| `totals_row` | `{"col_idx": "func"}` | Auto totals (sum/average/count) |
| `conditional_formats` | array | Color scales, data bars, highlights |
| `charts` | array | Native openpyxl charts |
| `freeze_panes` | string | Cell to freeze at e.g. `"A5"` |

### Number Format Reference

| Format | Example | Use For |
|---|---|---|
| `"0.0%"` | `5.2%` | Returns, allocations |
| `"0.00%"` | `5.23%` | Precision returns |
| `"$#,##0.0"` | `$1,234.5` | AUM in millions |
| `"#,##0"` | `1,235` | Integer counts |
| `"0.00"` | `1.23` | Sharpe, beta |
| `'0.0"x"'` | `2.5x` | Multiples |

### Conditional Format Types

| Type | Fields |
|---|---|
| `color_scale` | range, colors:[min_hex, mid_hex, max_hex] |
| `data_bars` | range, color (hex) |
| `highlight_negatives` | range |
| `highlight_positives` | range |

### Chart Types

`bar_chart`, `line_chart`, `pie_chart`, `area_chart`, `scatter_chart`

### Tool Output

```json
{
  "status": "success",
  "file_id": "uuid",
  "filename": "Potomac_Portfolio_Q1_2026.xlsx",
  "size_kb": 84.3,
  "download_url": "/files/uuid/download",
  "exec_time_ms": 187.2,
  "message": "✅ Workbook 'Potomac_Portfolio_Q1_2026.xlsx' generated (84.3 KB, 1 sheet(s))."
}
```

### Next.js Frontend Component

```tsx
interface XlsxResult {
  status: "success" | "error";
  file_id: string;
  filename: string;
  size_kb: number;
  download_url: string;
  exec_time_ms: number;
  message: string;
}

function XlsxDownloadCard({ result }: { result: XlsxResult }) {
  if (result.status !== "success") return null;
  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl">
      <div className="text-3xl">📊</div>
      <div className="flex-1">
        <p className="font-semibold text-gray-900">{result.filename}</p>
        <p className="text-sm text-gray-500">
          Excel workbook · {result.size_kb.toFixed(1)} KB · {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a
        href={downloadUrl}
        download={result.filename}
        className="px-4 py-2 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-lg text-sm"
      >
        Download .xlsx
      </a>
    </div>
  );
}
```

---

## Tool 5 — `analyze_xlsx`

**What it does:** Profiles any uploaded .xlsx or .csv — columns, data types, null counts, duplicates, numeric stats, 5 sample rows. Call this before transforming data.

**Performance:** 50–500ms (pandas, pure Python)

### Tool Input

```json
{
  "file_id": "uuid-of-uploaded-xlsx-or-csv"
}
```

### Tool Output

```json
{
  "status": "success",
  "file_id": "uuid",
  "filename": "holdings.xlsx",
  "exec_time_ms": 142.3,
  "profile": {
    "format": "xlsx",
    "sheet_count": 2,
    "sheets": ["HOLDINGS", "PERFORMANCE"],
    "profile": {
      "HOLDINGS": {
        "name": "HOLDINGS",
        "row_count": 47,
        "column_count": 6,
        "columns": ["TICKER", "NAME", "SHARES", "PRICE", "VALUE", "WEIGHT %"],
        "dtypes": {
          "TICKER": "object",
          "NAME": "object",
          "SHARES": "int64",
          "PRICE": "float64",
          "VALUE": "float64",
          "WEIGHT %": "float64"
        },
        "null_counts": {"TICKER": 0, "NAME": 0, "SHARES": 0, "PRICE": 2, "VALUE": 2, "WEIGHT %": 2},
        "duplicate_count": 0,
        "numeric_stats": {
          "SHARES": {"min": 100.0, "max": 50000.0, "mean": 4823.4, "median": 2000.0, "std": 8234.1},
          "PRICE": {"min": 12.4, "max": 482.1, "mean": 97.3, "median": 64.2, "std": 112.8}
        },
        "sample_rows": [
          ["AAPL", "Apple Inc.", 500, 174.23, 87115.0, 5.2],
          ["MSFT", "Microsoft Corp.", 300, 420.15, 126045.0, 7.5]
        ]
      }
    }
  },
  "message": "✅ File analyzed successfully. 2 sheet(s) found."
}
```

---

## Tool 6 — `transform_xlsx`

**What it does:** Apply a data transformation pipeline to any uploaded file. Returns a branded Potomac .xlsx.

**Performance:** 200ms–2s depending on dataset size (pandas, pure Python)

### Tool Input

```json
{
  "file_id": "uuid-of-uploaded-file",
  "output_title": "CLEANED HOLDINGS DATA",
  "output_filename": "Potomac_Holdings_Cleaned.xlsx",
  "operations": [
    {
      "type": "filter_rows",
      "column": "WEIGHT %",
      "op": ">",
      "value": 1.0
    },
    {
      "type": "sort",
      "by": ["VALUE"],
      "ascending": [false]
    },
    {
      "type": "normalize_text",
      "column": "TICKER",
      "transform": "upper"
    },
    {
      "type": "fill_nulls",
      "column": "PRICE",
      "value": 0
    },
    {
      "type": "add_column",
      "name": "MARKET_VALUE",
      "formula": "SHARES * PRICE"
    },
    {
      "type": "drop_duplicates",
      "subset": ["TICKER"],
      "keep": "first"
    },
    {
      "type": "group_aggregate",
      "by": ["SECTOR"],
      "agg": {"VALUE": "sum", "WEIGHT %": "mean"}
    }
  ]
}
```

### All Operations

| Operation | Fields | Description |
|---|---|---|
| `filter_rows` | column, op, value | Filter: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `not_contains`, `is_null`, `not_null` |
| `sort` | by:[cols], ascending:[bool] | Sort by one or more columns |
| `rename_columns` | mapper:{old:new} | Rename column headers |
| `drop_columns` | columns:[str] | Remove columns |
| `add_column` | name, formula | Add calculated column (pandas eval syntax) |
| `fill_nulls` | column, value | Replace null values |
| `drop_duplicates` | subset:[cols], keep | Remove duplicate rows |
| `change_dtype` | column, to | Convert type: `date`, `int`, `float`, `string` |
| `normalize_text` | column, transform | Text normalization: `upper`, `lower`, `title`, `strip` |
| `group_aggregate` | by:[cols], agg:{col:func} | Group + aggregate (sum/mean/count/min/max) |
| `pivot` | index, columns, values, aggfunc | Pivot table generation |

### Tool Output

```json
{
  "status": "success",
  "file_id": "uuid",
  "filename": "Potomac_Holdings_Cleaned.xlsx",
  "size_kb": 42.1,
  "download_url": "/files/uuid/download",
  "row_count": 32,
  "operations_applied": 6,
  "exec_time_ms": 387.4,
  "message": "✅ File transformed successfully. 6 operations applied, 32 rows output."
}
```

---

## Tool 7 — `generate_docx`

**What it does:** Generates Potomac-branded Word documents with full brand compliance — logo, headings, tables, images, disclosures.

**Performance:** 3–8 seconds (Node.js + docx npm)

### Tool Input (abbreviated)

```json
{
  "title": "POTOMAC MARKET COMMENTARY",
  "subtitle": "Q2 2026 Outlook",
  "date": "April 2026",
  "filename": "Potomac_Q2_Commentary.docx",
  "sections": [
    {"type": "heading", "level": 1, "text": "Executive Summary"},
    {"type": "paragraph", "text": "Markets remain elevated relative to historical norms..."},
    {"type": "bullets", "items": ["Fed on hold through Q2", "Credit spreads tightening"]},
    {
      "type": "table",
      "headers": ["METRIC", "VALUE", "BENCHMARK"],
      "rows": [
        ["Sharpe Ratio", "1.42", "0.87"],
        ["Max Drawdown", "-6.1%", "-10.3%"]
      ]
    },
    {"type": "divider"},
    {"type": "paragraph", "text": "See risk disclosures on following page."}
  ],
  "include_disclosure": true
}
```

### Tool Output

```json
{
  "status": "success",
  "file_id": "uuid",
  "filename": "Potomac_Q2_Commentary.docx",
  "size_kb": 284.7,
  "download_url": "/files/uuid/download",
  "exec_time_ms": 4821,
  "message": "✅ Document 'Potomac_Q2_Commentary.docx' generated (284.7 KB)."
}
```

### Next.js Frontend Component

```tsx
function DocxDownloadCard({ result }: { result: any }) {
  if (result.status !== "success") return null;
  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;

  return (
    <div className="flex items-center gap-3 p-4 bg-blue-50 border border-blue-200 rounded-xl">
      <div className="text-3xl">📄</div>
      <div className="flex-1">
        <p className="font-semibold">{result.filename}</p>
        <p className="text-sm text-gray-500">
          Word document · {result.size_kb.toFixed(1)} KB · {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a href={downloadUrl} download={result.filename} className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm">
        Download .docx
      </a>
    </div>
  );
}
```

---

## Universal File Download API

All tools use the same backend download endpoint:

```
GET /files/{file_id}/download
```

**Headers returned:**
```
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="Potomac_Q2_2026.pptx"
```

**Next.js API route** (if proxying through Next.js):
```typescript
// pages/api/files/[fileId]/download.ts
export default async function handler(req, res) {
  const { fileId } = req.query;
  const backendUrl = `${process.env.BACKEND_URL}/files/${fileId}/download`;
  const response = await fetch(backendUrl);
  
  res.setHeader("Content-Type", response.headers.get("content-type") || "application/octet-stream");
  res.setHeader("Content-Disposition", response.headers.get("content-disposition") || "attachment");
  
  const buffer = await response.arrayBuffer();
  res.send(Buffer.from(buffer));
}
```

---

## Universal Download Card Component

Use this single component for all 3 file types — detects from filename extension:

```tsx
interface FileResult {
  status: "success" | "error";
  file_id: string;
  filename: string;
  size_kb: number;
  download_url: string;
  exec_time_ms: number;
  message?: string;
  // pptx-specific
  slide_count?: number;
  // xlsx-specific
  row_count?: number;
  operations_applied?: number;
  replacements_made?: number;
  // pptx analyze-specific
  profile?: any;
}

const FILE_ICONS: Record<string, string> = {
  pptx: "📊",
  xlsx: "📗",
  docx: "📄",
  csv:  "📋",
};

const FILE_COLORS: Record<string, string> = {
  pptx: "bg-yellow-50 border-yellow-200",
  xlsx: "bg-green-50 border-green-200",
  docx: "bg-blue-50 border-blue-200",
};

const BUTTON_COLORS: Record<string, string> = {
  pptx: "bg-yellow-400 hover:bg-yellow-500 text-gray-900",
  xlsx: "bg-green-500 hover:bg-green-600 text-white",
  docx: "bg-blue-500 hover:bg-blue-600 text-white",
};

export function OfficeFileCard({ result }: { result: FileResult }) {
  if (result.status !== "success") return null;

  const ext = result.filename.split(".").pop()?.toLowerCase() || "docx";
  const downloadUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`;
  const icon = FILE_ICONS[ext] || "📁";
  const cardColor = FILE_COLORS[ext] || "bg-gray-50 border-gray-200";
  const btnColor = BUTTON_COLORS[ext] || "bg-gray-500 text-white";

  const meta: string[] = [];
  if (result.size_kb) meta.push(`${result.size_kb.toFixed(1)} KB`);
  if (result.slide_count) meta.push(`${result.slide_count} slides`);
  if (result.row_count) meta.push(`${result.row_count} rows`);
  if (result.operations_applied) meta.push(`${result.operations_applied} ops`);
  if (result.replacements_made) meta.push(`${result.replacements_made} replacements`);
  if (result.exec_time_ms) meta.push(`${(result.exec_time_ms / 1000).toFixed(1)}s`);

  return (
    <div className={`flex items-center gap-3 p-4 border rounded-xl ${cardColor}`}>
      <div className="text-3xl">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-gray-900 truncate">{result.filename}</p>
        <p className="text-sm text-gray-500">{meta.join(" · ")}</p>
      </div>
      <a
        href={downloadUrl}
        download={result.filename}
        className={`flex-shrink-0 px-4 py-2 font-semibold rounded-lg text-sm transition-colors ${btnColor}`}
      >
        Download
      </a>
    </div>
  );
}
```

**Usage:**
```tsx
// Same component works for ALL tool results
<OfficeFileCard result={toolResult} />
```

---

## Wiring Into the Chat Message Stream

The AI returns a JSON tool result as part of the message stream. Parse it in your message renderer:

```tsx
// In your ChatMessage component
function ChatMessage({ message }: { message: Message }) {
  // Check if the message contains a tool result with a download_url
  const toolResult = extractToolResult(message);

  if (toolResult?.download_url) {
    return (
      <div>
        <div className="prose">{message.text}</div>
        <OfficeFileCard result={toolResult} />
      </div>
    );
  }

  return <div className="prose">{message.text}</div>;
}

function extractToolResult(message: Message): any | null {
  try {
    if (message.tool_results) {
      for (const result of message.tool_results) {
        const parsed = JSON.parse(result.content);
        if (parsed.download_url && parsed.status === "success") {
          return parsed;
        }
      }
    }
  } catch {}
  return null;
}
```

---

## Error Output (All Tools)

```json
{
  "status": "error",
  "error": "File not found: bad-uuid",
  "exec_time_ms": 12.1
}
```

```tsx
function ErrorCard({ error }: { error: string }) {
  return (
    <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
      ⚠️ {error}
    </div>
  );
}
```

---

## Performance Summary

| Tool | Engine | Typical Time | File Type |
|---|---|---|---|
| `generate_pptx` | Node.js + pptxgenjs | 2–8s | .pptx |
| `analyze_pptx` | python-pptx | 50–300ms | JSON |
| `revise_pptx` | python-pptx | 100–500ms | .pptx |
| `generate_xlsx` | openpyxl | 50–300ms | .xlsx |
| `analyze_xlsx` | pandas | 50–500ms | JSON |
| `transform_xlsx` | pandas | 200ms–2s | .xlsx |
| `generate_docx` | Node.js + docx | 3–8s | .docx |

---

## Key Files Reference

| File | Purpose |
|---|---|
| `core/sandbox/pptx_sandbox.py` | PptxSandbox — Node.js builder with all 19 slide types |
| `core/sandbox/pptx_analyzer.py` | PptxAnalyzer — reads .pptx, returns profile + brand score |
| `core/sandbox/pptx_reviser.py` | PptxReviser — applies revisions to existing .pptx |
| `core/sandbox/xlsx_sandbox.py` | XlsxSandbox — openpyxl workbook builder |
| `core/sandbox/xlsx_analyzer.py` | XlsxAnalyzer — pandas profile of any Excel/CSV |
| `core/sandbox/xlsx_transformer.py` | XlsxTransformer — pandas pipeline operations |
| `core/tools_v2/document_tools.py` | All tool definitions + handlers |
| `core/tools.py` | TOOL_DEFINITIONS + dispatch table |
| `core/file_store.py` | 3-tier persistence (memory + Railway + Supabase) |
| `core/prompts/base.py` | System prompt routing rules (pptx/xlsx/docx → server tools) |
