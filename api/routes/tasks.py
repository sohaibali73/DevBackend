"""
Background Tasks API
=====================
REST endpoints for submitting, polling, and managing background tasks.
Supports document generation, presentation creation, and other long-running operations
that should continue even when the user navigates away from the chat page.

Endpoints:
    POST   /tasks              - Submit a new background task
    GET    /tasks              - List all tasks for current user
    GET    /tasks/{task_id}    - Get status of a specific task
    POST   /tasks/{task_id}/cancel  - Cancel a running task
    DELETE /tasks/{task_id}    - Dismiss a completed task
    DELETE /tasks              - Clear all completed tasks
"""

import logging
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from core.task_manager import (
    get_task_manager,
    TaskManager,
    TaskType,
    TaskStatus,
    BackgroundTask,
)
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ============================================================
#  Request/Response Models
# ============================================================

class TaskSubmitRequest(BaseModel):
    """Request to submit a new background task."""
    task_type: str = Field(..., description="Type: document, presentation, research, afl, general")
    title: str = Field(..., description="Human-readable task title")
    conversation_id: Optional[str] = Field(None, description="Associated conversation ID")
    # Parameters for the specific task type
    skill_slug: Optional[str] = Field(None, description="Skill slug to execute (e.g., 'create-word-document')")
    message: Optional[str] = Field(None, description="User message / prompt for the task")
    params: Optional[dict] = Field(None, description="Additional parameters for the task")


class TaskResponse(BaseModel):
    """Response for a single task."""
    id: str
    user_id: str
    conversation_id: Optional[str] = None
    title: str
    task_type: str
    status: str
    progress: int = 0
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    elapsed_seconds: float = 0


class TaskListResponse(BaseModel):
    """Response for listing tasks."""
    tasks: list
    active_count: int
    total_count: int


# ============================================================
#  Task Execution Factories
# ============================================================

async def _execute_skill_task(task: BackgroundTask, skill_slug: str, message: str, api_key: str):
    """Execute a skill via the SkillGateway in the background."""
    from core.skill_gateway import SkillGateway

    task.progress = 5
    task.message = "Initializing skill engine..."
    await asyncio.sleep(0.1)  # Yield to event loop

    settings = get_settings()
    gateway = SkillGateway(
        api_key=api_key or settings.anthropic_api_key,
        model=settings.default_model,
    )

    task.progress = 10
    task.message = f"Running skill: {skill_slug}..."
    await asyncio.sleep(0.1)

    # Execute the skill with a per-executor timeout (separate from the task-level timeout)
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: gateway.execute(
                    skill_slug=skill_slug,
                    user_message=message,
                )
            ),
            timeout=540,  # 9 min — under the 10 min task-level timeout
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"Skill '{skill_slug}' execution timed out after 9 minutes")

    task.progress = 90
    task.message = "Processing results..."
    await asyncio.sleep(0.1)

    # Extract file info from result
    task_result = {
        "text": result.get("text", ""),
        "skill": result.get("skill", skill_slug),
        "model": result.get("model", ""),
        "execution_time": result.get("execution_time", 0),
    }

    # Check for generated files
    files = result.get("files", [])
    if files:
        file_info = files[0] if isinstance(files, list) and files else files
        task_result["files"] = files
        task_result["has_file"] = True
        task_result["filename"] = file_info.get("filename", "") if isinstance(file_info, dict) else ""

    task.result = task_result
    task.progress = 100
    task.status = TaskStatus.COMPLETE
    task.message = "Completed successfully"


async def _execute_document_task(task: BackgroundTask, message: str, api_key: str, params: dict = None):
    """Generate a Word document in the background."""
    task.progress = 5
    task.message = "Initializing document engine..."

    # Try using the skill gateway for document generation
    skill_slug = (params or {}).get("skill_slug", "create-word-document")

    await _execute_skill_task(task, skill_slug, message, api_key)


async def _execute_presentation_task(task: BackgroundTask, message: str, api_key: str, params: dict = None):
    """Generate a PowerPoint presentation in the background."""
    task.progress = 5
    task.message = "Initializing presentation engine..."

    skill_slug = (params or {}).get("skill_slug", "create-pptx-with-skill")

    await _execute_skill_task(task, skill_slug, message, api_key)


async def _execute_research_task(task: BackgroundTask, message: str, api_key: str, params: dict = None):
    """Run deep research in the background."""
    task.progress = 5
    task.message = "Starting research pipeline..."

    skill_slug = (params or {}).get("skill_slug", "run-financial-deep-research")

    await _execute_skill_task(task, skill_slug, message, api_key)


