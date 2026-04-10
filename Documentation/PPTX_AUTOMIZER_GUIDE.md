# Potomac PPTX Automizer Guide

> **The staff-replacement engine.** This tool operates on *existing* professionally-designed PowerPoint decks — injecting fresh data while preserving every pixel of designer formatting.

---

## Table of Contents

1. [Overview](#overview)
2. [The Quarterly Report Workflow](#the-quarterly-report-workflow)
3. [Tool Reference](#tool-reference)
4. [Operation Catalog](#operation-catalog)
5. [Template Library](#template-library)
6. [Complete Spec Examples](#complete-spec-examples)
7. [How It Works](#how-it-works)
8. [Tips & Troubleshooting](#tips--troubleshooting)

---

## Overview

The `generate_pptx_template` tool is backed by `pptx-automizer` (Node.js library). Unlike `generate_pptx` and `generate_pptx_freestyle` which build presentations **from scratch**, this tool **loads an existing .pptx** and modifies it — preserving all chart styling, table borders, fonts, slide master, and layout.

### When to use which tool

| Tool | Use when |
|---|---|
| `generate_pptx` | Building a new Potomac deck from scratch (21 slide templates) |
| `generate_pptx_freestyle` | Custom design not covered by templates (raw pptxgenjs code) |
| **`generate_pptx_template`** | **Updating an existing deck with new data** (quarterly reports, fact sheets, client decks) |
| `revise_pptx` | Simple text find/replace on an existing deck (milliseconds, python-pptx) |
| `analyze_pptx` | Reading an uploaded deck to find shape names, slide count, text |

### Key capabilities

- **Global text replacement** — change "Q4 2025" → "Q1 2026" across the **entire deck** in one operation
- **Chart data injection** — replace series/category data in real PowerPoint charts; preserves ALL styling (colors, fonts, axes, legend, borders)
- **Table row injection** — inject rows into styled PowerPoint tables; preserves header fills, borders, column widths
- **Image swap** — replace a PNG/JPG image; preserves position, size, and cropping
- **Template assembly** — cherry-pick slides from multiple .pptx source files and combine into one output
- **{{tag}} replacement** — replace `{{date}}` style placeholders in any text box

---

## The Quarterly Report Workflow

This is the primary use case. Three steps replace hours of manual analyst work.

### Step 1 — Analyze the existing deck

```
User uploads: Q4_2025_Fund_Report.pptx
AI calls: analyze_pptx(file_id="<upload_id>")
```

The `analyze_pptx` output shows:
- Total slide count
- Shape names on each slide (use ALT+F10 in PowerPoint to see these)
- All text content per slide
- Which slides have charts / tables / images

**Key info to extract from the analysis:**
- Which slide numbers contain performance charts
- The PowerPoint shape name of each chart (e.g. `"PerformanceChart"`)
- The PowerPoint shape name of each table (e.g. `"HoldingsTable"`)

### Step 2 — Prepare the data

Gather the Q1 2026 numbers:
- New date strings to replace (e.g. "Q4 2025" → "Q1 2026")
- New chart data (series + categories with values)
- New table rows (holdings, risk metrics, etc.)

### Step 3 — Call generate_pptx_template

```json
{
  "template_file_id": "<upload_id_of_q4_deck>",
  "output_filename": "Potomac_Q1_2026_Fund_Report.pptx",
  "mode": "update",
  "global_replacements": [
    {"find": "Q4 2025",            "replace": "Q1 2026"},
    {"find": "December 31, 2025",  "replace": "March 31, 2026"},
    {"find": "Fourth Quarter",     "replace": "First Quarter"},
    {"find": "Full Year 2025",     "replace": "Year-to-Date 2026"}
  ],
  "slide_modifications": [
    {
      "slide_number": 4,
      "modifications": [
        {
          "op": "set_chart_data",
          "shape": "PerformanceChart",
          "series": [
            {"label": "Defensive Alpha Fund"},
            {"label": "S&P 500 Index"}
          ],
          "categories": [
            {"label": "Jan",  "values": [2.14, 1.88]},
            {"label": "Feb",  "values": [0.91, 1.12]},
            {"label": "Mar",  "values": [1.53, 1.31]}
          ]
        }
      ]
    },
    {
      "slide_number": 7,
      "modifications": [
        {
          "op": "set_table",
          "shape": "HoldingsTable",
          "body": [
            {"label": "r1", "values": ["Apple Inc.",      "AAPL",  "8.2%",  "+12.3%", "+1.01%"]},
            {"label": "r2", "values": ["Microsoft Corp.", "MSFT",  "7.1%",  "+9.8%",  "+0.70%"]},
            {"label": "r3", "values": ["NVIDIA Corp.",    "NVDA",  "5.8%",  "+31.2%", "+1.81%"]},
            {"label": "r4", "values": ["Amazon.com",      "AMZN",  "4.9%",  "+7.4%",  "+0.36%"]},
            {"label": "r5", "values": ["Alphabet Inc.",   "GOOGL", "4.2%",  "+10.1%", "+0.42%"]}
          ]
        }
      ]
    }
  ]
}
```

**Result:** A pixel-identical Q1 2026 deck with updated charts, tables, and all date strings replaced — in ~30 seconds.

---

## Tool Reference

### Input Parameters

| Parameter | Type | Mode | Description |
|---|---|---|---|
| `template_file_id` | string | both | file_id of uploaded .pptx to use as source |
| `output_filename` | string | both | Output filename e.g. `"Q1_2026_Report.pptx"` |
| `mode` | string | both | `"update"` (default) or `"assembly"` |
| `global_replacements` | array | update | Text replacements applied to ALL slides |
| `slide_modifications` | array | update | Per-slide operations by slide_number |
| `slides` | array | assembly | Slides to cherry-pick (source_file + slide_number) |
| `extra_images` | array | both | Images for `swap_image` ops: `[{name, file_id}]` |

### Response

```json
{
  "status":       "success",
  "mode":         "update",
  "file_id":      "abc123-...",
  "filename":     "Q1_2026_Report.pptx",
  "size_kb":      842.3,
  "download_url": "/files/abc123-.../download",
  "warnings":     [],
  "exec_time_ms": 28400,
  "message":      "✅ Presentation updated via pptx-automizer. 4 global replacements, 2 slides modified."
}
```

---

## Operation Catalog

All operations go inside the `modifications` array of a slide spec.

---

### `set_text` — Replace all text in a named shape

```json
{
  "op": "set_text",
  "shape": "TitleText",
  "text": "Q1 2026 QUARTERLY REVIEW"
}
```

Completely replaces the text content of the named shape.

---

### `replace_tagged` — Replace `{{tag}}` placeholders

```json
{
  "op": "replace_tagged",
  "shape": "BodyText",
  "tags": [
    {"find": "date",        "by": "March 31, 2026"},
    {"find": "fund_name",   "by": "Defensive Alpha Fund"},
    {"find": "nav",         "by": "$10.42"},
    {"find": "ytd_return",  "by": "+4.72%"}
  ],
  "opening_tag": "{{",
  "closing_tag":  "}}"
}
```

The template contains `{{date}}`, `{{fund_name}}` etc. This replaces them with actual values while preserving all other text formatting.

---

### `replace_text` — Simple find/replace within a shape

```json
{
  "op": "replace_text",
  "shape": "DisclaimerText",
  "replacements": [
    {"find": "December 31, 2025", "replace": "March 31, 2026"},
    {"find": "fourth quarter",    "replace": "first quarter"}
  ],
  "match_case": false
}
```

---

### `set_chart_data` — Inject data into a PowerPoint chart

```json
{
  "op": "set_chart_data",
  "shape": "PerformanceChart",
  "series": [
    {"label": "Fund"},
    {"label": "Benchmark"},
    {"label": "Peer Group"}
  ],
  "categories": [
    {"label": "Jan 2026", "values": [2.14,  1.88,  1.95]},
    {"label": "Feb 2026", "values": [0.91,  1.12,  0.78]},
    {"label": "Mar 2026", "values": [1.53,  1.31,  1.44]},
    {"label": "Apr 2026", "values": [-0.32, -0.18, -0.41]},
    {"label": "May 2026", "values": [1.82,  1.59,  1.73]}
  ]
}
```

**Preserves:** chart type, axis labels, colors, fonts, legend position, borders, gridlines.

Works with: BAR, COLUMN, LINE, AREA, PIE, DOUGHNUT, SCATTER.

---

### `set_extended_chart_data` — Waterfall / map / funnel charts

```json
{
  "op": "set_extended_chart_data",
  "shape": "WaterfallChart",
  "series": [{"label": "Attribution (bps)"}],
  "categories": [
    {"label": "Security Selection",  "values": [45]},
    {"label": "Sector Allocation",   "values": [22]},
    {"label": "Currency",            "values": [-8]},
    {"label": "Other",               "values": [3]},
    {"label": "Total",               "values": [62]}
  ]
}
```

---

### `set_table` — Inject rows into a styled table

```json
{
  "op": "set_table",
  "shape": "HoldingsTable",
  "body": [
    {"label": "r1", "values": ["Apple Inc.",      "AAPL",  "8.2%", "+12.3%"]},
    {"label": "r2", "values": ["Microsoft Corp.", "MSFT",  "7.1%", "+9.8%"]},
    {"label": "r3", "values": ["NVIDIA Corp.",    "NVDA",  "5.8%", "+31.2%"]}
  ],
  "adjust_height": true
}
```

The header row (row 0) is **preserved** from the template. Only data rows are replaced.  
The number of `values` must match the number of table columns.

---

### `swap_image` — Replace an image

```json
{
  "op": "swap_image",
  "shape": "ChartExportImage",
  "image_file": "q1_performance_chart.png"
}
```

The `image_file` must be listed in `extra_images` at the top level:

```json
{
  "extra_images": [
    {"name": "q1_performance_chart.png", "file_id": "<uploaded_png_id>"}
  ]
}
```

Preserves position, size, and cropping from the original image.

---

### `set_position` — Reposition / resize a shape

```json
{
  "op": "set_position",
  "shape": "LogoImage",
  "x": 8.5,
  "y": 0.15,
  "w": 1.25,
  "h": 0.5
}
```

Values are in **centimeters**. All four params are optional — only specified ones are changed.

---

### `remove_element` — Delete a shape

```json
{
  "op": "remove_element",
  "shape": "OldChart"
}
```

---

### `add_element` — Copy a shape from another slide

```json
{
  "op": "add_element",
  "source_file": "potomac-chart-slides.pptx",
  "slide_number": 1,
  "element_name": "PerformanceChart"
}
```

---

### `generate_scratch` — Add fresh pptxgenjs content

```json
{
  "op": "generate_scratch",
  "code": "pSlide.addText('UPDATED', { x:0.5, y:7.0, w:2, h:0.35, fontSize:10, color:'999999', italic:true });"
}
```

Runs pptxgenjs code on top of the existing slide. Useful for adding watermarks, timestamps, or dynamic labels.

---

## Template Library

Pre-built Potomac templates in `ClaudeSkills/potomac-pptx/automizer-templates/`. All shapes are named and visible in PowerPoint's Selection Pane (ALT+F10).

### `potomac-content-slides.pptx`

| Slide | Shape Names |
|---|---|
| 1 — Title | `TitleText`, `SubtitleText`, `DateText`, `TaglineText` |
| 2 — Content | `TitleText`, `BodyText` |
| 3 — Two Column | `TitleText`, `LeftHeader`, `RightHeader`, `LeftContent`, `RightContent` |
| 4 — Metrics (3 KPIs) | `TitleText`, `Metric1Value`, `Metric1Label`, `Metric2Value`, `Metric2Label`, `Metric3Value`, `Metric3Label`, `ContextText` |
| 5 — Section Divider | `TitleText`, `DescriptionText` |

### `potomac-chart-slides.pptx`

| Slide | Shape Names |
|---|---|
| 1 — Bar Chart | `TitleText`, **`PerformanceChart`**, `CaptionText` |
| 2 — Line Chart | `TitleText`, **`TrendChart`**, `CaptionText` |
| 3 — Column Chart | `TitleText`, **`AttributionChart`**, `CaptionText` |

### `potomac-table-slides.pptx`

| Slide | Shape Names |
|---|---|
| 1 — Data Table | `TitleText`, **`DataTable`** (4 cols: Name, Value, Change, Weight), `CaptionText` |
| 2 — Holdings Table | `TitleText`, **`HoldingsTable`** (5 cols: Security, Ticker, Weight, Return, Contribution), `CaptionText` |
| 3 — Risk Scorecard | `TitleText`, **`ScorecardTable`** (5 cols: Metric, Status, Current, Threshold, Commentary), `CaptionText` |

### `potomac-fund-fact-sheet.pptx` ⭐ (single-slide, fully tagged)

| Shape | Tag / Purpose |
|---|---|
| `FundName` | `{{fund_name}}` |
| `AsOfDate` | `{{date}}` |
| `FundDescription` | `{{fund_description}}` |
| `InceptionDate` | `{{inception_date}}` |
| `AUM` | `{{aum}}` |
| `NAV` | `{{nav}}` |
| `PerformanceTable` | Table: Fund vs Benchmark YTD / 1Y / 3Y / 5Y / SI |
| `BenchmarkName` | `{{benchmark_name}}` |
| `HoldingsTable` | Top 5 holdings: Security, Weight, Return |
| `RiskMetricsTable` | Sharpe, Sortino, Max DD, Beta, Std Dev |
| `AllocationChart` | Sector allocation pie chart |
| `FooterText` | Disclosure footer |

---

## Complete Spec Examples

### Example 1 — Fund Fact Sheet from Template

```json
{
  "template_file_id": null,
  "output_filename": "Defensive_Alpha_FactSheet_Q1_2026.pptx",
  "mode": "assembly",
  "slides": [
    {
      "source_file": "potomac-fund-fact-sheet.pptx",
      "slide_number": 1,
      "modifications": [
        {"op": "replace_tagged", "shape": "FundName",
         "tags": [{"find": "fund_name", "by": "Defensive Alpha Fund"}]},
        {"op": "replace_tagged", "shape": "AsOfDate",
         "tags": [{"find": "date", "by": "March 31, 2026"}]},
        {"op": "replace_tagged", "shape": "FundDescription",
         "tags": [{"find": "fund_description", "by": "A risk-managed equity strategy seeking capital appreciation through systematic factor selection."}]},
        {"op": "replace_tagged", "shape": "InceptionDate",
         "tags": [{"find": "inception_date", "by": "January 1, 2018"}]},
        {"op": "replace_tagged", "shape": "AUM",
         "tags": [{"find": "aum", "by": "$847M"}]},
        {"op": "replace_tagged", "shape": "NAV",
         "tags": [{"find": "nav", "by": "$10.42"}]},
        {"op": "set_table", "shape": "PerformanceTable",
         "body": [
           {"label": "Fund",      "values": ["+4.72%", "+12.8%", "+9.4%", "+11.2%", "+10.8%"]},
           {"label": "Benchmark", "values": ["+3.91%", "+10.1%", "+8.2%", "+9.6%",  "+9.1%"]}
         ]},
        {"op": "replace_tagged", "shape": "BenchmarkName",
         "tags": [{"find": "benchmark_name", "by": "S&P 500 Total Return Index"}]},
        {"op": "set_table", "shape": "HoldingsTable",
         "body": [
           {"label": "r1", "values": ["Apple Inc.",      "8.2%", "+12.3%"]},
           {"label": "r2", "values": ["Microsoft Corp.", "7.1%", "+9.8%"]},
           {"label": "r3", "values": ["NVIDIA Corp.",    "5.8%", "+31.2%"]},
           {"label": "r4", "values": ["Amazon.com",      "4.9%", "+7.4%"]},
           {"label": "r5", "values": ["Alphabet Inc.",   "4.2%", "+10.1%"]}
         ]},
        {"op": "set_table", "shape": "RiskMetricsTable",
         "body": [
           {"label": "r1", "values": ["Sharpe Ratio",  "1.42"]},
           {"label": "r2", "values": ["Sortino Ratio", "1.89"]},
           {"label": "r3", "values": ["Max Drawdown",  "-8.3%"]},
           {"label": "r4", "values": ["Beta",          "0.87"]},
           {"label": "r5", "values": ["Std Deviation", "9.2%"]}
         ]},
        {"op": "set_chart_data", "shape": "AllocationChart",
         "series": [{"label": "Allocation"}],
         "categories": [
           {"label": "US Large Cap",  "values": [42]},
           {"label": "US Small Cap",  "values": [18]},
           {"label": "International", "values": [25]},
           {"label": "Fixed Income",  "values": [10]},
           {"label": "Cash",          "values": [5]}
         ]}
      ]
    }
  ]
}
```

---

### Example 2 — Multi-Source Assembly

Build a client deck by pulling the best slides from different source presentations:

```json
{
  "template_file_id": "<uploaded_pptx>",
  "output_filename": "ClientName_Q1_2026_Review.pptx",
  "mode": "assembly",
  "slides": [
    {
      "source_file": "input.pptx",
      "slide_number": 1,
      "modifications": [
        {"op": "replace_tagged", "shape": "TitleText",
         "tags": [{"find": "title", "by": "Q1 2026 PORTFOLIO REVIEW"}]},
        {"op": "replace_tagged", "shape": "SubtitleText",
         "tags": [{"find": "subtitle", "by": "Prepared for: Acme Family Office"}]}
      ]
    },
    {
      "source_file": "input.pptx",
      "slide_number": 4,
      "modifications": [
        {"op": "set_chart_data", "shape": "PerformanceChart",
         "series": [{"label": "Portfolio"}, {"label": "Benchmark"}],
         "categories": [
           {"label": "Jan", "values": [2.1, 1.9]},
           {"label": "Feb", "values": [0.8, 1.1]},
           {"label": "Mar", "values": [1.4, 1.3]}
         ]}
      ]
    },
    {
      "source_file": "input.pptx",
      "slide_number": 7,
      "modifications": [
        {"op": "set_table", "shape": "HoldingsTable",
         "body": [
           {"label": "r1", "values": ["Apple Inc.", "AAPL", "8.2%", "+12.3%", "+1.01%"]},
           {"label": "r2", "values": ["Microsoft",  "MSFT", "7.1%", "+9.8%",  "+0.70%"]}
         ]}
      ]
    },
    {
      "source_file": "input.pptx",
      "slide_number": 12
    }
  ]
}
```

---

### Example 3 — Global Date Update Only (text-heavy deck)

```json
{
  "template_file_id": "<uploaded_annual_report>",
  "output_filename": "Annual_Report_2026.pptx",
  "mode": "update",
  "global_replacements": [
    {"find": "2025",                     "replace": "2026"},
    {"find": "fiscal year 2025",         "replace": "fiscal year 2026"},
    {"find": "as of december 31, 2025",  "replace": "as of december 31, 2026"},
    {"find": "fourth quarter 2025",      "replace": "fourth quarter 2026"},
    {"find": "Q4 2025",                  "replace": "Q4 2026"},
    {"find": "full year 2025",           "replace": "full year 2026"}
  ]
}
```

---

## How It Works

```
User uploads Q4 deck → file_id
           ↓
handle_generate_pptx_template()
  - reads PPTX bytes from file_store
  - builds spec dict
  - calls AutomizerSandbox.run()
           ↓
AutomizerSandbox (Python)
  - ensures ~/.sandbox/pptx_cache/node_modules/pptx-automizer exists
  - creates temp dir: pptx_auto_XXXXX/
    ├── spec.json
    ├── automizer_runner.js
    ├── templates/input.pptx     (user's uploaded deck)
    ├── templates/*.pptx          (builtin templates if referenced)
    ├── media/                    (extra images)
    └── node_modules -> symlink to unified cache
  - runs: node automizer_runner.js
           ↓
automizer_runner.js (Node.js)
  - reads spec.json
  - loads pptx-automizer
  - UPDATE MODE:
    1. automizer.loadRoot("input.pptx")
    2. .load("input.pptx", "__src__")
    3. pres.getInfo() → enumerate all slides
    4. for each slide:
       - getAllTextElementIds() → apply global_replacements
       - apply per-slide modifications (set_chart_data, set_table, etc.)
    5. pres.write("output.pptx")
  - writes SUCCESS: to stdout
           ↓
Python reads output.pptx bytes
  → store_file() → file_id
  → return JSON with download_url
```

---

## Tips & Troubleshooting

### Getting shape names

1. **ALT+F10** in PowerPoint opens the Selection Pane — shows all shape names on the current slide
2. `analyze_pptx(file_id)` returns shape names in the profile output
3. Run the generation script to create a .pptx, open it and name shapes before committing as a template

### Shape name not found

If pptx-automizer can't find a shape, it logs a `WARN` (non-fatal) and skips the operation. The tool still succeeds but the modification is not applied. The `warnings` array in the response will contain the message.

**Fix:** Check the exact shape name via ALT+F10 in PowerPoint. Shape names are case-sensitive.

### Chart data not updating

pptx-automizer's `set_chart_data` works with standard PowerPoint charts (embedded Excel workbook). It **does not** work with:
- Charts that are actually images (screenshots)
- SmartArt
- Animated charts with macros

**Fix:** Open the PPTX in PowerPoint, double-click the chart. If an Excel worksheet opens, it's a real chart. If not, it's an image.

### Number of values must match series count

For `set_chart_data`, each category's `values` array must have the **same length** as the `series` array. If you have 2 series, each category needs 2 values.

### Table column count must match

For `set_table`, each row's `values` array must have the same number of elements as the table's column count. Mismatched columns cause a WARN and that row is skipped.

### Performance

| Operation | Typical time |
|---|---|
| `global_replacements` only (entire deck) | 5–15 seconds |
| 1–3 chart updates | 15–30 seconds |
| Full quarterly refresh (charts + tables + text) | 25–45 seconds |
| First-time npm install (pptx-automizer) | 30–90 seconds (once only) |

### npm cache location

```
~/.sandbox/pptx_cache/          (shared with generate_pptx)
  node_modules/
    pptxgenjs/
    pptx-automizer/
  package.json
```

On Railway: uses `SANDBOX_DATA_DIR` env var → `/data/.sandbox/pptx_cache/` (persisted across deploys via volume).

### Regenerating built-in templates

```bash
python scripts/generate_automizer_templates.py
```

This regenerates all 4 template `.pptx` files in `ClaudeSkills/potomac-pptx/automizer-templates/`. Run after making layout changes to the generation script.

---

## Roadmap

- [ ] **`analyze_pptx` shape names** — update `pptx_analyzer.py` to surface shape names per slide in its output, enabling the AI to skip the "find shape name" step
- [ ] **More template types** — `potomac-board-deck.pptx`, `potomac-rfp-proposal.pptx`
- [ ] **Batch update** — single call updates multiple client decks from one data payload
- [ ] **Preview endpoint** — use PPTXjs on frontend to render template thumbnails
