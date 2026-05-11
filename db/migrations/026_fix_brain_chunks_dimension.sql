-- =====================================================================
-- Migration 026: Fix brain_chunks dimension + add user-scoped RAG RPC
-- =====================================================================
-- Why:
--   * brain_chunks.embedding was vector(1536) (OpenAI dims) but the app
--     uses Voyage voyage-2 which outputs 1024 dims, so every embedding
--     insert was silently failing.
--   * No KB-RAG RPC scoped to the current user existed, so chat.py
--     couldn't safely retrieve KB chunks during a chat turn.
--
-- WARNING: drops + recreates brain_chunks. Existing chunks/embeddings
-- will be wiped. Re-run KB processing (re-upload or scripts/bulk_kb_upload.py)
-- to repopulate.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- 1. Recreate brain_chunks at vector(1024) to match voyage-2
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS brain_chunks CASCADE;

CREATE TABLE brain_chunks (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID        NOT NULL REFERENCES brain_documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER     NOT NULL DEFAULT 0,
    content      TEXT        NOT NULL,
    embedding    vector(1024),
    token_count  INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brain_chunks_document_id ON brain_chunks(document_id);
CREATE INDEX idx_brain_chunks_chunk_index ON brain_chunks(document_id, chunk_index);
CREATE INDEX idx_brain_chunks_embedding
    ON brain_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ALTER TABLE brain_chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "brain_chunks_all" ON brain_chunks;
CREATE POLICY "brain_chunks_all" ON brain_chunks
    FOR ALL USING (true) WITH CHECK (true);

GRANT ALL ON brain_chunks TO service_role;
GRANT ALL ON brain_chunks TO authenticated;
GRANT ALL ON brain_chunks TO anon;

-- ---------------------------------------------------------------------
-- 2. Drop old (1536-dim) RPC variants, then recreate at 1024 dims
--    with optional user filter and an optional category filter.
-- ---------------------------------------------------------------------
DROP FUNCTION IF EXISTS match_brain_chunks(vector, float, int, uuid);
DROP FUNCTION IF EXISTS match_brain_chunks(vector(1536), float, int, uuid);
DROP FUNCTION IF EXISTS match_brain_chunks(vector(1024), float, int, uuid);
DROP FUNCTION IF EXISTS match_brain_chunks(vector(1024), float, int, uuid, text);

CREATE OR REPLACE FUNCTION match_brain_chunks(
    query_embedding   vector(1024),
    match_threshold   float DEFAULT 0.4,
    match_count       int   DEFAULT 8,
    p_user_id         uuid  DEFAULT NULL,
    p_category        text  DEFAULT NULL
)
RETURNS TABLE (
    chunk_id     uuid,
    document_id  uuid,
    title        text,
    filename     text,
    category     text,
    chunk_index  integer,
    content      text,
    similarity   float
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        bc.id                       AS chunk_id,
        bc.document_id,
        bd.title::text              AS title,
        bd.filename::text           AS filename,
        bd.category::text           AS category,
        bc.chunk_index,
        bc.content,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM brain_chunks bc
    JOIN brain_documents bd ON bd.id = bc.document_id
    WHERE bc.embedding IS NOT NULL
      AND (p_user_id  IS NULL OR bd.uploaded_by = p_user_id)
      AND (p_category IS NULL OR bd.category    = p_category)
      AND 1 - (bc.embedding <=> query_embedding) >= match_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
$$;

GRANT EXECUTE ON FUNCTION match_brain_chunks(vector(1024), float, int, uuid, text)
    TO authenticated, service_role, anon;

-- ---------------------------------------------------------------------
-- 3. Tell PostgREST to refresh its schema cache
-- ---------------------------------------------------------------------
NOTIFY pgrst, 'reload schema';

-- ---------------------------------------------------------------------
-- 4. Sanity check
-- ---------------------------------------------------------------------
SELECT
    a.attname        AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
WHERE c.relname = 'brain_chunks'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
