# Potomac Excel Templates Reference

Full column layouts, sheet structures, and formula patterns for each of the 10 standard Potomac spreadsheet types.

---

## 1. Performance Report

**Sheet layout:**
- Tab name: `PERFORMANCE`
- Tab color: `FEC00F`

**Columns:**
| Col | Header | Format | Notes |
|-----|--------|--------|-------|
| A | DATE | `MMM YYYY` | Month-end date |
| B | STRATEGY | Text | Strategy name |
| C | RETURN (%) | `0.00%` | Monthly net return |
| D | BENCHMARK (%) | `0.00%` | e.g., S&P 500 |
| E | ALPHA (%) | `=C#-D#` | Excess return formula |
| F | AUM ($MM) | `$#,##0.0` | Month-end AUM |
| G | CUMULATIVE RETURN (%) | `=PRODUCT(1+C$5:C#)-1` | Running cumulative |
| H | NOTES | Text | Commentary |

**Summary row formulas:**
```excel
=AVERAGE(C5:C100)     → Average monthly return
=MAX(C5:C100)         → Best month
=MIN(C5:C100)         → Worst month
=STDEV(C5:C100)*SQRT(12)  → Annualized volatility
=AVERAGE(E5:E100)     → Average alpha
```

**Additional sheets:** `SUMMARY`, `BENCHMARK_DATA`, `DISCLOSURES`

---

## 2. Portfolio Tracker

**Sheet layout:**
- Tab name: `HOLDINGS`
- Tab color: `212121`

**Columns:**
| Col | Header | Format | Notes |
|-----|--------|--------|-------|
| A | TICKER | Text | Symbol |
| B | NAME | Text | Full security name |
| C | ASSET CLASS | Text | Equity / Fixed / Alt |
| D | SHARES / UNITS | `#,##0.00` | Quantity |
| E | COST BASIS ($) | `$#,##0.00` | Per unit |
| F | CURRENT PRICE ($) | `$#,##0.00` | Live/manual |
| G | MARKET VALUE ($) | `=D#*F#` | Formula |
| H | WEIGHT (%) | `=G#/SUM($G$5:$G$100)` | Portfolio % |
| I | UNREALIZED P&L ($) | `=(F#-E#)*D#` | Formula |
| J | UNREALIZED P&L (%) | `=IFERROR((F#-E#)/E#,0)` | Formula |
| K | BETA | `0.00` | Input |
| L | NOTES | Text | |

**Summary cells:**
```excel
Total Market Value:  =SUM(G5:G100)
Total Cost:          =SUMPRODUCT(D5:D100, E5:E100)
Total P&L ($):       =SUM(I5:I100)
Total P&L (%):       =IFERROR(SUM(I5:I100)/SUMPRODUCT(D5:D100,E5:E100), 0)
Portfolio Beta:      =SUMPRODUCT(H5:H100, K5:K100)
```

**Additional sheets:** `SUMMARY`, `BY_ASSET_CLASS`, `DISCLOSURES`

---

## 3. Risk Dashboard

**Sheet layout:**
- Tab name: `RISK`
- Tab color: `EB2F5C`

**Section 1 — VaR Summary:**
| Col | Header | Format |
|-----|--------|--------|
| A | METRIC | Text |
| B | VALUE | `0.00%` or `$#,##0` |
| C | LIMIT | `0.00%` |
| D | STATUS | `=IF(B#>C#,"BREACH","OK")` |

**Rows (section 1):**
- 1-Day VaR (95%)
- 1-Day VaR (99%)
- 10-Day VaR (95%)
- Expected Shortfall (CVaR)
- Max Drawdown (MTD)
- Max Drawdown (YTD)

**Section 2 — Stress Tests:**
| Col | Header | Format |
|-----|--------|--------|
| A | SCENARIO | Text |
| B | PORTFOLIO P&L ($MM) | `$#,##0.0` |
| C | PORTFOLIO RETURN (%) | `0.00%` |
| D | BENCHMARK RETURN (%) | `0.00%` |

**Rows (section 2):**
- 2008 Global Financial Crisis
- 2020 COVID Shock (Mar)
- 2022 Rate Spike
- 10% Equity Selloff
- 100bps Rate Rise
- Dollar +10%

