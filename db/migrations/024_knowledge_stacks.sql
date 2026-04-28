-- ===========================================================================
-- 024_knowledge_stacks.sql — Msty-style Knowledge Stacks
-- ===========================================================================
-- Adds the concept of "Knowledge Stacks" — named, configurable collections
-- of brain_documents that the user can selectively attach to chats for RAG.
--
-- A Stack owns its own RAG settings (chunk_size, chunk_count, overlap,
-- load_mode) so different stacks can use different retrieval strategies.
--
-- Idempotent: safe to re-run.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS knowledge_stacks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    icon            TEXT NOT NULL DEFAULT '📚',
    color           TEXT NOT NULL DEFAULT '#6366f1',
    settings        JSONB NOT NULL DEFAULT
                      '{"chunk_size":1500,"chunk_count":20,"overlap":150,"load_mode":"static","generate_embeddings":true}'::jsonb,
    document_count  INTEGER NOT NULL DEFAULT 0,
    total_chunks    INTEGER NOT NULL DEFAULT 0,
    total_size_bytes BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Each user can only have one stack with the same name
CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_stacks_user_name
    ON knowledge_stacks(user_id, name);

CREATE INDEX IF NOT EXISTS idx_knowledge_stacks_user_id
    ON knowledge_stacks(user_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_stacks_updated_at
    ON knowledge_stacks(updated_at DESC);

-- ---------------------------------------------------------------------------
-- Wire stacks to brain_documents (nullable — backward compatible)
-- ---------------------------------------------------------------------------

ALTER TABLE brain_documents
    ADD COLUMN IF NOT EXISTS stack_id UUID
        REFERENCES knowledge_stacks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_brain_documents_stack_id
    ON brain_documents(stack_id);

CREATE INDEX IF NOT EXISTS idx_brain_documents_uploaded_by_stack
    ON brain_documents(uploaded_by, stack_id);

-- ---------------------------------------------------------------------------
-- Stats trigger — keep document_count / total_chunks / total_size in sync
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION refresh_knowledge_stack_stats(p_stack_id UUID)
RETURNS VOID AS $$
BEGIN
    IF p_stack_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE knowledge_stacks ks
    SET
        document_count = COALESCE(s.doc_count, 0),
        total_chunks = COALESCE(s.chunk_total, 0),
        total_size_bytes = COALESCE(s.size_total, 0),
        updated_at = NOW()
    FROM (
        SELECT
            COUNT(*) AS doc_count,
            COALESCE(SUM(chunk_count), 0) AS chunk_total,
            COALESCE(SUM(file_size), 0) AS size_total
        FROM brain_documents
        WHERE stack_id = p_stack_id
    ) s
    WHERE ks.id = p_stack_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_brain_documents_stack_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Refresh stats for the OLD stack (if doc was reassigned/deleted)
    IF TG_OP IN ('UPDATE', 'DELETE') AND OLD.stack_id IS NOT NULL THEN
        PERFORM refresh_knowledge_stack_stats(OLD.stack_id);
    END IF;

    -- Refresh stats for the NEW stack (if doc was added/reassigned)
    IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.stack_id IS NOT NULL THEN
        PERFORM refresh_knowledge_stack_stats(NEW.stack_id);
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS brain_documents_stack_stats ON brain_documents;
CREATE TRIGGER brain_documents_stack_stats
    AFTER INSERT OR UPDATE OR DELETE ON brain_documents
    FOR EACH ROW EXECUTE FUNCTION trg_brain_documents_stack_stats();

-- ---------------------------------------------------------------------------
-- Stack-scoped vector search RPC
-- ---------------------------------------------------------------------------
-- Returns top-K most-similar chunks WITHIN a specific stack.
-- Falls back gracefully if pgvector / embeddings are not available — the
-- application layer detects an empty result and switches to text search.

-- Drop first in case a previous run created it with a different signature
DROP FUNCTION IF EXISTS match_stack_chunks(UUID, VECTOR(1024), FLOAT, INT);
DROP FUNCTION IF EXISTS match_stack_chunks(UUID, VECTOR, FLOAT, INT);

CREATE OR REPLACE FUNCTION match_stack_chunks(
    p_stack_id UUID,
    query_embedding VECTOR(1024),
    match_threshold FLOAT DEFAULT 0.5,
    match_count INT DEFAULT 20
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    chunk_index INT,
    content TEXT,
    similarity FLOAT
)
LANGUAGE SQL
STABLE
AS $$
    SELECT
        bc.id AS chunk_id,
        bc.document_id,
        bc.chunk_index,
        bc.content,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM brain_chunks bc
    JOIN brain_documents bd ON bd.id = bc.document_id
    WHERE bd.stack_id = p_stack_id
      AND bc.embedding IS NOT NULL
      AND 1 - (bc.embedding <=> query_embedding) >= match_threshold
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ---------------------------------------------------------------------------
-- Auto-update updated_at on stack changes
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION trg_knowledge_stacks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS knowledge_stacks_updated_at ON knowledge_stacks;
CREATE TRIGGER knowledge_stacks_updated_at
    BEFORE UPDATE ON knowledge_stacks
    FOR EACH ROW EXECUTE FUNCTION trg_knowledge_stacks_updated_at();
