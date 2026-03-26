"""
Agent Teams V2 API Routes
=========================
Endpoints for creating and managing multi-agent teams with parallel execution,
custom roles, nicknames, and inter-agent communication.
"""

import logging
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-teams/v2", tags=["agent-teams-v2"])

VALID_ROLES = [
    "leader", "researcher", "analyst", "critic", "synthesizer",
    "coder", "writer", "designer", "translator", "expert",
]

VALID_WORKFLOW_MODES = ["sequential", "parallel", "hybrid"]


# ─── Request/Response Models ─────────────────────────────────────────────────────

class AgentConfigRequest(BaseModel):
    id: str = ""
    nickname: str = ""
    role: str = "researcher"
    model_id: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    custom_role_desc: str = ""
    instructions: str = ""
    color: str = ""
    capabilities: List[str] = []
    can_collaborate_with: List[str] = []

    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            return "researcher"
        return v


class CreateTeamRequest(BaseModel):
    name: str = "New Team"
    description: str = ""
    workflow_mode: str = "hybrid"
    allow_inter_agent_chat: bool = True
    agents: Optional[List[AgentConfigRequest]] = None

    @field_validator('workflow_mode')
    @classmethod
    def validate_workflow_mode(cls, v: str) -> str:
        if v not in VALID_WORKFLOW_MODES:
            return "hybrid"
        return v


class CreateTeamFromTemplateRequest(BaseModel):
    template_id: str
    name: str = ""
    description: str = ""
    overrides: Optional[dict] = None


class RunTaskRequest(BaseModel):
    task: str
    stream: bool = False
    max_rounds: int = 4


class UpdateAgentRequest(BaseModel):
    nickname: Optional[str] = None
    role: Optional[str] = None
    model_id: Optional[str] = None
    provider: Optional[str] = None
    custom_role_desc: Optional[str] = None
    instructions: Optional[str] = None
    color: Optional[str] = None
    capabilities: Optional[List[str]] = None
    can_collaborate_with: Optional[List[str]] = None


class AddAgentRequest(BaseModel):
    nickname: str = ""
    role: str = "researcher"
    model_id: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    custom_role_desc: str = ""
    instructions: str = ""
    color: str = ""
    capabilities: List[str] = []


class InterAgentMessageRequest(BaseModel):
    from_agent_id: str
    to_agent_id: Optional[str] = None
    content: str
    message_type: str = "question"


# ─── Endpoints ────────────────────────────────────────────────────────────────────

