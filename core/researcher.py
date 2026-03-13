"""
Strategy Researcher - Web Search, EDGAR SEC, and Yahoo Finance Integration
"""

import os
import logging
from typing import Optional, Dict, List, Any, Union, Generator
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class StrategyResearcher:
    """Research strategies using web search, SEC EDGAR, and Yahoo Finance."""
    
    def __init__(self, tavily_api_key: Optional[str] = None, claude_engine=None):
        self.tavily_api_key = tavily_api_key or os.environ.get("TAVILY_API_KEY")
        self._tavily_client = None
        self.claude_engine = claude_engine
    
    @property
    def tavily_client(self):
        """Lazy load Tavily client."""
        if self._tavily_client is None and self.tavily_api_key:
            try:
                from tavily import TavilyClient
                self._tavily_client = TavilyClient(api_key=self.tavily_api_key)
            except ImportError:
                logger.warning("Tavily not installed. Run: pip install tavily-python")
        return self._tavily_client

    def research_strategy(self, query: str, stream: bool = False) -> Union[str, Generator[str, None, None]]:
        """
        Performs comprehensive research on a trading strategy.
        Combines web search with financial data sources.
        """
        if stream and self.claude_engine:
            return self._research_strategy_streaming(query)
        else:
            return self._research_strategy_sync(query)

    def _research_strategy_sync(self, query: str) -> str:
        """Synchronous version of strategy research"""
        results = []
        
        # 1. Web Search via Tavily
        web_results = self.search_web(query)
        if web_results:
            results.append("## Web Research Results\n" + web_results)
        
        # 2. Try to identify if it's a fund and get SEC data
        fund_data = self.search_sec_edgar(query)
        if fund_data:
            results.append("## SEC EDGAR Filings\n" + fund_data)
        
        # 3. Get market data context if relevant
        market_context = self.get_market_context(query)
        if market_context:
            results.append("## Market Data Context\n" + market_context)
        
        return "\n\n".join(results) if results else "No research results found."

    def _research_strategy_streaming(self, query: str) -> Generator[str, None, None]:
        """Streaming version of strategy research"""
        try:
            # 1. Web Search via Tavily
            web_results = self.search_web(query)
            if web_results:
                yield "## Web Research Results\n" + web_results + "\n\n"
        
            # 2. Try to identify if it's a fund and get SEC data
            fund_data = self.search_sec_edgar(query)
            if fund_data:
                yield "## SEC EDGAR Filings\n" + fund_data + "\n\n"
        
            # 3. Get market data context if relevant
            market_context = self.get_market_context(query)
            if market_context:
                yield "## Market Data Context\n" + market_context + "\n\n"
                
            if not web_results and not fund_data and not market_context:
                yield "No research results found."
                
        except Exception as e:
            yield f"Research error: {str(e)}"

    def search_web(self, query: str, search_type: str = "strategy") -> str:
        """
        Search the web using Tavily for strategy-related information.
        """
        if not self.tavily_client:
            return ""
        
        try:
            # Build search query based on type
            if search_type == "strategy":
                search_query = f"{query} trading strategy rules indicators methodology"
            elif search_type == "fund":
                search_query = f"{query} fund prospectus strategy allocation methodology"
            elif search_type == "general":
                search_query = query
            else:
                search_query = query
            
            logger.info(f"Tavily search: {search_query}")
            search_result = self.tavily_client.search(
                query=search_query, 
                search_depth="advanced",
                max_results=8
            )
            
            # Format results
            context = ""
            for result in search_result.get('results', []):
                context += f"**Source:** {result.get('url', 'Unknown')}\n"
                context += f"{result.get('content', '')}\n\n"
            
            return context
            
        except Exception as e:
            logger.error(f"Tavily search error: {e}")
            return f"Web search error: {str(e)}"

    def search_sec_edgar(self, query: str) -> str:
        """
        Search SEC EDGAR for fund filings, prospectuses, and strategy documents.
        Uses the SEC EDGAR full-text search API.
        """
        try:
            import requests
            
            # SEC EDGAR full-text search API
            # https://efts.sec.gov/LATEST/search-index
            
            # First, try to find the fund/company
            search_url = "https://efts.sec.gov/LATEST/search-index"
            params = {
                "q": query,
                "dateRange": "custom",
                "startdt": "2020-01-01",
                "enddt": "2026-12-31",
                "forms": "N-1A,485BPOS,N-CSR,N-CSRS,N-Q,497",  # Fund-related forms
                "from": 0,
                "size": 10
            }
            
            headers = {
                "User-Agent": "Potomac Fund Management analyst@potomacfund.com",
                "Accept": "application/json"
            }
            
            response = requests.get(
                f"https://efts.sec.gov/LATEST/search-index?q={query}&forms=N-1A,485BPOS,N-CSR&from=0&size=5",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])
                
                if not hits:
                    return ""
                
                results = []
                for hit in hits[:5]:
                    source = hit.get("_source", {})
                    results.append(
                        f"**Filing:** {source.get('form', 'Unknown')} - {source.get('display_names', ['Unknown'])[0]}\n"
                        f"**Filed:** {source.get('file_date', 'Unknown')}\n"
                        f"**CIK:** {source.get('ciks', ['Unknown'])[0]}\n"
                        f"**Link:** https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={source.get('ciks', [''])[0]}&type=&dateb=&owner=include&count=40\n"
                    )
                
                return "\n".join(results)
            
            return ""
            
        except Exception as e:
            logger.error(f"SEC EDGAR search error: {e}")
            return ""

    def get_fund_holdings(self, cik: str) -> str:
        """
        Get fund holdings from SEC N-PORT or 13F filings.
        """
        try:
            import requests
            
            headers = {
                "User-Agent": "Potomac Fund Management analyst@potomacfund.com",
                "Accept": "application/json"
            }
            
            # Get recent filings for this CIK
            url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                name = data.get("name", "Unknown")
                recent = data.get("filings", {}).get("recent", {})
                
                forms = recent.get("form", [])
                dates = recent.get("filingDate", [])
                
                # Find relevant forms
                relevant_filings = []
                for i, form in enumerate(forms[:20]):
                    if form in ["N-PORT", "N-CSR", "N-CSRS", "13F-HR", "N-Q"]:
                        relevant_filings.append(f"- {form} filed on {dates[i]}")
                
                if relevant_filings:
                    return f"**{name}**\nRecent Filings:\n" + "\n".join(relevant_filings[:5])
            
            return ""
            
        except Exception as e:
            logger.error(f"Fund holdings error: {e}")
            return ""

    def get_yahoo_finance_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get financial data from Yahoo Finance.
        """
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return {
                "name": info.get("longName", symbol),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap", "N/A"),
                "pe_ratio": info.get("trailingPE", "N/A"),
                "dividend_yield": info.get("dividendYield", "N/A"),
                "52_week_high": info.get("fiftyTwoWeekHigh", "N/A"),
                "52_week_low": info.get("fiftyTwoWeekLow", "N/A"),
                "avg_volume": info.get("averageVolume", "N/A"),
                "description": info.get("longBusinessSummary", "")[:500] if info.get("longBusinessSummary") else ""
            }
            
        except ImportError:
            logger.warning("yfinance not installed. Run: pip install yfinance")
            return {}
        except Exception as e:
            logger.error(f"Yahoo Finance error: {e}")
            return {}

    def get_market_context(self, query: str) -> str:
        """
        Get relevant market context including index data and volatility.
        """
        try:
            import yfinance as yf
            
            # Key market indicators
            symbols = {
                "SPY": "S&P 500 ETF",
                "QQQ": "NASDAQ 100 ETF", 
                "VIX": "Volatility Index",
                "TLT": "20+ Year Treasury ETF",
                "GLD": "Gold ETF"
            }
            
            context_parts = []
            for symbol, name in symbols.items():
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period="1mo")
                    if not hist.empty:
                        current = hist['Close'].iloc[-1]
                        prev = hist['Close'].iloc[0]
                        change = ((current - prev) / prev) * 100
                        context_parts.append(f"- {name} ({symbol}): ${current:.2f} ({change:+.2f}% 1M)")
                except:
                    pass
            
            if context_parts:
                return "Current Market Context:\n" + "\n".join(context_parts)
            return ""
            
        except ImportError:
            return ""
        except Exception as e:
            logger.error(f"Market context error: {e}")
            return ""

    def research_fund(self, fund_name: str, stream: bool = False) -> Union[str, Generator[str, None, None]]:
        """
        Comprehensive research on a specific fund.
        """
        if stream and self.claude_engine:
            return self._research_fund_streaming(fund_name)
        else:
            return self._research_fund_sync(fund_name)

    def _research_fund_sync(self, fund_name: str) -> str:
        """Synchronous version of fund research"""
        results = []
        
        # 1. Web search for fund strategy
        web_results = self.search_web(fund_name, search_type="fund")
        if web_results:
            results.append("## Fund Strategy Research\n" + web_results)
        
        # 2. SEC EDGAR filings
        sec_results = self.search_sec_edgar(fund_name)
        if sec_results:
            results.append("## SEC Filings\n" + sec_results)
        
        # 3. Search for prospectus details
        prospectus_search = self.search_web(f"{fund_name} prospectus investment strategy methodology", search_type="general")
        if prospectus_search:
            results.append("## Prospectus Information\n" + prospectus_search)
        
        return "\n\n".join(results) if results else f"No detailed information found for {fund_name}"

    def _research_fund_streaming(self, fund_name: str) -> Generator[str, None, None]:
        """Streaming version of fund research"""
        try:
            # 1. Web search for fund strategy
            web_results = self.search_web(fund_name, search_type="fund")
            if web_results:
                yield "## Fund Strategy Research\n" + web_results + "\n\n"
        
            # 2. SEC EDGAR filings
            sec_results = self.search_sec_edgar(fund_name)
            if sec_results:
                yield "## SEC Filings\n" + sec_results + "\n\n"
        
            # 3. Search for prospectus details
            prospectus_search = self.search_web(f"{fund_name} prospectus investment strategy methodology", search_type="general")
            if prospectus_search:
                yield "## Prospectus Information\n" + prospectus_search + "\n\n"
                
            if not web_results and not sec_results and not prospectus_search:
                yield f"No detailed information found for {fund_name}"
                
        except Exception as e:
            yield f"Research error: {str(e)}"

    def search_trading_rules(self, strategy_name: str) -> str:
        """
        Search specifically for trading rules and implementation details.
        """
        searches = [
            f"{strategy_name} entry rules buy signal conditions",
            f"{strategy_name} exit rules sell signal stop loss",
            f"{strategy_name} indicators parameters settings",
        ]
        
        all_results = []
        for search in searches:
            result = self.search_web(search, search_type="general")
            if result:
                all_results.append(result)
        
        return "\n\n".join(all_results) if all_results else ""
