"""
Python Sandbox
==============
Wraps the existing execute_python() logic from core/tools.py
behind the BaseSandbox interface. All existing safety checks preserved.
"""

import math
import statistics
import csv
import io as _io
import json
import re as re_mod
import traceback
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage

# ---------------------------------------------------------------------------
# Dangerous code keywords — same as core/tools.py
# ---------------------------------------------------------------------------
_DANGEROUS_KEYWORDS = frozenset({
    "import os", "import sys", "import subprocess", "import shutil",
    "exec(", "eval(", "open(", "file(",
    "os.", "sys.", "subprocess.", "shutil.",
    "requests.", "urllib.", "socket.",
})

# ---------------------------------------------------------------------------
# Sandbox globals — built once at module load
# ---------------------------------------------------------------------------
_SANDBOX_GLOBALS: Dict[str, Any] = {
    "__builtins__": {
        "abs": abs, "all": all, "any": any, "bool": bool,
        "dict": dict, "enumerate": enumerate, "filter": filter,
        "float": float, "format": format, "int": int, "len": len,
        "list": list, "map": map, "max": max, "min": min,
        "pow": pow, "range": range, "reversed": reversed,
        "round": round, "set": set, "slice": slice, "sorted": sorted,
        "str": str, "sum": sum, "tuple": tuple, "zip": zip,
        "print": print, "True": True, "False": False, "None": None,
        "isinstance": isinstance, "type": type, "hasattr": hasattr,
        "getattr": getattr, "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError, "Exception": Exception,
        "__import__": __import__,
    },
    "math": math,
    "statistics": statistics,
    "csv": csv,
    "io": _io,
    "json": json,
    "StringIO": _io.StringIO,
    "BytesIO": _io.BytesIO,
    "re": re_mod,
    "datetime": datetime,
    "timedelta": timedelta,
}

# Inject numpy/pandas if available
try:
    import numpy as np
    _SANDBOX_GLOBALS["np"] = np
    _SANDBOX_GLOBALS["numpy"] = np
except ImportError:
    pass

try:
    import pandas as pd
    _SANDBOX_GLOBALS["pd"] = pd
    _SANDBOX_GLOBALS["pandas"] = pd
except ImportError:
    pass


class PythonSandbox(BaseSandbox):
    """Python execution sandbox using exec() with restricted globals."""

    @property
    def language(self) -> SandboxLanguage:
        return SandboxLanguage.PYTHON

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Execute Python code in a sandboxed environment."""
        start_time = time.time()

        # Safety check
        validation = self.validate(code)
        if not validation["safe"]:
            return SandboxResult(
                success=False,
                error=f"Unsafe code detected: {'; '.join(validation['issues'])}",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
            )

        try:
            # Run in thread to avoid blocking event loop
            result = await asyncio.wait_for(
                asyncio.to_thread(self._execute_sync, code, context),
                timeout=timeout,
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
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
            )

    def _execute_sync(self, code: str, context: Optional[Dict] = None) -> SandboxResult:
        """Synchronous execution (runs in thread)."""
        local_vars: Dict[str, Any] = {}

        # Inject context variables
        if context:
            local_vars.update(context)

        try:
            exec(code, _SANDBOX_GLOBALS, local_vars)

            output = local_vars.get("result", local_vars.get("output", None))
            if output is not None:
                output = str(output)
            else:
                output = "Code executed successfully"

            variables = {
                k: str(v)[:200]
                for k, v in local_vars.items()
                if not k.startswith("_")
            }

            return SandboxResult(
                success=True,
                output=output,
                variables=variables,
                language="python",
            )

        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                output=traceback.format_exc()[:500],
                language="python",
            )

    def validate(self, code: str) -> Dict[str, Any]:
        """Check code for dangerous patterns."""
        issues = []
        code_lower = code.lower()

        for keyword in _DANGEROUS_KEYWORDS:
            if keyword in code_lower:
                # Allow safe io.StringIO / csv patterns
                if keyword == "open(" and (
                    "io.stringio" in code_lower or "csv" in code_lower
                ):
                    continue
                issues.append(f"Dangerous pattern: {keyword}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
        }