-- ════════════════════════════════════════════════════════════════════════════
-- Migration 020: PPTX Program Store + Asset Library
-- ════════════════════════════════════════════════════════════════════════════
-- Adds:
--   • pptx_programs           — reusable "source code" of generated decks
--   • pptx_program_versions   — append-only version history for programs
--   • pptx_assets             — user-uploadable icon/graphic/logo library
--
-- RLS
-- ----
-- Programs: a user can only read/write their own rows.
-- Assets:   everyone reads global + their own; writes only their own rows.
-- Global assets are seeded by the backend (service_role bypasses RLS).
-- ════════════════════════════════════════════════════════════════════════════

-- ── Programs ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pptx_programs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title            TEXT NOT NULL DEFAULT 'Untitled',
    canvas           JSONB NOT NULL DEFAULT '{"preset":"wide"}'::jsonb,
    program          JSONB NOT NULL,          -- full slide list + metadata
    asset_snapshot   JSONB NOT NULL DEFAULT '{}'::jsonb,
    version          INT  NOT NULL DEFAULT 1,
    file_id          TEXT,                    -- pointer to latest rendered file_store entry
    last_render_sha  TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pptx_programs_user_updated
    ON pptx_programs (user_id, updated_at DESC);

ALTER TABLE pptx_programs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pptx_programs_self" ON pptx_programs;
CREATE POLICY "pptx_programs_self" ON pptx_programs
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Auto-update updated_at on row modification
CREATE OR REPLACE FUNCTION _pptx_programs_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pptx_programs_touch ON pptx_programs;
CREATE TRIGGER pptx_programs_touch
    BEFORE UPDATE ON pptx_programs
    FOR EACH ROW EXECUTE FUNCTION _pptx_programs_touch();

-- ── Program Versions (append-only history) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS pptx_program_versions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id   UUID NOT NULL REFERENCES pptx_programs(id) ON DELETE CASCADE,
    version      INT  NOT NULL,
    title        TEXT,
    canvas       JSONB,
    program      JSONB NOT NULL,
    patches      JSONB,             -- the patches that produced this version, if any
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (program_id, version)
);

CREATE INDEX IF NOT EXISTS idx_pptx_program_versions_program
    ON pptx_program_versions (program_id, version DESC);

ALTER TABLE pptx_program_versions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pptx_program_versions_self" ON pptx_program_versions;
CREATE POLICY "pptx_program_versions_self" ON pptx_program_versions
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM pptx_programs p
            WHERE p.id = pptx_program_versions.program_id
              AND p.user_id = auth.uid()
        )
    ) WITH CHECK (
        EXISTS (
            SELECT 1 FROM pptx_programs p
            WHERE p.id = pptx_program_versions.program_id
              AND p.user_id = auth.uid()
        )
    );

-- ── Assets ─────────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE TYPE pptx_asset_scope AS ENUM ('global','org','user');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS pptx_assets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope        pptx_asset_scope NOT NULL,
    owner_id     UUID,                           -- null for global, user_id for user scope
    key          TEXT NOT NULL,
    kind         TEXT NOT NULL,                  -- 'icon'|'graphic'|'background'|'logo'
    file_path    TEXT NOT NULL,                  -- absolute path on Railway volume
    file_sha     TEXT NOT NULL,
    mime         TEXT NOT NULL,
    aspect       NUMERIC,
    bytes_size   INT,
    tags         TEXT[] NOT NULL DEFAULT '{}',
    use_when     TEXT,                           -- natural-language hint for LLM
    on_colors    TEXT[] NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Unique (scope, owner_id, key) with NULL-safe owner_id comparison
CREATE UNIQUE INDEX IF NOT EXISTS idx_pptx_assets_unique
    ON pptx_assets (
        scope,
        COALESCE(owner_id, '00000000-0000-0000-0000-000000000000'::uuid),
        key
    );

CREATE INDEX IF NOT EXISTS idx_pptx_assets_tags
    ON pptx_assets USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_pptx_assets_owner
    ON pptx_assets (owner_id) WHERE owner_id IS NOT NULL;

ALTER TABLE pptx_assets ENABLE ROW LEVEL SECURITY;

-- Read: global + own user assets
DROP POLICY IF EXISTS "pptx_assets_read" ON pptx_assets;
CREATE POLICY "pptx_assets_read" ON pptx_assets
    FOR SELECT USING (
        scope = 'global'
        OR (scope = 'user' AND owner_id = auth.uid())
    );

-- Insert / update / delete: only own user-scoped rows (global is backend-only)
DROP POLICY IF EXISTS "pptx_assets_write_own" ON pptx_assets;
CREATE POLICY "pptx_assets_write_own" ON pptx_assets
    FOR INSERT WITH CHECK (scope = 'user' AND owner_id = auth.uid());

DROP POLICY IF EXISTS "pptx_assets_update_own" ON pptx_assets;
CREATE POLICY "pptx_assets_update_own" ON pptx_assets
    FOR UPDATE USING (scope = 'user' AND owner_id = auth.uid())
    WITH CHECK (scope = 'user' AND owner_id = auth.uid());

DROP POLICY IF EXISTS "pptx_assets_delete_own" ON pptx_assets;
CREATE POLICY "pptx_assets_delete_own" ON pptx_assets
    FOR DELETE USING (scope = 'user' AND owner_id = auth.uid());

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION _pptx_assets_touch()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pptx_assets_touch ON pptx_assets;
CREATE TRIGGER pptx_assets_touch
    BEFORE UPDATE ON pptx_assets
    FOR EACH ROW EXECUTE FUNCTION _pptx_assets_touch();

-- ════════════════════════════════════════════════════════════════════════════
-- End of migration 020
-- ════════════════════════════════════════════════════════════════════════════
