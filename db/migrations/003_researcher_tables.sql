-- Researcher Tool Database Schema
-- Adds tables for comprehensive market research and intelligence platform

-- Research Reports Table
CREATE TABLE IF NOT EXISTS research_reports (
    id SERIAL PRIMARY KEY,
    report_id VARCHAR(100) UNIQUE NOT NULL,
    user_id VARCHAR REFERENCES auth.users(id),
    symbol VARCHAR(10) NOT NULL,
    report_type VARCHAR(50) NOT NULL,  -- 'company', 'strategy', 'comparison', 'macro'
    title VARCHAR(255),
    sections JSONB NOT NULL,  -- Array of report sections
    export_formats TEXT[],   -- ['pdf', 'csv', 'markdown']
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,    -- For auto-cleanup
    INDEX idx_research_reports_user (user_id),
    INDEX idx_research_reports_symbol (symbol),
    INDEX idx_research_reports_type (report_type),
    INDEX idx_research_reports_created (created_at)
);

-- Research Cache Table
CREATE TABLE IF NOT EXISTS research_cache (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    data_type VARCHAR(50) NOT NULL,  -- 'fundamentals', 'news', 'insider', 'analyst', 'sec', 'volatility', 'macro'
    data JSONB NOT NULL,
    source VARCHAR(50) NOT NULL,     -- 'fmp', 'finnhub', 'sec', 'fred', 'tavily'
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    INDEX idx_research_cache_lookup (symbol, data_type),
    INDEX idx_research_cache_expires (expires_at),
    INDEX idx_research_cache_source (source)
);

-- Research History Table
CREATE TABLE IF NOT EXISTS research_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES auth.users(id),
    symbol VARCHAR(10),
    research_type VARCHAR(50),  -- 'company', 'strategy', 'comparison', 'macro'
    query_text TEXT,           -- User's research query
    result_summary TEXT,       -- Brief summary of results
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_research_history_user (user_id),
    INDEX idx_research_history_symbol (symbol),
    INDEX idx_research_history_type (research_type),
    INDEX idx_research_history_created (created_at)
);

-- Company Research Data Table
CREATE TABLE IF NOT EXISTS company_research (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    description TEXT,
    fundamentals JSONB,        -- Complete fundamentals data
    financial_health JSONB,    -- Calculated health metrics
    analyst_consensus JSONB,   -- Analyst ratings and targets
    insider_activity JSONB,    -- Insider trading data
    ai_summary TEXT,           -- AI-generated summary
    last_updated TIMESTAMP DEFAULT NOW(),
    data_source VARCHAR(50),   -- Primary data source
    INDEX idx_company_research_symbol (symbol),
    INDEX idx_company_research_sector (sector),
    INDEX idx_company_research_industry (industry)
);

-- Strategy Analysis Table
CREATE TABLE IF NOT EXISTS strategy_analysis (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES auth.users(id),
    symbol VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(100) NOT NULL,
    timeframe VARCHAR(20) DEFAULT 'daily',
    market_regime VARCHAR(50),
    strategy_fit VARCHAR(50),
    confidence DECIMAL(3,2),
    recommendation TEXT,
    risks JSONB,               -- Array of risk factors
    opportunities JSONB,       -- Array of opportunities
    adjusted_parameters JSONB, -- Suggested parameter adjustments
    analysis_data JSONB,       -- Raw analysis data
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_strategy_analysis_user (user_id),
    INDEX idx_strategy_analysis_symbol (symbol),
    INDEX idx_strategy_analysis_strategy (strategy_type),
    INDEX idx_strategy_analysis_created (created_at)
);

-- Peer Comparison Table
CREATE TABLE IF NOT EXISTS peer_comparison (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES auth.users(id),
    company_symbol VARCHAR(10) NOT NULL,
    comparison_date DATE NOT NULL,
    peers JSONB NOT NULL,      -- Array of peer symbols
    metrics JSONB NOT NULL,    -- Array of metrics compared
    comparison_data JSONB NOT NULL, -- Complete comparison results
    analysis TEXT,
    recommendation TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_peer_comparison_user (user_id),
    INDEX idx_peer_comparison_company (company_symbol),
    INDEX idx_peer_comparison_date (comparison_date)
);

-- Macro Context Table
CREATE TABLE IF NOT EXISTS macro_context (
    id SERIAL PRIMARY KEY,
    context_date DATE NOT NULL,
    fed_rate DECIMAL(5,3),
    inflation DECIMAL(5,3),
    unemployment DECIMAL(5,3),
    gdp_growth DECIMAL(5,3),
    sentiment_index DECIMAL(5,3),
    market_outlook VARCHAR(50),
    upcoming_events JSONB,     -- Array of upcoming economic events
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(context_date),
    INDEX idx_macro_context_date (context_date)
);

-- News Articles Table
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    headline VARCHAR(500) NOT NULL,
    source VARCHAR(100),
    timestamp TIMESTAMP,
    sentiment VARCHAR(20),     -- 'positive', 'negative', 'neutral'
    sentiment_score DECIMAL(4,3),
    summary TEXT,
    url VARCHAR(1000),
    content TEXT,              -- Full article content (optional)
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_news_articles_symbol (symbol),
    INDEX idx_news_articles_date (timestamp),
    INDEX idx_news_articles_sentiment (sentiment),
    INDEX idx_news_articles_source (source)
);

