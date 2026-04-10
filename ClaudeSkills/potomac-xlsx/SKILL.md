---
name: potomac-xlsx
description: >
  Create, read, edit, and modify Potomac-branded Excel spreadsheets (.xlsx files) for any
  business purpose. Potomac is a tactical fund manager — spreadsheets include performance
  reports, portfolio trackers, risk dashboards, trade logs, fee schedules, budget models,
  data exports, onboarding checklists, and financial models. Use whenever the user requests
  any Excel or spreadsheet work for Potomac, regardless of complexity. Always triggers for
  .xlsx, .xls, .csv tasks involving Potomac content or branding. Use this skill even for
  simple read/analyze tasks on Potomac data — it ensures brand-consistent output every time.
---

# Potomac Excel Skill

Create, read, edit, and format Potomac-branded Excel files. Potomac is a **tactical fund manager** — "Built to Conquer Risk®".

---

## Quick-Start Workflow

1. **Identify the task** → Create / Edit / Read / Analyze?
2. **Choose tool** → `openpyxl` for formatting+formulas, `pandas` for data ops
3. **Apply Potomac brand** → Colors, fonts, header/footer (see Brand section)
4. **Use formulas, not hardcoded values** (see Formula Rules)
5. **Recalculate** with `scripts/recalc.py` if formulas were written
6. **Verify** zero formula errors
7. **Save to** `/mnt/user-data/outputs/Potomac_[Name].xlsx`

---

## Potomac Brand Guidelines for Excel

### Color Palette

| Role | Color | Hex | RGB |
|------|-------|-----|-----|
| Header background | Potomac Yellow | `#FEC00F` | `254, 192, 15` |
| Header text | Potomac Dark Gray | `#212121` | `33, 33, 33` |
| Body text | Potomac Dark Gray | `#212121` | `33, 33, 33` |
| Accent / highlight | Potomac Yellow | `#FEC00F` | `254, 192, 15` |
| Subheader background | Yellow 40% tint | `#FEE896` | `254, 232, 150` |
| Investment Strategies only | Potomac Turquoise | `#00DED1` | `0, 222, 209` |
| Accent (use sparingly) | Potomac Pink | `#EB2F5C` | `235, 47, 92` |
| White / clean rows | White | `#FFFFFF` | `255, 255, 255` |
| Alternating rows | Light gray | `#F5F5F5` | `245, 245, 245` |

> **Rule**: Never use turquoise except for Investment Strategies / Potomac Funds content.

### Typography

Excel doesn't support web fonts, so use these substitutes:

| Purpose | Font |
|---------|------|
| Headers / titles | **Calibri Bold** (closest to Rajdhani weight) |
| Body / data | **Calibri** |
| Numbers / financials | **Calibri** |

All **column headers and sheet tab names** must be in **ALL CAPS**.

### Brand Constants (openpyxl)

```python
# Potomac brand colors for openpyxl
POTOMAC_YELLOW   = "FEC00F"   # Header backgrounds, accent bars
POTOMAC_GRAY     = "212121"   # All text
POTOMAC_TEAL     = "00DED1"   # Investment Strategies only
POTOMAC_PINK     = "EB2F5C"   # Sparingly — alerts, warnings
POTOMAC_YELLOW_LIGHT = "FEE896"  # Subheader / secondary row highlight
ROW_ALT          = "F5F5F5"   # Alternating row background
WHITE            = "FFFFFF"

# Standard fonts
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

def header_font(size=11):
    return Font(name="Calibri", bold=True, color=POTOMAC_GRAY, size=size)

def body_font(size=10):
    return Font(name="Calibri", color=POTOMAC_GRAY, size=size)

def yellow_fill():
    return PatternFill("solid", fgColor=POTOMAC_YELLOW)

def light_yellow_fill():
    return PatternFill("solid", fgColor=POTOMAC_YELLOW_LIGHT)

def alt_fill():
    return PatternFill("solid", fgColor=ROW_ALT)

def white_fill():
    return PatternFill("solid", fgColor=WHITE)

def thin_border():
    thin = Side(style="thin", color=POTOMAC_GRAY)
    return Border(left=thin, right=thin, top=thin, bottom=thin)

def bottom_border():
    thick = Side(style="medium", color=POTOMAC_YELLOW)
    return Border(bottom=thick)
```

---

## Spreadsheet Structure Standards

### Title Block (row 1–2 of every sheet)

