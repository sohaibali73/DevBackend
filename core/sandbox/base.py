"""
Base Sandbox Interface
======================
Abstract classes and data types for code execution sandboxes.
"""

import enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


class SandboxLanguage(enum.Enum):
    """Supported sandbox execution languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    REACT = "react"    # Client-side React/JSX → returns HTML artifact
    HTML = "html"      # Raw HTML document execution


@dataclass
class DisplayArtifact:
    """
    A rich display artifact produced by code execution.

    Attributes:
        type:         MIME type, e.g. "text/html", "image/png", "application/json"
        data:         Content — base64-encoded for binary, raw string for text
        encoding:     "utf-8" for text, "base64" for binary
        display_type: Frontend rendering hint: "react" | "html" | "image" | "json" | "text"
        metadata:     Optional extra info (e.g. {"width": 800, "height": 600})
        artifact_id:  Unique ID used for artifact retrieval via the API
    """
    type: str
    data: str
    encoding: str = "utf-8"
    display_type: str = "text"
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class SandboxResult:
    """
    Unified result from any sandbox execution.

    Attributes:
        success:          Whether execution completed without error.
        output:           Captured stdout / result text.
        error:            stderr / exception message.
        execution_time_ms: Time taken in milliseconds.
        language:         Which language was executed.
        variables:        Captured local variables (Python only, serializable values).
        artifacts:        Generated display artifacts (images, HTML, React, etc.).
        display_type:     Primary display hint for the frontend.
        execution_id:     UUID linking to the DB execution record.
        session_id:       UUID linking to the sandbox session.
    """
    success: bool = True
    output: str = ""
    error: str = ""
    execution_time_ms: float = 0
    language: str = "python"
    variables: Dict[str, str] = field(default_factory=dict)
    artifacts: List[DisplayArtifact] = field(default_factory=list)
    display_type: str = "text"
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""


class BaseSandbox(ABC):
    """Abstract base for all code execution sandboxes."""

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
        session_id: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute code and return a SandboxResult.

        Args:
            code:       Source code to execute.
            timeout:    Maximum execution time in seconds.
            context:    Optional variables to inject into the execution scope.
            session_id: Optional session ID for namespace persistence.

        Returns:
            SandboxResult with output, error, timing, artifacts, etc.
        """
        ...

    @abstractmethod
    def validate(self, code: str) -> Dict[str, Any]:
        """
        Pre-validate code for safety before execution.

        Returns:
            Dict with "safe" (bool) and "issues" (list[str]).
        """
        ...