async def _execute_general_task(task: BackgroundTask, message: str, api_key: str, params: dict = None):
    """Execute a general tool/skill in the background."""
    skill_slug = (params or {}).get("skill_slug")
    if not skill_slug:
        raise ValueError("skill_slug is required for general tasks")

    await _execute_skill_task(task, skill_slug, message, api_key)


# Map task types to their execution factories
TASK_EXECUTORS = {
    "document": _execute_document_task,
    "presentation": _execute_presentation_task,
    "research": _execute_research_task,
    "afl": _execute_general_task,
    "general": _execute_general_task,
}


# ============================================================
#  Helper: Get user API key
# ============================================================

async def _get_user_api_key(user_id: str) -> str:
    """Get the user's Anthropic API key from Supabase, fall back to system key."""
    try:
        from db.supabase_client import get_supabase
        from core.encryption import decrypt_value
        db = get_supabase()
        result = db.table("user_profiles").select(
            "claude_api_key_encrypted, claude_api_key"
        ).eq("user_id", user_id).limit(1).execute()

        if result.data:
            row = result.data[0]
            # Try encrypted key first
            encrypted = row.get("claude_api_key_encrypted")
            if encrypted:
                try:
                    return decrypt_value(encrypted)
                except Exception:
                    pass
            # Fall back to plain key column
            plain = row.get("claude_api_key")
            if plain:
                return plain
    except Exception as e:
        logger.warning(f"Could not fetch user API key for {user_id}: {e}")

    return get_settings().anthropic_api_key


# ============================================================
#  Routes
# ============================================================

@router.post("", response_model=dict)
async def submit_task(
    request: TaskSubmitRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Submit a new background task.

    The task will execute in the background and can be polled for status.
    Supports: document, presentation, research, afl, general.
    """
    manager = get_task_manager()

    # Validate task type
    task_type_str = request.task_type.lower()
    if task_type_str not in TASK_EXECUTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task type: {task_type_str}. Valid: {list(TASK_EXECUTORS.keys())}"
        )

    if not request.message:
        raise HTTPException(status_code=400, detail="Message/prompt is required")

    # Get API key
    api_key = await _get_user_api_key(user_id)

    # Map string to enum
    type_map = {
        "document": TaskType.DOCUMENT,
        "presentation": TaskType.PRESENTATION,
        "research": TaskType.RESEARCH,
        "afl": TaskType.AFL,
        "general": TaskType.GENERAL,
    }

    # Get executor
    executor = TASK_EXECUTORS[task_type_str]

    # Create the coroutine factory
    async def task_factory(task: BackgroundTask):
        await executor(
            task=task,
            message=request.message,
            api_key=api_key,
            params=request.params or {},
        )

    try:
        task_id = await manager.submit(
            user_id=user_id,
            title=request.title,
            task_type=type_map[task_type_str],
            coroutine_factory=task_factory,
            conversation_id=request.conversation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

    task = manager.get_task(task_id)
    return {
        "success": True,
        "task_id": task_id,
        "task": task.to_dict() if task else None,
    }


@router.get("", response_model=dict)
async def list_tasks(
    user_id: str = Depends(get_current_user_id),
):
    """List all tasks for the current user."""
    manager = get_task_manager()
    tasks = manager.get_user_tasks(user_id)

    active = sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING))

    return {
        "tasks": [t.to_dict() for t in tasks],
        "active_count": active,
        "total_count": len(tasks),
    }


@router.get("/{task_id}", response_model=dict)
async def get_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the status and result of a specific task."""
    manager = get_task_manager()
    task = manager.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your task")

    return {
        "success": True,
        "task": task.to_dict(),
    }


@router.post("/{task_id}/cancel", response_model=dict)
async def cancel_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Cancel a running task."""
    manager = get_task_manager()

    if manager.cancel_task(task_id, user_id):
        return {"success": True, "message": "Task cancelled"}
    else:
        raise HTTPException(status_code=400, detail="Cannot cancel this task")


@router.delete("/{task_id}", response_model=dict)
async def dismiss_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Dismiss (remove) a completed/failed task."""
    manager = get_task_manager()

    if manager.dismiss_task(task_id, user_id):
        return {"success": True, "message": "Task dismissed"}
    else:
        raise HTTPException(status_code=400, detail="Cannot dismiss this task")


@router.delete("", response_model=dict)
async def clear_completed_tasks(
    user_id: str = Depends(get_current_user_id),
):
    """Clear all completed/failed tasks for the current user."""
    manager = get_task_manager()
    removed = manager.clear_completed(user_id)
    return {"success": True, "removed": removed}