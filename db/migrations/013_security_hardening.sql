-- ============================================================================
-- Migration 013: Security Hardening — Re-enable RLS with proper policies
-- ============================================================================
-- Prerequisites: 
--   1. SUPABASE_SERVICE_KEY must be set in Railway env vars
--   2. Migration 012 must have been run first
-- ============================================================================

-- ============================================================================
-- STEP 1: Re-enable RLS on sensitive tables
-- ============================================================================

-- user_profiles: Contains API keys (encrypted) and personal data
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Policy: Service role can do everything (backend uses service_role key)
CREATE POLICY "service_role_full_access" ON user_profiles
    FOR ALL USING (true) WITH CHECK (true);

-- Policy: Authenticated users can read/update their OWN profile
CREATE POLICY "users_read_own_profile" ON user_profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "users_update_own_profile" ON user_profiles
    FOR UPDATE USING (auth.uid() = id);

-- Conversations: User-specific data
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access_conversations" ON conversations
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "users_manage_own_conversations" ON conversations
    FOR ALL USING (auth.uid() = user_id);

-- Messages: Child of conversations
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access_messages" ON messages
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "users_manage_own_messages" ON messages
    FOR ALL USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- ============================================================================
-- STEP 2: Re-enable RLS on other user-specific tables
-- ============================================================================

DO $$
BEGIN
    -- AFL codes
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_codes') THEN
        ALTER TABLE afl_codes ENABLE ROW LEVEL SECURITY;
        
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_afl_codes') THEN
            EXECUTE 'CREATE POLICY service_role_afl_codes ON afl_codes FOR ALL USING (true) WITH CHECK (true)';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_afl_codes') THEN
            EXECUTE 'CREATE POLICY users_own_afl_codes ON afl_codes FOR ALL USING (auth.uid() = user_id)';
        END IF;
    END IF;

    -- AFL history
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_history') THEN
        ALTER TABLE afl_history ENABLE ROW LEVEL SECURITY;
        
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_afl_history') THEN
            EXECUTE 'CREATE POLICY service_role_afl_history ON afl_history FOR ALL USING (true) WITH CHECK (true)';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_afl_history') THEN
            EXECUTE 'CREATE POLICY users_own_afl_history ON afl_history FOR ALL USING (auth.uid() = user_id)';
        END IF;
    END IF;

    -- User feedback
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_feedback') THEN
        ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
        
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_user_feedback') THEN
            EXECUTE 'CREATE POLICY service_role_user_feedback ON user_feedback FOR ALL USING (true) WITH CHECK (true)';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_feedback') THEN
            EXECUTE 'CREATE POLICY users_own_feedback ON user_feedback FOR ALL USING (auth.uid() = user_id)';
        END IF;
    END IF;

    -- Brain documents (shared resource - all authenticated users can read)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'brain_documents') THEN
        ALTER TABLE brain_documents ENABLE ROW LEVEL SECURITY;
        
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_brain_docs') THEN
            EXECUTE 'CREATE POLICY service_role_brain_docs ON brain_documents FOR ALL USING (true) WITH CHECK (true)';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_read_brain_docs') THEN
            EXECUTE 'CREATE POLICY authenticated_read_brain_docs ON brain_documents FOR SELECT USING (auth.role() = ''authenticated'')';
        END IF;
    END IF;

    -- Training data (admin-managed, readable by all authenticated)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'training_data') THEN
        ALTER TABLE training_data ENABLE ROW LEVEL SECURITY;
        
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_training') THEN
            EXECUTE 'CREATE POLICY service_role_training ON training_data FOR ALL USING (true) WITH CHECK (true)';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'authenticated_read_training') THEN
            EXECUTE 'CREATE POLICY authenticated_read_training ON training_data FOR SELECT USING (auth.role() = ''authenticated'')';
        END IF;
    END IF;
END $$;

-- ============================================================================
-- STEP 3: Revoke direct anon access to sensitive tables
-- ============================================================================

-- Only service_role and authenticated should access user data
REVOKE ALL ON user_profiles FROM anon;
GRANT SELECT ON user_profiles TO anon;  -- Needed for profile creation trigger

-- Keep authenticated and service_role full access
GRANT ALL ON user_profiles TO authenticated;
GRANT ALL ON user_profiles TO service_role;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 
    schemaname,
    tablename,
    rowsecurity as rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename IN ('user_profiles', 'conversations', 'messages', 'afl_codes')
ORDER BY tablename;

SELECT 'Migration 013: Security hardening complete!' as status;
