"""Streaming Python execution for the IDE workspace SSE endpoint.

The existing `core.sandbox.python_sandbox.PythonSandbox._execute_sync` captures
stdout into a `StringIO`, returns one blob, and is load-bearing for the
synchronous `execute_python` tool (matplotlib capture, plotly capture, file-
artifact collection, namespace persistence, package auto-install). We do
NOT touch that path — refactoring it is too risky for one feature.

Instead this module provides a separate, deliberately lean streaming runner
used ONLY by `/workspace/.../execute/stream`:

  • Per-conversation persistent dir (same path as the main sandbox so files
    written by previous turns are still visible).
  • Same restricted `__builtins__` and globals.
  • Line-buffered stdout & stderr streamed back as they happen via an
    `asyncio.Queue` — the SSE generator yields a frame per chunk.
  • No artifact capture, no auto-install. If the user needs charts or a
    package install, they use the synchronous `execute_workspace_file`
    endpoint (or the `execute_python` tool) which already supports both.

Public surface
--------------
    async for event in stream_python(code, conversation_id, filename):
        ...   # event is one of: StartEvent, StdoutEvent, StderrEvent,
              #                   EndEvent, ErrorEvent (dataclasses)
"""

from __future__ import annotations

import asyncio
import dataclasses
import io
import logging
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import AsyncIterator, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Output chunks are batched up to this many chars or this much idle time before
# being pushed onto the queue. Keeps the SSE traffic reasonable for a script
# that prints a million tiny values.
_FLUSH_CHARS = 1024
_FLUSH_IDLE_MS = 50
# Total wallclock cap. The existing sandbox uses 300s; the IDE panel is
# interactive so we cut it harder. Override with SANDBOX_STREAM_TIMEOUT_S.
_DEFAULT_TIMEOUT_S = int(os.environ.get("SANDBOX_STREAM_TIMEOUT_S", "60"))


@dataclasses.dataclass
class StartEvent:
    filename: str
    language: str = "python"


@dataclasses.dataclass
class StdoutEvent:
    text: str


@dataclasses.dataclass
class StderrEvent:
    text: str


@dataclasses.dataclass
class EndEvent:
    success: bool
    exit_code: int
    execution_time_ms: int
    timed_out: bool = False


@dataclasses.dataclass
class ErrorEvent:
    """Setup-side failure (couldn't even start). Terminal."""
    message: str


StreamEvent = Union[StartEvent, StdoutEvent, StderrEvent, EndEvent, ErrorEvent]


