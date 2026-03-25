-- Migration 016: Fix brain_chunks schema cache + storage_path column
-- Fixes:
--   1. PGRST204: brain_chunks.chunk_index not in PostgREST schema cache
--   2. brain_documents missing storage_path column (or NULL constraint issues)
--
-- Run in Supabase SQL Editor:
--   Dashboard → SQL Editor → Paste this → Run

-- ============================================================================
-- 1. Ensure storage_path exists on brain_documents (safe, idempotent)
-- ============================================================================
ALTER TABLE brain_documents
    ADD COLUMN IF NOT EXISTS storage_path TEXT DEFAULT '';

-- ============================================================================
-- 2. Drop + recreate brain_chunks so PostgREST picks up all columns fresh
--    (This is the safest fix for PGRST204 schema cache issues)
-- ============================================================================
DROP TABLE IF EXISTS brain_chunks CASCADE;

CREATE TABLE brain_chunks (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID        NOT NULL REFERENCES brain_documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER     NOT NULL DEFAULT 0,
    content      TEXT        NOT NULL,
    embedding    vector(1536),
    token_count  INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brain_chunks_document_id ON brain_chunks(document_id);
CREATE INDEX idx_brain_chunks_chunk_index ON brain_chunks(document_id, chunk_index);

ALTER TABLE brain_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "brain_chunks_all" ON brain_chunks
    FOR ALL
    USING (true)
    WITH CHECK (true);

GRANT ALL ON brain_chunks TO service_role;
GRANT ALL ON brain_chunks TO authenticated;
GRANT ALL ON brain_chunks TO anon;

-- ============================================================================
-- 3. Force PostgREST to reload its schema cache immediately
-- ============================================================================
NOTIFY pgrst, 'reload schema';

-- ============================================================================
-- 4. Verify
-- ============================================================================
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name IN ('brain_chunks', 'brain_documents')
  AND column_name IN ('chunk_index', 'storage_path')
ORDER BY table_name, column_name;