```python
# Row 1: "POTOMAC" or document title in large bold Calibri
# Row 2: Subtitle / date / classification
# Row 3: Empty spacer row before data

def write_title_block(sheet, title, subtitle=""):
    sheet.row_dimensions[1].height = 30
    sheet.row_dimensions[2].height = 18

    sheet["A1"] = title.upper()
    sheet["A1"].font = Font(name="Calibri", bold=True, size=16, color=POTOMAC_GRAY)
    sheet["A1"].fill = yellow_fill()
    sheet["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

    if subtitle:
        sheet["A2"] = subtitle
        sheet["A2"].font = Font(name="Calibri", size=10, color=POTOMAC_GRAY)
        sheet["A2"].fill = light_yellow_fill()
        sheet["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # Merge title across all used columns (adjust range to data width)
    # sheet.merge_cells("A1:H1")  — caller must do this after knowing column count
```

### Column Headers (standard pattern)

```python
def style_header_row(sheet, row_num, col_count):
    """Apply yellow header styling to a row."""
    for col in range(1, col_count + 1):
        cell = sheet.cell(row=row_num, column=col)
        cell.font = header_font()
        cell.fill = yellow_fill()
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border()
    sheet.row_dimensions[row_num].height = 20
```

### Data Rows (zebra striping)

```python
def style_data_rows(sheet, start_row, end_row, col_count):
    for r in range(start_row, end_row + 1):
        fill = alt_fill() if r % 2 == 0 else white_fill()
        for c in range(1, col_count + 1):
            cell = sheet.cell(row=r, column=c)
            cell.fill = fill
            cell.font = body_font()
            cell.border = thin_border()
            cell.alignment = Alignment(vertical="center")
```

### Footer / Disclaimer Row

```python
def write_footer(sheet, footer_row, col_count, text=None):
    if text is None:
        text = "Potomac | Built to Conquer Risk® | For Advisor Use Only"
    sheet.merge_cells(
        start_row=footer_row, start_column=1,
        end_row=footer_row, end_column=col_count
    )
    cell = sheet.cell(row=footer_row, column=1)
    cell.value = text
    cell.font = Font(name="Calibri", size=8, italic=True, color=POTOMAC_GRAY)
    cell.fill = light_yellow_fill()
    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
```

---

## Document Types and Templates

See `references/templates.md` for full column layouts and formula patterns for each type.

| # | Template | Use When |
|---|----------|----------|
| 1 | Performance Report | Monthly/quarterly fund performance vs benchmarks |
| 2 | Portfolio Tracker | Holdings, weights, P&L, risk metrics |
| 3 | Risk Dashboard | VaR, drawdown, correlation, stress tests |
| 4 | Trade Log | Entry/exit, size, rationale, P&L per trade |
| 5 | Fee Schedule | AUM tiers, basis points, annual/monthly amounts |
| 6 | Budget Model | Revenue, expenses, variance, YTD |
| 7 | Data Export | Clean tabular data from systems/CSVs |
| 8 | Onboarding Checklist | Tasks, owners, due dates, status |
| 9 | Financial Model | DCF, assumptions, projections |
| 10 | General Purpose | Any spreadsheet that doesn't fit above |

---

## Reading and Analyzing Files

### With pandas (data analysis)

```python
import pandas as pd

# Read
df = pd.read_excel("file.xlsx")                          # First sheet
all_sheets = pd.read_excel("file.xlsx", sheet_name=None) # All sheets

# Inspect
print(df.head())
print(df.info())
print(df.describe())

# Write clean output
df.to_excel("output.xlsx", index=False)
```

### With openpyxl (read formulas/formatting)

```python
from openpyxl import load_workbook

# Read formulas (not calculated values)
wb = load_workbook("file.xlsx")

# Read calculated values only (formulas become None)
wb_values = load_workbook("file.xlsx", data_only=True)

# ⚠ WARNING: If you save a data_only workbook, all formulas are permanently lost
```

---

## Creating New Excel Files

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

wb = Workbook()
sheet = wb.active
sheet.title = "REPORT"    # Always ALL CAPS tab names

# 1. Title block
write_title_block(sheet, "PORTFOLIO PERFORMANCE REPORT", "As of December 31, 2024")
sheet.merge_cells("A1:G1")
sheet.merge_cells("A2:G2")

# 2. Column headers (row 4, after spacer row 3)
headers = ["DATE", "STRATEGY", "RETURN %", "BENCHMARK %", "ALPHA %", "AUM ($MM)", "NOTES"]
for col, header in enumerate(headers, start=1):
    sheet.cell(row=4, column=col).value = header