# ─────────────────────────────────────────────────────────── stream writer
class _QueueWriter(io.TextIOBase):
    """File-like object whose `write()` pushes chunks onto an asyncio queue.

    Buffers small writes until either FLUSH_CHARS or FLUSH_IDLE_MS so the
    SSE client doesn't get a frame per character.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue,
                 kind: str):
        super().__init__()
        self._loop = loop
        self._queue = queue
        self._kind = kind          # "stdout" | "stderr"
        self._buf: list = []
        self._buf_len = 0
        self._last_flush = time.monotonic()
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        if not isinstance(s, str):
            s = str(s)
        if not s:
            return 0
        with self._lock:
            self._buf.append(s)
            self._buf_len += len(s)
            now = time.monotonic()
            should_flush = (
                "\n" in s
                or self._buf_len >= _FLUSH_CHARS
                or (now - self._last_flush) * 1000 >= _FLUSH_IDLE_MS
            )
            if should_flush:
                self._flush_locked(now)
        return len(s)

    def flush(self) -> None:
        with self._lock:
            self._flush_locked(time.monotonic())

    def _flush_locked(self, now: float) -> None:
        if not self._buf:
            return
        chunk = "".join(self._buf)
        self._buf.clear()
        self._buf_len = 0
        self._last_flush = now
        event = StdoutEvent(text=chunk) if self._kind == "stdout" else StderrEvent(text=chunk)
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # event loop closed mid-execution; nothing we can do
            pass


# ─────────────────────────────────────────────────────────── sandbox dir
def _sandbox_dir_for(conversation_id: str) -> Path:
    try:
        from core.sandbox.db import _SANDBOX_HOME as _SBHOME
        base = Path(_SBHOME) / "conversations" / str(conversation_id)
    except Exception:
        base = Path(os.environ.get(
            "SANDBOX_DATA_DIR", str(Path.home() / ".sandbox")
        )) / "conversations" / str(conversation_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


# Cache the main sandbox's pre-built globals + helpers at MODULE LOAD time.
# The first import of `core.sandbox.python_sandbox` pulls in pandas, numpy,
# matplotlib, plotly, yfinance, etc. — a one-time ~10 s cost that we do NOT
# want to pay on every streaming execution. Loading here means it happens
# once at process startup (or first call if not pre-warmed elsewhere).
try:
    from core.sandbox.python_sandbox import (
        _SANDBOX_GLOBALS as _CACHED_GLOBALS,
        _make_sandbox_imports,
        _make_sandboxed_open,
        PRE_APPROVED_PACKAGES,
    )
    _GLOBALS_AVAILABLE = True
except Exception as _e:
    logger.warning("could not import main sandbox helpers (%s); streaming will use bare builtins", _e)
    _CACHED_GLOBALS = None
    _make_sandbox_imports = None  # type: ignore[assignment]
    _make_sandboxed_open = None   # type: ignore[assignment]
    PRE_APPROVED_PACKAGES = []     # type: ignore[assignment]
    _GLOBALS_AVAILABLE = False


def _build_globals(
    sandbox_dir: Path,
    stdout_writer: "_QueueWriter",
    stderr_writer: "_QueueWriter",
) -> Dict:
    """Shallow-copy the cached sandbox globals + inject per-run helpers.

    Notably we install a custom ``print`` that targets our stdout queue and
    leave the process-wide ``sys.stdout`` UNCHANGED. The main sandbox uses
    the same trick. The reason: a runaway script we kill via timeout never
    reaches its ``finally`` to restore stdout; if we swapped sys.stdout
    globally, every other thread in the FastAPI process would have its
    prints hijacked until restart. With ``print`` redirected at the
    builtin level, the worst case for a runaway script is a leaked daemon
    thread (annoying, contained) instead of corrupted process state.

    Caveat: direct ``sys.stdout.write(...)`` in user code does NOT route
    through the queue — it goes to the real stdout. Use ``print(...)`` to
    stream into the IDE console.
    """
    if _GLOBALS_AVAILABLE and _CACHED_GLOBALS is not None:
        g = dict(_CACHED_GLOBALS)
        g["__builtins__"] = dict(_CACHED_GLOBALS["__builtins__"])
    else:
        g = {"__builtins__": dict(__builtins__) if isinstance(__builtins__, dict)
             else dict(vars(__builtins__))}

    def _streaming_print(*args, sep=" ", end="\n", file=None, flush=False):
        # Route to the appropriate queue writer:
        #   file=None or sys.stdout or our stdout_writer  → stdout queue
        #   file=sys.stderr or our stderr_writer          → stderr queue
        #   any other file-like object                    → real fallthrough
        target = stdout_writer
        if file is None or file is stdout_writer or file is sys.stdout:
            target = stdout_writer
        elif file is stderr_writer or file is sys.stderr:
            target = stderr_writer
        else:
            try:
                print(*args, sep=sep, end=end, file=file, flush=flush)
                return
            except Exception:
                target = stdout_writer  # last-resort fallback
        text = sep.join(str(a) for a in args) + (end or "")
        target.write(text)
        if flush:
            target.flush()

    g["__builtins__"]["print"] = _streaming_print
    # Sandbox-relative open() and import — same helpers the main sandbox uses,
    # so `open('foo.txt')` lands in the per-conversation dir and `import
    # other_workspace_file` succeeds for sibling files staged in that dir.
    if _make_sandboxed_open is not None:
        try:
            g["__builtins__"]["open"] = _make_sandboxed_open(sandbox_dir)
        except Exception as _oe:
            logger.debug("sandboxed open unavailable (%s); falling back to default", _oe)
    if _make_sandbox_imports is not None:
        try:
            g["__builtins__"]["__import__"] = _make_sandbox_imports(
                sandbox_dir, PRE_APPROVED_PACKAGES
            )
        except Exception as _ie:
            logger.debug("sandbox import override unavailable (%s); using default", _ie)
    g["__sandbox_dir__"] = str(sandbox_dir)
    g["__name__"] = "__sandbox_main__"
    # Provide a stderr-equivalent helper the user code can call directly
    # if they want red output: print(..., file=_sandbox_stderr)
    g["_sandbox_stderr"] = stderr_writer
    return g


# ─────────────────────────────────────────────────────────── thread runner
def _run_in_thread(
    code: str,
    sandbox_dir: Path,
    stdout: _QueueWriter,
    stderr: _QueueWriter,
    done: threading.Event,
    result: Dict,
) -> None:
    """Execute `code` with a print-redirected globals dict. Marks `done` on
    return.

    Does NOT mutate process-wide ``sys.stdout`` / ``sys.stderr`` — see
    ``_build_globals`` for the rationale. CWD is also left alone for the
    same reason (a stuck thread holding a chdir would silently move every
    other request's relative-path lookups).
    """
    try:
        run_ns = _build_globals(sandbox_dir, stdout, stderr)
        try:
            exec(compile(code, "<workspace>", "exec"), run_ns)
            result["success"] = True
            result["exit_code"] = 0
        except SystemExit as se:
            result["success"] = (se.code in (None, 0))
            result["exit_code"] = int(se.code) if isinstance(se.code, int) else (0 if se.code is None else 1)
        except Exception:
            stderr.write(traceback.format_exc())
            result["success"] = False
            result["exit_code"] = 1
    finally:
        try:
            stdout.flush()
            stderr.flush()
        except Exception:
            pass
        done.set()


# ─────────────────────────────────────────────────────────── public API
async def stream_python(
    code: str,
    conversation_id: str,
    filename: str = "<workspace>",
    timeout_s: Optional[int] = None,
) -> AsyncIterator[StreamEvent]:
    """Execute `code` in the conversation's persistent sandbox dir, streaming
    stdout/stderr as they happen.

    Yields: one StartEvent, zero-or-more Stdout/StderrEvent, exactly one
    EndEvent (or one ErrorEvent on setup failure). The iterator finishes
    after the terminal event.

    The execution timeout defaults to ``$SANDBOX_STREAM_TIMEOUT_S`` (60s).
    On timeout we yield an EndEvent with ``timed_out=True`` and stop reading
    the thread (it may keep running briefly until exec finishes a step;
    that's a Python limitation, not specific to this code).
    """
    if not isinstance(code, str):
        yield ErrorEvent(message="code must be a string")
        return

    sandbox_dir = _sandbox_dir_for(conversation_id)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    out_writer = _QueueWriter(loop, queue, "stdout")
    err_writer = _QueueWriter(loop, queue, "stderr")
    done = threading.Event()
    result: Dict = {"success": False, "exit_code": 1}

    yield StartEvent(filename=filename, language="python")
    started_at = time.monotonic()

    thread = threading.Thread(
        target=_run_in_thread,
        args=(code, sandbox_dir, out_writer, err_writer, done, result),
        daemon=True,
        name=f"sandbox-stream-{conversation_id[:8]}",
    )
    thread.start()

    timeout = timeout_s or _DEFAULT_TIMEOUT_S
    deadline = started_at + timeout
    timed_out = False

    # Drain the queue until the worker is done AND the queue is empty.
    while True:
        if done.is_set() and queue.empty():
            break
        if time.monotonic() > deadline:
            timed_out = True
            break
        try:
            # Short timeout so we re-check `done` and the wallclock often.
            evt = await asyncio.wait_for(queue.get(), timeout=0.1)
            yield evt
        except asyncio.TimeoutError:
            continue

    # Force-flush any tail bytes the worker buffered just before exit.
    try:
        out_writer.flush()
        err_writer.flush()
    except Exception:
        pass
    while not queue.empty():
        try:
            yield queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    if timed_out:
        yield StderrEvent(text=f"\n[execution exceeded {timeout}s timeout]\n")
        yield EndEvent(
            success=False, exit_code=124,
            execution_time_ms=elapsed_ms, timed_out=True,
        )
    else:
        yield EndEvent(
            success=bool(result.get("success")),
            exit_code=int(result.get("exit_code", 1)),
            execution_time_ms=elapsed_ms,
            timed_out=False,
        )
