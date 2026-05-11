"""
Analyst by Potomac - API Server
================================
AI-powered AmiBroker AFL development platform.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import logging
import os
import traceback


# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING" if os.getenv("ENVIRONMENT") == "production" else "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── Startup / shutdown handlers (lifespan-managed) ────────────────────────────

async def _startup_perf_infra():
    """LAZILY initialize asyncpg pool, Redis cache, shared HTTP client.

    Each is wrapped in ``asyncio.wait_for`` so a slow/failed external service
    can NEVER block the healthcheck. All swallow exceptions — startup
    completes regardless of whether the deps are reachable.
    """
    import asyncio as _aio

    async def _safe(name: str, coro_factory, timeout: float = 5.0):
        try:
            await _aio.wait_for(coro_factory(), timeout=timeout)
            logger.info("✓ %s ready", name)
        except _aio.TimeoutError:
            logger.warning("%s init timed out after %.1fs — continuing without it", name, timeout)
        except Exception as e:
            logger.warning("%s init failed (non-fatal): %s", name, e)

    async def _db():
        from db.async_db import init_pool as _init
        await _init()

    async def _redis():
        from core.cache import cache as _c
        await _c._ensure_redis()  # noqa: SLF001

    async def _http():
        from core.http_client import get_http_client as _get
        await _get()

    async def _node_pool():
        from core.sandbox import node_worker_pool as _nwp
        if _nwp.is_enabled():
            pool = await _nwp.get_pool()
            if pool is not None:
                # Force lazy init now so the first doc-gen call doesn't pay
                # the spawn cost (~500-1500 ms warming pptxgenjs+docx).
                await pool._ensure()  # noqa: SLF001

    await _safe("asyncpg pool", _db, timeout=8.0)
    await _safe("Redis cache", _redis, timeout=4.0)
    await _safe("shared HTTP client", _http, timeout=2.0)
    await _safe("Node worker pool", _node_pool, timeout=15.0)



async def _startup_task_manager():
    try:
        from core.task_manager import get_task_manager
        manager = get_task_manager()
        manager.start_cleanup_loop()
        logger.info("✓ Background task manager initialized")
    except Exception as e:
        logger.error(f"✗ Failed to start task manager: {e}")


async def _startup_copy_docx_assets():
    import shutil as _shutil
    from pathlib import Path as _Path

    src = _Path(__file__).parent / "ClaudeSkills" / "potomac-docx" / "assets"
    storage_root = os.getenv("STORAGE_ROOT", "/data")
    dst = _Path(storage_root) / "docx_assets"

    if not src.exists():
        logger.warning("startup_copy_docx_assets: source assets not found at %s", src)
        return
    try:
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for png in src.glob("*.png"):
            _shutil.copy2(png, dst / png.name)
            copied += 1
        logger.info("✓ Copied %d Potomac logo assets → %s", copied, dst)
    except Exception as e:
        logger.warning("startup_copy_docx_assets: could not copy assets: %s", e)


async def _startup_copy_pptx_assets():
    import shutil as _shutil
    from pathlib import Path as _Path

    src = _Path(__file__).parent / "ClaudeSkills" / "potomac-pptx" / "brand-assets" / "logos"
    storage_root = os.getenv("STORAGE_ROOT", "/data")
    dst = _Path(storage_root) / "pptx_assets"

    if not src.exists():
        logger.warning("startup_copy_pptx_assets: source logos not found at %s", src)
        return
    try:
        dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for png in src.glob("*.png"):
            _shutil.copy2(png, dst / png.name)
            copied += 1
        logger.info("✓ Copied %d Potomac PPTX logo assets → %s", copied, dst)
    except Exception as e:
        logger.warning("startup_copy_pptx_assets: could not copy assets: %s", e)


async def _startup_reconcile_user_skills():
    """Re-extract user skills missing from disk after a redeploy."""
    try:
        from pathlib import Path as _Path
        from db.supabase_client import get_supabase
        from core.skills import skill_storage, invalidate_cache
        from core.skills.uploads import (
            extract_and_validate, materialize, decide_storage_kind,
            LIGHTWEIGHT_ROOT, BUNDLE_ROOT, delete_on_disk,
        )

        sb = get_supabase()
        rows = sb.table("user_skills").select(
            "slug, storage_kind, storage_path, source"
        ).execute().data or []

        rehydrated, missing = 0, 0
        for row in rows:
            slug = row.get("slug")
            sp = _Path(row.get("storage_path") or "")
            if sp.exists() and sp.is_dir():
                continue
            if (row.get("source") or "system") == "system":
                missing += 1
                try:
                    sb.table("user_skills").update({"enabled": False}).eq("slug", slug).execute()
                except Exception:
                    pass
                continue
            zip_bytes = skill_storage.download_zip(slug)
            if zip_bytes is None:
                logger.warning("Skill '%s' folder missing and no archive in Storage", slug)
                missing += 1
                continue
            try:
                parsed = extract_and_validate(zip_bytes, metadata_overrides={"slug": slug})
                kind = decide_storage_kind(parsed)
                try:
                    delete_on_disk(slug)
                except Exception:
                    pass
                target = materialize(parsed, kind)
                sb.table("user_skills").update({
                    "storage_path": str(target),
                    "storage_kind": kind,
                    "enabled": True,
                }).eq("slug", slug).execute()
                rehydrated += 1
                try:
                    sb.table("user_skill_audit").insert({
                        "slug": slug, "actor_id": None,
                        "action": "rehydrate",
                        "detail": {"kind": kind},
                    }).execute()
                except Exception:
                    pass
            except Exception as e:
                logger.warning("Rehydrate failed for '%s': %s", slug, e)
                missing += 1

        known = {r["slug"] for r in rows}
        added_system = 0
        for root, kind in ((LIGHTWEIGHT_ROOT, "lightweight"),
                           (BUNDLE_ROOT, "bundle")):
            if not root.exists():
                continue
            for folder in root.iterdir():
                if not folder.is_dir() or folder.name.startswith((".", "_")):
                    continue
                if folder.name in known:
                    continue
                try:
                    sb.table("user_skills").insert({
                        "slug": folder.name,
                        "name": folder.name,
                        "description": "",
                        "category": "general",
                        "tags": [],
                        "storage_kind": kind,
                        "storage_path": str(folder),
                        "bundle_size": 0,
                        "file_count": sum(1 for _ in folder.rglob("*") if _.is_file()),
                        "enabled": True,
                        "source": "system",
                        "created_by": None,
                    }).execute()
                    added_system += 1
                except Exception as e:
                    logger.debug("System row insert skipped for %s: %s", folder.name, e)

        invalidate_cache()
        logger.info(
            "✓ user_skills reconciled: %d rehydrated, %d missing/disabled, %d new system rows",
            rehydrated, missing, added_system,
        )
    except Exception as e:
        logger.warning("startup_reconcile_user_skills failed: %s", e)


async def _startup_seed_pptx_global_assets():
    try:
        from core.sandbox import pptx_assets as _pa
        _pa.ensure_global_seed()
        logger.info("✓ Global pptx_assets seed ensured")
    except Exception as e:
        logger.warning("startup_seed_pptx_global_assets failed: %s", e)


async def _shutdown_perf_infra():
    try:
        from db.async_db import close_pool as _close_db_pool
        await _close_db_pool()
    except Exception:
        pass
    try:
        from core.cache import cache as _cache
        await _cache.close()
    except Exception:
        pass
    try:
        from core.http_client import close_http_client as _close_http
        await _close_http()
    except Exception:
        pass
    try:
        from core.sandbox.node_worker_pool import shutdown_pool as _close_node
        await _close_node()
    except Exception:
        pass



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Single lifespan for the entire app (replaces deprecated on_event hooks).

    All startup hooks run sequentially before the app accepts requests; if any
    one of them throws it is logged but does NOT block boot.
    """
    for name, fn in (
        ("perf_infra", _startup_perf_infra),
        ("task_manager", _startup_task_manager),
        ("copy_docx_assets", _startup_copy_docx_assets),
        ("copy_pptx_assets", _startup_copy_pptx_assets),
        ("reconcile_user_skills", _startup_reconcile_user_skills),
        ("seed_pptx_global_assets", _startup_seed_pptx_global_assets),
    ):
        try:
            await fn()
        except Exception as e:
            logger.error("startup hook '%s' raised: %s", name, e, exc_info=True)

    yield

    try:
        await _shutdown_perf_infra()
    except Exception:
        pass


