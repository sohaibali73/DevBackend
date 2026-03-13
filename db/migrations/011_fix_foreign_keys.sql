-- ============================================================================
-- Migration 011: Fix Foreign Keys to use auth.users
-- ============================================================================
-- Run EACH section separately in Supabase SQL Editor
-- ============================================================================

-- ============================================================================
-- PART 1: Create user_profiles table (RUN THIS FIRST)
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT,
    nickname TEXT,
    avatar_url TEXT,
    claude_api_key_encrypted BYTEA,
    tavily_api_key_encrypted BYTEA,
    preferences JSONB DEFAULT '{}'::jsonb,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- PART 2: Enable pgcrypto and create functions (RUN THIS SECOND)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION encrypt_api_key(plaintext TEXT, encryption_key TEXT)
RETURNS BYTEA
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF plaintext IS NULL OR plaintext = '' THEN
        RETURN NULL;
    END IF;
    RETURN pg_sym_encrypt(plaintext, encryption_key, 'cipher=aes-256-gcm');
END;
$$;

CREATE OR REPLACE FUNCTION decrypt_api_key(ciphertext BYTEA, encryption_key TEXT)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF ciphertext IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN pg_sym_decrypt(ciphertext, encryption_key, 'cipher=aes-256-gcm');
END;
$$;

-- ============================================================================
-- PART 3: Create user profile trigger (RUN THIS THIRD)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO public.user_profiles (id, name, nickname, is_admin)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        COALESCE(NEW.raw_user_meta_data->>'nickname', split_part(NEW.email, '@', 1)),
        NEW.email IN ('sohaib.ali@potomac.com', 'jamiecatrina9@gmail.com')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- PART 4: Enable RLS on user_profiles (RUN THIS FOURTH)
-- ============================================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
DROP POLICY IF EXISTS "Service role full access" ON user_profiles;

CREATE POLICY "Users can read own profile" ON user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON user_profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Service role full access" ON user_profiles FOR ALL USING (auth.role() = 'service_role');

GRANT ALL ON user_profiles TO authenticated;
GRANT ALL ON user_profiles TO service_role;

-- ============================================================================
-- PART 5: Fix conversations table foreign key (RUN THIS FIFTH)
-- ============================================================================

-- First, check what tables exist and their structure
SELECT table_name, column_name 
FROM information_schema.columns 
WHERE table_name IN ('conversations', 'messages', 'afl_codes', 'afl_history')
ORDER BY table_name, column_name;

-- Drop the old foreign key constraint on conversations
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_user_id_fkey;

-- Clean up orphaned conversations (users not in auth.users)
DELETE FROM conversations WHERE user_id NOT IN (SELECT id FROM auth.users);

-- Add new foreign key pointing to auth.users
ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- ============================================================================
-- PART 6: Fix messages table (if it has user_id column)
-- ============================================================================

-- Check if messages has user_id column
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'messages' AND column_name = 'user_id';

-- If the above returns a row, run these:
-- ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_user_id_fkey;
-- DELETE FROM messages WHERE user_id NOT IN (SELECT id FROM auth.users);
-- ALTER TABLE messages ADD CONSTRAINT messages_user_id_fkey
--     FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- ============================================================================
-- PART 7: Fix other tables (run as needed)
-- ============================================================================

-- afl_codes
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_codes' AND column_name = 'user_id') THEN
        ALTER TABLE afl_codes DROP CONSTRAINT IF EXISTS afl_codes_user_id_fkey;
        DELETE FROM afl_codes WHERE user_id NOT IN (SELECT id FROM auth.users);
        ALTER TABLE afl_codes ADD CONSTRAINT afl_codes_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- afl_history
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_history' AND column_name = 'user_id') THEN
        ALTER TABLE afl_history DROP CONSTRAINT IF EXISTS fk_afl_history_user;
        DELETE FROM afl_history WHERE user_id NOT IN (SELECT id FROM auth.users);
        ALTER TABLE afl_history ADD CONSTRAINT fk_afl_history_user
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ============================================================================
-- DONE! Verify the fix:
-- ============================================================================

SELECT 
    tc.table_name, 
    tc.constraint_name, 
    ccu.table_name AS foreign_table
FROM information_schema.table_constraints AS tc 
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND tc.table_name = 'conversations';