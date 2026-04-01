"""
Skills Execute Endpoint
========================
POST /skills/{slug}/execute - Execute a skill by slug
This wraps the SkillGateway and returns streamed responses.
"""

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from core.skill_gateway import SkillGateway
from core.skills import get_skill, list_skills

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["Skills Execute"])


class SkillExecuteRequest(BaseModel):
    """Request body for skill execution."""
    message: str
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = None
    extra_context: Optional[str] = ""


@router.post("/{slug}/execute")
async def execute_skill(
    slug: str,
    data: SkillExecuteRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Execute a registered Claude custom beta skill by slug.
    
    Supports both streaming and non-streaming responses.
    When stream=True, returns Vercel AI SDK Data Stream Protocol format.
    """
    if not api_keys or not api_keys.get("claude"):
        raise HTTPException(
            status_code=401,
            detail="Claude API key not configured. Please add your API key in Profile Settings."
        )

    # Validate skill exists
    skill = get_skill(slug)
    if skill is None:
        available = sorted({s.slug for s in list_skills(enabled_only=False, include_builtins=True)})
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{slug}' not found. Available slugs: {available}"
        )
    
    if not skill.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Skill '{slug}' is currently disabled."
        )

    gateway = SkillGateway(api_key=api_keys["claude"])

    # Streaming response using Vercel AI SDK Data Stream Protocol
    def generate():
        try:
            # Stream the skill execution using the Vercel AI SDK format
            for chunk in gateway.stream_ai_sdk(
                skill_slug=slug,
                user_message=data.message,
                system_prompt=data.system_prompt,
                extra_context=data.extra_context or "",
                max_tokens=data.max_tokens,
            ):
                # stream_ai_sdk yields pre-formatted strings like:
                # 0:"text chunk"\n
                # 2:[{...}]\n
                # d:{...}\n
                yield chunk
            
        except Exception as e:
            logger.error(f"Skill streaming error for '{slug}': {e}", exc_info=True)
            yield f'3:{json.dumps(str(e))}\n'
            yield f'd:{json.dumps({"finishReason": "error"})}\n'

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/plain; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "X-Skill-Slug": slug,
        },
    )