-- Economic Indicators Table
CREATE TABLE IF NOT EXISTS economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_date DATE NOT NULL,
    indicator_name VARCHAR(100) NOT NULL,
    indicator_value DECIMAL(15,6),
    indicator_source VARCHAR(50), -- 'fred', 'bureau_of_labor', etc.
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(indicator_date, indicator_name),
    INDEX idx_economic_indicators_date (indicator_date),
    INDEX idx_economic_indicators_name (indicator_name)
);

-- Research Analytics Table
CREATE TABLE IF NOT EXISTS research_analytics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES auth.users(id),
    research_type VARCHAR(50),
    symbol VARCHAR(10),
    action VARCHAR(50),        -- 'research', 'report_generated', 'comparison', 'analysis'
    action_data JSONB,         -- Additional action-specific data
    response_time DECIMAL(8,3), -- Response time in milliseconds
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_research_analytics_user (user_id),
    INDEX idx_research_analytics_type (research_type),
    INDEX idx_research_analytics_symbol (symbol),
    INDEX idx_research_analytics_action (action),
    INDEX idx_research_analytics_created (created_at)
);

-- Add RLS policies for security
ALTER TABLE research_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_research ENABLE ROW LEVEL SECURITY;
ALTER TABLE strategy_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE peer_comparison ENABLE ROW LEVEL SECURITY;
ALTER TABLE macro_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE economic_indicators ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_analytics ENABLE ROW LEVEL SECURITY;

-- Policies for research_reports
CREATE POLICY "Users can view their own reports" ON research_reports
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own reports" ON research_reports
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own reports" ON research_reports
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own reports" ON research_reports
    FOR DELETE USING (auth.uid() = user_id);

-- Policies for research_history
CREATE POLICY "Users can view their own history" ON research_history
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own history" ON research_history
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for strategy_analysis
CREATE POLICY "Users can view their own strategy analysis" ON strategy_analysis
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own strategy analysis" ON strategy_analysis
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for peer_comparison
CREATE POLICY "Users can view their own peer comparisons" ON peer_comparison
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own peer comparisons" ON peer_comparison
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for research_analytics
CREATE POLICY "Users can insert their own analytics" ON research_analytics
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for public data (company_research, macro_context, news_articles, economic_indicators)
-- These can be read by anyone but only admins can modify
CREATE POLICY "Public read access" ON company_research
    FOR SELECT USING (true);

CREATE POLICY "Admin write access" ON company_research
    FOR ALL USING (auth.uid() IN (SELECT id FROM users WHERE is_admin = true));

CREATE POLICY "Public read access" ON macro_context
    FOR SELECT USING (true);

CREATE POLICY "Admin write access" ON macro_context
    FOR ALL USING (auth.uid() IN (SELECT id FROM users WHERE is_admin = true));

CREATE POLICY "Public read access" ON news_articles
    FOR SELECT USING (true);

CREATE POLICY "Admin write access" ON news_articles
    FOR ALL USING (auth.uid() IN (SELECT id FROM users WHERE is_admin = true));

CREATE POLICY "Public read access" ON economic_indicators
    FOR SELECT USING (true);

CREATE POLICY "Admin write access" ON economic_indicators
    FOR ALL USING (auth.uid() IN (SELECT id FROM users WHERE is_admin = true));

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_research_reports_user_created ON research_reports(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_research_history_user_created ON research_history(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_analysis_user_created ON strategy_analysis(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_peer_comparison_user_created ON peer_comparison(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_research_analytics_user_created ON research_analytics(user_id, created_at);

-- Create function to clean up expired cache entries
CREATE OR REPLACE FUNCTION cleanup_expired_research_cache()
RETURNS void AS $$
BEGIN
    DELETE FROM research_cache WHERE expires_at < NOW();
    DELETE FROM research_reports WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

-- Create function to update company research timestamp
CREATE OR REPLACE FUNCTION update_company_research_timestamp()
RETURNS trigger AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for company_research updates
DROP TRIGGER IF EXISTS trigger_update_company_research_timestamp ON company_research;
CREATE TRIGGER trigger_update_company_research_timestamp
    BEFORE UPDATE ON company_research
    FOR EACH ROW EXECUTE FUNCTION update_company_research_timestamp();

-- Grant permissions
GRANT ALL ON research_reports TO authenticated;
GRANT ALL ON research_cache TO authenticated;
GRANT ALL ON research_history TO authenticated;
GRANT ALL ON company_research TO authenticated;
GRANT ALL ON strategy_analysis TO authenticated;
GRANT ALL ON peer_comparison TO authenticated;
GRANT ALL ON macro_context TO authenticated;
GRANT ALL ON news_articles TO authenticated;
GRANT ALL ON economic_indicators TO authenticated;
GRANT ALL ON research_analytics TO authenticated;

GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated;