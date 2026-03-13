-- ============================================================================
-- Migration 014: SECURE REBUILD — Single Source of Truth for Database Security
-- ============================================================================
-- This migration establishes the CORRECT final security state.
-- It replaces the contradictory toggles in migrations 012 and 013.
--
-- SECURITY MODEL:
--   1. Backend uses service_role key → automatically bypasses RLS (no policies needed)
--   2. RLS is ENABLED on all user-data tables as defense-in-depth
--   3. Policies scope authenticated users to their OWN data only
--   4. anon role is DENIED access to all sensitive tables
--   5. Shared resources (training_data, brain_documents) are read-only for authenticated
--
-- IMPORTANT: service_role bypasses RLS automatically in Supabase.
--   DO NOT create "USING (true)" catch-all policies — they open access to ALL roles.
-- ============================================================================

-- ============================================================================
-- STEP 1: Drop ALL existing policies (clean slate for policies only)
-- ============================================================================

-- user_profiles
DROP POLICY IF EXISTS "service_role_full_access" ON user_profiles;
DROP POLICY IF EXISTS "users_read_own_profile" ON user_profiles;
DROP POLICY IF EXISTS "users_update_own_profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can read own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON user_profiles;
DROP POLICY IF EXISTS "Service role full access" ON user_profiles;

-- conversations
DROP POLICY IF EXISTS "service_role_full_access_conversations" ON conversations;
DROP POLICY IF EXISTS "users_manage_own_conversations" ON conversations;
DROP POLICY IF EXISTS "Users can manage own conversations" ON conversations;
DROP POLICY IF EXISTS "Service role full access to conversations" ON conversations;

-- messages
DROP POLICY IF EXISTS "service_role_full_access_messages" ON messages;
DROP POLICY IF EXISTS "users_manage_own_messages" ON messages;
DROP POLICY IF EXISTS "Users can manage own messages" ON messages;
DROP POLICY IF EXISTS "Service role full access to messages" ON messages;

-- conversation_files
DROP POLICY IF EXISTS "service_role_conversation_files" ON conversation_files;
DROP POLICY IF EXISTS "users_own_conversation_files" ON conversation_files;

-- afl tables
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_codes') THEN
        DROP POLICY IF EXISTS "service_role_afl_codes" ON afl_codes;
        DROP POLICY IF EXISTS "users_own_afl_codes" ON afl_codes;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_history') THEN
        DROP POLICY IF EXISTS "service_role_afl_history" ON afl_history;
        DROP POLICY IF EXISTS "users_own_afl_history" ON afl_history;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_uploaded_files') THEN
        DROP POLICY IF EXISTS "service_role_afl_uploaded_files" ON afl_uploaded_files;
        DROP POLICY IF EXISTS "users_own_afl_uploaded_files" ON afl_uploaded_files;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_settings_presets') THEN
        DROP POLICY IF EXISTS "service_role_afl_settings" ON afl_settings_presets;
        DROP POLICY IF EXISTS "users_own_afl_settings" ON afl_settings_presets;
    END IF;
END $$;

-- feedback / analytics / suggestions
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_feedback') THEN
        DROP POLICY IF EXISTS "service_role_user_feedback" ON user_feedback;
        DROP POLICY IF EXISTS "users_own_feedback" ON user_feedback;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_suggestions') THEN
        DROP POLICY IF EXISTS "service_role_training_suggestions" ON training_suggestions;
        DROP POLICY IF EXISTS "users_own_suggestions" ON training_suggestions;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='analytics_events') THEN
        DROP POLICY IF EXISTS "service_role_analytics" ON analytics_events;
        DROP POLICY IF EXISTS "users_own_analytics" ON analytics_events;
    END IF;
END $$;

