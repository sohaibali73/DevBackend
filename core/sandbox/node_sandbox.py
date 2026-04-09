"""
Node.js + React Sandboxes
=========================
Two separate sandbox classes:

  NodeSandbox   (language="javascript") — plain JS via Node.js subprocess
  ReactSandbox  (language="react")      — JSX/React wrapped in a self-contained
                                          HTML document; no Node.js subprocess.
                                          Frontend iframes the returned HTML artifact.

Fix 3a — _wrap_for_client_render(): ESM importmap + Babel standalone, no server-side Node
Fix 3b — ReactSandbox registered as its own language="react"
Fix 3c — node_modules cache uses a configurable persistent path (not /tmp)
"""

import asyncio
import os
import re
import shutil
import time
import json
import hashlib
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage, DisplayArtifact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent cache path (Fix 3c) — configurable, not /tmp
# ---------------------------------------------------------------------------
_SANDBOX_HOME = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_NODE_CACHE_DIR = _SANDBOX_HOME / "node_cache"
_NODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Security patterns — dangerous Node.js patterns to block
# ---------------------------------------------------------------------------
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
]

_DANGEROUS_RE = [re.compile(p, re.IGNORECASE) for p in _DANGEROUS_PATTERNS]

# ---------------------------------------------------------------------------
# Pre-approved packages
# ---------------------------------------------------------------------------
PRE_APPROVED_PACKAGES = [
    # React ecosystem
    "react", "react-dom", "lucide-react",
    "@radix-ui/react-icons", "react-icons", "framer-motion",
    "react-hook-form", "react-router-dom",
    # UI utilities
    "clsx", "tailwind-merge", "class-variance-authority",
    "@headlessui/react", "@heroicons/react",
    # Date/time
    "date-fns", "dayjs", "moment",
    # Data utilities
    "lodash", "lodash-es", "ramda", "mathjs", "uuid", "zod",
    # HTTP
    "axios",
    # State management
    "immer", "zustand", "jotai", "recoil",
    # Other
    "classnames", "prop-types", "react-fast-compare", "shallowequal",
    # Charts
    "recharts", "chart.js", "d3",
]

# ---------------------------------------------------------------------------
# CDN import map for React client-side rendering (Fix 3a)
# ---------------------------------------------------------------------------
_ESM_IMPORT_MAP: Dict[str, str] = {
    "react":                       "https://esm.sh/react@18",
    "react-dom":                   "https://esm.sh/react-dom@18",
    "react-dom/client":            "https://esm.sh/react-dom@18/client",
    "react-dom/server":            "https://esm.sh/react-dom@18/server",
    "lucide-react":                "https://esm.sh/lucide-react",
    "@radix-ui/react-icons":       "https://esm.sh/@radix-ui/react-icons",
    "react-icons":                 "https://esm.sh/react-icons",
    "framer-motion":               "https://esm.sh/framer-motion",
    "react-hook-form":             "https://esm.sh/react-hook-form",
    "react-router-dom":            "https://esm.sh/react-router-dom",
    "clsx":                        "https://esm.sh/clsx",
    "tailwind-merge":              "https://esm.sh/tailwind-merge",
    "class-variance-authority":    "https://esm.sh/class-variance-authority",
    "@headlessui/react":           "https://esm.sh/@headlessui/react",
    "@heroicons/react":            "https://esm.sh/@heroicons/react",
    "date-fns":                    "https://esm.sh/date-fns",
    "dayjs":                       "https://esm.sh/dayjs",
    "moment":                      "https://esm.sh/moment",
    "lodash":                      "https://esm.sh/lodash",
    "lodash-es":                   "https://esm.sh/lodash-es",
    "ramda":                       "https://esm.sh/ramda",
    "mathjs":                      "https://esm.sh/mathjs",
    "uuid":                        "https://esm.sh/uuid",
    "zod":                         "https://esm.sh/zod",
    "axios":                       "https://esm.sh/axios",
    "immer":                       "https://esm.sh/immer",
    "zustand":                     "https://esm.sh/zustand",
    "jotai":                       "https://esm.sh/jotai",
    "recoil":                      "https://esm.sh/recoil",
    "classnames":                  "https://esm.sh/classnames",
    "prop-types":                  "https://esm.sh/prop-types",
    "recharts":                    "https://esm.sh/recharts",
    "chart.js":                    "https://esm.sh/chart.js",
    "d3":                          "https://esm.sh/d3",
}

