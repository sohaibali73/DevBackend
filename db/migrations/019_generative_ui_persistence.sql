-- ============================================================================
-- MIGRATION 019: Generative UI Persistence
-- ============================================================================
-- Purpose: Enable full rehydration of Generative UI cards (file download cards,
--          stock charts, research panels, etc.) when users return to conversations.
--
-- Changes:
--   1. generated_files  — new table (code in file_store.py already writes here
--                          but the table was never created via migration)
--   2. tool_results     — new table: one row per tool invocation; stores the
--                          rich output data used to render Generative UI cards
--   3. messages.parts   — new top-level JSONB column for AI SDK parts array
--                          (was previously buried inside metadata.parts)
--   4. Storage bucket   — "generated-files" bucket for AI-generated downloads
--   5. RLS & Indexes
-- ============================================================================

-- ============================================================================
-- SECTION 1: generated_files TABLE
-- ============================================================================
-- file_store.py already calls:
--   db.table("generated_files").upsert(record, on_conflict="file_id").execute()
-- with fields: file_id, filename, file_type, size_kb, tool_name, storage_path
--
-- This table finally creates that table so upserts no longer fail silently.
-- ============================================================================

CREATE TABLE IF NOT EXISTS generated_files (
    -- Internal surrogate key
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- App-side file identifier — used in download URLs: /files/{file_id}/download
    -- file_store.py uses this as the upsert conflict target
    file_id         TEXT        NOT NULL,

    -- Optional ownership (file_store.py runs in a background thread without
    -- user context, so these may be NULL for tool-generated files)
    user_id         UUID        REFERENCES user_profiles(id) ON DELETE SET NULL,

    -- Link to the tool_results row that produced this file (set after table exists)
    tool_result_id  UUID,       -- FK added below once tool_results is created

    -- File metadata
    filename        TEXT        NOT NULL,
    file_type       TEXT        NOT NULL,   -- docx, pptx, xlsx, pdf, csv, etc.
    size_kb         FLOAT       DEFAULT 0,
    tool_name       TEXT        DEFAULT '',

    -- Storage
    storage_path    TEXT,                   -- Supabase Storage path: {file_id}/{filename}
    download_url    TEXT,                   -- Optional cached public/signed URL

    -- Lifecycle
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT generated_files_file_id_unique UNIQUE (file_id)
);

CREATE INDEX IF NOT EXISTS idx_generated_files_file_id
    ON generated_files(file_id);

CREATE INDEX IF NOT EXISTS idx_generated_files_user_id
    ON generated_files(user_id);

CREATE INDEX IF NOT EXISTS idx_generated_files_tool_name
    ON generated_files(tool_name);

CREATE INDEX IF NOT EXISTS idx_generated_files_created_at
    ON generated_files(created_at DESC);


-- ============================================================================
-- SECTION 2: tool_results TABLE
-- ============================================================================
-- One row per tool invocation. Stores the rich output that the frontend needs
-- to reconstruct Generative UI cards without re-running the tool.
--
-- Linked to messages.id after the assistant message is persisted (message_id
-- starts NULL and is backfilled by chat.py after saving the assistant row).
-- ============================================================================

