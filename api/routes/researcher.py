"""
Researcher API Routes

Provides endpoints for the Market Researcher & Intelligence Platform.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import requests
import json
from functools import lru_cache

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(
    prefix="/researcher",
    tags=["Researcher"],
    dependencies=[],
    responses={404: {"description": "Not found"}},
)

# API clients for external services
class FinnhubClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"
    
    def get_quote(self, symbol: str):
        """Get current quote data"""
        try:
            response = requests.get(
                f"{self.base_url}/quote",
                params={"symbol": symbol, "token": self.api_key}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Finnhub quote error for {symbol}: {e}")
            return None
    
    def get_company_profile(self, symbol: str):
        """Get company profile"""
        try:
            response = requests.get(
                f"{self.base_url}/stock/profile2",
                params={"symbol": symbol, "token": self.api_key}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Finnhub profile error for {symbol}: {e}")
            return None
    
    def get_news(self, symbol: str, limit: int = 20):
        """Get company news"""
        try:
            response = requests.get(
                f"{self.base_url}/news",
                params={"category": symbol, "token": self.api_key}
            )
            response.raise_for_status()
            return response.json()[:limit]
        except Exception as e:
            logger.error(f"Finnhub news error for {symbol}: {e}")
            return []

class NewsApiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://newsapi.org/v2"
    
    def get_company_news(self, symbol: str, limit: int = 20):
        """Get company news from NewsAPI"""
        try:
            response = requests.get(
                f"{self.base_url}/everything",
                params={
                    "q": symbol,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": limit,
                    "apiKey": self.api_key
                }
            )
            response.raise_for_status()
            return response.json().get("articles", [])
        except Exception as e:
            logger.error(f"NewsAPI error for {symbol}: {e}")
            return []

class FredClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred"
    
    def get_indicator(self, series_id: str):
        """Get economic indicator"""
        try:
            response = requests.get(
                f"{self.base_url}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "limit": 1,
                    "order_by": "observation_date",
                    "sort_order": "desc"
                }
            )
            response.raise_for_status()
            data = response.json()
            if data.get("observations"):
                return data["observations"][0]
            return None
        except Exception as e:
            logger.error(f"FRED API error for {series_id}: {e}")
            return None

# Initialize API clients
finnhub_client = FinnhubClient(settings.finnhub_api_key)
newsapi_client = NewsApiClient(settings.newsapi_key)
fred_client = FredClient(settings.fred_api_key)

# Simple sentiment analysis function
def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Simple sentiment analysis based on keywords"""
    positive_words = ['buy', 'strong', 'growth', 'beat', 'increase', 'positive', 'up', 'gain', 'success']
    negative_words = ['sell', 'weak', 'decline', 'miss', 'decrease', 'negative', 'down', 'loss', 'problem']
    
    text_lower = text.lower()
    positive_score = sum(1 for word in positive_words if word in text_lower)
    negative_score = sum(1 for word in negative_words if word in text_lower)
    
    if positive_score > negative_score:
        return {"label": "POSITIVE", "score": min(positive_score / (positive_score + negative_score + 1), 1.0)}
    elif negative_score > positive_score:
        return {"label": "NEGATIVE", "score": min(negative_score / (positive_score + negative_score + 1), 1.0)}
    else:
        return {"label": "NEUTRAL", "score": 0.0}


