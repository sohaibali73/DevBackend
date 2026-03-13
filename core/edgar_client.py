"""
EDGAR API Client — SEC EDGAR Data Integration
==============================================

Provides structured access to the SEC's EDGAR (Electronic Data Gathering,
Analysis, and Retrieval) system.

Capabilities
────────────
• Company search by name or ticker  →  get_company_by_ticker / search_companies
• CIK (Central Index Key) lookup    →  used internally by all endpoints
• Filing list (10-K, 10-Q, 8-K, …) →  get_company_filings
• Filing document download          →  get_filing_document
• XBRL financial facts (structured) →  get_company_facts
• Single XBRL concept               →  get_company_concept
• Full-text filing search           →  search_filings_fulltext
• Bulk ticker→CIK mapping           →  get_all_tickers (cached)

All public endpoints share a module-level HTTP client (urllib) and a
lightweight in-memory TTL cache so repeated calls within the same
process avoid redundant network round-trips.

EDGAR rate limit: 10 req/s  — we stay well within that with serial calls.

NOTE: The SEC requires a descriptive User-Agent:
      "Application-Name Contact-Email"
      Configure via EDGAR_USER_AGENT env var or the default is used.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── User-Agent (required by SEC) ─────────────────────────────────────────────
_DEFAULT_UA = "PotomacAnalystWorkbench contact@potomac.ai"
_USER_AGENT = os.getenv("EDGAR_USER_AGENT", _DEFAULT_UA)

# ── Base URLs ─────────────────────────────────────────────────────────────────
_DATA_BASE   = "https://data.sec.gov"
_EFTS_BASE   = "https://efts.sec.gov"
_SEC_BASE    = "https://www.sec.gov"
_ARCHIVES    = "https://www.sec.gov/Archives/edgar/data"

# ── Cache ─────────────────────────────────────────────────────────────────────
_EDGAR_CACHE: Dict[str, Tuple[Any, float]] = {}
_CACHE_TTL_SHORT  =  300   # 5 min  — frequently changing data (recent filings)
_CACHE_TTL_MEDIUM = 3600   # 1 hour — company metadata
_CACHE_TTL_LONG   = 86400  # 1 day  — static reference data (ticker→CIK map)


def _get_cached(key: str, ttl: float) -> Optional[Any]:
    """Return cached value if present and not expired, otherwise None."""
    entry = _EDGAR_CACHE.get(key)
    if entry is None:
        return None
    data, ts = entry
    if time.time() - ts < ttl:
        logger.debug("EDGAR cache hit: %s", key)
        return data
    return None


def _set_cached(key: str, data: Any) -> None:
    _EDGAR_CACHE[key] = (data, time.time())


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = 15) -> Any:
    """
    Perform a GET request to the SEC and parse the JSON response.

    The SEC requires a descriptive User-Agent; requests without it are
    actively blocked.  All other errors are propagated to the caller.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept":     "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str, timeout: int = 30) -> str:
    """Fetch a raw text/html resource from the SEC archives."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept":     "text/html,application/xhtml+xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _pad_cik(cik: int | str) -> str:
    """Zero-pad a CIK to 10 digits as required by data.sec.gov endpoints."""
    return str(int(cik)).zfill(10)


# =============================================================================
# TICKER ↔ CIK MAPPING
# =============================================================================

def get_all_tickers() -> Dict[str, Any]:
    """
    Download and cache the SEC's master ticker→CIK reference file.

    Returns a dict keyed by ticker (uppercase) with values:
        {"cik": int, "name": str, "ticker": str}

    Cached for 24 hours — the file only changes when new companies list.
    """
    cached = _get_cached("all_tickers", _CACHE_TTL_LONG)
    if cached is not None:
        return cached

    try:
        url  = f"{_SEC_BASE}/files/company_tickers.json"
        data = _http_get(url)
        # The file is a dict of str(index) → {cik_str, ticker, title}
        tickers: Dict[str, Any] = {}
        for _idx, company in data.items():
            tkr = company.get("ticker", "").upper()
            if tkr:
                tickers[tkr] = {
                    "cik":    int(company.get("cik_str", 0)),
                    "name":   company.get("title", ""),
                    "ticker": tkr,
                }
        _set_cached("all_tickers", tickers)
        logger.info("EDGAR: loaded %d ticker mappings", len(tickers))
        return tickers
    except Exception as e:
        logger.error("EDGAR: failed to load ticker map: %s", e)
        return {}


def get_all_tickers_with_exchange() -> List[Dict[str, Any]]:
    """
    Return the enriched ticker list that also includes exchange information.

    Each entry: {"cik": int, "name": str, "ticker": str, "exchange": str}
    Cached for 24 hours.
    """
    cached = _get_cached("all_tickers_exchange", _CACHE_TTL_LONG)
    if cached is not None:
        return cached

    try:
        url  = f"{_SEC_BASE}/files/company_tickers_exchange.json"
        data = _http_get(url)
        fields   = data.get("fields", [])
        rows     = data.get("data", [])
        result   = [dict(zip(fields, row)) for row in rows]
        _set_cached("all_tickers_exchange", result)
        return result
    except Exception as e:
        logger.error("EDGAR: failed to load exchange ticker map: %s", e)
        return []


def get_company_by_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a ticker symbol to its SEC CIK and company name.

    Returns None if the ticker is not found.
    """
    tickers = get_all_tickers()
    return tickers.get(ticker.upper())