-- shared resources
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_documents') THEN
        DROP POLICY IF EXISTS "service_role_brain_docs" ON brain_documents;
        DROP POLICY IF EXISTS "authenticated_read_brain_docs" ON brain_documents;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_data') THEN
        DROP POLICY IF EXISTS "service_role_training" ON training_data;
        DROP POLICY IF EXISTS "authenticated_read_training" ON training_data;
        DROP POLICY IF EXISTS "Anyone can read active training data" ON training_data;
        DROP POLICY IF EXISTS "Admins can manage all training data" ON training_data;
    END IF;
END $$;

-- other user tables
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='reverse_engineer_history') THEN
        DROP POLICY IF EXISTS "service_role_re_history" ON reverse_engineer_history;
        DROP POLICY IF EXISTS "users_own_re_history" ON reverse_engineer_history;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='content_items') THEN
        DROP POLICY IF EXISTS "service_role_content" ON content_items;
        DROP POLICY IF EXISTS "users_own_content" ON content_items;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='writing_styles') THEN
        DROP POLICY IF EXISTS "service_role_writing" ON writing_styles;
        DROP POLICY IF EXISTS "users_own_writing" ON writing_styles;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='backtest_results') THEN
        DROP POLICY IF EXISTS "service_role_backtest" ON backtest_results;
        DROP POLICY IF EXISTS "users_own_backtest" ON backtest_results;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learnings') THEN
        DROP POLICY IF EXISTS "service_role_learnings" ON learnings;
        DROP POLICY IF EXISTS "users_own_learnings" ON learnings;
    END IF;
END $$;

-- ============================================================================
-- STEP 2: Revoke ALL grants to anon on sensitive tables
-- ============================================================================
-- The anon key is PUBLIC in Supabase. Anyone can use it.
-- anon should NEVER have direct access to user data.
-- ============================================================================

REVOKE ALL ON user_profiles FROM anon;
REVOKE ALL ON conversations FROM anon;
REVOKE ALL ON messages FROM anon;
REVOKE ALL ON conversation_files FROM anon;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_codes') THEN
        REVOKE ALL ON afl_codes FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_history') THEN
        REVOKE ALL ON afl_history FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_uploaded_files') THEN
        REVOKE ALL ON afl_uploaded_files FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_settings_presets') THEN
        REVOKE ALL ON afl_settings_presets FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='reverse_engineer_history') THEN
        REVOKE ALL ON reverse_engineer_history FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_feedback') THEN
        REVOKE ALL ON user_feedback FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_suggestions') THEN
        REVOKE ALL ON training_suggestions FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='analytics_events') THEN
        REVOKE ALL ON analytics_events FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='content_items') THEN
        REVOKE ALL ON content_items FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='writing_styles') THEN
        REVOKE ALL ON writing_styles FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='backtest_results') THEN
        REVOKE ALL ON backtest_results FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learnings') THEN
        REVOKE ALL ON learnings FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_documents') THEN
        REVOKE ALL ON brain_documents FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_document_chunks') THEN
        REVOKE ALL ON brain_document_chunks FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_data') THEN
        REVOKE ALL ON training_data FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_metrics') THEN
        REVOKE ALL ON ai_metrics FROM anon;
    END IF;
END $$;

-- ============================================================================
-- STEP 3: Enable RLS on ALL user-data tables
-- ============================================================================

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_files ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_codes') THEN
        ALTER TABLE afl_codes ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_history') THEN
        ALTER TABLE afl_history ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_uploaded_files') THEN
        ALTER TABLE afl_uploaded_files ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_settings_presets') THEN
        ALTER TABLE afl_settings_presets ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='reverse_engineer_history') THEN
        ALTER TABLE reverse_engineer_history ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_feedback') THEN
        ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_suggestions') THEN
        ALTER TABLE training_suggestions ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='analytics_events') THEN
        ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='content_items') THEN
        ALTER TABLE content_items ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='writing_styles') THEN
        ALTER TABLE writing_styles ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='backtest_results') THEN
        ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learnings') THEN
        ALTER TABLE learnings ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_documents') THEN
        ALTER TABLE brain_documents ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_document_chunks') THEN
        ALTER TABLE brain_document_chunks ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_data') THEN
        ALTER TABLE training_data ENABLE ROW LEVEL SECURITY;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_metrics') THEN
        ALTER TABLE ai_metrics ENABLE ROW LEVEL SECURITY;
    END IF;
