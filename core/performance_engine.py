"""
performance_engine.py
─────────────────────────────────────────────────────────────────────────────
Potomac Fund Management — Headless Performance Calculation Engine
─────────────────────────────────────────────────────────────────────────────

PURPOSE
    Designed to be called as a Claude tool so the LLM NEVER fabricates numbers.
    Every metric is calculated from live Yahoo Finance data and returned as a
    clean, serialisable dict that the LLM can cite verbatim.

TOOL SIGNATURE (registered in core/tools.py)
    name        : "calculate_performance"
    description : "Fetch live price data for a ticker and compute a full suite
                   of performance and risk metrics since inception. Always
                   call this tool before quoting any performance number."
    parameters  :
        ticker   (str)  – Yahoo Finance ticker symbol, e.g. "SIVR"
        freq     (str)  – "daily" | "weekly" | "monthly" (default "daily")
        initial  (float)– Hypothetical starting capital (default 100000)

USAGE (standalone / test)
    python performance_engine.py --ticker SIVR --freq daily --initial 100000

INSTALL
    pip install yfinance numpy
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Optional

import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None  # checked at runtime in fetch_prices


# ══════════════════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════════════════

FREQ_MAP = {
    "daily":   ("1d",  252.0),
    "weekly":  ("1wk",  52.0),
    "monthly": ("1mo",  12.0),
}

NA = None  # sentinel for "not enough data / undefined"


# ══════════════════════════════════════════════════════════════════════════════
#  Data fetch
# ══════════════════════════════════════════════════════════════════════════════

def fetch_prices(ticker: str, interval: str):
    """
    Download full-history close prices from Yahoo Finance.
    Returns (price_array, date_strings_list) or raises ValueError.
    """
    if yf is None:
        raise ValueError("yfinance is required: pip install yfinance")

    data = yf.download(
        ticker,
        period="max",
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    if data is None or data.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'.")

    # Flatten MultiIndex columns (single ticker still sometimes returns them)
    if hasattr(data.columns, "levels"):
        data.columns = data.columns.get_level_values(0)

    close = data["Close"].dropna()

    if len(close) < 10:
        raise ValueError(
            f"Insufficient data for '{ticker}': only {len(close)} bars available."
        )

    prices = np.array(close.values, dtype=float)
    dates = [str(d)[:10] for d in close.index]  # "YYYY-MM-DD"
    return prices, dates


# ══════════════════════════════════════════════════════════════════════════════
#  Core maths helpers
# ══════════════════════════════════════════════════════════════════════════════

def _safe(val, decimals: int = 4):
    """Round to decimals places; return None if NaN/Inf."""
    if val is None or not math.isfinite(val):
        return None
    return round(float(val), decimals)


def _drawdown_series(prices: np.ndarray) -> np.ndarray:
    """Return element-wise drawdown from running peak (values ≤ 0)."""
    peak = np.maximum.accumulate(prices)
    return (prices - peak) / peak


def _linear_regression(y: np.ndarray):
    """Return (slope, intercept, residuals) of OLS on y vs 0..N-1."""
    x = np.arange(len(y), dtype=float)
    xm = x.mean()
    ym = y.mean()
    ssxx = np.sum((x - xm) ** 2)
    ssxy = np.sum((x - xm) * (y - ym))
    slope = ssxy / ssxx if ssxx != 0 else 0.0
    intercept = ym - slope * xm
    residuals = y - (slope * x + intercept)
    return slope, intercept, residuals


# ══════════════════════════════════════════════════════════════════════════════
#  Metric computations
# ══════════════════════════════════════════════════════════════════════════════

def compute_all(
    prices: np.ndarray,
    dates,
    ppy: float,           # periods per year
    initial_capital: float,
) -> dict:
    """
    Compute every performance and risk metric from the QUADRA-PM report
    plus the full set from the GUI calculator.

    All percentage values are stored as plain floats (e.g. 7.35 means 7.35%).
    Dollar values are in the same currency as 'initial_capital'.
    """

    n = len(prices)
    ret: dict = {}

    # ── 0. Metadata ────────────────────────────────────────────────────────────
    ret["meta"] = {
        "start_date":      dates[0],
        "end_date":        dates[-1],
        "bars":            n,
        "start_price":     _safe(prices[0], 4),
        "end_price":       _safe(prices[-1], 4),
        "initial_capital": initial_capital,
    }

    # ── 1. Period returns ──────────────────────────────────────────────────────
    period_rets = np.diff(prices) / prices[:-1]  # simple returns, length n-1

    years = (
        (np.datetime64(dates[-1]) - np.datetime64(dates[0]))
        / np.timedelta64(365, "D")
    )
    years = float(years)
    ret["meta"]["years"] = _safe(years, 2)

    # ── 2. Return metrics ──────────────────────────────────────────────────────
    total_return_pct = (prices[-1] / prices[0] - 1.0) * 100.0
    cagr_pct = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100.0 \
        if years > 0 else None

    final_equity = initial_capital * (1 + total_return_pct / 100.0)
    net_profit_usd = final_equity - initial_capital
    net_profit_pct = total_return_pct

    exposure_pct = 100.0  # buy-and-hold: always fully invested
    rar_pct = cagr_pct / (exposure_pct / 100.0) if cagr_pct is not None else None

    ret["returns"] = {
        "annual_return_pct":   _safe(cagr_pct, 4),
        "total_return_pct":    _safe(total_return_pct, 4),
        "net_profit_usd":      _safe(net_profit_usd, 2),
        "net_profit_pct":      _safe(net_profit_pct, 4),
        "final_equity_usd":    _safe(final_equity, 2),
        "exposure_pct":        _safe(exposure_pct, 2),
        "risk_adj_return_pct": _safe(rar_pct, 4),
    }

    # ── 3. Drawdown metrics ────────────────────────────────────────────────────
    dd_series = _drawdown_series(prices)
    max_dd_pct = float(dd_series.min()) * 100.0
    trough_i = int(np.argmin(dd_series))

    peak_i = int(np.argmax(prices[:trough_i + 1]))
    peak_price = prices[peak_i]
    trough_price = prices[trough_i]

    max_dd_usd = (peak_price - trough_price) / prices[0] * initial_capital

    peak_date = dates[peak_i]
    trough_date = dates[trough_i]
    dd_duration = (
        np.datetime64(trough_date) - np.datetime64(peak_date)
    ) / np.timedelta64(1, "D")
    dd_duration_days = int(dd_duration)

    recovery_date = None
    recovery_bars = None
    for j in range(trough_i + 1, n):
        if prices[j] >= peak_price:
            recovery_date = dates[j]
            recovery_bars = j - trough_i
            break

    ret["drawdown"] = {
        "max_system_drawdown_pct": _safe(max_dd_pct, 4),
        "max_system_drawdown_usd": _safe(max_dd_usd, 2),
        "max_trade_drawdown_pct":  _safe(max_dd_pct, 4),
        "max_trade_drawdown_usd":  _safe(max_dd_usd, 2),
        "peak_date":               peak_date,
        "trough_date":              trough_date,
        "recovery_date":            recovery_date,
        "dd_duration_days":         dd_duration_days,
        "recovery_bars":            recovery_bars,
    }

    # ── 4. Risk-adjusted ratios ────────────────────────────────────────────────
    abs_max_dd = abs(max_dd_pct)

    recovery_factor = net_profit_usd / max_dd_usd if max_dd_usd != 0 else None
    car_maxdd = cagr_pct / abs_max_dd if (cagr_pct is not None and abs_max_dd != 0) else None
    rar_maxdd = rar_pct / abs_max_dd if (rar_pct is not None and abs_max_dd != 0) else None
    net_rar = net_profit_pct / abs_max_dd if abs_max_dd != 0 else None

    ret["risk_ratios"] = {
        "net_risk_adj_return": _safe(net_rar, 4),
        "recovery_factor":     _safe(recovery_factor, 4),
        "car_maxdd":           _safe(car_maxdd, 4),
        "rar_maxdd":           _safe(rar_maxdd, 4),
    }

    # ── 5. Volatility and regression statistics ────────────────────────────────
    ann_vol_pct = float(period_rets.std(ddof=1)) * math.sqrt(ppy) * 100.0
    ann_return_pct = cagr_pct if cagr_pct is not None else 0.0

    sharpe = ann_return_pct / ann_vol_pct if ann_vol_pct != 0 else None
    rr_ratio = ann_return_pct / ann_vol_pct if ann_vol_pct != 0 else None

    log_prices = np.log(prices)
    slope, intercept, residuals = _linear_regression(log_prices)
    std_error_pct = float(residuals.std(ddof=1)) * 100.0

    x = np.arange(n, dtype=float)
    xm = x.mean()
    ssxx = float(np.sum((x - xm) ** 2))
    res_var = float(residuals.var(ddof=2)) if n > 2 else None
    if res_var is not None and ssxx > 0:
        se_slope = math.sqrt(res_var / ssxx)
        k_ratio = slope / (n * se_slope) if se_slope != 0 else None
    else:
        k_ratio = None

    ret["statistics"] = {
        "ann_volatility_pct": _safe(ann_vol_pct, 4),
        "sharpe_ratio":       _safe(sharpe, 4),
        "risk_reward_ratio":  _safe(rr_ratio, 4),
        "std_error_pct":      _safe(std_error_pct, 4),
        "k_ratio":            _safe(k_ratio, 6),
    }

    # ── 6. Ulcer metrics ───────────────────────────────────────────────────────
    dd_pct_series = dd_series * 100.0
    ulcer_index = float(math.sqrt(np.mean(dd_pct_series ** 2)))
    upi = ann_return_pct / ulcer_index if ulcer_index != 0 else None

    ret["ulcer"] = {
        "ulcer_index":             _safe(ulcer_index, 4),
        "ulcer_performance_index": _safe(upi, 4),
    }

    # ── 7. Trade-level stats (single buy-and-hold "trade") ────────────────────
    avg_win_pct = total_return_pct if total_return_pct > 0 else 0.0
    avg_loss_pct = total_return_pct if total_return_pct < 0 else 0.0
    win_rate_pct = 100.0 if total_return_pct > 0 else 0.0
    profit_factor = None
    wl_ratio = None

    if ppy >= 200:  # daily → compute monthly roll-ups
        monthly_rets = []
        for i in range(0, len(period_rets) - 20, 21):
            chunk = period_rets[i:i + 21]
            monthly_rets.append(float(np.prod(1 + chunk) - 1) * 100.0)
        if monthly_rets:
            wins = [r for r in monthly_rets if r > 0]
            losses = [r for r in monthly_rets if r <= 0]
            avg_win_pct = float(np.mean(wins)) if wins else 0.0
            avg_loss_pct = float(np.mean(losses)) if losses else 0.0
            win_rate_pct = len(wins) / len(monthly_rets) * 100.0
            wl_ratio = abs(avg_win_pct / avg_loss_pct) if avg_loss_pct != 0 else None
            total_won = sum(wins)
            total_lost = abs(sum(losses))
            profit_factor = total_won / total_lost if total_lost != 0 else None

    ret["trade_stats"] = {
        "avg_win_pct":    _safe(avg_win_pct, 4),
        "avg_loss_pct":   _safe(avg_loss_pct, 4),
        "win_loss_ratio": _safe(wl_ratio, 4),
        "win_rate_pct":   _safe(win_rate_pct, 4),
        "profit_factor":  _safe(profit_factor, 4),
        "note": (
            "Trade stats are decomposed into approximate monthly periods for "
            "daily/weekly data. For a pure buy-and-hold there is 1 trade."
        ),
    }

    return ret


# ══════════════════════════════════════════════════════════════════════════════
#  Public entry point — this is what the Claude tool calls
# ══════════════════════════════════════════════════════════════════════════════

def calculate_performance(
    ticker: str,
    freq: str = "daily",
    initial: float = 100_000.0,
) -> dict:
    """
    Main entry point for the Claude tool.

    Parameters
    ----------
    ticker  : Yahoo Finance symbol (e.g. "SIVR", "PHYS", "SPY")
    freq    : "daily" | "weekly" | "monthly"
    initial : hypothetical starting capital (default 100,000)

    Returns
    -------
    dict with keys: status, ticker, frequency, meta, returns, drawdown,
    risk_ratios, statistics, ulcer, trade_stats.
    On failure: {"status": "error", "error": "..."}
    """
    freq = (freq or "daily").lower().strip()
    if freq not in FREQ_MAP:
        return {
            "status": "error",
            "error":  f"Invalid freq '{freq}'. Must be daily, weekly, or monthly.",
        }

    interval, ppy = FREQ_MAP[freq]
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"status": "error", "error": "Missing ticker symbol."}

    try:
        prices, dates = fetch_prices(ticker, interval)
    except ValueError as exc:
        return {"status": "error", "error": str(exc)}
    except Exception as exc:
        return {"status": "error", "error": f"Data fetch failed: {exc}"}

    try:
        result = compute_all(prices, dates, ppy, float(initial))
    except Exception as exc:
        return {"status": "error", "error": f"Calculation failed: {exc}"}

    return {
        "status":    "ok",
        "ticker":    ticker,
        "frequency": freq,
        **result,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CLI — for testing outside the LLM context
# ══════════════════════════════════════════════════════════════════════════════

def _cli():
    parser = argparse.ArgumentParser(
        description="Potomac Performance Engine — headless CLI test"
    )
    parser.add_argument("--ticker",  default="SPY",    help="Yahoo Finance ticker")
    parser.add_argument("--freq",    default="daily",  help="daily | weekly | monthly")
    parser.add_argument("--initial", default=100000.0, type=float,
                        help="Initial capital (default 100000)")
    parser.add_argument("--pretty",  action="store_true",
                        help="Pretty-print JSON output")
    args = parser.parse_args()

    result = calculate_performance(args.ticker, args.freq, args.initial)
    indent = 2 if args.pretty else None
    print(json.dumps(result, indent=indent))

    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    _cli()