# Base package.json template for Node.js execution
_BASE_PACKAGE_JSON = {
    "name": "sandbox-execution",
    "version": "1.0.0",
    "private": True,
    "type": "module",
    "dependencies": {"esbuild": "^0.20.0"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_imports(code: str) -> List[str]:
    """Extract npm package names from ES6 import / require statements."""
    packages: set = set()
    import_re = r"""import\s+(?:(?:[\w*\s{},]*)\s+from\s+)?['"]([^'"]+)['"]"""
    require_re = r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""

    for match in re.finditer(import_re, code):
        pkg = match.group(1)
        if not pkg.startswith((".", "/")):
            root = "/".join(pkg.split("/")[:2]) if pkg.startswith("@") else pkg.split("/")[0]
            packages.add(root)

    for match in re.finditer(require_re, code):
        pkg = match.group(1)
        if not pkg.startswith((".", "/")):
            root = "/".join(pkg.split("/")[:2]) if pkg.startswith("@") else pkg.split("/")[0]
            packages.add(root)

    return list(packages)


def _get_cache_key(packages: List[str]) -> str:
    """MD5 key for a sorted package list."""
    return hashlib.md5(json.dumps(sorted(packages)).encode()).hexdigest()


def _is_react_code(code: str) -> bool:
    """Return True if the code contains JSX or React imports."""
    jsx_patterns = [
        r"<[A-Z][a-zA-Z]*[\s/>]",
        r"<[a-z]+[\s/>]",
        r"</[A-Za-z]+>",
        r"<>",
        r"<React\.",
        r"<Fragment>",
        r"createElement\s*\(",
    ]
    react_imports = [
        r"""from\s+['"]react['"]""",
        r"""from\s+['"]react-dom['"]""",
        r"""from\s+['"]lucide-react['"]""",
        r"""from\s+['"]react-icons['"]""",
    ]
    return any(re.search(p, code) for p in jsx_patterns + react_imports)


# ---------------------------------------------------------------------------
# Fix 3a — Client-side React render wrapper
# ---------------------------------------------------------------------------
def _wrap_for_client_render(jsx_code: str) -> str:
    """
    Wrap JSX/React code in a self-contained HTML document.

    Uses:
      - ESM importmap → esm.sh CDN for React + approved packages
      - Babel standalone for in-browser JSX transpilation
      - Tailwind CSS CDN for styling
      - Auto-detects and mounts: App → Component → Default

    No Node.js execution is needed — the frontend simply iframes this HTML.
    """
    import_map_json = json.dumps({"imports": _ESM_IMPORT_MAP}, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sandbox</title>
  <script type="importmap">
{import_map_json}
  </script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ margin: 0; padding: 0; background: transparent; font-family: sans-serif; }}
    #root {{ min-height: 100vh; }}
    #sandbox-error {{
      padding: 16px; background: #fee2e2; border: 1px solid #fca5a5;
      border-radius: 8px; margin: 16px; font-family: monospace;
      white-space: pre-wrap; color: #991b1b;
    }}
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" data-type="module" data-presets="react">
    import React, {{ useState, useEffect, useRef, useCallback, useMemo, useReducer, useContext }} from 'react';
    import {{ createRoot }} from 'react-dom/client';

    // ---- User code ----
    {jsx_code}
    // ---- End user code ----

    // Auto-detect and mount the exported component
    (function mountApp() {{
      const root = createRoot(document.getElementById('root'));
      if (typeof App !== 'undefined') {{ root.render(React.createElement(App)); return; }}
      if (typeof Component !== 'undefined') {{ root.render(React.createElement(Component)); return; }}
      if (typeof Default !== 'undefined') {{ root.render(React.createElement(Default)); return; }}
      // Try to find any capitalised function / class
      const candidates = [typeof Dashboard, typeof Page, typeof View, typeof Widget]
        .map((t, i) => [['Dashboard','Page','View','Widget'][i], t])
        .filter(([,t]) => t !== 'undefined');
      if (candidates.length) {{
        const [name] = candidates[0];
        const C = eval(name);
        root.render(React.createElement(C));
        return;
      }}
      document.getElementById('root').innerHTML =
        '<div id="sandbox-error">No component found. Export a component named App, Component, or Default.</div>';
    }})();
  </script>
  <script>
    window.addEventListener('error', function(e) {{
      const el = document.getElementById('sandbox-error') || document.createElement('div');
      el.id = 'sandbox-error';
      el.textContent = 'Runtime error: ' + e.message;
      document.body.appendChild(el);
    }});
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# ReactSandbox (Fix 3b) — no subprocess, pure HTML artifact output
# ---------------------------------------------------------------------------
class ReactSandbox(BaseSandbox):
    """
    React/JSX sandbox.

    Wraps the user's JSX code in a self-contained HTML document using the
    esm.sh CDN + Babel standalone. No Node.js subprocess is spawned.
    The returned artifact is a complete HTML page the frontend can iframe.
    """

    @property
    def language(self) -> SandboxLanguage:
        return SandboxLanguage.REACT

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SandboxResult:
        """Wrap JSX code and return an HTML DisplayArtifact immediately."""
        start_time = time.time()
        execution_id = str(uuid.uuid4())
        if session_id is None:
            session_id = str(uuid.uuid4())

        validation = self.validate(code)
        if not validation["safe"]:
            return SandboxResult(
                success=False,
                error=f"Unsafe code: {'; '.join(validation['issues'])}",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="react",
                execution_id=execution_id,
                session_id=session_id,
            )

        try:
            html = _wrap_for_client_render(code)
            artifact = DisplayArtifact(
                type="text/html",
                data=html,
                encoding="utf-8",
                display_type="react",
                metadata={"renderer": "client", "framework": "react18"},
            )
            elapsed = round((time.time() - start_time) * 1000, 2)

            # Persist to DB (best-effort)
            await self._persist(session_id, execution_id, code, html, elapsed, artifact)

            return SandboxResult(
                success=True,
                output="React component compiled successfully",
                artifacts=[artifact],
                display_type="react",
                language="react",
                execution_time_ms=elapsed,
                execution_id=execution_id,
                session_id=session_id,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="react",
                execution_id=execution_id,
                session_id=session_id,
            )

    async def _persist(
        self,
        session_id: str,
        execution_id: str,
        code: str,
        html: str,
        elapsed: float,
        artifact: DisplayArtifact,
    ) -> None:
        try:
            from core.sandbox.db import save_execution, save_artifact
            await save_execution(
                execution_id=execution_id,
                session_id=session_id,
                code=code,
                language="react",
                output="React component compiled successfully",
                error="",
                success=True,
                exec_time_ms=elapsed,
            )
            await save_artifact(
                artifact_id=artifact.artifact_id,
                session_id=session_id,
                execution_id=execution_id,
                type_=artifact.type,
                display_type=artifact.display_type,
                data=artifact.data,
                encoding=artifact.encoding,
                metadata=artifact.metadata,
            )
        except Exception as e:
            logger.debug("React artifact persistence skipped: %s", e)

    def validate(self, code: str) -> Dict[str, Any]:
        """Check for dangerous Node.js patterns."""
        issues = []
        for pattern in _DANGEROUS_RE:
            if pattern.search(code):
                issues.append(f"Dangerous pattern: {pattern.pattern}")
        return {"safe": len(issues) == 0, "issues": issues}

    def list_available_packages(self) -> List[str]:
        return PRE_APPROVED_PACKAGES.copy()