END $$;

-- ============================================================================
-- STEP 4: Create PROPERLY SCOPED policies for authenticated users
-- ============================================================================
-- NOTE: service_role key bypasses RLS automatically. No policies needed for it.
-- These policies ONLY allow authenticated users to access their OWN data.
-- ============================================================================

-- user_profiles: users can read and update ONLY their own profile
CREATE POLICY "auth_read_own_profile" ON user_profiles
    FOR SELECT TO authenticated
    USING (auth.uid() = id);

CREATE POLICY "auth_update_own_profile" ON user_profiles
    FOR UPDATE TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- conversations: users can CRUD their own conversations
CREATE POLICY "auth_own_conversations" ON conversations
    FOR ALL TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- messages: users can access messages in their own conversations
CREATE POLICY "auth_own_messages" ON messages
    FOR ALL TO authenticated
    USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- conversation_files: users can access files in their own conversations
CREATE POLICY "auth_own_conversation_files" ON conversation_files
    FOR ALL TO authenticated
    USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- ============================================================================
-- STEP 5: Policies for AFL tables (user-scoped)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_codes') THEN
        EXECUTE 'CREATE POLICY "auth_own_afl_codes" ON afl_codes FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_history') THEN
        EXECUTE 'CREATE POLICY "auth_own_afl_history" ON afl_history FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_uploaded_files') THEN
        EXECUTE 'CREATE POLICY "auth_own_afl_files" ON afl_uploaded_files FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_settings_presets') THEN
        EXECUTE 'CREATE POLICY "auth_own_afl_settings" ON afl_settings_presets FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
END $$;

-- ============================================================================
-- STEP 6: Policies for feedback / analytics / suggestions (user-scoped)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_feedback') THEN
        EXECUTE 'CREATE POLICY "auth_own_feedback" ON user_feedback FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_suggestions') THEN
        EXECUTE 'CREATE POLICY "auth_own_suggestions" ON training_suggestions FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='analytics_events') THEN
        EXECUTE 'CREATE POLICY "auth_own_analytics" ON analytics_events FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
END $$;

-- ============================================================================
-- STEP 7: Policies for other user-scoped tables
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='reverse_engineer_history') THEN
        EXECUTE 'CREATE POLICY "auth_own_re_history" ON reverse_engineer_history FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='content_items') THEN
        EXECUTE 'CREATE POLICY "auth_own_content" ON content_items FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='writing_styles') THEN
        EXECUTE 'CREATE POLICY "auth_own_writing" ON writing_styles FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='backtest_results') THEN
        EXECUTE 'CREATE POLICY "auth_own_backtest" ON backtest_results FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learnings') THEN
        EXECUTE 'CREATE POLICY "auth_own_learnings" ON learnings FOR ALL TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)';
    END IF;
END $$;

-- ============================================================================
-- STEP 8: Policies for SHARED resources (read-only for authenticated)
-- ============================================================================
-- brain_documents and training_data are shared across all users.
-- authenticated users can READ, only service_role (backend) can WRITE.
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_documents') THEN
        EXECUTE 'CREATE POLICY "auth_read_brain_docs" ON brain_documents FOR SELECT TO authenticated USING (true)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_document_chunks') THEN
        EXECUTE 'CREATE POLICY "auth_read_brain_chunks" ON brain_document_chunks FOR SELECT TO authenticated USING (true)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_data') THEN
        EXECUTE 'CREATE POLICY "auth_read_training" ON training_data FOR SELECT TO authenticated USING (true)';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_metrics') THEN
        EXECUTE 'CREATE POLICY "auth_read_metrics" ON ai_metrics FOR SELECT TO authenticated USING (true)';
    END IF;
