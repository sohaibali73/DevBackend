-- =============================================================================
-- Migration: create_slide_library
-- Description: Corporate slide library for semantic search and reuse
-- =============================================================================

-- slide_library stores analyzed slides with metadata for search and reuse.
-- Falls back gracefully if this table doesn't exist (SlideLibrary uses
-- in-memory store when Supabase is unavailable).

CREATE TABLE IF NOT EXISTS slide_library (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          TEXT NOT NULL,
    source_filename  TEXT NOT NULL,
    slide_index      INTEGER NOT NULL DEFAULT 1,
    job_id           TEXT NOT NULL DEFAULT '',

    -- Layout + content metadata (from VisionEngine SlideAnalysis)
    layout_type      TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    section_label    TEXT NOT NULL DEFAULT '',
    background       TEXT NOT NULL DEFAULT 'FFFFFF',    -- hex without #

    -- Color palette (stored as JSONB array of hex strings)
    color_palette    JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Full SlideAnalysis JSON (for reconstruction)
    analysis         JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Perceptual hash for visual similarity search
    phash            TEXT NOT NULL DEFAULT '',

    -- Preview image URL (served from job storage)
    preview_url      TEXT NOT NULL DEFAULT '',

    -- Searchable tags (auto-generated + user-supplied)
    tags             TEXT[] NOT NULL DEFAULT '{}',

    -- Brand compliance score (0-100 from BrandEnforcer)
    brand_score      INTEGER NOT NULL DEFAULT 0,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Primary lookup by user
CREATE INDEX IF NOT EXISTS idx_slide_library_user_id
    ON slide_library (user_id);

-- Layout-type filter (common query pattern)
CREATE INDEX IF NOT EXISTS idx_slide_library_layout
    ON slide_library (user_id, layout_type);

-- Brand score filter (find high-scoring slides)
CREATE INDEX IF NOT EXISTS idx_slide_library_brand_score
    ON slide_library (user_id, brand_score DESC);

-- Source file filter (find all slides from a specific deck)
CREATE INDEX IF NOT EXISTS idx_slide_library_source
    ON slide_library (user_id, source_filename);

-- GIN index on tags for array containment queries
CREATE INDEX IF NOT EXISTS idx_slide_library_tags
    ON slide_library USING GIN (tags);

-- Full-text search on title + section_label
CREATE INDEX IF NOT EXISTS idx_slide_library_title_fts
    ON slide_library USING GIN (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(section_label, ''))
    );

-- ── RLS (Row Level Security) ──────────────────────────────────────────────────
-- Disabled by default — the backend enforces user_id isolation.
-- Enable RLS if you expose this table directly to the Supabase JS client:
-- ALTER TABLE slide_library ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Users see own slides" ON slide_library
--     FOR ALL USING (auth.uid()::text = user_id);

-- ── Auto-update updated_at ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_slide_library_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_slide_library_updated_at ON slide_library;
CREATE TRIGGER trigger_slide_library_updated_at
    BEFORE UPDATE ON slide_library
    FOR EACH ROW EXECUTE FUNCTION update_slide_library_updated_at();

-- ── Utility view: slide_library_summary ──────────────────────────────────────
-- Lightweight summary for listing endpoints (no large JSONB fields)
CREATE OR REPLACE VIEW slide_library_summary AS
SELECT
    id,
    user_id,
    source_filename,
    slide_index,
    job_id,
    layout_type,
    title,
    section_label,
    background,
    color_palette,
    phash,
    preview_url,
    tags,
    brand_score,
    created_at
FROM slide_library;