CREATE TABLE IF NOT EXISTS tool_results (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership
    user_id         UUID        REFERENCES user_profiles(id) ON DELETE CASCADE,
    conversation_id UUID        REFERENCES conversations(id) ON DELETE CASCADE,

    -- Linked to the assistant message that contains this tool invocation.
    -- Set by chat.py after the assistant message row is created.
    -- Not a hard FK so the INSERT ordering doesn't matter.
    message_id      UUID,

    -- AI SDK stream identifiers
    tool_call_id    TEXT        NOT NULL,   -- e.g. "toolu_01AbCd…"
    tool_name       TEXT        NOT NULL,   -- e.g. "invoke_skill", "web_search"

    -- Payload
    input           JSONB       NOT NULL DEFAULT '{}',
    output          JSONB,       -- The rich structured result (file info, chart data, etc.)

    -- Execution state
    state           TEXT        NOT NULL DEFAULT 'completed'
                    CHECK (state IN ('pending', 'completed', 'error')),
    error_text      TEXT,

    -- Timestamps
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_results_conversation
    ON tool_results(conversation_id);

CREATE INDEX IF NOT EXISTS idx_tool_results_message
    ON tool_results(message_id);

CREATE INDEX IF NOT EXISTS idx_tool_results_tool_call
    ON tool_results(tool_call_id);

CREATE INDEX IF NOT EXISTS idx_tool_results_user
    ON tool_results(user_id);

CREATE INDEX IF NOT EXISTS idx_tool_results_tool_name
    ON tool_results(tool_name);

CREATE INDEX IF NOT EXISTS idx_tool_results_created_at
    ON tool_results(created_at DESC);


-- ============================================================================
-- Back-reference: generated_files → tool_results
-- ============================================================================
-- Add the FK now that both tables exist.

ALTER TABLE generated_files
    ADD COLUMN IF NOT EXISTS _tr_fk_placeholder BOOLEAN;  -- placeholder to avoid error if col exists

-- Drop the placeholder immediately (ALTER TABLE ADD COLUMN IF NOT EXISTS
-- is fine, but we use a real column):
ALTER TABLE generated_files
    DROP COLUMN IF EXISTS _tr_fk_placeholder;

DO $$
BEGIN
    -- Only add the FK column if it doesn't exist yet
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'generated_files' AND column_name = 'tool_result_id'
    ) THEN
        ALTER TABLE generated_files
            ADD COLUMN tool_result_id UUID REFERENCES tool_results(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_generated_files_tool_result
    ON generated_files(tool_result_id)
    WHERE tool_result_id IS NOT NULL;


-- ============================================================================
-- updated_at trigger for tool_results
-- ============================================================================
-- Reuse the existing update_updated_at() function from migration 001.

DROP TRIGGER IF EXISTS update_tool_results_updated_at ON tool_results;
CREATE TRIGGER update_tool_results_updated_at
    BEFORE UPDATE ON tool_results
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();


-- ============================================================================
-- SECTION 3: messages.parts column
-- ============================================================================
-- Top-level JSONB column for the AI SDK v4 parts array.
-- Previously stored inside metadata.parts (still kept there for backwards
-- compatibility with any clients reading the old location).
--
-- Format: [{ "type": "text", "text": "..." }, { "type": "tool-invocation", ... }]
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'parts'
    ) THEN
        ALTER TABLE messages ADD COLUMN parts JSONB;
        COMMENT ON COLUMN messages.parts IS
            'AI SDK v4 message parts array. '
            'Format: [{type:"text",text:"..."},{type:"tool-invocation",toolCallId:"...",toolName:"...",state:"result",result:{...}}]. '
            'Enables frontend to reconstruct Generative UI cards from conversation history.';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_messages_parts
    ON messages USING GIN(parts)
    WHERE parts IS NOT NULL;


-- ============================================================================
-- SECTION 4: Supabase Storage bucket for generated files
-- ============================================================================
-- A dedicated bucket keeps AI-generated downloads separate from user uploads.
-- file_store.py currently uses the "user-uploads" bucket; future code can
-- write here instead via the GENERATED_FILES_BUCKET env var.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'generated-files',
    'generated-files',
    false,
    104857600,   -- 100 MB limit
    ARRAY[
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/pdf',
        'text/csv',
        'application/json',
        'text/plain',
        'image/png',
        'image/jpeg'
    ]
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================================
-- SECTION 5: Row Level Security
-- ============================================================================

ALTER TABLE generated_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_results     ENABLE ROW LEVEL SECURITY;

-- ── generated_files ──────────────────────────────────────────────────────────