# Create FastAPI app
app = FastAPI(
    title="Analyst by Potomac API",
    description="AI-powered AmiBroker AFL development platform with streaming support",
    version="3.6",
    lifespan=lifespan,
)


# CORS middleware — open to all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression — only applied to large NON-streaming responses.
# Streaming responses (chat, agent, AI SDK) MUST NOT be wrapped in GZip:
# the middleware buffers the entire response while gzipping, which can add
# 5-10 s to time-to-first-token for SSE/text streams. We use a tiny
# pass-through middleware to skip any path that returns text/plain or
# text/event-stream, then apply GZip to the rest.

class _SmartGZipMiddleware(GZipMiddleware):
    async def __call__(self, scope, receive, send):
        # Only apply to HTTP requests.
        if scope.get("type") != "http":
            return await super().__call__(scope, receive, send)

        path = scope.get("path", "")
        # Skip GZip entirely on known streaming routes — they emit tiny
        # chunks and any buffering shows up as multi-second TTFT delay.
        STREAM_PATHS = (
            "/chat/agent", "/chat/agent/ui-stream",
            "/chat/stream", "/chat/sse",
            "/ai/", "/agent/", "/researcher/stream",
            "/skills/execute/stream", "/consensus/stream",
        )

        if any(path.startswith(p) for p in STREAM_PATHS):
            from starlette.types import ASGIApp
            # Bypass: forward unchanged to the next app.
            return await self.app(scope, receive, send)
        return await super().__call__(scope, receive, send)


