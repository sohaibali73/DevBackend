"""
Analyst by Potomac - API Server
================================
AI-powered AmiBroker AFL development platform.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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

# Create FastAPI app
app = FastAPI(
    title="Analyst by Potomac API",
    description="AI-powered AmiBroker AFL development platform with streaming support",
    version="3.6",
)

# CORS middleware — open to all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    # Skip rate limiting for health checks and docs
    if path in ("/health", "/", "/docs", "/openapi.json", "/routes", "/redoc"):
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

# Start background task cleanup loop on app startup
@app.on_event("startup")
async def startup_task_manager():
    """Initialize the background task manager cleanup loop."""
    try:
        from core.task_manager import get_task_manager
        manager = get_task_manager()
        manager.start_cleanup_loop()
        logger.info("✓ Background task manager initialized")
    except Exception as e:
        logger.error(f"✗ Failed to start task manager: {e}")


@app.on_event("startup")
async def startup_copy_docx_assets():
    """
    Copy Potomac logo assets to the Railway persistent volume on startup.

    This ensures logos survive a container restart/redeploy even if the image
    filesystem is ephemeral.  The primary path (Dockerfile COPY) is always
    available; this gives an extra durable copy on the mounted volume.

    Source  : ClaudeSkills/potomac-docx/assets/*.png (baked into image)
    Dest    : $STORAGE_ROOT/docx_assets/*.png         (Railway volume)
    """
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
            target = dst / png.name
            _shutil.copy2(png, target)
            copied += 1
        logger.info("✓ Copied %d Potomac logo assets → %s", copied, dst)
    except Exception as e:
        logger.warning("startup_copy_docx_assets: could not copy assets: %s", e)

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
        "routers_failed": [name for name, _ in routers_failed] if routers_failed else None,
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

    logger.info(f"Starting Analyst by Potomac API server on port {port}")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"Log level: {LOG_LEVEL}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=LOG_LEVEL.lower(),
        timeout_keep_alive=120,
    )
