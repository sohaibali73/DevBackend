"""
Node.js Sandbox (Advanced)
==========================
JavaScript execution via Node.js subprocess with full npm package support.
Supports React, JSX, and popular libraries like Lucide React.
"""

import asyncio
import time
import json
import re
import os
import shutil
import tempfile
import hashlib
from typing import Dict, Any, Optional, List
from pathlib import Path

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
    r"child_process",
    r"spawn\s*\(",
    r"exec\s*\(",
    r"execSync\s*\(",
]

_DANGEROUS_RE = [re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS]

# Popular pre-approved packages that can be used
PRE_APPROVED_PACKAGES = [
    "react",
    "react-dom",
    "lucide-react",
    "@radix-ui/react-icons",
    "clsx",
    "tailwind-merge",
    "class-variance-authority",
    "date-fns",
    "lodash",
    "uuid",
    "zod",
    "axios",
    "dayjs",
    "moment",
    "ramda",
    "mathjs",
    "lodash-es",
    "immer",
    "zustand",
    "jotai",
    "recoil",
]

# Base package.json template
BASE_PACKAGE_JSON = {
    "name": "sandbox-execution",
    "version": "1.0.0",
    "private": True,
    "type": "module",
    "dependencies": {},
    "devDependencies": {
        "esbuild": "^0.20.0"
    }
}

# Cache directory for installed packages
_CACHE_DIR = Path(tempfile.gettempdir()) / "sandbox_node_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _extract_imports(code: str) -> List[str]:
    """Extract npm package names from import/require statements."""
    packages = set()

    # Match ES6 imports: import X from 'package' or import { X } from 'package'
    import_pattern = r"""import\s+(?:(?:[\w*\s{},]*)\s+from\s+)?['"]([^'"]+)['"]"""
    for match in re.finditer(import_pattern, code):
        pkg = match.group(1)
        # Skip relative imports
        if not pkg.startswith('.') and not pkg.startswith('/'):
            # Handle scoped packages and subpaths
            if pkg.startswith('@'):
                parts = pkg.split('/')
                if len(parts) >= 2:
                    packages.add('/'.join(parts[:2]))
                else:
                    packages.add(pkg)
            else:
                packages.add(pkg.split('/')[0])

    # Match require statements: require('package')
    require_pattern = r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""
    for match in re.finditer(require_pattern, code):
        pkg = match.group(1)
        if not pkg.startswith('.') and not pkg.startswith('/'):
            if pkg.startswith('@'):
                parts = pkg.split('/')
                if len(parts) >= 2:
                    packages.add('/'.join(parts[:2]))
                else:
                    packages.add(pkg)
            else:
                packages.add(pkg.split('/')[0])

    return list(packages)


def _get_cache_key(packages: List[str]) -> str:
    """Generate a cache key from package list."""
    sorted_pkgs = sorted(packages)
    return hashlib.md5(json.dumps(sorted_pkgs).encode()).hexdigest()


