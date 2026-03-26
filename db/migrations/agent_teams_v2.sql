-- Agent Teams V2 Migration
-- Adds support for parallel execution, custom roles, nicknames, and inter-agent communication

-- Add new columns to agent_teams table
DO $$
BEGIN
    -- Add workflow_mode column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_teams' AND column_name = 'workflow_mode') THEN
        ALTER TABLE agent_teams ADD COLUMN workflow_mode TEXT DEFAULT 'hybrid';
    END IF;

    -- Add allow_inter_agent_chat column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_teams' AND column_name = 'allow_inter_agent_chat') THEN
        ALTER TABLE agent_teams ADD COLUMN allow_inter_agent_chat BOOLEAN DEFAULT true;
    END IF;
END $$;

-- Add new columns to agent_team_members table
DO $$
BEGIN
    -- Add agent_id column (unique identifier for the agent within the team)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_team_members' AND column_name = 'agent_id') THEN
        ALTER TABLE agent_team_members ADD COLUMN agent_id TEXT;
    END IF;

    -- Add nickname column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_team_members' AND column_name = 'nickname') THEN
        ALTER TABLE agent_team_members ADD COLUMN nickname TEXT;
    END IF;

    -- Add custom_role_desc column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_team_members' AND column_name = 'custom_role_desc') THEN
        ALTER TABLE agent_team_members ADD COLUMN custom_role_desc TEXT DEFAULT '';
    END IF;

    -- Add capabilities column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_team_members' AND column_name = 'capabilities') THEN
        ALTER TABLE agent_team_members ADD COLUMN capabilities JSONB DEFAULT '[]';
    END IF;

    -- Add can_collaborate_with column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_team_members' AND column_name = 'can_collaborate_with') THEN
        ALTER TABLE agent_team_members ADD COLUMN can_collaborate_with JSONB DEFAULT '[]';
    END IF;
END $$;

-- Create agent_inter_messages table for inter-agent communication
CREATE TABLE IF NOT EXISTS agent_inter_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES agent_teams(id) ON DELETE CASCADE,
    from_agent_id TEXT NOT NULL,
    to_agent_id TEXT,  -- NULL means broadcast to all agents
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'question',  -- question, answer, feedback, request, broadcast
    requires_response BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_agent_inter_messages_team_id ON agent_inter_messages(team_id);
CREATE INDEX IF NOT EXISTS idx_agent_inter_messages_created_at ON agent_inter_messages(created_at);

-- Create index for agent_team_members agent_id
CREATE INDEX IF NOT EXISTS idx_agent_team_members_agent_id ON agent_team_members(agent_id);

-- Update existing agent_team_members records to have agent_id if they don't
UPDATE agent_team_members 
SET agent_id = 'agent_' || SUBSTRING(id::text FROM 1 FOR 8)
WHERE agent_id IS NULL;

-- Update existing agent_team_members records to have nickname if they don't
UPDATE agent_team_members 
SET nickname = INITCAP(REPLACE(role, '_', ' '))
WHERE nickname IS NULL;

-- Update existing agent_team_members records to have capabilities if they're empty
UPDATE agent_team_members 
SET capabilities = CASE 
    WHEN role = 'leader' THEN '["plan", "coordinate", "delegate", "synthesize"]'::jsonb
    WHEN role = 'researcher' THEN '["research", "search", "gather", "cite"]'::jsonb
    WHEN role = 'analyst' THEN '["analyze", "calculate", "code", "visualize"]'::jsonb
    WHEN role = 'critic' THEN '["review", "challenge", "evaluate", "suggest"]'::jsonb
    WHEN role = 'synthesizer' THEN '["combine", "structure", "write", "summarize"]'::jsonb
    WHEN role = 'coder' THEN '["code", "debug", "test", "execute"]'::jsonb
    WHEN role = 'writer' THEN '["write", "edit", "proofread", "format"]'::jsonb
    WHEN role = 'designer' THEN '["design", "visualize", "layout", "style"]'::jsonb
    WHEN role = 'translator' THEN '["translate", "localize", "adapt"]'::jsonb
    WHEN role = 'expert' THEN '["advise", "consult", "specialize"]'::jsonb
    ELSE '["general"]'::jsonb
END
WHERE capabilities = '[]'::jsonb OR capabilities IS NULL;