# `generate_xlsx` Tool Guide

Server-side Potomac-branded Excel workbook generator. Runs entirely in Python
via **openpyxl** — no Node.js, no subprocess, instant execution.

---

## Architecture

```
Claude (AI)
  └─ generate_xlsx({title, sheets: [...]})
       └─ handle_generate_xlsx()       # core/tools_v2/document_tools.py
            └─ XlsxSandbox.generate()  # core/sandbox/xlsx_sandbox.py
                 ├─ Workbook()         # pure Python openpyxl
                 ├─ title block, headers, data rows, footer
                 ├─ optional DISCLOSURES sheet
                 └─ BytesIO → bytes
                      └─ store_file() → /files/{uuid}/download
```

No assets needed. All brand styling is applied in-process.

---

## Potomac Brand Styling (auto-applied)

| Element | Style |
|---------|-------|
| Title row 1 | Yellow `#FEC00F` background, Calibri Bold 16pt, dark gray text |
| Subtitle row 2 | Light yellow `#FEE896` background, Calibri 10pt |
| Column headers row 4 | Yellow `#FEC00F` fill, Calibri Bold 11pt, centered, thin borders |
| Data rows (odd) | White `#FFFFFF` background |
| Data rows (even) | Light gray `#F5F5F5` background (zebra striping) |
| Footer row | Light yellow `#FEE896`, Calibri Italic 8pt |
| Borders | Thin `#212121` border on all data cells |
| Tab colors | First sheet = Yellow, others = Dark Gray |
| DISCLOSURES sheet | Dark Gray tab, yellow title block |
| Page setup | Landscape, fit to width, print titles rows 1-4 |
| Freeze panes | Rows 1-4 frozen by default (above data) |

---

## Sheet Spec

Each item in `sheets` defines one worksheet tab:

```json
{
  "name": "PERFORMANCE",           // tab name (auto-uppercased, max 31 chars)
  "tab_color": "FEC00F",            // optional hex (no #)
  "columns": ["DATE", "STRATEGY", "RETURN %", "BENCHMARK %", "ALPHA %"],
  "col_widths": [12, 22, 12, 14, 10],  // optional, in Excel char units
  "rows": [
    ["Jan 2026", "GROWTH", 0.052, 0.031, 0.021],
    ["Feb 2026", "GROWTH", 0.038, 0.022, 0.016]
  ],
  "number_formats": {
    "3": "0.0%",
    "4": "0.0%",
    "5": "0.0%"
  },
  "formulas": [
    {"cell": "C10", "formula": "=AVERAGE(C5:C9)"},
    {"cell": "D10", "formula": "=AVERAGE(D5:D9)"},
    {"cell": "E10", "formula": "=C10-D10"}
  ],
  "include_footer": true,
  "footer_text": "Potomac | Built to Conquer Risk® | For Advisor Use Only",
  "freeze_panes": "A5"
}
```

---

## Number Format Reference

| Format String | Example Output | Use For |
|---------------|---------------|---------|
| `"0.0%"` | `5.2%` | Returns, allocations |
| `"0.00%"` | `5.23%` | Precision returns |
| `"$#,##0.0"` | `$1,234.5` | AUM in millions |
| `"$#,##0"` | `$1,235` | Dollar amounts |
| `"#,##0"` | `1,235` | Integer counts |
| `"0.00"` | `1.23` | Sharpe, beta |
| `'0.0"x"'` | `2.5x` | Multiples |
| `"MMM D, YYYY"` | `Jan 1, 2026` | Dates |
| `"YYYY-MM-DD"` | `2026-01-01` | ISO dates |

**Zeros display as `-`** (not `0`): use `'$#,##0.0;($#,##0.0);"-"'` for currency with zero handling.

---

## Full Spec Example — Performance Report

```json
{
  "title": "POTOMAC GROWTH STRATEGY",
  "subtitle": "Monthly Performance Report — Q1 2026",
  "filename": "Potomac_Growth_Q1_2026.xlsx",
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
      "include_footer": true,
      "freeze_panes": "A5"
    },
    {
      "name": "RISK METRICS",
      "tab_color": "212121",
      "columns": ["METRIC", "VALUE", "BENCHMARK", "NOTES"],
      "col_widths": [22, 14, 14, 35],
      "rows": [
        ["Sharpe Ratio",       1.42,  0.87,  "Annualized, risk-free rate 5.0%"],
        ["Sortino Ratio",      2.18,  1.23,  "Downside deviation only"],
        ["Max Drawdown",      -0.061, -0.089, "Peak-to-trough Q1 2026"],
        ["Beta",               0.78,   1.00,  "vs. S&P 500"],
        ["Alpha (Annualized)", 0.062,  0.00,  "Jensen's alpha"]
      ],
      "number_formats": {
        "2": "0.00",
        "3": "0.00"
      },
      "include_footer": true
    }
  ],
  "include_disclosures": true
}
```

---

## Template Types

