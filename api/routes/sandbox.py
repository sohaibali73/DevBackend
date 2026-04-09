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


class LLMSandboxExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 60
    context: Optional[dict] = None


class LLMSandboxStatusResponse(BaseModel):
    available: bool
    languages: list


class PackageInstallRequest(BaseModel):
    language: str
    packages: list[str]
    user_id: Optional[str] = None


class PackageInstallResponse(BaseModel):
    success: bool
    message: str
    packages: list
    logs: list[str]


class PackageListResponse(BaseModel):
    language: str
    preinstalled: list
    cached: list
    user_installed: list


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


@router.post("/llm/execute", response_model=SandboxExecuteResponse)
async def execute_llm_sandbox(request: LLMSandboxExecuteRequest):
    """Execute code in an isolated Docker sandbox via llm-sandbox."""
    try:
        from core.sandbox import get_llm_sandbox_manager
        
        manager = get_llm_sandbox_manager()
        
        if manager is None:
            raise HTTPException(
                status_code=503,
                detail="LLM Sandbox is not available. Install with: pip install llm-sandbox docker"
            )
        
        if not manager.is_available:
            raise HTTPException(
                status_code=503,
                detail="LLM Sandbox is not available. Docker may not be running."
            )
        
        result = await manager.execute(
            code=request.code,
            language=request.language,
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
        logger.error(f"LLM Sandbox execution error: {e}", exc_info=True)
        return SandboxExecuteResponse(
            success=False,
            error=str(e),
            language=request.language,
        )


@router.get("/llm/status", response_model=LLMSandboxStatusResponse)
async def get_llm_sandbox_status():
    """Check if LLM Sandbox is available and list supported languages."""
    try:
        from core.sandbox.llm_sandbox import HAS_LLM_SANDBOX
        from core.sandbox import get_llm_sandbox_manager
        
        manager = get_llm_sandbox_manager()
        available = manager is not None and manager.is_available
        
        return LLMSandboxStatusResponse(
            available=available,
            languages=manager.list_languages() if available else [],
        )
    except Exception as e:
        logger.error(f"Error checking LLM sandbox status: {e}", exc_info=True)
        return LLMSandboxStatusResponse(
            available=False,
            languages=[],
        )


@router.post("/packages/install", response_model=PackageInstallResponse)
async def install_sandbox_packages(request: PackageInstallRequest):
    """Install packages into the sandbox environment."""
    try:
        from core.sandbox.package_manager import get_package_manager
        
        manager = get_package_manager()
        
        result = await manager.install_packages(
            language=request.language,
            packages=request.packages,
            user_id=request.user_id
        )
        
        return PackageInstallResponse(
            success=result.success,
            message=result.message,
            packages=[{
                "name": pkg.name,
                "version": pkg.version,
                "status": pkg.status.value,
                "language": pkg.language,
                "install_time_ms": pkg.install_time_ms,
                "size_kb": pkg.size_kb
            } for pkg in result.packages],
            logs=result.logs
        )
    except Exception as e:
        logger.error(f"Package installation error: {e}", exc_info=True)
        return PackageInstallResponse(
            success=False,
            message=f"Installation failed: {str(e)}",
            packages=[],
            logs=[f"Error: {str(e)}"]
        )


@router.get("/packages/{language}/all", response_model=PackageListResponse)
async def list_all_packages(language: str, user_id: Optional[str] = None):
    """List all available packages including preinstalled, cached, and user installed."""
    try:
        from core.sandbox.package_manager import get_package_manager
        
        manager = get_package_manager()
        packages = manager.list_all_packages(language, user_id)
        
        return PackageListResponse(
            language=language,
            preinstalled=[{
                "name": pkg.name,
                "status": pkg.status.value
            } for pkg in packages["preinstalled"]],
            cached=[{
                "name": pkg.name,
                "version": pkg.version,
                "status": pkg.status.value
            } for pkg in packages["cached"]],
            user_installed=[{
                "name": pkg.name,
                "version": pkg.version,
                "status": pkg.status.value
            } for pkg in packages["user_installed"]]
        )
    except Exception as e:
        logger.error(f"Error listing packages: {e}", exc_info=True)
        return PackageListResponse(
            language=language,
            preinstalled=[],
            cached=[],
            user_installed=[]
        )


@router.post("/packages/cache/clear")
async def clear_package_cache():
    """Clear the package cache."""
    try:
        from core.sandbox.package_manager import get_package_manager
        
        manager = get_package_manager()
        manager.clear_cache()
        
        return {"success": True, "message": "Package cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing package cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

