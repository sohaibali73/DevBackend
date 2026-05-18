"""Per-conversation IDE workspace HTTP routes.

Five endpoints, all scoped by the URL's `conversation_id`:

  GET    /workspace/{conversation_id}/files
  GET    /workspace/{conversation_id}/files/{filename}
  PUT    /workspace/{conversation_id}/files/{filename}
  DELETE /workspace/{conversation_id}/files/{filename}
  POST   /workspace/{conversation_id}/files/{filename}/execute        (JSON)
  GET    /workspace/{conversation_id}/files/{filename}/execute/stream  (SSE)

Auth: every request requires a valid bearer token via `get_current_user_id`.
The same user_id is enforced as the WHERE clause on all DB ops — a request
with conversation_id X but the wrong user_id sees an empty workspace, not
someone else's files.

The streaming endpoint is GET-only because EventSource is GET-only on the
browser; the file contents are already in the DB, so we don't need a body.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id, get_current_user_id_sse
from core.workspace import (
    EXECUTABLE_LANGUAGES,
    VALID_LANGUAGES,
    WorkspaceError,
    delete_file,
    execute_file,
    list_files,
    read_file,
    write_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# ─────────────────────────────────────────────────────────────────── DTOs
class WorkspaceFileSummary(BaseModel):
    id:           Optional[str] = None
    filename:     str
    language:     str
    version:      int = 1
    last_author:  str = "agent"
    created_at:   Optional[str] = None
    updated_at:   Optional[str] = None
    size_bytes:   int = 0


class WorkspaceFile(WorkspaceFileSummary):
    content: str = ""
    conversation_id: Optional[str] = None


class WorkspaceWriteRequest(BaseModel):
    content:  str = Field(default="", description="Full file content; replaces previous version.")
    language: Optional[str] = Field(
        default=None,
        description=f"Optional language override. One of: {sorted(VALID_LANGUAGES)}. Inferred from extension if omitted.",
    )
    author:   str = Field(default="user", description="'user' | 'agent' | 'system' — used to surface edit provenance in the UI.")


class WorkspaceExecuteResponse(BaseModel):
    success:     bool
    filename:    str
    language:    str = "python"
    output:      Optional[str] = ""
    error:       Optional[str] = ""
    exit_code:   Optional[int] = None
    artifacts:   list = []
    execution_time_ms: Optional[float] = None


# ─────────────────────────────────────────────────────────── list / read / write
@router.get("/{conversation_id}/files", response_model=List[WorkspaceFileSummary])
async def list_workspace_files(
    conversation_id: str = Path(..., description="Conversation UUID"),
    user_id: str = Depends(get_current_user_id),
) -> List[WorkspaceFileSummary]:
    """All files in this conversation's workspace, newest-updated first."""
    rows = await asyncio.to_thread(list_files, conversation_id, user_id)
    return [WorkspaceFileSummary(**r) for r in rows]


@router.get(
    "/{conversation_id}/files/{filename}",
    response_model=WorkspaceFile,
)
async def get_workspace_file(
    conversation_id: str,
    filename: str,
    user_id: str = Depends(get_current_user_id),
) -> WorkspaceFile:
    """Return one file with its current content. 404 if it doesn't exist."""
    try:
        row = await asyncio.to_thread(read_file, conversation_id, user_id, filename)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail=f"file {filename!r} not found")
    return WorkspaceFile(**row)


@router.put(
    "/{conversation_id}/files/{filename}",
    response_model=WorkspaceFile,
)
async def put_workspace_file(
    conversation_id: str,
    filename: str,
    body: WorkspaceWriteRequest,
    user_id: str = Depends(get_current_user_id),
) -> WorkspaceFile:
    """Upsert a file. Bumps the file's `version` on every write."""
    try:
        row = await asyncio.to_thread(
            write_file,
            conversation_id,
            user_id,
            filename,
            body.content,
            body.language,
            body.author,
        )
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("workspace write failed")
        raise HTTPException(status_code=500, detail=f"write failed: {e}")
    return WorkspaceFile(**row)


