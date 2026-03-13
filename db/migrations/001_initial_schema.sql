-- ============================================================================
-- MIGRATION 001: Initial Schema - Clean Slate for Potomac Analyst Workbench
-- ============================================================================
-- This is a complete schema for a fresh Supabase project.
-- Run on a fresh database only - not for migration of existing data.
-- ============================================================================

-- ============================================================================
-- SECTION 1: EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- ============================================================================
-- SECTION 2: STORAGE BUCKETS
-- ============================================================================
-- Supabase Storage uses storage.buckets and storage.objects tables
-- Insert bucket definitions directly

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES 
  -- User uploads: private, max 50MB, common document types
  ('user-uploads', 'user-uploads', false, 52428800, 
   ARRAY['application/pdf', 'text/plain', 'text/csv', 'application/json',
         'application/vnd.openxmlformats-officedocument.presentationml.presentation',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'image/png', 'image/jpeg', 'image/gif', 'image/webp']),
  -- Presentations: private, max 100MB, PowerPoint only
  ('presentations', 'presentations', false, 104857600,
   ARRAY['application/vnd.openxmlformats-officedocument.presentationml.presentation']),
  -- Brain documents: private, max 50MB, any type
  ('brain-docs', 'brain-docs', false, 52428800, null)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- SECTION 3: USER PROFILES TABLE
-- ============================================================================
-- Extends Supabase auth.users with app-specific data
-- Created automatically via trigger when user signs up

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Profile info
    email TEXT NOT NULL,
    name TEXT,
    nickname TEXT,
    avatar_url TEXT,
    
    -- Role & Status
    is_admin BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    
    -- Encrypted API keys (AES-256, prefixed with 'enc:')
    claude_api_key TEXT,
    tavily_api_key TEXT,
    
    -- Preferences
    preferences JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ,
    
    -- Constraints
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_profiles_created_at ON user_profiles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_profiles_last_active ON user_profiles(last_active_at DESC);

-- ============================================================================
-- SECTION 4: CONVERSATIONS & MESSAGES
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Conversation metadata
    title TEXT,
    summary TEXT,
    
    -- Context
    system_prompt TEXT,
    model TEXT DEFAULT 'claude-sonnet-4-20250514',
    
    -- State
    is_archived BOOLEAN DEFAULT false,
    is_pinned BOOLEAN DEFAULT false,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Token tracking
    total_tokens_used INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_archived ON conversations(user_id, is_archived) WHERE is_archived = false;

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    
    -- Message content
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    
    -- Token tracking
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    
    -- Tool usage
    tool_calls JSONB,
    tool_results JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(conversation_id, created_at);

-- ============================================================================
-- SECTION 5: FILE UPLOADS (Metadata only - actual files in Storage)
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Storage reference
    bucket_id TEXT NOT NULL,
    storage_path TEXT NOT NULL,  -- Path within bucket: user_id/filename
    
    -- File metadata
    original_filename TEXT NOT NULL,
    content_type TEXT,
    file_size INTEGER,
    
    -- Content hash for deduplication
    content_hash TEXT,
    
    -- Processing status
    status TEXT DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'ready', 'error')),
    error_message TEXT,
    
    -- Parsed content (for text-based files)
    extracted_text TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    UNIQUE(bucket_id, storage_path)
);

CREATE INDEX IF NOT EXISTS idx_file_uploads_user_id ON file_uploads(user_id);
CREATE INDEX IF NOT EXISTS idx_file_uploads_content_hash ON file_uploads(content_hash);
CREATE INDEX IF NOT EXISTS idx_file_uploads_status ON file_uploads(status);

