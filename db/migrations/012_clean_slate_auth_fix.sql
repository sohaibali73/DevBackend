
-- ============================================================================
-- Migration 012: Clean Slate - Delete Old Data & Fix Auth
-- ============================================================================
-- WARNING: This deletes ALL existing conversations, messages, and user data
-- that was associated with the old users table.
-- After this, only Supabase Auth users will work.
-- ============================================================================

-- ============================================================================
-- STEP 1: Drop ALL foreign key constraints (so we can delete safely)
-- ============================================================================

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_user_id_fkey;
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_user_id_users_fkey;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_codes' AND column_name = 'user_id') THEN
        ALTER TABLE afl_codes DROP CONSTRAINT IF EXISTS afl_codes_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_history' AND column_name = 'user_id') THEN
        ALTER TABLE afl_history DROP CONSTRAINT IF EXISTS fk_afl_history_user;
        ALTER TABLE afl_history DROP CONSTRAINT IF EXISTS afl_history_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_uploaded_files' AND column_name = 'user_id') THEN
        ALTER TABLE afl_uploaded_files DROP CONSTRAINT IF EXISTS fk_afl_uploaded_files_user;
        ALTER TABLE afl_uploaded_files DROP CONSTRAINT IF EXISTS afl_uploaded_files_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_settings_presets' AND column_name = 'user_id') THEN
        ALTER TABLE afl_settings_presets DROP CONSTRAINT IF EXISTS afl_settings_presets_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'reverse_engineer_history' AND column_name = 'user_id') THEN
        ALTER TABLE reverse_engineer_history DROP CONSTRAINT IF EXISTS fk_reverse_engineer_history_user;
        ALTER TABLE reverse_engineer_history DROP CONSTRAINT IF EXISTS reverse_engineer_history_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_feedback' AND column_name = 'user_id') THEN
        ALTER TABLE user_feedback DROP CONSTRAINT IF EXISTS user_feedback_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'training_suggestions' AND column_name = 'user_id') THEN
        ALTER TABLE training_suggestions DROP CONSTRAINT IF EXISTS training_suggestions_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'analytics_events' AND column_name = 'user_id') THEN
        ALTER TABLE analytics_events DROP CONSTRAINT IF EXISTS analytics_events_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'content_items' AND column_name = 'user_id') THEN
        ALTER TABLE content_items DROP CONSTRAINT IF EXISTS content_items_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'writing_styles' AND column_name = 'user_id') THEN
        ALTER TABLE writing_styles DROP CONSTRAINT IF EXISTS writing_styles_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'backtest_results' AND column_name = 'user_id') THEN
        ALTER TABLE backtest_results DROP CONSTRAINT IF EXISTS backtest_results_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'brain_documents' AND column_name = 'uploaded_by') THEN
        ALTER TABLE brain_documents DROP CONSTRAINT IF EXISTS brain_documents_uploaded_by_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'learnings' AND column_name = 'user_id') THEN
        ALTER TABLE learnings DROP CONSTRAINT IF EXISTS learnings_user_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'training_data' AND column_name = 'created_by') THEN
        ALTER TABLE training_data DROP CONSTRAINT IF EXISTS training_data_created_by_fkey;
    END IF;
END $$;

-- ============================================================================
-- STEP 2: Delete ALL old data (clean slate)
-- ============================================================================

-- Delete messages first (child of conversations)
DELETE FROM messages;

-- Delete conversation files
DELETE FROM conversation_files WHERE TRUE;

-- Delete all conversations
DELETE FROM conversations;

-- Delete other user data
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_codes') THEN DELETE FROM afl_codes; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_history') THEN DELETE FROM afl_history; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_uploaded_files') THEN DELETE FROM afl_uploaded_files; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_settings_presets') THEN DELETE FROM afl_settings_presets; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'reverse_engineer_history') THEN DELETE FROM reverse_engineer_history; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_feedback') THEN DELETE FROM user_feedback; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'training_suggestions') THEN DELETE FROM training_suggestions; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'analytics_events') THEN DELETE FROM analytics_events; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'content_items') THEN DELETE FROM content_items; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'writing_styles') THEN DELETE FROM writing_styles; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'backtest_results') THEN DELETE FROM backtest_results; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'learnings') THEN DELETE FROM learnings; END IF;
END $$;

-- Drop the old users table (replace with auth.users)
DROP TABLE IF EXISTS users CASCADE;

-- ============================================================================
-- STEP 3: Create user_profiles table linked to auth.users
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT,
    nickname TEXT,
    avatar_url TEXT,
    claude_api_key TEXT,
    tavily_api_key TEXT,
    preferences JSONB DEFAULT '{}'::jsonb,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW()
);

-- Populate user_profiles from existing auth.users
INSERT INTO user_profiles (id, name, nickname, is_admin)
SELECT 
    id,
    COALESCE(raw_user_meta_data->>'name', raw_user_meta_data->>'full_name', split_part(email, '@', 1)),
    split_part(email, '@', 1),
    email IN ('sohaib.ali@potomac.com', 'jamiecatrina9@gmail.com')
FROM auth.users
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- STEP 4: Disable RLS on user_profiles (backend handles authorization)
-- ============================================================================

-- DISABLE RLS - the Python backend handles all authorization via JWT validation.
-- RLS is not needed since the frontend never directly accesses the database.
ALTER TABLE user_profiles DISABLE ROW LEVEL SECURITY;

-- Drop any existing policies
DROP POLICY IF EXISTS "Users can read own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON user_profiles;
DROP POLICY IF EXISTS "Service role full access" ON user_profiles;