# ---------------------------------------------------------------------------
# NodeSandbox — plain JavaScript via Node.js subprocess
# ---------------------------------------------------------------------------
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
        session_id: Optional[str] = None,
    ) -> SandboxResult:
        """Execute JavaScript code with full npm support."""
        start_time = time.time()
        execution_id = str(uuid.uuid4())
        if session_id is None:
            session_id = str(uuid.uuid4())

        validation = self.validate(code)
        if not validation["safe"]:
            return SandboxResult(
                success=False,
                error=f"Unsafe code detected: {'; '.join(validation['issues'])}",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
                execution_id=execution_id,
                session_id=session_id,
            )

        temp_dir = None
        try:
            import tempfile
            temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_node_"))
            required_packages = _extract_imports(code)
            is_react = _is_react_code(code)

            await self._setup_project(temp_dir, required_packages, is_react)

            if is_react:
                code_file = temp_dir / "index.jsx"
                full_code = self._wrap_react_ssr(code)
            else:
                code_file = temp_dir / "index.js"
                full_code = code

            if context:
                ctx_json = json.dumps({k: str(v) for k, v in context.items()})
                full_code = f"const context = {ctx_json};\n{full_code}"

            code_file.write_text(full_code, encoding="utf-8")

            if is_react:
                result = await self._execute_react(temp_dir, timeout, start_time)
            else:
                result = await self._execute_plain(temp_dir, code_file, timeout, start_time)

            result.execution_id = execution_id
            result.session_id = session_id

            # Persist execution record
            try:
                from core.sandbox.db import save_execution
                await save_execution(
                    execution_id=execution_id,
                    session_id=session_id,
                    code=code,
                    language="javascript",
                    output=result.output or "",
                    error=result.error or "",
                    success=result.success,
                    exec_time_ms=result.execution_time_ms,
                )
            except Exception:
                pass

            return result

        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
                execution_id=execution_id,
                session_id=session_id,
            )
        finally:
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

    def _wrap_react_ssr(self, code: str) -> str:
        """Wrap React code for server-side rendering via renderToString."""
        has_default_export = bool(re.search(r"export\s+default", code))

        wrapped = code + "\n\n"
        component_match = re.search(r"export\s+default\s+(\w+)", code)
        if component_match:
            name = component_match.group(1)
            wrapped += f"""
import {{ renderToString }} from 'react-dom/server';
import {{ createElement }} from 'react';
console.log(renderToString(createElement({name})));
"""
        else:
            func_matches = re.findall(r"(?:function|const)\s+([A-Z][a-zA-Z]*)", code)
            if func_matches:
                name = func_matches[-1]
                wrapped += f"""
import {{ renderToString }} from 'react-dom/server';
import {{ createElement }} from 'react';
console.log(renderToString(createElement({name})));
"""
        return wrapped

    async def _setup_project(
        self,
        temp_dir: Path,
        packages: List[str],
        is_react: bool,
    ) -> None:
        """Setup package.json and install or link cached node_modules."""
        pkg_json = {
            **_BASE_PACKAGE_JSON,
            "dependencies": {},
        }
        for pkg in packages:
            if pkg in PRE_APPROVED_PACKAGES or pkg.startswith("@"):
                pkg_json["dependencies"][pkg] = "latest"
        if is_react:
            pkg_json["dependencies"]["react"] = "latest"
            pkg_json["dependencies"]["react-dom"] = "latest"

        (temp_dir / "package.json").write_text(
            json.dumps(pkg_json, indent=2), encoding="utf-8"
        )

        dep_keys = list(pkg_json["dependencies"].keys())
        cache_key = _get_cache_key(dep_keys)

        # Check in-memory cache first (persistent across requests)
        cached = self._node_modules_cache.get(cache_key)
        if cached and cached.exists():
            shutil.copytree(cached, temp_dir / "node_modules")
            return

        # Check persistent disk cache (Fix 3c — survives restart)
        disk_cache = _NODE_CACHE_DIR / cache_key
        if disk_cache.exists():
            shutil.copytree(disk_cache, temp_dir / "node_modules")
            self._node_modules_cache[cache_key] = disk_cache
            return

        # Install fresh
        proc = await asyncio.create_subprocess_exec(
            "npm", "install", "--prefer-offline", "--no-audit", "--no-fund",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Cache to persistent disk (Fix 3c)
        node_modules = temp_dir / "node_modules"
        if node_modules.exists() and dep_keys:
            if disk_cache.exists():
                shutil.rmtree(disk_cache)
            shutil.copytree(node_modules, disk_cache)
            self._node_modules_cache[cache_key] = disk_cache

    async def _execute_react(
        self,
        temp_dir: Path,
        timeout: int,
        start_time: float,
    ) -> SandboxResult:
        """Bundle index.jsx with esbuild and execute with Node.js."""
        try:
            bundled = temp_dir / "bundle.js"
            proc = await asyncio.create_subprocess_exec(
                "npx", "esbuild", "index.jsx",
                "--bundle", "--format=cjs", "--platform=node",
                "--outfile=bundle.js", "--jsx=automatic", "--loader:.jsx=jsx",
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except asyncio.TimeoutError:
                proc.kill()
                return SandboxResult(
                    success=False, error="Bundling timed out",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )
            if proc.returncode != 0:
                return SandboxResult(
                    success=False,
                    error=f"Bundling failed: {stderr.decode().strip()}",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            exec_proc = await asyncio.create_subprocess_exec(
                "node", str(bundled),
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
                    error=f"Execution timed out after {timeout}s",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            elapsed = round((time.time() - start_time) * 1000, 2)
            out = stdout.decode().strip()
            err = stderr.decode().strip()

            if exec_proc.returncode == 0:
                return SandboxResult(
                    success=True,
                    output=out or "Code executed successfully",
                    execution_time_ms=elapsed,
                    language="javascript",
                )
            return SandboxResult(
                success=False, output=out, error=err or "Execution failed",
                execution_time_ms=elapsed, language="javascript",
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False, error="Node.js or npm is not installed.",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

    async def _execute_plain(
        self,
        temp_dir: Path,
        code_file: Path,
        timeout: int,
        start_time: float,
    ) -> SandboxResult:
        """Execute plain JavaScript with Node.js."""
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
                    error=f"Execution timed out after {timeout}s",
                    execution_time_ms=round((time.time() - start_time) * 1000, 2),
                    language="javascript",
                )

            elapsed = round((time.time() - start_time) * 1000, 2)
            out = stdout.decode().strip()
            err = stderr.decode().strip()

            if proc.returncode == 0:
                return SandboxResult(
                    success=True,
                    output=out or "Code executed successfully",
                    execution_time_ms=elapsed,
                    language="javascript",
                )
            return SandboxResult(
                success=False, output=out, error=err or "Execution failed",
                execution_time_ms=elapsed, language="javascript",
            )
        except FileNotFoundError:
            return SandboxResult(
                success=False, error="Node.js is not installed.",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="javascript",
            )

    def validate(self, code: str) -> Dict[str, Any]:
        """Check for dangerous Node.js patterns and unapproved packages."""
        issues = []
        for pattern in _DANGEROUS_RE:
            if pattern.search(code):
                issues.append(f"Dangerous pattern: {pattern.pattern}")

        imported = _extract_imports(code)
        for pkg in imported:
            if pkg.startswith("@"):
                approved = any(
                    pkg.startswith(ap) or ap.startswith(pkg)
                    for ap in PRE_APPROVED_PACKAGES
                )
                if not approved:
                    issues.append(f"Unapproved package: {pkg}")
            elif pkg not in PRE_APPROVED_PACKAGES:
                issues.append(f"Unapproved package: {pkg}")

        return {"safe": len(issues) == 0, "issues": issues}

    def list_available_packages(self) -> List[str]:
        return PRE_APPROVED_PACKAGES.copy()
