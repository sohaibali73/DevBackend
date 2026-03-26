"""
Code Execution Sandbox Package
===============================
Universal, provider-agnostic code execution for Yang.

Supports:
  - Python (via exec() with restricted globals)
  - JavaScript (via Node.js subprocess)

Usage:
    from core.sandbox import get_sandbox_manager
    
    manager = get_sandbox_manager()
    result = await manager.execute("python", "print('hello')")
    result = await manager.execute("javascript", "console.log('hello')")
"""

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage
from core.sandbox.manager import SandboxManager

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


__all__ = [
    "BaseSandbox",
    "SandboxResult",
    "SandboxLanguage",
    "SandboxManager",
    "get_sandbox_manager",
]
