"""
Sandbox API Routes
==================
Endpoints for executing code in sandboxed Python and JavaScript environments.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class SandboxExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 30
    context: Optional[dict] = None


class SandboxExecuteResponse(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    language: str = "python"


class SandboxPackagesResponse(BaseModel):
    language: str
    packages: list


@router.post("/execute", response_model=SandboxExecuteResponse)
async def execute_sandbox(request: SandboxExecuteRequest):
    """Execute code in a sandboxed environment."""
    try:
        from core.sandbox import get_sandbox_manager
        
        manager = get_sandbox_manager()
        
        if not manager.has_language(request.language):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported language: {request.language}. Available: {manager.list_languages()}"
            )
        
        result = await manager.execute(
            language=request.language,
            code=request.code,
            timeout=request.timeout,
            context=request.context,
        )
        
        return SandboxExecuteResponse(
            success=result.success,
            output=result.output,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
            language=result.language,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sandbox execution error: {e}", exc_info=True)
        return SandboxExecuteResponse(
            success=False,
            error=str(e),
            language=request.language,
        )


@router.get("/packages/{language}", response_model=SandboxPackagesResponse)
async def get_approved_packages(language: str):
    """Get list of pre-approved packages for a language."""
    try:
        from core.sandbox import get_sandbox_manager
        
        manager = get_sandbox_manager()
        packages = manager.get_available_packages(language)
        
        return SandboxPackagesResponse(
            language=language,
            packages=packages,
        )
    except Exception as e:
        logger.error(f"Error getting packages: {e}", exc_info=True)
        return SandboxPackagesResponse(
            language=language,
            packages=[],
        )


@router.get("/languages")
async def list_languages():
    """List available sandbox languages."""
    try:
        from core.sandbox import get_sandbox_manager
        
        manager = get_sandbox_manager()
        return {
            "languages": manager.list_languages(),
        }
    except Exception as e:
        logger.error(f"Error listing languages: {e}", exc_info=True)
        return {"languages": ["python", "javascript"]}