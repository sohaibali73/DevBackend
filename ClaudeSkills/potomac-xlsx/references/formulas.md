# Potomac Excel — Financial Formula Patterns

Common financial formulas used across Potomac spreadsheets. Reference this file when building financial models, performance reports, or risk dashboards.

---

## Return Calculations

```excel
# Simple return
= (P_end - P_start) / P_start

# Logarithmic (continuous) return
= LN(P_end / P_start)

# Cumulative return from a series of period returns
= PRODUCT(1 + C5:C100) - 1   ← array formula (Ctrl+Shift+Enter) or use REDUCE in newer Excel

# Annualized return from cumulative (n periods, T = periods per year)
= (1 + cumulative_return)^(T/n) - 1

# Annualized from monthly returns (12-period year)
= PRODUCT(1+C5:C16)^(12/12) - 1

# Alpha = Portfolio Return - Benchmark Return
= portfolio_return - benchmark_return
```

---

## Risk Metrics

```excel
# Standard deviation (sample)
= STDEV(C5:C100)

# Annualized volatility (monthly returns → annual)
= STDEV(C5:C100) * SQRT(12)

# Sharpe Ratio
= (annualized_return - risk_free_rate) / annualized_volatility
= IFERROR((AVERAGE(C5:C100)*12 - risk_free_rate) / (STDEV(C5:C100)*SQRT(12)), 0)

# Sortino Ratio (only downside deviation)
# Step 1: Downside returns
= IF(C5<0, C5, 0)   → in helper column
# Step 2: Downside deviation
= SQRT(SUMPRODUCT((IF(C5:C100<0,C5:C100,0))^2)/COUNT(C5:C100)) * SQRT(12)
# Step 3: Sortino
= (annualized_return - risk_free_rate) / downside_deviation

# Information Ratio
= AVERAGE(alpha_series) / STDEV(alpha_series) * SQRT(12)
```

---

## Drawdown

```excel
# Running maximum (cumulative return series in col D)
= MAX($D$5:D5)

# Drawdown at each point
= D5 / MAX($D$5:D5) - 1

# Maximum drawdown over full series
= MIN(drawdown_series)

# Calmar Ratio
= annualized_return / ABS(max_drawdown)
```

---

## VaR (Parametric, Normal Distribution)

```excel
# 1-Day VaR at 95% confidence
= portfolio_value * daily_vol * NORM.S.INV(0.95)

# 1-Day VaR at 99% confidence
= portfolio_value * daily_vol * NORM.S.INV(0.99)

# 10-Day VaR (scale from 1-day using square root of time)
= VaR_1day * SQRT(10)

# CVaR / Expected Shortfall (approx, normal distribution, 95%)
= portfolio_value * daily_vol * NORM.S.DIST(NORM.S.INV(0.05), FALSE) / 0.05
```

---

## Portfolio Analytics

```excel
# Portfolio weight
= market_value_i / SUM(all_market_values)

# Weighted average (e.g., weighted average beta)
= SUMPRODUCT(weights, betas)

# Contribution to return (position weight × position return)
= weight_i * return_i

# Active weight (vs benchmark)
= portfolio_weight_i - benchmark_weight_i

# Tracking error (annualized)
= STDEV(active_returns) * SQRT(12)

# Beta (vs benchmark)
= COVAR(portfolio_returns, benchmark_returns) / VAR(benchmark_returns)

# Correlation
= CORREL(series_a, series_b)

# R-Squared
= CORREL(portfolio_returns, benchmark_returns)^2
```

---

## Fixed Income

```excel
# Bond price (simplified, annual coupon)
= coupon / yield * (1 - 1/(1+yield)^maturity) + face/(1+yield)^maturity

# Modified Duration (approximate)
= -(1/P) * dP/dy

# DV01 (dollar value of a 1bp move)
= -modified_duration * price * 0.0001

# Yield to Maturity (use Excel's RATE function)
= RATE(periods, coupon_payment, -price, face_value)

# Current Yield
= annual_coupon / price
```

---

## AUM and Fee Calculations

```excel
# Annual fee from AUM and rate
= AUM * rate_bps / 10000

# Quarterly fee
= AUM * rate_bps / 10000 / 4

# Monthly fee
= AUM * rate_bps / 10000 / 12

# Tiered fee (blended rate for $X AUM)
= SUMPRODUCT(
    MIN(AUM, tier_maxes) - MIN(AUM, tier_mins),
    tier_rates
  ) / AUM
```

---

## Error-Safe Patterns

Always wrap division and lookup formulas:

```excel
# Safe division
= IFERROR(numerator / denominator, 0)
= IFERROR(numerator / denominator, "-")

# Safe VLOOKUP
= IFERROR(VLOOKUP(key, range, col, FALSE), "")

# Safe INDEX/MATCH
= IFERROR(INDEX(range, MATCH(key, lookup_range, 0)), "")

# Safe percentage change
= IFERROR((new - old) / ABS(old), 0)

# Check for zero denominator explicitly
= IF(denominator=0, "-", numerator/denominator)
```

---

## Date and Time

```excel
# Current date
= TODAY()

# Month-end date
= EOMONTH(date, 0)

# Prior month-end
= EOMONTH(date, -1)

# Days between dates
= end_date - start_date

# Trading days between (approximate)
= NETWORKDAYS(start_date, end_date) - 1

# Year from date
= YEAR(date)

# Quarter
= "Q" & ROUNDUP(MONTH(date)/3, 0)

# Quarter + Year label
= "Q" & ROUNDUP(MONTH(A1)/3,0) & " " & YEAR(A1)
```

---

## Conditional Formatting Rules (Python)

```python
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, CellIsRule
from openpyxl.styles import PatternFill, Font

# Green-Yellow-Red scale (returns, P&L)
sheet.conditional_formatting.add(
    "C5:C100",
    ColorScaleRule(
        start_type="min", start_color="F8696B",   # red
        mid_type="num",   mid_value=0, mid_color="FFEB84",  # yellow at 0
        end_type="max",   end_color="63BE7B"       # green
    )
)

# Data bars (AUM, position sizes)
sheet.conditional_formatting.add(
    "F5:F100",
    DataBarRule(start_type="min", end_type="max", color="FEC00F")  # Potomac yellow bars
)

# Red text for negative P&L
sheet.conditional_formatting.add(
    "L5:L1000",
    CellIsRule(operator="lessThan", formula=["0"],
               font=Font(color="EB2F5C"))  # Potomac pink = alert
)

# Green text for positive P&L
sheet.conditional_formatting.add(
    "L5:L1000",
    CellIsRule(operator="greaterThan", formula=["0"],
               font=Font(color="276221"))
)
```