@router.post("/create")
async def create_team(request: CreateTeamRequest):
    """Create a new agent team with full configuration."""
    try:
        from db.supabase_client import get_supabase
        from core.agent_team_v2 import AgentConfig, ROLE_COLORS

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Get user from auth context
        user = supabase.auth.get_user()
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_id = user.user.id

        # Create team
        team_result = supabase.table("agent_teams").insert({
            "user_id": user_id,
            "name": request.name,
            "description": request.description,
            "status": "idle",
            "workflow_mode": request.workflow_mode,
            "allow_inter_agent_chat": request.allow_inter_agent_chat,
        }).execute()

        if not team_result.data:
            raise HTTPException(status_code=500, detail="Failed to create team")

        team_id = team_result.data[0]["id"]

        # Create agents
        agents_config = []
        if request.agents:
            for i, agent_req in enumerate(request.agents):
                agent_id = agent_req.id or f"agent_{i}_{team_id[:8]}"
                nickname = agent_req.nickname or agent_req.role.replace("_", " ").title()
                color = agent_req.color or ROLE_COLORS.get(agent_req.role, "#6B7280")
                capabilities = agent_req.capabilities or []

                supabase.table("agent_team_members").insert({
                    "team_id": team_id,
                    "agent_id": agent_id,
                    "nickname": nickname,
                    "role": agent_req.role,
                    "model_id": agent_req.model_id,
                    "provider": agent_req.provider,
                    "custom_role_desc": agent_req.custom_role_desc,
                    "instructions": agent_req.instructions,
                    "color": color,
                    "capabilities": json.dumps(capabilities),
                    "can_collaborate_with": json.dumps(agent_req.can_collaborate_with),
                }).execute()

                agents_config.append({
                    "id": agent_id,
                    "nickname": nickname,
                    "role": agent_req.role,
                    "model_id": agent_req.model_id,
                    "provider": agent_req.provider,
                    "color": color,
                    "capabilities": capabilities,
                })
        else:
            # Create default team
            from core.agent_team_v2 import create_default_team_config
            default_agents = create_default_team_config()
            for agent in default_agents:
                agent_id = f"agent_{default_agents.index(agent)}_{team_id[:8]}"
                supabase.table("agent_team_members").insert({
                    "team_id": team_id,
                    "agent_id": agent_id,
                    "nickname": agent.nickname,
                    "role": agent.role,
                    "model_id": agent.model_id,
                    "provider": agent.provider,
                    "custom_role_desc": "",
                    "instructions": "",
                    "color": agent.color,
                    "capabilities": json.dumps(agent.capabilities),
                    "can_collaborate_with": json.dumps([]),
                }).execute()

                agents_config.append({
                    "id": agent_id,
                    "nickname": agent.nickname,
                    "role": agent.role,
                    "model_id": agent.model_id,
                    "provider": agent.provider,
                    "color": agent.color,
                    "capabilities": agent.capabilities,
                })

        # Fetch created team with members
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        members = supabase.table("agent_team_members").select("*").eq("team_id", team_id).execute()

        return {
            "success": True,
            "team": team.data[0] if team.data else None,
            "agents": agents_config,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def list_templates():
    """List all available team templates."""
    try:
        from core.agent_team_v2 import list_available_templates
        templates = list_available_templates()
        return {
            "success": True,
            "templates": templates,
        }
    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-template")
async def create_team_from_template(request: CreateTeamFromTemplateRequest):
    """Create a team from a predefined template."""
    try:
        from db.supabase_client import get_supabase
        from core.agent_team_v2 import TEAM_TEMPLATES, AgentConfig, ROLE_COLORS

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        template = TEAM_TEMPLATES.get(request.template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{request.template_id}' not found")

        user = supabase.auth.get_user()
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        user_id = user.user.id

        # Use template defaults or overrides
        name = request.name or template["name"]
        description = request.description or template["description"]
        workflow_mode = template["workflow_mode"]

        # Create team
        team_result = supabase.table("agent_teams").insert({
            "user_id": user_id,
            "name": name,
            "description": description,
            "status": "idle",
            "workflow_mode": workflow_mode,
            "allow_inter_agent_chat": True,
        }).execute()

        if not team_result.data:
            raise HTTPException(status_code=500, detail="Failed to create team")

        team_id = team_result.data[0]["id"]

        # Create agents from template
        agents_config = []
        for i, agent_template in enumerate(template["agents"]):
            agent_id = f"agent_{i}_{team_id[:8]}"

            # Apply overrides if provided
            nickname = agent_template.nickname
            model_id = agent_template.model_id
            provider = agent_template.provider

            if request.overrides and request.overrides.get("agents"):
                agent_overrides = request.overrides["agents"]
                if i < len(agent_overrides):
                    override = agent_overrides[i]
                    nickname = override.get("nickname", nickname)
                    model_id = override.get("model_id", model_id)
                    provider = override.get("provider", provider)

            supabase.table("agent_team_members").insert({
                "team_id": team_id,
                "agent_id": agent_id,
                "nickname": nickname,
                "role": agent_template.role,
                "model_id": model_id,
                "provider": provider,
                "custom_role_desc": agent_template.custom_role_desc or "",
                "instructions": agent_template.instructions or "",
                "color": agent_template.color or ROLE_COLORS.get(agent_template.role, "#6B7280"),
                "capabilities": json.dumps(agent_template.capabilities or []),
                "can_collaborate_with": json.dumps([]),
            }).execute()

            agents_config.append({
                "id": agent_id,
                "nickname": nickname,
                "role": agent_template.role,
                "model_id": model_id,
                "provider": provider,
                "color": agent_template.color or ROLE_COLORS.get(agent_template.role, "#6B7280"),
            })

        # Fetch created team
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()

        return {
            "success": True,
            "team": team.data[0] if team.data else None,
            "agents": agents_config,
            "template_used": request.template_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team from template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_teams():
    """List all teams for the current user."""
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        user = supabase.auth.get_user()
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        teams = supabase.table("agent_teams").select(
            "*, agent_team_members(*)"
        ).eq("user_id", user.user.id).order("created_at", desc=True).execute()

        return {
            "success": True,
            "teams": teams.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing teams: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{team_id}")
async def get_team(team_id: str):
    """Get a specific team with its agents and recent messages."""
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        if not team.data:
            raise HTTPException(status_code=404, detail="Team not found")

        members = supabase.table("agent_team_members").select("*").eq("team_id", team_id).execute()
        messages = supabase.table("agent_messages").select("*").eq(
            "team_id", team_id
        ).order("created_at", desc=False).limit(100).execute()

        return {
            "success": True,
            "team": team.data[0],
            "agents": members.data or [],
            "messages": messages.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{team_id}/agents")
async def add_agent(team_id: str, request: AddAgentRequest):
    """Add a new agent to the team."""
    try:
        from db.supabase_client import get_supabase
        from core.agent_team_v2 import ROLE_COLORS

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Check team exists
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        if not team.data:
            raise HTTPException(status_code=404, detail="Team not found")

        agent_id = f"agent_{team_id[:8]}_{len(team.data)}"
        nickname = request.nickname or request.role.replace("_", " ").title()
        color = request.color or ROLE_COLORS.get(request.role, "#6B7280")

        supabase.table("agent_team_members").insert({
            "team_id": team_id,
            "agent_id": agent_id,
            "nickname": nickname,
            "role": request.role,
            "model_id": request.model_id,
            "provider": request.provider,
            "custom_role_desc": request.custom_role_desc,
            "instructions": request.instructions,
            "color": color,
            "capabilities": json.dumps(request.capabilities),
            "can_collaborate_with": json.dumps([]),
        }).execute()

        return {
            "success": True,
            "agent": {
                "id": agent_id,
                "nickname": nickname,
                "role": request.role,
                "model_id": request.model_id,
                "provider": request.provider,
                "color": color,
                "capabilities": request.capabilities,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{team_id}/agents/{agent_id}")
async def update_agent(team_id: str, agent_id: str, request: UpdateAgentRequest):
    """Update an agent in the team."""
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Build update dict
        update_data = {}
        if request.nickname is not None:
            update_data["nickname"] = request.nickname
        if request.role is not None:
            update_data["role"] = request.role
        if request.model_id is not None:
            update_data["model_id"] = request.model_id
        if request.provider is not None:
            update_data["provider"] = request.provider
        if request.custom_role_desc is not None:
            update_data["custom_role_desc"] = request.custom_role_desc
        if request.instructions is not None:
            update_data["instructions"] = request.instructions
        if request.color is not None:
            update_data["color"] = request.color
        if request.capabilities is not None:
            update_data["capabilities"] = json.dumps(request.capabilities)
        if request.can_collaborate_with is not None:
            update_data["can_collaborate_with"] = json.dumps(request.can_collaborate_with)

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = supabase.table("agent_team_members").update(update_data).eq(
            "team_id", team_id
        ).eq("agent_id", agent_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Agent not found")

        return {
            "success": True,
            "agent": result.data[0],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{team_id}/agents/{agent_id}")
async def remove_agent(team_id: str, agent_id: str):
    """Remove an agent from the team."""
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        result = supabase.table("agent_team_members").delete().eq(
            "team_id", team_id
        ).eq("agent_id", agent_id).execute()

        return {
            "success": True,
            "message": "Agent removed from team",
        }

    except Exception as e:
        logger.error(f"Error removing agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{team_id}/run")
async def run_team_task(team_id: str, request: RunTaskRequest):
    """Run a collaborative task with the agent team (parallel execution)."""
    try:
        from db.supabase_client import get_supabase
        from core.agent_team_v2 import AgentTeamV2, AgentConfig
        from core.llm import get_registry
        from config import get_settings

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        settings = get_settings()

        # Get team and agents
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        if not team.data:
            raise HTTPException(status_code=404, detail="Team not found")

        members = supabase.table("agent_team_members").select("*").eq("team_id", team_id).execute()

        # Update team status
        supabase.table("agent_teams").update({
            "status": "working",
            "task": request.task,
        }).eq("id", team_id).execute()

        # Save task message
        supabase.table("agent_messages").insert({
            "team_id": team_id,
            "from_role": "user",
            "to_role": None,
            "content": request.task,
            "message_type": "task",
        }).execute()

        # Initialize LLM registry
        api_keys = {}
        if settings.anthropic_api_key:
            api_keys["claude"] = settings.anthropic_api_key
        if settings.openai_api_key:
            api_keys["openai"] = settings.openai_api_key
        if settings.openrouter_api_key:
            api_keys["openrouter"] = settings.openrouter_api_key

        registry = get_registry(api_keys)

        # Create agent configs
        agent_configs = []
        for m in members.data:
            agent_configs.append(AgentConfig(
                id=m.get("agent_id", m["id"]),
                nickname=m.get("nickname", m["role"]),
                role=m["role"],
                model_id=m["model_id"],
                provider=m["provider"],
                custom_role_desc=m.get("custom_role_desc", ""),
                instructions=m.get("instructions", ""),
                color=m.get("color", "#6B7280"),
                capabilities=json.loads(m.get("capabilities", "[]")) if isinstance(m.get("capabilities"), str) else m.get("capabilities", []),
                can_collaborate_with=json.loads(m.get("can_collaborate_with", "[]")) if isinstance(m.get("can_collaborate_with"), str) else m.get("can_collaborate_with", []),
            ))

        # Create team instance
        workflow_mode = team.data[0].get("workflow_mode", "hybrid")
        allow_inter_agent_chat = team.data[0].get("allow_inter_agent_chat", True)

        agent_team = AgentTeamV2(
            team_id=team_id,
            user_id=team.data[0]["user_id"],
            agents=agent_configs,
            registry=registry,
            workflow_mode=workflow_mode,
            allow_inter_agent_chat=allow_inter_agent_chat,
        )

        if request.stream:
            # Streaming response using event queue
            events_queue = asyncio.Queue()

            async def callback(event):
                """Handle events and save to database."""
                await events_queue.put(event)

                # Save messages to database
                if event.get("type") == "agent_message":
                    try:
                        supabase.table("agent_messages").insert({
                            "team_id": team_id,
                            "from_role": event.get("role", "unknown"),
                            "to_role": None,
                            "content": event.get("content", ""),
                            "message_type": "answer",
                        }).execute()
                    except Exception as e:
                        logger.error(f"Failed to save agent message: {e}")

            async def stream_generator():
                # Start the task in background
                task_future = asyncio.create_task(
                    agent_team.run_collaborative_task(
                        task=request.task,
                        callback=callback,
                        max_rounds=request.max_rounds,
                    )
                )

                # Stream events as they come
                while True:
                    try:
                        # Wait for events with timeout
                        event = await asyncio.wait_for(events_queue.get(), timeout=0.1)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        # Check if task is done and queue is empty
                        if task_future.done() and events_queue.empty():
                            break
                        continue

                # Get the final result
                result = await task_future

                # Update team status
                supabase.table("agent_teams").update({
                    "status": "completed" if result.get("success") else "failed",
                    "result": json.dumps(result),
                }).eq("id", team_id).execute()

                yield f"data: {json.dumps({'type': 'done'})}\n\n"

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # Non-streaming response
            result = await agent_team.run_collaborative_task(
                task=request.task,
                max_rounds=request.max_rounds,
            )

            # Save all messages
            for msg in agent_team.messages:
                supabase.table("agent_messages").insert({
                    "team_id": team_id,
                    "from_role": msg.from_agent_id,
                    "to_role": msg.to_agent_id,
                    "content": msg.content,
                    "message_type": msg.message_type,
                }).execute()

            # Update team status
            supabase.table("agent_teams").update({
                "status": "completed" if result.get("success") else "failed",
                "result": json.dumps(result),
            }).eq("id", team_id).execute()

            return {
                "success": result.get("success", False),
                "result": result,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running team task: {e}", exc_info=True)
        # Update team status to failed
        try:
            from db.supabase_client import get_supabase
            supabase = get_supabase()
            if supabase:
                supabase.table("agent_teams").update({
                    "status": "failed",
                }).eq("id", team_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{team_id}/plan")
async def preview_execution_plan(team_id: str):
    """Preview the execution plan for a team without running it."""
    try:
        from db.supabase_client import get_supabase
        from core.agent_team_v2 import AgentTeamV2, AgentConfig

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Get team and agents
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        if not team.data:
            raise HTTPException(status_code=404, detail="Team not found")

        members = supabase.table("agent_team_members").select("*").eq("team_id", team_id).execute()

        # Create agent configs
        agent_configs = []
        for m in members.data:
            agent_configs.append(AgentConfig(
                id=m.get("agent_id", m["id"]),
                nickname=m.get("nickname", m["role"]),
                role=m["role"],
                model_id=m["model_id"],
                provider=m["provider"],
            ))

        # Create team instance to get plan
        workflow_mode = team.data[0].get("workflow_mode", "hybrid")
        agent_team = AgentTeamV2(
            team_id=team_id,
            user_id=team.data[0]["user_id"],
            agents=agent_configs,
            registry=None,
            workflow_mode=workflow_mode,
        )

        plan = await agent_team._create_execution_plan("Preview task")

        return {
            "success": True,
            "plan": {
                "workflow_mode": plan.workflow_mode,
                "reasoning": plan.reasoning,
                "phases": [
                    {
                        "phase_id": p.phase_id,
                        "agents": [
                            {
                                "id": a_id,
                                "nickname": agent_team.agents[a_id].nickname,
                                "role": agent_team.agents[a_id].role,
                            }
                            for a_id in p.agents if a_id in agent_team.agents
                        ],
                        "description": p.description,
                        "dependencies": p.dependencies,
                    }
                    for p in plan.phases
                ],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing plan: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{team_id}")
async def delete_team(team_id: str):
    """Delete a team and all its data."""
    try:
        from db.supabase_client import get_supabase

        supabase = get_supabase()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Delete messages first (foreign key constraint)
        supabase.table("agent_messages").delete().eq("team_id", team_id).execute()

        # Delete agents
        supabase.table("agent_team_members").delete().eq("team_id", team_id).execute()

        # Delete team
        supabase.table("agent_teams").delete().eq("id", team_id).execute()

        return {"success": True, "message": "Team deleted"}

    except Exception as e:
        logger.error(f"Error deleting team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))