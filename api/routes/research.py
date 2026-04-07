"""Research routes — company analysis, strategy analysis, peer comparison."""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from db.supabase_client import get_supabase

router = APIRouter(prefix="/research", tags=["Research"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class StrategyAnalysisRequest(BaseModel):
    strategy_name: str
    description: str
    indicators: List[str] = []
    timeframe: str = "daily"
    risk_parameters: dict = {}


class PeerComparisonRequest(BaseModel):
    symbols: List[str]
    metrics: List[str] = ["revenue", "pe_ratio", "market_cap", "profit_margin"]


# ──────────────────────────────────────────────────────────────────────────────
# Company Search
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/company/search")
async def search_companies(
    q: str = Query(..., min_length=1, description="Ticker or company name"),
    user_id: str = Depends(get_current_user_id),
):
    """Search for companies by ticker or name using yfinance."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(q.upper())
        info = ticker.info or {}

        if not info or not info.get("shortName"):
            # Try search via yfinance search (not always reliable)
            return {
                "results": [{
                    "symbol": q.upper(),
                    "name": info.get("longName") or info.get("shortName") or q.upper(),
                    "exchange": info.get("exchange", ""),
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                }]
            }

        return {
            "results": [{
                "symbol": q.upper(),
                "name": info.get("longName") or info.get("shortName", q.upper()),
                "exchange": info.get("exchange", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
            }]
        }
    except Exception as e:
        logger.warning(f"yfinance company search failed: {e}")
        return {"results": [{"symbol": q.upper(), "name": q.upper(), "exchange": "", "sector": "", "industry": ""}]}


# ──────────────────────────────────────────────────────────────────────────────
# Company Overview
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/company/{symbol}")
async def get_company_info(
    symbol: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get detailed company information."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol.upper())
        info = ticker.info or {}

        return {
            "symbol": symbol.upper(),
            "name": info.get("longName") or info.get("shortName", symbol.upper()),
            "description": info.get("longBusinessSummary", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "website": info.get("website", ""),
            "employees": info.get("fullTimeEmployees"),
            "country": info.get("country", ""),
            "fundamentals": {
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "beta": info.get("beta"),
                "price_to_book": info.get("priceToBook"),
            },
            "financials": {
                "revenue": info.get("totalRevenue"),
                "net_income": info.get("netIncomeToCommon"),
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
            },
            "key_metrics": {
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
            },
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except Exception as e:
        logger.error(f"Company info fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not fetch company data: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Company AI Analysis
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/company/{symbol}/analyze")
async def analyze_company(
    symbol: str,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Generate AI analysis of a company."""
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key required")

    # Fetch company data first
    company_data = await get_company_info(symbol=symbol, user_id=user_id)

    import anthropic
    import json as _json

    client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

    prompt = (
        f"Analyse this company for a stock trader:\n\n"
        f"Company: {company_data['name']} ({symbol})\n"
        f"Sector: {company_data.get('sector')}\n"
        f"Fundamentals: {_json.dumps(company_data.get('fundamentals', {}), indent=2)}\n"
        f"Financials: {_json.dumps(company_data.get('financials', {}), indent=2)}\n\n"
        "Provide:\n"
        "1. A brief investment summary (2-3 sentences)\n"
        "2. 3 key strengths\n"
        "3. 3 key weaknesses/risks\n"
        "4. 2-3 opportunities\n"
        "5. 2-3 threats\n"
        "6. A recommendation: buy/hold/sell\n"
        "7. A price target (if possible)\n"
        "8. Confidence score (0-1)\n\n"
        "Return as JSON with keys: summary, strengths, weaknesses, opportunities, threats, "
        "recommendation, target_price, confidence."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        try:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            result = _json.loads(raw_text)
        except Exception:
            result = {
                "summary": raw_text[:300],
                "strengths": [],
                "weaknesses": [],
                "opportunities": [],
                "threats": [],
                "recommendation": "hold",
                "target_price": None,
                "confidence": 0.5,
            }

        return {
            "symbol": symbol.upper(),
            "name": company_data["name"],
            **result,
        }

    except Exception as e:
        logger.error(f"Company analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Strategy Analysis
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/strategy/analyze")
async def analyze_strategy(
    request: StrategyAnalysisRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Analyse trading strategy viability using AI."""
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key required")

    import anthropic
    import json as _json

    client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

    prompt = (
        f"Analyse this AmiBroker AFL trading strategy:\n\n"
        f"Name: {request.strategy_name}\n"
        f"Description: {request.description}\n"
        f"Indicators: {', '.join(request.indicators) or 'Not specified'}\n"
        f"Timeframe: {request.timeframe}\n"
        f"Risk Parameters: {_json.dumps(request.risk_parameters)}\n\n"
        "Provide a viability analysis with:\n"
        "1. Viability score (0-10)\n"
        "2. Estimated historical performance (win_rate, avg_return, max_drawdown, sharpe_ratio)\n"
        "3. Best market conditions\n"
        "4. Worst market conditions\n"
        "5. 3-5 specific recommendations to improve\n"
        "6. A similar well-known strategy name and similarity score\n\n"
        "Return as JSON with keys: analysis_id, viability_score, historical_performance, "
        "market_suitability (best_markets array, worst_markets array), recommendations array, "
        "similar_strategies array."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        try:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            result = _json.loads(raw_text)
        except Exception:
            result = {
                "viability_score": 5.0,
                "historical_performance": {"win_rate": 50, "avg_return": 0, "max_drawdown": -20, "sharpe_ratio": 0.5},
                "market_suitability": {"best_markets": ["trending"], "worst_markets": ["range-bound"]},
                "recommendations": [raw_text[:200]],
                "similar_strategies": [],
            }

        result["analysis_id"] = f"strat_{user_id[:8]}"
        return result

    except Exception as e:
        logger.error(f"Strategy analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Peer Comparison
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/peer-comparison")
async def compare_peers(
    request: PeerComparisonRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Compare multiple companies across key financial metrics."""
    if len(request.symbols) < 2:
        raise HTTPException(status_code=400, detail="At least 2 symbols required")
    if len(request.symbols) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 symbols allowed")

    try:
        import yfinance as yf

        companies = []
        for symbol in request.symbols:
            try:
                ticker = yf.Ticker(symbol.upper())
                info = ticker.info or {}

                companies.append({
                    "symbol": symbol.upper(),
                    "name": info.get("longName") or info.get("shortName", symbol.upper()),
                    "market_cap": info.get("marketCap"),
                    "pe_ratio": info.get("trailingPE"),
                    "revenue": info.get("totalRevenue"),
                    "profit_margin": info.get("profitMargins"),
                    "roe": info.get("returnOnEquity"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "beta": info.get("beta"),
                    "52_week_return": None,  # Would need historical data
                })
            except Exception as e:
                logger.warning(f"Could not fetch data for {symbol}: {e}")
                companies.append({"symbol": symbol.upper(), "name": symbol.upper(), "error": str(e)})

        def _safe_sort(lst, key, reverse=False):
            return sorted(
                [c for c in lst if c.get(key) is not None],
                key=lambda x: x[key],
                reverse=reverse,
            )

        rankings = {
            "by_market_cap": [c["symbol"] for c in _safe_sort(companies, "market_cap", reverse=True)],
            "by_revenue": [c["symbol"] for c in _safe_sort(companies, "revenue", reverse=True)],
            "by_pe_ratio": [c["symbol"] for c in _safe_sort(companies, "pe_ratio")],
            "by_profit_margin": [c["symbol"] for c in _safe_sort(companies, "profit_margin", reverse=True)],
            "by_roe": [c["symbol"] for c in _safe_sort(companies, "roe", reverse=True)],
        }

        return {
            "comparison": {
                "companies": companies,
                "rankings": rankings,
                "analysis": (
                    f"Comparing {len(companies)} companies: "
                    + ", ".join(c["symbol"] for c in companies)
                ),
            }
        }

    except Exception as e:
        logger.error(f"Peer comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Historical price data
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/company/{symbol}/history")
async def get_price_history(
    symbol: str,
    period: str = Query("1y", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max"),
    interval: str = Query("1d", description="Interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo"),
    user_id: str = Depends(get_current_user_id),
):
    """Get historical price data for a company."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return {"symbol": symbol.upper(), "period": period, "interval": interval, "data": []}

        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.isoformat(),
                "open": round(float(row["Open"]), 4) if row["Open"] else None,
                "high": round(float(row["High"]), 4) if row["High"] else None,
                "low": round(float(row["Low"]), 4) if row["Low"] else None,
                "close": round(float(row["Close"]), 4) if row["Close"] else None,
                "volume": int(row["Volume"]) if row["Volume"] else None,
            })

        return {
            "symbol": symbol.upper(),
            "period": period,
            "interval": interval,
            "data": data,
            "count": len(data),
        }

    except Exception as e:
        logger.error(f"Price history fetch failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not fetch price history: {str(e)}")
