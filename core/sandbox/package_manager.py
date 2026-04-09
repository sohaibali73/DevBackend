"""
Sandbox Package Manager
=======================
Handles package installation, caching, and management for sandbox environments.

Fix 4 — _do_install() actually runs pip / npm (replaces the no-op PENDING stub).

Key behaviours:
  - Python packages install into a persistent venv at ~/.sandbox/python_venv/
    The venv path is added to sys.path at runtime so new packages are
    importable immediately without a server restart.
  - JavaScript packages install into ~/.sandbox/node_packages/ via npm prefix.
  - All install results are persisted to the sandbox SQLite DB so they survive
    server restarts (get_installed_packages() is called by PythonSandbox on init).
  - Path is configurable via SANDBOX_DATA_DIR env var.
"""

import asyncio
import logging
import os
import re
import sys
import time
import importlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent install paths (configurable via SANDBOX_DATA_DIR)
# ---------------------------------------------------------------------------
_SANDBOX_HOME = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_SANDBOX_HOME.mkdir(parents=True, exist_ok=True)

PERSISTENT_PYTHON_VENV = _SANDBOX_HOME / "python_venv"
PERSISTENT_NODE_DIR = _SANDBOX_HOME / "node_packages"
PERSISTENT_NODE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class PackageStatus(Enum):
    PREINSTALLED = "preinstalled"
    CACHED = "cached"
    INSTALLED = "installed"
    FAILED = "failed"
    PENDING = "pending"
    BLOCKED = "blocked"


@dataclass
class PackageInfo:
    name: str
    version: Optional[str] = None
    status: PackageStatus = PackageStatus.INSTALLED
    language: str = "python"
    install_time_ms: float = 0
    size_kb: float = 0
    install_path: Optional[str] = None


@dataclass
class InstallationResult:
    success: bool
    message: str
    packages: List[PackageInfo]
    logs: List[str]


# ---------------------------------------------------------------------------
# SandboxPackageManager
# ---------------------------------------------------------------------------

