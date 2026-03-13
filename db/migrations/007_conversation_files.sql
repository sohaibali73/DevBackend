-- Migration: 007_conversation_files.sql
-- Description: Add conversation_files table for chat file uploads
-- Date: 2026-02-06
-- FIX: The chat file upload endpoint writes to this table but it was never created

CREATE TABLE IF NOT EXISTS conversation_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT fk_conversation_files_conversation FOREIGN KEY (conversation_id) 
        REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversation_files_conversation 
    ON conversation_files(conversation_id, created_at DESC);

-- Enable RLS
ALTER TABLE conversation_files ENABLE ROW LEVEL SECURITY;

-- Grant permissions for service role
GRANT ALL ON conversation_files TO service_role;

COMMENT ON TABLE conversation_files IS 'Stores uploaded files attached to chat conversations';
