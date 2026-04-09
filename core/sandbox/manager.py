"""
Sandbox Manager
===============
Routes code execution to the appropriate sandbox by language.
Single unified entry point for all code execution.

Updated: wires session_id through execute() for persistence (Fix 6 / manager.py).
"""

import logging
from typing import Dict, Any, Optional, List

from core.sandbox.base import BaseSandbox, SandboxResult

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    Routes code execution to the appropriate sandbox.

    Usage:
        manager = SandboxManager()
        manager.register(PythonSandbox())
        manager.register(NodeSandbox())
        manager.register(ReactSandbox())

        result = await manager.execute("python", "print('hello')")
        result = await manager.execute("javascript", "console.log('hello')")
        result = await manager.execute("react", "function App() { return <h1>Hi</h1> }")
    """

    def __init__(self):
        self._sandboxes: Dict[str, BaseSandbox] = {}

    def register(self, sandbox: BaseSandbox) -> None:
        """Register a sandbox by its language value."""
        lang = sandbox.language.value
        self._sandboxes[lang] = sandbox
        logger.info("Registered sandbox: %s", lang)

    async def execute(
        self,
        language: str,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute code in the specified language's sandbox.

        Args:
            language:   "python", "javascript", or "react"
            code:       Source code to execute
            timeout:    Max execution time in seconds
            context:    Optional variables to inject
            session_id: Optional session ID for namespace persistence

        Returns:
            SandboxResult
        """
        sandbox = self._sandboxes.get(language)
        if not sandbox:
            available = list(self._sandboxes.keys())
            return SandboxResult(
                success=False,
                error=(
                    f"Unsupported language: '{language}'. "
                    f"Available: {available}"
                ),
                language=language,
            )

        return await sandbox.execute(code, timeout, context, session_id)

    def validate(self, language: str, code: str) -> Dict[str, Any]:
        """Pre-validate code for a given language."""
        sandbox = self._sandboxes.get(language)
        if not sandbox:
            return {
                "safe": False,
                "issues": [f"Unknown language: {language}"],
            }
        return sandbox.validate(code)

    def list_languages(self) -> List[str]:
        """List all registered sandbox languages."""
        return list(self._sandboxes.keys())

    def has_language(self, language: str) -> bool:
        """Check if a language sandbox is registered."""
        return language in self._sandboxes

    def get_available_packages(self, language: str) -> list:
        """
        Get list of pre-approved packages for a language.

        Returns:
            List of package names, or empty list if not supported.
        """
        sandbox = self._sandboxes.get(language)
        if sandbox and hasattr(sandbox, "list_available_packages"):
            return sandbox.list_available_packages()
        return []