class SandboxPackageManager:
    """
    Manages package installation for sandbox environments.

    Features:
      - Preinstalled library tracking
      - Real on-demand package installation (Fix 4)
      - Malicious package blocking
      - SQLite DB persistence (packages survive restart)
      - Installation rate limiting per user
    """

    # Preinstalled libraries available by default in the sandbox
    PREINSTALLED_PACKAGES = {
        "python": [
            "aiofiles", "annotated-types", "anyio", "beautifulsoup4",
            "certifi", "cffi", "charset-normalizer", "colorama",
            "contourpy", "curl_cffi", "cycler", "distro",
            "docstring_parser", "edgartools", "et_xmlfile", "fake-useragent",
            "filelock", "fonttools", "frozendict", "greenlet",
            "h11", "httpcore", "httpx", "httpxthrottlecache",
            "humanize", "idna", "Jinja2", "jiter",
            "kiwisolver", "Logbook", "lxml", "markdown-it-py",
            "MarkupSafe", "matplotlib", "mdurl", "multitasking",
            "nest-asyncio", "numpy", "numpy-typing-compat", "openpyxl",
            "optype", "orjson", "packaging", "pandas",
            "peewee", "pillow", "pip", "platformdirs",
            "playwright", "protobuf", "pyarrow", "pycparser",
            "pydantic", "pydantic_core", "pyee", "Pygments",
            "pyparsing", "pyrate-limiter", "python-dateutil", "python-docx",
            "python-pptx", "pytz", "rank-bm25", "RapidFuzz",
            "requests", "requests-file", "rich", "scipy",
            "scipy-stubs", "sec-edgar-api", "setuptools", "six",
            "sniffio", "soupsieve", "stamina", "tabulate",
            "tenacity", "textdistance", "tldextract", "tls-client",
            "tqdm", "truststore", "typing_extensions", "typing-inspection",
            "tzdata", "Unidecode", "urllib3", "websockets", "yfinance",
            "scikit-learn", "seaborn", "plotly", "networkx",
            "sympy", "fastapi", "flask", "sqlalchemy", "alembic",
            "aiohttp", "pytest", "click",
        ],
        "javascript": [
            "react", "react-dom", "@mui/material", "axios", "lodash",
            "moment", "date-fns", "chart.js", "d3", "uuid", "yup",
            "formik", "react-query", "redux", "zustand", "tailwindcss",
            "typescript", "react-router-dom", "framer-motion",
            "react-hook-form", "pptxgenjs", "@types/node",
            "classnames", "clsx", "lucide-react",
        ],
    }

    # Known malicious / typosquat patterns to block
    MALICIOUS_PACKAGES = {
        "python": {
            "evilpackage", "malicious", "backdoor", "exploit", "trojan",
        },
        "javascript": {
            "evil-package", "malicious-package", "backdoor",
        },
    }

    MAX_USER_PACKAGES = 15
    MAX_INSTALL_SIZE_MB = 500
    INSTALL_TIMEOUT_SEC = 180

    def __init__(self):
        self._cache: Dict[Tuple[str, str], PackageInfo] = {}
        self._user_installs: Dict[str, List[PackageInfo]] = {}

    # -------------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------------

    def get_preinstalled_packages(self, language: str) -> List[str]:
        return self.PREINSTALLED_PACKAGES.get(language.lower(), [])

    def is_preinstalled(self, language: str, package_name: str) -> bool:
        pkgs = self.get_preinstalled_packages(language)
        return package_name.lower() in [p.lower() for p in pkgs]

    def is_package_allowed(
        self, language: str, package_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Return (allowed, reason_if_blocked)."""
        pkg_lower = package_name.lower()

        if pkg_lower in self.MALICIOUS_PACKAGES.get(language, set()):
            return False, "Package is in malicious package blocklist"

        suspicious = [
            r"^[0-9a-f]{32,}$",
            r"backdoor|exploit|trojan|virus|malware",
            r"password|steal|keylogger",
        ]
        for pattern in suspicious:
            if re.search(pattern, pkg_lower, re.IGNORECASE):
                return False, "Package name contains suspicious patterns"

        if "==" in package_name and len(package_name.split("==")) > 2:
            return False, "Invalid package specification format"

        return True, None

    # -------------------------------------------------------------------------
    # Installation entry-point
    # -------------------------------------------------------------------------

    async def install_packages(
        self,
        language: str,
        packages: List[str],
        user_id: Optional[str] = None,
    ) -> InstallationResult:
        """
        Install packages into the sandbox environment.

        For Python: installs into PERSISTENT_PYTHON_VENV and adds to sys.path + _SANDBOX_GLOBALS.
        For JavaScript: installs into PERSISTENT_NODE_DIR via npm --prefix.
        All results are persisted to the sandbox SQLite DB.
        """
        results: List[PackageInfo] = []
        logs: List[str] = []
        all_success = True

        for spec in packages:
            name, version = self._parse_spec(spec)

            # Security gate
            allowed, reason = self.is_package_allowed(language, name)
            if not allowed:
                logs.append(f"❌ '{name}' blocked: {reason}")
                results.append(PackageInfo(
                    name=name, version=version,
                    status=PackageStatus.BLOCKED, language=language
                ))
                all_success = False
                continue

            # Already in sandbox globals / preinstalled
            if self.is_preinstalled(language, name):
                logs.append(f"✅ '{name}' is preinstalled")
                results.append(PackageInfo(
                    name=name, version=version,
                    status=PackageStatus.PREINSTALLED, language=language
                ))
                continue

            # Check in-memory cache
            cache_key = (language.lower(), name.lower())
            if cache_key in self._cache:
                logs.append(f"✅ '{name}' found in cache")
                results.append(self._cache[cache_key])
                continue

            # Check DB for previously installed package (survives restart)
            db_pkg = await self._check_db(language, name)
            if db_pkg and db_pkg.get("status") == "installed":
                logs.append(f"✅ '{name}' already installed (from DB)")
                info = PackageInfo(
                    name=name, version=db_pkg.get("version"),
                    status=PackageStatus.INSTALLED, language=language,
                    install_path=db_pkg.get("install_path"),
                )
                self._cache[cache_key] = info
                results.append(info)
                continue

            # User package limit
            if user_id:
                user_pkgs = self._user_installs.get(user_id, [])
                if len(user_pkgs) >= self.MAX_USER_PACKAGES:
                    logs.append(
                        f"❌ User package limit reached ({self.MAX_USER_PACKAGES})"
                    )
                    results.append(PackageInfo(
                        name=name, version=version,
                        status=PackageStatus.FAILED, language=language
                    ))
                    all_success = False
                    continue

            # ---- Actual installation (Fix 4) ----
            logs.append(f"📦 Installing '{spec}'…")
            info = await self._do_install(language, name, version)
            results.append(info)

            if info.status == PackageStatus.INSTALLED:
                logs.append(
                    f"✅ '{name}' installed in {info.install_time_ms:.0f}ms"
                )
                self._cache[cache_key] = info
                if user_id:
                    self._user_installs.setdefault(user_id, []).append(info)
            else:
                logs.append(f"❌ Failed to install '{name}'")
                all_success = False

        return InstallationResult(
            success=all_success,
            message=f"Processed {len(packages)} package(s)",
            packages=results,
            logs=logs,
        )

    # -------------------------------------------------------------------------
    # Fix 4 — Real install implementation
    # -------------------------------------------------------------------------

    async def _do_install(
        self,
        language: str,
        name: str,
        version: Optional[str],
    ) -> PackageInfo:
        """
        Actually run pip / npm to install the package into the persistent location.
        Persists the result to DB regardless of success/failure.
        """
        spec = f"{name}=={version}" if version else name
        start = time.time()

        if language == "python":
            info = await self._install_python(name, version, spec, start)
        elif language in ("javascript", "react"):
            info = await self._install_node(name, version, spec, start)
        else:
            info = PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language=language,
            )

        # Persist to DB
        await self._persist_to_db(language, info)
        return info

    async def _install_python(
        self,
        name: str,
        version: Optional[str],
        spec: str,
        start: float,
    ) -> PackageInfo:
        """Install into a persistent venv, then inject into _SANDBOX_GLOBALS."""
        # Ensure venv exists
        venv_pip = await self._ensure_python_venv()
        if venv_pip is None:
            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language="python",
                install_path=str(PERSISTENT_PYTHON_VENV),
            )

        cmd = [str(venv_pip), "install", spec, "--quiet", "--no-deps-check"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.INSTALL_TIMEOUT_SEC
            )
            elapsed = round((time.time() - start) * 1000, 2)
            success = proc.returncode == 0

            if success:
                # Add venv site-packages to sys.path if not already there
                await self._inject_python_venv_path()
                # Try importing and injecting into sandbox globals immediately
                await asyncio.to_thread(self._inject_into_sandbox_globals, name)

            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.INSTALLED if success else PackageStatus.FAILED,
                language="python",
                install_time_ms=elapsed,
                install_path=str(PERSISTENT_PYTHON_VENV),
            )
        except asyncio.TimeoutError:
            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language="python",
                install_path=str(PERSISTENT_PYTHON_VENV),
            )
        except Exception as e:
            logger.warning("Python install error for %s: %s", name, e)
            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language="python",
                install_path=str(PERSISTENT_PYTHON_VENV),
            )

    async def _install_node(
        self,
        name: str,
        version: Optional[str],
        spec: str,
        start: float,
    ) -> PackageInfo:
        """Install into the persistent node_packages directory via npm prefix."""
        cmd = [
            "npm", "install", spec,
            "--prefix", str(PERSISTENT_NODE_DIR),
            "--no-audit", "--no-fund", "--quiet",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self.INSTALL_TIMEOUT_SEC
            )
            elapsed = round((time.time() - start) * 1000, 2)
            success = proc.returncode == 0

            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.INSTALLED if success else PackageStatus.FAILED,
                language="javascript",
                install_time_ms=elapsed,
                install_path=str(PERSISTENT_NODE_DIR),
            )
        except asyncio.TimeoutError:
            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language="javascript",
                install_path=str(PERSISTENT_NODE_DIR),
            )
        except FileNotFoundError:
            logger.warning("npm not found — cannot install %s", name)
            return PackageInfo(
                name=name, version=version,
                status=PackageStatus.FAILED, language="javascript",
            )

    # -------------------------------------------------------------------------
    # Venv helpers
    # -------------------------------------------------------------------------

    async def _ensure_python_venv(self) -> Optional[Path]:
        """Create the persistent venv if it doesn't exist. Return pip path."""
        pip_unix = PERSISTENT_PYTHON_VENV / "bin" / "pip"
        pip_win = PERSISTENT_PYTHON_VENV / "Scripts" / "pip.exe"

        if pip_unix.exists():
            return pip_unix
        if pip_win.exists():
            return pip_win

        # Create the venv
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "venv", str(PERSISTENT_PYTHON_VENV),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)
        except Exception as e:
            logger.warning("Could not create venv: %s", e)
            return None

        if pip_unix.exists():
            return pip_unix
        if pip_win.exists():
            return pip_win
        return None

    async def _inject_python_venv_path(self) -> None:
        """Add venv site-packages to sys.path so imports work immediately."""
        venv_lib = PERSISTENT_PYTHON_VENV / "lib"
        if venv_lib.exists():
            for sp in venv_lib.rglob("site-packages"):
                if str(sp) not in sys.path:
                    sys.path.insert(0, str(sp))
        # Windows path
        venv_lib_win = PERSISTENT_PYTHON_VENV / "Lib" / "site-packages"
        if venv_lib_win.exists() and str(venv_lib_win) not in sys.path:
            sys.path.insert(0, str(venv_lib_win))

    def _inject_into_sandbox_globals(self, module_name: str) -> None:
        """Import a newly installed module and inject into _SANDBOX_GLOBALS."""
        try:
            from core.sandbox.python_sandbox import _SANDBOX_GLOBALS
            mod = importlib.import_module(module_name)
            _SANDBOX_GLOBALS[module_name] = mod
            logger.info("Injected '%s' into sandbox globals", module_name)
        except Exception as e:
            logger.debug("Could not inject %s into sandbox globals: %s", module_name, e)

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    async def _check_db(self, language: str, name: str) -> Optional[Dict]:
        """Check if a package is recorded as installed in the DB."""
        try:
            from core.sandbox.db import get_package
            return await get_package(language, name)
        except Exception:
            return None

    async def _persist_to_db(self, language: str, info: PackageInfo) -> None:
        """Write/update the package record in the DB."""
        try:
            from core.sandbox.db import upsert_package
            await upsert_package(
                language=language,
                name=info.name,
                version=info.version,
                status=info.status.value,
                install_path=info.install_path,
            )
        except Exception as e:
            logger.debug("Could not persist package to DB: %s", e)

    # -------------------------------------------------------------------------
    # Listing helpers
    # -------------------------------------------------------------------------

    def list_all_packages(
        self,
        language: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, List[PackageInfo]]:
        """List all available packages: preinstalled + cached + user-installed."""
        preinstalled = [
            PackageInfo(name=pkg, status=PackageStatus.PREINSTALLED, language=language)
            for pkg in self.get_preinstalled_packages(language)
        ]
        cached = [
            pkg for (lang, _), pkg in self._cache.items()
            if lang == language.lower()
        ]
        user_pkgs = (
            self._user_installs.get(user_id, []) if user_id else []
        )
        return {
            "preinstalled": preinstalled,
            "cached": cached,
            "user_installed": user_pkgs,
        }

    def clear_cache(self) -> None:
        """Clear the in-memory package cache."""
        self._cache.clear()
        logger.info("Package cache cleared")

    # -------------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_spec(spec: str) -> Tuple[str, Optional[str]]:
        """Parse 'name==version' or 'name' into (name, version)."""
        if "==" in spec:
            name, version = spec.split("==", 1)
            return name.strip(), version.strip()
        return spec.strip(), None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_package_manager: Optional[SandboxPackageManager] = None


def get_package_manager() -> SandboxPackageManager:
    """Get or create the global package manager instance."""
    global _package_manager
    if _package_manager is None:
        _package_manager = SandboxPackageManager()
    return _package_manager


__all__ = [
    "SandboxPackageManager",
    "PackageInfo",
    "PackageStatus",
    "InstallationResult",
    "get_package_manager",
    "PERSISTENT_PYTHON_VENV",
    "PERSISTENT_NODE_DIR",
]
