-- ============================================================================
-- Migration 010: Supabase Auth Integration with Data Encryption
-- ============================================================================
-- This migration rebuilds the auth infrastructure to use Supabase's built-in
-- authentication system with proper encryption for sensitive data.
--
-- Features:
-- - Uses Supabase Auth (auth.users) for authentication
-- - Encrypts sensitive data (API keys) at rest using pgcrypto
-- - Proper RLS policies using auth.uid()
-- - Secure password handling via Supabase Auth
-- - TLS/SSL encryption in transit (handled by Supabase)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- 1. Create user_profiles table (extends auth.users)
-- ============================================================================
-- This table stores additional user data and links to Supabase Auth
-- Sensitive fields are encrypted using pgcrypto

DROP TABLE IF EXISTS user_profiles CASCADE;
DROP TABLE IF EXISTS password_resets CASCADE;  -- No longer needed with Supabase Auth

CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Public profile data (not encrypted)
    name TEXT,
    nickname TEXT,
    avatar_url TEXT,
    
    -- Encrypted sensitive data (API keys)
    -- These are encrypted using pgcrypto's pg_sym_encrypt
    claude_api_key_encrypted BYTEA,
    tavily_api_key_encrypted BYTEA,
    
    -- User preferences
    preferences JSONB DEFAULT '{}'::jsonb,
    
    -- Admin flag
    is_admin BOOLEAN DEFAULT FALSE,
    
    -- Account status
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX idx_user_profiles_is_admin ON user_profiles(is_admin) WHERE is_admin = TRUE;
CREATE INDEX idx_user_profiles_created_at ON user_profiles(created_at DESC);

-- ============================================================================
-- 2. Create encryption key management
-- ============================================================================
-- The encryption key is derived from a server-side secret
-- In production, this should be stored in a secure vault (e.g., Supabase Vault)

-- Create a schema for encryption functions (accessible only to service role)
CREATE SCHEMA IF NOT EXISTS auth_private;

-- Function to get encryption key
-- This key should be set via environment variable and passed from the backend
CREATE OR REPLACE FUNCTION auth_private.get_encryption_key()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- The key is retrieved from a secure configuration
    -- In production, use Supabase Vault or similar
    -- This is a placeholder - the actual key is passed from the backend
    RETURN current_setting('app.encryption_key', true);
END;
$$;

-- Function to encrypt sensitive data
CREATE OR REPLACE FUNCTION auth_private.encrypt_value(plaintext TEXT)
RETURNS BYTEA
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    key TEXT;
BEGIN
    key := auth_private.get_encryption_key();
    IF key IS NULL OR key = '' THEN
        RAISE EXCEPTION 'Encryption key not configured';
    END IF;
    RETURN pg_sym_encrypt(plaintext, key, 'cipher=aes-256-gcm');
END;
$$;

-- Function to decrypt sensitive data
CREATE OR REPLACE FUNCTION auth_private.decrypt_value(ciphertext BYTEA)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    key TEXT;
BEGIN
    key := auth_private.get_encryption_key();
    IF key IS NULL OR key = '' THEN
        RAISE EXCEPTION 'Encryption key not configured';
    END IF;
    RETURN pg_sym_decrypt(ciphertext, key, 'cipher=aes-256-gcm');
END;
$$;

-- Public functions for use by service role (with encryption key set)
CREATE OR REPLACE FUNCTION encrypt_api_key(plaintext TEXT, encryption_key TEXT)
RETURNS BYTEA
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
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
SET search_path = public
AS $$
BEGIN
    IF ciphertext IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN pg_sym_decrypt(ciphertext, encryption_key, 'cipher=aes-256-gcm');
END;
$$;

-- ============================================================================
-- 3. Create trigger to auto-create user profile on auth.users insert
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.user_profiles (id, name, nickname, is_admin)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        COALESCE(NEW.raw_user_meta_data->>'nickname', split_part(NEW.email, '@', 1)),
        -- Check if email is in admin list
        NEW.email IN (
            'sohaib.ali@potomac.com'
            -- Add more admin emails as needed
        )
    );
    RETURN NEW;
END;
$$;

-- Drop existing trigger if any
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Create trigger
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- 4. Create updated_at trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_user_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_profiles_updated_at ON user_profiles;
CREATE TRIGGER user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_user_profiles_updated_at();

-- ============================================================================
-- 5. Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own profile
CREATE POLICY "Users can read own profile"
    ON user_profiles FOR SELECT
    USING (auth.uid() = id);

-- Users can update their own profile (except is_admin)
CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Service role can do everything (for backend operations)
CREATE POLICY "Service role full access"
    ON user_profiles FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ============================================================================
-- 6. Update existing tables to use auth.users.id
-- ============================================================================

