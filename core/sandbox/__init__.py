"""
Code Execution Sandbox Package
===============================
Universal, provider-agnostic code execution.

Supports:
  - Python      (exec() with restricted globals + AST validation + session persistence)
  - JavaScript  (Node.js subprocess with npm package caching)
  - React       (Client-side HTML artifact — no Node.js subprocess, CDN Babel)
  - LLM Sandbox (Docker containers via llm-sandbox library)

Usage:
    from core.sandbox import get_sandbox_manager

    manager = get_sandbox_manager()
    result = await manager.execute("python", "print('hello')", session_id="abc")
    result = await manager.execute("javascript", "console.log('hello')")
    result = await manager.execute("react", "function App() { return <h1>Hi</h1> }")

    # Docker-isolated execution
    from core.sandbox import get_llm_sandbox_manager
    llm_manager = get_llm_sandbox_manager()
    result = await llm_manager.execute("python", "print('hello')")
"""

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage, DisplayArtifact
from core.sandbox.manager import SandboxManager
from core.sandbox.package_manager import get_package_manager

# Singleton manager — initialized once per process
_manager: "SandboxManager | None" = None


def get_sandbox_manager() -> SandboxManager:
    """
    Get or create the singleton sandbox manager with all sandboxes registered.
    Registers: PythonSandbox, NodeSandbox, ReactSandbox.
    """
    global _manager
    if _manager is not None:
        return _manager

    _manager = SandboxManager()

    # Register Python sandbox
    try:
        from core.sandbox.python_sandbox import PythonSandbox
        _manager.register(PythonSandbox())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to register Python sandbox: %s", e
        )

    # Register JavaScript sandbox
    try:
        from core.sandbox.node_sandbox import NodeSandbox
        _manager.register(NodeSandbox())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to register Node.js sandbox: %s", e
        )

    # Register React sandbox (Fix 3b)
    try:
        from core.sandbox.node_sandbox import ReactSandbox
        _manager.register(ReactSandbox())
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to register React sandbox: %s", e
        )

    # Initialize SQLite DB in background (best-effort)
    try:
        import asyncio
        asyncio.ensure_future(_init_db_background())
    except Exception:
        pass

    return _manager


async def _init_db_background() -> None:
    """Initialize the sandbox SQLite DB tables in the background."""
    try:
        from core.sandbox.db import init_db
        await init_db()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Sandbox DB init skipped: %s", e)


def get_llm_sandbox_manager():
    """
    Get or create the LLM Sandbox manager for Docker-based isolated execution.
    Returns None if llm-sandbox or Docker is not available.
    """
    try:
        from core.sandbox.llm_sandbox import get_llm_sandbox_manager as _get_llm_manager
        return _get_llm_manager()
    except ImportError as e:
        import logging
        logging.getLogger(__name__).warning(
            "LLM Sandbox not available: %s. Install with: pip install llm-sandbox docker", e
        )
        return None


__all__ = [
    "BaseSandbox",
    "SandboxResult",
    "SandboxLanguage",
    "DisplayArtifact",
    "SandboxManager",
    "get_sandbox_manager",
    "get_llm_sandbox_manager",
    "get_package_manager",
]