| Template | Columns Pattern | Use Case |
|----------|----------------|----------|
| Performance Report | DATE, STRATEGY, RETURN %, BENCHMARK %, ALPHA % | Monthly/quarterly returns |
| Portfolio Tracker | TICKER, NAME, SHARES, PRICE, VALUE ($), WEIGHT %, P&L | Holdings snapshot |
| Risk Dashboard | METRIC, VALUE, LIMIT, STATUS | VaR, drawdown, correlation |
| Trade Log | DATE, TICKER, ACTION, SIZE, ENTRY, EXIT, P&L, NOTES | Trade history |
| Fee Schedule | AUM TIER, RATE (bps), ANNUAL FEE ($), MONTHLY FEE ($) | Client billing |
| Budget Model | CATEGORY, Q1, Q2, Q3, Q4, TOTAL, VARIANCE % | Annual budget |
| Onboarding Checklist | TASK, OWNER, DUE DATE, STATUS, NOTES | Project tracking |
| Financial Model | ASSUMPTION, VALUE, NOTES (inputs tab) + projections tab | DCF models |

---

## Stress Test Prompts

**1. Simple performance tracker:**
> "Create a Potomac Excel workbook for our Q1 2026 performance. Include monthly returns for January (5.2%), February (3.8%), and March (6.1%) vs. the S&P 500 benchmark. Add a row with =AVERAGE() formulas at the bottom. Format return columns as percentages."

**2. Multi-sheet portfolio workbook:**
> "Generate a Potomac portfolio tracker Excel file with 3 sheets: HOLDINGS (ticker, name, shares, price, market value, weight %), PERFORMANCE (monthly returns vs benchmark for 6 months), and RISK (Sharpe 1.42, Sortino 2.18, Max DD -6.1%, Beta 0.78, Alpha 6.2%). Add a DISCLOSURES sheet."

**3. Fee schedule with tiered rates:**
> "Build a Potomac fee schedule Excel showing AUM tiers: under $1M = 100bps, $1M-$5M = 75bps, $5M-$25M = 60bps, $25M+ = 50bps. Include columns for AUM tier, annual rate, annual fee for median AUM in each tier, and monthly fee. Format as currency."

**4. Trade log for a quarter:**
> "Create a Potomac trade log Excel with 15 sample trades from Q1 2026. Include date, ticker, action (buy/sell), shares, entry price, exit price, gross P&L, and notes. Add a totals row using SUM() formulas. Zebra stripe the rows."

**5. Risk dashboard with status indicators:**
> "Generate a Potomac risk dashboard Excel showing 8 key risk metrics: VaR 95%, VaR 99%, Max Drawdown, Current Drawdown, Sharpe Ratio, Beta, Tracking Error, and Information Ratio. Include current value, limit/threshold, and a status column (OK/WARNING/BREACH). Color the tab red (EB2F5C)."

**6. Budget model:**
> "Build a Potomac annual budget model for FY2026 with quarterly columns (Q1-Q4) and a Total column. Include revenue categories (Advisory Fees, Performance Fees, Other) and expense categories (Personnel, Technology, Marketing, Operations, Compliance). Add variance % formulas comparing to prior year."

---

## Formula Rules

Always use Excel formulas — never hardcode calculated values:

```
✅ {"cell": "C10", "formula": "=SUM(C5:C9)"}
✅ {"cell": "D10", "formula": "=AVERAGE(D5:D9)"}
✅ {"cell": "E10", "formula": "=C10-D10"}
✅ {"cell": "F10", "formula": "=IF(E10>0,E10/D10-1,0)"}
✅ {"cell": "G10", "formula": "=IFERROR((C10-B10)/ABS(B10),0)"}
```

---

## Frontend Download Card

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
          Excel workbook · {result.size_kb.toFixed(1)} KB ·{" "}
          Generated in {(result.exec_time_ms / 1000).toFixed(1)}s
        </p>
      </div>
      <a
        href={downloadUrl}
        download={result.filename}
        className="px-4 py-2 bg-green-500 hover:bg-green-600 text-white font-semibold rounded-lg text-sm transition-colors"
      >
        Download Excel
      </a>
    </div>
  );
}
```

---

## Key Files

| File | Purpose |
|------|---------|
| `core/sandbox/xlsx_sandbox.py` | XlsxSandbox class — pure Python openpyxl builder |
| `core/tools_v2/document_tools.py` | `GENERATE_XLSX_TOOL_DEF` + `handle_generate_xlsx()` |
| `core/tools.py` | TOOL_DEFINITIONS entry + `elif tool_name == "generate_xlsx"` dispatch |
| `ClaudeSkills/potomac-xlsx/SKILL.md` | Brand guidelines reference |
| `ClaudeSkills/potomac-xlsx/references/templates.md` | Column layouts for all 10 document types |
| `ClaudeSkills/potomac-xlsx/references/formulas.md` | Financial formula patterns |

---

## Performance

Since XlsxSandbox is pure Python (no subprocess), workbook generation typically completes
in **50–300 ms** regardless of the number of rows or sheets. No npm cache warm-up needed.

The `openpyxl` library is already in `requirements.txt` and installed in the Docker image.