def cik_from_ticker(ticker: str) -> Optional[int]:
    """Convenience: return just the CIK integer for a ticker, or None."""
    company = get_company_by_ticker(ticker)
    return company["cik"] if company else None


# =============================================================================
# COMPANY SEARCH
# =============================================================================

def search_companies(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for companies by name (case-insensitive substring match against the
    full ticker→CIK map).

    Returns up to `limit` matches, each with keys: cik, name, ticker.
    """
    tickers = get_all_tickers()
    query_l = query.lower()
    results = [
        v for v in tickers.values()
        if query_l in v["name"].lower() or query_l in v["ticker"].lower()
    ]
    return sorted(results, key=lambda x: x["name"])[:limit]


# =============================================================================
# COMPANY SUBMISSIONS / FILINGS
# =============================================================================

def get_company_submissions(cik: int | str) -> Dict[str, Any]:
    """
    Fetch the full submissions object for a company from data.sec.gov.

    The returned dict contains:
      - name, sic, tickers, exchanges, category, …
      - filings.recent: recent filings index (form, date, accessionNumber, …)
      - filings.files: pointers to older filing pages when the company is large

    Cached for 5 minutes.
    """
    cik_padded = _pad_cik(cik)
    cache_key  = f"submissions_{cik_padded}"
    cached     = _get_cached(cache_key, _CACHE_TTL_SHORT)
    if cached is not None:
        return cached

    url  = f"{_DATA_BASE}/submissions/CIK{cik_padded}.json"
    data = _http_get(url)
    _set_cached(cache_key, data)
    return data


def get_company_info(cik: int | str) -> Dict[str, Any]:
    """
    Return a cleaned summary of company metadata from its submissions object.
    """
    raw = get_company_submissions(cik)
    return {
        "cik":              int(cik),
        "cik_padded":       _pad_cik(cik),
        "name":             raw.get("name", ""),
        "sic":              raw.get("sic", ""),
        "sic_description":  raw.get("sicDescription", ""),
        "tickers":          raw.get("tickers", []),
        "exchanges":        raw.get("exchanges", []),
        "ein":              raw.get("ein", ""),
        "category":         raw.get("category", ""),
        "state_of_inc":     raw.get("stateOfIncorporation", ""),
        "fiscal_year_end":  raw.get("fiscalYearEnd", ""),
        "entity_type":      raw.get("entityType", ""),
        "business_address": raw.get("addresses", {}).get("business", {}),
        "mailing_address":  raw.get("addresses", {}).get("mailing", {}),
        "phone":            raw.get("phone", ""),
        "website":          raw.get("website", ""),
    }


def get_company_filings(
    cik:        int | str,
    form_type:  Optional[str] = None,
    limit:      int  = 20,
    offset:     int  = 0,
) -> Dict[str, Any]:
    """
    Return a filtered, paginated list of filings for a company.

    Parameters
    ----------
    cik       : SEC Central Index Key
    form_type : Optional filter, e.g. "10-K", "10-Q", "8-K", "DEF 14A"
    limit     : Max filings to return (max 200)
    offset    : Starting index for pagination

    Returns
    -------
    {
        "cik": …, "company_name": …, "total": …,
        "filings": [{"form": …, "date": …, "accession_number": …,
                     "document_url": …, "size": …, "is_inline_xbrl": …}, …]
    }
    """
    limit = min(limit, 200)
    raw   = get_company_submissions(cik)

    recent = raw.get("filings", {}).get("recent", {})
    forms   = recent.get("form",            [])
    dates   = recent.get("filingDate",      [])
    accnos  = recent.get("accessionNumber", [])
    primary = recent.get("primaryDocument", [])
    sizes   = recent.get("size",            [])
    ixbrl   = recent.get("isInlineXBRL",    [])
    reports = recent.get("reportDate",      [])

    filings: List[Dict[str, Any]] = []
    for i, form in enumerate(forms):
        if form_type and form.upper() != form_type.upper():
            continue
        acc_raw = accnos[i] if i < len(accnos) else ""
        acc_fmt = acc_raw.replace("-", "")
        cik_pad = _pad_cik(cik)
        doc     = primary[i] if i < len(primary) else ""
        doc_url = (
            f"{_ARCHIVES}/{int(cik)}/{acc_fmt}/{doc}"
            if doc else
            f"{_SEC_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={cik_pad}"
            f"&type={urllib.parse.quote(form)}&dateb=&owner=include&count=1"
        )
        filings.append({
            "form":              form,
            "filing_date":       dates[i]   if i < len(dates)   else "",
            "report_date":       reports[i] if i < len(reports) else "",
            "accession_number":  acc_raw,
            "accession_clean":   acc_fmt,
            "document_url":      doc_url,
            "primary_document":  doc,
            "size_bytes":        sizes[i] if i < len(sizes) else 0,
            "is_inline_xbrl":    bool(ixbrl[i]) if i < len(ixbrl) else False,
            "viewer_url":        (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={cik_pad}&type={urllib.parse.quote(form)}&dateb=&owner=include&count=1"
            ),
        })

    total    = len(filings)
    paginated = filings[offset: offset + limit]

    return {
        "cik":          int(cik),
        "company_name": raw.get("name", ""),
        "form_filter":  form_type,
        "total":        total,
        "offset":       offset,
        "limit":        limit,
        "filings":      paginated,
    }


def get_filing_index(cik: int | str, accession_number: str) -> Dict[str, Any]:
    """
    Fetch the filing index page for a specific accession number.

    Returns a dict with the list of documents in the filing, including
    their type, description, and direct download URLs.
    """
    acc_clean = accession_number.replace("-", "")
    cik_int   = int(cik)
    url       = f"{_ARCHIVES}/{cik_int}/{acc_clean}/{accession_number}-index.json"

    cache_key = f"filing_index_{acc_clean}"
    cached    = _get_cached(cache_key, _CACHE_TTL_MEDIUM)
    if cached is not None:
        return cached

    try:
        data = _http_get(url)
        # Enrich each document with its full URL
        for doc in data.get("documents", []):
            doc["url"] = f"{_ARCHIVES}/{cik_int}/{acc_clean}/{doc.get('name', '')}"
        _set_cached(cache_key, data)
        return data
    except Exception as e:
        # Fallback: return minimal info
        return {
            "accession_number": accession_number,
            "error":            str(e),
            "filing_url":       f"{_ARCHIVES}/{cik_int}/{acc_clean}/",
        }


def get_filing_document(
    cik: int | str,
    accession_number: str,
    document_name: Optional[str] = None,
    max_chars: int = 50_000,
) -> Dict[str, Any]:
    """
    Download the text of a specific filing document.

    If `document_name` is None the primary document from the index is used.
    Content is truncated to `max_chars` to stay within API response limits.
    """
    acc_clean = accession_number.replace("-", "")
    cik_int   = int(cik)

    if document_name is None:
        # Look up the primary document from the index
        idx  = get_filing_index(cik, accession_number)
        docs = idx.get("documents", [])
        if docs:
            document_name = docs[0].get("name", "")

    if not document_name:
        return {
            "success": False,
            "error":   "No document name provided and primary document not found",
        }

    url = f"{_ARCHIVES}/{cik_int}/{acc_clean}/{document_name}"
    try:
        content = _http_get_text(url)
        truncated = len(content) > max_chars
        return {
            "success":       True,
            "cik":           cik_int,
            "accession":     accession_number,
            "document_name": document_name,
            "url":           url,
            "content":       content[:max_chars],
            "total_chars":   len(content),
            "truncated":     truncated,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


# =============================================================================
# XBRL FINANCIAL DATA
# =============================================================================

def get_company_facts(cik: int | str) -> Dict[str, Any]:
    """
    Fetch all XBRL financial facts for a company.

    The returned structure is large (~MB for mature public companies).
    It is cached for 5 minutes and the caller should filter to the
    specific concepts they need.

    Top-level keys: cik, entityName, facts
      facts.us-gaap  → dict of GAAP concept names → units+values
      facts.dei      → document & entity information concepts
    """
    cik_padded = _pad_cik(cik)
    cache_key  = f"facts_{cik_padded}"
    cached     = _get_cached(cache_key, _CACHE_TTL_SHORT)
    if cached is not None:
        return cached

    url  = f"{_DATA_BASE}/api/xbrl/companyfacts/CIK{cik_padded}.json"
    data = _http_get(url)
    _set_cached(cache_key, data)
    return data


def get_company_concept(
    cik:      int | str,
    concept:  str,
    taxonomy: str = "us-gaap",
) -> Dict[str, Any]:
    """
    Fetch time-series values for a single XBRL concept (e.g. "EarningsPerShare").

    Parameters
    ----------
    cik      : SEC Central Index Key
    concept  : XBRL concept name (e.g. "EarningsPerShare", "Revenues",
               "NetIncomeLoss", "Assets", "CommonStockSharesOutstanding")
    taxonomy : "us-gaap" (default) or "dei" or "ifrs-full"

    Returns a dict with the entity name, units, and a sorted list of
    period-value pairs ready for charting or analysis.
    """
    cik_padded = _pad_cik(cik)
    cache_key  = f"concept_{cik_padded}_{taxonomy}_{concept}"
    cached     = _get_cached(cache_key, _CACHE_TTL_SHORT)
    if cached is not None:
        return cached

    url  = f"{_DATA_BASE}/api/xbrl/companyconcept/CIK{cik_padded}/{taxonomy}/{concept}.json"
    data = _http_get(url)

    # Flatten the units structure into a sorted list for easier consumption
    units_map = data.get("units", {})
    flat_series: List[Dict[str, Any]] = []
    for unit_label, periods in units_map.items():
        for period in periods:
            flat_series.append({
                "unit":          unit_label,
                "start":         period.get("start"),
                "end":           period.get("end"),
                "val":           period.get("val"),
                "accn":          period.get("accn"),
                "fy":            period.get("fy"),
                "fp":            period.get("fp"),
                "form":          period.get("form"),
                "filed":         period.get("filed"),
                "frame":         period.get("frame"),
            })

    flat_series.sort(key=lambda x: x.get("end") or "", reverse=True)

    result = {
        "cik":         int(cik),
        "entity_name": data.get("entityName", ""),
        "taxonomy":    taxonomy,
        "concept":     concept,
        "label":       data.get("label", concept),
        "description": data.get("description", ""),
        "units":       list(units_map.keys()),
        "series":      flat_series,
        "latest":      flat_series[0] if flat_series else None,
    }
    _set_cached(cache_key, result)
    return result


def get_key_financials(cik: int | str) -> Dict[str, Any]:
    """
    Return a curated snapshot of key financial metrics for a company using
    XBRL data.  Fetches the common concepts used in fundamental analysis.

    Concepts fetched (us-gaap unless noted):
      Revenues / RevenueFromContractWithCustomerExcludingAssessedTax
      NetIncomeLoss
      EarningsPerShareBasic
      Assets
      Liabilities
      StockholdersEquity
      CommonStockSharesOutstanding
      OperatingIncomeLoss
      CashAndCashEquivalentsAtCarryingValue
      LongTermDebt
    """
    _CONCEPTS = [
        ("Revenues",                                           "us-gaap"),
        ("RevenueFromContractWithCustomerExcludingAssessedTax","us-gaap"),
        ("NetIncomeLoss",                                      "us-gaap"),
        ("EarningsPerShareBasic",                              "us-gaap"),
        ("Assets",                                             "us-gaap"),
        ("Liabilities",                                        "us-gaap"),
        ("StockholdersEquity",                                 "us-gaap"),
        ("CommonStockSharesOutstanding",                       "us-gaap"),
        ("OperatingIncomeLoss",                                "us-gaap"),
        ("CashAndCashEquivalentsAtCarryingValue",              "us-gaap"),
        ("LongTermDebt",                                       "us-gaap"),
    ]

    financials: Dict[str, Any] = {}
    for concept, taxonomy in _CONCEPTS:
        try:
            data   = get_company_concept(cik, concept, taxonomy)
            latest = data.get("latest")
            if latest:
                financials[concept] = {
                    "value":    latest.get("val"),
                    "unit":     latest.get("unit"),
                    "end":      latest.get("end"),
                    "form":     latest.get("form"),
                    "filed":    latest.get("filed"),
                    "label":    data.get("label", concept),
                }
        except Exception:
            pass   # Concept not available for this company

    company_info = {}
    try:
        raw          = get_company_submissions(cik)
        company_info = {
            "name":    raw.get("name", ""),
            "tickers": raw.get("tickers", []),
            "sic":     raw.get("sic", ""),
        }
    except Exception:
        pass

    return {
        "cik":          int(cik),
        "company":      company_info,
        "financials":   financials,
        "concepts_found": len(financials),
    }


# =============================================================================
# FULL-TEXT SEARCH
# =============================================================================

def search_filings_fulltext(
    query:      str,
    form_type:  Optional[str] = None,
    date_from:  Optional[str] = None,
    date_to:    Optional[str] = None,
    limit:      int = 10,
) -> Dict[str, Any]:
    """
    Search EDGAR full-text filing index via the EFTS API.

    Parameters
    ----------
    query     : Free-text search query (supports quotes, AND/OR/NOT operators)
    form_type : Optional form filter, e.g. "10-K", "8-K", "DEF 14A"
    date_from : Optional start date  "YYYY-MM-DD"
    date_to   : Optional end date    "YYYY-MM-DD"
    limit     : Max results (max 100)

    Returns
    -------
    {"total": int, "hits": [{entity_name, form, filed, accession_number, …}, …]}
    """
    limit = min(limit, 100)
    params: Dict[str, str] = {
        "q":    query,
        "from": "0",
        "size": str(limit),
    }
    if form_type:
        params["forms"] = form_type
    if date_from or date_to:
        params["dateRange"] = "custom"
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to

    url = f"{_EFTS_BASE}/LATEST/search-index?" + urllib.parse.urlencode(params)

    cache_key = f"fts_{urllib.parse.urlencode(params)}"
    cached    = _get_cached(cache_key, _CACHE_TTL_SHORT)
    if cached is not None:
        return cached

    try:
        data  = _http_get(url)
        hits  = data.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        raw_hits = hits.get("hits", [])

        results = []
        for h in raw_hits:
            src = h.get("_source", {})
            results.append({
                "entity_name":      src.get("entity_name", ""),
                "file_date":        src.get("file_date", ""),
                "form_type":        src.get("form_type", ""),
                "accession_number": src.get("accession_no", ""),
                "period_of_report": src.get("period_of_report", ""),
                "cik":              src.get("entity_id", ""),
                "description":      src.get("file_description", ""),
                "document_url":     (
                    f"{_ARCHIVES}/{int(src.get('entity_id', 0))}/"
                    f"{src.get('accession_no', '').replace('-', '')}/"
                    f"{src.get('file_name', '')}"
                    if src.get("entity_id") and src.get("accession_no")
                    else ""
                ),
            })

        result = {
            "success":   True,
            "query":     query,
            "form_type": form_type,
            "date_from": date_from,
            "date_to":   date_to,
            "total":     total,
            "returned":  len(results),
            "hits":      results,
        }
        _set_cached(cache_key, result)
        return result

    except Exception as e:
        return {
            "success": False,
            "query":   query,
            "error":   str(e),
        }


# =============================================================================
# CONVENIENCE / COMPOSITE FUNCTIONS
# =============================================================================

def get_latest_filings_by_form(
    ticker:    str,
    form_type: str,
    limit:     int = 5,
) -> Dict[str, Any]:
    """
    One-shot helper: resolve ticker → CIK → return latest N filings of a form.

    Example: get_latest_filings_by_form("AAPL", "10-K", 3)
    """
    company = get_company_by_ticker(ticker)
    if not company:
        return {"success": False, "error": f"Ticker '{ticker}' not found in EDGAR"}

    cik = company["cik"]
    filings = get_company_filings(cik, form_type=form_type, limit=limit)
    filings["ticker"]  = ticker.upper()
    filings["success"] = True
    return filings


def get_security_id(identifier: str) -> Dict[str, Any]:
    """
    Resolve an identifier (ticker OR company name) to its EDGAR security IDs.

    Returns: {ticker, cik, cik_padded, name, sic, exchanges, tickers}
    """
    # 1. Try exact ticker match first
    company = get_company_by_ticker(identifier)
    if company:
        try:
            info = get_company_info(company["cik"])
            return {
                "success":   True,
                "matched_as": "ticker",
                **info,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # 2. Fall back to name search
    results = search_companies(identifier, limit=3)
    if results:
        top = results[0]
        try:
            info = get_company_info(top["cik"])
            return {
                "success":    True,
                "matched_as": "name_search",
                "all_matches": results,
                **info,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "candidates": results}

    return {
        "success": False,
        "error":   f"No matching company found for '{identifier}'",
    }


def get_insider_transactions(cik: int | str, limit: int = 20) -> Dict[str, Any]:
    """
    Return recent Form 4 insider transaction filings for a company.
    Convenience wrapper over get_company_filings with form_type="4".
    """
    return get_company_filings(cik, form_type="4", limit=limit)


def get_material_events(cik: int | str, limit: int = 20) -> Dict[str, Any]:
    """
    Return recent 8-K (material event) filings for a company.
    """
    return get_company_filings(cik, form_type="8-K", limit=limit)


def get_proxy_statements(cik: int | str, limit: int = 5) -> Dict[str, Any]:
    """
    Return DEF 14A proxy statement filings for a company.
    """
    return get_company_filings(cik, form_type="DEF 14A", limit=limit)
