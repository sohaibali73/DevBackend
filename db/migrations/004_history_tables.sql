-- Migration: 004_history_tables.sql
-- Description: Add history tables for AFL Generator and Reverse Engineer
-- Date: 2026-01-30

-- ============================================
-- AFL History Table
-- Stores history of AFL code generation sessions
-- ============================================
CREATE TABLE IF NOT EXISTS afl_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    strategy_description TEXT NOT NULL,
    generated_code TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key to users table (if exists)
    CONSTRAINT fk_afl_history_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast user history queries
CREATE INDEX IF NOT EXISTS idx_afl_history_user_timestamp 
    ON afl_history(user_id, timestamp DESC);

-- Index for strategy type filtering
CREATE INDEX IF NOT EXISTS idx_afl_history_strategy_type 
    ON afl_history(strategy_type);

-- ============================================
-- Reverse Engineer History Table
-- Stores history of reverse engineering sessions
-- ============================================
CREATE TABLE IF NOT EXISTS reverse_engineer_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    research_summary TEXT,
    generated_code TEXT NOT NULL,
    schematic JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key to users table (if exists)
    CONSTRAINT fk_reverse_engineer_history_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast user history queries
CREATE INDEX IF NOT EXISTS idx_reverse_engineer_history_user_timestamp 
    ON reverse_engineer_history(user_id, timestamp DESC);

-- Index for strategy name searches
CREATE INDEX IF NOT EXISTS idx_reverse_engineer_history_strategy_name 
    ON reverse_engineer_history(strategy_name);

-- ============================================
-- Add metadata column to messages table
-- For storing artifact data with messages
-- ============================================
ALTER TABLE messages 
    ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Index for artifact queries
CREATE INDEX IF NOT EXISTS idx_messages_metadata_has_artifacts 
    ON messages((metadata->>'has_artifacts')) 
    WHERE metadata IS NOT NULL;

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================

-- Enable RLS on afl_history
ALTER TABLE afl_history ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own AFL history
CREATE POLICY afl_history_select_policy ON afl_history
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only insert their own AFL history
CREATE POLICY afl_history_insert_policy ON afl_history
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only delete their own AFL history
CREATE POLICY afl_history_delete_policy ON afl_history
    FOR DELETE
    USING (user_id = current_setting('app.current_user_id', true));

-- Enable RLS on reverse_engineer_history
ALTER TABLE reverse_engineer_history ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own reverse engineer history
CREATE POLICY reverse_engineer_history_select_policy ON reverse_engineer_history
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only insert their own reverse engineer history
CREATE POLICY reverse_engineer_history_insert_policy ON reverse_engineer_history
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only delete their own reverse engineer history
CREATE POLICY reverse_engineer_history_delete_policy ON reverse_engineer_history
    FOR DELETE
    USING (user_id = current_setting('app.current_user_id', true));

-- ============================================
-- Grant Permissions (for service role)
-- ============================================
GRANT ALL ON afl_history TO service_role;
GRANT ALL ON reverse_engineer_history TO service_role;

-- ============================================
-- Comments for documentation
-- ============================================
COMMENT ON TABLE afl_history IS 'Stores history of AFL code generation sessions for each user';
COMMENT ON TABLE reverse_engineer_history IS 'Stores history of reverse engineering sessions with research and schematics';
COMMENT ON COLUMN messages.metadata IS 'JSON metadata including artifact information for renderable code blocks';
