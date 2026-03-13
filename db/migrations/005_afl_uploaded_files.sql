-- Migration: 005_afl_uploaded_files.sql
-- Description: Add uploaded files table for AFL Generator file context
-- Date: 2026-01-30

-- ============================================
-- AFL Uploaded Files Table
-- Stores uploaded files for AFL generation context
-- ============================================
CREATE TABLE IF NOT EXISTS afl_uploaded_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key to users table
    CONSTRAINT fk_afl_uploaded_files_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

-- Index for fast user file queries
CREATE INDEX IF NOT EXISTS idx_afl_uploaded_files_user 
    ON afl_uploaded_files(user_id, created_at DESC);

-- Index for filename searches within user
CREATE INDEX IF NOT EXISTS idx_afl_uploaded_files_filename 
    ON afl_uploaded_files(user_id, filename);

-- Index for content type filtering
CREATE INDEX IF NOT EXISTS idx_afl_uploaded_files_content_type 
    ON afl_uploaded_files(content_type);

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================

-- Enable RLS on afl_uploaded_files
ALTER TABLE afl_uploaded_files ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own uploaded files
CREATE POLICY afl_uploaded_files_select_policy ON afl_uploaded_files
    FOR SELECT
    USING (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only insert their own files
CREATE POLICY afl_uploaded_files_insert_policy ON afl_uploaded_files
    FOR INSERT
    WITH CHECK (user_id = current_setting('app.current_user_id', true));

-- Policy: Users can only delete their own files
CREATE POLICY afl_uploaded_files_delete_policy ON afl_uploaded_files
    FOR DELETE
    USING (user_id = current_setting('app.current_user_id', true));

-- ============================================
-- Grant Permissions (for service role)
-- ============================================
GRANT ALL ON afl_uploaded_files TO service_role;

-- ============================================
-- Comments for documentation
-- ============================================
COMMENT ON TABLE afl_uploaded_files IS 'Stores uploaded files (CSV, TXT, PDF, AFL) for AFL code generation context';
COMMENT ON COLUMN afl_uploaded_files.file_data IS 'JSON object containing text_content, preview, or base64_content for PDFs';
COMMENT ON COLUMN afl_uploaded_files.content_type IS 'MIME type of the uploaded file';
