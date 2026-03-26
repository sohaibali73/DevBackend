"""
Agent Teams API Routes
======================
Endpoints for creating and managing multi-agent teams.
"""

import logging
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-teams", tags=["agent-teams"])


class TeamMemberCreate(BaseModel):
    role: str
    model_id: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    instructions: str = ""
    color: str = "#FEC00F"


class CreateTeamRequest(BaseModel):
    name: str = "New Team"
    description: str = ""
    members: Optional[List[TeamMemberCreate]] = None


class RunTaskRequest(BaseModel):
    task: str
    stream: bool = False


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    members: list
    created_at: str


@router.post("/create")
async def create_team(request: CreateTeamRequest):
    """Create a new agent team."""
    try:
        from db.supabase_client import get_supabase_client
        from core.agent_team import create_default_team_config

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Get user from auth context (simplified - in production, use proper auth)
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
        }).execute()

        if not team_result.data:
            raise HTTPException(status_code=500, detail="Failed to create team")

        team_id = team_result.data[0]["id"]

        # Create members
        members_config = (
            [m.dict() for m in request.members]
            if request.members
            else create_default_team_config()
        )

        for member in members_config:
            supabase.table("agent_team_members").insert({
                "team_id": team_id,
                "role": member.get("role", "leader"),
                "model_id": member.get("model_id", "claude-sonnet-4-20250514"),
                "provider": member.get("provider", "anthropic"),
                "instructions": member.get("instructions", ""),
                "color": member.get("color", "#FEC00F"),
            }).execute()

        # Fetch created team with members
        team = supabase.table("agent_teams").select("*").eq("id", team_id).execute()
        members = supabase.table("agent_team_members").select("*").eq("team_id", team_id).execute()

        return {
            "success": True,
            "team": team.data[0] if team.data else None,
            "members": members.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_teams():
    """List all teams for the current user."""
    try:
        from db.supabase_client import get_supabase_client

        supabase = get_supabase_client()
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
    """Get a specific team with its members and recent messages."""
    try:
        from db.supabase_client import get_supabase_client

        supabase = get_supabase_client()
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
            "members": members.data or [],
            "messages": messages.data or [],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{team_id}/run")
async def run_team_task(team_id: str, request: RunTaskRequest):
    """Run a collaborative task with the agent team."""
    try:
        from db.supabase_client import get_supabase_client
        from core.agent_team import AgentTeam
        from core.llm import get_registry
        from config import get_settings

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        settings = get_settings()

        # Get team and members
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

        # Create team instance
        agent_team = AgentTeam(
            team_id=team_id,
            user_id=team.data[0]["user_id"],
            members=[{
                "role": m["role"],
                "model_id": m["model_id"],
                "provider": m["provider"],
                "instructions": m.get("instructions", ""),
                "color": m.get("color", "#FEC00F"),
            } for m in members.data],
            registry=registry,
        )

        if request.stream:
            # Streaming response
            async def stream_generator():
                async def callback(event):
                    event_data = json.dumps(event)
                    yield f"data: {event_data}\n\n"

                    # Save messages to database
                    if event.get("type") == "agent_message":
                        supabase.table("agent_messages").insert({
                            "team_id": team_id,
                            "from_role": event.get("role", "unknown"),
                            "to_role": None,
                            "content": event.get("content", ""),
                            "message_type": "answer",
                        }).execute()

                result = await agent_team.run_collaborative_task(
                    task=request.task,
                    callback=callback,
                )

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
            result = await agent_team.run_collaborative_task(task=request.task)

            # Save all messages
            for msg in agent_team.conversation:
                supabase.table("agent_messages").insert({
                    "team_id": team_id,
                    "from_role": msg.get("from_role", "unknown"),
                    "to_role": msg.get("to_role"),
                    "content": msg.get("content", ""),
                    "message_type": msg.get("message_type", "message"),
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
            from db.supabase_client import get_supabase_client
            supabase = get_supabase_client()
            if supabase:
                supabase.table("agent_teams").update({
                    "status": "failed",
                }).eq("id", team_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{team_id}")
async def delete_team(team_id: str):
    """Delete a team and all its data."""
    try:
        from db.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(status_code=500, detail="Database not available")

        # Delete messages first (foreign key constraint)
        supabase.table("agent_messages").delete().eq("team_id", team_id).execute()

        # Delete members
        supabase.table("agent_team_members").delete().eq("team_id", team_id).execute()

        # Delete team
        supabase.table("agent_teams").delete().eq("id", team_id).execute()

        return {"success": True, "message": "Team deleted"}

    except Exception as e:
        logger.error(f"Error deleting team: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))