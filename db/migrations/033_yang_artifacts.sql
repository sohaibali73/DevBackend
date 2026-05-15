-- ============================================================================
-- Migration 033: YANG Autopilot — Goal Artifacts
-- ============================================================================
-- Idempotent: safe to re-run.
-- Run in the Supabase SQL Editor (paste this whole file).
--
-- Table created:
--   * goal_artifacts — file artifacts a goal produced (DOCX, PPTX, charts,
--     screenshots, etc). The actual bytes live on the Railway volume under
--     $STORAGE_ROOT/yang_artifacts/{goal_id}/{artifact_id}__{safe_name}.
--     This table is the metadata index so we can:
--       - serve `GET /goals/{id}/artifacts` cheaply
--       - return 410 Gone when retention GC has deleted the bytes
--       - enforce per-user ownership via RLS
--
-- Retention policy is enforced in core/artifacts.py:
--     bytes deleted ≥ 24h after the goal reaches a terminal status; the row
--     stays so the SSE `artifact` step's `url` returns 410, not 404.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS goal_artifacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id         UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,
        -- denormalised for RLS; mirrors goals.user_id.
    name            TEXT NOT NULL,
    mime            TEXT NOT NULL,
    bytes           BIGINT NOT NULL,
    sha256          TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
        -- absolute path on the Railway volume.
    produced_by     TEXT,
        -- tool-call id or tool name that produced this artifact.
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
        -- set when retention GC removes the bytes from disk. Row stays so
        -- GET /goals/{id}/artifacts/{aid} can return 410 Gone instead of 404.
);

CREATE INDEX IF NOT EXISTS goal_artifacts_goal_idx       ON goal_artifacts(goal_id);
CREATE INDEX IF NOT EXISTS goal_artifacts_user_idx       ON goal_artifacts(user_id);
CREATE INDEX IF NOT EXISTS goal_artifacts_goal_sha_idx   ON goal_artifacts(goal_id, sha256);
CREATE INDEX IF NOT EXISTS goal_artifacts_created_idx    ON goal_artifacts(created_at DESC);

ALTER TABLE goal_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS goal_artifacts_owner        ON goal_artifacts;
DROP POLICY IF EXISTS goal_artifacts_service_role ON goal_artifacts;

CREATE POLICY goal_artifacts_owner
    ON goal_artifacts FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY goal_artifacts_service_role
    ON goal_artifacts FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON goal_artifacts TO authenticated;
GRANT ALL                            ON goal_artifacts TO service_role;

COMMIT;