END $$;

-- ============================================================================
-- STEP 9: Ensure proper grants for authenticated and service_role
-- ============================================================================
-- authenticated needs table-level grants (RLS policies then restrict rows)
-- service_role needs full access (and bypasses RLS automatically)
-- ============================================================================

GRANT SELECT, UPDATE ON user_profiles TO authenticated;
GRANT ALL ON user_profiles TO service_role;

GRANT ALL ON conversations TO authenticated;
GRANT ALL ON conversations TO service_role;

GRANT ALL ON messages TO authenticated;
GRANT ALL ON messages TO service_role;

GRANT ALL ON conversation_files TO authenticated;
GRANT ALL ON conversation_files TO service_role;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_codes') THEN
        GRANT ALL ON afl_codes TO authenticated; GRANT ALL ON afl_codes TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_history') THEN
        GRANT ALL ON afl_history TO authenticated; GRANT ALL ON afl_history TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_uploaded_files') THEN
        GRANT ALL ON afl_uploaded_files TO authenticated; GRANT ALL ON afl_uploaded_files TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='afl_settings_presets') THEN
        GRANT ALL ON afl_settings_presets TO authenticated; GRANT ALL ON afl_settings_presets TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='reverse_engineer_history') THEN
        GRANT ALL ON reverse_engineer_history TO authenticated; GRANT ALL ON reverse_engineer_history TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='user_feedback') THEN
        GRANT ALL ON user_feedback TO authenticated; GRANT ALL ON user_feedback TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_suggestions') THEN
        GRANT ALL ON training_suggestions TO authenticated; GRANT ALL ON training_suggestions TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='analytics_events') THEN
        GRANT ALL ON analytics_events TO authenticated; GRANT ALL ON analytics_events TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='content_items') THEN
        GRANT ALL ON content_items TO authenticated; GRANT ALL ON content_items TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='writing_styles') THEN
        GRANT ALL ON writing_styles TO authenticated; GRANT ALL ON writing_styles TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='backtest_results') THEN
        GRANT ALL ON backtest_results TO authenticated; GRANT ALL ON backtest_results TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learnings') THEN
        GRANT ALL ON learnings TO authenticated; GRANT ALL ON learnings TO service_role;
    END IF;
    -- Shared resources: read-only for authenticated, full for service_role
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_documents') THEN
        GRANT SELECT ON brain_documents TO authenticated; GRANT ALL ON brain_documents TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='brain_document_chunks') THEN
        GRANT SELECT ON brain_document_chunks TO authenticated; GRANT ALL ON brain_document_chunks TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='training_data') THEN
        GRANT SELECT ON training_data TO authenticated; GRANT ALL ON training_data TO service_role;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_metrics') THEN
        GRANT SELECT ON ai_metrics TO authenticated; GRANT ALL ON ai_metrics TO service_role;
    END IF;
END $$;

-- ============================================================================
-- STEP 10: Ensure profile auto-creation trigger is SECURITY DEFINER
-- ============================================================================
-- The trigger must run as the owner (bypassing RLS) to create profiles
-- for new auth.users signups.
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
        COALESCE(
            NEW.raw_user_meta_data->>'name',
            NEW.raw_user_meta_data->>'full_name',
            split_part(NEW.email, '@', 1)
        ),
        split_part(NEW.email, '@', 1),
        NEW.email IN ('sohaib.ali@potomac.com', 'jamiecatrina9@gmail.com')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

-- Recreate trigger (idempotent)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- VERIFICATION: Check RLS is enabled and policies are correct
-- ============================================================================

SELECT
    schemaname,
    tablename,
    rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename IN (
        'user_profiles', 'conversations', 'messages', 'conversation_files',
        'afl_codes', 'afl_history', 'user_feedback', 'brain_documents',
        'training_data'
    )
ORDER BY tablename;

-- List all policies
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;

SELECT '✅ Migration 014: Secure rebuild complete!' AS status;
