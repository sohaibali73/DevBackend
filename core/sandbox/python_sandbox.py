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

# Inject additional scientific/data libraries if available
try:
    import scipy
    _SANDBOX_GLOBALS["scipy"] = scipy
except ImportError:
    pass

try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    _SANDBOX_GLOBALS["matplotlib"] = matplotlib
    _SANDBOX_GLOBALS["plt"] = plt
except ImportError:
    pass

try:
    import seaborn as sns
    _SANDBOX_GLOBALS["sns"] = sns
    _SANDBOX_GLOBALS["seaborn"] = sns
except ImportError:
    pass

try:
    import sympy
    _SANDBOX_GLOBALS["sympy"] = sympy
except ImportError:
    pass

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

# Inject additional commonly used packages
try:
    import yfinance
    _SANDBOX_GLOBALS["yfinance"] = yfinance
    _SANDBOX_GLOBALS["yf"] = yfinance
except ImportError:
    pass

try:
    from pptx import Presentation
    _SANDBOX_GLOBALS["pptx"] = __import__("pptx")
    _SANDBOX_GLOBALS["Presentation"] = Presentation
except ImportError:
    pass

try:
    import openpyxl
    _SANDBOX_GLOBALS["openpyxl"] = openpyxl
except ImportError:
    pass

try:
    import aiofiles
    _SANDBOX_GLOBALS["aiofiles"] = aiofiles
except ImportError:
    pass

try:
    import bs4
    _SANDBOX_GLOBALS["bs4"] = bs4
    from bs4 import BeautifulSoup
    _SANDBOX_GLOBALS["BeautifulSoup"] = BeautifulSoup
except ImportError:
    pass

try:
    import lxml
    _SANDBOX_GLOBALS["lxml"] = lxml
except ImportError:
    pass

try:
    import httpx
    _SANDBOX_GLOBALS["httpx"] = httpx
except ImportError:
    pass

try:
    import aiohttp
    _SANDBOX_GLOBALS["aiohttp"] = aiohttp
except ImportError:
    pass

try:
    import requests
    _SANDBOX_GLOBALS["requests"] = requests
except ImportError:
    pass

try:
    import pydantic
    _SANDBOX_GLOBALS["pydantic"] = pydantic
except ImportError:
    pass

try:
    import rich
    _SANDBOX_GLOBALS["rich"] = rich
except ImportError:
    pass

try:
    import anthropic
    _SANDBOX_GLOBALS["anthropic"] = anthropic
except ImportError:
    pass

try:
    import tabulate
    _SANDBOX_GLOBALS["tabulate"] = tabulate
except ImportError:
    pass

try:
    import tqdm
    _SANDBOX_GLOBALS["tqdm"] = tqdm
except ImportError:
    pass

try:
    import pyarrow
    _SANDBOX_GLOBALS["pyarrow"] = pyarrow
except ImportError:
    pass

try:
    import edgartools
    _SANDBOX_GLOBALS["edgartools"] = edgartools
except ImportError:
    pass

try:
    import rank_bm25
    _SANDBOX_GLOBALS["rank_bm25"] = rank_bm25
except ImportError:
    pass

try:
    import rapidfuzz
    _SANDBOX_GLOBALS["rapidfuzz"] = rapidfuzz
except ImportError:
    pass

try:
    import textdistance
    _SANDBOX_GLOBALS["textdistance"] = textdistance
except ImportError:
    pass

try:
    import unidecode
    _SANDBOX_GLOBALS["unidecode"] = unidecode
    _SANDBOX_GLOBALS["Unidecode"] = unidecode
except ImportError:
    pass

try:
    import nest_asyncio
    _SANDBOX_GLOBALS["nest_asyncio"] = nest_asyncio
except ImportError:
    pass

try:
    import jinja2
    _SANDBOX_GLOBALS["jinja2"] = jinja2
except ImportError:
    pass

try:
    import markupsafe
    _SANDBOX_GLOBALS["markupsafe"] = markupsafe
except ImportError:
    pass

try:
    import tenacity
    _SANDBOX_GLOBALS["tenacity"] = tenacity
except ImportError:
    pass

try:
    import stamina
    _SANDBOX_GLOBALS["stamina"] = stamina
except ImportError:
    pass

try:
    import humanize
    _SANDBOX_GLOBALS["humanize"] = humanize
except ImportError:
    pass

try:
    import orjson
    _SANDBOX_GLOBALS["orjson"] = orjson
except ImportError:
    pass

try:
    import tldextract
    _SANDBOX_GLOBALS["tldextract"] = tldextract
except ImportError:
    pass

# Pre-approved Python packages
PRE_APPROVED_PACKAGES = [
    # Data Science & Analysis
    "numpy",
    "numpy-typing-compat",
    "pandas",
    "scipy",
    "scipy-stubs",
    "matplotlib",
    "seaborn",
    "sympy",
    "scikit-learn",
    "pyarrow",
    
    # Financial & SEC
    "yfinance",
    "edgartools",
    "sec-edgar-api",
    
    # Image & Document Processing
    "pillow",
    "python-pptx",
    "openpyxl",
    "et-xmlfile",
    "lxml",
    
    # HTTP & Web
    "requests",
    "requests-file",
    "httpx",
    "httpxthrottlecache",
    "httpcore",
    "aiohttp",
    "aiofiles",
    "curl-cffi",
    "tls-client",
    "h11",
    "certifi",
    "urllib3",
    "charset-normalizer",
    "idna",
    "sniffio",
    "anyio",
    
    # Web Scraping
    "beautifulsoup4",
    "soupsieve",
    "tldextract",
    "fake-useragent",
    
    # Search & NLP
    "rank-bm25",
    "RapidFuzz",
    "textdistance",
    "Unidecode",
    
    # Async & Concurrency
    "nest-asyncio",
    "greenlet",
    
    # Date & Time
    "python-dateutil",
    "tzdata",
    
    # Type Checking & Validation
    "pydantic",
    "pydantic-core",
    "annotated-types",
    "typing-extensions",
    "typing-inspection",
    "optype",
    
    # AI & ML
    "anthropic",
    "jiter",
    
    # CLI & Output
    "rich",
    "Pygments",
    "tabulate",
    "tqdm",
    "colorama",
    "humanize",
    "Logbook",
    
    # Utilities
    "jinja2",
    "markupsafe",
    "packaging",
    "six",
    "distro",
    "orjson",
    "filelock",
    "truststore",
    
    # Rate Limiting & Retry
    "pyrate-limiter",
    "stamina",
    "tenacity",
    
    # Browser Automation
    "playwright",
    "pyee",
    "docstring-parser",
    
    # Math & Plotting
    "contourpy",
    "cycler",
    "fonttools",
    "kiwisolver",
    "pyparsing",
    
    # Other
    "cffi",
    "pycparser",
    "markdown-it-py",
    "mdurl",
    "setuptools",
    "pip",
]


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

    def list_available_packages(self) -> list:
        """Return list of pre-approved Python packages."""
        return PRE_APPROVED_PACKAGES.copy()
