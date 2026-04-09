"""
Sandbox Database Layer
======================
SQLite persistence for sandbox sessions, executions, artifacts, and packages.
Uses aiosqlite for async access. All data survives server restarts.

Tables:
    sandbox_sessions   — per-user/conversation session namespaces
    sandbox_executions — history of every code run
    sandbox_artifacts  — generated outputs (HTML, images, React, etc.)
    installed_packages — user-installed packages that survive restart
"""

import json
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — configurable via env vars, fallback to ~/.sandbox/
# ---------------------------------------------------------------------------
import os

_SANDBOX_HOME = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
_DB_PATH = _SANDBOX_HOME / "sandbox.db"

# Session TTL: 7 days
SESSION_TTL_SECONDS = 7 * 24 * 3600

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_CREATE_TABLES = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sandbox_sessions (
    session_id   TEXT PRIMARY KEY,
    user_id      TEXT,
    language     TEXT NOT NULL DEFAULT 'python',
    namespace    TEXT NOT NULL DEFAULT '{}',
    created_at   INTEGER NOT NULL,
    updated_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sandbox_executions (
    execution_id   TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    code           TEXT NOT NULL,
    language       TEXT NOT NULL,
    output         TEXT NOT NULL DEFAULT '',
    error          TEXT NOT NULL DEFAULT '',
    success        INTEGER NOT NULL DEFAULT 1,
    exec_time_ms   REAL NOT NULL DEFAULT 0,
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sandbox_artifacts (
    artifact_id    TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    execution_id   TEXT NOT NULL,
    type           TEXT NOT NULL,
    display_type   TEXT NOT NULL DEFAULT 'text',
    data           TEXT NOT NULL,
    encoding       TEXT NOT NULL DEFAULT 'utf-8',
    metadata       TEXT NOT NULL DEFAULT '{}',
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS installed_packages (
    id             TEXT PRIMARY KEY,
    language       TEXT NOT NULL,
    name           TEXT NOT NULL,
    version        TEXT,
    status         TEXT NOT NULL,
    install_path   TEXT,
    installed_at   INTEGER NOT NULL,
    UNIQUE(language, name)
);

CREATE INDEX IF NOT EXISTS idx_exec_session   ON sandbox_executions(session_id);
CREATE INDEX IF NOT EXISTS idx_art_execution  ON sandbox_artifacts(execution_id);
CREATE INDEX IF NOT EXISTS idx_art_session    ON sandbox_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_pkg_lang_name  ON installed_packages(language, name);
CREATE INDEX IF NOT EXISTS idx_session_user   ON sandbox_sessions(user_id);
"""


async def _get_conn():
    """Open and return an aiosqlite connection. Caller must close."""
    try:
        import aiosqlite
    except ImportError:
        raise RuntimeError(
            "aiosqlite is required for sandbox persistence. "
            "Install with: pip install aiosqlite"
        )
    conn = await aiosqlite.connect(str(_DB_PATH))
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db() -> None:
    """Create all tables if they don't exist. Call once at startup."""
    conn = await _get_conn()
    try:
        await conn.executescript(_CREATE_TABLES)
        await conn.commit()
        logger.info("Sandbox DB initialized at %s", _DB_PATH)
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

async def get_or_create_session(
    session_id: str,
    language: str = "python",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Load session from DB (creating it if new). Extends TTL on every access.

    Returns:
        {session_id, language, namespace (dict)}
    """
    now = int(time.time())
    conn = await _get_conn()
    try:
        async with conn.execute(
            "SELECT * FROM sandbox_sessions WHERE session_id = ?", (session_id,)
        ) as cur:
            row = await cur.fetchone()

        if row:
            # Refresh TTL
            await conn.execute(
                "UPDATE sandbox_sessions SET updated_at=?, expires_at=? WHERE session_id=?",
                (now, now + SESSION_TTL_SECONDS, session_id),
            )
            await conn.commit()
            return {
                "session_id": row["session_id"],
                "language": row["language"],
                "namespace": json.loads(row["namespace"] or "{}"),
            }
        else:
            await conn.execute(
                """INSERT INTO sandbox_sessions
                   (session_id, user_id, language, namespace, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, user_id, language,
                    "{}", now, now, now + SESSION_TTL_SECONDS,
                ),
            )
            await conn.commit()
            return {"session_id": session_id, "language": language, "namespace": {}}
    finally:
        await conn.close()


async def save_session_namespace(session_id: str, namespace: Dict[str, Any]) -> None:
    """Persist the current execution namespace back to DB."""
    now = int(time.time())
    try:
        serialized = json.dumps(namespace, default=str)
    except Exception:
        serialized = "{}"

    conn = await _get_conn()
    try:
        await conn.execute(
            "UPDATE sandbox_sessions SET namespace=?, updated_at=? WHERE session_id=?",
            (serialized, now, session_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_session_variables(session_id: str) -> Dict[str, Any]:
    """Get the current namespace dict for a session."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            "SELECT namespace FROM sandbox_sessions WHERE session_id=?", (session_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return json.loads(row["namespace"] or "{}")
        return {}
    finally:
        await conn.close()


async def get_session_history(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all executions for a session, newest first."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            """SELECT execution_id, language, success, output, error,
                      exec_time_ms, created_at,
                      SUBSTR(code, 1, 200) AS code_preview
               FROM sandbox_executions
               WHERE session_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def delete_session(session_id: str) -> None:
    """Delete a session and all its executions and artifacts."""
    conn = await _get_conn()
    try:
        await conn.execute(
            "DELETE FROM sandbox_artifacts WHERE session_id=?", (session_id,)
        )
        await conn.execute(
            "DELETE FROM sandbox_executions WHERE session_id=?", (session_id,)
        )
        await conn.execute(
            "DELETE FROM sandbox_sessions WHERE session_id=?", (session_id,)
        )
        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Execution CRUD
# ---------------------------------------------------------------------------

async def save_execution(
    execution_id: str,
    session_id: str,
    code: str,
    language: str,
    output: str,
    error: str,
    success: bool,
    exec_time_ms: float,
) -> None:
    """Persist an execution record."""
    conn = await _get_conn()
    try:
        await conn.execute(
            """INSERT OR REPLACE INTO sandbox_executions
               (execution_id, session_id, code, language, output, error,
                success, exec_time_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id, session_id, code, language,
                output or "", error or "",
                1 if success else 0, exec_time_ms,
                int(time.time()),
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Artifact CRUD
# ---------------------------------------------------------------------------

async def save_artifact(
    artifact_id: str,
    session_id: str,
    execution_id: str,
    type_: str,
    display_type: str,
    data: str,
    encoding: str = "utf-8",
    metadata: Optional[Dict] = None,
) -> None:
    """Persist a display artifact."""
    conn = await _get_conn()
    try:
        await conn.execute(
            """INSERT OR REPLACE INTO sandbox_artifacts
               (artifact_id, session_id, execution_id, type, display_type,
                data, encoding, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id, session_id, execution_id,
                type_, display_type, data, encoding,
                json.dumps(metadata or {}),
                int(time.time()),
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_artifacts_by_execution(execution_id: str) -> List[Dict[str, Any]]:
    """Get all artifacts produced by a single execution."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            """SELECT * FROM sandbox_artifacts
               WHERE execution_id=? ORDER BY created_at""",
            (execution_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_artifact(artifact_id: str) -> Optional[Dict[str, Any]]:
    """Get a single artifact by ID."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            "SELECT * FROM sandbox_artifacts WHERE artifact_id=?", (artifact_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Package CRUD
# ---------------------------------------------------------------------------

async def upsert_package(
    language: str,
    name: str,
    version: Optional[str],
    status: str,
    install_path: Optional[str] = None,
) -> None:
    """Insert or update a package record (upsert on language+name)."""
    conn = await _get_conn()
    try:
        await conn.execute(
            """INSERT INTO installed_packages
               (id, language, name, version, status, install_path, installed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(language, name) DO UPDATE SET
                 version       = excluded.version,
                 status        = excluded.status,
                 install_path  = excluded.install_path,
                 installed_at  = excluded.installed_at""",
            (
                str(uuid.uuid4()), language, name.lower(), version,
                status, install_path, int(time.time()),
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_installed_packages(language: str) -> List[Dict[str, Any]]:
    """Return all DB-tracked packages for a language."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            "SELECT * FROM installed_packages WHERE language=? ORDER BY name",
            (language,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_package(language: str, name: str) -> Optional[Dict[str, Any]]:
    """Look up a single package record."""
    conn = await _get_conn()
    try:
        async with conn.execute(
            "SELECT * FROM installed_packages WHERE language=? AND name=?",
            (language, name.lower()),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


__all__ = [
    "init_db",
    "get_or_create_session",
    "save_session_namespace",
    "get_session_variables",
    "get_session_history",
    "delete_session",
    "save_execution",
    "save_artifact",
    "get_artifacts_by_execution",
    "get_artifact",
    "upsert_package",
    "get_installed_packages",
    "get_package",
    "_SANDBOX_HOME",
    "_DB_PATH",
]
