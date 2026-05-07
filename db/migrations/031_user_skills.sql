-- =====================================================================
-- Migration 031: User-Uploaded Skills
-- =====================================================================
-- Adds two tables backing the skill upload feature:
--   user_skills        — registry row per skill (system + user-uploaded)
--   user_skill_audit   — append-only audit log for create/update/delete
--
-- Filesystem is the source of truth for skill content (folders under
-- core/skills/ and ClaudeSkills/). The raw zip for user-uploaded skills
-- is also archived in Supabase Storage bucket 'skills-bundles' so
-- ephemeral Railway containers can rehydrate after redeploy.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Table: user_skills
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_skills (
    slug          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    category      TEXT NOT NULL DEFAULT 'general',
    tags          TEXT[] NOT NULL DEFAULT '{}',

    -- 'lightweight' = core/skills/<slug>/   (skill.json + prompt.md)
    -- 'bundle'      = ClaudeSkills/<slug>/  (full Anthropic SKILL.md bundle)
    storage_kind  TEXT NOT NULL CHECK (storage_kind IN ('lightweight', 'bundle')),

    -- Repo-relative directory of the materialized skill on disk
    storage_path  TEXT NOT NULL,

    -- Metadata about the uploaded zip (0 for system skills)
    bundle_size   BIGINT  NOT NULL DEFAULT 0,
    file_count    INTEGER NOT NULL DEFAULT 0,

    enabled       BOOLEAN NOT NULL DEFAULT TRUE,

    -- 'system' = pre-existing repo folder (auto-registered on boot)
    -- 'upload' = user uploaded a .zip
    -- 'inline' = user filled the form, frontend synthesized a 1-file zip
    source        TEXT NOT NULL DEFAULT 'upload'
                  CHECK (source IN ('system', 'upload', 'inline')),

    created_by    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_skills_created_by ON public.user_skills(created_by);
CREATE INDEX IF NOT EXISTS idx_user_skills_category   ON public.user_skills(category);
CREATE INDEX IF NOT EXISTS idx_user_skills_enabled    ON public.user_skills(enabled);
CREATE INDEX IF NOT EXISTS idx_user_skills_source     ON public.user_skills(source);

CREATE OR REPLACE FUNCTION public.user_skills_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_skills_updated_at ON public.user_skills;
CREATE TRIGGER trg_user_skills_updated_at
    BEFORE UPDATE ON public.user_skills
    FOR EACH ROW
    EXECUTE FUNCTION public.user_skills_set_updated_at();

-- ---------------------------------------------------------------------
-- Table: user_skill_audit
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_skill_audit (
    id          BIGSERIAL PRIMARY KEY,
    slug        TEXT NOT NULL,
    actor_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL
                CHECK (action IN ('create', 'update', 'delete', 'enable',
                                  'disable', 'reconcile', 'rehydrate')),
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_skill_audit_slug       ON public.user_skill_audit(slug);
CREATE INDEX IF NOT EXISTS idx_user_skill_audit_actor      ON public.user_skill_audit(actor_id);
CREATE INDEX IF NOT EXISTS idx_user_skill_audit_created_at ON public.user_skill_audit(created_at DESC);

ALTER TABLE public.user_skills      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_skill_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "user_skills_select_authenticated" ON public.user_skills;
CREATE POLICY "user_skills_select_authenticated"
    ON public.user_skills
    FOR SELECT
    TO authenticated
    USING (true);

DROP POLICY IF EXISTS "user_skill_audit_select_self_or_admin" ON public.user_skill_audit;
CREATE POLICY "user_skill_audit_select_self_or_admin"
    ON public.user_skill_audit
    FOR SELECT
    TO authenticated
    USING (
        actor_id = auth.uid()
        OR EXISTS (
            SELECT 1 FROM public.user_profiles
            WHERE id = auth.uid() AND is_admin = TRUE
        )
    );

-- ---------------------------------------------------------------------
-- Storage bucket: skills-bundles
-- ---------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'skills-bundles',
    'skills-bundles',
    FALSE,
    26214400,  -- 25 MB
    ARRAY['application/zip', 'application/x-zip-compressed', 'application/octet-stream']
)
ON CONFLICT (id) DO UPDATE
SET public             = EXCLUDED.public,
    file_size_limit    = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "skills_bundles_no_client_access" ON storage.objects;
CREATE POLICY "skills_bundles_no_client_access"
    ON storage.objects
    FOR ALL
    TO authenticated, anon
    USING (bucket_id <> 'skills-bundles')
    WITH CHECK (bucket_id <> 'skills-bundles');
