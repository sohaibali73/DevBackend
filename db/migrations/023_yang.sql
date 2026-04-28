-- ============================================================================
-- Migration 023: YANG Advanced Features
-- Tables: user_yang_settings, conversation_focus, yang_checkpoints
-- ============================================================================
-- Idempotent: safe to re-run. Uses IF NOT EXISTS / CREATE OR REPLACE.
-- Run in Supabase SQL Editor or via psql.
-- ============================================================================

BEGIN;

-- ────────────────────────────────────────────────────────────────────────────
-- Shared: reusable updated_at trigger function (no-op if already exists)
-- ────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. user_yang_settings — per-user feature toggles
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_yang_settings (
    user_id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    subagents        BOOLEAN NOT NULL DEFAULT true,
    parallel_tools   BOOLEAN NOT NULL DEFAULT true,
    plan_mode        BOOLEAN NOT NULL DEFAULT false,
    tool_search      BOOLEAN NOT NULL DEFAULT true,
    auto_compact     BOOLEAN NOT NULL DEFAULT true,
    focus_chain      BOOLEAN NOT NULL DEFAULT true,
    background_edit  BOOLEAN NOT NULL DEFAULT false,
    checkpoints      BOOLEAN NOT NULL DEFAULT true,
    yolo_mode        BOOLEAN NOT NULL DEFAULT false,
    double_check     BOOLEAN NOT NULL DEFAULT false,
    advanced         JSONB   NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_yang_settings IS
    'Per-user toggles for YANG advanced agentic features. '
    'Defaults tuned so the typical user gets safe behaviour out of the box.';

ALTER TABLE user_yang_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS yang_settings_owner        ON user_yang_settings;
DROP POLICY IF EXISTS yang_settings_service_role ON user_yang_settings;

CREATE POLICY yang_settings_owner
    ON user_yang_settings FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY yang_settings_service_role
    ON user_yang_settings FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS trg_user_yang_settings_updated_at ON user_yang_settings;
CREATE TRIGGER trg_user_yang_settings_updated_at
    BEFORE UPDATE ON user_yang_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON user_yang_settings TO authenticated;
GRANT ALL                           ON user_yang_settings TO service_role;

-- ============================================================================
-- 2. conversation_focus — per-conversation focus chain
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_focus (
    conversation_id         UUID PRIMARY KEY
                                REFERENCES conversations(id) ON DELETE CASCADE,
    user_id                 UUID NOT NULL,
    focus                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    turns_since_llm_polish  INT  NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE conversation_focus IS
    'Rolling focus chain per conversation: goal, open tasks, key files, '
    'decisions. Updated deterministically each turn; optionally LLM-polished '
    'every 5 turns in the background.';

CREATE INDEX IF NOT EXISTS idx_conversation_focus_user
    ON conversation_focus(user_id);

ALTER TABLE conversation_focus ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS focus_owner        ON conversation_focus;
DROP POLICY IF EXISTS focus_service_role ON conversation_focus;

CREATE POLICY focus_owner
    ON conversation_focus FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY focus_service_role
    ON conversation_focus FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS trg_conversation_focus_updated_at ON conversation_focus;
CREATE TRIGGER trg_conversation_focus_updated_at
    BEFORE UPDATE ON conversation_focus
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_focus TO authenticated;
GRANT ALL                           ON conversation_focus TO service_role;

-- ============================================================================
-- 3. yang_checkpoints — rollback points for conversations
-- ============================================================================
CREATE TABLE IF NOT EXISTS yang_checkpoints (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL
                         REFERENCES conversations(id) ON DELETE CASCADE,
    user_id          UUID NOT NULL,
    label            TEXT,
    trigger          TEXT NOT NULL DEFAULT 'manual',
                     -- 'manual' | 'pre_yolo' | 'pre_destructive' | 'auto'
    last_message_id  UUID,
                     -- high-water mark; restore deletes messages with
                     -- created_at > this message's created_at
    focus_snapshot   JSONB,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE yang_checkpoints IS
    'Rollback points. Restoring a checkpoint deletes messages newer than '
    'last_message_id and restores focus_snapshot. Generated files are NOT '
    'deleted — user is warned they persist on disk.';

CREATE INDEX IF NOT EXISTS idx_yang_checkpoints_conversation
    ON yang_checkpoints(conversation_id);
CREATE INDEX IF NOT EXISTS idx_yang_checkpoints_user
    ON yang_checkpoints(user_id);
CREATE INDEX IF NOT EXISTS idx_yang_checkpoints_created
    ON yang_checkpoints(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_yang_checkpoints_trigger
    ON yang_checkpoints(trigger);

ALTER TABLE yang_checkpoints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ckpt_owner        ON yang_checkpoints;
DROP POLICY IF EXISTS ckpt_service_role ON yang_checkpoints;

CREATE POLICY ckpt_owner
    ON yang_checkpoints FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY ckpt_service_role
    ON yang_checkpoints FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON yang_checkpoints TO authenticated;
GRANT ALL                           ON yang_checkpoints TO service_role;

-- ============================================================================
-- Verification
-- ============================================================================
DO $$
DECLARE
    yang_count  INT;
    focus_count INT;
    ckpt_count  INT;
BEGIN
    SELECT COUNT(*) INTO yang_count  FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'user_yang_settings';
    SELECT COUNT(*) INTO focus_count FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'conversation_focus';
    SELECT COUNT(*) INTO ckpt_count  FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'yang_checkpoints';

    RAISE NOTICE '✓ Migration 023 complete — user_yang_settings: %, conversation_focus: %, yang_checkpoints: %',
        yang_count, focus_count, ckpt_count;
END $$;

COMMIT;
