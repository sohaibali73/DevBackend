"""
EDGAR API Routes — SEC EDGAR Data Integration
==============================================

REST endpoints that expose the core/edgar_client.py capabilities
through the same auth / dependency pattern used by the rest of the API.

All endpoints require a valid JWT (Supabase Auth) via get_current_user_id.
No EDGAR-specific API key is needed — the SEC provides free public access.

Route prefix : /edgar
Tags         : EDGAR

Endpoints
─────────
GET  /edgar/security/{identifier}           → CIK + company metadata by ticker or name
GET  /edgar/search                          → Company name/ticker search
GET  /edgar/company/{cik}                   → Full company metadata by CIK
GET  /edgar/company/{cik}/filings           → Paginated filing list (optional form filter)
GET  /edgar/company/{cik}/filings/{accn}    → Documents in a specific filing
GET  /edgar/company/{cik}/financials        → Key XBRL financials snapshot
GET  /edgar/company/{cik}/concept           → Single XBRL concept time-series
GET  /edgar/ticker/{ticker}/filings         → Latest filings by ticker (shortcut)
GET  /edgar/ticker/{ticker}/annual          → Latest 10-K filings
GET  /edgar/ticker/{ticker}/quarterly       → Latest 10-Q filings
GET  /edgar/ticker/{ticker}/events          → Latest 8-K material events
GET  /edgar/ticker/{ticker}/insider         → Latest Form 4 insider transactions
GET  /edgar/ticker/{ticker}/proxy           → Latest DEF 14A proxy statements
POST /edgar/search/fulltext                 → Full-text filing search (EFTS)
GET  /edgar/tickers                         → Complete ticker → CIK reference (cached 24h)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/edgar", tags=["EDGAR"])

# ── Lazy-load the client so import errors don't kill the router ───────────────
def _client():
    try:
        import core.edgar_client as ec
        return ec
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EDGAR client unavailable: {e}")


# =============================================================================
# PYDANTIC REQUEST MODELS
# =============================================================================

class FullTextSearchRequest(BaseModel):
    """Request body for full-text filing search."""
    query:     str              = Field(..., description="Search query (supports AND/OR/NOT and quoted phrases)")
    form_type: Optional[str]    = Field(None, description='Optional form filter, e.g. "10-K", "8-K", "DEF 14A"')
    date_from: Optional[str]    = Field(None, description="Start date filter YYYY-MM-DD")
    date_to:   Optional[str]    = Field(None, description="End date filter YYYY-MM-DD")
    limit:     int              = Field(10,  ge=1, le=100, description="Max results (1-100)")


# =============================================================================
# SECURITY ID / COMPANY LOOKUP
# =============================================================================

@router.get(
    "/security/{identifier}",
    summary="Resolve ticker or company name → EDGAR security IDs",
    response_description="CIK, padded CIK, company name, SIC, exchanges, tickers",
)
async def get_security_id(
    identifier: str,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Resolve a stock ticker symbol OR company name to its SEC EDGAR identifiers.

    Returns the CIK (Central Index Key), padded CIK, company name, SIC code,
    industry description, listed tickers, and exchange(s).

    This is the primary entry-point when you know a ticker (e.g. "AAPL") or
    a company name (e.g. "Apple") and need the EDGAR CIK to call other endpoints.
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_security_id(identifier)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "Not found"))
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("EDGAR security lookup failed for %s: %s", identifier, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/search",
    summary="Search companies by name or ticker substring",
)
async def search_companies(
    q:     str = Query(..., description="Company name or ticker substring to search"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Search the full SEC company→CIK reference file for matching companies.
    Matches against both company name and ticker symbol (case-insensitive).
    """
    t0 = time.time()
    ec = _client()
    try:
        results = ec.search_companies(q, limit=limit)
        return {
            "query":          q,
            "results":        results,
            "count":          len(results),
            "fetch_time_ms":  round((time.time() - t0) * 1000, 2),
        }
    except Exception as e:
        logger.error("EDGAR company search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# COMPANY METADATA
# =============================================================================

@router.get(
    "/company/{cik}",
    summary="Get company metadata by CIK",
)
async def get_company_info(
    cik: int,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Fetch full company metadata from EDGAR for a known CIK.

    Includes: name, SIC code & description, tickers, exchanges, EIN,
    fiscal year end, state of incorporation, business & mailing address.
    """
    t0 = time.time()
    ec = _client()
    try:
        info = ec.get_company_info(cik)
        info["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return info
    except Exception as e:
        logger.error("EDGAR company info failed for CIK %s: %s", cik, e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FILINGS
# =============================================================================

@router.get(
    "/company/{cik}/filings",
    summary="List filings for a company (optionally filtered by form type)",
)
async def get_company_filings(
    cik:       int,
    form_type: Optional[str] = Query(None, description='Form type filter, e.g. "10-K", "10-Q", "8-K"'),
    limit:     int           = Query(20, ge=1, le=200, description="Max filings to return"),
    offset:    int           = Query(0,  ge=0,         description="Pagination offset"),
    user_id:   str           = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Return a paginated list of SEC filings for a company, identified by its CIK.

    Each filing record includes:
    - `form`           – Filing form type (10-K, 10-Q, 8-K, DEF 14A, 4, …)
    - `filing_date`    – Date the filing was submitted to EDGAR
    - `report_date`    – Period of the report (fiscal period end)
    - `accession_number` – EDGAR accession number (use to fetch filing documents)
    - `document_url`   – Direct URL to the primary document
    - `size_bytes`     – File size
    - `is_inline_xbrl` – Whether the filing uses Inline XBRL
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_company_filings(cik, form_type=form_type, limit=limit, offset=offset)
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except Exception as e:
        logger.error("EDGAR filings failed for CIK %s: %s", cik, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/company/{cik}/filings/{accession_number}",
    summary="Get documents in a specific filing",
)
async def get_filing_index(
    cik:              int,
    accession_number: str,
    user_id:          str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Fetch the filing index for a specific accession number.

    Returns the list of all documents included in the filing with their
    types (e.g. primary document, exhibit 31.1, exhibit 32, XBRL data),
    descriptions, and direct download URLs.

    The `accession_number` should be in the format returned by `/filings`
    (e.g. `0000320193-23-000106` — with or without dashes, both accepted).
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_filing_index(cik, accession_number)
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except Exception as e:
        logger.error("EDGAR filing index failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FINANCIAL DATA (XBRL)
# =============================================================================

@router.get(
    "/company/{cik}/financials",
    summary="Key XBRL financial snapshot (revenues, income, EPS, assets, …)",
)
async def get_key_financials(
    cik:     int,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Fetch a curated snapshot of key financial metrics from XBRL data.

    Retrieves the most recent value for the following US-GAAP concepts:
    - Revenues / RevenueFromContractWithCustomerExcludingAssessedTax
    - NetIncomeLoss
    - EarningsPerShareBasic
    - Assets, Liabilities, StockholdersEquity
    - OperatingIncomeLoss
    - CashAndCashEquivalentsAtCarryingValue
    - LongTermDebt
    - CommonStockSharesOutstanding

    Note: Some concepts may not be reported by all companies. Only available
    concepts are included in the response.
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_key_financials(cik)
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except Exception as e:
        logger.error("EDGAR financials failed for CIK %s: %s", cik, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/company/{cik}/concept",
    summary="Fetch time-series for a single XBRL financial concept",
)
async def get_company_concept(
    cik:      int,
    concept:  str = Query(..., description='XBRL concept name, e.g. "Revenues", "NetIncomeLoss", "EarningsPerShareBasic"'),
    taxonomy: str = Query("us-gaap", description='Taxonomy: "us-gaap" (default), "dei", or "ifrs-full"'),
    limit:    int = Query(20, ge=1, le=200, description="Max time-series entries to return"),
    user_id:  str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Return the full time-series of a single XBRL financial concept for a company.

    The series is sorted newest-first and includes fiscal year, fiscal period,
    the associated filing accession number, and the date the value was filed.

    Common concept names:
    - `Revenues` or `RevenueFromContractWithCustomerExcludingAssessedTax`
    - `NetIncomeLoss`
    - `EarningsPerShareBasic` / `EarningsPerShareDiluted`
    - `Assets`, `Liabilities`, `StockholdersEquity`
    - `OperatingIncomeLoss`
    - `CashAndCashEquivalentsAtCarryingValue`
    - `LongTermDebt`
    - `CommonStockSharesOutstanding`
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_company_concept(cik, concept, taxonomy)
        # Apply pagination to the series
        result["series"] = result.get("series", [])[:limit]
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except Exception as e:
        logger.error("EDGAR concept failed for CIK %s / %s: %s", cik, concept, e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TICKER SHORTCUTS
# =============================================================================

@router.get(
    "/ticker/{ticker}/filings",
    summary="List recent filings for a ticker (all form types)",
)
async def get_ticker_filings(
    ticker:    str,
    form_type: Optional[str] = Query(None, description="Optional form type filter"),
    limit:     int           = Query(20, ge=1, le=200),
    user_id:   str           = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Resolve ticker → CIK and return the company's filing list."""
    t0 = time.time()
    ec = _client()
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in EDGAR")
        result = ec.get_company_filings(company["cik"], form_type=form_type, limit=limit)
        result["ticker"]       = ticker.upper()
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/annual",
    summary="Latest 10-K (annual report) filings for a ticker",
)
async def get_annual_filings(
    ticker:  str,
    limit:   int = Query(5, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Return the most recent 10-K annual report filings for a ticker."""
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_latest_filings_by_form(ticker, "10-K", limit=limit)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/quarterly",
    summary="Latest 10-Q (quarterly report) filings for a ticker",
)
async def get_quarterly_filings(
    ticker:  str,
    limit:   int = Query(8, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Return the most recent 10-Q quarterly report filings for a ticker."""
    t0 = time.time()
    ec = _client()
    try:
        result = ec.get_latest_filings_by_form(ticker, "10-Q", limit=limit)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error"))
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/events",
    summary="Latest 8-K (material event) filings for a ticker",
)
async def get_material_events(
    ticker:  str,
    limit:   int = Query(10, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Return the most recent 8-K material event / current report filings."""
    t0 = time.time()
    ec = _client()
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in EDGAR")
        result = ec.get_material_events(company["cik"], limit=limit)
        result["ticker"]        = ticker.upper()
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/insider",
    summary="Latest Form 4 insider transaction filings for a ticker",
)
async def get_insider_transactions(
    ticker:  str,
    limit:   int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Return the most recent Form 4 (insider transaction) filings."""
    t0 = time.time()
    ec = _client()
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in EDGAR")
        result = ec.get_insider_transactions(company["cik"], limit=limit)
        result["ticker"]        = ticker.upper()
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/proxy",
    summary="Latest DEF 14A proxy statement filings for a ticker",
)
async def get_proxy_statements(
    ticker:  str,
    limit:   int = Query(5, ge=1, le=20),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Return the most recent DEF 14A proxy statement filings."""
    t0 = time.time()
    ec = _client()
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in EDGAR")
        result = ec.get_proxy_statements(company["cik"], limit=limit)
        result["ticker"]        = ticker.upper()
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/ticker/{ticker}/financials",
    summary="Key XBRL financial snapshot by ticker (shortcut)",
)
async def get_ticker_financials(
    ticker:  str,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """Resolve ticker to CIK then return key XBRL financials."""
    t0 = time.time()
    ec = _client()
    try:
        company = ec.get_company_by_ticker(ticker.upper())
        if not company:
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in EDGAR")
        result = ec.get_key_financials(company["cik"])
        result["ticker"]        = ticker.upper()
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# FULL-TEXT SEARCH
# =============================================================================

@router.post(
    "/search/fulltext",
    summary="Full-text search across all EDGAR filings (EFTS)",
)
async def search_filings_fulltext(
    body:    FullTextSearchRequest,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Search the full text of all EDGAR filings using the SEC's EFTS engine.

    Supports:
    - Exact phrases:       `"climate risk"`
    - Boolean operators:   `AI AND revenue AND guidance`
    - Exclusion:           `bitcoin NOT mining`
    - Form type filter:    `form_type = "10-K"`
    - Date range filter:   `date_from = "2024-01-01"`, `date_to = "2024-12-31"`

    Returns matching filing metadata with direct document URLs.
    """
    t0 = time.time()
    ec = _client()
    try:
        result = ec.search_filings_fulltext(
            query=body.query,
            form_type=body.form_type,
            date_from=body.date_from,
            date_to=body.date_to,
            limit=body.limit,
        )
        if not result.get("success"):
            raise HTTPException(status_code=502, detail=result.get("error", "EDGAR search failed"))
        result["fetch_time_ms"] = round((time.time() - t0) * 1000, 2)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("EDGAR full-text search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REFERENCE DATA
# =============================================================================

@router.get(
    "/tickers",
    summary="Complete ticker → CIK mapping (all ~10k SEC-listed companies)",
)
async def get_all_tickers(
    exchange: Optional[str] = Query(None, description="Filter by exchange (e.g. Nasdaq, NYSE)"),
    limit:    int           = Query(100, ge=1, le=5000, description="Max entries to return"),
    offset:   int           = Query(0,   ge=0,          description="Pagination offset"),
    user_id:  str           = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Return the SEC's complete company-tickers mapping, optionally enriched
    with exchange information.

    The response is a paginated list of {cik, ticker, name, exchange?} records.
    Results are cached for 24 hours; the first call may take ~1–2 seconds.
    """
    t0 = time.time()
    ec = _client()
    try:
        if exchange:
            # Use the richer exchange-aware file
            all_companies = ec.get_all_tickers_with_exchange()
            if exchange.lower() not in ("all", ""):
                all_companies = [
                    c for c in all_companies
                    if (c.get("exchange") or "").lower() == exchange.lower()
                ]
        else:
            tickers_dict  = ec.get_all_tickers()
            all_companies = list(tickers_dict.values())

        total     = len(all_companies)
        paginated = all_companies[offset: offset + limit]

        return {
            "total":          total,
            "offset":         offset,
            "limit":          limit,
            "exchange_filter": exchange,
            "companies":      paginated,
            "fetch_time_ms":  round((time.time() - t0) * 1000, 2),
        }
    except Exception as e:
        logger.error("EDGAR tickers list failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
