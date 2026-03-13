-- ============================================================================
-- Feedback & Analytics Migration
-- ============================================================================
-- This migration creates tables for user feedback, training suggestions,
-- and analytics to track AI improvement and user engagement.
--
-- Run this SQL in your Supabase SQL Editor after 001_training_data.sql
-- ============================================================================

-- ============================================================================
-- 1. User Feedback Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- User who submitted feedback
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    
    -- Reference to the code this feedback is about
    code_id UUID REFERENCES afl_codes(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    
    -- Feedback content
    original_prompt TEXT NOT NULL,
    generated_code TEXT NOT NULL,
    feedback_type VARCHAR(50) NOT NULL, -- correction, improvement, bug, praise
    feedback_text TEXT NOT NULL,
    correct_code TEXT, -- User's corrected version (if applicable)
    rating INTEGER CHECK (rating >= 1 AND rating <= 5), -- 1-5 stars
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending_review', -- pending_review, reviewed, implemented, rejected
    admin_notes TEXT,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. Training Suggestions Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS training_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- User who suggested this training
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    
    -- Link to feedback if this came from feedback
    feedback_id UUID REFERENCES user_feedback(id) ON DELETE SET NULL,
    
    -- Suggested training data
    title VARCHAR(255) NOT NULL,
    training_type VARCHAR(50) NOT NULL, -- example, rule, correction, pattern, etc.
    input_prompt TEXT NOT NULL,
    expected_output TEXT NOT NULL,
    explanation TEXT,
    category VARCHAR(100) DEFAULT 'afl',
    tags JSONB DEFAULT '[]'::jsonb,
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    
    -- Review status
    status VARCHAR(50) DEFAULT 'pending', -- pending, approved, rejected, implemented
    admin_notes TEXT,
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    
    -- If approved, link to the created training data
    training_data_id UUID REFERENCES training_data(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. Analytics Events Table (for tracking usage patterns)
-- ============================================================================

CREATE TABLE IF NOT EXISTS analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- User tracking
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
    -- Event details
    event_type VARCHAR(100) NOT NULL, -- code_generated, training_added, feedback_submitted, etc.
    event_category VARCHAR(50) NOT NULL, -- afl, training, admin, user
    event_data JSONB DEFAULT '{}'::jsonb, -- Flexible event-specific data
    
    -- Context
    session_id VARCHAR(255),
    ip_address VARCHAR(50),
    user_agent TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 4. AI Performance Metrics Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS ai_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Metric details
    metric_name VARCHAR(100) NOT NULL, -- avg_quality_score, correction_rate, user_satisfaction, etc.
    metric_value DECIMAL(10, 2) NOT NULL,
    metric_category VARCHAR(50), -- afl, training, overall
    
    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Time period this metric represents
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 5. Create Indexes for Better Performance
-- ============================================================================

-- User Feedback indexes
CREATE INDEX IF NOT EXISTS idx_feedback_user ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON user_feedback(status);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON user_feedback(rating);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON user_feedback(created_at DESC);

-- Training Suggestions indexes
CREATE INDEX IF NOT EXISTS idx_suggestions_user ON training_suggestions(user_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON training_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_suggestions_type ON training_suggestions(training_type);
CREATE INDEX IF NOT EXISTS idx_suggestions_created ON training_suggestions(created_at DESC);

-- Analytics Events indexes
CREATE INDEX IF NOT EXISTS idx_events_user ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_category ON analytics_events(event_category);
CREATE INDEX IF NOT EXISTS idx_events_created ON analytics_events(created_at DESC);

-- AI Metrics indexes
CREATE INDEX IF NOT EXISTS idx_metrics_name ON ai_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_category ON ai_metrics(metric_category);
CREATE INDEX IF NOT EXISTS idx_metrics_period ON ai_metrics(period_start, period_end);

-- ============================================================================
-- 6. Create Updated_at Triggers
-- ============================================================================

CREATE OR REPLACE FUNCTION update_feedback_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS feedback_updated_at ON user_feedback;
CREATE TRIGGER feedback_updated_at
    BEFORE UPDATE ON user_feedback
    FOR EACH ROW
    EXECUTE FUNCTION update_feedback_updated_at();

DROP TRIGGER IF EXISTS suggestions_updated_at ON training_suggestions;
CREATE TRIGGER suggestions_updated_at
    BEFORE UPDATE ON training_suggestions
    FOR EACH ROW
    EXECUTE FUNCTION update_feedback_updated_at();

-- ============================================================================
-- 7. Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_metrics ENABLE ROW LEVEL SECURITY;

-- User Feedback Policies
-- Users can read their own feedback
CREATE POLICY "Users can read own feedback"
    ON user_feedback FOR SELECT
    USING (user_id = auth.uid());

-- Users can create their own feedback
CREATE POLICY "Users can create feedback"
    ON user_feedback FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admins can read all feedback
CREATE POLICY "Admins can read all feedback"
    ON user_feedback FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- Admins can update all feedback
CREATE POLICY "Admins can update feedback"
    ON user_feedback FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- Training Suggestions Policies
-- Users can read their own suggestions
CREATE POLICY "Users can read own suggestions"
    ON training_suggestions FOR SELECT
    USING (user_id = auth.uid());

-- Users can create suggestions
CREATE POLICY "Users can create suggestions"
    ON training_suggestions FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admins can do everything with suggestions
CREATE POLICY "Admins can manage suggestions"
    ON training_suggestions FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- Analytics Events Policies
-- Users can create their own events
CREATE POLICY "Users can create events"
    ON analytics_events FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Admins can read all events
CREATE POLICY "Admins can read events"
    ON analytics_events FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- AI Metrics Policies
-- Admins only
CREATE POLICY "Admins can manage metrics"
    ON ai_metrics FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- ============================================================================
-- 8. Grant Permissions
-- ============================================================================

-- Grant usage to authenticated users
GRANT SELECT, INSERT ON user_feedback TO authenticated;
GRANT SELECT, INSERT ON training_suggestions TO authenticated;
GRANT INSERT ON analytics_events TO authenticated;

-- Grant full access to service role (backend)
GRANT ALL ON user_feedback TO service_role;
GRANT ALL ON training_suggestions TO service_role;
GRANT ALL ON analytics_events TO service_role;
GRANT ALL ON ai_metrics TO service_role;

-- ============================================================================
-- 9. Create Views for Common Queries
-- ============================================================================

-- View for pending suggestions with user info
CREATE OR REPLACE VIEW pending_training_suggestions AS
SELECT 
    ts.id,
    ts.title,
    ts.training_type,
    ts.category,
    ts.priority,
    ts.created_at,
    u.email as suggested_by_email,
    u.name as suggested_by_name,
    uf.feedback_text as related_feedback
FROM training_suggestions ts
JOIN users u ON ts.user_id = u.id
LEFT JOIN user_feedback uf ON ts.feedback_id = uf.id
WHERE ts.status = 'pending'
ORDER BY ts.created_at DESC;

-- View for recent feedback with ratings
CREATE OR REPLACE VIEW recent_feedback_summary AS
SELECT 
    uf.id,
    uf.feedback_type,
    uf.rating,
    uf.created_at,
    u.email as user_email,
    uf.status,
    CASE 
        WHEN uf.correct_code IS NOT NULL THEN TRUE 
        ELSE FALSE 
    END as has_correction
FROM user_feedback uf
JOIN users u ON uf.user_id = u.id
ORDER BY uf.created_at DESC
LIMIT 100;

-- View for training effectiveness metrics
CREATE OR REPLACE VIEW training_effectiveness_view AS
SELECT 
    COUNT(*) FILTER (WHERE feedback_type = 'correction') as total_corrections,
    COUNT(*) FILTER (WHERE feedback_type = 'praise') as total_praise,
    AVG(rating) as average_rating,
    COUNT(DISTINCT user_id) as unique_users,
    DATE_TRUNC('day', created_at) as date
FROM user_feedback
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date DESC;

-- ============================================================================
-- Done! Feedback and analytics tables are ready.
-- ============================================================================

-- To verify, run:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('user_feedback', 'training_suggestions', 'analytics_events', 'ai_metrics');