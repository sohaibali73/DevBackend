-- ============================================================================
-- Migration 010: v4 Feature Tables
-- Run this in Supabase SQL Editor (Settings → SQL Editor → New query)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. AFL Feedback
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS afl_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    generation_id TEXT NOT NULL,
    feedback    TEXT NOT NULL CHECK (feedback IN ('positive', 'negative')),
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_afl_feedback_user ON afl_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_afl_feedback_gen  ON afl_feedback(generation_id);

-- RLS
ALTER TABLE afl_feedback ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own afl_feedback" ON afl_feedback;
CREATE POLICY "Users own afl_feedback" ON afl_feedback
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 2. Reverse Engineering Analyses
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reverse_analyses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    image_path  TEXT,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'processing'
                     CHECK (status IN ('processing', 'completed', 'failed')),
    progress    INT  NOT NULL DEFAULT 0,
    patterns    JSONB,
    strategy    JSONB,
    confidence  FLOAT,
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reverse_analyses_user ON reverse_analyses(user_id, created_at DESC);

ALTER TABLE reverse_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own reverse_analyses" ON reverse_analyses;
CREATE POLICY "Users own reverse_analyses" ON reverse_analyses
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 3. Application API Keys  (not Claude/Tavily — user-generated app keys)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    key_hash     TEXT NOT NULL,        -- encrypted raw key
    key_prefix   TEXT NOT NULL,        -- first 16 chars + "..." for display
    permissions  TEXT[] NOT NULL DEFAULT '{"read","write"}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_app_api_keys_user ON app_api_keys(user_id);

ALTER TABLE app_api_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own app_api_keys" ON app_api_keys;
CREATE POLICY "Users own app_api_keys" ON app_api_keys
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 4. Chat Attachments
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS attachments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    size            INT,
    mime_type       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_attachments_conv ON attachments(conversation_id);
CREATE INDEX IF NOT EXISTS idx_attachments_user ON attachments(user_id);

ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own attachments" ON attachments;
CREATE POLICY "Users own attachments" ON attachments
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 5. Tool Results  (Generative UI persistence)
--    This table may already exist from an earlier migration; CREATE IF NOT EXISTS
--    is safe to run again.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tool_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      UUID,
    tool_call_id    TEXT NOT NULL,
    tool_name       TEXT NOT NULL,
    input           JSONB NOT NULL DEFAULT '{}',
    output          JSONB DEFAULT '{}',
    state           TEXT DEFAULT 'pending'
                         CHECK (state IN ('pending', 'completed', 'error')),
    error_text      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tool_results_conv    ON tool_results(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_results_msg     ON tool_results(message_id);
CREATE INDEX IF NOT EXISTS idx_tool_results_call_id ON tool_results(tool_call_id);
-- Ensure upsert on tool_call_id works
CREATE UNIQUE INDEX IF NOT EXISTS uq_tool_results_call_id ON tool_results(tool_call_id);

ALTER TABLE tool_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users view own tool_results" ON tool_results;
DROP POLICY IF EXISTS "Users insert own tool_results" ON tool_results;
CREATE POLICY "Users view own tool_results"
    ON tool_results FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own tool_results"
    ON tool_results FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users update own tool_results"
    ON tool_results FOR UPDATE USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 6. Training Courses
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courses (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         TEXT NOT NULL,
    description   TEXT,
    level         TEXT NOT NULL DEFAULT 'beginner'
                       CHECK (level IN ('beginner', 'intermediate', 'advanced')),
    duration      INT  NOT NULL DEFAULT 60,     -- minutes
    thumbnail_url TEXT,
    lessons       JSONB NOT NULL DEFAULT '[]',  -- embedded lesson objects
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Courses are publicly readable (no user filter)
ALTER TABLE courses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone reads courses" ON courses;
CREATE POLICY "Anyone reads courses" ON courses FOR SELECT USING (true);

-- ----------------------------------------------------------------------------
-- 7. User Course Progress
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_progress (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    course_id         UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    completed_lessons TEXT[]    NOT NULL DEFAULT '{}',
    progress_percent  FLOAT     NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_user_progress_user ON user_progress(user_id);

ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own user_progress" ON user_progress;
CREATE POLICY "Users own user_progress" ON user_progress
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 8. Quizzes  (standalone records or embedded references)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quizzes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id     UUID REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id     TEXT,
    title         TEXT NOT NULL,
    passing_score FLOAT NOT NULL DEFAULT 70.0,
    questions     JSONB NOT NULL DEFAULT '[]',  -- [{id,question,options,correct_answer,explanation}]
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE quizzes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone reads quizzes" ON quizzes;
CREATE POLICY "Anyone reads quizzes" ON quizzes FOR SELECT USING (true);

-- ----------------------------------------------------------------------------
-- 9. Quiz Results
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quiz_results (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    quiz_id      UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    score        FLOAT NOT NULL,
    passed       BOOL  NOT NULL DEFAULT FALSE,
    answers      JSONB NOT NULL DEFAULT '{}',
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quiz_results_user ON quiz_results(user_id, quiz_id);

ALTER TABLE quiz_results ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users own quiz_results" ON quiz_results;
CREATE POLICY "Users own quiz_results" ON quiz_results
    FOR ALL USING (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 10. Extend user_profiles with settings JSONB column (if missing)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'user_profiles' AND column_name = 'settings'
    ) THEN
        ALTER TABLE user_profiles ADD COLUMN settings JSONB DEFAULT '{}';
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 11. Extend afl_history with feedback column (if missing)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'afl_history' AND column_name = 'feedback'
    ) THEN
        ALTER TABLE afl_history ADD COLUMN feedback TEXT;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 12. Extend afl_codes with feedback column (if missing)
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'afl_codes' AND column_name = 'feedback'
    ) THEN
        ALTER TABLE afl_codes ADD COLUMN feedback TEXT;
    END IF;
END $$;

-- ============================================================================
-- Done — 12 tables / column additions applied.
-- ============================================================================