-- Grant access to all roles for backend operations
GRANT ALL ON user_profiles TO anon;
GRANT ALL ON user_profiles TO authenticated;
GRANT ALL ON user_profiles TO service_role;

-- ============================================================================
-- STEP 5: Create trigger to auto-create profile for new auth users
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
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
        split_part(NEW.email, '@', 1),
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
-- STEP 6: Fix foreign keys to point to auth.users
-- ============================================================================

-- conversations
ALTER TABLE conversations ADD CONSTRAINT conversations_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Other tables (only if they exist and have user_id)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_codes' AND column_name = 'user_id') THEN
        ALTER TABLE afl_codes ADD CONSTRAINT afl_codes_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_history' AND column_name = 'user_id') THEN
        ALTER TABLE afl_history ADD CONSTRAINT fk_afl_history_user
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_uploaded_files' AND column_name = 'user_id') THEN
        ALTER TABLE afl_uploaded_files ADD CONSTRAINT fk_afl_uploaded_files_user
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'afl_settings_presets' AND column_name = 'user_id') THEN
        ALTER TABLE afl_settings_presets ADD CONSTRAINT afl_settings_presets_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'reverse_engineer_history' AND column_name = 'user_id') THEN
        ALTER TABLE reverse_engineer_history ADD CONSTRAINT fk_reverse_engineer_history_user
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_feedback' AND column_name = 'user_id') THEN
        ALTER TABLE user_feedback ADD CONSTRAINT user_feedback_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'training_suggestions' AND column_name = 'user_id') THEN
        ALTER TABLE training_suggestions ADD CONSTRAINT training_suggestions_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'analytics_events' AND column_name = 'user_id') THEN
        ALTER TABLE analytics_events ADD CONSTRAINT analytics_events_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'content_items' AND column_name = 'user_id') THEN
        ALTER TABLE content_items ADD CONSTRAINT content_items_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'writing_styles' AND column_name = 'user_id') THEN
        ALTER TABLE writing_styles ADD CONSTRAINT writing_styles_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'backtest_results' AND column_name = 'user_id') THEN
        ALTER TABLE backtest_results ADD CONSTRAINT backtest_results_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'brain_documents' AND column_name = 'uploaded_by') THEN
        ALTER TABLE brain_documents ADD CONSTRAINT brain_documents_uploaded_by_fkey
            FOREIGN KEY (uploaded_by) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'learnings' AND column_name = 'user_id') THEN
        ALTER TABLE learnings ADD CONSTRAINT learnings_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'training_data' AND column_name = 'created_by') THEN
        ALTER TABLE training_data ADD CONSTRAINT training_data_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ============================================================================
-- STEP 7: Disable RLS on all tables (backend handles authorization via JWT)
-- ============================================================================

-- The Python backend validates JWT tokens and filters data by user_id.
-- RLS is not needed and causes issues without service_role key.

ALTER TABLE conversations DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can manage own conversations" ON conversations;
DROP POLICY IF EXISTS "Service role full access to conversations" ON conversations;
GRANT ALL ON conversations TO anon;
GRANT ALL ON conversations TO authenticated;
GRANT ALL ON conversations TO service_role;

ALTER TABLE messages DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can manage own messages" ON messages;
DROP POLICY IF EXISTS "Service role full access to messages" ON messages;
GRANT ALL ON messages TO anon;
GRANT ALL ON messages TO authenticated;
GRANT ALL ON messages TO service_role;

-- Disable RLS on conversation_files too
ALTER TABLE conversation_files DISABLE ROW LEVEL SECURITY;
GRANT ALL ON conversation_files TO anon;
GRANT ALL ON conversation_files TO authenticated;
GRANT ALL ON conversation_files TO service_role;

-- Disable RLS on other tables the backend needs
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_codes') THEN ALTER TABLE afl_codes DISABLE ROW LEVEL SECURITY; GRANT ALL ON afl_codes TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'afl_history') THEN ALTER TABLE afl_history DISABLE ROW LEVEL SECURITY; GRANT ALL ON afl_history TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_feedback') THEN ALTER TABLE user_feedback DISABLE ROW LEVEL SECURITY; GRANT ALL ON user_feedback TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'training_data') THEN ALTER TABLE training_data DISABLE ROW LEVEL SECURITY; GRANT ALL ON training_data TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'training_suggestions') THEN ALTER TABLE training_suggestions DISABLE ROW LEVEL SECURITY; GRANT ALL ON training_suggestions TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'analytics_events') THEN ALTER TABLE analytics_events DISABLE ROW LEVEL SECURITY; GRANT ALL ON analytics_events TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'brain_documents') THEN ALTER TABLE brain_documents DISABLE ROW LEVEL SECURITY; GRANT ALL ON brain_documents TO anon, authenticated, service_role; END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'learnings') THEN ALTER TABLE learnings DISABLE ROW LEVEL SECURITY; GRANT ALL ON learnings TO anon, authenticated, service_role; END IF;
END $$;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Auth users:' as info, COUNT(*) as count FROM auth.users
UNION ALL
SELECT 'User profiles:' as info, COUNT(*) as count FROM user_profiles
UNION ALL
SELECT 'Conversations:' as info, COUNT(*) as count FROM conversations;

SELECT 
    tc.table_name, 
    tc.constraint_name, 
    ccu.table_schema || '.' || ccu.table_name AS foreign_table
FROM information_schema.table_constraints AS tc 
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND tc.table_name IN ('conversations', 'messages', 'afl_codes', 'afl_history')
ORDER BY tc.table_name;

SELECT 'Migration 012 completed successfully!' as status;
