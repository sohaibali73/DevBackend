-- ===========================================================================
-- 027_studio_projects.sql — Content Studio: Projects + Versioned Artifacts
-- ===========================================================================
-- A Studio Project is a thin wrapper over an existing `conversations` row:
--   • kind: 'pptx' | 'docx' | 'chat'
--   • optional writing-style profile (writing_styles)
--   • optional humanize settings
--   • ordered list of artifact versions stored on Railway volume
--
-- Files live on the Railway volume at:
--   $STORAGE_ROOT/projects/{project_id}/v{n}.{ext}
--   $STORAGE_ROOT/projects/{project_id}/edit_state/v{n}.json
--
-- The DB stores only metadata + paths. No bytes.
--
-- Idempotent: safe to re-run.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- studio_projects
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS studio_projects (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id      UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,

    kind                 TEXT NOT NULL CHECK (kind IN ('pptx','docx','chat')),
    title                TEXT NOT NULL DEFAULT 'Untitled Project',
    description          TEXT NOT NULL DEFAULT '',

    -- Writing-style profile (clone) attached to this project
    style_profile_id     UUID,

    -- Humanizer settings
    -- Example:
    -- {"enabled":true,"intensity":"standard","seo_target":"linkedin","preserve_facts":true,"auto_apply":false}
    humanize_settings    JSONB NOT NULL DEFAULT
        '{"enabled":false,"intensity":"standard","seo_target":null,"preserve_facts":true,"auto_apply":false}'::jsonb,

    -- Pointer to the "live" artifact version shown in the editor
    current_artifact_id  UUID,

    -- Volume-relative thumbnail path (rendered by frontend, optional)
    thumbnail_path       TEXT,

    tags                 TEXT[] NOT NULL DEFAULT '{}',
    is_archived          BOOLEAN NOT NULL DEFAULT FALSE,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_studio_projects_user_id
    ON studio_projects(user_id);
CREATE INDEX IF NOT EXISTS idx_studio_projects_user_kind
    ON studio_projects(user_id, kind) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_studio_projects_conversation_id
    ON studio_projects(conversation_id);
CREATE INDEX IF NOT EXISTS idx_studio_projects_updated_at
    ON studio_projects(updated_at DESC);

-- ---------------------------------------------------------------------------
-- studio_artifacts — versioned output files on Railway volume
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS studio_artifacts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES studio_projects(id) ON DELETE CASCADE,
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    conversation_id   UUID REFERENCES conversations(id) ON DELETE SET NULL,
    message_id        UUID,                          -- optional, source assistant message
    source_file_id    TEXT,                          -- file_store/file_uploads id this was derived from

    kind              TEXT NOT NULL CHECK (kind IN ('pptx','docx')),
    version           INTEGER NOT NULL DEFAULT 1,

    filename          TEXT NOT NULL,                 -- e.g. "Q1_Outlook.pptx"
    volume_path       TEXT NOT NULL,                 -- absolute path under STORAGE_ROOT/projects/{project_id}/v{n}.{ext}
    size_bytes        BIGINT NOT NULL DEFAULT 0,

    -- Type-specific stats
    slide_count       INTEGER,
    page_count        INTEGER,

    -- JSON ops applied by visual editor (or null on first render)
    edit_state        JSONB,

    -- Metadata bag (parser hints, source skill, humanizer pass info, etc.)
    meta              JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_studio_artifacts_project_id
    ON studio_artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_studio_artifacts_user_id
    ON studio_artifacts(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_studio_artifacts_project_version
    ON studio_artifacts(project_id, version);
CREATE INDEX IF NOT EXISTS idx_studio_artifacts_conversation_id
    ON studio_artifacts(conversation_id);

-- Late-add FK from project.current_artifact_id → artifact.id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'studio_projects_current_artifact_fk'
    ) THEN
        ALTER TABLE studio_projects
            ADD CONSTRAINT studio_projects_current_artifact_fk
            FOREIGN KEY (current_artifact_id)
            REFERENCES studio_artifacts(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_studio_projects_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS studio_projects_updated_at ON studio_projects;
CREATE TRIGGER studio_projects_updated_at
    BEFORE UPDATE ON studio_projects
    FOR EACH ROW EXECUTE FUNCTION trg_studio_projects_updated_at();

-- Touch project.updated_at when an artifact is added
CREATE OR REPLACE FUNCTION trg_studio_artifacts_touch_project()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE studio_projects
    SET updated_at = NOW()
    WHERE id = NEW.project_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS studio_artifacts_touch_project ON studio_artifacts;
CREATE TRIGGER studio_artifacts_touch_project
    AFTER INSERT OR UPDATE ON studio_artifacts
    FOR EACH ROW EXECUTE FUNCTION trg_studio_artifacts_touch_project();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE studio_projects  ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS studio_projects_owner_all  ON studio_projects;
DROP POLICY IF EXISTS studio_projects_service    ON studio_projects;
CREATE POLICY studio_projects_owner_all ON studio_projects
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY studio_projects_service ON studio_projects
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS studio_artifacts_owner_all ON studio_artifacts;
DROP POLICY IF EXISTS studio_artifacts_service   ON studio_artifacts;
CREATE POLICY studio_artifacts_owner_all ON studio_artifacts
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY studio_artifacts_service ON studio_artifacts
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

GRANT ALL ON studio_projects  TO authenticated, service_role;
GRANT ALL ON studio_artifacts TO authenticated, service_role;

COMMENT ON TABLE studio_projects  IS 'Content Studio project — wraps a conversation with kind/style/humanize metadata';
COMMENT ON TABLE studio_artifacts IS 'Versioned PPTX/DOCX outputs for Content Studio projects (bytes on Railway volume)';