app.add_middleware(_SmartGZipMiddleware, minimum_size=1024)

# Server-Timing header — adds total;dur=<ms> to every response so the
# browser DevTools Network panel "Timings" tab shows exactly how long each
# request spent on the server. Routes can record sub-measurements via
# ``with perf.span("label"): ...`` for fine-grained breakdowns.
try:
    from core.perf import PerfMiddleware
    app.add_middleware(PerfMiddleware)
except Exception as _perf_err:
    logger.warning("PerfMiddleware not loaded: %s", _perf_err)




# ── Public Sites: Host-header subdomain router (Lovable-style) ───────────────

# Runs BEFORE the rate limiter so a request like
#   Host: my-portfolio.sites.potomacai.com  →  /index.html
# is served straight from the published bundle without traversing the
# normal API rate-limit / auth pipeline. Activates only when
# PUBLIC_SITES_BASE_DOMAINS is set (e.g. "sites.potomacai.com").
@app.middleware("http")
async def public_sites_host_middleware(request: Request, call_next):
    try:
        from api.routes.public_sites import serve_host_routed
        resp = await serve_host_routed(request)
        if resp is not None:
            return resp
    except Exception as _e:
        # Never let the public-sites router crash the rest of the API.
        logger.warning("public_sites_host_middleware error: %s", _e)
    return await call_next(request)


# Simple in-memory rate limiting middleware
from collections import defaultdict
import time as _time

