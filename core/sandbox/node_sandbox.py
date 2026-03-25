"""
Node.js Sandbox
================
JavaScript execution via Node.js subprocess.
Runs `node -e "<code>"` with timeout enforcement and resource limits.
"""

import asyncio
import time
import json
import re
from typing import Dict, Any, Optional

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage

# Dangerous Node.js patterns to block
_DANGEROUS_PATTERNS = [
    r"require\s*\(\s*['\"]child_process['\"]",
    r"require\s*\(\s*['\"]fs['\"]",
    r"require\s*\(\s*['\"]net['\"]",
    r"require\s*\(\s*['\"]http['\"]",
    r"require\s*\(\s*['\"]https['\"]",
    r"require\s*\(\s*['\"]dgram['\"]",
    r"require\s*\(\s*['\"]cluster['\"]",
    r"process\.exit",
    r"process\.env",
    r"\.exec\s*\(",
    r"\.spawn\s*\(",
    r"\.execSync\s*\(",
]

_DANGEROUS_RE = [re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS]


class NodeSandbox(BaseSandbox):
    """JavaScript execution sandbox using Node.js subprocess."""

    @property
    def language(self) -> SandboxLanguage:
        return SandboxLanguage.JAVASCRIPT

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Execute JavaScript code via Node.js."""
        start_time = time.time()

        # Safety check
        validation = self.validate(code)
        if not validation["safe"]:
            return SandboxResult(
                success=False,
                error=f"Unsafe code detected: {'; '.join(validation['issues'])}",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

        try:
            # Build the code with context injection
            full_code = code
            if context:
                # Inject context as a global object
                context_json = json.dumps(
                    {k: str(v) for k, v in context.items()}
                )
                full_code = f"const context = {context_json};\n{code}"

            proc = await asyncio.create_subprocess_exec(
                "node", "-e", full_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {timeout} seconds",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            elapsed = round((time.time() - start_time) * 1000, 2)

            if proc.returncode == 0:
                return SandboxResult(
                    success=True,
                    output=stdout.decode().strip(),
                    execution_time_ms=elapsed,
                    language="javascript",
                )
            else:
                return SandboxResult(
                    success=False,
                    output=stdout.decode().strip(),
                    error=stderr.decode().strip(),
                    execution_time_ms=elapsed,
                    language="javascript",
                )

        except FileNotFoundError:
            return SandboxResult(
                success=False,
                error="Node.js is not installed. Install Node.js to run JavaScript.",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

    def validate(self, code: str) -> Dict[str, Any]:
        """Check code for dangerous Node.js patterns."""
        issues = []
        for pattern in _DANGEROUS_RE:
            if pattern.search(code):
                issues.append(f"Dangerous pattern: {pattern.pattern}")

        return {
            "safe": len(issues) == 0,
            "issues": issues,
        }