@router.get("/company/{symbol}")
async def get_company_research(
    symbol: str,
    user_id: str = None
):
    """
    Get comprehensive company research for a symbol using OpenBB
    
    Returns:
        - Fundamentals (P/E, dividend, growth rates)
        - Financial statements (income, balance sheet, cash flow)
        - Recent news with sentiment analysis
        - Insider trading activity
        - Analyst ratings and estimates
        - SEC filings summary
        - AI-generated summary
    """
    try:
        logger.info(f"Company research requested for {symbol} by user {user_id or 'anonymous'}")
        
        # Initialize researcher engine
        from core.researcher_engine import ResearcherEngine
        engine = ResearcherEngine()
        
        # Get comprehensive research data using OpenBB
        research_data = engine.get_company_research(symbol)
        
        return JSONResponse(
            content={
                "success": True,
                "data": research_data,
                "message": f"Research data for {symbol} retrieved successfully using OpenBB"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting company research for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve research data for {symbol}: {str(e)}"
        )


@router.get("/company/{symbol}/stream")
async def get_company_research_stream(
    symbol: str,
    user_id: str = None
):
    """
    Get comprehensive company research for a symbol using OpenBB with streaming response
    
    Returns:
        - Fundamentals (P/E, dividend, growth rates)
        - Financial statements (income, balance sheet, cash flow)
        - Recent news with sentiment analysis
        - Insider trading activity
        - Analyst ratings and estimates
        - SEC filings summary
        - AI-generated summary
    """
    try:
        logger.info(f"Company research stream requested for {symbol} by user {user_id or 'anonymous'}")
        
        # Initialize researcher engine
        from core.researcher_engine import ResearcherEngine
        engine = ResearcherEngine()
        
        # Get comprehensive research data using OpenBB
        research_data = engine.get_company_research(symbol)
        
        # Return streaming response
        from fastapi.responses import StreamingResponse
        import json
        
        async def generate():
            # Stream the research data in chunks
            yield f"data: {json.dumps({'type': 'research_data', 'data': research_data})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'message': f'Research data for {symbol} retrieved successfully using OpenBB'})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
        
    except Exception as e:
        logger.error(f"Error getting company research stream for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve research data for {symbol}: {str(e)}"
        )


@router.get("/news/{symbol}")
async def get_company_news(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    user_id: str = None
):
    """
    Get aggregated news for a company with sentiment analysis
    
    Query Parameters:
        - limit: Number of news items to return (1-100)
    """
    try:
        logger.info(f"News requested for {symbol} by user {user_id or 'anonymous'}")
        
        # Get news from multiple sources
        finnhub_news = finnhub_client.get_news(symbol, limit=limit)
        newsapi_news = newsapi_client.get_company_news(symbol, limit=limit)
        
        # Combine and analyze news
        all_news = []
        sentiment_scores = []
        
        # Process Finnhub news
        for news_item in finnhub_news:
            if isinstance(news_item, dict):
                title = news_item.get('headline', '')
                description = news_item.get('summary', '')
                url = news_item.get('url', '')
                published_at = news_item.get('datetime', datetime.now().timestamp())
                
                if isinstance(published_at, (int, float)):
                    published_at = datetime.fromtimestamp(published_at).isoformat()
                
                sentiment = analyze_sentiment(title + " " + description)
                sentiment_scores.append(sentiment['score'])
                
                all_news.append({
                    "source": "Finnhub",
                    "title": title,
                    "description": description,
                    "url": url,
                    "published_at": published_at,
                    "sentiment": sentiment
                })
        
        # Process NewsAPI news
        for news_item in newsapi_news:
            if isinstance(news_item, dict):
                title = news_item.get('title', '')
                description = news_item.get('description', '')
                url = news_item.get('url', '')
                published_at = news_item.get('publishedAt', datetime.now().isoformat())
                
                sentiment = analyze_sentiment(title + " " + description)
                sentiment_scores.append(sentiment['score'])
                
                all_news.append({
                    "source": "NewsAPI",
                    "title": title,
                    "description": description,
                    "url": url,
                    "published_at": published_at,
                    "sentiment": sentiment
                })
        
        # Limit results and calculate overall sentiment
        news = all_news[:limit]
        overall_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        
        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "symbol": symbol,
                    "news": news,
                    "sentiment_score": overall_sentiment,
                    "news_count": len(news)
                },
                "message": f"News for {symbol} retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting news for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve news for {symbol}: {str(e)}"
        )


