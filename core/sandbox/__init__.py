"""
Code Execution Sandbox Package
===============================
Universal, provider-agnostic code execution for Yang.

Supports:
  - Python (via exec() with restricted globals)
  - JavaScript (via Node.js subprocess)
  - LLM Sandbox (via Docker containers for isolated execution)

Usage:
    from core.sandbox import get_sandbox_manager
    
    manager = get_sandbox_manager()
    result = await manager.execute("python", "print('hello')")
    result = await manager.execute("javascript", "console.log('hello')")
    
    # Use LLM Sandbox for isolated Docker execution
    from core.sandbox import get_llm_sandbox_manager
    llm_manager = get_llm_sandbox_manager()
    result = await llm_manager.execute("python", "print('hello')")
"""

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage
from core.sandbox.manager import SandboxManager
from core.sandbox.package_manager import get_package_manager

# Singleton manager — initialized once per process
_manager: "SandboxManager | None" = None


def get_sandbox_manager() -> SandboxManager:
    """
    Get or create the singleton sandbox manager with all sandboxes registered.
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

    return _manager


def get_llm_sandbox_manager():
    """
    Get or create the LLM Sandbox manager for Docker-based isolated execution.
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
    "SandboxManager",
    "get_sandbox_manager",
    "get_llm_sandbox_manager",
    "get_package_manager",
]
