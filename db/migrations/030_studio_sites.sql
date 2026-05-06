-- ===========================================================================
-- 030_studio_sites.sql — Content Studio: Websites (Lovable-style)
-- ===========================================================================
-- Adds a third Studio kind, 'site', alongside pptx/docx/chat. Each site
-- artifact is a multi-file HTML/CSS/JS bundle stored as a zip + extracted
-- directory under the Railway volume:
--
--   $STORAGE_ROOT/projects/{project_id}/v{n}.zip
--   $STORAGE_ROOT/projects/{project_id}/v{n}_files/index.html, ...
--
-- Sites can be *published* to a public subdomain (or path-based slug at
-- /s/{subdomain}/), tracked in the `published_sites` table.
--
-- Idempotent: safe to re-run.
-- ===========================================================================

-- 1) Allow kind='site' on studio_projects -----------------------------------
DO $$
BEGIN
    -- Drop the old CHECK constraint and recreate with 'site' allowed.
    IF EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  constraint_name = 'studio_projects_kind_check'
    ) THEN
        ALTER TABLE studio_projects DROP CONSTRAINT studio_projects_kind_check;
    END IF;

    ALTER TABLE studio_projects
        ADD CONSTRAINT studio_projects_kind_check
        CHECK (kind IN ('pptx','docx','chat','site'));
END $$;

-- 2) Allow kind='site' on studio_artifacts ----------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.table_constraints
        WHERE  constraint_name = 'studio_artifacts_kind_check'
    ) THEN
        ALTER TABLE studio_artifacts DROP CONSTRAINT studio_artifacts_kind_check;
    END IF;

    ALTER TABLE studio_artifacts
        ADD CONSTRAINT studio_artifacts_kind_check
        CHECK (kind IN ('pptx','docx','site'));
END $$;

-- Site-specific artifact stats (optional, JSON `meta` already covers most).
ALTER TABLE studio_artifacts
    ADD COLUMN IF NOT EXISTS file_count INTEGER;

-- 3) published_sites — public subdomains -----------------------------------
CREATE TABLE IF NOT EXISTS published_sites (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id           UUID NOT NULL REFERENCES studio_projects(id) ON DELETE CASCADE,
    artifact_id          UUID NOT NULL REFERENCES studio_artifacts(id) ON DELETE CASCADE,

    -- e.g. "my-portfolio" → served at /s/my-portfolio/  AND
    --                                  https://my-portfolio.sites.<DOMAIN>/
    subdomain            TEXT NOT NULL,
    custom_domain        TEXT,                       -- future: tenant CNAME

    -- Cached path to the unzipped static-file directory on the Railway
    -- volume so the public router doesn't have to re-resolve every request.
    site_root_path       TEXT NOT NULL,

    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    published_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_request_at      TIMESTAMPTZ,
    request_count        BIGINT NOT NULL DEFAULT 0,

    meta                 JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- subdomain charset / length sanity (router enforces too)
    CONSTRAINT published_sites_subdomain_format
        CHECK (subdomain ~ '^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])?$')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_published_sites_subdomain_active
    ON published_sites (LOWER(subdomain))
    WHERE is_active;

CREATE UNIQUE INDEX IF NOT EXISTS uq_published_sites_custom_domain_active
    ON published_sites (LOWER(custom_domain))
    WHERE is_active AND custom_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_published_sites_user_id
    ON published_sites (user_id);
CREATE INDEX IF NOT EXISTS idx_published_sites_project_id
    ON published_sites (project_id);

-- updated_at trigger -------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_published_sites_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS published_sites_updated_at ON published_sites;
CREATE TRIGGER published_sites_updated_at
    BEFORE UPDATE ON published_sites
    FOR EACH ROW EXECUTE FUNCTION trg_published_sites_updated_at();

-- RLS ---------------------------------------------------------------------
ALTER TABLE published_sites ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS published_sites_owner_all ON published_sites;
DROP POLICY IF EXISTS published_sites_service   ON published_sites;
DROP POLICY IF EXISTS published_sites_public_read ON published_sites;

-- Owners can do anything with their own publications.
CREATE POLICY published_sites_owner_all ON published_sites
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

-- Service role bypass (used by the public router to resolve subdomains).
CREATE POLICY published_sites_service ON published_sites
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

-- Anonymous users can READ active rows so a public-facing subdomain lookup
-- works without service_role. Lookup key = subdomain (which is enforced
-- unique via the partial unique index above).
CREATE POLICY published_sites_public_read ON published_sites
    FOR SELECT USING (is_active);

GRANT SELECT ON published_sites TO anon;
GRANT ALL    ON published_sites TO authenticated, service_role;

COMMENT ON TABLE published_sites
    IS 'Content Studio site publications — public subdomains for AI-generated websites';
