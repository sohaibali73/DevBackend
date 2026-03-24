"""
AI Router — Vercel AI SDK streaming endpoints for Claude Skills
================================================================
Provides /ai/skills/{slug} which invokes a registered Claude custom beta
skill and streams the response in the Vercel AI SDK Data Stream Protocol
format, making it directly consumable by useChat() / useCompletion() on
the Next.js / React frontend.

Stream protocol lines (one per newline):
    0:"text chunk"              ← text delta
    2:[{...}]                   ← data parts (file downloads, metadata)
    3:"error message"           ← error
    d:{finishReason, usage}     ← finish message

Router prefix: /ai
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI SDK"])


# ── Request model ─────────────────────────────────────────────────────────────

class SkillInvokeRequest(BaseModel):
    """Request body for POST /ai/skills/{slug}."""
    message: str
    system_prompt: Optional[str] = None
    extra_context: str = ""
    conversation_history: Optional[List[Dict[str, Any]]] = None
    max_tokens: Optional[int] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def ai_status():
    """
    Health check for the AI / Skills streaming endpoints.
    Returns available skill count and stream protocol info.
    No auth required — safe to call from frontend on page load.
    """
    try:
        from api.routes.skills import list_skills_dict
        skills = list_skills_dict(enabled_only=True)
        skill_count = len(skills)
    except Exception:
        skill_count = 0

    return {
        "status": "online",
        "skills_available": skill_count,
        "stream_protocol": "vercel-ai-sdk-data-stream-v1",
        "endpoints": {
            "list_skills":   "GET  /ai/skills",
            "invoke_skill":  "POST /ai/skills/{slug}",
            "skill_detail":  "GET  /ai/skills/{slug}",
        },
    }


@router.get("/skills")
async def list_invokable_skills(
    user_id: str = Depends(get_current_user_id),
):
    """
    List all skills that can be invoked via the AI SDK streaming endpoint.
    Returns the same payload as GET /skills but from the /ai namespace for
    callers that prefer keeping all AI-SDK calls under /ai/*.
    """
    from api.routes.skills import list_skills_dict, get_categories
    skills = list_skills_dict(enabled_only=True)
    return {
        "skills": skills,
        "count": len(skills),
        "categories": get_categories(),
        "invoke_endpoint": "POST /ai/skills/{slug}",
    }


@router.get("/skills/{slug}")
async def get_invokable_skill(
    slug: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details for a single skill by slug (AI namespace alias of GET /skills/{slug})."""
    from api.routes.skills import get_skill, list_skills
    skill = get_skill(slug)
    if skill is None:
        available = sorted({s.slug for s in list_skills(enabled_only=False, include_builtins=True)})
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{slug}' not found. Available slugs: {available}",
        )
    return skill.to_dict()


@router.post("/skills/{slug}")
async def invoke_skill_stream(
    slug: str,
    data: SkillInvokeRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Invoke a registered Claude custom beta skill and stream the response
    using the Vercel AI SDK Data Stream Protocol.

    Compatible with ``useChat()`` / ``useCompletion()`` on the Next.js frontend.

    Stream protocol lines (Vercel AI SDK Data Stream v1):
        0:"text chunk"              ← incremental text
        2:[{type,file_id,...}]      ← data parts (file downloads when skill
                                      produces a .docx / .pptx / .xlsx)
        3:"error message"           ← error (non-200 already raised above)
        d:{finishReason, usage,...} ← finish message with token counts

    The X-Skill-Slug response header carries the executed skill slug so the
    frontend can correlate streams when running multiple skills in parallel.
    """
    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Claude API key not configured. "
                "Please add your API key in Profile Settings."
            ),
        )

    from api.routes.skills import get_skill, list_skills
    skill = get_skill(slug)
    if skill is None:
        available = sorted({s.slug for s in list_skills(enabled_only=False, include_builtins=True)})
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{slug}' not found. Available slugs: {available}",
        )
    if not skill.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{slug}' is currently disabled.",
        )

    from core.skill_gateway import SkillGateway

    def generate():
        gateway = SkillGateway(api_key=api_keys["claude"])
        yield from gateway.stream_ai_sdk(
            slug,
            data.message,
            system_prompt=data.system_prompt,
            conversation_history=data.conversation_history,
            max_tokens=data.max_tokens,
            extra_context=data.extra_context,
        )

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "X-Skill-Slug",
            "X-Skill-Slug": slug,
        },
    )