-- Update conversations table
ALTER TABLE conversations 
    DROP CONSTRAINT IF EXISTS conversations_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE conversations
    ADD CONSTRAINT conversations_user_id_fkey 
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update messages table
ALTER TABLE messages
    DROP CONSTRAINT IF EXISTS messages_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE messages
    ADD CONSTRAINT messages_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update afl_codes table
ALTER TABLE afl_codes
    DROP CONSTRAINT IF EXISTS afl_codes_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE afl_codes
    ADD CONSTRAINT afl_codes_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update afl_history table
ALTER TABLE afl_history
    DROP CONSTRAINT IF EXISTS fk_afl_history_user,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE afl_history
    ADD CONSTRAINT fk_afl_history_user
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update afl_uploaded_files table
ALTER TABLE afl_uploaded_files
    DROP CONSTRAINT IF EXISTS fk_afl_uploaded_files_user,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE afl_uploaded_files
    ADD CONSTRAINT fk_afl_uploaded_files_user
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update afl_settings_presets table
ALTER TABLE afl_settings_presets
    DROP CONSTRAINT IF EXISTS afl_settings_presets_user_id_fkey;

ALTER TABLE afl_settings_presets
    ADD CONSTRAINT afl_settings_presets_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update reverse_engineer_history table
ALTER TABLE reverse_engineer_history
    DROP CONSTRAINT IF EXISTS fk_reverse_engineer_history_user,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE reverse_engineer_history
    ADD CONSTRAINT fk_reverse_engineer_history_user
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update training_data table
ALTER TABLE training_data
    DROP CONSTRAINT IF EXISTS training_data_created_by_fkey;

ALTER TABLE training_data
    ADD CONSTRAINT training_data_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;

-- Update user_feedback table
ALTER TABLE user_feedback
    DROP CONSTRAINT IF EXISTS user_feedback_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE user_feedback
    ADD CONSTRAINT user_feedback_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update training_suggestions table
ALTER TABLE training_suggestions
    DROP CONSTRAINT IF EXISTS training_suggestions_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE training_suggestions
    ADD CONSTRAINT training_suggestions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update analytics_events table
ALTER TABLE analytics_events
    DROP CONSTRAINT IF EXISTS analytics_events_user_id_fkey,
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE analytics_events
    ADD CONSTRAINT analytics_events_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update content_items table
ALTER TABLE content_items
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE content_items
    ADD CONSTRAINT content_items_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update writing_styles table
ALTER TABLE writing_styles
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE writing_styles
    ADD CONSTRAINT writing_styles_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update backtest_results table
ALTER TABLE backtest_results
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE backtest_results
    ADD CONSTRAINT backtest_results_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Update brain_documents table
ALTER TABLE brain_documents
    ALTER COLUMN uploaded_by TYPE UUID USING uploaded_by::UUID;

ALTER TABLE brain_documents
    ADD CONSTRAINT brain_documents_uploaded_by_fkey
    FOREIGN KEY (uploaded_by) REFERENCES auth.users(id) ON DELETE SET NULL;

-- Update learnings table
ALTER TABLE learnings
    ALTER COLUMN user_id TYPE UUID USING user_id::UUID;

ALTER TABLE learnings
    ADD CONSTRAINT learnings_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;

-- Update strategies table (if exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'strategies') THEN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'strategies' AND column_name = 'user_id') THEN
            ALTER TABLE strategies
                ALTER COLUMN user_id TYPE UUID USING user_id::UUID;
            
            ALTER TABLE strategies
                ADD CONSTRAINT strategies_user_id_fkey
                FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
        END IF;
    END IF;
END $$;

-- ============================================================================
-- 7. Update RLS policies to use auth.uid() properly
-- ============================================================================

-- Drop old policies that used current_setting
DROP POLICY IF EXISTS afl_history_select_policy ON afl_history;
DROP POLICY IF EXISTS afl_history_insert_policy ON afl_history;
DROP POLICY IF EXISTS afl_history_delete_policy ON afl_history;
DROP POLICY IF EXISTS reverse_engineer_history_select_policy ON reverse_engineer_history;
DROP POLICY IF EXISTS reverse_engineer_history_insert_policy ON reverse_engineer_history;
DROP POLICY IF EXISTS reverse_engineer_history_delete_policy ON reverse_engineer_history;
DROP POLICY IF EXISTS afl_uploaded_files_select_policy ON afl_uploaded_files;
DROP POLICY IF EXISTS afl_uploaded_files_insert_policy ON afl_uploaded_files;
DROP POLICY IF EXISTS afl_uploaded_files_delete_policy ON afl_uploaded_files;