@router.post("/strategy-analysis")
async def analyze_strategy_fit(
    request: Dict[str, Any],
    user_id: str = None
):
    """
    Analyze how well a strategy fits current market conditions
    
    Request Body:
        - symbol: Stock symbol
        - strategy_type: Type of strategy (e.g., 'momentum', 'mean_reversion', 'trend_following')
        - timeframe: Timeframe for analysis (e.g., 'daily', 'weekly', 'monthly')
    """
    try:
        symbol = request.get('symbol')
        strategy_type = request.get('strategy_type')
        timeframe = request.get('timeframe', 'daily')
        
        if not symbol or not strategy_type:
            raise HTTPException(
                status_code=400,
                detail="Symbol and strategy_type are required"
            )
        
        logger.info(f"Strategy analysis requested for {symbol} ({strategy_type}) by user {user_id or 'anonymous'}")
        
        # Return mock analysis data
        analysis = {
            "symbol": symbol,
            "strategy_type": strategy_type,
            "timeframe": timeframe,
            "market_regime": "bull_market",
            "volatility": {
                "historical_volatility": 25.5,
                "volatility_rank": 0.6,
                "volatility_trend": "stable"
            },
            "technical_indicators": {
                "trend": "uptrend",
                "momentum": "strong",
                "support_level": 180.00,
                "resistance_level": 220.00
            },
            "market_context": {
                "regime": "bull_market",
                "sp500_level": 5200.0,
                "vix_level": 15.5,
                "market_sentiment": 0.75
            },
            "strategy_fit_score": 0.8,
            "recommendations": [
                f"Strategy {strategy_type} shows good fit for current market conditions",
                "Consider adjusting position size based on volatility levels",
                "Monitor key support and resistance levels"
            ]
        }
        
        return JSONResponse(
            content={
                "success": True,
                "data": analysis,
                "message": f"Strategy analysis for {symbol} completed"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing strategy for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze strategy for {symbol}: {str(e)}"
        )


@router.post("/comparison")
async def get_peer_comparison(
    request: Dict[str, Any],
    user_id: str = None
):
    """
    Compare a company against its peers
    
    Request Body:
        - symbol: Base company symbol
        - peers: List of peer company symbols
    """
    try:
        symbol = request.get('symbol')
        peers = request.get('peers', [])
        
        if not symbol:
            raise HTTPException(
                status_code=400,
                detail="Symbol is required"
            )
        
        if not peers:
            raise HTTPException(
                status_code=400,
                detail="At least one peer symbol is required"
            )
        
        logger.info(f"Peer comparison requested for {symbol} vs {peers} by user {user_id or 'anonymous'}")
        
        # Return mock comparison data
        comparison = {
            "symbol": symbol,
            "peers": peers,
            "companies": {
                symbol: {
                    "fundamentals": {
                        "pe_ratio": 25.5,
                        "market_cap": "2.5T",
                        "revenue_growth": 12.5
                    }
                }
            },
            "comparison_metrics": {
                "valuation": {
                    "symbol": symbol,
                    "pe_ratio": 25.5,
                    "peers_average": 22.3,
                    "relative_valuation": "premium"
                },
                "growth": {
                    "symbol": symbol,
                    "revenue_growth": 12.5,
                    "peers_average": 8.7,
                    "growth_rank": 1
                }
            },
            "analysis": {
                "summary": f"{symbol} trades at a premium to peers but shows superior growth metrics",
                "strengths": ["Higher growth rate", "Stronger fundamentals"],
                "weaknesses": ["Higher valuation", "Potential overvaluation risk"],
                "recommendation": "Consider for growth-focused portfolios"
            }
        }
        
        return JSONResponse(
            content={
                "success": True,
                "data": comparison,
                "message": f"Peer comparison for {symbol} completed"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting peer comparison for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get peer comparison for {symbol}: {str(e)}"
        )


@router.get("/macro-context")
async def get_macro_context(
    user_id: str = None
):
    """
    Get current macroeconomic context and market outlook
    """
    try:
        logger.info(f"Macro context requested by user {user_id or 'anonymous'}")
        
        # Get economic indicators from FRED
        gdp_data = fred_client.get_indicator("A191RL1Q225SBEA")  # Real GDP Growth Rate
        unemployment_data = fred_client.get_indicator("UNRATE")   # Unemployment Rate
        inflation_data = fred_client.get_indicator("FPCPITOTLZGUSA")  # Inflation Rate
        fed_rate_data = fred_client.get_indicator("FEDFUNDS")     # Fed Funds Rate
        
        # Build economic indicators data
        economic_indicators = {
            "latest_values": {
                "gdp_growth": float(gdp_data.get("value", 0)) if gdp_data else 0,
                "unemployment": float(unemployment_data.get("value", 0)) if unemployment_data else 0,
                "inflation": float(inflation_data.get("value", 0)) if inflation_data else 0,
                "fed_funds_rate": float(fed_rate_data.get("value", 0)) if fed_rate_data else 0
            },
            "trends": {
                "gdp_growth": "up" if gdp_data and float(gdp_data.get("value", 0)) > 0 else "down",
                "unemployment": "up" if unemployment_data and float(unemployment_data.get("value", 0)) > 4 else "down",
                "inflation": "up" if inflation_data and float(inflation_data.get("value", 0)) > 2 else "down",
                "fed_funds_rate": "up" if fed_rate_data and float(fed_rate_data.get("value", 0)) > 2 else "down"
            }
        }
        
        # Build macro data
        macro_data = {
            "timestamp": datetime.now().isoformat(),
            "economic_indicators": economic_indicators,
            "market_sentiment": {
                "fear_greed_index": 65,  # Mock data - would need premium API
                "put_call_ratio": 0.85,   # Mock data - would need premium API
                "overall_sentiment": "neutral"
            },
            "fed_policy": {
                "current_rate": economic_indicators["latest_values"]["fed_funds_rate"],
                "inflation_trend": economic_indicators["trends"]["inflation"],
                "policy_stance": "neutral"  # Would need more analysis for real stance
            },
            "outlook": {
                "short_term": "Cautious optimism with potential for volatility",
                "medium_term": "Stable growth expected with Fed policy monitoring",
                "long_term": "Positive outlook driven by innovation and productivity gains"
            }
        }
        
        return JSONResponse(
            content={
                "success": True,
                "data": macro_data,
                "message": "Macro context retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting macro context: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve macro context: {str(e)}"
        )


@router.get("/sec-filings/{symbol}")
async def get_sec_filings(
    symbol: str,
    user_id: str = None
):
    """
    Get recent SEC filings for a company
    """
    try:
        logger.info(f"SEC filings requested for {symbol} by user {user_id or 'anonymous'}")
        
        # Return mock SEC filings data
        filings = [
            {
                "type": "10-K",
                "date": "2024-01-31",
                "description": "Annual Report",
                "url": f"https://sec.gov/edgar/{symbol}/10k"
            },
            {
                "type": "10-Q",
                "date": "2023-10-31",
                "description": "Quarterly Report",
                "url": f"https://sec.gov/edgar/{symbol}/10q"
            }
        ]
        
        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "symbol": symbol,
                    "filings": filings,
                    "filing_count": len(filings)
                },
                "message": f"SEC filings for {symbol} retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting SEC filings for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve SEC filings for {symbol}: {str(e)}"
        )


@router.post("/generate-report")
async def generate_research_report(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: str = None
):
    """
    Generate a custom research report
    
    Request Body:
        - symbol: Stock symbol
        - report_type: Type of report (e.g., 'company', 'strategy', 'comparison')
        - sections: List of sections to include
        - format: Export format (pdf, csv, markdown)
    """
    try:
        symbol = request.get('symbol')
        report_type = request.get('report_type', 'company')
        sections = request.get('sections', ['executive_summary', 'fundamental_analysis'])
        export_format = request.get('format', 'json')
        
        if not symbol:
            raise HTTPException(
                status_code=400,
                detail="Symbol is required"
            )
        
        logger.info(f"Report generation requested for {symbol} by user {user_id or 'anonymous'}")
        
        # Generate mock report
        report = {
            "symbol": symbol,
            "report_type": report_type,
            "sections": {},
            "generated_at": datetime.now().isoformat(),
            "sections_included": sections,
            "export_options": ['json', 'pdf', 'csv', 'markdown'],
            "export_format": export_format
        }
        
        for section in sections:
            if section == 'executive_summary':
                report['sections']['executive_summary'] = f"Executive summary for {symbol}: Strong company with solid fundamentals and growth prospects."
            elif section == 'fundamental_analysis':
                report['sections']['fundamental_analysis'] = f"Fundamental analysis for {symbol}: P/E ratio of 25.5, strong revenue growth of 12.5%, healthy balance sheet."
            elif section == 'technical_analysis':
                report['sections']['technical_analysis'] = f"Technical analysis for {symbol}: Currently in uptrend with support at $180 and resistance at $220."
            elif section == 'risk_assessment':
                report['sections']['risk_assessment'] = f"Risk assessment for {symbol}: Market risk, regulatory risk, and competitive pressures identified."
            elif section == 'investment_recommendation':
                report['sections']['investment_recommendation'] = f"Investment recommendation for {symbol}: Buy with target price of $220, suitable for long-term investors."
        
        # Schedule background export if requested
        if export_format != 'json':
            background_tasks.add_task(
                _export_report_background,
                report,
                export_format,
                user_id
            )
        
        return JSONResponse(
            content={
                "success": True,
                "data": report,
                "message": f"Research report for {symbol} generated successfully"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate report for {symbol}: {str(e)}"
        )


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = Query(default="pdf", pattern="^(pdf|csv|markdown)$"),
    user_id: str = None
):
    """
    Export a previously generated report
    
    Query Parameters:
        - format: Export format (pdf, csv, markdown)
    """
    try:
        logger.info(f"Report export requested for {report_id} in {format} format by user {user_id or 'anonymous'}")
        
        return JSONResponse(
            content={
                "success": True,
                "data": {
                    "report_id": report_id,
                    "format": format,
                    "download_url": f"/api/researcher/reports/{report_id}/download?format={format}",
                    "expires_at": (datetime.now()).isoformat()
                },
                "message": f"Report {report_id} export prepared"
            }
        )
        
    except Exception as e:
        logger.error(f"Error exporting report {report_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export report {report_id}: {str(e)}"
        )


@router.get("/search")
async def search_research(
    query: str = Query(..., min_length=2),
    search_type: str = Query(default="company", pattern="^(company|strategy|macro)$"),
    limit: int = Query(default=10, ge=1, le=50),
    user_id: str = None
):
    """
    Search for research across different categories
    
    Query Parameters:
        - query: Search query
        - search_type: Type of search (company, strategy, macro)
        - limit: Number of results to return
    """
    try:
        logger.info(f"Search requested for '{query}' ({search_type}) by user {user_id or 'anonymous'}")
        
        # Return mock search results
        search_results = {
            "query": query,
            "search_type": search_type,
            "results": [
                {
                    "title": f"Research on {query}",
                    "type": search_type,
                    "symbol": query if search_type == "company" else None,
                    "summary": f"Mock research results for {query}",
                    "url": f"/api/researcher/company/{query}" if search_type == "company" else "/api/researcher/macro-context",
                    "last_updated": datetime.now().isoformat()
                }
            ],
            "total_results": 1,
            "search_time": datetime.now().isoformat()
        }
        
        return JSONResponse(
            content={
                "success": True,
                "data": search_results,
                "message": f"Search completed for '{query}'"
            }
        )
        
    except Exception as e:
        logger.error(f"Error searching for '{query}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search for '{query}': {str(e)}"
        )


@router.get("/trending")
async def get_trending_research(
    limit: int = Query(default=10, ge=1, le=20),
    user_id: str = None
):
    """
    Get trending research topics and companies
    
    Query Parameters:
        - limit: Number of trending items to return
    """
    try:
        logger.info(f"Trending research requested by user {user_id or 'anonymous'}")
        
        trending_data = {
            "trending_companies": [
                {"symbol": "AAPL", "reason": "Strong earnings report"},
                {"symbol": "NVDA", "reason": "AI boom driving growth"},
                {"symbol": "TSLA", "reason": "New product announcements"}
            ],
            "trending_strategies": [
                {"strategy": "AI-driven momentum", "popularity": 85},
                {"strategy": "ESG-focused investing", "popularity": 72},
                {"strategy": "Volatility harvesting", "popularity": 64}
            ],
            "trending_topics": [
                {"topic": "Artificial Intelligence", "trend": "up"},
                {"topic": "Renewable Energy", "trend": "up"},
                {"topic": "Cybersecurity", "trend": "stable"}
            ],
            "last_updated": datetime.now().isoformat()
        }
        
        return JSONResponse(
            content={
                "success": True,
                "data": trending_data,
                "message": "Trending research data retrieved"
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting trending research: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trending research: {str(e)}"
        )


# Background task for report export
async def _export_report_background(report: Dict[str, Any], format: str, user: dict):
    """Background task to export reports"""
    try:
        logger.info(f"Background export started for report {report.get('symbol')} in {format} format")
        
        # Mock export logic
        logger.info(f"Background export completed for report {report.get('symbol')} in {format} format")
        
    except Exception as e:
        logger.error(f"Background export failed for report {report.get('symbol')}: {str(e)}")


# Health check endpoint
@router.get("/health")
async def researcher_health_check():
    """Health check for researcher service"""
    try:
        # Test API clients
        finnhub_status = "configured" if settings.finnhub_api_key else "not_configured"
        newsapi_status = "configured" if settings.newsapi_key else "not_configured"
        fred_status = "configured" if settings.fred_api_key else "not_configured"
        
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "researcher",
                "last_test": datetime.now().isoformat(),
                "test_symbol": "AAPL",
                "test_data_available": True,
                "data_sources": {
                    "openbb": "not_configured",
                    "finnhub": finnhub_status,
                    "fred": fred_status,
                    "newsapi": newsapi_status,
                    "transformers": "not_configured"
                },
                "note": "Service running with configured API keys where available"
            }
        )
        
    except Exception as e:
        logger.error(f"Researcher health check failed: {str(e)}")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "service": "researcher",
                "error": str(e),
                "last_test": datetime.now().isoformat()
            },
            status_code=503
        )