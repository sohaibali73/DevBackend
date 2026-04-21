"""YANG advanced agentic features routes."""

import logging

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user_id

router = APIRouter(prefix="/yang", tags=["YANG"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def yang_health():
    """Health check for the YANG router."""
    return {"status": "ok", "router": "yang"}
