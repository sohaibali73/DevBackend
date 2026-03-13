-- Migration 009: Create brain tables with pgvector embeddings
-- SAFE VERSION: Drops and recreates to avoid schema conflicts
-- Run BEFORE migration 008
-- Date: 2026-02-23

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- brain_documents
-- ============================================================================
DROP TABLE IF EXISTS brain_chunks CASCADE;
DROP TABLE IF EXISTS learnings CASCADE;
DROP TABLE IF EXISTS brain_documents CASCADE;

CREATE TABLE brain_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    uploaded_by UUID,
    title VARCHAR(500) NOT NULL,
    filename VARCHAR(500),
    file_type VARCHAR(100),
    file_size BIGINT DEFAULT 0,
    category VARCHAR(100) DEFAULT 'general',
    subcategories JSONB DEFAULT '[]'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    raw_content TEXT,
    summary TEXT,
    content_hash VARCHAR(64),
    source_type VARCHAR(50) DEFAULT 'upload',
    is_processed BOOLEAN DEFAULT FALSE,
    chunk_count INTEGER DEFAULT 0,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brain_documents_uploaded_by ON brain_documents(uploaded_by);
CREATE INDEX idx_brain_documents_category ON brain_documents(category);
CREATE INDEX idx_brain_documents_content_hash ON brain_documents(content_hash);

ALTER TABLE brain_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "brain_documents_all" ON brain_documents FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON brain_documents TO service_role;
GRANT ALL ON brain_documents TO authenticated;

-- ============================================================================
-- brain_chunks with vector embeddings
-- ============================================================================
CREATE TABLE brain_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES brain_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    token_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brain_chunks_document_id ON brain_chunks(document_id);

ALTER TABLE brain_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "brain_chunks_all" ON brain_chunks FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON brain_chunks TO service_role;
GRANT ALL ON brain_chunks TO authenticated;

-- ============================================================================
-- learnings
-- ============================================================================
CREATE TABLE learnings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES brain_documents(id) ON DELETE CASCADE,
    user_id UUID,
    title VARCHAR(500),
    content TEXT,
    category VARCHAR(100) DEFAULT 'general',
    tags JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_learnings_user_id ON learnings(user_id);

ALTER TABLE learnings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "learnings_all" ON learnings FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON learnings TO service_role;
GRANT ALL ON learnings TO authenticated;

-- ============================================================================
-- Vector similarity search function
-- ============================================================================
CREATE OR REPLACE FUNCTION match_brain_chunks(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    filter_document_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index integer,
    content text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        bc.id,
        bc.document_id,
        bc.chunk_index,
        bc.content,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM brain_chunks bc
    WHERE 
        bc.embedding IS NOT NULL
        AND (filter_document_id IS NULL OR bc.document_id = filter_document_id)
        AND 1 - (bc.embedding <=> query_embedding) > match_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