**Additional sheets:** `FACTOR_EXPOSURE`, `CORRELATIONS`, `LIQUIDITY`, `DISCLOSURES`

---

## 4. Trade Log

**Sheet layout:**
- Tab name: `TRADE LOG`
- Tab color: `212121`

**Columns:**
| Col | Header | Format |
|-----|--------|--------|
| A | DATE | `MMM D, YYYY` |
| B | TICKER | Text |
| C | NAME | Text |
| D | DIRECTION | Text (BUY / SELL / SHORT) |
| E | ASSET CLASS | Text |
| F | STRATEGY | Text |
| G | SHARES | `#,##0` |
| H | ENTRY PRICE ($) | `$#,##0.00` |
| I | EXIT PRICE ($) | `$#,##0.00` |
| J | GROSS P&L ($) | `=(I#-H#)*G#` |
| K | COMMISSION ($) | `$#,##0.00` |
| L | NET P&L ($) | `=J#-K#` |
| M | RETURN (%) | `=IFERROR(L#/(H#*G#),0)` |
| N | STATUS | Text (OPEN / CLOSED) |
| O | RATIONALE | Text |

**Summary formulas:**
```excel
Total Net P&L:        =SUM(L5:L1000)
Win Rate:             =COUNTIF(L5:L1000,">0")/COUNTA(L5:L1000)
Avg Win ($):          =AVERAGEIF(L5:L1000,">0",L5:L1000)
Avg Loss ($):         =AVERAGEIF(L5:L1000,"<0",L5:L1000)
Profit Factor:        =IFERROR(SUMIF(L5:L1000,">0")/ABS(SUMIF(L5:L1000,"<0")),0)
```

---

## 5. Fee Schedule

**Sheet layout:**
- Tab name: `FEE SCHEDULE`
- Tab color: `FEC00F`

**Columns:**
| Col | Header | Format |
|-----|--------|--------|
| A | AUM TIER (FROM $MM) | `$#,##0.0` |
| B | AUM TIER (TO $MM) | `$#,##0.0` |
| C | ANNUAL RATE (BPS) | `0.0` |
| D | ANNUAL RATE (%) | `=C#/10000` |
| E | QUARTERLY RATE (%) | `=D#/4` |
| F | MONTHLY RATE (%) | `=D#/12` |
| G | EXAMPLE AUM ($MM) | Input |
| H | ANNUAL FEE ($) | `=G#*D#*1000000` |

**AUM tiers (standard Potomac):**
```
$0      – $1MM     | 100 bps
$1MM    – $5MM     |  85 bps
$5MM    – $10MM    |  75 bps
$10MM   – $25MM    |  65 bps
$25MM+             |  50 bps
```

---

## 6. Budget Model

**Sheet layout:**
- Tab names: `SUMMARY`, `REVENUE`, `EXPENSES`, `HEADCOUNT`, `DISCLOSURES`
- SUMMARY tab color: `FEC00F`; others: `212121`

**REVENUE columns:**
| Col | Header | Format |
|-----|--------|--------|
| A | CATEGORY | Text |
| B | BUDGET ($) | `$#,##0` |
| C–N | JAN–DEC ACTUAL ($) | `$#,##0` |
| O | YTD ACTUAL ($) | `=SUM(C#:N#)` |
| P | VARIANCE ($) | `=O#-B#` |
| Q | VARIANCE (%) | `=IFERROR(P#/B#,0)` |

**EXPENSES:** Same structure as REVENUE.

**SUMMARY tab:**
```excel
Total Revenue:   =SUM(REVENUE!O5:O50)
Total Expenses:  =SUM(EXPENSES!O5:O50)
EBITDA:          =B5-B6
EBITDA Margin:   =IFERROR(B7/B5,0)
```

---

## 7. Data Export / Clean Table

**Sheet layout:**
- Tab name: (matches data topic, ALL CAPS)
- Tab color: `212121`
- No title block needed for pure data exports — start with headers at row 1

