"""
Researcher Engine - Core component for the Market Researcher & Intelligence Platform

This module orchestrates multiple financial data sources to provide comprehensive
market research, company analysis, and strategic intelligence.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import json
import os

import pandas as pd
import requests
from bs4 import BeautifulSoup
from transformers import pipeline
import finnhub
import openbb
from fredapi import Fred
from newsapi import NewsApiClient

from core.claude_engine import ClaudeAFLEngine
from config import get_settings

logger = logging.getLogger(__name__)


class ResearcherEngine:
    """Main orchestrator for market research and intelligence gathering"""
    
    # Class-level cache for sentiment model (shared across instances)
    _sentiment_model = None
    
    def __init__(self):
        self.claude = ClaudeAFLEngine()
        settings = get_settings()
        self.finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)
        self.fred = Fred(api_key=settings.fred_api_key)
        self.newsapi = NewsApiClient(api_key=settings.newsapi_key)
        
        # Cache for expensive operations
        self._cache = {}
        self._cache_ttl = {}
    
    @classmethod
    def get_sentiment_analyzer(cls):
        """Lazy-load sentiment analyzer (only when needed)"""
        if cls._sentiment_model is None:
            logger.info("Loading FinBERT sentiment model (first use only)...")
            cls._sentiment_model = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finBERT",
                tokenizer="ProsusAI/finBERT"
            )
            logger.info("FinBERT model loaded successfully")
        return cls._sentiment_model
        
    async def get_company_research(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive company research"""
        cache_key = f"company_research_{symbol}"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)
            
        logger.info(f"Researching company: {symbol}")
        
        # Run all data collection tasks concurrently
        tasks = {
            'fundamentals': self._get_fundamentals(symbol),
            'financials': self._get_financials(symbol),
            'news': self._get_company_news(symbol),
            'insider': self._get_insider_trading(symbol),
            'analyst': self._get_analyst_data(symbol),
            'sentiment': self._get_sentiment_analysis(symbol),
            'sec_filings': self._get_sec_filings(symbol)
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Combine results
        research_data = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'fundamentals': results[0] if not isinstance(results[0], Exception) else {},
            'financials': results[1] if not isinstance(results[1], Exception) else {},
            'news': results[2] if not isinstance(results[2], Exception) else [],
            'insider': results[3] if not isinstance(results[3], Exception) else {},
            'analyst': results[4] if not isinstance(results[4], Exception) else {},
            'sentiment': results[5] if not isinstance(results[5], Exception) else {},
            'sec_filings': results[6] if not isinstance(results[6], Exception) else []
        }
        
        # Generate AI summary
        research_data['ai_summary'] = await self._generate_company_summary(research_data)
        
        self._cache_data(cache_key, research_data, ttl_hours=24)
        return research_data
    
    async def get_strategy_analysis(self, symbol: str, strategy_type: str, timeframe: str = "daily") -> Dict[str, Any]:
        """Analyze how well a strategy fits current market conditions"""
        cache_key = f"strategy_analysis_{symbol}_{strategy_type}_{timeframe}"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)
            
        logger.info(f"Analyzing strategy {strategy_type} for {symbol}")
        
        # Get market context
        market_data = await self._get_market_context()
        
        # Get technical analysis
        technical_data = await self._get_technical_analysis(symbol, timeframe)
        
        # Get volatility analysis
        volatility_data = await self._get_volatility_analysis(symbol, timeframe)
        
        # Combine and analyze
        analysis = {
            'symbol': symbol,
            'strategy_type': strategy_type,
            'timeframe': timeframe,
            'market_regime': market_data.get('regime', 'unknown'),
            'volatility': volatility_data,
            'technical_indicators': technical_data,
            'market_context': market_data,
            'strategy_fit_score': self._calculate_strategy_fit(strategy_type, market_data, technical_data),
            'recommendations': await self._generate_strategy_recommendations(strategy_type, market_data, technical_data)
        }
        
        self._cache_data(cache_key, analysis, ttl_hours=6)
        return analysis
    
    async def get_peer_comparison(self, symbol: str, peers: List[str]) -> Dict[str, Any]:
        """Compare company against peers"""
        cache_key = f"peer_comparison_{symbol}_{'_'.join(peers)}"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)
            
        logger.info(f"Comparing {symbol} against peers: {peers}")
        
        # Get data for all companies
        all_symbols = [symbol] + peers
        tasks = {s: self.get_company_research(s) for s in all_symbols}
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Process results
        comparison_data = {
            'symbol': symbol,
            'peers': peers,
            'companies': {},
            'comparison_metrics': {},
            'analysis': {}
        }
        
        for i, symbol in enumerate(all_symbols):
            if not isinstance(results[i], Exception):
                comparison_data['companies'][symbol] = results[i]
        
        # Generate comparison analysis
        comparison_data['analysis'] = await self._generate_comparison_analysis(comparison_data)
        
        self._cache_data(cache_key, comparison_data, ttl_hours=12)
        return comparison_data
    
    async def get_macro_context(self) -> Dict[str, Any]:
        """Get current macroeconomic context"""
        cache_key = "macro_context"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)
            
        logger.info("Getting macroeconomic context")
        
        # Get economic indicators
        economic_data = await self._get_economic_indicators()
        
        # Get market sentiment
        market_sentiment = await self._get_market_sentiment()
        
        # Get Fed policy
        fed_policy = await self._get_fed_policy()
        
        macro_data = {
            'timestamp': datetime.now().isoformat(),
            'economic_indicators': economic_data,
            'market_sentiment': market_sentiment,
            'fed_policy': fed_policy,
            'outlook': await self._generate_macro_outlook(economic_data, market_sentiment, fed_policy)
        }
        
        self._cache_data(cache_key, macro_data, ttl_hours=1)
        return macro_data
    
    async def generate_research_report(self, symbol: str, report_type: str, sections: List[str]) -> Dict[str, Any]:
        """Generate a custom research report"""
        logger.info(f"Generating {report_type} report for {symbol}")
        
        # Get base research data
        research_data = await self.get_company_research(symbol)
        
        # Generate report sections
        report = {
            'symbol': symbol,
            'report_type': report_type,
            'sections': {},
            'generated_at': datetime.now().isoformat(),
            'sections_included': sections
        }
        
        for section in sections:
            if section == 'executive_summary':
                report['sections']['executive_summary'] = await self._generate_executive_summary(research_data)
            elif section == 'fundamental_analysis':
                report['sections']['fundamental_analysis'] = await self._generate_fundamental_analysis(research_data)
            elif section == 'technical_analysis':
                report['sections']['technical_analysis'] = await self._generate_technical_analysis(research_data)
            elif section == 'risk_assessment':
                report['sections']['risk_assessment'] = await self._generate_risk_assessment(research_data)
            elif section == 'investment_recommendation':
                report['sections']['investment_recommendation'] = await self._generate_investment_recommendation(research_data)
        
        return report
    
    # Private methods for data collection
    
    async def _get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Get company fundamentals using OpenBB SDK"""
        try:
            # Use OpenBB SDK for comprehensive fundamentals
            fundamentals = openbb.sdk.equity.fundamental.latest_attributes(symbol=symbol)
            # Return as dict directly if possible, avoiding unnecessary DataFrame conversion
            if hasattr(fundamentals, 'to_dict'):
                return fundamentals.to_dict()
            elif hasattr(fundamentals, 'to_df'):
                return fundamentals.to_df().to_dict()
            return {}
        except Exception as e:
            logger.error(f"Error getting fundamentals for {symbol}: {e}")
            return {}
    
    async def _get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get financial statements using OpenBB SDK"""
        try:
            # Get income statement, balance sheet, cash flow using OpenBB SDK
            income = openbb.sdk.equity.fundamental.income(symbol=symbol)
            balance = openbb.sdk.equity.fundamental.balance(symbol=symbol)
            cashflow = openbb.sdk.equity.fundamental.cash(symbol=symbol)
            
            # Helper to convert efficiently
            def to_dict_efficient(data):
                if hasattr(data, 'to_dict'):
                    return data.to_dict()
                elif hasattr(data, 'to_df'):
                    return data.to_df().to_dict()
                return {}
            
            return {
                'income_statement': to_dict_efficient(income),
                'balance_sheet': to_dict_efficient(balance),
                'cash_flow': to_dict_efficient(cashflow)
            }
        except Exception as e:
            logger.error(f"Error getting financials for {symbol}: {e}")
            return {}
    
    async def _get_company_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Get company news from multiple sources"""
        try:
            # Get news from Finnhub
            finnhub_news = self.finnhub_client.company_news(symbol, _from=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'), to=datetime.now().strftime('%Y-%m-%d'))
            
            # Get news from NewsAPI
            newsapi_news = self.newsapi.get_everything(q=symbol, language='en', sort_by='publishedAt', page_size=10)
            
            # Combine and deduplicate
            all_news = []
            seen_urls = set()
            
            for news_item in finnhub_news:
                if news_item.get('url') not in seen_urls:
                    all_news.append({
                        'source': 'Finnhub',
                        'title': news_item.get('headline', ''),
                        'description': news_item.get('summary', ''),
                        'url': news_item.get('url', ''),
                        'published_at': news_item.get('datetime', ''),
                        'sentiment': self._analyze_news_sentiment(news_item.get('headline', ''))
                    })
                    seen_urls.add(news_item.get('url'))
            
            for article in newsapi_news.get('articles', []):
                if article.get('url') not in seen_urls:
                    all_news.append({
                        'source': article.get('source', {}).get('name', 'NewsAPI'),
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'published_at': article.get('publishedAt', ''),
                        'sentiment': self._analyze_news_sentiment(article.get('title', ''))
                    })
                    seen_urls.add(article.get('url'))
            
            return sorted(all_news, key=lambda x: x.get('published_at', ''), reverse=True)
        except Exception as e:
            logger.error(f"Error getting news for {symbol}: {e}")
            return []
    
    async def _get_insider_trading(self, symbol: str) -> Dict[str, Any]:
        """Get insider trading data"""
        try:
            insider_data = openbb.equity.corporate_actions(symbol, action="insider")
            return insider_data.to_dict() if hasattr(insider_data, 'to_dict') else {}
        except Exception as e:
            logger.error(f"Error getting insider trading for {symbol}: {e}")
            return {}
    
    async def _get_analyst_data(self, symbol: str) -> Dict[str, Any]:
        """Get analyst ratings and estimates"""
        try:
            ratings = openbb.equity.valuation(symbol)
            estimates = openbb.equity.estimates(symbol)
            
            return {
                'ratings': ratings.to_dict() if hasattr(ratings, 'to_dict') else {},
                'estimates': estimates.to_dict() if hasattr(estimates, 'to_dict') else {}
            }
        except Exception as e:
            logger.error(f"Error getting analyst data for {symbol}: {e}")
            return {}
    
    async def _get_sentiment_analysis(self, symbol: str) -> Dict[str, Any]:
        """Analyze overall sentiment for the company"""
        try:
            news = await self._get_company_news(symbol)
            
            if not news:
                return {'overall_sentiment': 'neutral', 'confidence': 0.0, 'sources_analyzed': 0}
            
            # Analyze sentiment of recent news
            sentiments = [item.get('sentiment', {'label': 'NEUTRAL', 'score': 0.0}) for item in news[:10]]
            
            # Calculate weighted sentiment
            positive_count = sum(1 for s in sentiments if s['label'] == 'POSITIVE')
            negative_count = sum(1 for s in sentiments if s['label'] == 'NEGATIVE')
            neutral_count = len(sentiments) - positive_count - negative_count
            
            overall_sentiment = 'neutral'
            if positive_count > negative_count:
                overall_sentiment = 'positive'
            elif negative_count > positive_count:
                overall_sentiment = 'negative'
            
            confidence = (abs(positive_count - negative_count) / len(sentiments)) if sentiments else 0.0
            
            return {
                'overall_sentiment': overall_sentiment,
                'confidence': confidence,
                'sources_analyzed': len(news),
                'sentiment_breakdown': {
                    'positive': positive_count,
                    'negative': negative_count,
                    'neutral': neutral_count
                }
            }
        except Exception as e:
            logger.error(f"Error getting sentiment analysis for {symbol}: {e}")
            return {'overall_sentiment': 'neutral', 'confidence': 0.0, 'sources_analyzed': 0}
    
    async def _get_sec_filings(self, symbol: str) -> List[Dict[str, Any]]:
        """Get recent SEC filings"""
        try:
            # Use OpenBB to get SEC filings
            filings = openbb.sec.filings(symbol)
            return filings.to_dict() if hasattr(filings, 'to_dict') else []
        except Exception as e:
            logger.error(f"Error getting SEC filings for {symbol}: {e}")
            return []
    
    async def _get_market_context(self) -> Dict[str, Any]:
        """Get current market context and regime using OpenBB SDK"""
        try:
            # Get market indices data using OpenBB SDK
            sp500 = openbb.sdk.equity.price.historical(symbol="SPY")
            vix = openbb.sdk.equity.price.historical(symbol="^VIX")
            
            # Get current prices efficiently
            if hasattr(sp500, 'to_df'):
                sp500_df = sp500.to_df()
                sp500_current = float(sp500_df['close'].iloc[-1]) if not sp500_df.empty else 0
            else:
                sp500_current = 0
            
            if hasattr(vix, 'to_df'):
                vix_df = vix.to_df()
                vix_current = float(vix_df['close'].iloc[-1]) if not vix_df.empty else 0
            else:
                vix_current = 0
            
            # Determine market regime based on technical indicators
            market_regime = self._determine_market_regime({'close': sp500_current}, {'close': vix_current})
            
            return {
                'regime': market_regime,
                'sp500_level': sp500_current,
                'vix_level': vix_current,
                'market_sentiment': self._get_market_sentiment_score()
            }
        except Exception as e:
            logger.error(f"Error getting market context: {e}")
            return {'regime': 'unknown', 'market_sentiment': 0.5}
    
    async def _get_technical_analysis(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Get technical indicators using OpenBB SDK"""
        try:
            # Get price data using OpenBB SDK
            price_data = openbb.sdk.equity.price.historical(symbol=symbol, interval=timeframe)
            
            # Calculate technical indicators manually from price data
            if hasattr(price_data, 'to_df'):
                df = price_data.to_df()
                if not df.empty:
                    # Calculate SMA
                    sma_20 = df['close'].rolling(window=20).mean()
                    
                    # Calculate RSI
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    rsi = 100 - (100 / (1 + rs))
                    
                    # Calculate MACD
                    exp1 = df['close'].ewm(span=12).mean()
                    exp2 = df['close'].ewm(span=26).mean()
                    macd_line = exp1 - exp2
                    signal_line = macd_line.ewm(span=9).mean()
                    macd_histogram = macd_line - signal_line
                    
                    return {
                        'price_data': {
                            'latest_close': float(df['close'].iloc[-1]),
                            'latest_volume': float(df['volume'].iloc[-1]) if 'volume' in df else 0,
                            'period_high': float(df['close'].max()),
                            'period_low': float(df['close'].min())
                        },
                        'indicators': {
                            'sma': float(sma_20.iloc[-1]) if not sma_20.empty else 0,
                            'rsi': float(rsi.iloc[-1]) if not rsi.empty else 0,
                            'macd': {
                                'macd_line': float(macd_line.iloc[-1]),
                                'signal_line': float(signal_line.iloc[-1]),
                                'histogram': float(macd_histogram.iloc[-1])
                            }
                        }
                    }
            
            return {'price_data': {}, 'indicators': {}}
        except Exception as e:
            logger.error(f"Error getting technical analysis for {symbol}: {e}")
            return {}
    
    async def _get_volatility_analysis(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """Analyze volatility characteristics using OpenBB SDK"""
        try:
            # Get historical volatility using OpenBB SDK
            volatility = openbb.sdk.equity.price.historical(symbol=symbol, interval=timeframe)
            
            # Calculate volatility metrics
            if hasattr(volatility, 'to_df'):
                df = volatility.to_df()
                if not df.empty:
                    returns = df['close'].pct_change().dropna()
                    historical_volatility = returns.std() * (252 ** 0.5)  # Annualized volatility
                    
                    return {
                        'historical_volatility': float(historical_volatility),
                        'volatility_rank': 0.5,  # Simplified for now
                        'volatility_trend': 'stable'
                    }
            
            return {'historical_volatility': 0, 'volatility_rank': 0, 'volatility_trend': 'unknown'}
        except Exception as e:
            logger.error(f"Error getting volatility analysis for {symbol}: {e}")
            return {'historical_volatility': 0, 'volatility_rank': 0, 'volatility_trend': 'unknown'}
    
    async def _get_economic_indicators(self) -> Dict[str, Any]:
        """Get key economic indicators"""
        try:
            # Get from FRED
            indicators = {
                'gdp_growth': self.fred.get_series('GDPC1', observation_start='2020-01-01'),
                'unemployment': self.fred.get_series('UNRATE', observation_start='2020-01-01'),
                'inflation': self.fred.get_series('CPIAUCSL', observation_start='2020-01-01'),
                'fed_funds_rate': self.fred.get_series('FEDFUNDS', observation_start='2020-01-01')
            }
            
            return {
                'latest_values': {k: v.iloc[-1] if hasattr(v, 'iloc') else 0 for k, v in indicators.items()},
                'trends': {k: self._calculate_trend(v) for k, v in indicators.items()}
            }
        except Exception as e:
            logger.error(f"Error getting economic indicators: {e}")
            return {}
    
    async def _get_market_sentiment(self) -> Dict[str, Any]:
        """Get overall market sentiment"""
        try:
            # Use various sentiment indicators
            fear_greed = self._get_fear_greed_index()
            put_call_ratio = self._get_put_call_ratio()
            
            return {
                'fear_greed_index': fear_greed,
                'put_call_ratio': put_call_ratio,
                'overall_sentiment': self._calculate_overall_sentiment(fear_greed, put_call_ratio)
            }
        except Exception as e:
            logger.error(f"Error getting market sentiment: {e}")
            return {'overall_sentiment': 'neutral'}
    
    async def _get_fed_policy(self) -> Dict[str, Any]:
        """Get current Fed policy stance"""
        try:
            # Get Fed funds rate and policy expectations
            fed_rate = self.fred.get_series('FEDFUNDS').iloc[-1]
            inflation_expectations = self.fred.get_series('PCEPI').iloc[-1]
            
            return {
                'current_rate': fed_rate,
                'inflation_trend': inflation_expectations,
                'policy_stance': self._determine_policy_stance(fed_rate, inflation_expectations)
            }
        except Exception as e:
            logger.error(f"Error getting Fed policy: {e}")
            return {'policy_stance': 'neutral'}
    
    # Helper methods
    
    def _analyze_news_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of a news headline"""
        try:
            # Use lazy-loaded sentiment analyzer
            analyzer = self.get_sentiment_analyzer()
            result = analyzer(text)[0]
            return {
                'label': result['label'],
                'score': result['score']
            }
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {'label': 'NEUTRAL', 'score': 0.0}
    
    def _determine_market_regime(self, sp500_data: Any, vix_data: Any) -> str:
        """Determine current market regime"""
        # Simplified regime detection
        try:
            sp500_change = sp500_data.get('change_percent', 0) if hasattr(sp500_data, 'get') else 0
            vix_level = vix_data.get('close', 20) if hasattr(vix_data, 'get') else 20
            
            if sp500_change > 0 and vix_level < 20:
                return 'bull_market'
            elif sp500_change < 0 and vix_level > 30:
                return 'bear_market'
            else:
                return 'sideways'
        except Exception:
            return 'unknown'
    
    def _calculate_strategy_fit(self, strategy_type: str, market_data: Dict, technical_data: Dict) -> float:
        """Calculate how well a strategy fits current conditions"""
        # Simplified scoring logic
        base_score = 0.5
        
        if strategy_type == 'momentum':
            if market_data.get('regime') == 'bull_market':
                base_score += 0.3
            elif market_data.get('regime') == 'bear_market':
                base_score -= 0.2
        
        elif strategy_type == 'mean_reversion':
            if market_data.get('regime') == 'sideways':
                base_score += 0.3
            elif market_data.get('regime') == 'bull_market':
                base_score -= 0.1
        
        return max(0.0, min(1.0, base_score))
    
    def _generate_company_summary(self, research_data: Dict) -> str:
        """Generate AI summary of company research"""
        prompt = f"""
        Summarize this company research data for {research_data['symbol']}:
        
        Fundamentals: {research_data.get('fundamentals', {})}
        Financial Health: {research_data.get('financials', {})}
        Recent News Sentiment: {research_data.get('sentiment', {})}
        Analyst Consensus: {research_data.get('analyst', {})}
        
        Provide a concise summary focusing on:
        1. Company's current position
        2. Key strengths and risks
        3. Investment outlook
        """
        
        return self.claude.chat(message=prompt)
    
    def _generate_strategy_recommendations(self, strategy_type: str, market_data: Dict, technical_data: Dict) -> List[str]:
        """Generate strategy-specific recommendations"""
        prompt = f"""
        Based on current market conditions and technical analysis, provide specific recommendations for {strategy_type} strategy:
        
        Market Regime: {market_data.get('regime')}
        Market Sentiment: {market_data.get('market_sentiment')}
        Technical Indicators: {technical_data.get('indicators', {})}
        
        Focus on parameter adjustments and risk management.
        """
        
        response = self.claude.chat(message=prompt)
        return response.split('\n') if response else []
    
    def _generate_comparison_analysis(self, comparison_data: Dict) -> Dict[str, Any]:
        """Generate peer comparison analysis"""
        prompt = f"""
        Analyze this peer comparison for {comparison_data['symbol']} vs {comparison_data['peers']}:
        
        Company Data: {comparison_data['companies']}
        
        Provide analysis focusing on:
        1. Relative valuation
        2. Growth prospects
        3. Risk factors
        4. Investment recommendation
        """
        
        response = self.claude.chat(message=prompt)
        return {'analysis': response}
    
    def _generate_executive_summary(self, research_data: Dict) -> str:
        """Generate executive summary section"""
        prompt = f"""
        Create an executive summary for {research_data['symbol']} research report.
        Focus on key insights and actionable recommendations.
        Keep it under 300 words.
        """
        return self.claude.chat(message=prompt)
    
    def _generate_fundamental_analysis(self, research_data: Dict) -> str:
        """Generate fundamental analysis section"""
        prompt = f"""
        Create a detailed fundamental analysis for {research_data['symbol']} based on:
        Financials: {research_data.get('financials', {})}
        Fundamentals: {research_data.get('fundamentals', {})}
        Focus on valuation, growth, and financial health.
        """
        return self.claude.chat(message=prompt)
    
    def _generate_technical_analysis(self, research_data: Dict) -> str:
        """Generate technical analysis section"""
        prompt = f"""
        Create a technical analysis for {research_data['symbol']} based on available data.
        Focus on key support/resistance levels and trend analysis.
        """
        return self.claude.chat(message=prompt)
    
    def _generate_risk_assessment(self, research_data: Dict) -> str:
        """Generate risk assessment section"""
        prompt = f"""
        Create a comprehensive risk assessment for {research_data['symbol']} including:
        1. Business risks
        2. Financial risks
        3. Market risks
        4. Regulatory risks
        """
        return self.claude.chat(message=prompt)
    
    def _generate_investment_recommendation(self, research_data: Dict) -> str:
        """Generate investment recommendation"""
        prompt = f"""
        Based on all research data for {research_data['symbol']}, provide:
        1. Investment thesis
        2. Price target (if applicable)
        3. Risk/reward assessment
        4. Time horizon
        5. Specific recommendation (Buy/Hold/Sell)
        """
        return self.claude.chat(message=prompt)
    
    # Caching methods
    
    def _is_cached(self, key: str) -> bool:
        """Check if data is cached and still valid"""
        if key not in self._cache:
            return False
        
        if key not in self._cache_ttl:
            return False
        
        return datetime.now() < self._cache_ttl[key]
    
    def _get_cached(self, key: str) -> Any:
        """Get cached data"""
        return self._cache.get(key)
    
    def _cache_data(self, key: str, data: Any, ttl_hours: int = 1):
        """Cache data with TTL"""
        self._cache[key] = data
        self._cache_ttl[key] = datetime.now() + timedelta(hours=ttl_hours)
    
    # Utility methods for economic analysis
    
    def _calculate_trend(self, series) -> str:
        """Calculate trend direction of a time series"""
        if hasattr(series, 'pct_change'):
            recent_change = series.pct_change().tail(10).mean()
            if recent_change > 0.001:
                return 'up'
            elif recent_change < -0.001:
                return 'down'
            else:
                return 'flat'
        return 'unknown'
    
    def _get_fear_greed_index(self) -> float:
        """Get Fear & Greed Index (simplified)"""
        # This would typically call an external API
        # For now, return a placeholder
        return 50.0
    
    def _get_put_call_ratio(self) -> float:
        """Get Put/Call Ratio (simplified)"""
        # This would typically call an options data API
        # For now, return a placeholder
        return 0.8
    
    def _calculate_overall_sentiment(self, fear_greed: float, put_call: float) -> str:
        """Calculate overall market sentiment"""
        if fear_greed > 70:
            return 'greedy'
        elif fear_greed < 30:
            return 'fearful'
        else:
            return 'neutral'
    
    def _determine_policy_stance(self, rate: float, inflation: float) -> str:
        """Determine Fed policy stance"""
        if rate > 4.0 and inflation > 3.0:
            return 'hawkish'
        elif rate < 2.0 and inflation < 2.0:
            return 'dovish'
        else:
            return 'neutral'

    def _get_market_sentiment_score(self) -> float:
        """Get a composite market sentiment score between 0.0 and 1.0"""
        fear_greed = self._get_fear_greed_index()
        # Normalize fear/greed (0-100) to 0.0-1.0
        return fear_greed / 100.0

    async def _generate_macro_outlook(
        self,
        economic_data: Dict[str, Any],
        market_sentiment: Dict[str, Any],
        fed_policy: Dict[str, Any],
    ) -> str:
        """Generate a macro outlook narrative using Claude"""
        prompt = f"""
        Based on the following macroeconomic data, provide a concise market outlook:

        Economic Indicators: {economic_data}
        Market Sentiment: {market_sentiment}
        Fed Policy: {fed_policy}

        Provide:
        1. Overall market environment assessment
        2. Key risks and opportunities
        3. Short-term outlook (1-3 months)
        """
        return self.claude.chat(message=prompt)