_rate_limit_store: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 120  # max requests per window per IP


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting — 120 requests/minute per IP. Skips health/docs."""
    path = request.url.path
    # Skip rate limiting for health checks, docs, AND site preview/public hosting
    # (a single page load can trigger 20+ asset requests — must not count against limit)
    if path in ("/health", "/", "/docs", "/openapi.json", "/routes", "/redoc") \
       or path.startswith("/studio/sites/") \
       or path.startswith("/s/"):
        return await call_next(request)
    
    client_ip = request.client.host if request.client else "unknown"
    now = _time.time()
    
    # Clean old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < _RATE_LIMIT_WINDOW
    ]
    
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again in a minute."},
            headers={"Retry-After": "60", "Access-Control-Allow-Origin": "*"},
        )
    
    _rate_limit_store[client_ip].append(now)
    
    # Prune store periodically (every ~1000 requests)
    if len(_rate_limit_store) > 1000:
        cutoff = now - _RATE_LIMIT_WINDOW * 2
        stale_ips = [ip for ip, times in _rate_limit_store.items() if not times or times[-1] < cutoff]
        for ip in stale_ips:
            del _rate_limit_store[ip]
    
    return await call_next(request)


# Global exception handler - ensures CORS headers are always present on errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return safe JSON with CORS headers."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    is_production = os.getenv("ENVIRONMENT") == "production" or os.getenv("RAILWAY_ENVIRONMENT")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error" if is_production else str(exc),
            "type": "ServerError" if is_production else type(exc).__name__,
        },
        headers={
            "Access-Control-Allow-Origin": "*",
        },
    )


# Explicit router imports - safer and clearer than dynamic loading
logger.info("Loading routers...")

# Load routers with individual error handling
routers_loaded = []
routers_failed = []

try:
    from api.routes import auth
    app.include_router(auth.router)
    routers_loaded.append("auth")
    logger.info("✓ Loaded auth router")
except Exception as e:
    routers_failed.append(("auth", str(e)))
    logger.error(f"✗ Failed to load auth router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import chat
    app.include_router(chat.router)
    routers_loaded.append("chat")
    logger.info("✓ Loaded chat router")
except Exception as e:
    routers_failed.append(("chat", str(e)))
    logger.error(f"✗ Failed to load chat router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import ai
    app.include_router(ai.router)
    routers_loaded.append("ai")
    logger.info("✓ Loaded ai router (Vercel AI SDK streaming)")
except Exception as e:
    routers_failed.append(("ai", str(e)))
    logger.error(f"✗ Failed to load ai router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import afl
    app.include_router(afl.router)
    routers_loaded.append("afl")
    logger.info("✓ Loaded afl router")
except Exception as e:
    routers_failed.append(("afl", str(e)))
    logger.error(f"✗ Failed to load afl router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import brain
    app.include_router(brain.router)
    routers_loaded.append("brain")
    logger.info("✓ Loaded brain router")
except Exception as e:
    routers_failed.append(("brain", str(e)))
    logger.error(f"✗ Failed to load brain router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import backtest
    app.include_router(backtest.router)
    routers_loaded.append("backtest")
    logger.info("✓ Loaded backtest router")
except Exception as e:
    routers_failed.append(("backtest", str(e)))
    logger.error(f"✗ Failed to load backtest router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import admin
    app.include_router(admin.router)
    routers_loaded.append("admin")
    logger.info("✓ Loaded admin router")
except Exception as e:
    routers_failed.append(("admin", str(e)))
    logger.error(f"✗ Failed to load admin router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import train
    app.include_router(train.router)
    routers_loaded.append("train")
    logger.info("✓ Loaded train router")
except Exception as e:
    routers_failed.append(("train", str(e)))
    logger.error(f"✗ Failed to load train router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import researcher
    app.include_router(researcher.router)
    routers_loaded.append("researcher")
    logger.info("✓ Loaded researcher router")
except Exception as e:
    routers_failed.append(("researcher", str(e)))
    logger.error(f"✗ Failed to load researcher router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import files_router
    app.include_router(files_router.router)
except Exception as e:
    print(f"Warning: Could not register files router: {e}")

try:
    from api.routes import preview
    app.include_router(preview.router)
    routers_loaded.append("preview")
    logger.info("✓ Loaded preview router (PPTX/DOCX file preview extraction)")
except Exception as e:
    routers_failed.append(("preview", str(e)))
    logger.error(f"✗ Failed to load preview router: {e}")

try:
    from api.routes import health
    app.include_router(health.router)
    routers_loaded.append("health")
    logger.info("✓ Loaded health router (database diagnostics)")
except Exception as e:
    routers_failed.append(("health", str(e)))
    logger.error(f"✗ Failed to load health router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import upload
    app.include_router(upload.router)
    routers_loaded.append("upload")
    logger.info("✓ Loaded upload router (Supabase Storage file uploads)")
except Exception as e:
    routers_failed.append(("upload", str(e)))
    logger.error(f"✗ Failed to load upload router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import skills
    app.include_router(skills.router)
    routers_loaded.append("skills")
    logger.info("✓ Loaded skills router (Claude custom beta skills gateway)")
except Exception as e:
    routers_failed.append(("skills", str(e)))
    logger.error(f"✗ Failed to load skills router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import skills_execute
    app.include_router(skills_execute.router)
    routers_loaded.append("skills_execute")
    logger.info("✓ Loaded skills_execute router (Direct skill execution endpoint)")
except Exception as e:
    routers_failed.append(("skills_execute", str(e)))
    logger.error(f"✗ Failed to load skills_execute router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import skills_upload
    app.include_router(skills_upload.router)
    routers_loaded.append("skills_upload")
    logger.info("✓ Loaded skills_upload router (User skill bundle upload / edit / delete)")
except Exception as e:
    routers_failed.append(("skills_upload", str(e)))
    logger.error(f"✗ Failed to load skills_upload router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import yfinance
    app.include_router(yfinance.router)
    routers_loaded.append("yfinance")
    logger.info("✓ Loaded yfinance router (Comprehensive YFinance data API)")
except Exception as e:
    routers_failed.append(("yfinance", str(e)))
    logger.error(f"✗ Failed to load yfinance router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import edgar
    app.include_router(edgar.router)
    routers_loaded.append("edgar")
    logger.info("✓ Loaded edgar router (SEC EDGAR filings, CIK lookup, XBRL financials)")
except Exception as e:
    routers_failed.append(("edgar", str(e)))
    logger.error(f"✗ Failed to load edgar router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import tasks
    app.include_router(tasks.router)
    routers_loaded.append("tasks")
    logger.info("✓ Loaded tasks router (Background task queue for multitasking)")
except Exception as e:
    routers_failed.append(("tasks", str(e)))
    logger.error(f"✗ Failed to load tasks router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import generate_presentation
    app.include_router(generate_presentation.router)
    routers_loaded.append("generate_presentation")
    logger.info("✓ Loaded generate_presentation router (Complete presentation editor with images, charts, and tables)")
except Exception as e:
    routers_failed.append(("generate_presentation", str(e)))
    logger.error(f"✗ Failed to load generate_presentation router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import kb_admin
    app.include_router(kb_admin.router)
    routers_loaded.append("kb_admin")
    logger.info("✓ Loaded kb_admin router (Bulk KB upload via API key — no JWT required)")
except Exception as e:
    routers_failed.append(("kb_admin", str(e)))
    logger.error(f"✗ Failed to load kb_admin router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import consensus
    app.include_router(consensus.router)
    routers_loaded.append("consensus")
    logger.info("✓ Loaded consensus router (Multi-model response validation & scoring)")
except Exception as e:
    routers_failed.append(("consensus", str(e)))
    logger.error(f"✗ Failed to load consensus router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import sandbox
    app.include_router(sandbox.router)
    routers_loaded.append("sandbox")
    logger.info("✓ Loaded sandbox router (Python/JavaScript code execution)")
except Exception as e:
    routers_failed.append(("sandbox", str(e)))
    logger.error(f"✗ Failed to load sandbox router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import agent_teams
    app.include_router(agent_teams.router)
    routers_loaded.append("agent_teams")
    logger.info("✓ Loaded agent_teams router (Multi-agent collaboration)")
except Exception as e:
    routers_failed.append(("agent_teams", str(e)))
    logger.error(f"✗ Failed to load agent_teams router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import agent_teams_v2
    app.include_router(agent_teams_v2.router)
    routers_loaded.append("agent_teams_v2")
    logger.info("✓ Loaded agent_teams_v2 router (Parallel execution, custom roles, unlimited agents)")
except Exception as e:
    routers_failed.append(("agent_teams_v2", str(e)))
    logger.error(f"✗ Failed to load agent_teams_v2 router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import volume_debug
    app.include_router(volume_debug.router)
    routers_loaded.append("volume_debug")
    logger.info("✓ Loaded volume_debug router (Railway volume CRUD — secured by VOLUME_DEBUG_KEY)")
except Exception as e:
    routers_failed.append(("volume_debug", str(e)))
    logger.error(f"✗ Failed to load volume_debug router: {e}")
    logger.debug(traceback.format_exc())

# ── New v4 feature routers ────────────────────────────────────────────────────

try:
    from api.routes import dashboard
    app.include_router(dashboard.router)
    routers_loaded.append("dashboard")
    logger.info("✓ Loaded dashboard router (Stats & activity feed)")
except Exception as e:
    routers_failed.append(("dashboard", str(e)))
    logger.error(f"✗ Failed to load dashboard router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import knowledge_base
    app.include_router(knowledge_base.router)
    routers_loaded.append("knowledge_base")
    logger.info("✓ Loaded knowledge_base router (/knowledge-base/* alias)")
except Exception as e:
    routers_failed.append(("knowledge_base", str(e)))
    logger.error(f"✗ Failed to load knowledge_base router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import stacks
    app.include_router(stacks.router)
    routers_loaded.append("stacks")
    logger.info("✓ Loaded stacks router (Msty-style Knowledge Stacks)")
except Exception as e:
    routers_failed.append(("stacks", str(e)))
    logger.error(f"✗ Failed to load stacks router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import settings
    app.include_router(settings.router)
    routers_loaded.append("settings")
    logger.info("✓ Loaded settings router (Profile, password, appearance, notifications)")
except Exception as e:
    routers_failed.append(("settings", str(e)))
    logger.error(f"✗ Failed to load settings router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import reverse_engineer
    app.include_router(reverse_engineer.router)
    routers_loaded.append("reverse_engineer")
    logger.info("✓ Loaded reverse_engineer router (Chart image & text analysis)")
except Exception as e:
    routers_failed.append(("reverse_engineer", str(e)))
    logger.error(f"✗ Failed to load reverse_engineer router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import research
    app.include_router(research.router)
    routers_loaded.append("research")
    logger.info("✓ Loaded research router (Company info, strategy analysis, peer comparison)")
except Exception as e:
    routers_failed.append(("research", str(e)))
    logger.error(f"✗ Failed to load research router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import websocket_router
    app.include_router(websocket_router.router)
    routers_loaded.append("websocket_router")
    logger.info("✓ Loaded websocket_router (Real-time progress & notifications via WS)")
except Exception as e:
    routers_failed.append(("websocket_router", str(e)))
    logger.error(f"✗ Failed to load websocket_router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import training_courses
    app.include_router(training_courses.router)
    routers_loaded.append("training_courses")
    logger.info("✓ Loaded training_courses router (Courses, lessons, quizzes, progress)")
except Exception as e:
    routers_failed.append(("training_courses", str(e)))
    logger.error(f"✗ Failed to load training_courses router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import pptx_intelligence
    app.include_router(pptx_intelligence.router)
    routers_loaded.append("pptx_intelligence")
    logger.info("✓ Loaded pptx_intelligence router (CV-powered slide merging, analysis, reconstruction)")
except Exception as e:
    routers_failed.append(("pptx_intelligence", str(e)))
    logger.error(f"✗ Failed to load pptx_intelligence router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import pptx as pptx_programs_router
    app.include_router(pptx_programs_router.router)
    routers_loaded.append("pptx_programs")
    logger.info("✓ Loaded pptx_programs router (program store + JSON-patch edit memory)")
except Exception as e:
    routers_failed.append(("pptx_programs", str(e)))
    logger.error(f"✗ Failed to load pptx_programs router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import pptx_assets as pptx_assets_router
    app.include_router(pptx_assets_router.router)
    routers_loaded.append("pptx_assets")
    logger.info("✓ Loaded pptx_assets router (user icon/graphic library)")
except Exception as e:
    routers_failed.append(("pptx_assets", str(e)))
    logger.error(f"✗ Failed to load pptx_assets router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import yang
    app.include_router(yang.router)
    routers_loaded.append("yang")
    logger.info("✓ Loaded yang router (YANG advanced agentic features)")
except Exception as e:
    routers_failed.append(("yang", str(e)))
    logger.error(f"✗ Failed to load yang router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import debug as debug_router
    app.include_router(debug_router.router)
    routers_loaded.append("debug")
    logger.info("✓ Loaded debug router (Debug transcript access — set DEBUG_TRANSCRIPTS_ENABLED=1)")
except Exception as e:
    routers_failed.append(("debug", str(e)))
    logger.error(f"✗ Failed to load debug router: {e}")
    logger.debug(traceback.format_exc())

# ── Content Studio routers (projects, voice cloning, humanizer) ───────────────

try:
    from api.routes import studio_projects
    app.include_router(studio_projects.router)
    routers_loaded.append("studio_projects")
    logger.info("✓ Loaded studio_projects router (Content Studio: projects + artifacts on Railway volume)")
except Exception as e:
    routers_failed.append(("studio_projects", str(e)))
    logger.error(f"✗ Failed to load studio_projects router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import studio_styles
    app.include_router(studio_styles.router)
    routers_loaded.append("studio_styles")
    logger.info("✓ Loaded studio_styles router (Voice cloning / writing-style training)")
except Exception as e:
    routers_failed.append(("studio_styles", str(e)))
    logger.error(f"✗ Failed to load studio_styles router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import studio_humanize
    app.include_router(studio_humanize.router)
    routers_loaded.append("studio_humanize")
    logger.info("✓ Loaded studio_humanize router (Advanced humanizer + LinkedIn SEO + AI-detector ensemble)")
except Exception as e:
    routers_failed.append(("studio_humanize", str(e)))
    logger.error(f"✗ Failed to load studio_humanize router: {e}")
    logger.debug(traceback.format_exc())

# ── Content Studio: Sites (Lovable-style website builder) ────────────────────
try:
    from api.routes import studio_sites
    app.include_router(studio_sites.router)
    routers_loaded.append("studio_sites")
    logger.info("✓ Loaded studio_sites router (Lovable-style site builder: preview, publish, subdomains)")
except Exception as e:
    routers_failed.append(("studio_sites", str(e)))
    logger.error(f"✗ Failed to load studio_sites router: {e}")
    logger.debug(traceback.format_exc())

try:
    from api.routes import public_sites
    app.include_router(public_sites.router)
    routers_loaded.append("public_sites")
    logger.info("✓ Loaded public_sites router (anonymous /s/{subdomain}/* path-based hosting)")
except Exception as e:
    routers_failed.append(("public_sites", str(e)))
    logger.error(f"✗ Failed to load public_sites router: {e}")
    logger.debug(traceback.format_exc())

# Log summary

logger.info(f"Router loading complete: {len(routers_loaded)} loaded, {len(routers_failed)} failed")
if routers_failed:
    logger.warning(f"Failed routers: {[name for name, _ in routers_failed]}")

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Analyst by Potomac API",
        "version": "3.6",
        "status": "online",
        "routers_loaded": routers_loaded,
        "routers_failed": [name for name, _ in routers_failed] if routers_failed else [],
        "routers_failed_errors": {name: err for name, err in routers_failed} if routers_failed else {},
    }

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "routers_active": len(routers_loaded),
        "routers_failed": len(routers_failed),
    }

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    # Multiple workers — async-friendly, doubles throughput on Railway's 2 vCPU box.
    workers = int(os.environ.get("WEB_CONCURRENCY", "2"))

    logger.info(f"Starting Analyst by Potomac API server on port {port} (workers={workers})")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"Log level: {LOG_LEVEL}")

    # Pass the import string ("main:app") rather than the app object so uvicorn
    # can spawn workers and reload correctly.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level=LOG_LEVEL.lower(),
        timeout_keep_alive=120,
        workers=workers,
    )

