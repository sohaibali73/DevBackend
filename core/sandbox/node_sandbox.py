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
#
# IMPORTANT: React-dependent packages must use ?external=react,react-dom
# so esm.sh does NOT bundle its own React copy. All `import 'react'` calls
# from those packages are resolved by the browser via THIS importmap,
# guaranteeing a single React instance (no React error #31).
# ---------------------------------------------------------------------------
_ESM_IMPORT_MAP: Dict[str, str] = {
    # ── Core React (pinned to 18, single instance) ────────────────────────
    "react":                       "https://esm.sh/react@18",
    "react-dom":                   "https://esm.sh/react-dom@18?external=react",
    "react-dom/client":            "https://esm.sh/react-dom@18/client?external=react,react-dom",
    "react-dom/server":            "https://esm.sh/react-dom@18/server?external=react,react-dom",
    # Babel @preset-react (automatic runtime) emits these sub-path imports;
    # they MUST be in the importmap or the browser throws a bare-specifier error.
    "react/jsx-runtime":           "https://esm.sh/react@18/jsx-runtime",
    "react/jsx-dev-runtime":       "https://esm.sh/react@18/jsx-dev-runtime",

    # ── React component libraries (external=react,react-dom) ─────────────
    "lucide-react":                "https://esm.sh/lucide-react?external=react",
    "@radix-ui/react-icons":       "https://esm.sh/@radix-ui/react-icons?external=react",
    "react-icons":                 "https://esm.sh/react-icons?external=react",
    "framer-motion":               "https://esm.sh/framer-motion?external=react,react-dom",
    "react-hook-form":             "https://esm.sh/react-hook-form?external=react",
    "react-router-dom":            "https://esm.sh/react-router-dom?external=react,react-dom",
    "@headlessui/react":           "https://esm.sh/@headlessui/react?external=react,react-dom",
    "@heroicons/react":            "https://esm.sh/@heroicons/react?external=react",
    "recharts":                    "https://esm.sh/recharts?external=react,react-dom",

    # ── Pure utility packages (no React dep, no external needed) ─────────
    "clsx":                        "https://esm.sh/clsx",
    "tailwind-merge":              "https://esm.sh/tailwind-merge",
    "class-variance-authority":    "https://esm.sh/class-variance-authority",
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
# Helpers for React code pre-processing
# ---------------------------------------------------------------------------

def _strip_react_imports(code: str) -> str:
    """
    Remove React / ReactDOM import statements from user code.

    The wrapper already provides:
      React, useState, useEffect, useRef, useCallback, useMemo,
      useReducer, useContext  (from 'react')
      createRoot               (from 'react-dom/client')

    Keeping duplicate imports causes Babel to throw
    "Identifier 'React' has already been declared".
    """
    patterns = [
        # import React, { useState, ... } from 'react'
        r"import\s+React\s*,?\s*(?:\{[^}]*\})?\s*from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
        # import { useState, useEffect, ... } from 'react'
        r"import\s*\{[^}]*\}\s*from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
        # import * as React from 'react'
        r"import\s*\*\s*as\s+\w+\s+from\s+['\"]react['\"][ \t]*;?[ \t]*\n?",
        # import ReactDOM from 'react-dom'
        r"import\s+\w+\s+from\s+['\"]react-dom['\"][ \t]*;?[ \t]*\n?",
        # import { createRoot } from 'react-dom/client'  OR  react-dom/server
        r"import\s*\{[^}]*\}\s*from\s+['\"]react-dom(?:/client|/server)?['\"][ \t]*;?[ \t]*\n?",
    ]
    for p in patterns:
        code = re.sub(p, "", code, flags=re.MULTILINE)
    return code


def _extract_default_export(code: str):
    """
    Strip the 'export default' prefix from function / class declarations
    so the symbol stays in scope for the mount helper.

    Returns (modified_code, component_name | None).
    """
    # export default function ComponentName(...)
    m = re.search(r"\bexport\s+default\s+(function)\s+(\w+)", code)
    if m:
        new_code = code[: m.start()] + m.group(1) + " " + m.group(2) + code[m.end() :]
        return new_code, m.group(2)

    # export default class ComponentName
    m = re.search(r"\bexport\s+default\s+(class)\s+(\w+)", code)
    if m:
        new_code = code[: m.start()] + m.group(1) + " " + m.group(2) + code[m.end() :]
        return new_code, m.group(2)

    # export default ComponentName; (standalone reference on its own line)
    m = re.search(r"^\s*export\s+default\s+(\w+)\s*;?\s*$", code, re.MULTILINE)
    if m:
        name = m.group(1)
        new_code = (code[: m.start()] + code[m.end() :]).strip()
        return new_code, name

    return code, None


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
      - Strips duplicate React/ReactDOM imports from user code
      - Strips 'export default' so component stays in scope for mount

    No Node.js execution is needed — the frontend simply iframes this HTML.
    """
    import_map_json = json.dumps({"imports": _ESM_IMPORT_MAP}, indent=2)

    # Pre-process user code ------------------------------------------------
    # 1. Remove any React / ReactDOM imports (wrapper provides them)
    clean_code = _strip_react_imports(jsx_code)
    # 2. Remove 'export default' and discover the component name
    clean_code, component_name = _extract_default_export(clean_code)

    # Build mount call -------------------------------------------------------
    if component_name:
        # We know the exact name — use it directly (most reliable)
        mount_call = f"root.render(React.createElement({component_name}));"
    else:
        # Fallback: try common names
        mount_call = """
      var _found = false;
      var _names = ['App','Component','Default','Dashboard','Page','View','Widget'];
      for (var _i = 0; _i < _names.length; _i++) {
        try {
          var _C = eval(_names[_i]);
          if (typeof _C === 'function') { root.render(React.createElement(_C)); _found = true; break; }
        } catch(e) {}
      }
      if (!_found) {
        document.getElementById('root').innerHTML =
          '<div id=\\"sandbox-error\\">No component found. Export a function named App, Component, or Default.</div>';
      }"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sandbox</title>
  <script type="importmap">
{import_map_json}
  </script>
  <script src="https://unpkg.com/@babel/standalone@7.24.7/babel.min.js"></script>
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
    import React, {{ useState, useEffect, useRef, useCallback, useMemo, useReducer, useContext, createContext, forwardRef, memo }} from 'react';
    import {{ createRoot }} from 'react-dom/client';

    // ---- User code ----
    {clean_code}
    // ---- End user code ----

    (function mountApp() {{
      const root = createRoot(document.getElementById('root'));
      {mount_call}
    }})();
  </script>
  <script>
    window.addEventListener('error', function(e) {{
      var el = document.getElementById('sandbox-error');
      if (!el) {{ el = document.createElement('div'); el.id = 'sandbox-error'; document.body.appendChild(el); }}
      el.textContent = 'Runtime error: ' + (e.message || String(e));
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
