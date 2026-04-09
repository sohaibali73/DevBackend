"""
Python Sandbox
==============
Executes Python code in a restricted environment with:

  Fix 2a — stdout capture via patched print() (thread-safe, no sys.stdout monkey-patch)
  Fix 2b — matplotlib figure capture: plt.show() → PNG → base64 DisplayArtifact
  Fix 2c — AST-based safety validation (replaces bypassable keyword blocklist)
  Fix 2d — Persistent session namespaces via SQLite (variables survive restarts)
  Fix 2e — display() / HTML() / SVG() helpers injected into exec globals (Jupyter-like)
"""

import ast
import base64
import io as _io
import json
import math
import re as re_mod
import statistics
import csv
import time
import asyncio
import traceback
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage, DisplayArtifact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AST-based safety: forbidden imports and calls
# ---------------------------------------------------------------------------
_FORBIDDEN_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pty", "tty",
    "fcntl", "termios", "ctypes", "signal", "resource", "mmap",
    "multiprocessing", "socket", "pathlib", "glob", "importlib",
    "builtins", "__builtin__", "code", "codeop", "codecs",
    "inspect", "gc", "weakref", "dis",
})

_FORBIDDEN_CALLS = frozenset({
    "eval", "compile", "open", "exec",
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
        "print": print,          # overridden per-execution (Fix 2a)
        "True": True, "False": False, "None": None,
        "isinstance": isinstance, "type": type, "hasattr": hasattr,
        "getattr": getattr, "callable": callable,
        "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError,
        "AttributeError": AttributeError, "RuntimeError": RuntimeError,
        "StopIteration": StopIteration, "Exception": Exception,
        "NotImplementedError": NotImplementedError,
        "OverflowError": OverflowError, "ZeroDivisionError": ZeroDivisionError,
        "__import__": __import__,   # needed for `import pandas` etc in exec
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

# Inject optional scientific/data libraries
def _try_inject(name: str, module_expr: str, alias: Optional[str] = None):
    try:
        import importlib
        mod = importlib.import_module(module_expr)
        _SANDBOX_GLOBALS[name] = mod
        if alias:
            _SANDBOX_GLOBALS[alias] = mod
    except ImportError:
        pass

_try_inject("np", "numpy", "numpy")
_try_inject("pd", "pandas", "pandas")
_try_inject("scipy", "scipy")
_try_inject("sns", "seaborn", "seaborn")
_try_inject("sympy", "sympy")
_try_inject("yf", "yfinance", "yfinance")
_try_inject("openpyxl", "openpyxl")
_try_inject("aiofiles", "aiofiles")
_try_inject("bs4", "bs4")
_try_inject("lxml", "lxml")
_try_inject("httpx", "httpx")
_try_inject("aiohttp", "aiohttp")
_try_inject("requests", "requests")
_try_inject("pydantic", "pydantic")
_try_inject("rich", "rich")
_try_inject("anthropic", "anthropic")
_try_inject("tabulate", "tabulate")
_try_inject("tqdm", "tqdm")
_try_inject("pyarrow", "pyarrow")
_try_inject("edgartools", "edgartools")
_try_inject("rank_bm25", "rank_bm25")
_try_inject("rapidfuzz", "rapidfuzz")
_try_inject("textdistance", "textdistance")
_try_inject("unidecode", "unidecode")
_try_inject("nest_asyncio", "nest_asyncio")
_try_inject("jinja2", "jinja2")
_try_inject("markupsafe", "markupsafe")
_try_inject("tenacity", "tenacity")
_try_inject("stamina", "stamina")
_try_inject("humanize", "humanize")
_try_inject("orjson", "orjson")
_try_inject("tldextract", "tldextract")
_try_inject("plotly", "plotly")
_try_inject("networkx", "networkx")
_try_inject("sklearn", "sklearn")

# Inject BeautifulSoup convenience alias
try:
    from bs4 import BeautifulSoup
    _SANDBOX_GLOBALS["BeautifulSoup"] = BeautifulSoup
except ImportError:
    pass

# Inject Decimal / Fraction
try:
    from decimal import Decimal
    _SANDBOX_GLOBALS["Decimal"] = Decimal
except ImportError:
    pass
try:
    from fractions import Fraction
    _SANDBOX_GLOBALS["Fraction"] = Fraction
except ImportError:
    pass

# Inject Presentation (python-pptx)
try:
    from pptx import Presentation
    _SANDBOX_GLOBALS["Presentation"] = Presentation
    _SANDBOX_GLOBALS["pptx"] = __import__("pptx")
except ImportError:
    pass

# Matplotlib — inject with Agg backend, patched per-execution (Fix 2b)
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt_module
    _SANDBOX_GLOBALS["matplotlib"] = matplotlib
    _SANDBOX_GLOBALS["plt"] = _plt_module   # overridden per-execution
    _HAS_MATPLOTLIB = True
except ImportError:
    _plt_module = None
    _HAS_MATPLOTLIB = False

# Pre-approved Python packages list (for package manager validation)
PRE_APPROVED_PACKAGES = [
    "numpy", "numpy-typing-compat", "pandas", "scipy", "scipy-stubs",
    "matplotlib", "seaborn", "sympy", "scikit-learn", "pyarrow",
    "yfinance", "edgartools", "sec-edgar-api",
    "pillow", "python-pptx", "openpyxl", "et-xmlfile", "lxml",
    "requests", "requests-file", "httpx", "httpxthrottlecache", "httpcore",
    "aiohttp", "aiofiles", "curl-cffi", "tls-client", "h11", "certifi",
    "urllib3", "charset-normalizer", "idna", "sniffio", "anyio",
    "beautifulsoup4", "soupsieve", "tldextract", "fake-useragent",
    "rank-bm25", "RapidFuzz", "textdistance", "Unidecode",
    "nest-asyncio", "greenlet",
    "python-dateutil", "tzdata",
    "pydantic", "pydantic-core", "annotated-types", "typing-extensions",
    "typing-inspection", "optype",
    "anthropic", "jiter",
    "rich", "Pygments", "tabulate", "tqdm", "colorama", "humanize", "Logbook",
    "jinja2", "markupsafe", "packaging", "six", "distro", "orjson",
    "filelock", "truststore",
    "pyrate-limiter", "stamina", "tenacity",
    "playwright", "pyee", "docstring-parser",
    "contourpy", "cycler", "fonttools", "kiwisolver", "pyparsing",
    "cffi", "pycparser", "markdown-it-py", "mdurl", "setuptools", "pip",
    "plotly", "networkx", "flask", "fastapi", "sqlalchemy",
]


# ---------------------------------------------------------------------------
# Fix 2b — Matplotlib capture wrapper
# ---------------------------------------------------------------------------
class _PltCapture:
    """
    Drop-in replacement for matplotlib.pyplot that captures show() calls
    as PNG base64 DisplayArtifacts instead of rendering to screen.
    """

    def __init__(self, plt_mod, captured: List[DisplayArtifact]):
        self._plt = plt_mod
        self._captured = captured

    def show(self, **kwargs):
        """Capture current figure as PNG artifact instead of displaying."""
        if self._plt is None:
            return
        buf = _io.BytesIO()
        try:
            self._plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
            buf.seek(0)
            png_b64 = base64.b64encode(buf.read()).decode("utf-8")
            self._captured.append(DisplayArtifact(
                type="image/png",
                data=png_b64,
                encoding="base64",
                display_type="image",
                metadata={"format": "png", "source": "matplotlib"},
            ))
        finally:
            self._plt.close("all")

    def __getattr__(self, name: str):
        return getattr(self._plt, name)


# ---------------------------------------------------------------------------
# Fix 2e — Jupyter-like display helpers
# ---------------------------------------------------------------------------
def _make_display_helpers(artifacts: List[DisplayArtifact]):
    """Build display() and HTML() functions bound to this execution's artifact list."""

    def display(obj, **kwargs):
        """Render obj as a rich artifact (HTML, PNG, SVG, JSON, or text)."""
        if hasattr(obj, "_repr_html_"):
            artifacts.append(DisplayArtifact(
                type="text/html",
                data=obj._repr_html_(),
                encoding="utf-8",
                display_type="html",
            ))
        elif hasattr(obj, "_repr_svg_"):
            artifacts.append(DisplayArtifact(
                type="image/svg+xml",
                data=obj._repr_svg_(),
                encoding="utf-8",
                display_type="image",
            ))
        elif hasattr(obj, "_repr_png_"):
            raw = obj._repr_png_()
            artifacts.append(DisplayArtifact(
                type="image/png",
                data=base64.b64encode(raw).decode("utf-8"),
                encoding="base64",
                display_type="image",
            ))
        elif hasattr(obj, "_repr_json_"):
            artifacts.append(DisplayArtifact(
                type="application/json",
                data=json.dumps(obj._repr_json_()),
                encoding="utf-8",
                display_type="json",
            ))
        else:
            artifacts.append(DisplayArtifact(
                type="text/plain",
                data=str(obj),
                encoding="utf-8",
                display_type="text",
            ))

    class _HTML:
        """Wrap an HTML string so display() renders it as HTML."""
        def __init__(self, html: str):
            self.html = html
        def _repr_html_(self):
            return self.html

    class _SVG:
        """Wrap an SVG string so display() renders it as an image."""
        def __init__(self, svg: str):
            self.svg = svg
        def _repr_svg_(self):
            return self.svg

    class _JSON:
        """Wrap a dict/list so display() renders it as JSON."""
        def __init__(self, data):
            self._data = data
        def _repr_json_(self):
            return self._data

    def HTML(html_str: str):
        return _HTML(html_str)

    def SVG(svg_str: str):
        return _SVG(svg_str)

    def JSON(data):
        return _JSON(data)

    return display, HTML, SVG, JSON


# ---------------------------------------------------------------------------
# Namespace serialization helpers (Fix 2d)
# ---------------------------------------------------------------------------
def _serialize_namespace(local_vars: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only JSON-serializable values from local_vars for DB persistence.
    Skips private names, functions, modules, and non-serializable objects.
    """
    result = {}
    for k, v in local_vars.items():
        if k.startswith("_"):
            continue
        if callable(v) or hasattr(v, "__module__"):
            # Skip functions, classes, modules
            try:
                if hasattr(v, "__module__") and not isinstance(v, (int, float, str, bool, type(None), list, dict, tuple, set)):
                    continue
            except Exception:
                continue
        try:
            # Only keep JSON-serializable primitives and containers
            json.dumps(v)
            result[k] = v
        except (TypeError, ValueError, OverflowError):
            # Try string fallback for simple scalars
            if isinstance(v, (int, float, str, bool, type(None))):
                result[k] = v
            # Skip everything else (numpy arrays, DataFrames, etc.)
    return result


def _inject_persisted_namespace(
    persisted: Dict[str, Any],
    local_vars: Dict[str, Any],
) -> None:
    """
    Load persisted namespace values into local_vars.
    JSON scalars map directly to Python equivalents.
    """
    for k, v in persisted.items():
        if not k.startswith("_"):
            local_vars[k] = v


# ---------------------------------------------------------------------------
# PythonSandbox
# ---------------------------------------------------------------------------
class PythonSandbox(BaseSandbox):
    """
    Python execution sandbox using exec() with restricted globals.

    On init, loads any user-installed packages from the DB into _SANDBOX_GLOBALS
    so they're available immediately after a server restart.
    """

    def __init__(self):
        # Load previously installed packages from DB on startup (best-effort)
        asyncio.ensure_future(self._load_installed_packages())

    async def _load_installed_packages(self):
        """Inject user-installed packages from DB into _SANDBOX_GLOBALS on startup."""
        try:
            from core.sandbox.db import get_installed_packages, _SANDBOX_HOME
            from core.sandbox.package_manager import PERSISTENT_PYTHON_VENV

            # Add venv site-packages to sys.path if it exists
            import sys
            venv_site = PERSISTENT_PYTHON_VENV / "lib"
            if venv_site.exists():
                for sp in venv_site.rglob("site-packages"):
                    if str(sp) not in sys.path:
                        sys.path.insert(0, str(sp))

            packages = await get_installed_packages("python")
            for pkg in packages:
                if pkg.get("status") == "installed":
                    name = pkg["name"]
                    try:
                        import importlib
                        mod = importlib.import_module(name)
                        _SANDBOX_GLOBALS[name] = mod
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Could not load installed packages on init: %s", e)

    @property
    def language(self) -> SandboxLanguage:
        return SandboxLanguage.PYTHON

    async def execute(
        self,
        code: str,
        timeout: int = 30,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> SandboxResult:
        """Execute Python code in the sandboxed environment."""
        if session_id is None:
            session_id = str(uuid.uuid4())

        execution_id = str(uuid.uuid4())
        start_time = time.time()

        # --- Safety check (AST-based) ---
        validation = self.validate(code)
        if not validation["safe"]:
            return SandboxResult(
                success=False,
                error=f"Unsafe code detected: {'; '.join(validation['issues'])}",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
                execution_id=execution_id,
                session_id=session_id,
            )

        # --- Load persisted session namespace (Fix 2d) ---
        persisted_namespace: Dict[str, Any] = {}
        try:
            from core.sandbox.db import get_or_create_session
            session_data = await get_or_create_session(session_id, "python")
            persisted_namespace = session_data.get("namespace", {})
        except Exception as e:
            logger.debug("Session load skipped: %s", e)

        # --- Execute in thread (non-blocking) ---
        try:
            result, new_namespace = await asyncio.wait_for(
                asyncio.to_thread(
                    self._execute_sync, code, context, persisted_namespace
                ),
                timeout=timeout,
            )
            result.execution_time_ms = round((time.time() - start_time) * 1000, 2)
            result.execution_id = execution_id
            result.session_id = session_id

            # --- Persist namespace + artifacts to DB ---
            if result.success:
                await self._persist_result(
                    session_id, execution_id, code, result, new_namespace
                )

            return result

        except asyncio.TimeoutError:
            return SandboxResult(
                success=False,
                error=f"Execution timed out after {timeout} seconds",
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
                execution_id=execution_id,
                session_id=session_id,
            )
        except Exception as e:
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=round((time.time() - start_time) * 1000, 2),
                language="python",
                execution_id=execution_id,
                session_id=session_id,
            )

    async def _persist_result(
        self,
        session_id: str,
        execution_id: str,
        code: str,
        result: SandboxResult,
        new_namespace: Dict[str, Any],
    ) -> None:
        """Persist execution + namespace + artifacts to DB. Best-effort."""
        try:
            from core.sandbox.db import (
                save_session_namespace,
                save_execution,
                save_artifact,
            )
            await save_session_namespace(session_id, new_namespace)
            await save_execution(
                execution_id=execution_id,
                session_id=session_id,
                code=code,
                language="python",
                output=result.output or "",
                error=result.error or "",
                success=result.success,
                exec_time_ms=result.execution_time_ms,
            )
            for artifact in result.artifacts:
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
            logger.debug("Persistence skipped: %s", e)

    def _execute_sync(
        self,
        code: str,
        context: Optional[Dict] = None,
        persisted_namespace: Optional[Dict] = None,
    ) -> Tuple[SandboxResult, Dict[str, Any]]:
        """
        Synchronous execution (runs in a thread via asyncio.to_thread).
        Returns (SandboxResult, serializable_namespace_for_db).
        """
        # ---- Set up per-execution captures ----
        captured_output = _io.StringIO()
        captured_artifacts: List[DisplayArtifact] = []

        # Fix 2a — thread-safe stdout capture via patched print
        def _sandbox_print(*args, sep=" ", end="\n", file=None, flush=False):
            print(*args, sep=sep, end=end, file=captured_output, flush=flush)

        # Fix 2b — matplotlib capture
        plt_wrapper = None
        if _HAS_MATPLOTLIB and _plt_module is not None:
            plt_wrapper = _PltCapture(_plt_module, captured_artifacts)

        # Fix 2e — Jupyter-style helpers
        display, HTML, SVG, JSON = _make_display_helpers(captured_artifacts)

        # Build per-execution globals (shallow copy of shared globals)
        exec_globals = dict(_SANDBOX_GLOBALS)
        exec_globals["__builtins__"] = dict(_SANDBOX_GLOBALS["__builtins__"])
        exec_globals["__builtins__"]["print"] = _sandbox_print
        if plt_wrapper is not None:
            exec_globals["plt"] = plt_wrapper
        exec_globals["display"] = display
        exec_globals["HTML"] = HTML
        exec_globals["SVG"] = SVG
        exec_globals["JSON"] = JSON

        # ---- Set up local vars ----
        local_vars: Dict[str, Any] = {}

        # Fix 2d — inject persisted namespace
        if persisted_namespace:
            _inject_persisted_namespace(persisted_namespace, local_vars)

        # Inject caller context on top
        if context:
            local_vars.update(context)

        # ---- Execute ----
        try:
            exec(code, exec_globals, local_vars)  # noqa: S102

            # Capture any remaining matplotlib figures (code that didn't call show())
            if plt_wrapper is not None and _plt_module is not None:
                try:
                    figs = _plt_module.get_fignums()
                    if figs:
                        plt_wrapper.show()
                except Exception:
                    pass

            stdout_str = captured_output.getvalue()
            # Primary output: stdout first, then result/output variable, then fallback
            if stdout_str.strip():
                output_text = stdout_str
            else:
                raw_out = local_vars.get("result", local_vars.get("output", None))
                output_text = str(raw_out) if raw_out is not None else "Code executed successfully"

            # Determine display_type
            display_type = "image" if any(
                a.display_type == "image" for a in captured_artifacts
            ) else ("html" if any(
                a.display_type in ("html", "react") for a in captured_artifacts
            ) else "text")

            # Serialize variables for API response (string preview)
            variables = {
                k: str(v)[:200]
                for k, v in local_vars.items()
                if not k.startswith("_")
            }

            # Serialize namespace for DB (only JSON-safe values)
            new_namespace = _serialize_namespace(local_vars)

            return SandboxResult(
                success=True,
                output=output_text,
                variables=variables,
                artifacts=captured_artifacts,
                display_type=display_type,
                language="python",
            ), new_namespace

        except Exception as e:
            tb = traceback.format_exc()
            return SandboxResult(
                success=False,
                error=str(e),
                output=tb[:1000],
                language="python",
            ), {}

    # -------------------------------------------------------------------------
    # Fix 2c — AST-based validation
    # -------------------------------------------------------------------------
    def validate(self, code: str) -> Dict[str, Any]:
        """
        AST-walk based validation. Replaces the bypassable keyword string search.

        Blocks:
          - import / from-import of forbidden modules (os, sys, subprocess, etc.)
          - calls to forbidden builtins (eval, compile, open, exec)
          - __import__('dangerous_module') patterns
        """
        issues = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"safe": False, "issues": [f"Syntax error: {e}"]}

        for node in ast.walk(tree):
            # --- Import statements ---
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in _FORBIDDEN_IMPORTS:
                        issues.append(f"Forbidden import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    if top in _FORBIDDEN_IMPORTS:
                        issues.append(f"Forbidden import: from {node.module}")

            # --- Function calls ---
            elif isinstance(node, ast.Call):
                func = node.func
                func_name: Optional[str] = None

                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    # e.g. builtins.eval
                    func_name = func.attr

                if func_name in _FORBIDDEN_CALLS:
                    issues.append(f"Forbidden call: {func_name}()")

                # Catch __import__('os') / __import__('subprocess') patterns
                if func_name == "__import__" and node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant):
                        mod = str(first_arg.value).split(".")[0]
                        if mod in _FORBIDDEN_IMPORTS:
                            issues.append(
                                f"Forbidden import via __import__: {mod}"
                            )

        return {
            "safe": len(issues) == 0,
            "issues": issues,
        }

    def list_available_packages(self) -> list:
        """Return list of pre-approved Python packages."""
        return PRE_APPROVED_PACKAGES.copy()
