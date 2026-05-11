"""
Long-lived Node.js worker pool for DOCX / PPTX generation.

The first call to ``submit()`` lazily spawns N worker processes (defaults to
``NODE_WORKER_POOL_SIZE`` env var, or 2). Each worker:

* Loads ``pptxgenjs`` and ``docx`` once at startup (~500–1500 ms paid once)
* Sits in an NDJSON request/response loop on stdin/stdout
* Reuses its V8 instance and the loaded libraries across many generations

Compared to the legacy "subprocess per call" path (``subprocess.run(node, …)``),
this saves ~500–1500 ms per DOCX/PPTX call.

Opt-in: set ``USE_NODE_WORKER_POOL=true`` to enable. When disabled (default),
the existing per-call subprocess path is used, so nothing breaks if anything
goes wrong with the pool.

Concurrency model: each worker handles one job at a time. The pool round-robins
jobs across workers via an ``asyncio.Queue``. Per-worker stdout reading is
serialized because a single Node process can only respond to one job at a
time on its NDJSON channel.

Lifecycle:
    * ``get_pool()`` lazily builds the pool.
    * ``await pool.submit(kind, spec, workdir)`` dispatches a job.
    * ``await pool.shutdown()`` on FastAPI shutdown.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_THIS_DIR    = Path(__file__).parent
_WORKER_JS   = _THIS_DIR / "workers" / "worker.js"


def is_enabled() -> bool:
    """True when ``USE_NODE_WORKER_POOL`` is set to a truthy value."""
    val = os.getenv("USE_NODE_WORKER_POOL", "false").strip().lower()
    return val in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────────────────────
# Worker
# ─────────────────────────────────────────────────────────────────────────────

class _Worker:
    """Wraps a single long-lived Node subprocess."""

    def __init__(self, idx: int):
        self.idx = idx
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()  # only one inflight job at a time

    async def start(self) -> bool:
        try:
            # On Railway/Docker we install pptxgenjs+docx globally; tell Node
            # to look there so `require()` finds them from the worker script.
            env = dict(os.environ)
            global_modules = "/usr/lib/node_modules:/usr/local/lib/node_modules"
            existing = env.get("NODE_PATH", "")
            env["NODE_PATH"] = f"{existing}:{global_modules}" if existing else global_modules

            self.proc = await asyncio.create_subprocess_exec(
                "node",
                str(_WORKER_JS),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Read the "ready" line from stderr (best-effort, non-blocking)
            try:
                line = await asyncio.wait_for(self.proc.stderr.readline(), timeout=10)
                logger.info("Node worker %d ready: %s", self.idx, line.decode(errors="replace").strip())
            except asyncio.TimeoutError:
                logger.warning("Node worker %d didn't emit ready line within 10s", self.idx)
            return True
        except FileNotFoundError:
            logger.error("Cannot start Node worker %d: 'node' binary not on PATH", self.idx)
            return False
        except Exception as exc:
            logger.error("Cannot start Node worker %d: %s", self.idx, exc, exc_info=True)
            return False

    async def submit(
        self,
        kind: str,
        spec: Dict[str, Any],
        workdir: str,
        timeout: float = 180.0,
    ) -> Dict[str, Any]:
        """Send one job to this worker and await the response.

        Returns the parsed JSON response dict from worker.js, e.g.
        ``{"id": "...", "ok": true, "outfile": "..."}``.
        """
        if self.proc is None:
            raise RuntimeError(f"worker {self.idx} not started")

        job_id = uuid.uuid4().hex
        req = {"id": job_id, "kind": kind, "spec": spec, "workdir": workdir}
        line = (json.dumps(req) + "\n").encode("utf-8")

        async with self._lock:
            if self.proc.returncode is not None:
                raise RuntimeError(f"worker {self.idx} exited (rc={self.proc.returncode})")
            try:
                self.proc.stdin.write(line)
                await self.proc.stdin.drain()
            except Exception as exc:
                raise RuntimeError(f"worker {self.idx} stdin write failed: {exc}") from exc

            try:
                resp_line = await asyncio.wait_for(
                    self.proc.stdout.readline(), timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(f"worker {self.idx} timed out after {timeout}s")

            if not resp_line:
                raise RuntimeError(f"worker {self.idx} closed stdout unexpectedly")

            try:
                resp = json.loads(resp_line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"worker {self.idx} returned invalid JSON: {resp_line!r}"
                ) from exc

            if resp.get("id") not in (job_id, None):
                logger.warning(
                    "worker %d id mismatch: expected %s, got %s",
                    self.idx, job_id, resp.get("id"),
                )
            return resp

    async def shutdown(self) -> None:
        if self.proc is None:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.is_closing():
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            self.proc.kill()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Pool
# ─────────────────────────────────────────────────────────────────────────────

class NodeWorkerPool:
    """Round-robin pool over N long-lived Node workers."""

    def __init__(self, size: int):
        self.size = size
        self._workers: list[_Worker] = []
        self._next = 0
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure(self) -> bool:
        if self._initialized:
            return bool(self._workers)
        async with self._init_lock:
            if self._initialized:
                return bool(self._workers)
            self._initialized = True
            if not _WORKER_JS.exists():
                logger.error("worker.js not found at %s — pool disabled", _WORKER_JS)
                return False
            for i in range(self.size):
                w = _Worker(i)
                if await w.start():
                    self._workers.append(w)
            logger.info("NodeWorkerPool ready with %d/%d workers", len(self._workers), self.size)
            return bool(self._workers)

    async def submit(
        self,
        kind: str,
        spec: Dict[str, Any],
        workdir: str,
        timeout: float = 180.0,
    ) -> Dict[str, Any]:
        """Dispatch to the next available worker."""
        ok = await self._ensure()
        if not ok:
            raise RuntimeError("NodeWorkerPool has no live workers")
        # Round-robin pick. The worker's own _lock handles per-worker serialization.
        worker = self._workers[self._next % len(self._workers)]
        self._next += 1
        return await worker.submit(kind, spec, workdir, timeout=timeout)

    async def shutdown(self) -> None:
        for w in self._workers:
            try:
                await w.shutdown()
            except Exception:
                pass
        self._workers.clear()
        self._initialized = False


# ── Module-level singleton ────────────────────────────────────────────────────

_pool: Optional[NodeWorkerPool] = None
_pool_lock = asyncio.Lock()
# The event loop the pool was created on. We have to route every job through
# this loop because the worker subprocesses (and their stdin/stdout pipes)
# are bound to it — calling them from a different loop will hang/raise.
_pool_loop: Optional[asyncio.AbstractEventLoop] = None


async def get_pool() -> Optional[NodeWorkerPool]:
    """Return the shared pool (lazy init). None if the feature is disabled."""
    global _pool, _pool_loop
    if not is_enabled():
        return None
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is not None:
            return _pool
        size = max(1, int(os.getenv("NODE_WORKER_POOL_SIZE", "2")))
        _pool = NodeWorkerPool(size)
        _pool_loop = asyncio.get_running_loop()
    return _pool


async def shutdown_pool() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        try:
            await _pool.shutdown()
        except Exception:
            pass
        _pool = None
        _pool_loop = None



# ─────────────────────────────────────────────────────────────────────────────
# Sync wrapper for legacy code paths
# ─────────────────────────────────────────────────────────────────────────────

def submit_sync(kind: str, spec: Dict[str, Any], workdir: str, timeout: float = 180.0) -> Dict[str, Any]:
    """Sync-call wrapper for code paths that aren't async yet.

    Critical: the pool's subprocesses are owned by the event loop on which
    the pool was created (typically the FastAPI lifespan loop). When called
    from a sync function running inside a thread (FastAPI runs sync route /
    threaded background tasks in a thread executor), we MUST schedule the
    coroutine on the pool's owning loop via ``run_coroutine_threadsafe``,
    otherwise the workers would be inaccessible.
    """
    async def _go():
        pool = await get_pool()
        if pool is None:
            raise RuntimeError("Node worker pool disabled (USE_NODE_WORKER_POOL not set)")
        return await pool.submit(kind, spec, workdir, timeout=timeout)

    # Prefer the pool's owning loop when set (this is the common server case).
    target_loop = _pool_loop
    if target_loop is not None and not target_loop.is_closed():
        fut = asyncio.run_coroutine_threadsafe(_go(), target_loop)
        return fut.result(timeout=timeout + 10)

    # Fallback paths used only by scripts / CLI tools (no FastAPI running).
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is None:
        return asyncio.run(_go())
    # Inside *some* running loop but no pool_loop captured yet — schedule and
    # wait on the current loop.
    fut = asyncio.run_coroutine_threadsafe(_go(), running)
    return fut.result(timeout=timeout + 10)

