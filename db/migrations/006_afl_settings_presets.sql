-- Migration: AFL Settings Presets Table
-- Description: Stores user backtest settings presets for AFL generation
-- Created: 2026-01-30

-- Create afl_settings_presets table
CREATE TABLE IF NOT EXISTS afl_settings_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}',
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_afl_settings_presets_user_id 
    ON afl_settings_presets(user_id);

CREATE INDEX IF NOT EXISTS idx_afl_settings_presets_is_default 
    ON afl_settings_presets(user_id, is_default) 
    WHERE is_default = TRUE;

-- Enable RLS
ALTER TABLE afl_settings_presets ENABLE ROW LEVEL SECURITY;

-- RLS Policies
-- Users can only see their own presets
CREATE POLICY "Users can view own settings presets"
    ON afl_settings_presets FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own presets
CREATE POLICY "Users can create own settings presets"
    ON afl_settings_presets FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own presets
CREATE POLICY "Users can update own settings presets"
    ON afl_settings_presets FOR UPDATE
    USING (auth.uid() = user_id);

-- Users can delete their own presets
CREATE POLICY "Users can delete own settings presets"
    ON afl_settings_presets FOR DELETE
    USING (auth.uid() = user_id);

-- Grant permissions
GRANT ALL ON afl_settings_presets TO authenticated;
GRANT ALL ON afl_settings_presets TO service_role;

-- Add comment for documentation
COMMENT ON TABLE afl_settings_presets IS 'Stores user backtest settings presets for AFL code generation';
COMMENT ON COLUMN afl_settings_presets.settings IS 'JSONB containing backtest settings: initial_equity, position_size, position_size_type, max_positions, commission, trade_delays, margin_requirement';
COMMENT ON COLUMN afl_settings_presets.is_default IS 'If true, this preset is auto-loaded when user opens AFL Generator';