-- Create new policies using auth.uid()
CREATE POLICY "Users can read own afl_history"
    ON afl_history FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own afl_history"
    ON afl_history FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own afl_history"
    ON afl_history FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can read own reverse_engineer_history"
    ON reverse_engineer_history FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own reverse_engineer_history"
    ON reverse_engineer_history FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own reverse_engineer_history"
    ON reverse_engineer_history FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can read own uploaded files"
    ON afl_uploaded_files FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own uploaded files"
    ON afl_uploaded_files FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own uploaded files"
    ON afl_uploaded_files FOR DELETE
    USING (auth.uid() = user_id);

-- Update content_items policies
DROP POLICY IF EXISTS content_items_all ON content_items;
CREATE POLICY "Users can read own content"
    ON content_items FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own content"
    ON content_items FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own content"
    ON content_items FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own content"
    ON content_items FOR DELETE
    USING (auth.uid() = user_id);

-- Update writing_styles policies
DROP POLICY IF EXISTS writing_styles_all ON writing_styles;
CREATE POLICY "Users can read own writing styles"
    ON writing_styles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own writing styles"
    ON writing_styles FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own writing styles"
    ON writing_styles FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own writing styles"
    ON writing_styles FOR DELETE
    USING (auth.uid() = user_id);

-- Update backtest_results policies
DROP POLICY IF EXISTS backtest_results_all ON backtest_results;
CREATE POLICY "Users can read own backtest results"
    ON backtest_results FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own backtest results"
    ON backtest_results FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own backtest results"
    ON backtest_results FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own backtest results"
    ON backtest_results FOR DELETE
    USING (auth.uid() = user_id);

-- Update brain_documents policies
DROP POLICY IF EXISTS brain_documents_all ON brain_documents;
CREATE POLICY "Users can read brain documents"
    ON brain_documents FOR SELECT
    USING (auth.uid() = uploaded_by OR uploaded_by IS NULL);

CREATE POLICY "Users can insert brain documents"
    ON brain_documents FOR INSERT
    WITH CHECK (auth.uid() = uploaded_by);

CREATE POLICY "Users can update own brain documents"
    ON brain_documents FOR UPDATE
    USING (auth.uid() = uploaded_by);

CREATE POLICY "Users can delete own brain documents"
    ON brain_documents FOR DELETE
    USING (auth.uid() = uploaded_by);

-- Update learnings policies
DROP POLICY IF EXISTS learnings_all ON learnings;
CREATE POLICY "Users can read own learnings"
    ON learnings FOR SELECT
    USING (auth.uid() = user_id OR user_id IS NULL);

CREATE POLICY "Users can insert own learnings"
    ON learnings FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own learnings"
    ON learnings FOR DELETE
    USING (auth.uid() = user_id);

-- Update brain_chunks policies
DROP POLICY IF EXISTS brain_chunks_all ON brain_chunks;
CREATE POLICY "Users can read brain chunks"
    ON brain_chunks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM brain_documents bd
            WHERE bd.id = brain_chunks.document_id
            AND (bd.uploaded_by = auth.uid() OR bd.uploaded_by IS NULL)
        )
    );

-- ============================================================================
-- 8. Create helper functions for user management
-- ============================================================================

-- Function to check if user is admin
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM user_profiles
        WHERE id = auth.uid() AND is_admin = TRUE
    );
END;
$$;

