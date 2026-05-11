-- Migration 025: Per-conversation document RAG ("Chat with Documents")
-- =====================================================================
-- Adds a `file_chunks` table mirroring brain_chunks but scoped to
-- file_uploads.id, plus a vector-search RPC that filters by
-- conversation_id via the conversation_files junction table.
--
-- Embedding dimension: 1024 (voyage-2 / voyage-3-lite default)

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- file_chunks
-- ============================================================================
CREATE TABLE IF NOT EXISTS file_chunks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id      UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    embedding    VECTOR(1024),
    token_count  INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id ON file_chunks(file_id);
CREATE INDEX IF NOT EXISTS idx_file_chunks_embedding
    ON file_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ALTER TABLE file_chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "file_chunks_all" ON file_chunks;
CREATE POLICY "file_chunks_all" ON file_chunks FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON file_chunks TO service_role;
GRANT ALL ON file_chunks TO authenticated;

-- ============================================================================
-- match_conversation_file_chunks
-- ----------------------------------------------------------------------------
-- Vector-search across all chunks of files linked to a given conversation.
-- ============================================================================
DROP FUNCTION IF EXISTS match_conversation_file_chunks(UUID, VECTOR(1024), FLOAT, INT);

CREATE OR REPLACE FUNCTION match_conversation_file_chunks(
    p_conversation_id UUID,
    query_embedding   VECTOR(1024),
    match_threshold   FLOAT DEFAULT 0.4,
    match_count       INT   DEFAULT 8
)
RETURNS TABLE (
    chunk_id     UUID,
    file_id      UUID,
    filename     TEXT,
    chunk_index  INTEGER,
    content      TEXT,
    similarity   FLOAT
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        fc.id          AS chunk_id,
        fc.file_id,
        fu.original_filename AS filename,
        fc.chunk_index,
        fc.content,
        1 - (fc.embedding <=> query_embedding) AS similarity
    FROM file_chunks fc
    JOIN conversation_files cf ON cf.file_id = fc.file_id
    JOIN file_uploads       fu ON fu.id      = fc.file_id
    WHERE cf.conversation_id = p_conversation_id
      AND fc.embedding IS NOT NULL
      AND 1 - (fc.embedding <=> query_embedding) >= match_threshold
    ORDER BY fc.embedding <=> query_embedding
    LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_conversation_file_chunks(UUID, VECTOR(1024), FLOAT, INT)
    TO authenticated, service_role;
