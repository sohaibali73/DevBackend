"""
Sandbox API Routes
==================
Endpoints for executing code in sandboxed Python, JavaScript, and React environments.

Fix 5a — ArtifactResponse model; artifacts + display_type exposed in execute response
Fix 5b — session_id added to execute request/response
Fix 5c — New artifact retrieval & session management routes
Fix 5d — Package status route + install route that actually works
Fix 5e — Dedicated POST /sandbox/react/execute shorthand
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SandboxExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 30
    context: Optional[dict] = None
    session_id: Optional[str] = None          # Fix 5b — persist namespace across calls


class ArtifactResponse(BaseModel):            # Fix 5a
    artifact_id: str
    type: str                                  # MIME type
    display_type: str                          # "react" | "html" | "image" | "json" | "text"
    data: str                                  # base64 for binary, raw for text
    encoding: str = "utf-8"
    metadata: dict = {}


class SandboxExecuteResponse(BaseModel):      # Fix 5a
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    language: str = "python"
    execution_id: str = ""
    session_id: str = ""
    artifacts: List[ArtifactResponse] = []    # Fix 5a
    display_type: str = "text"                # Fix 5a
    variables: dict = {}


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
    packages: List[str]
    user_id: Optional[str] = None


class PackageInstallResponse(BaseModel):
    success: bool
    message: str
    packages: list
    logs: List[str]


class PackageListResponse(BaseModel):
    language: str
    preinstalled: list
    cached: list
    user_installed: list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result_to_artifacts(result) -> List[ArtifactResponse]:
    """Convert SandboxResult.artifacts to ArtifactResponse list."""
    out = []
    for a in (result.artifacts or []):
        out.append(ArtifactResponse(
            artifact_id=a.artifact_id,
            type=a.type,
            display_type=a.display_type,
            data=a.data,
            encoding=a.encoding,
            metadata=a.metadata or {},
        ))
    return out


def _result_to_response(result, request_language: str) -> SandboxExecuteResponse:
    """Build a full SandboxExecuteResponse from a SandboxResult."""
    return SandboxExecuteResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        language=result.language or request_language,
        execution_id=getattr(result, "execution_id", ""),
        session_id=getattr(result, "session_id", ""),
        artifacts=_result_to_artifacts(result),
        display_type=getattr(result, "display_type", "text"),
        variables=getattr(result, "variables", {}),
    )


# ---------------------------------------------------------------------------
# Core execution routes
# ---------------------------------------------------------------------------

@router.post("/execute", response_model=SandboxExecuteResponse)
async def execute_sandbox(request: SandboxExecuteRequest):
    """
    Execute Python, JavaScript, or React code in a sandboxed environment.

    Pass `session_id` to carry variable state across multiple calls (Python only).
    The response includes `artifacts` for rich outputs (images, HTML, React components).
    """
    try:
        from core.sandbox import get_sandbox_manager

        manager = get_sandbox_manager()

        if not manager.has_language(request.language):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported language: {request.language}. "
                    f"Available: {manager.list_languages()}"
                ),
            )

        result = await manager.execute(
            language=request.language,
            code=request.code,
            timeout=request.timeout,
            context=request.context,
            session_id=request.session_id,
        )

        return _result_to_response(result, request.language)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sandbox execution error: %s", e, exc_info=True)
        return SandboxExecuteResponse(
            success=False,
            error=str(e),
            language=request.language,
        )


@router.post("/react/execute", response_model=SandboxExecuteResponse)
async def execute_react_sandbox(request: SandboxExecuteRequest):
    """
    Shorthand for React/JSX execution (always uses language='react').

    Returns a `text/html` artifact with `display_type='react'` that the
    frontend can render in an iframe. No Node.js subprocess is needed.
    """
    # Force language to react
    request = SandboxExecuteRequest(
        code=request.code,
        language="react",
        timeout=request.timeout,
        context=request.context,
        session_id=request.session_id,
    )
    return await execute_sandbox(request)


# ---------------------------------------------------------------------------
# Language + package discovery
# ---------------------------------------------------------------------------

@router.get("/languages")
async def list_languages():
    """List available sandbox languages."""
    try:
        from core.sandbox import get_sandbox_manager
        manager = get_sandbox_manager()
        return {"languages": manager.list_languages()}
    except Exception as e:
        logger.error("Error listing languages: %s", e, exc_info=True)
        return {"languages": ["python", "javascript", "react"]}


@router.get("/packages/{language}", response_model=SandboxPackagesResponse)
async def get_approved_packages(language: str):
    """Get list of pre-approved packages for a language."""
    try:
        from core.sandbox import get_sandbox_manager
        manager = get_sandbox_manager()
        packages = manager.get_available_packages(language)
        return SandboxPackagesResponse(language=language, packages=packages)
    except Exception as e:
        logger.error("Error getting packages: %s", e, exc_info=True)
        return SandboxPackagesResponse(language=language, packages=[])


@router.get("/packages/{language}/all", response_model=PackageListResponse)
async def list_all_packages(language: str, user_id: Optional[str] = None):
    """List all packages: preinstalled + cached + user-installed."""
    try:
        from core.sandbox.package_manager import get_package_manager
        manager = get_package_manager()
        packages = manager.list_all_packages(language, user_id)
        return PackageListResponse(
            language=language,
            preinstalled=[{"name": p.name, "status": p.status.value}
                          for p in packages["preinstalled"]],
            cached=[{"name": p.name, "version": p.version, "status": p.status.value}
                    for p in packages["cached"]],
            user_installed=[{"name": p.name, "version": p.version, "status": p.status.value}
                            for p in packages["user_installed"]],
        )
    except Exception as e:
        logger.error("Error listing packages: %s", e, exc_info=True)
        return PackageListResponse(language=language, preinstalled=[], cached=[], user_installed=[])


@router.get("/packages/{language}/status/{name}")
async def get_package_status(language: str, name: str):
    """Check if a specific package is installed and get its version."""
    try:
        from core.sandbox.db import get_package
        pkg = await get_package(language, name)
        if pkg:
            return {
                "installed": pkg.get("status") == "installed",
                "status": pkg.get("status"),
                "version": pkg.get("version"),
                "install_path": pkg.get("install_path"),
                "installed_at": pkg.get("installed_at"),
            }
        return {"installed": False, "status": "unknown"}
    except Exception as e:
        logger.error("Error checking package status: %s", e, exc_info=True)
        return {"installed": False, "status": "error", "error": str(e)}


@router.post("/packages/install", response_model=PackageInstallResponse)
async def install_sandbox_packages(request: PackageInstallRequest):
    """
    Install packages into the sandbox environment.

    Python packages are installed into a persistent venv at ~/.sandbox/python_venv/
    and immediately available in new executions without server restart.
    JavaScript packages are installed into ~/.sandbox/node_packages/ via npm.
    """
    try:
        from core.sandbox.package_manager import get_package_manager
        manager = get_package_manager()
        result = await manager.install_packages(
            language=request.language,
            packages=request.packages,
            user_id=request.user_id,
        )
        return PackageInstallResponse(
            success=result.success,
            message=result.message,
            packages=[{
                "name": p.name,
                "version": p.version,
                "status": p.status.value,
                "language": p.language,
                "install_time_ms": p.install_time_ms,
                "install_path": p.install_path,
            } for p in result.packages],
            logs=result.logs,
        )
    except Exception as e:
        logger.error("Package installation error: %s", e, exc_info=True)
        return PackageInstallResponse(
            success=False,
            message=f"Installation failed: {e}",
            packages=[],
            logs=[f"Error: {e}"],
        )


@router.post("/packages/cache/clear")
async def clear_package_cache():
    """Clear the in-memory package cache."""
    try:
        from core.sandbox.package_manager import get_package_manager
        get_package_manager().clear_cache()
        return {"success": True, "message": "Package cache cleared successfully"}
    except Exception as e:
        logger.error("Error clearing package cache: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Fix 5c — Artifact retrieval routes
# ---------------------------------------------------------------------------

@router.get("/artifacts/{execution_id}")
async def get_execution_artifacts(execution_id: str):
    """Get all artifacts produced by a single execution."""
    try:
        from core.sandbox.db import get_artifacts_by_execution
        artifacts = await get_artifacts_by_execution(execution_id)
        return {
            "execution_id": execution_id,
            "artifacts": [
                {
                    "artifact_id": a["artifact_id"],
                    "type": a["type"],
                    "display_type": a["display_type"],
                    "encoding": a["encoding"],
                    "metadata": a.get("metadata", "{}"),
                    "created_at": a["created_at"],
                    # Omit raw data from listing — use /raw endpoint for data
                }
                for a in artifacts
            ],
            "count": len(artifacts),
        }
    except Exception as e:
        logger.error("Error fetching artifacts: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/artifacts/{artifact_id}/raw")
async def get_artifact_raw(artifact_id: str):
    """
    Return the raw artifact data with the correct Content-Type header.
    Binary artifacts (images) are returned as base64-decoded bytes.
    """
    try:
        from core.sandbox.db import get_artifact
        import json as _json
        import base64 as _base64

        artifact = await get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")

        mime_type = artifact["type"]
        encoding = artifact.get("encoding", "utf-8")
        data = artifact["data"]

        if encoding == "base64":
            raw_bytes = _base64.b64decode(data)
            return Response(
                content=raw_bytes,
                media_type=mime_type,
                headers={
                    "Content-Disposition": f'inline; filename="artifact.{mime_type.split("/")[-1]}"',
                    "Cache-Control": "public, max-age=3600",
                },
            )
        else:
            return Response(
                content=data,
                media_type=mime_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching artifact raw: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Fix 5c — Session management routes
# ---------------------------------------------------------------------------

@router.get("/session/{session_id}/history")
async def get_session_history(session_id: str, limit: int = 20):
    """Get the execution history for a session (newest first)."""
    try:
        from core.sandbox.db import get_session_history
        history = await get_session_history(session_id, limit=min(limit, 100))
        return {
            "session_id": session_id,
            "executions": history,
            "count": len(history),
        }
    except Exception as e:
        logger.error("Error fetching session history: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}/variables")
async def get_session_variables(session_id: str):
    """Get the current namespace (persisted variables) for a session."""
    try:
        from core.sandbox.db import get_session_variables
        variables = await get_session_variables(session_id)
        return {
            "session_id": session_id,
            "variables": variables,
            "count": len(variables),
        }
    except Exception as e:
        logger.error("Error fetching session variables: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its executions and artifacts."""
    try:
        from core.sandbox.db import delete_session as _delete_session
        await _delete_session(session_id)
        return {"success": True, "message": f"Session {session_id} deleted"}
    except Exception as e:
        logger.error("Error deleting session: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# File download endpoint
# ---------------------------------------------------------------------------

@router.get("/download/{artifact_id}")
async def download_artifact(artifact_id: str, filename: Optional[str] = None):
    """
    Download an artifact as a file attachment.

    Sets `Content-Disposition: attachment` so the browser triggers a save-as
    dialog. Use this for CSV, Excel, PPTX, PDF, and any other file written
    by sandbox code.

    The `filename` query param overrides the stored filename if provided.
    """
    try:
        from core.sandbox.db import get_artifact
        import base64 as _b64
        import json as _json

        artifact = await get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")

        mime_type = artifact["type"]
        encoding = artifact.get("encoding", "utf-8")
        data = artifact["data"]

        # Resolve filename: query param → stored metadata → fallback
        meta = artifact.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except Exception:
                meta = {}

        dl_filename = (
            filename
            or meta.get("filename")
            or f"artifact.{mime_type.split('/')[-1]}"
        )

        raw_bytes = _b64.b64decode(data) if encoding == "base64" else data.encode("utf-8")

        return Response(
            content=raw_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{dl_filename}"',
                "Content-Length": str(len(raw_bytes)),
                "Cache-Control": "no-cache",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error downloading artifact %s: %s", artifact_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# LLM Sandbox (Docker) routes — unchanged logic, updated response model
# ---------------------------------------------------------------------------

@router.post("/llm/execute", response_model=SandboxExecuteResponse)
async def execute_llm_sandbox(request: LLMSandboxExecuteRequest):
    """Execute code in an isolated Docker sandbox via llm-sandbox."""
    try:
        from core.sandbox import get_llm_sandbox_manager

        manager = get_llm_sandbox_manager()
        if manager is None:
            raise HTTPException(
                status_code=503,
                detail="LLM Sandbox is not available. Install with: pip install llm-sandbox docker",
            )
        if not manager.is_available:
            raise HTTPException(
                status_code=503,
                detail="LLM Sandbox is not available. Docker may not be running.",
            )

        result = await manager.execute(
            code=request.code,
            language=request.language,
            timeout=request.timeout,
            context=request.context,
        )

        return _result_to_response(result, request.language)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("LLM Sandbox execution error: %s", e, exc_info=True)
        return SandboxExecuteResponse(
            success=False, error=str(e), language=request.language
        )


@router.get("/llm/status", response_model=LLMSandboxStatusResponse)
async def get_llm_sandbox_status():
    """Check if LLM Sandbox (Docker) is available."""
    try:
        from core.sandbox import get_llm_sandbox_manager

        manager = get_llm_sandbox_manager()
        available = manager is not None and manager.is_available
        return LLMSandboxStatusResponse(
            available=available,
            languages=manager.list_languages() if available else [],
        )
    except Exception as e:
        logger.error("Error checking LLM sandbox status: %s", e, exc_info=True)
        return LLMSandboxStatusResponse(available=False, languages=[])
