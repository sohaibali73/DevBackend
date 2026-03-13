-- Migration: 004_history_tables_FIXED.sql
-- Description: Add history tables for AFL Generator and Reverse Engineer (FIXED VERSION)
-- Date: 2026-02-05
-- 
-- IMPORTANT: This migration creates tables and uses JWT-based RLS policies
-- that work with both anon and service_role keys
-- ============================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- AFL History Table
-- Stores history of AFL code generation sessions
-- ============================================
DROP TABLE IF EXISTS afl_history CASCADE;

CREATE TABLE afl_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,  -- Changed from TEXT to UUID to match users.id
    strategy_description TEXT NOT NULL,
    generated_code TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key to users table
    CONSTRAINT fk_afl_history_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast user history queries
CREATE INDEX idx_afl_history_user_timestamp 
    ON afl_history(user_id, timestamp DESC);

-- Index for strategy type filtering
CREATE INDEX idx_afl_history_strategy_type 
    ON afl_history(strategy_type);

-- ============================================
-- Reverse Engineer History Table
-- Stores history of reverse engineering sessions
-- ============================================
DROP TABLE IF EXISTS reverse_engineer_history CASCADE;

CREATE TABLE reverse_engineer_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,  -- Changed from TEXT to UUID to match users.id
    strategy_name TEXT NOT NULL,
    research_summary TEXT,
    generated_code TEXT NOT NULL,
    schematic JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key to users table
    CONSTRAINT fk_reverse_engineer_history_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast user history queries
CREATE INDEX idx_reverse_engineer_history_user_timestamp 
    ON reverse_engineer_history(user_id, timestamp DESC);

-- Index for strategy name searches
CREATE INDEX idx_reverse_engineer_history_strategy_name 
    ON reverse_engineer_history(strategy_name);

-- ============================================
-- Add metadata column to messages table (if it doesn't exist)
-- For storing artifact data with messages
-- ============================================
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'messages' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE messages ADD COLUMN metadata JSONB;
    END IF;
END $$;

-- Index for artifact queries
DROP INDEX IF EXISTS idx_messages_metadata_has_artifacts;
CREATE INDEX idx_messages_metadata_has_artifacts 
    ON messages((metadata->>'has_artifacts')) 
    WHERE metadata IS NOT NULL;

-- ============================================
-- Row Level Security (RLS) Policies
-- Using JWT-based authentication (auth.uid())
-- ============================================

-- Enable RLS on afl_history
ALTER TABLE afl_history ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS afl_history_select_policy ON afl_history;
DROP POLICY IF EXISTS afl_history_insert_policy ON afl_history;
DROP POLICY IF EXISTS afl_history_delete_policy ON afl_history;

-- Policy: Users can only see their own AFL history
-- Using auth.uid() which works with Supabase JWT tokens
CREATE POLICY afl_history_select_policy ON afl_history
    FOR SELECT
    USING (
        user_id = auth.uid()
        OR
        -- Allow service_role to bypass (for admin operations)
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Policy: Users can only insert their own AFL history
CREATE POLICY afl_history_insert_policy ON afl_history
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        OR
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Policy: Users can only delete their own AFL history
CREATE POLICY afl_history_delete_policy ON afl_history
    FOR DELETE
    USING (
        user_id = auth.uid()
        OR
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Enable RLS on reverse_engineer_history
ALTER TABLE reverse_engineer_history ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS reverse_engineer_history_select_policy ON reverse_engineer_history;
DROP POLICY IF EXISTS reverse_engineer_history_insert_policy ON reverse_engineer_history;
DROP POLICY IF EXISTS reverse_engineer_history_delete_policy ON reverse_engineer_history;

-- Policy: Users can only see their own reverse engineer history
CREATE POLICY reverse_engineer_history_select_policy ON reverse_engineer_history
    FOR SELECT
    USING (
        user_id = auth.uid()
        OR
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Policy: Users can only insert their own reverse engineer history
CREATE POLICY reverse_engineer_history_insert_policy ON reverse_engineer_history
    FOR INSERT
    WITH CHECK (
        user_id = auth.uid()
        OR
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Policy: Users can only delete their own reverse engineer history
CREATE POLICY reverse_engineer_history_delete_policy ON reverse_engineer_history
    FOR DELETE
    USING (
        user_id = auth.uid()
        OR
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- ============================================
-- Grant Permissions (for service role and authenticated users)
-- ============================================
GRANT ALL ON afl_history TO service_role;
GRANT ALL ON reverse_engineer_history TO service_role;
GRANT SELECT, INSERT, DELETE ON afl_history TO authenticated;
GRANT SELECT, INSERT, DELETE ON reverse_engineer_history TO authenticated;

-- ============================================
-- Comments for documentation
-- ============================================
COMMENT ON TABLE afl_history IS 'Stores history of AFL code generation sessions for each user';
COMMENT ON TABLE reverse_engineer_history IS 'Stores history of reverse engineering sessions with research and schematics';
COMMENT ON COLUMN messages.metadata IS 'JSON metadata including artifact information for renderable code blocks';

-- ============================================
-- Verification Query
-- Run this to verify the tables were created successfully
-- ============================================
-- SELECT table_name, table_type 
-- FROM information_schema.tables 
-- WHERE table_schema = 'public' 
-- AND table_name IN ('afl_history', 'reverse_engineer_history');