style_header_row(sheet, 4, len(headers))

# 3. Data
data = [...]  # list of lists
for row_idx, row_data in enumerate(data, start=5):
    for col_idx, value in enumerate(row_data, start=1):
        sheet.cell(row=row_idx, column=col_idx).value = value
style_data_rows(sheet, 5, 5 + len(data) - 1, len(headers))

# 4. Footer
footer_row = 5 + len(data) + 1
write_footer(sheet, footer_row, len(headers))

# 5. Column widths
col_widths = [12, 20, 12, 14, 10, 12, 30]
for i, width in enumerate(col_widths, start=1):
    sheet.column_dimensions[get_column_letter(i)].width = width

wb.save("/mnt/user-data/outputs/Potomac_PerformanceReport.xlsx")
```

---

## Editing Existing Files

```python
from openpyxl import load_workbook

wb = load_workbook("existing.xlsx")

# List sheets
print(wb.sheetnames)

# Target a specific sheet
sheet = wb["PERFORMANCE"]   # or wb.active

# Modify cells
sheet["C5"] = "=B5/B4-1"    # Always use formulas, not hardcoded values
sheet.insert_rows(6)         # Insert row above row 6
sheet.delete_rows(10)
sheet.insert_cols(3)
sheet.delete_cols(5)

# Re-apply brand styling to modified rows (don't leave unstyled rows)
style_data_rows(sheet, 6, 6, sheet.max_column)

wb.save("modified.xlsx")
```

---

## Formula Rules (Critical)

**Always use Excel formulas — never hardcode calculated values.**

```python
# ❌ WRONG
total = sum(values)
sheet["B10"] = total          # Hardcoded, won't update

# ✅ CORRECT
sheet["B10"] = "=SUM(B2:B9)"  # Dynamic, updates with data

# ✅ Cross-sheet references
sheet["C5"] = "=Holdings!B5*Holdings!C5"

# ✅ Conditional
sheet["D5"] = "=IF(C5>0,C5/B5-1,0)"

# ✅ Financial
sheet["E5"] = "=IFERROR((C5-B5)/ABS(B5),0)"
```

### Formula Verification

After writing formulas, **always recalculate**:

```bash
python scripts/recalc.py output.xlsx 30
```

Check the JSON output:
```json
{
  "status": "success",       ← target this
  "total_errors": 0,
  "total_formulas": 42
}
```

If `status` is `errors_found`, fix each location in `error_summary` and recalculate again. **Never deliver a file with formula errors.**

---

## Number Formatting Standards

```python
from openpyxl.styles import numbers

# Percentages (1 decimal)
cell.number_format = "0.0%"

# Currency — dollars, in millions
cell.number_format = '$#,##0.0;($#,##0.0);"-"'

# Integers with commas
cell.number_format = "#,##0;(#,##0);-"

# Basis points
cell.number_format = "0.0"

# Multiples (1 decimal + x)
cell.number_format = '0.0"x"'

# Dates
cell.number_format = "MMM D, YYYY"

# Years as text (avoid comma-formatting years)
sheet["A1"] = "2024"   # string, not number
```

**Rules:**
- Zeros display as `-` (not `0` or `0.0`)
- Negative numbers use parentheses `(123)` not minus `-123`
- Currency headers must specify units: `RETURN ($MM)`, `AUM ($B)`

---

## Multi-Sheet Workbooks

```python
from openpyxl import Workbook
from openpyxl.styles.colors import Color
from openpyxl.styles import PatternFill

wb = Workbook()

# Sheet tab colors (brand-consistent)
sheet_config = [
    ("SUMMARY",       "FEC00F"),   # Yellow — summary / overview
    ("PERFORMANCE",   "212121"),   # Dark gray — data sheets
    ("HOLDINGS",      "212121"),
    ("RISK",          "EB2F5C"),   # Pink — risk / alert sheets
]

for idx, (name, tab_color) in enumerate(sheet_config):
    if idx == 0:
        sheet = wb.active
        sheet.title = name
    else:
        sheet = wb.create_sheet(name)
    sheet.sheet_properties.tabColor = tab_color

# Remove default "Sheet" if unused
if "Sheet" in wb.sheetnames and wb["Sheet"].max_row == 1:
    del wb["Sheet"]
