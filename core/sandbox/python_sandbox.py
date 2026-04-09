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
import random
import re as re_mod
import statistics
import csv
import time
import asyncio
import traceback
import logging
import uuid
import os as _os_real
import sys as _sys_real
import types as _types_mod
import tempfile as _tempfile_mod
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from core.sandbox.base import BaseSandbox, SandboxResult, SandboxLanguage, DisplayArtifact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AST-based safety: forbidden imports and calls
# ---------------------------------------------------------------------------
_FORBIDDEN_IMPORTS = frozenset({
    # Process execution / spawning
    "subprocess", "pty", "tty",
    # Low-level C/system access
    "fcntl", "termios", "ctypes", "signal", "resource", "mmap",
    # Process management
    "multiprocessing",
    # Raw network
    "socket",
    # Import bypass
    "importlib",
    # Python internals (allow inspect, codecs, weakref — they're harmless)
    "builtins", "__builtin__", "code", "codeop",
    # Memory / bytecode
    "gc", "dis",
})

_FORBIDDEN_CALLS = frozenset({
    # "open" REMOVED — sandboxed version provided per-execution
    "eval", "compile", "exec",
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
        "isinstance": isinstance, "issubclass": issubclass,
        "type": type, "hasattr": hasattr,
        "getattr": getattr, "setattr": setattr, "delattr": delattr,
        "callable": callable, "repr": repr, "hash": hash, "id": id,
        "iter": iter, "next": next,
        "dir": dir, "vars": vars,
        "chr": chr, "ord": ord, "bin": bin, "hex": hex, "oct": oct,
        "object": object, "super": super,
        "property": property, "staticmethod": staticmethod, "classmethod": classmethod,
        "ValueError": ValueError, "TypeError": TypeError,
        "KeyError": KeyError, "IndexError": IndexError,
        "AttributeError": AttributeError, "RuntimeError": RuntimeError,
        "NameError": NameError, "StopIteration": StopIteration,
        "Exception": Exception, "BaseException": BaseException,
        "NotImplementedError": NotImplementedError,
        "OverflowError": OverflowError, "ZeroDivisionError": ZeroDivisionError,
        "ImportError": ImportError, "ModuleNotFoundError": ModuleNotFoundError,
        "AssertionError": AssertionError, "LookupError": LookupError,
        "ArithmeticError": ArithmeticError,
        "__import__": __import__,   # needed for `import pandas` etc in exec
    },
    "random": random,
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
# tabulate — inject the function directly (not the module) so tabulate(data, headers=...) works
try:
    from tabulate import tabulate as _tabulate_fn
    _SANDBOX_GLOBALS["tabulate"] = _tabulate_fn      # tabulate(rows, headers=...)
    _SANDBOX_GLOBALS["tabulate_formats"] = [          # convenience: list of valid tablefmt strings
        "plain", "simple", "github", "grid", "fancy_grid", "pipe",
        "orgtbl", "rst", "mediawiki", "html", "latex", "tsv",
    ]
except ImportError:
    pass
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

# faker — inject Faker class directly so Faker() works without import
try:
    from faker import Faker as _Faker
    _SANDBOX_GLOBALS["Faker"] = _Faker
    _SANDBOX_GLOBALS["faker"] = __import__("faker")  # also expose the module
except ImportError:
    pass

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
    "faker",
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
        """Render obj as a rich artifact (plotly, HTML, PNG, SVG, JSON, or text)."""
        # Plotly figures (have to_html + data + layout)
        if hasattr(obj, "to_html") and hasattr(obj, "data") and hasattr(obj, "layout"):
            try:
                html_content = obj.to_html(include_plotlyjs="cdn", full_html=False)
                artifacts.append(DisplayArtifact(
                    type="text/html",
                    data=html_content,
                    encoding="utf-8",
                    display_type="plotly",
                    metadata={"format": "plotly-html"},
                ))
                return
            except Exception:
                pass
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
# Fix: File MIME types for downloadable artifacts
# ---------------------------------------------------------------------------
_MAX_FILE_ARTIFACT_BYTES = 50 * 1_000_000   # 50 MB

_FILE_MIME_TYPES: Dict[str, str] = {
    ".csv":     "text/csv",
    ".tsv":     "text/tab-separated-values",
    ".txt":     "text/plain",
    ".log":     "text/plain",
    ".ini":     "text/plain",
    ".md":      "text/markdown",
    ".html":    "text/html",
    ".htm":     "text/html",
    ".py":      "text/x-python",
    ".js":      "application/javascript",
    ".json":    "application/json",
    ".xml":     "application/xml",
    ".yaml":    "application/x-yaml",
    ".yml":     "application/x-yaml",
    ".toml":    "application/toml",
    ".svg":     "image/svg+xml",
    ".png":     "image/png",
    ".jpg":     "image/jpeg",
    ".jpeg":    "image/jpeg",
    ".gif":     "image/gif",
    ".bmp":     "image/bmp",
    ".pdf":     "application/pdf",
    ".xlsx":    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":     "application/vnd.ms-excel",
    ".pptx":    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx":    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip":     "application/zip",
    ".gz":      "application/gzip",
    ".tar":     "application/x-tar",
    ".parquet": "application/octet-stream",
    ".pkl":     "application/octet-stream",
    ".pickle":  "application/octet-stream",
    ".feather": "application/octet-stream",
    ".mp3":     "audio/mpeg",
    ".wav":     "audio/wav",
    ".mp4":     "video/mp4",
}

# ---------------------------------------------------------------------------
# Fix: Auto-install __import__ + safe os/sys/shutil proxies
# ---------------------------------------------------------------------------

def _make_sandbox_imports(sandbox_dir: Path, approved: List[str]):
    """
    Build a custom __import__ for sandbox exec() calls.

    • os / sys / shutil → returns safe namespace proxies (no fork/system/exit etc.)
    • pathlib / glob / inspect / codecs / weakref → real module (safe)
    • Missing approved packages → auto-installs via pip, then imports
    • Everything else → delegates to the real __import__
    """
    import subprocess as _sub
    import importlib as _imp

    # Normalise approved package names for loose matching
    _approved: set = set()
    for p in approved:
        _approved.add(p.lower())
        _approved.add(p.lower().replace("-", "_"))
        _approved.add(p.lower().replace("_", "-"))

    # Helper: resolve a relative path into sandbox_dir
    def _rp(p) -> str:
        s = str(p)
        return s if _os_real.path.isabs(s) else _os_real.path.join(str(sandbox_dir), s)

    # ---- Safe os proxy ----
    _safe_os = _types_mod.SimpleNamespace(
        path=_os_real.path,
        sep=_os_real.sep,
        linesep=_os_real.linesep,
        curdir=_os_real.curdir,
        pardir=_os_real.pardir,
        extsep=_os_real.extsep,
        altsep=_os_real.altsep,
        devnull=_os_real.devnull,
        name=_os_real.name,
        environ={},                              # empty — don't leak secrets
        getenv=lambda key, default=None: None,
        getcwd=lambda: str(sandbox_dir),
        urandom=_os_real.urandom,
        listdir=lambda p=".": _os_real.listdir(_rp(p)),
        makedirs=lambda p, mode=0o777, exist_ok=True: _os_real.makedirs(
            _rp(p), mode=mode, exist_ok=exist_ok
        ),
        mkdir=lambda p, mode=0o777: _os_real.mkdir(_rp(p), mode),
        remove=lambda p: _os_real.remove(_rp(p)),
        unlink=lambda p: _os_real.remove(_rp(p)),
        rename=lambda src, dst: _os_real.rename(_rp(src), _rp(dst)),
        stat=lambda p: _os_real.stat(_rp(p)),
        walk=lambda p=".", **kw: _os_real.walk(_rp(p), **kw),
        SEEK_SET=0, SEEK_CUR=1, SEEK_END=2,
    )

    # ---- Safe sys proxy ----
    _safe_sys = _types_mod.SimpleNamespace(
        version=_sys_real.version,
        version_info=_sys_real.version_info,
        platform=_sys_real.platform,
        maxsize=_sys_real.maxsize,
        maxunicode=_sys_real.maxunicode,
        byteorder=_sys_real.byteorder,
        argv=[],
        path=[str(sandbox_dir)],
        float_info=_sys_real.float_info,
        int_info=_sys_real.int_info,
        builtin_module_names=(),
        exc_info=_sys_real.exc_info,
        getrecursionlimit=_sys_real.getrecursionlimit,
        setrecursionlimit=lambda n: None,   # no-op
        stdin=None,
        stderr=_sys_real.stderr,
        stdout=_sys_real.stdout,
        modules={},
        executable=_sys_real.executable,
    )

    # ---- Safe shutil proxy (operations sandboxed to sandbox_dir) ----
    try:
        import shutil as _real_shutil
        _safe_shutil = _types_mod.SimpleNamespace(
            copy=lambda src, dst: _real_shutil.copy(_rp(src), _rp(dst)),
            copy2=lambda src, dst: _real_shutil.copy2(_rp(src), _rp(dst)),
            move=lambda src, dst: _real_shutil.move(_rp(src), _rp(dst)),
            rmtree=lambda p, **kw: _real_shutil.rmtree(_rp(p), **kw),
            copytree=lambda src, dst, **kw: _real_shutil.copytree(_rp(src), _rp(dst), **kw),
            make_archive=lambda base_name, fmt, root_dir=None, base_dir=None, **kw: (
                _real_shutil.make_archive(
                    _rp(base_name), fmt,
                    root_dir=root_dir or str(sandbox_dir),
                    base_dir=base_dir, **kw,
                )
            ),
            unpack_archive=lambda fn, extract_dir=None, **kw: _real_shutil.unpack_archive(
                _rp(fn), extract_dir=extract_dir or str(sandbox_dir), **kw
            ),
            which=_real_shutil.which,
            get_terminal_size=_real_shutil.get_terminal_size,
            disk_usage=lambda p=".": _real_shutil.disk_usage(_rp(p)),
        )
    except ImportError:
        _safe_shutil = _types_mod.SimpleNamespace()

    # Modules returned as safe proxies
    _PROXY_MAP = {
        "os":     _safe_os,
        "sys":    _safe_sys,
        "shutil": _safe_shutil,
    }

    def _custom_import(name, globals=None, locals=None, fromlist=(), level=0):
        top = name.split(".")[0].lower()

        # Return safe proxy
        if top in _PROXY_MAP:
            # Special case: from os.path import X — return the real os.path (safe)
            if name == "os.path" and fromlist:
                return _os_real.path
            return _PROXY_MAP[top]

        # Normal import
        try:
            return __import__(name, globals, locals, fromlist, level)
        except ImportError as orig_err:
            pkg = top.replace("-", "_")
            if pkg in _approved or pkg.replace("_", "-") in _approved:
                logger.info("Auto-installing missing package: '%s'", pkg)
                try:
                    proc = _sub.run(
                        [_sys_real.executable, "-m", "pip", "install", pkg, "-q"],
                        timeout=120,
                        capture_output=True,
                    )
                    if proc.returncode != 0:
                        _sub.run(
                            [_sys_real.executable, "-m", "pip", "install",
                             pkg.replace("_", "-"), "-q"],
                            timeout=120,
                            capture_output=True,
                        )
                    _imp.invalidate_caches()
                    return __import__(name, globals, locals, fromlist, level)
                except Exception as install_err:
                    logger.warning("Auto-install of '%s' failed: %s", pkg, install_err)
            raise orig_err

    return _custom_import


def _make_sandboxed_open(sandbox_dir: Path):
    """
    Return an open() replacement.

    Write / append / exclusive-create modes → path is always inside sandbox_dir.
    Read modes → prefer sandbox_dir for relative paths, fall through otherwise
                 (libraries need to read their own data files from site-packages).
    """
    import builtins as _builtins
    _real_open = _builtins.open

    def _sandboxed_open(
        file, mode="r", buffering=-1, encoding=None,
        errors=None, newline=None, closefd=True, opener=None,
    ):
        kw: Dict[str, Any] = {}
        if encoding is not None:
            kw["encoding"] = encoding
        if errors is not None:
            kw["errors"] = errors
        if newline is not None:
            kw["newline"] = newline

        if isinstance(file, (str, bytes)):
            file_str = file.decode() if isinstance(file, bytes) else file
            # Write / append / exclusive → force into sandbox_dir
            if any(c in mode for c in "wax"):
                if not _os_real.path.isabs(file_str):
                    file_str = _os_real.path.join(str(sandbox_dir), file_str)
                parent = _os_real.path.dirname(file_str)
                if parent:
                    _os_real.makedirs(parent, exist_ok=True)
                return _real_open(file_str, mode, buffering, **kw)
            # Read → prefer sandbox_dir for relative paths
            if not _os_real.path.isabs(file_str):
                sandbox_path = _os_real.path.join(str(sandbox_dir), file_str)
                if _os_real.path.exists(sandbox_path):
                    return _real_open(sandbox_path, mode, buffering, **kw)

        return _real_open(file, mode, buffering, **kw)

    return _sandboxed_open


def _collect_file_artifacts(
    sandbox_dir: Path,
    injected_mtimes: Optional[Dict[str, float]] = None,
) -> List[DisplayArtifact]:
    """
    Walk sandbox_dir after execution; convert files the user's code wrote into
    downloadable FileArtifacts (stored as base64 in the DB, served via API).

    injected_mtimes: mapping of absolute path → mtime at injection time.
    Files that are in injected_mtimes AND whose mtime has not changed are
    skipped (they are unmodified input files, not outputs).
    """
    _skip: Dict[str, float] = injected_mtimes or {}
    artifacts: List[DisplayArtifact] = []
    try:
        for fp in sorted(Path(str(sandbox_dir)).rglob("*")):
            if not fp.is_file():
                continue
            # Skip injected input files that were NOT modified by user code
            fp_str = str(fp)
            if fp_str in _skip:
                try:
                    current_mtime = fp.stat().st_mtime
                    if abs(current_mtime - _skip[fp_str]) < 0.5:
                        logger.debug("Skipping unmodified injected file: %s", fp.name)
                        continue
                except OSError:
                    pass  # file deleted — nothing to skip
            size = fp.stat().st_size
            if size == 0 or size > _MAX_FILE_ARTIFACT_BYTES:
                continue
            ext = fp.suffix.lower()
            mime = _FILE_MIME_TYPES.get(ext, "application/octet-stream")
            filename = fp.name
            try:
                is_text = mime.startswith("text/") or mime in (
                    "application/json", "application/xml",
                    "application/x-yaml", "application/toml",
                    "text/x-python", "application/javascript",
                )
                if is_text:
                    data = fp.read_text(encoding="utf-8", errors="replace")
                    encoding = "utf-8"
                else:
                    data = base64.b64encode(fp.read_bytes()).decode("ascii")
                    encoding = "base64"
            except Exception as e:
                logger.debug("Cannot read sandbox file %s: %s", filename, e)
                continue

            artifacts.append(DisplayArtifact(
                type=mime,
                data=data,
                encoding=encoding,
                display_type="file",
                metadata={
                    "filename": filename,
                    "size_bytes": size,
                    "extension": ext,
                    "downloadable": True,
                },
            ))
    except Exception as e:
        logger.debug("File artifact collection error: %s", e)
    return artifacts


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
                    self._execute_sync, code, context, persisted_namespace, execution_id
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
        execution_id: Optional[str] = None,
    ) -> Tuple[SandboxResult, Dict[str, Any]]:
        """
        Synchronous execution (runs in a thread via asyncio.to_thread).
        Returns (SandboxResult, serializable_namespace_for_db).

        • Creates a per-execution temp directory for file I/O.
        • Auto-installs missing approved packages via pip.
        • Captures plotly fig.show() + matplotlib plt.show() as artifacts.
        • Converts files written by the code into downloadable FileArtifacts.
        """
        import shutil as _shutil

        # ---- Per-execution sandbox directory for file I/O ----
        exec_id = execution_id or str(uuid.uuid4())
        sandbox_dir = Path(_tempfile_mod.mkdtemp(prefix=f"sbx_{exec_id[:8]}_"))

        # ---- Captures ----
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

        # Auto-install __import__ + sandboxed open()
        custom_import = _make_sandbox_imports(sandbox_dir, PRE_APPROVED_PACKAGES)
        sandboxed_open = _make_sandboxed_open(sandbox_dir)

        # Build per-execution globals (shallow copy of shared globals)
        exec_globals = dict(_SANDBOX_GLOBALS)
        exec_globals["__builtins__"] = dict(_SANDBOX_GLOBALS["__builtins__"])
        exec_globals["__builtins__"]["print"] = _sandbox_print
        exec_globals["__builtins__"]["__import__"] = custom_import
        exec_globals["__builtins__"]["open"] = sandboxed_open
        if plt_wrapper is not None:
            exec_globals["plt"] = plt_wrapper
        exec_globals["display"] = display
        exec_globals["HTML"] = HTML
        exec_globals["SVG"] = SVG
        exec_globals["JSON"] = JSON
        exec_globals["__sandbox_dir__"] = str(sandbox_dir)  # let code discover its workspace

        # ---- Fix 6a: Inject uploaded files from _sandbox_files context key ----
        # sandbox_files: Dict[str, bytes]  (filename → raw bytes)
        # Written to sandbox_dir so the sandboxed open() can access them.
        # _files  = {"report.xlsx": "/tmp/sbx_xxx/report.xlsx"}   — all types
        # _images = {"chart.png":   "<base64>"}                   — images only
        #
        # Track injection mtimes so _collect_file_artifacts can skip input files
        # that were NOT modified by the code (avoids returning noisy unmodified inputs).
        _injected_files: Dict[str, str] = {}
        _injected_images: Dict[str, str] = {}
        _injected_mtimes: Dict[str, float] = {}  # path → mtime right after write
        if context and "_sandbox_files" in context:
            for _fname, _fdata in (context.get("_sandbox_files") or {}).items():
                try:
                    _dest = sandbox_dir / _fname
                    _dest.write_bytes(_fdata)
                    _injected_mtimes[str(_dest)] = _dest.stat().st_mtime
                    _injected_files[_fname] = str(_dest)
                    _ext_lower = _fname.rsplit(".", 1)[-1].lower() if "." in _fname else ""
                    if _ext_lower in ("png", "jpg", "jpeg", "gif", "webp", "bmp"):
                        _injected_images[_fname] = base64.b64encode(_fdata).decode("utf-8")
                    logger.info("Injected sandbox file: %s → %s", _fname, _dest)
                except Exception as _inj_err:
                    logger.warning("Could not inject sandbox file %s: %s", _fname, _inj_err)

        # ---- Local vars ----
        local_vars: Dict[str, Any] = {}
        if persisted_namespace:
            _inject_persisted_namespace(persisted_namespace, local_vars)
        if context:
            # Inject user context variables, skip internal _sandbox_* transport keys
            for _k, _v in context.items():
                if not _k.startswith("_sandbox_"):
                    local_vars[_k] = _v
        # Always expose _files and _images so code can reference them unconditionally
        local_vars["_files"] = _injected_files
        local_vars["_images"] = _injected_images

        # ---- Patch plotly.io.show to capture figures as HTML artifacts ----
        _plotly_show_orig = None
        try:
            import plotly.io as _pio
            _plotly_show_orig = _pio.show

            def _plotly_show_patch(fig, *args, **kwargs):
                try:
                    html = _pio.to_html(fig, include_plotlyjs="cdn", full_html=False)
                    captured_artifacts.append(DisplayArtifact(
                        type="text/html", data=html, encoding="utf-8",
                        display_type="plotly",
                        metadata={"format": "plotly-html"},
                    ))
                except Exception:
                    pass

            _pio.show = _plotly_show_patch
        except ImportError:
            pass

        # ---- Execute ----
        try:
            exec(code, exec_globals, local_vars)  # noqa: S102

            # Capture any remaining matplotlib figures
            if plt_wrapper is not None and _plt_module is not None:
                try:
                    if _plt_module.get_fignums():
                        plt_wrapper.show()
                except Exception:
                    pass

            # Auto-capture any plotly Figure objects in local_vars not yet captured
            try:
                import plotly.graph_objects as _pgo
                if not any(a.display_type == "plotly" for a in captured_artifacts):
                    for _v in list(local_vars.values()):
                        if isinstance(_v, _pgo.Figure):
                            try:
                                import plotly.io as _pio2
                                html = _pio2.to_html(_v, include_plotlyjs="cdn", full_html=False)
                                captured_artifacts.append(DisplayArtifact(
                                    type="text/html", data=html, encoding="utf-8",
                                    display_type="plotly",
                                    metadata={"format": "plotly-html"},
                                ))
                            except Exception:
                                pass
            except ImportError:
                pass

            # Collect files written to sandbox_dir as downloadable artifacts.
            # Skip injected input files that were NOT modified by the code.
            file_artifacts = _collect_file_artifacts(sandbox_dir, _injected_mtimes)
            captured_artifacts.extend(file_artifacts)

            stdout_str = captured_output.getvalue()
            if stdout_str.strip():
                output_text = stdout_str
            else:
                raw_out = local_vars.get("result", local_vars.get("output", None))
                output_text = (
                    str(raw_out) if raw_out is not None else "Code executed successfully"
                )

            display_type = (
                "image"  if any(a.display_type == "image"  for a in captured_artifacts) else
                "plotly" if any(a.display_type == "plotly" for a in captured_artifacts) else
                "html"   if any(a.display_type in ("html", "react") for a in captured_artifacts) else
                "file"   if any(a.display_type == "file"   for a in captured_artifacts) else
                "text"
            )

            variables = {
                k: str(v)[:200]
                for k, v in local_vars.items()
                if not k.startswith("_")
            }
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

        finally:
            # Restore plotly.io.show
            if _plotly_show_orig is not None:
                try:
                    import plotly.io as _pio_restore
                    _pio_restore.show = _plotly_show_orig
                except Exception:
                    pass
            # Clean up temp directory (artifacts already captured in memory)
            try:
                _shutil.rmtree(str(sandbox_dir), ignore_errors=True)
            except Exception:
                pass

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
