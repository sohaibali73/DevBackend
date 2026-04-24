"""
PPTX Sandbox v2
===============
Generates Potomac-branded PowerPoint presentations server-side via pptxgenjs
in a Node.js subprocess.

Architecture
------------
- core/sandbox/js/brand.js           : palette, fonts, logos
- core/sandbox/js/layout-engine.js   : canvas, grid, stack, auto-fit
- core/sandbox/js/primitives.js      : pill, hex tile, framed slide, chrome, ...
- core/sandbox/js/templates.js       : named templates (title, hex_row, team_triad, ...)
- core/sandbox/js/runtime.js         : entry point that reads spec.json

The Python side is thin: it ensures pptxgenjs is installed, materializes a
temp workspace with JS + assets, invokes node, and returns bytes.

Spec
----
::

    {
      "title": "...",
      "filename": "output.pptx",
      "canvas": { "preset": "wide" },          # or {width, height}
      "slides": [
        { "mode": "template", "template": "hex_row", "data": {...}, "overrides": {...} },
        { "mode": "hybrid",   "template": "content", "data": {...}, "customize": "<JS>" },
        { "mode": "freestyle", "code": "<JS>", "data": {...} },
        # legacy: { "type": "title", ...fields... }  → auto-mapped
      ],
      "asset_keys": ["icon_globe_fist", "shield_swords"]   # auto-resolved
    }

Usage
-----
::

    sandbox = PptxSandbox()
    result  = sandbox.generate(spec, user_id=user_id)
    if result.success:
        entry = store_file(result.data, result.filename, "pptx", "generate_pptx")
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_THIS_DIR     = Path(__file__).parent
_JS_DIR       = _THIS_DIR / "js"
_SANDBOX_HOME = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_PPTX_CACHE_DIR = _SANDBOX_HOME / "pptx_cache"

_STORAGE_ROOT       = Path(os.environ.get("STORAGE_ROOT", "/data"))
_VOLUME_ASSETS_DIR  = _STORAGE_ROOT / "pptx_assets"
_VOLUME_GLOBAL_DIR  = _VOLUME_ASSETS_DIR / "global"
_REPO_BRAND_LOGOS   = (
    _THIS_DIR.parent.parent / "ClaudeSkills" / "potomac-pptx"
    / "brand-assets" / "logos"
)

_LOGO_FILENAMES = [
    "potomac-full-logo.png", "potomac-full-logo-black.png",
    "potomac-full-logo-white.png", "potomac-icon-black.png",
    "potomac-icon-white.png", "potomac-icon-yellow.png",
]


# ─────────────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PptxResult:
    success: bool
    data: Optional[bytes] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    exec_time_ms: float = 0.0
    canvas: Optional[Dict[str, float]] = None
    program_id: Optional[str] = None
    version: Optional[int] = None
    script: Optional[str] = None   # standalone Node.js debug script


# ─────────────────────────────────────────────────────────────────────────────
# npm cache bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_pptxgenjs_modules() -> Optional[Path]:
    """Install pptxgenjs into the persistent cache dir if not already present."""
    modules = _PPTX_CACHE_DIR / "node_modules"
    pkg = modules / "pptxgenjs"

    if pkg.exists():
        return modules

    logger.info("First-time pptxgenjs install → %s", _PPTX_CACHE_DIR)
    _PPTX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_PPTX_CACHE_DIR / "package.json").write_text(json.dumps({
        "name": "pptx-cache", "version": "1.0.0",
        "dependencies": { "pptxgenjs": "^3.12.0" },
    }, indent=2), encoding="utf-8")

    # On Windows, npm is shipped as `npm.cmd` or `npm.ps1` which cmd cannot
    # directly invoke through subprocess without shell=True.  Try a few
    # common invocations before giving up.
    npm_candidates = ["npm", "npm.cmd", "npm.ps1"]
    proc = None
    last_err: Optional[Exception] = None
    for binname in npm_candidates:
        try:
            proc = subprocess.run(
                [binname, "install", "--prefer-offline", "--no-audit", "--no-fund"],
                cwd=str(_PPTX_CACHE_DIR),
                capture_output=True,
                timeout=240,
                shell=(os.name == "nt"),  # Windows needs shell resolution
            )
            break
        except FileNotFoundError as exc:
            last_err = exc
            continue
    if proc is None:
        logger.error("npm not found — cannot install pptxgenjs (%s)", last_err)
        return None

    if proc.returncode != 0:
        logger.error("npm install failed (rc=%d): %s",
                     proc.returncode, proc.stderr.decode(errors="replace"))
        return None

    return modules


# ─────────────────────────────────────────────────────────────────────────────
# Assets
# ─────────────────────────────────────────────────────────────────────────────

def _copy_brand_logos(target_dir: Path) -> int:
    """Copy brand logo PNGs into a temp assets dir, preferring volume."""
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in _LOGO_FILENAMES:
        src = None
        if (_VOLUME_GLOBAL_DIR / name).exists():
            src = _VOLUME_GLOBAL_DIR / name
        elif (_VOLUME_ASSETS_DIR / name).exists():
            src = _VOLUME_ASSETS_DIR / name
        elif (_REPO_BRAND_LOGOS / name).exists():
            src = _REPO_BRAND_LOGOS / name
        if src:
            try:
                shutil.copy2(src, target_dir / name)
                copied += 1
            except Exception as exc:
                logger.debug("Could not copy logo %s: %s", name, exc)
    return copied


def _resolve_spec_assets(spec: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
    """Resolve any asset keys referenced in the spec into an asset_registry."""
    try:
        from core.sandbox import pptx_assets
    except ImportError:
        return {}

    keys = set(spec.get("asset_keys") or [])
    # Walk slides and collect icon_key / image_key references
    for s in spec.get("slides", []):
        if not isinstance(s, dict):
            continue
        data = s.get("data") or s
        for tile in (data.get("tiles") or data.get("items") or []):
            if isinstance(tile, dict) and tile.get("icon_key"):
                keys.add(tile["icon_key"])
        if isinstance(data, dict):
            for k in ("icon_key", "image_key", "background_key"):
                if data.get(k):
                    keys.add(data[k])

    if not keys:
        return {}
    return pptx_assets.resolve_assets(keys=sorted(keys), user_id=user_id)


def _resolve_image_file_ids(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve any `{type:'image', file_id:'...'}` → inline data."""
    spec = copy.deepcopy(spec)
    slides = spec.get("slides", [])
    needs = [s for s in slides if isinstance(s, dict)
             and (s.get("type") == "image" or (s.get("data") or {}).get("type") == "image")
             and (s.get("file_id") or (s.get("data") or {}).get("file_id"))]
    if not needs:
        return spec
    try:
        from core.file_store import get_file
    except ImportError:
        return spec
    for s in needs:
        container = s.get("data") if s.get("data") else s
        file_id = container.get("file_id", "").strip()
        if not file_id or container.get("data"):
            continue
        try:
            entry = get_file(file_id)
            if entry and entry.data:
                container["data"]   = base64.b64encode(entry.data).decode("ascii")
                container["format"] = entry.file_type or (
                    entry.filename.rsplit(".", 1)[-1].lower()
                    if "." in entry.filename else "png"
                )
        except Exception as exc:
            logger.warning("Could not resolve image file_id %s: %s", file_id, exc)
    return spec


