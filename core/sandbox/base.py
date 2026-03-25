"""
Base Sandbox Interface
======================
Abstract classes for code execution sandboxes.
"""

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


class SandboxLanguage(enum.Enum):
    """Supported sandbox execution languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"


@dataclass
class SandboxResult:
    """
    Unified result from any sandbox execution.

    Attributes:
        success: Whether execution completed without error.
        output: stdout / result text.
        error: stderr / exception message.
        execution_time_ms: Time taken in milliseconds.
        language: Which language was executed.
        variables: Captured local variables (Python only).
        artifacts: Generated files (images, data, etc.).
    """
    success: bool = True
    output: str = ""
    error: str = ""
    execution_time_ms: float = 0
    language: str = "python"
    variables: Dict[str, str] = field(default_factory=dict)
    artifacts: list = field(default_factory=list)


class BaseSandbox(ABC):
    """Abstract sandbox for code execution."""

    @property
    @abstractmethod
    def language(self) -> SandboxLanguage:
        """The language this sandbox executes."""
        ...

    @abstractmethod
    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Execute code and return result.

        Args:
            code: Source code to execute.
            timeout: Maximum execution time in seconds.
            context: Optional context variables to inject.

        Returns:
            SandboxResult with output, error, timing, etc.
        """
        ...

    @abstractmethod
    def validate(self, code: str) -> Dict[str, Any]:
        """
        Pre-validate code for safety.

        Returns:
            Dict with "safe" (bool) and "issues" (list of strings).
        """
        ...