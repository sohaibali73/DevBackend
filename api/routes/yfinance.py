"""YFinance data retrieval routes."""

from typing import Optional, Dict, Any, List, Union
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
import json

from api.dependencies import get_current_user_id, get_user_api_keys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yfinance", tags=["YFinance Data"])


def _convert_pandas_to_dict(obj: Any) -> Any:
    """Convert pandas objects to JSON-serializable dictionaries."""
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, pd.Series):
        return obj.to_dict()
    elif isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    elif isinstance(obj, (pd.Int64, pd.Int32, pd.Float64, pd.Float32)):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: _convert_pandas_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_pandas_to_dict(item) for item in obj]
    return obj


def _validate_ticker(ticker: str) -> bool:
    """Validate that a ticker symbol is reasonable."""
    if not ticker or len(ticker) < 1 or len(ticker) > 10:
        return False
    # Basic alphanumeric check (allows . for some tickers like BRK.B)
    return all(c.isalnum() or c == '.' for c in ticker)


@router.get("/{ticker}")
async def get_yfinance_data(
    ticker: str,
    include: Optional[str] = Query(None, description="Comma-separated list of data categories to include"),
    exclude: Optional[str] = Query(None, description="Comma-separated list of data categories to exclude"),
    history_period: Optional[str] = Query("1y", description="History period (1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max)"),
    history_interval: Optional[str] = Query("1d", description="History interval (1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo)"),
    options_date: Optional[str] = Query(None, description="Options expiration date (YYYY-MM-DD)"),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Retrieve comprehensive YFinance data for a given ticker symbol.
    
    Args:
        ticker: Stock ticker symbol (e.g., AAPL, MSFT, GOOGL)
        include: Comma-separated list of data categories to include
        exclude: Comma-separated list of data categories to exclude  
        history_period: Period for historical data
        history_interval: Interval for historical data
        options_date: Specific options expiration date
        user_id: Authenticated user ID
    
    Returns:
        Comprehensive financial data for the ticker
    """
    
    # Validate ticker
    if not _validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker symbol: {ticker}. Must be 1-10 characters and contain only letters, numbers, and periods."
        )
    
    # Define available data categories
    available_categories = {
        'info', 'history', 'actions', 'calendar', 'dividends', 'splits', 'capital_gains',
        'shares', 'fast_info', 'recommendations', 'recommendations_summary', 'upgrades_downgrades',
        'earnings', 'quarterly_earnings', 'income_stmt', 'quarterly_income_stmt', 'ttm_income_stmt',
        'balance_sheet', 'quarterly_balance_sheet', 'cash_flow', 'quarterly_cash_flow', 'ttm_cash_flow',
        'analyst_price_targets', 'earnings_estimate', 'revenue_estimate', 'earnings_history', 
        'eps_trend', 'eps_revisions', 'growth_estimates', 'sustainability', 'options', 'news',
        'earnings_dates', 'history_metadata', 'major_holders', 'institutional_holders', 'mutualfund_holders',
        'insider_purchases', 'insider_transactions', 'insider_roster_holders'
    }
    
    # Parse include/exclude parameters
    include_categories = set()
    exclude_categories = set()
    
    if include:
        include_categories = {cat.strip().lower() for cat in include.split(',')}
        if not include_categories.issubset(available_categories):
            invalid_cats = include_categories - available_categories
            raise HTTPException(
                status_code=400,
                detail=f"Invalid include categories: {', '.join(invalid_cats)}. Available: {', '.join(sorted(available_categories))}"
            )
    
    if exclude:
        exclude_categories = {cat.strip().lower() for cat in exclude.split(',')}
        if not exclude_categories.issubset(available_categories):
            invalid_cats = exclude_categories - available_categories
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exclude categories: {', '.join(invalid_cats)}. Available: {', '.join(sorted(available_categories))}"
            )
    
    # If include is specified, only get those categories
    # If exclude is specified, get all except those
    # If neither is specified, get all categories
    if include_categories:
        categories_to_fetch = include_categories
    elif exclude_categories:
        categories_to_fetch = available_categories - exclude_categories
    else:
        categories_to_fetch = available_categories
    
    # Validate history parameters
    valid_periods = {'1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'}
    valid_intervals = {'1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'}
    
    if history_period not in valid_periods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid history period: {history_period}. Valid periods: {', '.join(sorted(valid_periods))}"
        )
    
    if history_interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid history interval: {history_interval}. Valid intervals: {', '.join(sorted(valid_intervals))}"
        )
    
    try:
        # Create ticker object
        ticker_obj = yf.Ticker(ticker)
        
        # Initialize response
        response = {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {},
            "metadata": {
                "requested_categories": sorted(list(categories_to_fetch)),
                "history_period": history_period,
                "history_interval": history_interval,
                "options_date": options_date
            }
        }
        
        # Fetch data categories
        data_to_fetch = {}
        
        # Core data categories
        if 'info' in categories_to_fetch:
            data_to_fetch['info'] = lambda: ticker_obj.info
        
        if 'history' in categories_to_fetch:
            data_to_fetch['history'] = lambda: ticker_obj.history(
                period=history_period,
                interval=history_interval
            )
        
        if 'actions' in categories_to_fetch:
            data_to_fetch['actions'] = lambda: ticker_obj.actions
        
        if 'calendar' in categories_to_fetch:
            data_to_fetch['calendar'] = lambda: ticker_obj.calendar
        
        if 'dividends' in categories_to_fetch:
            data_to_fetch['dividends'] = lambda: ticker_obj.dividends
        
        if 'splits' in categories_to_fetch:
            data_to_fetch['splits'] = lambda: ticker_obj.splits
        
        if 'capital_gains' in categories_to_fetch:
            data_to_fetch['capital_gains'] = lambda: ticker_obj.capital_gains
        
        if 'shares' in categories_to_fetch:
            data_to_fetch['shares'] = lambda: ticker_obj.shares
        
        if 'fast_info' in categories_to_fetch:
            data_to_fetch['fast_info'] = lambda: {
                'currency': ticker_obj.fast_info.currency,
                'quote_type': ticker_obj.fast_info.quote_type,
                'exchange': ticker_obj.fast_info.exchange,
                'timezone': ticker_obj.fast_info.timezone,
                'shares': ticker_obj.fast_info.shares,
                'last_price': ticker_obj.fast_info.last_price,
                'previous_close': ticker_obj.fast_info.previous_close,
                'regular_market_previous_close': ticker_obj.fast_info.regular_market_previous_close,
                'open': ticker_obj.fast_info.open,
                'day_high': ticker_obj.fast_info.day_high,
                'day_low': ticker_obj.fast_info.day_low,
                'last_volume': ticker_obj.fast_info.last_volume,
                'fifty_day_average': ticker_obj.fast_info.fifty_day_average,
                'two_hundred_day_average': ticker_obj.fast_info.two_hundred_day_average,
                'ten_day_average_volume': ticker_obj.fast_info.ten_day_average_volume,
                'three_month_average_volume': ticker_obj.fast_info.three_month_average_volume,
                'year_high': ticker_obj.fast_info.year_high,
                'year_low': ticker_obj.fast_info.year_low,
                'year_change': ticker_obj.fast_info.year_change,
                'market_cap': ticker_obj.fast_info.market_cap,
            }
        
        if 'recommendations' in categories_to_fetch:
            data_to_fetch['recommendations'] = lambda: ticker_obj.recommendations
        
        if 'recommendations_summary' in categories_to_fetch:
            data_to_fetch['recommendations_summary'] = lambda: ticker_obj.recommendations_summary
        
        if 'upgrades_downgrades' in categories_to_fetch:
            data_to_fetch['upgrades_downgrades'] = lambda: ticker_obj.upgrades_downgrades
        
        if 'earnings' in categories_to_fetch:
            data_to_fetch['earnings'] = lambda: ticker_obj.earnings
        
        if 'quarterly_earnings' in categories_to_fetch:
            data_to_fetch['quarterly_earnings'] = lambda: ticker_obj.quarterly_earnings
        
        # Financial statements
        if 'income_stmt' in categories_to_fetch:
            data_to_fetch['income_stmt'] = lambda: ticker_obj.income_stmt
        
        if 'quarterly_income_stmt' in categories_to_fetch:
            data_to_fetch['quarterly_income_stmt'] = lambda: ticker_obj.quarterly_income_stmt
        
        if 'ttm_income_stmt' in categories_to_fetch:
            data_to_fetch['ttm_income_stmt'] = lambda: ticker_obj.ttm_income_stmt
        
        if 'balance_sheet' in categories_to_fetch:
            data_to_fetch['balance_sheet'] = lambda: ticker_obj.balance_sheet
        
        if 'quarterly_balance_sheet' in categories_to_fetch:
            data_to_fetch['quarterly_balance_sheet'] = lambda: ticker_obj.quarterly_balance_sheet
        
        if 'cash_flow' in categories_to_fetch:
            data_to_fetch['cash_flow'] = lambda: ticker_obj.cash_flow
        
        if 'quarterly_cash_flow' in categories_to_fetch:
            data_to_fetch['quarterly_cash_flow'] = lambda: ticker_obj.quarterly_cash_flow
        
        if 'ttm_cash_flow' in categories_to_fetch:
            data_to_fetch['ttm_cash_flow'] = lambda: ticker_obj.ttm_cash_flow
        
        # Analyst data
        if 'analyst_price_targets' in categories_to_fetch:
            data_to_fetch['analyst_price_targets'] = lambda: ticker_obj.analyst_price_targets
        
        if 'earnings_estimate' in categories_to_fetch:
            data_to_fetch['earnings_estimate'] = lambda: ticker_obj.earnings_estimate
        
        if 'revenue_estimate' in categories_to_fetch:
            data_to_fetch['revenue_estimate'] = lambda: ticker_obj.revenue_estimate
        
        if 'earnings_history' in categories_to_fetch:
            data_to_fetch['earnings_history'] = lambda: ticker_obj.earnings_history
        
        if 'eps_trend' in categories_to_fetch:
            data_to_fetch['eps_trend'] = lambda: ticker_obj.eps_trend
        
        if 'eps_revisions' in categories_to_fetch:
            data_to_fetch['eps_revisions'] = lambda: ticker_obj.eps_revisions
        
        if 'growth_estimates' in categories_to_fetch:
            data_to_fetch['growth_estimates'] = lambda: ticker_obj.growth_estimates
        
        if 'sustainability' in categories_to_fetch:
            data_to_fetch['sustainability'] = lambda: ticker_obj.sustainability
        
        # Options data
        if 'options' in categories_to_fetch:
            if options_date:
                data_to_fetch['options'] = lambda: ticker_obj.option_chain(options_date)
            else:
                data_to_fetch['options'] = lambda: ticker_obj.options
        
        if 'news' in categories_to_fetch:
            data_to_fetch['news'] = lambda: ticker_obj.news
        
        if 'earnings_dates' in categories_to_fetch:
            data_to_fetch['earnings_dates'] = lambda: ticker_obj.earnings_dates
        
        if 'history_metadata' in categories_to_fetch:
            data_to_fetch['history_metadata'] = lambda: ticker_obj.history_metadata
        
        # Holders data
        if 'major_holders' in categories_to_fetch:
            data_to_fetch['major_holders'] = lambda: ticker_obj.major_holders
        
        if 'institutional_holders' in categories_to_fetch:
            data_to_fetch['institutional_holders'] = lambda: ticker_obj.institutional_holders
        
        if 'mutualfund_holders' in categories_to_fetch:
            data_to_fetch['mutualfund_holders'] = lambda: ticker_obj.mutualfund_holders
        
        if 'insider_purchases' in categories_to_fetch:
            data_to_fetch['insider_purchases'] = lambda: ticker_obj.insider_purchases
        
        if 'insider_transactions' in categories_to_fetch:
            data_to_fetch['insider_transactions'] = lambda: ticker_obj.insider_transactions
        
        if 'insider_roster_holders' in categories_to_fetch:
            data_to_fetch['insider_roster_holders'] = lambda: ticker_obj.insider_roster_holders
        
        # Fetch data with error handling
        for category, fetch_func in data_to_fetch.items():
            try:
                logger.info(f"Fetching {category} data for {ticker}")
                raw_data = fetch_func()
                
                # Convert to JSON-serializable format
                if raw_data is not None:
                    if hasattr(raw_data, 'to_dict'):
                        # Handle pandas objects
                        if isinstance(raw_data, pd.DataFrame):
                            converted_data = raw_data.to_dict(orient='records')
                        else:
                            converted_data = raw_data.to_dict()
                    elif isinstance(raw_data, tuple) and hasattr(raw_data, '_asdict'):
                        # Handle namedtuples (like options)
                        converted_data = raw_data._asdict()
                    else:
                        converted_data = raw_data
                    
                    # Recursively convert any remaining pandas objects
                    response["data"][category] = _convert_pandas_to_dict(converted_data)
                    
            except Exception as e:
                logger.warning(f"Failed to fetch {category} data for {ticker}: {str(e)}")
                response["data"][category] = {
                    "error": str(e),
                    "message": f"Failed to retrieve {category} data"
                }
        
        # Add summary statistics
        response["summary"] = {
            "total_categories_requested": len(categories_to_fetch),
            "categories_successfully_fetched": len([k for k, v in response["data"].items() if "error" not in v]),
            "categories_with_errors": len([k for k, v in response["data"].items() if "error" in v]),
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Error fetching data for ticker {ticker}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve data for {ticker}: {str(e)}"
        )


@router.get("/{ticker}/summary")
async def get_yfinance_summary(
    ticker: str,
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Get a quick summary of key financial data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        user_id: Authenticated user ID
    
    Returns:
        Summary of key financial metrics
    """
    
    if not _validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker symbol: {ticker}"
        )
    
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Get basic info and fast info
        info = ticker_obj.info
        fast_info = ticker_obj.fast_info
        
        summary = {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "company": {
                "name": info.get('longName', ''),
                "symbol": info.get('symbol', ''),
                "currency": fast_info.currency,
                "exchange": fast_info.exchange,
                "sector": info.get('sector', ''),
                "industry": info.get('industry', ''),
                "website": info.get('website', ''),
            },
            "market_data": {
                "current_price": fast_info.last_price,
                "previous_close": fast_info.previous_close,
                "day_open": fast_info.open,
                "day_high": fast_info.day_high,
                "day_low": fast_info.day_low,
                "volume": fast_info.last_volume,
                "market_cap": fast_info.market_cap,
                "year_high": fast_info.year_high,
                "year_low": fast_info.year_low,
                "year_change": fast_info.year_change,
            },
            "key_metrics": {
                "pe_ratio": info.get('trailingPE', 0),
                "forward_pe": info.get('forwardPE', 0),
                "eps": info.get('trailingEps', 0),
                "forward_eps": info.get('forwardEps', 0),
                "dividend_yield": info.get('dividendYield', 0),
                "dividend_rate": info.get('dividendRate', 0),
                "payout_ratio": info.get('payoutRatio', 0),
                "beta": info.get('beta', 0),
                "shares_outstanding": info.get('sharesOutstanding', 0),
            },
            "financials": {
                "revenue": info.get('totalRevenue', 0),
                "gross_profit": info.get('grossProfits', 0),
                "net_income": info.get('netIncomeToCommon', 0),
                "operating_cashflow": info.get('operatingCashflow', 0),
                "free_cashflow": info.get('freeCashflow', 0),
            }
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error fetching summary for ticker {ticker}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve summary for {ticker}: {str(e)}"
        )


@router.get("/{ticker}/history")
async def get_yfinance_history(
    ticker: str,
    period: Optional[str] = Query("1y", description="History period"),
    interval: Optional[str] = Query("1d", description="History interval"),
    user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Get historical price data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        period: History period
        interval: History interval
        user_id: Authenticated user ID
    
    Returns:
        Historical price data
    """
    
    if not _validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker symbol: {ticker}"
        )
    
    valid_periods = {'1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'}
    valid_intervals = {'1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'}
    
    if period not in valid_periods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period: {period}"
        )
    
    if interval not in valid_intervals:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interval: {interval}"
        )
    
    try:
        ticker_obj = yf.Ticker(ticker)
        history = ticker_obj.history(period=period, interval=interval)
        
        # Convert to JSON-serializable format
        history_data = history.to_dict(orient='records')
        
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "timestamp": datetime.utcnow().isoformat(),
            "data": history_data,
            "summary": {
                "total_records": len(history_data),
                "start_date": history.index[0].isoformat() if len(history_data) > 0 else None,
                "end_date": history.index[-1].isoformat() if len(history_data) > 0 else None,
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching history for ticker {ticker}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve history for {ticker}: {str(e)}"
        )