# ─────────────────────────────────────────────────────────────────────────────
# Main Sandbox
# ─────────────────────────────────────────────────────────────────────────────

class PptxSandbox:
    """Thin orchestrator around the Node.js runtime."""

    # ── Primary API ───────────────────────────────────────────────────────
    def generate(
        self,
        spec: Dict[str, Any],
        *,
        user_id: Optional[str] = None,
        timeout: int = 180,
    ) -> PptxResult:
        """
        Render *spec* to a .pptx.

        user_id: optional — used to resolve user-scoped assets.
        result.script contains a self-contained Node.js debug script that
        reproduces the exact generation; run it with:
            node debug_script.js
        from any directory that has js/ and node_modules/pptxgenjs.
        """
        start = time.time()
        tmp: Optional[Path] = None
        debug_script: Optional[str] = None          # populated after spec is resolved
        try:
            modules = _ensure_pptxgenjs_modules()
            if modules is None:
                return PptxResult(False, error="pptxgenjs unavailable",
                                  exec_time_ms=self._ms(start))

            # Preprocess spec
            spec = _resolve_image_file_ids(spec)
            asset_registry = _resolve_spec_assets(spec, user_id)
            spec.setdefault("canvas", {"preset": "wide"})
            if asset_registry:
                spec["asset_registry"] = asset_registry

            # ── Build the debug script from the fully-resolved spec ────────
            debug_script = self._build_debug_script(spec)

            # Build temp workspace
            tmp = Path(tempfile.mkdtemp(prefix="pptx_gen_"))
            assets_dir = tmp / "assets"
            logos_found = _copy_brand_logos(assets_dir)
            if logos_found == 0:
                logger.warning("No brand logos found for pptx run")

            # Copy the JS module directory
            js_target = tmp / "js"
            shutil.copytree(_JS_DIR, js_target)

            # Write spec
            (tmp / "spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (tmp / "package.json").write_text(
                json.dumps({"name": "pptx-gen", "version": "1.0.0"}),
                encoding="utf-8",
            )

            # Symlink node_modules
            nm_link = tmp / "node_modules"
            try:
                os.symlink(str(modules), str(nm_link))
            except (OSError, NotImplementedError):
                shutil.copytree(str(modules), str(nm_link))

            # Run node
            proc = subprocess.run(
                ["node", "js/runtime.js", "spec.json"],
                cwd=str(tmp),
                capture_output=True,
                timeout=timeout,
            )
            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()

            if proc.returncode != 0:
                return PptxResult(
                    False,
                    error=f"Node.js runtime failed: {stderr or stdout}",
                    warnings=self._collect_warnings(stderr),
                    exec_time_ms=self._ms(start),
                    script=debug_script,
                )

            # Parse stdout JSON ack
            meta = {}
            try:
                meta = json.loads(stdout.splitlines()[-1])
            except Exception:
                pass

            warnings = meta.get("warnings") or self._collect_warnings(stderr)
            filename = spec.get("filename") or meta.get("filename") or "output.pptx"
            out_path = tmp / filename
            if not out_path.exists():
                cand = sorted(tmp.glob("*.pptx"))
                if cand:
                    out_path = cand[0]
                    filename = out_path.name
                else:
                    return PptxResult(
                        False,
                        error="output .pptx missing",
                        warnings=warnings,
                        exec_time_ms=self._ms(start),
                        script=debug_script,
                    )

            data = out_path.read_bytes()
            return PptxResult(
                True, data=data, filename=filename,
                warnings=warnings,
                exec_time_ms=self._ms(start),
                canvas=meta.get("canvas"),
                script=debug_script,
            )
        except subprocess.TimeoutExpired:
            return PptxResult(False, error=f"timed out after {timeout}s",
                              exec_time_ms=self._ms(start),
                              script=debug_script)
        except FileNotFoundError:
            return PptxResult(False, error="node not installed",
                              exec_time_ms=self._ms(start),
                              script=debug_script)
        except Exception as exc:
            logger.error("PptxSandbox.generate failed: %s", exc, exc_info=True)
            return PptxResult(False, error=str(exc), exec_time_ms=self._ms(start),
                              script=debug_script)
        finally:
            if tmp and tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    # ── Program lifecycle (edit memory) ───────────────────────────────────
    def generate_and_store_program(
        self,
        spec: Dict[str, Any],
        *,
        user_id: str,
        program_id: Optional[str] = None,
        title: Optional[str] = None,
        timeout: int = 180,
    ) -> PptxResult:
        """
        Render *spec* AND persist the program for future edits.

        Returns PptxResult with program_id + version populated.  Rendered
        .pptx is also saved alongside the program on the volume.
        """
        from core.sandbox import pptx_program_store

        result = self.generate(spec, user_id=user_id, timeout=timeout)
        if not result.success:
            return result

        rec = pptx_program_store.save_program(
            user_id=user_id,
            title=title or spec.get("title") or "Untitled",
            canvas=spec.get("canvas") or {"preset": "wide"},
            program={
                "title":   spec.get("title"),
                "canvas":  spec.get("canvas"),
                "slides":  spec.get("slides", []),
                "filename": spec.get("filename"),
            },
            asset_snapshot={
                k: v.get("mime") for k, v in (spec.get("asset_registry") or {}).items()
            },
            program_id=program_id,
        )
        if result.data:
            pptx_program_store.save_render_artifact(rec.id, rec.version, result.data)

        result.program_id = rec.id
        result.version    = rec.version
        return result

    def edit_program(
        self,
        program_id: str,
        *,
        user_id: str,
        patches: List[Dict[str, Any]],
        timeout: int = 180,
    ) -> PptxResult:
        """Apply patches to a stored program and re-render."""
        from core.sandbox import pptx_program_store
        rec = pptx_program_store.load_program(program_id, user_id=user_id)
        if not rec:
            return PptxResult(False, error=f"program {program_id} not found")

        new_program = pptx_program_store.apply_patches(rec.program, patches)
        spec = {
            "title":    new_program.get("title") or rec.title,
            "canvas":   new_program.get("canvas") or rec.canvas,
            "slides":   new_program.get("slides") or [],
            "filename": new_program.get("filename"),
        }
        return self.generate_and_store_program(
            spec, user_id=user_id, program_id=program_id, timeout=timeout,
        )

    def render_program(
        self,
        program_id: str,
        *,
        user_id: str,
        version: Optional[int] = None,
        timeout: int = 180,
    ) -> PptxResult:
        """Re-render a stored program (optionally a specific version)."""
        from core.sandbox import pptx_program_store
        if version is not None:
            v = pptx_program_store.get_version(
                program_id=program_id, version=version,
            )
            if not v:
                return PptxResult(False, error="version not found")
            prog = v.get("program") or {}
            canvas = v.get("canvas") or {}
            title = v.get("title") or ""
        else:
            rec = pptx_program_store.load_program(program_id, user_id=user_id)
            if not rec:
                return PptxResult(False, error="program not found")
            prog = rec.program or {}
            canvas = rec.canvas or {}
            title = rec.title or ""

        spec = {
            "title":  prog.get("title") or title,
            "canvas": canvas,
            "slides": prog.get("slides") or [],
            "filename": prog.get("filename"),
        }
        return self.generate(spec, user_id=user_id, timeout=timeout)

    # ── Freestyle (single-slide or multi-slide raw JS) ────────────────────
    def generate_freestyle(
        self,
        code: str,
        *,
        user_id: Optional[str] = None,
        title: str = "Potomac Presentation",
        filename: str = "output.pptx",
        canvas: Optional[Dict[str, Any]] = None,
        timeout: int = 180,
    ) -> PptxResult:
        """
        Shortcut for a single freestyle slide.  For multi-slide freestyle,
        build the spec manually with mode='freestyle' per slide.
        """
        spec = {
            "title":    title,
            "filename": filename,
            "canvas":   canvas or {"preset": "wide"},
            "slides":   [{"mode": "freestyle", "code": code}],
        }
        return self.generate(spec, user_id=user_id, timeout=timeout)

    # ── helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _ms(start: float) -> float:
        return round((time.time() - start) * 1000, 2)

    @staticmethod
    def _collect_warnings(stderr: str) -> List[str]:
        out = []
        for line in (stderr or "").splitlines():
            line = line.strip()
            if line.startswith("WARN:"):
                out.append(line[5:].strip())
        return out

    @staticmethod
    def _build_debug_script(spec: Dict[str, Any]) -> str:
        """
        Return a self-contained Node.js script that reproduces this exact
        pptxgenjs generation run.

        Run it from any directory that already has:
          • js/          (copy of core/sandbox/js/)
          • node_modules/ containing pptxgenjs

        Usage::

            node debug_script.js

        The script writes the spec to ``_debug_spec.json`` in the current
        directory, then delegates to the standard runtime.js entry-point so
        the output is byte-for-byte identical to the server-side render.

        Large binary blobs (asset_registry dataUrls) are truncated in the
        inline copy to keep the file human-readable; the runtime can still
        resolve them through the normal asset pipeline if needed.
        """
        # Deep-copy so we don't mutate the live spec
        display_spec = copy.deepcopy(spec)

        # Truncate long dataUrls so the script remains readable
        for _key, val in (display_spec.get("asset_registry") or {}).items():
            if isinstance(val, dict):
                raw = val.get("dataUrl", "")
                if isinstance(raw, str) and len(raw) > 200:
                    val["dataUrl"] = raw[:120] + "  /* …truncated… */"

        spec_json = json.dumps(display_spec, ensure_ascii=False, indent=2)

        lines = [
            "'use strict';",
            "/**",
            " * Auto-generated pptxgenjs debug script",
            " * =========================================",
            " * Reproduces the exact server-side PPTX generation.",
            " *",
            " * Prerequisites (run from a workspace that has these paths):",
            " *   js/            ← copy of core/sandbox/js/",
            " *   node_modules/  ← npm install pptxgenjs",
            " *",
            " * Usage:",
            " *   node debug_script.js",
            " *",
            " * Output file: output.pptx  (or whatever spec.filename is)",
            " */",
            "",
            "const fs   = require('fs');",
            "const path = require('path');",
            "",
            "// ── Fully-resolved spec (binary blobs truncated for readability) ─────",
            f"const spec = {spec_json};",
            "",
            "// Write spec to disk so runtime.js can load it via process.argv[2]",
            "const specFile = path.join(process.cwd(), '_debug_spec.json');",
            "fs.writeFileSync(specFile, JSON.stringify(spec, null, 2), 'utf8');",
            "console.error('[debug] spec written to', specFile);",
            "",
            "// Patch argv so runtime.js picks up our spec file",
            "process.argv[2] = specFile;",
            "",
            "// Run the standard Potomac runtime — output is identical to server render",
            "require('./js/runtime.js');",
        ]
        return "\n".join(lines) + "\n"
