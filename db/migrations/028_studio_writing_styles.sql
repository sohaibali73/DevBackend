-- ===========================================================================
-- 028_studio_writing_styles.sql — Voice Cloning ("writing-style training")
-- ===========================================================================
-- Stores per-user "voice profiles" derived from raw writing samples.
-- The cloner extracts a quantitative + qualitative voice card and a cached
-- system_prompt + few-shot exemplars to inject into /chat/agent so the model
-- writes in the cloned voice 1:1.
--
-- Files (raw samples) live on the Railway volume:
--   $STORAGE_ROOT/styles/{style_id}/samples/{sample_id}.txt
--   $STORAGE_ROOT/styles/{style_id}/voice_card.json
--
-- Tables created here are NEW and do NOT touch the legacy `writing_styles`
-- table mentioned in older migrations. Use `studio_writing_styles` everywhere.
--
-- Idempotent: safe to re-run.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- studio_writing_styles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS studio_writing_styles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    icon            TEXT NOT NULL DEFAULT '✍️',
    color           TEXT NOT NULL DEFAULT '#FEC00F',

    -- 'draft'      → created, no samples yet
    -- 'analyzing'  → background analysis running
    -- 'ready'      → voice_card + system_prompt populated
    -- 'failed'     → analysis errored (see meta.error)
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','analyzing','ready','failed')),

    -- Quantitative voice card (sentence stats, lexical fingerprints, idiolect markers, ...)
    -- Shape documented in core/styles/cloner.py
    voice_card      JSONB,

    -- Cached system prompt that injects this voice into /chat/agent
    -- (built from voice_card + few-shot exemplars by core/styles/injector.py)
    system_prompt   TEXT,

    -- 8–12 most-characteristic passages from samples (full text)
    exemplars       JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Average sample embedding (sentence-transformers, 384-dim) for fidelity scoring
    embedding       VECTOR(384),

    -- Self-test fidelity score (0..1) from generation-vs-sample similarity
    fidelity_score  DOUBLE PRECISION,

    sample_count    INTEGER NOT NULL DEFAULT 0,
    total_words     INTEGER NOT NULL DEFAULT 0,

    meta            JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_studio_writing_styles_user_name
    ON studio_writing_styles(user_id, name);
CREATE INDEX IF NOT EXISTS idx_studio_writing_styles_user
    ON studio_writing_styles(user_id);
CREATE INDEX IF NOT EXISTS idx_studio_writing_styles_status
    ON studio_writing_styles(status);

-- ---------------------------------------------------------------------------
-- studio_writing_style_samples — raw user-provided writing
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS studio_writing_style_samples (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    style_id        UUID NOT NULL REFERENCES studio_writing_styles(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    title           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'paste'
                    CHECK (source IN ('paste','file','url')),
    source_url      TEXT,
    source_file_id  TEXT,                 -- optional file_uploads/file_store id

    text            TEXT NOT NULL,
    word_count      INTEGER NOT NULL DEFAULT 0,
    char_count      INTEGER NOT NULL DEFAULT 0,

    -- Volume-relative path where the raw sample is saved
    volume_path     TEXT,

    -- Per-sample mini-stats computed at ingest (sentence_len_avg, burstiness, ...)
    stats           JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Per-sample embedding for centroid + exemplar selection
    embedding       VECTOR(384),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_studio_writing_style_samples_style
    ON studio_writing_style_samples(style_id);
CREATE INDEX IF NOT EXISTS idx_studio_writing_style_samples_user
    ON studio_writing_style_samples(user_id);

-- ---------------------------------------------------------------------------
-- Keep parent style stats in sync
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_studio_writing_style_stats(p_style_id UUID)
RETURNS VOID AS $$
BEGIN
    IF p_style_id IS NULL THEN
        RETURN;
    END IF;

    UPDATE studio_writing_styles ws
    SET
        sample_count = COALESCE(s.cnt, 0),
        total_words  = COALESCE(s.words, 0),
        updated_at   = NOW()
    FROM (
        SELECT
            COUNT(*)               AS cnt,
            COALESCE(SUM(word_count), 0) AS words
        FROM studio_writing_style_samples
        WHERE style_id = p_style_id
    ) s
    WHERE ws.id = p_style_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_studio_writing_style_samples_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP IN ('UPDATE','DELETE') AND OLD.style_id IS NOT NULL THEN
        PERFORM refresh_studio_writing_style_stats(OLD.style_id);
    END IF;
    IF TG_OP IN ('INSERT','UPDATE') AND NEW.style_id IS NOT NULL THEN
        PERFORM refresh_studio_writing_style_stats(NEW.style_id);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS studio_writing_style_samples_stats ON studio_writing_style_samples;
CREATE TRIGGER studio_writing_style_samples_stats
    AFTER INSERT OR UPDATE OR DELETE ON studio_writing_style_samples
    FOR EACH ROW EXECUTE FUNCTION trg_studio_writing_style_samples_stats();

CREATE OR REPLACE FUNCTION trg_studio_writing_styles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS studio_writing_styles_updated_at ON studio_writing_styles;
CREATE TRIGGER studio_writing_styles_updated_at
    BEFORE UPDATE ON studio_writing_styles
    FOR EACH ROW EXECUTE FUNCTION trg_studio_writing_styles_updated_at();

-- ---------------------------------------------------------------------------
-- Late-add FK on studio_projects.style_profile_id → studio_writing_styles.id
-- (created in migration 027 without FK; we add it now)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='studio_projects')
       AND NOT EXISTS (
           SELECT 1 FROM information_schema.table_constraints
           WHERE constraint_name = 'studio_projects_style_profile_fk'
       ) THEN
        ALTER TABLE studio_projects
            ADD CONSTRAINT studio_projects_style_profile_fk
            FOREIGN KEY (style_profile_id)
            REFERENCES studio_writing_styles(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE studio_writing_styles         ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_writing_style_samples  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS studio_writing_styles_owner_all  ON studio_writing_styles;
DROP POLICY IF EXISTS studio_writing_styles_service    ON studio_writing_styles;
CREATE POLICY studio_writing_styles_owner_all ON studio_writing_styles
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY studio_writing_styles_service ON studio_writing_styles
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS studio_writing_style_samples_owner_all  ON studio_writing_style_samples;
DROP POLICY IF EXISTS studio_writing_style_samples_service    ON studio_writing_style_samples;
CREATE POLICY studio_writing_style_samples_owner_all ON studio_writing_style_samples
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY studio_writing_style_samples_service ON studio_writing_style_samples
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

GRANT ALL ON studio_writing_styles        TO authenticated, service_role;
GRANT ALL ON studio_writing_style_samples TO authenticated, service_role;

COMMENT ON TABLE studio_writing_styles IS
    'Per-user cloned voice profiles (1:1 voice cloning) for Content Studio';
COMMENT ON TABLE studio_writing_style_samples IS
    'Raw writing samples used to clone a voice (text on volume + DB metadata)';
