-- Agent Teams Migration
-- Run this in your Supabase SQL Editor

-- Agent Teams table
CREATE TABLE IF NOT EXISTS agent_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'New Team',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'working', 'completed', 'failed')),
    task TEXT,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Team Members table
CREATE TABLE IF NOT EXISTS agent_team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES agent_teams(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('leader', 'researcher', 'analyst', 'critic', 'synthesizer', 'coder')),
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'anthropic',
    instructions TEXT,
    color TEXT DEFAULT '#FEC00F',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent Messages table (conversation history)
CREATE TABLE IF NOT EXISTS agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES agent_teams(id) ON DELETE CASCADE,
    from_role TEXT NOT NULL,
    to_role TEXT,  -- NULL means broadcast to all
    content TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'message' CHECK (message_type IN ('task', 'question', 'answer', 'critique', 'synthesis', 'sandbox_result', 'message')),
    metadata JSONB,  -- For sandbox outputs, tool results, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_agent_teams_user_id ON agent_teams(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_teams_status ON agent_teams(status);
CREATE INDEX IF NOT EXISTS idx_agent_team_members_team_id ON agent_team_members(team_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_team_id ON agent_messages(team_id);
CREATE INDEX IF NOT EXISTS idx_agent_messages_created_at ON agent_messages(created_at);

-- Row Level Security
ALTER TABLE agent_teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;

-- Policies: Users can only access their own teams
CREATE POLICY "Users can view their own teams" ON agent_teams
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own teams" ON agent_teams
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own teams" ON agent_teams
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own teams" ON agent_teams
    FOR DELETE USING (auth.uid() = user_id);

-- Team members: access through team ownership
CREATE POLICY "Users can view members of their teams" ON agent_team_members
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_team_members.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can add members to their teams" ON agent_team_members
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_team_members.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can update members of their teams" ON agent_team_members
    FOR UPDATE USING (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_team_members.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can delete members of their teams" ON agent_team_members
    FOR DELETE USING (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_team_members.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

-- Messages: access through team ownership
CREATE POLICY "Users can view messages of their teams" ON agent_messages
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_messages.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can add messages to their teams" ON agent_messages
    FOR INSERT WITH CHECK (
        EXISTS (
            SELECT 1 FROM agent_teams 
            WHERE agent_teams.id = agent_messages.team_id 
            AND agent_teams.user_id = auth.uid()
        )
    );

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_agent_teams_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_agent_teams_updated_at
    BEFORE UPDATE ON agent_teams
    FOR EACH ROW
    EXECUTE FUNCTION update_agent_teams_updated_at();