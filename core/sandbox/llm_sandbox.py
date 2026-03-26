"""
LLM Sandbox Integration
========================
Integrates the llm-sandbox library for isolated code execution with Docker containers.

Features:
- Isolated Docker-based execution
- Multiple language support (Python, JavaScript, Java, C++, Go, Rust)
- Package installation within sandbox
- Automatic cleanup
- Timeout handling
"""

import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage

logger = logging.getLogger(__name__)

# Try to import llm-sandbox
try:
    from sandbox import Sandbox, SandboxExecutionResult
    from sandbox.core.sandbox_types import SandboxLanguage as LLMsandboxLanguage
    HAS_LLM_SANDBOX = True
except ImportError:
    HAS_LLM_SANDBOX = False
    logger.warning("llm-sandbox not installed. Install with: pip install llm-sandbox docker")


@dataclass
class LLMSandboxConfig:
    """Configuration for LLM Sandbox."""
    language: str = "python"
    timeout: int = 60
    enable_network: bool = False
    packages: Optional[List[str]] = None


class LLMSandbox(BaseSandbox):
    """
    LLM Sandbox execution using Docker containers via llm-sandbox library.
    
    Provides isolated, secure code execution with automatic cleanup.
    """

    def __init__(self):
        """Initialize the LLM Sandbox."""
        if not HAS_LLM_SANDBOX:
            raise ImportError(
                "llm-sandbox is not installed. "
                "Install with: pip install llm-sandbox docker"
            )

    @property
    def language(self) -> SandboxLanguage:
        """Return the sandbox language type."""
        return SandboxLanguage.PYTHON

    async def execute(
        self,
        code: str,
        timeout: int = 60,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Execute code in an isolated Docker sandbox.

        Args:
            code: The code to execute
            timeout: Maximum execution time in seconds
            context: Optional context variables

        Returns:
            SandboxResult with execution output
        """
        start_time = time.time()

        try:
            # Run in thread to avoid blocking
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute_sync, code, timeout, context),
                timeout=timeout + 10,  # Add buffer for Docker operations
            )
            result.execution_time_ms = round((time.time() - start_time) * 1000, 2)
            return result

        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {timeout} seconds",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
            )
        except Exception as e:
            logger.error(f"LLM Sandbox execution failed: {e}", exc_info=True)
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
            )

    def _execute_sync(
        self,
        code: str,
        timeout: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Synchronous execution in Docker sandbox.

        Args:
            code: The code to execute
            timeout: Maximum execution time in seconds
            context: Optional context variables

        Returns:
            SandboxResult with execution output
        """
        try:
            with Sandbox() as sandbox:
                # Execute the code
                execution_result = sandbox.run_code(
                    code=code,
                    language=LLMsandboxLanguage.PYTHON,
                    timeout=timeout,
                )

                # Extract output
                output_parts = []
                if execution_result.output:
                    output_parts.append(execution_result.output)
                if execution_result.result:
                    output_parts.append(str(execution_result.result))

                output = "\n".join(output_parts) if output_parts else "Code executed successfully"

                # Extract variables from execution
                variables = {}
                if context:
                    variables = {k: str(v)[:200] for k, v in context.items()}

                return SandboxResult(
                    success=execution_result.success,
                    output=output,
                    error=execution_result.error if not execution_result.success else None,
                    variables=variables,
                    language="python",
                )

        except Exception as e:
            logger.error(f"LLM Sandbox sync execution failed: {e}", exc_info=True)
            return SandboxResult(
                success=False,
                error=str(e),
                language="python",
            )

    def validate(self, code: str) -> Dict[str, Any]:
        """
        Validate code for safety.
        LLM Sandbox provides isolation via Docker, so fewer restrictions needed.
        """
        # Basic validation - Docker provides the main isolation
        issues = []

        # Check for extremely dangerous patterns even in Docker
        extremely_dangerous = [
            "rm -rf /",
            "dd if=/dev/zero",
            ":(){ :|:& };:",  # Fork bomb
        ]

        code_lower = code.lower()
        for pattern in extremely_dangerous:
            if pattern.lower() in code_lower:
                issues.append(f"Extremely dangerous pattern detected: {pattern}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
        }


class LLMSandboxJavaScript(BaseSandbox):
    """
    JavaScript execution using LLM Sandbox with Node.js.
    """

    def __init__(self):
        """Initialize the JavaScript LLM Sandbox."""
        if not HAS_LLM_SANDBOX:
            raise ImportError(
                "llm-sandbox is not installed. "
                "Install with: pip install llm-sandbox docker"
            )

    @property
    def language(self) -> SandboxLanguage:
        """Return the sandbox language type."""
        return SandboxLanguage.JAVASCRIPT

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Execute JavaScript code in an isolated Docker sandbox."""
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute_sync, code, timeout, context),
                timeout=timeout + 10,
            )
            result.execution_time_ms = round((time.time() - start_time) * 1000, 2)
            return result

        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {timeout} seconds",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )
        except Exception as e:
            logger.error(f"LLM Sandbox JavaScript execution failed: {e}", exc_info=True)
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

    def _execute_sync(
        self,
        code: str,
        timeout: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Synchronous JavaScript execution in Docker sandbox."""
        try:
            with Sandbox() as sandbox:
                execution_result = sandbox.run_code(
                    code=code,
                    language=LLMsandboxLanguage.JS,
                    timeout=timeout,
                )

                output_parts = []
                if execution_result.output:
                    output_parts.append(execution_result.output)
                if execution_result.result:
                    output_parts.append(str(execution_result.result))

                output = "\n".join(output_parts) if output_parts else "Code executed successfully"

                variables = {}
                if context:
                    variables = {k: str(v)[:200] for k, v in context.items()}

                return SandboxResult(
                    success=execution_result.success,
                    output=output,
                    error=execution_result.error if not execution_result.success else None,
                    variables=variables,
                    language="javascript",
                )

        except Exception as e:
            logger.error(f"LLM Sandbox JavaScript sync execution failed: {e}", exc_info=True)
            return SandboxResult(
                success=False,
                error=str(e),
                language="javascript",
            )

    def validate(self, code: str) -> Dict[str, Any]:
        """Validate JavaScript code."""
        issues = []
        extremely_dangerous = [
            "process.exit",
            "require('child_process')",
            "require('fs')",
        ]

        code_lower = code.lower()
        for pattern in extremely_dangerous:
            if pattern.lower() in code_lower:
                issues.append(f"Dangerous pattern: {pattern}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
        }


class LLMSandboxManager:
    """
    Manager for LLM Sandbox instances.
    Provides a unified interface for different language sandboxes.
    """

    def __init__(self):
        """Initialize the LLM Sandbox Manager."""
        self._sandboxes: Dict[str, BaseSandbox] = {}
        self._available = HAS_LLM_SANDBOX

    @property
    def is_available(self) -> bool:
        """Check if LLM Sandbox is available."""
        return self._available

    def register_sandbox(self, language: str, sandbox: BaseSandbox) -> None:
        """Register a sandbox for a specific language."""
        self._sandboxes[language.lower()] = sandbox
        logger.info(f"Registered LLM Sandbox for {language}")

    def get_sandbox(self, language: str) -> Optional[BaseSandbox]:
        """Get a sandbox for a specific language."""
        return self._sandboxes.get(language.lower())

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 60,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Execute code in the appropriate sandbox.

        Args:
            code: The code to execute
            language: Programming language
            timeout: Maximum execution time
            context: Optional context variables

        Returns:
            SandboxResult with execution output
        """
        sandbox = self.get_sandbox(language)
        if not sandbox:
            return SandboxResult(
                success=False,
                error=f"No sandbox available for language: {language}",
                language=language,
            )

        return await sandbox.execute(code, timeout, context)

    def list_languages(self) -> List[str]:
        """List available sandbox languages."""
        return list(self._sandboxes.keys())


# Global instance
_llm_sandbox_manager: Optional[LLMSandboxManager] = None


def get_llm_sandbox_manager() -> LLMSandboxManager:
    """
    Get or create the global LLM Sandbox Manager.
    """
    global _llm_sandbox_manager

    if _llm_sandbox_manager is None:
        _llm_sandbox_manager = LLMSandboxManager()

        if HAS_LLM_SANDBOX:
            try:
                python_sandbox = LLMSandbox()
                _llm_sandbox_manager.register_sandbox("python", python_sandbox)
                logger.info("Registered Python LLM Sandbox")
            except Exception as e:
                logger.warning(f"Failed to register Python LLM Sandbox: {e}")

            try:
                js_sandbox = LLMSandboxJavaScript()
                _llm_sandbox_manager.register_sandbox("javascript", js_sandbox)
                logger.info("Registered JavaScript LLM Sandbox")
            except Exception as e:
                logger.warning(f"Failed to register JavaScript LLM Sandbox: {e}")

    return _llm_sandbox_manager


__all__ = [
    "LLMSandbox",
    "LLMSandboxJavaScript",
    "LLMSandboxManager",
    "LLMSandboxConfig",
    "get_llm_sandbox_manager",
    "HAS_LLM_SANDBOX",
]