```

---

## Financial Model Color-Coding

For financial models specifically, follow industry-standard color conventions **in addition to** Potomac brand styling:

| Cell type | Text color | Hex |
|-----------|-----------|-----|
| Hardcoded input | Blue | `0000FF` |
| Formula / calculation | Black | `000000` |
| Cross-sheet link | Green | `008000` |
| External link | Red | `FF0000` |
| Key assumption (background) | Yellow | `FFFF00` |

```python
def input_cell_font():
    return Font(name="Calibri", color="0000FF", size=10)

def formula_cell_font():
    return Font(name="Calibri", color="000000", size=10)

def link_cell_font():
    return Font(name="Calibri", color="008000", size=10)
```

> Yellow background for key assumptions coexists with Potomac brand yellows — use bright `FFFF00` for input cells to distinguish from the brand's `FEC00F` header fills.

---

## Compliance & Disclosure

Every Potomac spreadsheet distributed externally must include a disclosure tab or footer row:

```python
DISCLOSURE_TEXT = (
    "IMPORTANT DISCLOSURES: Past performance is not indicative of future results. "
    "This material is for informational purposes only and does not constitute investment advice. "
    "Potomac | potomac.com | Built to Conquer Risk®"
)
```

For external workbooks (performance reports, proposals, fact sheets), add a `DISCLOSURES` sheet:

```python
disc_sheet = wb.create_sheet("DISCLOSURES")
disc_sheet.sheet_properties.tabColor = "212121"
disc_sheet["A1"] = "DISCLOSURES"
disc_sheet["A1"].font = Font(name="Calibri", bold=True, size=14, color=POTOMAC_GRAY)
disc_sheet["A1"].fill = yellow_fill()
disc_sheet["A2"] = DISCLOSURE_TEXT
disc_sheet["A2"].font = Font(name="Calibri", size=9, color=POTOMAC_GRAY)
disc_sheet["A2"].alignment = Alignment(wrap_text=True)
disc_sheet.column_dimensions["A"].width = 120
disc_sheet.row_dimensions[2].height = 60
```

---

## Page Setup (for Printable Reports)

```python
from openpyxl.worksheet.page import PageMargins

sheet.page_setup.orientation = "landscape"   # or "portrait"
sheet.page_setup.paperSize = 1               # Letter
sheet.page_setup.fitToWidth = 1
sheet.page_setup.fitToHeight = 0
sheet.print_title_rows = "1:4"               # Repeat header rows on every printed page

# Margins in inches
sheet.page_margins = PageMargins(
    left=0.75, right=0.75, top=0.75, bottom=0.75,
    header=0.3, footer=0.3
)

# Header/Footer text (printed)
sheet.oddHeader.center.text = "POTOMAC | &[Tab]"
sheet.oddFooter.left.text = "Built to Conquer Risk®"
sheet.oddFooter.right.text = "Page &[Page] of &[Pages]"
sheet.oddFooter.center.text = "CONFIDENTIAL"
```

---

## Output & File Naming

```bash
# Always output to:
/mnt/user-data/outputs/Potomac_[DocumentName].xlsx

# Examples:
Potomac_PerformanceReport_Q42024.xlsx
Potomac_PortfolioTracker.xlsx
Potomac_RiskDashboard.xlsx
Potomac_TradeLog.xlsx
Potomac_FeeSchedule.xlsx
Potomac_BudgetModel_FY2025.xlsx
```

---

## Quality Checklist

Before presenting any file:

- [ ] Tab names: ALL CAPS
- [ ] Column headers: ALL CAPS, Calibri Bold, yellow fill `#FEC00F`
- [ ] Body text: Calibri, dark gray `#212121`
- [ ] Title block present on each sheet (row 1–2)
- [ ] Disclosure footer or DISCLOSURES sheet present (external files)
- [ ] Formulas used — no hardcoded calculations
- [ ] `scripts/recalc.py` run → `"status": "success"`, zero errors
- [ ] Number formats applied (%, $, commas, zeros as `-`)
- [ ] Company name is "Potomac" — never "Potomac Fund Management"
- [ ] File saved to `/mnt/user-data/outputs/Potomac_[Name].xlsx`

---

## Reference Files

| File | When to Read |
|------|-------------|
| `references/templates.md` | Column layouts and formula patterns for all 10 document types |
| `references/formulas.md` | Common financial formula patterns (returns, drawdown, VaR, Sharpe) |
| `scripts/recalc.py` | Always run after writing formulas — never skip |
