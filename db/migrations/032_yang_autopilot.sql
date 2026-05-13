-- ============================================================================
-- Migration 032: YANG Autopilot (Goals + Memory + Schedules)
-- ============================================================================
-- Idempotent: safe to re-run.
-- Run in the Supabase SQL Editor (paste this whole file).
--
-- Tables created:
--   * goals               — long-running autonomous goals
--   * goal_steps          — append-only event log per goal (plan/thought/tool-…)
--   * memories            — long-term embedded memory store
--   * scheduled_jobs      — cron-driven goal spawners
--
-- Notes:
--   * user_id is UUID (matches auth.users) — the recipe uses BIGINT but this
--     codebase uses Supabase auth UUIDs everywhere; switched for consistency.
--   * goals.id is UUID (not BIGSERIAL) for the same reason.
--   * Memory embedding dimension matches the rest of the codebase (Voyage-2,
--     1024 dims) — change the column if you switch embedding providers.
-- ============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- Shared updated_at trigger function (no-op if already exists from migration 023)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 1. goals
-- ============================================================================
CREATE TABLE IF NOT EXISTS goals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title            TEXT NOT NULL,
    description      TEXT,
    prompt           TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued',
        -- queued | running | waiting_for_input | paused | done | failed | cancelled
    plan_jsonb       JSONB,
    conversation_id  UUID,
        -- chat that spawned the goal (optional, no FK so a deleted chat
        -- doesn't take its goals with it).
    last_note        TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS goals_user_status_idx ON goals(user_id, status);
CREATE INDEX IF NOT EXISTS goals_user_created_idx ON goals(user_id, created_at DESC);

ALTER TABLE goals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS goals_owner        ON goals;
DROP POLICY IF EXISTS goals_service_role ON goals;

CREATE POLICY goals_owner
    ON goals FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY goals_service_role
    ON goals FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS trg_goals_updated_at ON goals;
CREATE TRIGGER trg_goals_updated_at
    BEFORE UPDATE ON goals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON goals TO authenticated;
GRANT ALL                           ON goals TO service_role;


-- ============================================================================
-- 2. goal_steps
-- ============================================================================
CREATE TABLE IF NOT EXISTS goal_steps (
    id          BIGSERIAL PRIMARY KEY,
    goal_id     UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,
        -- denormalised for RLS; mirrors goals.user_id.
    idx         INT NOT NULL,
        -- 0-based step number within the goal. Loosely ordered — multiple
        -- rows can share an idx (e.g. tool-call + tool-result emitted in
        -- the same agent turn) and the SSE consumer sorts by (idx, id).
    kind        TEXT NOT NULL,
        -- plan | thought | tool-call | tool-result | note | done | error
    content     JSONB NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS goal_steps_goal_idx ON goal_steps(goal_id, idx);
CREATE INDEX IF NOT EXISTS goal_steps_goal_ts  ON goal_steps(goal_id, ts);

ALTER TABLE goal_steps ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS goal_steps_owner        ON goal_steps;
DROP POLICY IF EXISTS goal_steps_service_role ON goal_steps;

CREATE POLICY goal_steps_owner
    ON goal_steps FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY goal_steps_service_role
    ON goal_steps FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON goal_steps TO authenticated;
GRANT USAGE, SELECT                  ON SEQUENCE goal_steps_id_seq TO authenticated;
GRANT ALL                            ON goal_steps TO service_role;


-- ============================================================================
-- 3. memories
-- ============================================================================
CREATE TABLE IF NOT EXISTS memories (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'fact',
        -- preference | fact | tool_recipe | schedule
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    embedding       VECTOR(1024),
        -- Matches the rest of the codebase (Voyage-2). Bump and re-embed if
        -- you switch providers.
    tags            TEXT[] NOT NULL DEFAULT '{}',
    source_goal_id  UUID REFERENCES goals(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS memories_user_idx        ON memories(user_id);
CREATE INDEX IF NOT EXISTS memories_user_updated_idx ON memories(user_id, updated_at DESC);

-- IVFFlat needs ANALYZE before it becomes useful; harmless on empty tables.
-- Use `vector_cosine_ops` to match the cosine similarity helper RPC below.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE indexname = 'memories_embedding_idx'
    ) THEN
        EXECUTE 'CREATE INDEX memories_embedding_idx '
                'ON memories USING ivfflat (embedding vector_cosine_ops) '
                'WITH (lists = 100)';
    END IF;
END $$;

ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS memories_owner        ON memories;
DROP POLICY IF EXISTS memories_service_role ON memories;

CREATE POLICY memories_owner
    ON memories FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY memories_service_role
    ON memories FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS trg_memories_updated_at ON memories;
CREATE TRIGGER trg_memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON memories TO authenticated;
GRANT USAGE, SELECT                  ON SEQUENCE memories_id_seq TO authenticated;
GRANT ALL                            ON memories TO service_role;


-- ============================================================================
-- 4. RPC: match_memories — cosine-similarity search scoped to a user
-- ============================================================================
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding VECTOR(1024),
    match_threshold FLOAT,
    match_count     INT,
    p_user_id       UUID
)
RETURNS TABLE (
    id          BIGINT,
    key         TEXT,
    value       JSONB,
    kind        TEXT,
    tags        TEXT[],
    updated_at  TIMESTAMPTZ,
    similarity  FLOAT
)
LANGUAGE SQL STABLE AS $$
    SELECT m.id, m.key, m.value, m.kind, m.tags, m.updated_at,
           1 - (m.embedding <=> query_embedding) AS similarity
    FROM   memories m
    WHERE  m.user_id = p_user_id
      AND  m.embedding IS NOT NULL
      AND  1 - (m.embedding <=> query_embedding) >= match_threshold
    ORDER  BY m.embedding <=> query_embedding
    LIMIT  match_count;
$$;

GRANT EXECUTE ON FUNCTION match_memories(VECTOR(1024), FLOAT, INT, UUID)
    TO authenticated, service_role;


-- ============================================================================
-- 5. scheduled_jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    cron          TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    timezone      TEXT NOT NULL DEFAULT 'UTC',
    last_run_at   TIMESTAMPTZ,
    next_run_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS scheduled_jobs_user_idx     ON scheduled_jobs(user_id);
CREATE INDEX IF NOT EXISTS scheduled_jobs_due_idx
    ON scheduled_jobs(next_run_at)
    WHERE enabled = TRUE;

ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS scheduled_jobs_owner        ON scheduled_jobs;
DROP POLICY IF EXISTS scheduled_jobs_service_role ON scheduled_jobs;

CREATE POLICY scheduled_jobs_owner
    ON scheduled_jobs FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY scheduled_jobs_service_role
    ON scheduled_jobs FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS trg_scheduled_jobs_updated_at ON scheduled_jobs;
CREATE TRIGGER trg_scheduled_jobs_updated_at
    BEFORE UPDATE ON scheduled_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

GRANT SELECT, INSERT, UPDATE, DELETE ON scheduled_jobs TO authenticated;
GRANT ALL                           ON scheduled_jobs TO service_role;


COMMIT;
