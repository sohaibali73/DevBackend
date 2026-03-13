-- ============================================================================
-- Training Data Migration
-- ============================================================================
-- This migration creates the training_data table for AI training functionality
-- and adds the is_admin column to the users table.
--
-- Run this SQL in your Supabase SQL Editor to set up the admin training feature.
-- ============================================================================

-- ============================================================================
-- 1. Add is_admin column to users table (if not exists)
-- ============================================================================

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'is_admin'
    ) THEN
        ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- ============================================================================
-- 2. Create training_data table
-- ============================================================================

CREATE TABLE IF NOT EXISTS training_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Training type: example, rule, correction, pattern, anti_pattern, terminology
    training_type VARCHAR(50) NOT NULL DEFAULT 'example',
    
    -- Title for easy identification
    title VARCHAR(255) NOT NULL,
    
    -- The input/prompt that triggers this training
    input_prompt TEXT NOT NULL,
    
    -- The expected/correct output
    expected_output TEXT NOT NULL,
    
    -- Explanation of why this is correct
    explanation TEXT DEFAULT '',
    
    -- Category for organization (afl, trading, general, etc.)
    category VARCHAR(100) DEFAULT 'afl',
    
    -- Tags for filtering (stored as JSON array)
    tags JSONB DEFAULT '[]'::jsonb,
    
    -- Priority level 1-10 (higher = more important, shown first)
    priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
    
    -- Whether this training is active
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Admin who created this training
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 3. Create indexes for better query performance
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_training_data_type ON training_data(training_type);
CREATE INDEX IF NOT EXISTS idx_training_data_category ON training_data(category);
CREATE INDEX IF NOT EXISTS idx_training_data_active ON training_data(is_active);
CREATE INDEX IF NOT EXISTS idx_training_data_priority ON training_data(priority DESC);
CREATE INDEX IF NOT EXISTS idx_training_data_created_by ON training_data(created_by);

-- Full text search index for searching training content
CREATE INDEX IF NOT EXISTS idx_training_data_search ON training_data 
    USING gin(to_tsvector('english', title || ' ' || input_prompt || ' ' || expected_output));

-- ============================================================================
-- 4. Create updated_at trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_training_data_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS training_data_updated_at ON training_data;
CREATE TRIGGER training_data_updated_at
    BEFORE UPDATE ON training_data
    FOR EACH ROW
    EXECUTE FUNCTION update_training_data_updated_at();

-- ============================================================================
-- 5. Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE training_data ENABLE ROW LEVEL SECURITY;

-- Allow all authenticated users to read active training data
CREATE POLICY "Anyone can read active training data"
    ON training_data FOR SELECT
    USING (is_active = TRUE);

-- Allow admins to do everything
CREATE POLICY "Admins can manage all training data"
    ON training_data FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM users 
            WHERE users.id = auth.uid() 
            AND users.is_admin = TRUE
        )
    );

-- ============================================================================
-- 6. Sample training data (optional - uncomment to insert)
-- ============================================================================

-- INSERT INTO training_data (training_type, title, input_prompt, expected_output, explanation, category, priority) VALUES
-- ('rule', 'Always use SetTradeDelays', 'trade timing', 'SetTradeDelays(0, 0, 0, 0); // for same bar execution', 'SetTradeDelays must be specified to avoid look-ahead bias', 'afl', 9),
-- ('rule', 'Use ExRem for signal cleanup', 'duplicate signals', 'Buy = ExRem(Buy, Sell); Sell = ExRem(Sell, Buy);', 'ExRem removes duplicate consecutive signals', 'afl', 8),
-- ('pattern', 'RSI with proper syntax', 'RSI indicator', 'rsiValue = RSI(14);  // RSI takes only period, not Close', 'RSI() only takes period as argument, not the array', 'afl', 9),
-- ('anti_pattern', 'Wrong RSI syntax', 'RSI(Close, 14)', 'RSI(14)', 'RSI does not take Close as first argument', 'afl', 9);

-- ============================================================================
-- 7. Grant permissions (adjust based on your Supabase setup)
-- ============================================================================

-- Grant usage to authenticated users
GRANT SELECT ON training_data TO authenticated;

-- Grant full access to service role (backend)
GRANT ALL ON training_data TO service_role;

-- ============================================================================
-- Done! Training data table is ready.
-- ============================================================================