-- service_role bypasses RLS entirely (already true, but explicit is clearer)
DROP POLICY IF EXISTS "generated_files_service_role_all" ON generated_files;
CREATE POLICY "generated_files_service_role_all"
    ON generated_files FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Authenticated users can read files they own OR unowned files
-- (file_store.py background thread has no user context → user_id IS NULL)
DROP POLICY IF EXISTS "generated_files_user_select" ON generated_files;
CREATE POLICY "generated_files_user_select"
    ON generated_files FOR SELECT
    TO authenticated
    USING (user_id IS NULL OR user_id = auth.uid());

-- Authenticated users can insert rows they own or unowned rows
DROP POLICY IF EXISTS "generated_files_user_insert" ON generated_files;
CREATE POLICY "generated_files_user_insert"
    ON generated_files FOR INSERT
    TO authenticated
    WITH CHECK (user_id IS NULL OR user_id = auth.uid());

-- Allow update only on own rows (or unowned)
DROP POLICY IF EXISTS "generated_files_user_update" ON generated_files;
CREATE POLICY "generated_files_user_update"
    ON generated_files FOR UPDATE
    TO authenticated
    USING  (user_id IS NULL OR user_id = auth.uid())
    WITH CHECK (user_id IS NULL OR user_id = auth.uid());


-- ── tool_results ──────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "tool_results_service_role_all" ON tool_results;
CREATE POLICY "tool_results_service_role_all"
    ON tool_results FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "tool_results_user_all" ON tool_results;
CREATE POLICY "tool_results_user_all"
    ON tool_results FOR ALL
    TO authenticated
    USING  (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());


-- ── Storage: generated-files bucket ──────────────────────────────────────────

-- Service role already has full access.
-- Allow authenticated users to download their own generated files.
DROP POLICY IF EXISTS "generated_files_bucket_user_select" ON storage.objects;
CREATE POLICY "generated_files_bucket_user_select"
    ON storage.objects FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'generated-files'
        AND (storage.foldername(name))[1] IN (
            SELECT file_id FROM generated_files WHERE user_id = auth.uid()
        )
    );


-- ============================================================================
-- SECTION 6: Grants
-- ============================================================================

GRANT ALL ON generated_files TO service_role;
GRANT ALL ON tool_results     TO service_role;

GRANT SELECT, INSERT, UPDATE ON generated_files TO authenticated;
GRANT SELECT, INSERT, UPDATE ON tool_results     TO authenticated;


-- ============================================================================
-- SECTION 7: Comments
-- ============================================================================

COMMENT ON TABLE generated_files IS
    'Metadata for every AI-generated file (DOCX, PPTX, XLSX, PDF, CSV). '
    'Actual bytes live in Supabase Storage bucket "user-uploads" at path '
    '{file_id}/{filename} (or "generated-files" for new uploads). '
    'Referenced by core/file_store.py which upserts on conflict(file_id).';

COMMENT ON TABLE tool_results IS
    'One row per tool call executed during a chat turn. '
    'Stores the structured output (presentations, charts, research data) '
    'so the frontend can reconstruct Generative UI cards when revisiting '
    'a conversation without re-running the tool. '
    'message_id is backfilled by chat.py after the assistant message is saved.';


-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    gf_count  INTEGER;
    tr_count  INTEGER;
    parts_col TEXT;
BEGIN
    SELECT COUNT(*) INTO gf_count FROM information_schema.tables
        WHERE table_name = 'generated_files' AND table_schema = 'public';

    SELECT COUNT(*) INTO tr_count FROM information_schema.tables
        WHERE table_name = 'tool_results' AND table_schema = 'public';

    SELECT column_name INTO parts_col FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'parts';

    RAISE NOTICE '✓ Migration 019 complete — generated_files: %, tool_results: %, messages.parts: %',
        gf_count, tr_count, COALESCE(parts_col, 'MISSING');
END $$;
