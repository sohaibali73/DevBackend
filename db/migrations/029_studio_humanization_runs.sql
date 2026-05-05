-- ===========================================================================
-- 029_studio_humanization_runs.sql — Audit log for the advanced humanizer
-- ===========================================================================
-- Each row records one full pipeline run (multi-pass rewrite + detector loop).
-- Large fields (passes, full diffs) are also dumped to the Railway volume at:
--   $STORAGE_ROOT/humanize/{run_id}.json
-- so the DB stays small. The DB row carries the summary + scores so the
-- frontend can list / paginate runs cheaply.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS studio_humanization_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    project_id          UUID REFERENCES studio_projects(id)         ON DELETE SET NULL,
    conversation_id     UUID REFERENCES conversations(id)            ON DELETE SET NULL,
    style_profile_id    UUID REFERENCES studio_writing_styles(id)    ON DELETE SET NULL,

    intensity           TEXT NOT NULL DEFAULT 'standard'
                        CHECK (intensity IN ('light','standard','max')),
    seo_target          TEXT CHECK (seo_target IN ('linkedin')),     -- nullable, expand later
    preserve_facts      BOOLEAN NOT NULL DEFAULT TRUE,

    -- Truncated inputs/outputs for cheap previews; full text on volume.
    input_text          TEXT NOT NULL,
    output_text         TEXT NOT NULL DEFAULT '',
    input_word_count    INTEGER NOT NULL DEFAULT 0,
    output_word_count   INTEGER NOT NULL DEFAULT 0,

    -- Final scores: {ai_detection:0..1, style_fidelity:0..1,
    --                readability:flesch, seo:0..1, perplexity_ratio:..., gltr_score:...}
    final_scores        JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Per-pass summary: [{pass:"burstiness", model, in_tokens, out_tokens,
    --                     duration_ms, scores_after:{...}}, ...]
    -- Full prompt + diff are on disk.
    passes_summary      JSONB NOT NULL DEFAULT '[]'::jsonb,

    detector_retries    INTEGER NOT NULL DEFAULT 0,

    -- Where the full trace JSON was written
    volume_path         TEXT,

    -- 'pending' | 'running' | 'succeeded' | 'failed'
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','succeeded','failed')),
    error               TEXT,

    duration_ms         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_humanization_runs_user
    ON studio_humanization_runs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_humanization_runs_project
    ON studio_humanization_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_humanization_runs_style
    ON studio_humanization_runs(style_profile_id);

ALTER TABLE studio_humanization_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS studio_humanization_runs_owner_all ON studio_humanization_runs;
DROP POLICY IF EXISTS studio_humanization_runs_service   ON studio_humanization_runs;
CREATE POLICY studio_humanization_runs_owner_all ON studio_humanization_runs
    FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY studio_humanization_runs_service ON studio_humanization_runs
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

GRANT ALL ON studio_humanization_runs TO authenticated, service_role;

COMMENT ON TABLE studio_humanization_runs IS
    'Audit log of multi-pass humanizer runs (AI detector bypass + LinkedIn SEO)';
