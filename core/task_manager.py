"""
Background Task Manager for Potomac Analyst
=============================================
In-memory async task queue that supports background execution of long-running
operations (document generation, presentation creation, deep research, etc.).

Tasks survive page navigation — the frontend polls for status/results.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    RESEARCH = "research"
    AFL = "afl"
    GENERAL = "general"


@dataclass
class BackgroundTask:
    """Represents a background task with its state and result."""
    id: str
    user_id: str
    conversation_id: Optional[str]
    title: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    # Internal: the asyncio Task handle
    _async_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for API response."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "title": self.title,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": (
                (self.completed_at or time.time()) - self.started_at
                if self.started_at else 0
            ),
        }


class TaskManager:
    """
    Global in-memory task manager. Stores tasks per user and executes them
    in the background using asyncio.create_task().

    Usage:
        manager = TaskManager()
        task_id = await manager.submit(
            user_id="user123",
            title="Generate PowerPoint",
            task_type=TaskType.PRESENTATION,
            coroutine_factory=lambda task: generate_pptx(task, params),
        )
        status = manager.get_task(task_id)
    """

    def __init__(self, max_tasks_per_user: int = 20, task_ttl_seconds: int = 3600):
        self._tasks: Dict[str, BackgroundTask] = {}
        self._user_tasks: Dict[str, List[str]] = {}  # user_id -> [task_ids]
        self._max_tasks_per_user = max_tasks_per_user
        self._task_ttl = task_ttl_seconds
        self._cleanup_interval = 300  # 5 minutes
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_loop(self):
        """Start the periodic cleanup loop (call once at app startup)."""
        if self._cleanup_task is None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            except RuntimeError:
                pass

    async def _cleanup_loop(self):
        """Periodically remove expired tasks."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            self._cleanup_expired()

    def _cleanup_expired(self):
        """Remove tasks older than TTL."""
        now = time.time()
        expired = [
            tid for tid, task in self._tasks.items()
            if (task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED)
                and now - task.created_at > self._task_ttl)
        ]
        for tid in expired:
            task = self._tasks.pop(tid, None)
            if task and task.user_id in self._user_tasks:
                self._user_tasks[task.user_id] = [
                    t for t in self._user_tasks[task.user_id] if t != tid
                ]
        if expired:
            logger.info(f"[TaskManager] Cleaned up {len(expired)} expired tasks")

    async def submit(
        self,
        user_id: str,
        title: str,
        task_type: TaskType,
        coroutine_factory: Callable[["BackgroundTask"], Coroutine],
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Submit a new background task.

        Args:
            user_id: The user who owns this task
            title: Human-readable task title
            task_type: Category of the task
            coroutine_factory: Async function that takes a BackgroundTask and does the work.
                              It should update task.progress, task.message, and set task.result.
            conversation_id: Optional conversation this task belongs to

        Returns:
            task_id: Unique ID for polling
        """
        # Enforce per-user limit
        user_task_ids = self._user_tasks.get(user_id, [])
        active = [
            tid for tid in user_task_ids
            if tid in self._tasks and self._tasks[tid].status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]
        if len(active) >= self._max_tasks_per_user:
            raise ValueError(f"Too many active tasks (max {self._max_tasks_per_user})")

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = BackgroundTask(
            id=task_id,
            user_id=user_id,
            conversation_id=conversation_id,
            title=title,
            task_type=task_type,
            status=TaskStatus.PENDING,
            message="Queued...",
        )

        self._tasks[task_id] = task
        if user_id not in self._user_tasks:
            self._user_tasks[user_id] = []
        self._user_tasks[user_id].append(task_id)

        # Start executing in background
        async_task = asyncio.create_task(self._run_task(task, coroutine_factory))
        task._async_task = async_task

        logger.info(f"[TaskManager] Submitted task {task_id}: {title} (type={task_type.value})")
        return task_id

    # Maximum wall-clock seconds a task is allowed to run before being killed
    TASK_TIMEOUT_SECONDS: int = 600  # 10 minutes

    async def _run_task(
        self,
        task: BackgroundTask,
        coroutine_factory: Callable[[BackgroundTask], Coroutine],
    ):
        """Execute the task coroutine and handle status transitions."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        task.message = "Starting..."

        try:
            # Hard timeout — prevents any task from running forever
            await asyncio.wait_for(
                coroutine_factory(task),
                timeout=self.TASK_TIMEOUT_SECONDS,
            )

            # If the coroutine didn't set status, mark complete
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.COMPLETE
                task.progress = 100
                task.message = task.message or "Completed successfully"

            task.completed_at = time.time()
            elapsed = task.completed_at - task.started_at
            logger.info(
                f"[TaskManager] Task {task.id} completed in {elapsed:.1f}s: {task.title}"
            )

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = f"Task timed out after {self.TASK_TIMEOUT_SECONDS}s"
            task.message = "Timed out — task took too long"
            task.progress = 0
            logger.error(f"[TaskManager] Task {task.id} timed out after {self.TASK_TIMEOUT_SECONDS}s")

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            task.message = "Cancelled"
            logger.info(f"[TaskManager] Task {task.id} cancelled")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = str(e)
            task.message = f"Failed: {str(e)[:200]}"
            task.progress = 0
            logger.error(f"[TaskManager] Task {task.id} failed: {e}", exc_info=True)

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_user_tasks(self, user_id: str) -> List[BackgroundTask]:
        """Get all tasks for a user, newest first."""
        task_ids = self._user_tasks.get(user_id, [])
        tasks = [self._tasks[tid] for tid in task_ids if tid in self._tasks]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a running task."""
        task = self._tasks.get(task_id)
        if not task or task.user_id != user_id:
            return False
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            if task._async_task and not task._async_task.done():
                task._async_task.cancel()
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            task.message = "Cancelled by user"
            return True
        return False

    def dismiss_task(self, task_id: str, user_id: str) -> bool:
        """Remove a completed/failed task from the list."""
        task = self._tasks.get(task_id)
        if not task or task.user_id != user_id:
            return False
        if task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
            self._tasks.pop(task_id, None)
            if user_id in self._user_tasks:
                self._user_tasks[user_id] = [
                    t for t in self._user_tasks[user_id] if t != task_id
                ]
            return True
        return False

    def clear_completed(self, user_id: str) -> int:
        """Remove all completed/failed tasks for a user."""
        task_ids = self._user_tasks.get(user_id, [])
        removed = 0
        for tid in list(task_ids):
            task = self._tasks.get(tid)
            if task and task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                self._tasks.pop(tid, None)
                task_ids.remove(tid)
                removed += 1
        return removed


# ============================================================
# Global singleton
# ============================================================
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get or create the global TaskManager singleton."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager