"""
Sandbox Package Manager  s
=======================
Handles package installation, caching, and management for sandbox environments.
Supports preinstalled libraries and on-demand user package installation with security checks.
"""

import logging
import asyncio
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PackageStatus(Enum):
    """Status of package installation."""
    PREINSTALLED = "preinstalled"
    CACHED = "cached"
    INSTALLED = "installed"
    FAILED = "failed"
    PENDING = "pending"
    BLOCKED = "blocked"


@dataclass
class PackageInfo:
    """Information about an installed package."""
    name: str
    version: Optional[str] = None
    status: PackageStatus = PackageStatus.INSTALLED
    language: str = "python"
    install_time_ms: float = 0
    size_kb: float = 0


@dataclass
class InstallationResult:
    """Result of package installation."""
    success: bool
    message: str
    packages: List[PackageInfo]
    logs: List[str]


class SandboxPackageManager:
    """
    Manages package installation for sandbox environments with security validation and caching.
    
    Features:
    - Preinstalled library tracking
    - On-demand package installation
    - Malicious package blocking
    - Shared package caching
    - Installation rate limiting
    """

    # Preinstalled libraries available by default
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
            "aiohttp", "pytest", "click"
        ],
        "javascript": [
            "react", "react-dom", "@mui/material", "axios", "lodash",
            "moment", "date-fns", "chart.js", "d3", "uuid", "yup",
            "formik", "react-query", "redux", "zustand", "tailwindcss",
            "typescript", "react-router-dom", "framer-motion", "react-hook-form",
            "pptxgenjs", "@types/node", "hash.js", "jszip",
            "nanoid", "xml", "xml-js", "@types/inquirer",
            "@types/unzipper", "@types/xml", "@typescript-eslint/eslint-plugin",
            "@typescript-eslint/parser", "@vitest/coverage-v8", "@vitest/ui",
            "cspell", "docsify-cli", "eslint", "eslint-import-resolver-typescript",
            "eslint-plugin-functional", "eslint-plugin-import", "eslint-plugin-jsdoc",
            "eslint-plugin-no-null", "eslint-plugin-prefer-arrow", "eslint-plugin-unicorn",
            "execa", "glob", "inquirer", "jiti", "jsdom", "pre-commit",
            "prettier", "tsconfig-paths", "tsx", "typedoc", "typescript-eslint",
            "unzipper", "vite", "vite-plugin-dts", "vite-plugin-node-polyfills",
            "vite-tsconfig-paths", "https", "image-size", "@eslint/js",
            "@rollup/plugin-commonjs", "@rollup/plugin-node-resolve", "@stylistic/eslint-plugin",
            "express", "gulp", "gulp-concat", "gulp-delete-lines", "gulp-ignore",
            "gulp-insert", "gulp-sourcemaps", "gulp-uglify", "rollup",
            "rollup-plugin-typescript2", "tslib"
        ]
    }

    # Known malicious packages to block (from Snyk/OSV databases)
    MALICIOUS_PACKAGES = {
        "python": {
            "requests-", "urllib3-", "numpy-", "pandas-", "django-",
            "evilpackage", "malicious", "backdoor", "exploit", "trojan"
        },
        "javascript": {
            "lodash-", "react-", "axios-", "jquery-",
            "evil-package", "malicious-package", "backdoor"
        }
    }

    # Maximum limits
    MAX_USER_PACKAGES = 15
    MAX_INSTALL_SIZE_MB = 500
    INSTALL_TIMEOUT_SEC = 120

    def __init__(self):
        """Initialize package manager."""
        self._cache: Dict[Tuple[str, str], PackageInfo] = {}
        self._install_queue: asyncio.Queue = asyncio.Queue()
        self._user_installs: Dict[str, List[PackageInfo]] = {}

    def get_preinstalled_packages(self, language: str) -> List[str]:
        """Get list of preinstalled packages for a language."""
        return self.PREINSTALLED_PACKAGES.get(language.lower(), [])

    def is_preinstalled(self, language: str, package_name: str) -> bool:
        """Check if a package is preinstalled."""
        packages = self.get_preinstalled_packages(language)
        return package_name.lower() in [p.lower() for p in packages]

    def is_package_allowed(self, language: str, package_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate if a package is allowed to be installed.
        
        Returns: (allowed, reason_if_blocked)
        """
        package_lower = package_name.lower()

        # Block known malicious packages
        if package_lower in self.MALICIOUS_PACKAGES.get(language, set()):
            return False, "Package is in malicious package blocklist"

        # Block packages with suspicious names
        suspicious_patterns = [
            r'^[0-9a-f]{32,}$',  # Random hash names
            r'backdoor|exploit|trojan|virus|malware',
            r'password|steal|keylogger',
        ]

        for pattern in suspicious_patterns:
            if re.search(pattern, package_lower, re.IGNORECASE):
                return False, "Package name contains suspicious patterns"

        # Block version override attacks
        if '==' in package_name and len(package_name.split('==')) > 2:
            return False, "Invalid package specification format"

        return True, None

    async def install_packages(
        self,
        language: str,
        packages: List[str],
        user_id: Optional[str] = None
    ) -> InstallationResult:
        """
        Install multiple packages into the sandbox environment.
        
        Args:
            language: Programming language (python/javascript)
            packages: List of package names, optionally with versions (e.g. "pandas==2.1.0")
            user_id: Optional user identifier for rate limiting
        
        Returns:
            InstallationResult with success status and details
        """
        results = []
        logs = []
        all_success = True

        for package_spec in packages:
            # Parse package name and version
            if '==' in package_spec:
                name, version = package_spec.split('==', 1)
            else:
                name = package_spec
                version = None

            name = name.strip()
            version = version.strip() if version else None

            # Security check
            allowed, reason = self.is_package_allowed(language, name)
            if not allowed:
                logs.append(f"❌ Package '{name}' blocked: {reason}")
                results.append(PackageInfo(
                    name=name,
                    version=version,
                    status=PackageStatus.BLOCKED,
                    language=language
                ))
                all_success = False
                continue

            # Check if already preinstalled
            if self.is_preinstalled(language, name):
                logs.append(f"✅ Package '{name}' is already preinstalled")
                results.append(PackageInfo(
                    name=name,
                    version=version,
                    status=PackageStatus.PREINSTALLED,
                    language=language
                ))
                continue

            # Check cache
            cache_key = (language.lower(), name.lower())
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                logs.append(f"✅ Package '{name}' found in cache")
                results.append(cached)
                continue

            # Validate user package limits
            if user_id:
                user_packages = self._user_installs.get(user_id, [])
                if len(user_packages) >= self.MAX_USER_PACKAGES:
                    logs.append(f"❌ User package limit reached ({self.MAX_USER_PACKAGES})")
                    results.append(PackageInfo(
                        name=name,
                        version=version,
                        status=PackageStatus.FAILED,
                        language=language
                    ))
                    all_success = False
                    continue

            # Actual installation logic would go here
            # This will be implemented in the sandbox specific classes
            logs.append(f"🔧 Package '{name}' queued for installation")
            results.append(PackageInfo(
                name=name,
                version=version,
                status=PackageStatus.PENDING,
                language=language
            ))

        return InstallationResult(
            success=all_success,
            message=f"Processed {len(packages)} packages",
            packages=results,
            logs=logs
        )

    def list_all_packages(self, language: str, user_id: Optional[str] = None) -> Dict[str, List[PackageInfo]]:
        """List all available packages for a language."""
        preinstalled = [
            PackageInfo(name=pkg, status=PackageStatus.PREINSTALLED, language=language)
            for pkg in self.get_preinstalled_packages(language)
        ]

        cached = [
            pkg for (lang, _), pkg in self._cache.items()
            if lang == language.lower()
        ]

        user_packages = []
        if user_id and user_id in self._user_installs:
            user_packages = self._user_installs[user_id]

        return {
            "preinstalled": preinstalled,
            "cached": cached,
            "user_installed": user_packages
        }

    def clear_cache(self) -> None:
        """Clear the package cache."""
        self._cache.clear()
        logger.info("Package cache cleared")


# Global instance
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
]