@router.delete("/{conversation_id}/files/{filename}")
async def delete_workspace_file(
    conversation_id: str,
    filename: str,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Hard-delete a file. Idempotent — returns `removed: false` if not found."""
    try:
        removed = await asyncio.to_thread(
            delete_file, conversation_id, user_id, filename
        )
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"removed": removed, "filename": filename}


# ─────────────────────────────────────────────────────────────────── execute
@router.post(
    "/{conversation_id}/files/{filename}/execute",
    response_model=WorkspaceExecuteResponse,
)
async def execute_workspace_file(
    conversation_id: str,
    filename: str,
    user_id: str = Depends(get_current_user_id),
) -> WorkspaceExecuteResponse:
    """Synchronously run a workspace file, return the captured output.

    Python uses the existing PythonSandbox (per-conversation namespace +
    persistent dir); JavaScript shells out to `node`. Languages outside
    EXECUTABLE_LANGUAGES are rejected with 400.
    """
    try:
        result = await asyncio.to_thread(
            execute_file, conversation_id, user_id, filename
        )
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("workspace execute failed")
        raise HTTPException(status_code=500, detail=f"execute failed: {e}")
    if not isinstance(result, dict):
        result = {"success": False, "error": "internal: non-dict execute result"}
    return WorkspaceExecuteResponse(
        success=bool(result.get("success")),
        filename=filename,
        language=result.get("language") or "python",
        output=result.get("output") or "",
        error=result.get("error") or "",
        exit_code=result.get("exit_code"),
        artifacts=result.get("artifacts") or [],
        execution_time_ms=result.get("execution_time_ms"),
    )


@router.get("/{conversation_id}/files/{filename}/execute/stream")
async def stream_execute_workspace_file(
    conversation_id: str,
    filename: str,
    user_id: str = Depends(get_current_user_id_sse),
):
    """Server-Sent Events execution stream.

    Auth: accepts the bearer token via `Authorization` header (server-to-
    server) OR `?token=<jwt>` query param (browser EventSource, which
    cannot set headers). See `get_current_user_id_sse`.

    Frame format (one event per line, blank line terminates):
      event: start  | data: {"filename": "...", "language": "python"}
      event: stdout | data: {"text": "..."}
      event: stderr | data: {"text": "..."}
      event: end    | data: {"success": true, "exit_code": 0,
                              "execution_time_ms": 412, "timed_out": false}
      event: error  | data: {"message": "..."}                  (terminal)

    Python is now chunk-streamed via `core.sandbox.streaming_sandbox`:
    stdout/stderr lines arrive on the SSE wire as the script writes them,
    not as a single trailing blob. The streaming sandbox does NOT capture
    matplotlib/plotly artifacts — for charts, use the synchronous JSON
    `POST .../execute` endpoint which delegates to the main sandbox.

    JavaScript still goes through the synchronous path (node subprocess,
    captured output) and emits one stdout/stderr frame plus end.
    """

    def _frame(event: str, payload: dict) -> bytes:
        return (
            f"event: {event}\n"
            f"data: {json.dumps(payload, default=str)}\n\n"
        ).encode("utf-8")

    async def _agen():
        # ── Resolve the file from Supabase ───────────────────────────────
        try:
            file_row = await asyncio.to_thread(
                read_file, conversation_id, user_id, filename
            )
        except WorkspaceError as e:
            yield _frame("error", {"message": str(e)})
            return
        except Exception as e:
            logger.exception("workspace stream: read_file failed")
            yield _frame("error", {"message": f"read failed: {e}"})
            return
        if file_row is None:
            yield _frame("error", {"message": f"file {filename!r} not found"})
            return

        language = (file_row.get("language") or "python").lower()
        if language not in EXECUTABLE_LANGUAGES:
            yield _frame("error", {
                "message": f"language {language!r} is not executable; "
                           f"only {sorted(EXECUTABLE_LANGUAGES)} are run.",
            })
            return

        content = file_row.get("content") or ""

        # ── Python: real-time chunked stdout/stderr ──────────────────────
        if language == "python":
            from core.sandbox.streaming_sandbox import (
                EndEvent, ErrorEvent, StartEvent,
                StdoutEvent, StderrEvent, stream_python,
            )
            try:
                async for evt in stream_python(content, conversation_id, filename):
                    if isinstance(evt, StartEvent):
                        yield _frame("start", {
                            "filename": evt.filename, "language": evt.language,
                        })
                    elif isinstance(evt, StdoutEvent):
                        yield _frame("stdout", {"text": evt.text})
                    elif isinstance(evt, StderrEvent):
                        yield _frame("stderr", {"text": evt.text})
                    elif isinstance(evt, EndEvent):
                        yield _frame("end", {
                            "success":            evt.success,
                            "exit_code":          evt.exit_code,
                            "execution_time_ms":  evt.execution_time_ms,
                            "timed_out":          evt.timed_out,
                        })
                    elif isinstance(evt, ErrorEvent):
                        yield _frame("error", {"message": evt.message})
            except Exception as e:
                logger.exception("workspace stream: python execution crashed")
                yield _frame("error", {"message": f"execution crashed: {e}"})
            return

        # ── JavaScript: still synchronous (one shot) ─────────────────────
        yield _frame("start", {"filename": filename, "language": language})
        try:
            result = await asyncio.to_thread(
                execute_file, conversation_id, user_id, filename
            )
        except Exception as e:
            yield _frame("error", {"message": f"execute failed: {e}"})
            return
        out = (result or {}).get("output") or ""
        err = (result or {}).get("error") or ""
        if out:
            yield _frame("stdout", {"text": out})
        if err:
            yield _frame("stderr", {"text": err})
        yield _frame("end", {
            "success":   bool((result or {}).get("success")),
            "exit_code": (result or {}).get("exit_code"),
            "execution_time_ms": (result or {}).get("execution_time_ms"),
            "timed_out": False,
        })

    return StreamingResponse(
        _agen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