**Rules for data exports:**
- Row 1 = column headers (yellow fill, bold, ALL CAPS)
- Row 2+ = data (alternating white / `F5F5F5`)
- Freeze top row: `sheet.freeze_panes = "A2"`
- Auto-filter: `sheet.auto_filter.ref = sheet.dimensions`
- No merged cells in data range
- Dates in ISO format `YYYY-MM-DD` or `MMM D, YYYY`

---

## 8. Onboarding Checklist

**Sheet layout:**
- Tab name: `ONBOARDING`
- Tab color: `FEC00F`

**Columns:**
| Col | Header | Format |
|-----|--------|--------|
| A | # | `0` |
| B | PHASE | Text (Pre-Onboard / Week 1 / Month 1) |
| C | TASK | Text |
| D | OWNER | Text |
| E | DUE DATE | `MMM D, YYYY` |
| F | STATUS | Text (NOT STARTED / IN PROGRESS / COMPLETE) |
| G | NOTES | Text |

**Conditional formatting for STATUS:**
```python
from openpyxl.formatting.rule import CellIsRule

# Green for COMPLETE
sheet.conditional_formatting.add(
    f"F5:F200",
    CellIsRule(operator="equal", formula=['"COMPLETE"'],
               fill=PatternFill("solid", fgColor="C6EFCE"),
               font=Font(color="276221"))
)
# Yellow for IN PROGRESS
sheet.conditional_formatting.add(
    f"F5:F200",
    CellIsRule(operator="equal", formula=['"IN PROGRESS"'],
               fill=PatternFill("solid", fgColor="FFEB9C"),
               font=Font(color="9C5700"))
)
```

---

## 9. Financial Model

**Sheet layout:**
- Tab names: `ASSUMPTIONS`, `DCF`, `COMPARABLES`, `OUTPUT`, `DISCLOSURES`
- ASSUMPTIONS tab color: `FEC00F`

**ASSUMPTIONS sheet:**
All inputs in blue text (`0000FF`), labeled clearly:
```
WACC:               10.5%
Terminal Growth:     2.5%
Tax Rate:           21.0%
Projection Years:      5
```

**DCF columns (years across):**
| Row | Label | Y1 | Y2 | Y3 | Y4 | Y5 | Terminal |
|-----|-------|----|----|----|----|----|---------|
| Revenue | `$#,##0` | Input or formula |
| Revenue Growth | `0.0%` | `=(C#/B#)-1` |
| EBIT Margin | `0.0%` | Input |
| EBIT | `$#,##0` | `=C*C_margin` |
| NOPAT | `$#,##0` | `=EBIT*(1-tax)` |
| D&A | `$#,##0` | Input |
| CapEx | `$(#,##0)` | Input |
| ΔNWC | `$(#,##0)` | Input |
| FCFF | `$#,##0` | `=NOPAT+D&A-CapEx-ΔNWC` |
| Discount Factor | `0.000` | `=1/(1+WACC)^n` |
| PV of FCFF | `$#,##0` | `=FCFF*DF` |

```excel
Terminal Value:     =FCFF_Y5*(1+g)/(WACC-g)
PV Terminal Value:  =TV*DF_Y5
Enterprise Value:   =SUM(PV_FCFF) + PV_TV
Equity Value:       =EV - Net_Debt
Value per Share:    =Equity_Value / Shares_Out
```

---

## 10. General Purpose

**Sheet layout:**
- Tab name: `DATA` (rename to topic)
- Tab color: `FEC00F`

**Structure:**
1. Title block (rows 1–2)
2. Column headers (row 4)
3. Data rows (row 5+)
4. Totals row (last data row + 1, yellow fill)
5. Footer / disclosure (last row)

**Totals row pattern:**
```python
totals_row = last_data_row + 2
sheet.cell(row=totals_row, column=1).value = "TOTAL"
sheet.cell(row=totals_row, column=1).font = header_font()
# Sum numeric columns
for col in numeric_columns:
    sheet.cell(row=totals_row, column=col).value = f"=SUM({get_column_letter(col)}5:{get_column_letter(col)}{last_data_row})"
    sheet.cell(row=totals_row, column=col).font = header_font()
# Style totals row
for c in range(1, total_cols + 1):
    sheet.cell(row=totals_row, column=c).fill = light_yellow_fill()
    sheet.cell(row=totals_row, column=c).border = thin_border()
```