-- Function to get user's decrypted API keys (for service role only)
CREATE OR REPLACE FUNCTION get_user_api_keys(user_id UUID, encryption_key TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    result JSONB;
    claude_key TEXT;
    tavily_key TEXT;
BEGIN
    -- Only service role can call this
    IF auth.role() != 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized';
    END IF;
    
    SELECT 
        claude_api_key_encrypted,
        tavily_api_key_encrypted
    INTO claude_key, tavily_key
    FROM user_profiles
    WHERE id = user_id;
    
    result := jsonb_build_object(
        'claude', CASE WHEN claude_key IS NOT NULL 
                       THEN decrypt_api_key(claude_key::BYTEA, encryption_key)
                       ELSE NULL END,
        'tavily', CASE WHEN tavily_key IS NOT NULL 
                      THEN decrypt_api_key(tavily_key::BYTEA, encryption_key)
                      ELSE NULL END
    );
    
    RETURN result;
END;
$$;

-- Function to set user's encrypted API keys
CREATE OR REPLACE FUNCTION set_user_api_keys(
    user_id UUID,
    claude_key TEXT,
    tavily_key TEXT,
    encryption_key TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Only service role can call this
    IF auth.role() != 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized';
    END IF;
    
    UPDATE user_profiles
    SET 
        claude_api_key_encrypted = CASE WHEN claude_key IS NOT NULL AND claude_key != ''
                                        THEN encrypt_api_key(claude_key, encryption_key)
                                        ELSE NULL END,
        tavily_api_key_encrypted = CASE WHEN tavily_key IS NOT NULL AND tavily_key != ''
                                        THEN encrypt_api_key(tavily_key, encryption_key)
                                        ELSE NULL END,
        updated_at = NOW()
    WHERE id = user_id;
END;
$$;

-- ============================================================================
-- 9. Create view for admin user management
-- ============================================================================

CREATE OR REPLACE VIEW admin_user_list AS
SELECT 
    up.id,
    u.email,
    up.name,
    up.nickname,
    up.is_admin,
    up.is_active,
    up.created_at,
    up.last_active_at,
    up.preferences
FROM user_profiles up
JOIN auth.users u ON u.id = up.id
ORDER BY up.created_at DESC;

-- Grant access to admins only
CREATE POLICY "Admins can view user list"
    ON admin_user_list FOR SELECT
    USING (is_admin());

-- ============================================================================
-- 10. Grant permissions
-- ============================================================================

-- Grant usage on sequences
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Grant table permissions
GRANT ALL ON user_profiles TO authenticated;
GRANT ALL ON user_profiles TO service_role;

GRANT ALL ON afl_history TO authenticated;
GRANT ALL ON afl_history TO service_role;

GRANT ALL ON reverse_engineer_history TO authenticated;
GRANT ALL ON reverse_engineer_history TO service_role;

GRANT ALL ON afl_uploaded_files TO authenticated;
GRANT ALL ON afl_uploaded_files TO service_role;

GRANT ALL ON afl_settings_presets TO authenticated;
GRANT ALL ON afl_settings_presets TO service_role;

GRANT ALL ON content_items TO authenticated;
GRANT ALL ON content_items TO service_role;

GRANT ALL ON writing_styles TO authenticated;
GRANT ALL ON writing_styles TO service_role;

GRANT ALL ON backtest_results TO authenticated;
GRANT ALL ON backtest_results TO service_role;

GRANT ALL ON brain_documents TO authenticated;
GRANT ALL ON brain_documents TO service_role;

GRANT ALL ON brain_chunks TO authenticated;
GRANT ALL ON brain_chunks TO service_role;

GRANT ALL ON learnings TO authenticated;
GRANT ALL ON learnings TO service_role;

-- ============================================================================
-- 11. Data migration from old users table (if exists)
-- ============================================================================

-- Migrate existing users to user_profiles
-- Note: Passwords cannot be migrated - users will need to reset passwords
DO $$
DECLARE
    old_user RECORD;
    new_user_id UUID;
BEGIN
    -- Check if old users table exists
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        FOR old_user IN SELECT * FROM users LOOP
            -- Check if user already exists in auth.users by email
            SELECT id INTO new_user_id FROM auth.users WHERE email = old_user.email;
            
            IF new_user_id IS NULL THEN
                -- User doesn't exist in auth.users - they'll need to re-register
                -- Log this for admin attention
                RAISE NOTICE 'User % needs to re-register in Supabase Auth', old_user.email;
            ELSE
                -- User exists - update their profile
                INSERT INTO user_profiles (id, name, nickname, is_admin, created_at, last_active_at)
                VALUES (
                    new_user_id,
                    old_user.name,
                    old_user.nickname,
                    old_user.is_admin OR FALSE,
                    old_user.created_at,
                    old_user.last_active
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, user_profiles.name),
                    nickname = COALESCE(EXCLUDED.nickname, user_profiles.nickname),
                    is_admin = EXCLUDED.is_admin OR user_profiles.is_admin;
            END IF;
        END LOOP;
    END IF;
END $$;

-- ============================================================================
-- 12. Drop old users table (after migration)
-- ============================================================================
-- Uncomment this after verifying the migration is successful
-- DROP TABLE IF EXISTS users CASCADE;

-- ============================================================================
-- Done! The database is now configured for Supabase Auth with encryption.
-- ============================================================================
-- 
-- Next steps:
-- 1. Set the ENCRYPTION_KEY environment variable in your backend
-- 2. Update the auth routes to use Supabase Auth SDK
-- 3. Update the frontend to use Supabase Auth client
-- 4. Users will need to reset their passwords (passwords cannot be migrated)
-- ============================================================================

COMMENT ON TABLE user_profiles IS 'User profile data extending auth.users with encrypted API keys';
COMMENT ON COLUMN user_profiles.claude_api_key_encrypted IS 'AES-256-GCM encrypted Claude API key';
COMMENT ON COLUMN user_profiles.tavily_api_key_encrypted IS 'AES-256-GCM encrypted Tavily API key';
COMMENT ON FUNCTION encrypt_api_key IS 'Encrypts an API key using AES-256-GCM';
COMMENT ON FUNCTION decrypt_api_key IS 'Decrypts an API key that was encrypted with encrypt_api_key';
COMMENT ON FUNCTION is_admin IS 'Returns true if the current user is an admin';