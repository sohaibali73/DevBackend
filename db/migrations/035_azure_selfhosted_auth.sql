-- ============================================================================
-- Migration 035: SELF-HOSTED AUTH — move identity into user_profiles
-- ============================================================================
-- Supabase Auth is gone. The backend now stores credentials and issues its own
-- JWTs. user_profiles becomes the single source of truth for accounts:
--   * email          — login identifier (was in auth.users)
--   * password_hash  — bcrypt hash (was managed by Supabase GoTrue)
--
-- RLS is no longer used for authorization (the backend connects with a
-- privileged role and enforces access in application code), so we disable it on
-- user_profiles to avoid the now-meaningless auth.uid() policies blocking the
-- app. Other tables can keep RLS enabled harmlessly (owner bypasses it).
-- ============================================================================

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS email         citext;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS password_hash text;

-- Encrypted per-user API keys. claude/tavily originate in migration 010 (which
-- can fail to fully apply on a clean replay); add them defensively so the app's
-- profile queries always have these columns. openai/openrouter come from 017.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS claude_api_key_encrypted     text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS tavily_api_key_encrypted     text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS openai_api_key_encrypted     text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS openrouter_api_key_encrypted text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_provider           text DEFAULT 'anthropic';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferred_model              text DEFAULT 'claude-sonnet-4-20250514';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_active_at               timestamptz;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS updated_at                   timestamptz DEFAULT now();

-- Unique email (case-insensitive via citext), allowing existing NULLs.
CREATE UNIQUE INDEX IF NOT EXISTS user_profiles_email_unique
    ON user_profiles (email)
    WHERE email IS NOT NULL;

-- Self-hosted accounts live in user_profiles and generate their own uuids; the
-- backend enforces ownership in code (no RLS). Drop EVERY foreign key that
-- references auth.users across all tables, otherwise inserts would require a
-- matching (never-populated) auth.users row and fail at runtime.
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT conrelid::regclass AS tbl, conname
        FROM pg_constraint
        WHERE contype = 'f' AND confrelid = 'auth.users'::regclass
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tbl, r.conname);
        RAISE NOTICE 'Dropped auth.users FK % on %', r.conname, r.tbl;
    END LOOP;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'auth.users FK cleanup skipped: %', SQLERRM;
END $$;

ALTER TABLE user_profiles ALTER COLUMN id SET DEFAULT gen_random_uuid();

-- RLS off for user_profiles (authz enforced in app code now).
ALTER TABLE user_profiles DISABLE ROW LEVEL SECURITY;

-- The Supabase signup trigger no longer fires (no auth.users inserts).
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

SELECT '✅ Migration 035: self-hosted auth columns ready' AS status;
