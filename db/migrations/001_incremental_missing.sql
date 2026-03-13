-- ============================================================================
-- INCREMENTAL MIGRATION: Create missing tables
-- ============================================================================
-- Run this to add missing tables to an existing database
-- Missing: file_uploads, usage_events, presentations, audit_logs
-- ============================================================================

-- ============================================================================
-- SECTION 1: EXTENSIONS (if not already installed)
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- SECTION 2: STORAGE BUCKETS
-- ============================================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES 
  ('user-uploads', 'user-uploads', false, 52428800, 
   ARRAY['application/pdf', 'text/plain', 'text/csv', 'application/json',
         'application/vnd.openxmlformats-officedocument.presentationml.presentation',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'image/png', 'image/jpeg', 'image/gif', 'image/webp']),
  ('presentations', 'presentations', false, 104857600,
   ARRAY['application/vnd.openxmlformats-officedocument.presentationml.presentation']),
  ('brain-docs', 'brain-docs', false, 52428800, null)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- SECTION 3: FILE UPLOADS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS file_uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Storage reference
    bucket_id TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    
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
-- SECTION 4: USAGE EVENTS TABLE
-- ============================================================================

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
-- SECTION 5: PRESENTATIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS presentations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    
    -- Storage reference
    storage_path TEXT,
    
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
-- SECTION 6: AUDIT LOGS TABLE
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
-- SECTION 7: RLS POLICIES FOR NEW TABLES
-- ============================================================================

-- Enable RLS
ALTER TABLE file_uploads ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE presentations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- File Uploads Policies
CREATE POLICY "Users can manage own file uploads"
    ON file_uploads FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Usage Events Policies
CREATE POLICY "Users can read own usage events"
    ON usage_events FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert usage events"
    ON usage_events FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

-- Presentations Policies
CREATE POLICY "Users can manage own presentations"
    ON presentations FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Audit Logs Policies
CREATE POLICY "Admins can read audit logs"
    ON audit_logs FOR SELECT
    TO authenticated
    USING (
        EXISTS (SELECT 1 FROM user_profiles WHERE id = auth.uid() AND is_admin = true)
    );

-- ============================================================================
-- SECTION 8: GRANTS
-- ============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Grant storage permissions
GRANT ALL ON storage.objects TO service_role;
GRANT INSERT, SELECT, DELETE ON storage.objects TO authenticated;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'Incremental migration complete!' AS status;