class NodeSandbox(BaseSandbox):
    """Advanced JavaScript execution sandbox with npm package support."""

    def __init__(self):
        self._node_modules_cache: Dict[str, Path] = {}

    @property
    def language(self) -> SandboxLanguage:
        return SandboxLanguage.JAVASCRIPT

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """Execute JavaScript code with full npm support."""
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

        # Create temp directory for this execution
        temp_dir = None
        try:
            temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_node_"))

            # Extract required packages from code
            required_packages = _extract_imports(code)

            # Check if this is React/JSX code
            is_react_code = any(
                pkg in required_packages
                for pkg in ["react", "react-dom", "lucide-react"]
            ) or "jsx" in code.lower() or "<" in code and "/>" in code

            # Setup project
            await self._setup_project(temp_dir, required_packages, is_react_code)

            # Prepare the code file
            code_file = temp_dir / "index.js"
            if is_react_code:
                code_file = temp_dir / "index.jsx"

            # Add context injection if provided
            full_code = code
            if context:
                context_json = json.dumps(
                    {k: str(v) for k, v in context.items()}
                )
                full_code = f"const context = {context_json};\n{code}"

            # Write the code file
            code_file.write_text(full_code, encoding="utf-8")

            # Execute with esbuild for JSX support
            if is_react_code:
                return await self._execute_react(temp_dir, timeout, start_time)
            else:
                return await self._execute_plain(temp_dir, code_file, timeout, start_time)

        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )
        finally:
            # Cleanup temp directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

    async def _setup_project(
        self,
        temp_dir: Path,
        packages: List[str],
        is_react: bool
    ) -> None:
        """Setup a Node.js project with required dependencies."""
        # Create package.json
        pkg_json = BASE_PACKAGE_JSON.copy()
        pkg_json["dependencies"] = {}

        # Add requested packages
        for pkg in packages:
            if pkg in PRE_APPROVED_PACKAGES or pkg.startswith("@"):
                pkg_json["dependencies"][pkg] = "latest"

        # Ensure React is included for React code
        if is_react:
            pkg_json["dependencies"]["react"] = "latest"
            pkg_json["dependencies"]["react-dom"] = "latest"

        # Write package.json
        (temp_dir / "package.json").write_text(
            json.dumps(pkg_json, indent=2),
            encoding="utf-8"
        )

        # Check cache for node_modules
        cache_key = _get_cache_key(list(pkg_json["dependencies"].keys()))
        cached_modules = self._node_modules_cache.get(cache_key)

        if cached_modules and cached_modules.exists():
            # Copy from cache
            shutil.copytree(cached_modules, temp_dir / "node_modules")
        else:
            # Install packages
            proc = await asyncio.create_subprocess_exec(
                "npm", "install", "--prefer-offline", "--no-audit", "--no-fund",
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Cache node_modules
            node_modules = temp_dir / "node_modules"
            if node_modules.exists():
                cache_target = _CACHE_DIR / cache_key
                if cache_target.exists():
                    shutil.rmtree(cache_target)
                shutil.copytree(node_modules, cache_target)
                self._node_modules_cache[cache_key] = cache_target

    async def _execute_react(
        self,
        temp_dir: Path,
        timeout: int,
        start_time: float
    ) -> SandboxResult:
        """Execute React code using esbuild for transpilation."""
        try:
            # First, bundle with esbuild
            bundled_file = temp_dir / "bundle.js"

            proc = await asyncio.create_subprocess_exec(
                "npx", "esbuild", "index.jsx",
                "--bundle",
                "--format=esm",
                "--platform=node",
                "--outfile=bundle.js",
                "--external:react",
                "--external:react-dom",
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=30
                )
            except asyncio.TimeoutError:
                proc.kill()
                return SandboxResult(
                    success=False,
                    error="Bundling timed out",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            if proc.returncode != 0:
                error_msg = stderr.decode().strip()
                return SandboxResult(
                    success=False,
                    error=f"Bundling failed: {error_msg}",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            # Execute the bundled code
            exec_proc = await asyncio.create_subprocess_exec(
                "node", "--experimental-vm-modules", str(bundled_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(temp_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    exec_proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                exec_proc.kill()
                return SandboxResult(
                    success=False,
                    error=f"Execution timed out after {timeout} seconds",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            elapsed = round((time.time() - start_time) * 1000, 2)

            if exec_proc.returncode == 0:
                output = stdout.decode().strip()
                return SandboxResult(
                    success=True,
                    output=output if output else "Code executed successfully",
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
                error="Node.js or npm is not installed.",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

    async def _execute_plain(
        self,
        temp_dir: Path,
        code_file: Path,
        timeout: int,
        start_time: float
    ) -> SandboxResult:
        """Execute plain JavaScript code."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", str(code_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(temp_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
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

    def list_available_packages(self) -> List[str]:
        """Return list of pre-approved packages."""
        return PRE_APPROVED_PACKAGES.copy()