-- ============================================================================
-- SECTION 6: CONVERSATION FILES (Junction table)
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversation_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES file_uploads(id) ON DELETE CASCADE,
    
    -- How the file is used in this conversation
    purpose TEXT DEFAULT 'reference',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(conversation_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_files_conversation ON conversation_files(conversation_id);

-- ============================================================================
-- SECTION 7: BRAIN DOCUMENTS (Knowledge Base)
-- ============================================================================

CREATE TABLE IF NOT EXISTS brain_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,  -- NULL = global document
    
    -- Storage reference
    bucket_id TEXT DEFAULT 'brain-docs',
    storage_path TEXT,
    
    -- Document info
    title TEXT NOT NULL,
    filename TEXT,
    content_type TEXT,
    file_size INTEGER,
    
    -- Content
    raw_content TEXT,
    summary TEXT,
    
    -- Classification
    category TEXT DEFAULT 'general',
    tags TEXT[] DEFAULT '{}',
    
    -- Search vector (for full-text search)
    search_vector tsvector,
    
    -- Embedding status
    is_processed BOOLEAN DEFAULT false,
    chunk_count INTEGER DEFAULT 0,
    
    -- Content hash
    content_hash TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_brain_documents_user_id ON brain_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_brain_documents_category ON brain_documents(category);
CREATE INDEX IF NOT EXISTS idx_brain_documents_tags ON brain_documents USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_brain_documents_search ON brain_documents USING GIN(search_vector);

-- Trigger to update search vector
CREATE OR REPLACE FUNCTION update_brain_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.summary, '')), 'B') ||
        setweight(to_tsvector('english', COALESCE(NEW.raw_content, '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS brain_documents_search_update ON brain_documents;
CREATE TRIGGER brain_documents_search_update
    BEFORE INSERT OR UPDATE ON brain_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_brain_search_vector();

-- ============================================================================
-- SECTION 8: AFL CODE & HISTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS afl_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Code info
    title TEXT NOT NULL,
    description TEXT,
    code TEXT NOT NULL,
    
    -- Classification
    strategy_type TEXT DEFAULT 'standalone',
    tags TEXT[] DEFAULT '{}',
    
    -- Validation
    is_valid BOOLEAN,
    validation_errors TEXT[],
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_afl_codes_user_id ON afl_codes(user_id);
CREATE INDEX IF NOT EXISTS idx_afl_codes_tags ON afl_codes USING GIN(tags);

CREATE TABLE IF NOT EXISTS afl_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Action
    action TEXT NOT NULL CHECK (action IN ('generate', 'debug', 'validate', 'explain')),
    
    -- Input/Output
    input_prompt TEXT,
    input_code TEXT,
    output_code TEXT,
    output_explanation TEXT,
    
    -- Context
    model TEXT,
    tokens_used INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_afl_history_user_id ON afl_history(user_id);
CREATE INDEX IF NOT EXISTS idx_afl_history_created_at ON afl_history(created_at DESC);

-- ============================================================================
-- SECTION 9: FEEDBACK & ANALYTICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    
    -- Context
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    
    -- Feedback
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    feedback_type TEXT CHECK (feedback_type IN ('rating', 'bug', 'feature', 'general')),
    comment TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON user_feedback(created_at DESC);

CREATE TABLE IF NOT EXISTS usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    
    -- Event info
    event_type TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    
    -- Usage metrics
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    
    -- Cost tracking (in cents)
    estimated_cost_cents INTEGER DEFAULT 0,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_user_id ON usage_events(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_events_type ON usage_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_events_created_at ON usage_events(created_at DESC);

-- ============================================================================
-- SECTION 10: PRESENTATIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS presentations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Storage reference
    storage_path TEXT,  -- Path in presentations bucket
    
    -- Info
    title TEXT NOT NULL,
    slide_count INTEGER,
    prompt TEXT,
    
    -- Status
    status TEXT DEFAULT 'generated' CHECK (status IN ('generating', 'generated', 'error')),
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_presentations_user_id ON presentations(user_id);
CREATE INDEX IF NOT EXISTS idx_presentations_created_at ON presentations(created_at DESC);

-- ============================================================================
-- SECTION 11: AUDIT LOGS
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    
    -- Action info
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    
    -- Request context
    ip_address INET,
    user_agent TEXT,
    
    -- Details
    old_values JSONB,
    new_values JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- ============================================================================
-- SECTION 12: ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- Enable RLS on all tables
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE file_uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE afl_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE afl_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE presentations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- User Profiles Policies
-- ============================================================================

CREATE POLICY "Users can read own profile"
    ON user_profiles FOR SELECT
    TO authenticated
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- ============================================================================
-- Conversations Policies
-- ============================================================================

CREATE POLICY "Users can manage own conversations"
    ON conversations FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- Messages Policies
-- ============================================================================

CREATE POLICY "Users can manage messages in own conversations"
    ON messages FOR ALL
    TO authenticated
    USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- ============================================================================
-- File Uploads Policies
-- ============================================================================

CREATE POLICY "Users can manage own file uploads"
    ON file_uploads FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- Conversation Files Policies
-- ============================================================================

CREATE POLICY "Users can access files in own conversations"
    ON conversation_files FOR ALL
    TO authenticated
    USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- ============================================================================
-- Brain Documents Policies
-- ============================================================================

-- Users can read global documents and their own
CREATE POLICY "Users can read accessible brain documents"
    ON brain_documents FOR SELECT
    TO authenticated
    USING (user_id IS NULL OR user_id = auth.uid());

-- Users can create own documents
CREATE POLICY "Users can create own brain documents"
    ON brain_documents FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

-- Users can update own documents
CREATE POLICY "Users can update own brain documents"
    ON brain_documents FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ============================================================================
-- AFL Policies
-- ============================================================================

CREATE POLICY "Users can manage own AFL codes"
    ON afl_codes FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can manage own AFL history"
    ON afl_history FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- Feedback & Analytics Policies
-- ============================================================================

CREATE POLICY "Users can manage own feedback"
    ON user_feedback FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can read own usage events"
    ON usage_events FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

-- Users can insert usage events (for tracking)
CREATE POLICY "Users can insert usage events"
    ON usage_events FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

-- ============================================================================
-- Presentations Policies
-- ============================================================================

CREATE POLICY "Users can manage own presentations"
    ON presentations FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ============================================================================
-- Audit Logs Policies (Read-only for admins)
-- ============================================================================

CREATE POLICY "Admins can read audit logs"
    ON audit_logs FOR SELECT
    TO authenticated
    USING (
        EXISTS (SELECT 1 FROM user_profiles WHERE id = auth.uid() AND is_admin = true)
    );

-- ============================================================================
-- SECTION 13: FUNCTIONS & TRIGGERS
-- ============================================================================

-- Auto-create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email, name, nickname)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(
            NEW.raw_user_meta_data->>'name',
            NEW.raw_user_meta_data->>'full_name',
            split_part(NEW.email, '@', 1)
        ),
        split_part(NEW.email, '@', 1)
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- Update updated_at timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations;
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

DROP TRIGGER IF EXISTS update_afl_codes_updated_at ON afl_codes;
CREATE TRIGGER update_afl_codes_updated_at
    BEFORE UPDATE ON afl_codes
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

DROP TRIGGER IF EXISTS update_brain_documents_updated_at ON brain_documents;
CREATE TRIGGER update_brain_documents_updated_at
    BEFORE UPDATE ON brain_documents
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at();

-- Audit log trigger (for sensitive tables)
CREATE OR REPLACE FUNCTION public.audit_log_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, new_values)
        VALUES (auth.uid(), 'INSERT', TG_TABLE_NAME, NEW.id::text, to_jsonb(NEW));
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, old_values, new_values)
        VALUES (auth.uid(), 'UPDATE', TG_TABLE_NAME, NEW.id::text, to_jsonb(OLD), to_jsonb(NEW));
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO audit_logs (user_id, action, resource_type, resource_id, old_values)
        VALUES (auth.uid(), 'DELETE', TG_TABLE_NAME, OLD.id::text, to_jsonb(OLD));
    END IF;
    RETURN NEW;
END;
$$;

-- Apply audit trigger to key tables
DROP TRIGGER IF EXISTS audit_user_profiles ON user_profiles;
CREATE TRIGGER audit_user_profiles
    AFTER INSERT OR UPDATE OR DELETE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.audit_log_trigger();

-- ============================================================================
-- SECTION 14: GRANTS
-- ============================================================================

-- Grant table permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Grant storage permissions
GRANT ALL ON storage.objects TO service_role;
GRANT INSERT, SELECT, DELETE ON storage.objects TO authenticated;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Schema created successfully!' AS status;