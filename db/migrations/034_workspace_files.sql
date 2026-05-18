-- Migration: 034_workspace_files.sql
-- Description: Per-conversation IDE workspace. One row per file authored by
--              the agent (or edited by the user) inside a conversation's
--              persistent code panel. Supabase is the source of truth; the
--              sandbox dir is a derived working copy populated at execute
--              time.
-- Date: 2026-05-17

CREATE TABLE IF NOT EXISTS workspace_files (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL,
    user_id         UUID NOT NULL,
    filename        TEXT NOT NULL,
    -- Language hint for syntax highlighting / sandbox selection.
    -- One of: 'python' | 'javascript' | 'typescript' | 'afl' | 'sql' |
    --         'json' | 'yaml' | 'markdown' | 'text'
    language        TEXT NOT NULL DEFAULT 'python',
    content         TEXT NOT NULL DEFAULT '',
    -- Bumped on every write; lets the IDE detect external changes.
    version         INTEGER NOT NULL DEFAULT 1,
    -- Who/what last wrote: 'agent' | 'user' | 'system'
    last_author     TEXT NOT NULL DEFAULT 'agent',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_workspace_files_conversation
        FOREIGN KEY (conversation_id)
        REFERENCES conversations(id) ON DELETE CASCADE,
    CONSTRAINT fk_workspace_files_user
        FOREIGN KEY (user_id)
        REFERENCES user_profiles(id) ON DELETE CASCADE,
    CONSTRAINT uq_workspace_files_conv_filename
        UNIQUE (conversation_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_workspace_files_conversation
    ON workspace_files(conversation_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_files_user
    ON workspace_files(user_id);

-- Maintain updated_at automatically on row updates.
CREATE OR REPLACE FUNCTION workspace_files_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_workspace_files_touch ON workspace_files;
CREATE TRIGGER trg_workspace_files_touch
    BEFORE UPDATE ON workspace_files
    FOR EACH ROW EXECUTE FUNCTION workspace_files_touch_updated_at();

ALTER TABLE workspace_files ENABLE ROW LEVEL SECURITY;

GRANT ALL ON workspace_files TO service_role;

COMMENT ON TABLE workspace_files IS
    'Per-conversation code files surfaced in the IDE panel. One file per (conversation, filename). Agent and user both read/write.';
