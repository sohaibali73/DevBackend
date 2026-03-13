-- Migration 008: Create missing tables for content, backtest, and writing styles
-- SAFE VERSION: Drops and recreates tables to avoid schema conflicts
-- Date: 2026-02-23

-- ============================================================================
-- content_items — stores articles, documents, slides, dashboards
-- ============================================================================
DROP TABLE IF EXISTS content_items CASCADE;
CREATE TABLE content_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT DEFAULT '',
    content_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    tags JSONB DEFAULT '[]'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_content_items_user_id ON content_items(user_id);
CREATE INDEX idx_content_items_content_type ON content_items(content_type);
CREATE INDEX idx_content_items_status ON content_items(status);

ALTER TABLE content_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "content_items_all" ON content_items FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON content_items TO service_role;
GRANT ALL ON content_items TO authenticated;

-- ============================================================================
-- writing_styles
-- ============================================================================
DROP TABLE IF EXISTS writing_styles CASCADE;
CREATE TABLE writing_styles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    tone VARCHAR(100) DEFAULT 'professional',
    formality VARCHAR(50) DEFAULT 'medium',
    personality_tags JSONB DEFAULT '[]'::jsonb,
    sample_text TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_writing_styles_user_id ON writing_styles(user_id);

ALTER TABLE writing_styles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "writing_styles_all" ON writing_styles FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON writing_styles TO service_role;
GRANT ALL ON writing_styles TO authenticated;

-- ============================================================================
-- backtest_results
-- ============================================================================
DROP TABLE IF EXISTS backtest_results CASCADE;
CREATE TABLE backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    strategy_id UUID,
    filename VARCHAR(500),
    raw_results TEXT,
    metrics JSONB DEFAULT '{}'::jsonb,
    ai_analysis TEXT,
    recommendations JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_backtest_results_user_id ON backtest_results(user_id);

ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "backtest_results_all" ON backtest_results FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON backtest_results TO service_role;
GRANT ALL ON backtest_results TO authenticated;
