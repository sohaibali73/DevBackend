-- ============================================================================
-- Migration 000: AZURE BOOTSTRAP — Supabase compatibility shim
-- ============================================================================
-- Runs FIRST. Lets the historical migrations (001–034), which were written for
-- Supabase, apply cleanly on a plain Azure Database for PostgreSQL instance.
--
-- It creates the Supabase-provided objects our migrations reference but that do
-- not exist on vanilla Postgres:
--   * extensions: pgcrypto (gen_random_uuid), vector (pgvector), citext
--   * roles: anon / authenticated / service_role (so GRANT/REVOKE succeed)
--   * schema `auth` + a stub `auth.users` table (FK + trigger targets)
--   * auth.uid() -> NULL (RLS policies compile; the backend connects as the
--     table owner and bypasses RLS, enforcing authz in application code)
--
-- Idempotent: safe to run multiple times.
-- ============================================================================

-- ── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- pgvector must be allow-listed on the server first:
--   az postgres flexible-server parameter set ... --name azure.extensions --value VECTOR
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'pgvector not available yet (allow-list azure.extensions=VECTOR): %', SQLERRM;
END $$;

-- ── Roles (NOLOGIN; only needed so GRANT/REVOKE statements resolve) ───────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN BYPASSRLS;
    END IF;
END $$;

-- ── auth schema + stub users table + auth.uid() ───────────────────────────────
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         text UNIQUE,
    raw_user_meta_data jsonb DEFAULT '{}'::jsonb,
    created_at    timestamptz DEFAULT now()
);

-- auth.uid() returns the request's user id when set as a GUC, else NULL.
-- The app does not rely on this (authz is enforced in code); it exists only so
-- RLS policies referencing auth.uid() can be created without error.
CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;

-- auth.role() / auth.jwt() — referenced by historical RLS policies. Stubs only.
CREATE OR REPLACE FUNCTION auth.role()
RETURNS text
LANGUAGE sql STABLE
AS $$ SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role', true), ''), 'service_role'); $$;

CREATE OR REPLACE FUNCTION auth.jwt()
RETURNS jsonb
LANGUAGE sql STABLE
AS $$ SELECT '{}'::jsonb; $$;

-- Legacy `public.users` table: pre-Supabase-auth migrations (001_training_data,
-- 002, 004, 005) create FKs against it. 011 later repoints those to auth.users,
-- and 035 drops the auth.users FKs entirely (authz is code-enforced). This stub
-- exists only so those historical statements apply on a fresh database.
CREATE TABLE IF NOT EXISTS public.users (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email      text,
    name       text,
    nickname   text,
    is_admin   boolean DEFAULT false,
    is_active  boolean DEFAULT true,
    status     text DEFAULT 'active',
    created_at timestamptz DEFAULT now()
);

-- ── storage schema stub ───────────────────────────────────────────────────────
-- Historical migrations INSERT bucket definitions into Supabase's storage.buckets
-- and may reference storage.objects. Object data now lives in Azure Blob; these
-- stub tables exist only so those migration statements succeed harmlessly.
CREATE SCHEMA IF NOT EXISTS storage;

CREATE TABLE IF NOT EXISTS storage.buckets (
    id               text PRIMARY KEY,
    name             text,
    public           boolean DEFAULT false,
    file_size_limit  bigint,
    allowed_mime_types text[],
    created_at       timestamptz DEFAULT now(),
    updated_at       timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS storage.objects (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket_id   text,
    name        text,
    owner       uuid,
    metadata    jsonb DEFAULT '{}'::jsonb,
    created_at  timestamptz DEFAULT now(),
    updated_at  timestamptz DEFAULT now()
);

-- storage.foldername() helper used by some Supabase storage RLS policies.
CREATE OR REPLACE FUNCTION storage.foldername(name text)
RETURNS text[]
LANGUAGE sql IMMUTABLE
AS $$ SELECT string_to_array(name, '/'); $$;

SELECT '✅ Migration 000: Azure bootstrap complete' AS status;
