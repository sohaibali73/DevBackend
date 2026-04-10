"""
Automizer Sandbox
=================
Template-driven PPTX generation and update via pptx-automizer (Node.js).

This is the staff-replacement engine.  Previous tools BUILD presentations from
scratch; this tool OPERATES on existing professionally-designed decks — inject
fresh chart data, update table rows, swap images, and replace tagged text while
preserving every pixel of original designer formatting.

Modes
-----
assembly  — Cherry-pick slides from one or more .pptx template files and
             assemble a new presentation with optional data injection.
             Perfect for: building from Potomac-designed master templates,
             merging slides from multiple source decks into one output.

update    — Load an existing .pptx (e.g. last quarter's report), re-add all
             slides with global find/replace + targeted chart/table/image ops.
             Perfect for: quarterly report refreshes, fund fact sheet updates,
             client deck data updates — zero manual work.

Per-Slide Operations (``modifications`` array)
----------------------------------------------
set_text              → Set entire text of a named shape
replace_tagged        → Replace {{tag}} placeholders in a shape with dynamic values
replace_text          → Simple find/replace within a specific named shape
set_chart_data        → Inject new data into an existing PowerPoint chart object
                        Preserves ALL chart styling, colors, and layout
set_extended_chart_data → Same for waterfall/funnel/map/combo charts
set_table             → Inject rows into an existing styled PowerPoint table
                        Preserves borders, fills, fonts, column widths
swap_image            → Replace image source, preserving position & size
set_position          → Reposition/resize a shape (values in centimeters)
remove_element        → Delete a shape from the slide
add_element           → Copy a named shape from another template slide
generate_scratch      → Add fresh pptxgenjs content on top of the slide

Usage
-----
    from core.sandbox.automizer_sandbox import AutomizerSandbox

    # Quarterly update: inject new chart data into last quarter's deck
    result = AutomizerSandbox().run(
        spec={
            "mode": "update",
            "filename": "q1_2026_report.pptx",
            "root_template": "input.pptx",
            "global_replacements": [
                {"find": "Q4 2025", "replace": "Q1 2026"},
                {"find": "December 31, 2025", "replace": "March 31, 2026"},
            ],
            "slide_modifications": [
                {
                    "slide_number": 3,
                    "modifications": [
                        {
                            "op": "set_chart_data",
                            "shape": "PerformanceChart",
                            "series":     [{"label": "Fund"}, {"label": "Benchmark"}],
                            "categories": [
                                {"label": "Jan", "values": [2.1, 1.8]},
                                {"label": "Feb", "values": [0.9, 1.1]},
                                {"label": "Mar", "values": [1.5, 1.3]},
                            ],
                        },
                        {
                            "op": "set_table",
                            "shape": "TopHoldingsTable",
                            "body": [
                                {"label": "r1", "values": ["Apple Inc.", "8.2%", "$1.2M"]},
                                {"label": "r2", "values": ["Microsoft", "7.1%", "$1.0M"]},
                            ],
                        },
                    ],
                }
            ],
        },
        template_bytes=pptx_bytes,   # bytes of the uploaded Q4 deck
    )
    if result.success:
        # result.data = updated .pptx bytes, fully formatted
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_SANDBOX_HOME    = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_AUTOMIZER_CACHE = _SANDBOX_HOME / "automizer_cache"

# Built-in Potomac slide templates (committed to repo at this path)
_THIS_DIR        = Path(__file__).parent                              # core/sandbox/
_BUILTIN_TPL_DIR = (
    _THIS_DIR.parent.parent
    / "ClaudeSkills" / "potomac-pptx" / "automizer-templates"
)

# ── Embedded Node.js runner ────────────────────────────────────────────────────
_AUTOMIZER_RUNNER = r"""'use strict';
/**
 * automizer_runner.js
 * Reads spec.json from cwd and orchestrates pptx-automizer operations.
 *
 * Expected cwd layout:
 *   spec.json          - operation specification
 *   templates/         - .pptx source/template files
 *   media/             - image files for swap_image operations
 *   node_modules/      - pptx-automizer + deps (symlinked from cache)
 */

const path = require('path');
const fs   = require('fs');

async function main() {
  // ── Load spec ──────────────────────────────────────────────────────────
  const spec = JSON.parse(fs.readFileSync(path.join(__dirname, 'spec.json'), 'utf8'));

  // ── Load pptx-automizer ────────────────────────────────────────────────
  const AutomizerPkg      = require('pptx-automizer');
  const Automizer         = AutomizerPkg.default || AutomizerPkg;
  const modify            = AutomizerPkg.modify;
  const ModifyShapeHelper  = AutomizerPkg.ModifyShapeHelper;
  const ModifyTextHelper   = AutomizerPkg.ModifyTextHelper;
  const ModifyTableHelper  = AutomizerPkg.ModifyTableHelper;
  const ModifyImageHelper  = AutomizerPkg.ModifyImageHelper;
  const CmToDxa            = AutomizerPkg.CmToDxa;

  // ── Paths ──────────────────────────────────────────────────────────────
  const TEMPLATE_DIR = path.join(__dirname, 'templates');
  const MEDIA_DIR    = path.join(__dirname, 'media');
  const OUTPUT_DIR   = __dirname;
  const outputFile   = spec.filename || 'output.pptx';

  // ── Build automizer instance ───────────────────────────────────────────
  const automizer = new Automizer({
    templateDir:            TEMPLATE_DIR,
    mediaDir:               MEDIA_DIR,
    outputDir:              OUTPUT_DIR,
    removeExistingSlides:   spec.remove_existing_slides !== false,
    autoImportSlideMasters: spec.auto_import_masters    !== false,
    cleanupPlaceholders:    false,
    verbosity:              0,
    compression:            0,
  });

  const mode       = spec.mode || 'assembly';
  const mediaFiles = spec.media_files || [];
  const helpers    = {
    modify, ModifyShapeHelper, ModifyTextHelper,
    ModifyTableHelper, ModifyImageHelper, CmToDxa,
  };

  // ════════════════════════════════════════════════════════════════════════
  // ASSEMBLY MODE: cherry-pick slides from template files
  // ════════════════════════════════════════════════════════════════════════
  if (mode === 'assembly') {
    const rootTemplate = spec.root_template || null;
    const slides       = spec.slides || [];

    let pres;
    if (rootTemplate) {
      pres = automizer.loadRoot(rootTemplate);
    } else {
      if (!slides.length) throw new Error('assembly mode requires slides or root_template');
      pres = automizer.loadRoot(slides[0].source_file);
    }

    // Load additional templates (deduplicated)
    const loaded = new Set();
    if (rootTemplate) loaded.add(rootTemplate);
    for (const s of slides) {
      if (s.source_file && !loaded.has(s.source_file)) {
        pres = pres.load(s.source_file, s.source_file);
        loaded.add(s.source_file);
      }
    }

    // Load media files for image swapping
    if (mediaFiles.length > 0) {
      pres = pres.loadMedia(mediaFiles);
    }

    // Add slides with modifications
    for (const slideSpec of slides) {
      if (!slideSpec.source_file) continue;
      const src  = slideSpec.source_file;
      const num  = slideSpec.slide_number || 1;
      const mods = slideSpec.modifications || [];

      pres.addSlide(src, num, async (slide) => {
        for (const mod of mods) {
          await applyMod(slide, mod, helpers);
        }
      });
    }

    await pres.write(outputFile);

  // ════════════════════════════════════════════════════════════════════════
  // UPDATE MODE: modify all slides of an existing presentation
  // ════════════════════════════════════════════════════════════════════════
  } else if (mode === 'update') {
    const inputFile          = spec.root_template || 'input.pptx';
    const globalReplacements = spec.global_replacements || [];
    const slideModMap        = {};

    for (const sm of (spec.slide_modifications || [])) {
      slideModMap[sm.slide_number] = sm.modifications || [];
    }

    // Load the file as BOTH root (truncated) AND as a named template source
    let pres = automizer
      .loadRoot(inputFile)
      .load(inputFile, '__src__');

    if (mediaFiles.length > 0) {
      pres = pres.loadMedia(mediaFiles);
    }

    // Enumerate all slides from the source
    const presInfo  = await pres.getInfo();
    const allSlides = presInfo.slidesByTemplate('__src__');

    const matchCase = !!(globalReplacements.length > 0 && globalReplacements[0].match_case);

    for (const slideInfo of allSlides) {
      const slideNum = slideInfo.number;
      const perMods  = slideModMap[slideNum] || [];

      pres.addSlide('__src__', slideNum, async (slide) => {
        // ── Global text find/replace across all text shapes ──────────────
        if (globalReplacements.length > 0) {
          const textIds = await slide.getAllTextElementIds();
          for (const elemId of textIds) {
            slide.modifyElement(elemId, [
              ModifyShapeHelper.replaceText(
                globalReplacements.map(r => ({ replace: r.find, by: r.replace })),
                { matchCase }
              )
            ]);
          }
        }

        // ── Per-slide targeted operations ─────────────────────────────────
        for (const mod of perMods) {
          await applyMod(slide, mod, helpers);
        }
      });
    }

    await pres.write(outputFile);

  } else {
    throw new Error('Unknown mode: ' + mode + '. Use "assembly" or "update".');
  }

  process.stdout.write('SUCCESS:' + outputFile + '\n');
}

// ── Apply a single modification to a slide ─────────────────────────────────────
async function applyMod(slide, mod, helpers) {
  const {
    modify, ModifyShapeHelper, ModifyTextHelper,
    ModifyTableHelper, ModifyImageHelper, CmToDxa,
  } = helpers;

  const op        = mod.op;
  const shapeName = mod.shape;

  try {
    switch (op) {

      // ── Set full text content of a named shape ──────────────────────────
      case 'set_text': {
        slide.modifyElement(shapeName, [
          ModifyShapeHelper.setText(mod.text || ''),
        ]);
        break;
      }

      // ── Replace {{tag}} style placeholders within a named shape ─────────
      case 'replace_tagged': {
        const tags = (mod.tags || []).map(t => ({
          replace: t.find || t.tag || t.replace || '',
          by:      { text: String(t.by || t.value || t.replace_with || '') },
        }));
        if (tags.length) {
          slide.modifyElement(shapeName, [
            modify.replaceText(tags, {
              openingTag: mod.opening_tag || '{{',
              closingTag:  mod.closing_tag  || '}}',
            }),
          ]);
        }
        break;
      }

      // ── Simple find/replace within a named shape ────────────────────────
      case 'replace_text': {
        const reps = (mod.replacements || []).map(r => ({
          replace: r.find,
          by:      r.replace,
        }));
        if (reps.length) {
          slide.modifyElement(shapeName, [
            ModifyShapeHelper.replaceText(reps, { matchCase: !!mod.match_case }),
          ]);
        }
        break;
      }

      // ── Inject new data into an existing PowerPoint chart object ────────
      // Preserves: chart type, colors, fonts, axis labels, legend, borders
      case 'set_chart_data': {
        slide.modifyElement(shapeName, [
          modify.setChartData({
            series:     mod.series     || [],
            categories: mod.categories || [],
          }),
        ]);
        break;
      }

      // ── Same for waterfall / map / funnel / combo extended charts ───────
      case 'set_extended_chart_data': {
        slide.modifyElement(shapeName, [
          modify.setExtendedChartData({
            series:     mod.series     || [],
            categories: mod.categories || [],
          }),
        ]);
        break;
      }

      // ── Inject rows into an existing styled PowerPoint table ────────────
      // Preserves: header formatting, borders, fill colors, column widths
      case 'set_table': {
        const tblParams = {};
        if (mod.adjust_height) tblParams.adjustHeight = true;
        if (mod.adjust_width)  tblParams.adjustWidth  = true;
        const tblArgs = [{ body: mod.body || [] }];
        if (Object.keys(tblParams).length) tblArgs.push(tblParams);
        slide.modifyElement(shapeName, [modify.setTable(...tblArgs)]);
        break;
      }

      // ── Swap image source; preserves position, size, and cropping ───────
      case 'swap_image': {
        slide.modifyElement(shapeName, [
          ModifyImageHelper.setRelationTarget(mod.image_file),
        ]);
        break;
      }

      // ── Reposition / resize a shape (input in centimeters) ──────────────
      case 'set_position': {
        const pos = {};
        if (mod.x !== undefined) pos.x = CmToDxa(mod.x);
        if (mod.y !== undefined) pos.y = CmToDxa(mod.y);
        if (mod.w !== undefined) pos.w = CmToDxa(mod.w);
        if (mod.h !== undefined) pos.h = CmToDxa(mod.h);
        slide.modifyElement(shapeName, [modify.setPosition(pos)]);
        break;
      }

      // ── Remove a shape from the slide ───────────────────────────────────
      case 'remove_element': {
        slide.removeElement(shapeName);
        break;
      }

      // ── Copy a named shape from another template slide ──────────────────
      case 'add_element': {
        slide.addElement(
          mod.source_file,
          mod.slide_number || 1,
          mod.element_name || mod.shape,
          [],
        );
        break;
      }

      // ── Add fresh pptxgenjs content on top of the existing slide ────────
      case 'generate_scratch': {
        slide.generate((pSlide, pptxGenJs) => {
          // The provided code runs with pSlide and pptxGenJs in scope.
          // Server-side only — safe to eval LLM-generated code.
          const fn = new Function('pSlide', 'pptxGenJs', mod.code || '');
          fn(pSlide, pptxGenJs);
        });
        break;
      }

      default:
        process.stderr.write(
          'WARN: Unknown op "' + op + '" on shape "' + (shapeName || '(null)') + '" — skipped\n'
        );
    }
  } catch (err) {
    process.stderr.write(
      'WARN: op=' + op + ' shape=' + (shapeName || '(null)') + ': ' + err.message + '\n'
    );
  }
}

main().catch(err => {
  process.stderr.write('ERROR: ' + err.message + '\n');
  process.exit(1);
});
""".strip()


# =============================================================================
# Result dataclass
# =============================================================================

class AutomizerResult:
    """Lightweight result container returned by AutomizerSandbox.run()."""
    __slots__ = ("success", "data", "filename", "error", "exec_time_ms", "warnings")

    def __init__(
        self,
        success:      bool,
        data:         Optional[bytes]      = None,
        filename:     Optional[str]        = None,
        error:        Optional[str]        = None,
        exec_time_ms: float                = 0.0,
        warnings:     Optional[List[str]]  = None,
    ):
        self.success      = success
        self.data         = data
        self.filename     = filename
        self.error        = error
        self.exec_time_ms = exec_time_ms
        self.warnings     = warnings or []


# =============================================================================
# npm cache helper
# =============================================================================

def _ensure_automizer_modules() -> Optional[Path]:
    """
    Ensure pptx-automizer npm package is installed in the persistent cache dir.

    First call installs once (~60–120 s). Subsequent calls return instantly
    after confirming node_modules/pptx-automizer exists.

    Returns the ``node_modules`` Path, or ``None`` on failure.
    """
    modules       = _AUTOMIZER_CACHE / "node_modules"
    automizer_pkg = modules / "pptx-automizer"

    if automizer_pkg.exists():
        logger.debug("pptx-automizer cache hit: %s", modules)
        return modules

    logger.info("First-time pptx-automizer install — this takes ~90 s…")
    _AUTOMIZER_CACHE.mkdir(parents=True, exist_ok=True)

    pkg = {
        "name":    "automizer-cache",
        "version": "1.0.0",
        "dependencies": {
            "pptx-automizer": "latest",
        },
    }
    (_AUTOMIZER_CACHE / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    proc = subprocess.run(
        ["npm", "install", "--prefer-offline", "--no-audit", "--no-fund"],
        cwd=str(_AUTOMIZER_CACHE),
        capture_output=True,
        timeout=360,
    )
    if proc.returncode != 0:
        logger.error(
            "npm install (pptx-automizer) failed (rc=%d): %s",
            proc.returncode,
            proc.stderr.decode(errors="replace").strip(),
        )
        return None

    logger.info("pptx-automizer installed → %s", modules)
    return modules


# =============================================================================
# AutomizerSandbox
# =============================================================================

class AutomizerSandbox:
    """
    Runs pptx-automizer in an isolated Node.js subprocess.

    Each call gets its own ``tempfile.mkdtemp()`` workspace.
    Thread-safe. Stateless.
    """

    def run(
        self,
        spec:           Dict[str, Any],
        template_bytes: Optional[bytes]            = None,
        extra_images:   Optional[Dict[str, bytes]] = None,
        timeout:        int                        = 180,
    ) -> AutomizerResult:
        """
        Execute an automizer spec and return the result PPTX bytes.

        Parameters
        ----------
        spec : dict
            Operation specification.  Key fields:

            mode (str):
                ``"assembly"`` — cherry-pick slides from template files.
                ``"update"``   — preserve all slides, apply global + per-slide ops.
                Default: ``"assembly"``.

            filename (str):
                Output filename, e.g. ``"Q1_2026_Report.pptx"``.

            root_template (str):
                Filename of the root .pptx inside templates/.
                For update mode: same file is used as root AND template.
                If omitted in assembly mode, first slide's source_file is used.

            remove_existing_slides (bool):
                Remove root template's slides before adding new ones.
                Default: ``True``.

            slides (list):  [assembly mode]
                Each entry: ``{source_file, slide_number, modifications}``.

            global_replacements (list):  [update mode]
                ``[{"find": "Q4 2025", "replace": "Q1 2026"}, ...]``
                Applied to ALL text shapes on ALL slides.

            slide_modifications (list):  [update mode]
                ``[{"slide_number": 3, "modifications": [mod_spec, ...]}]``
                Per-slide operations applied after global replacements.

            media_files (list):
                Filenames of images (in media/) to make available for swap_image.

        template_bytes : bytes, optional
            Raw bytes of the input .pptx.  Written to templates/input.pptx.
            Required when spec.root_template is "input.pptx".

        extra_images : dict, optional
            ``{"chart_export.png": <bytes>, ...}``
            Images written to media/ for use with ``swap_image`` operations.

        timeout : int
            Maximum seconds for Node.js execution. Default 180.

        Returns
        -------
        AutomizerResult
            ``.success``, ``.data`` (bytes), ``.filename``, ``.error``,
            ``.exec_time_ms``, ``.warnings`` (non-fatal WARN lines from Node.js).
        """
        start    = time.time()
        temp_dir: Optional[Path] = None

        try:
            # ── 1. Ensure npm cache ────────────────────────────────────────
            modules_path = _ensure_automizer_modules()
            if modules_path is None:
                return AutomizerResult(
                    False,
                    error="pptx-automizer npm package unavailable — npm install failed",
                )

            # ── 2. Isolated temp workspace ─────────────────────────────────
            temp_dir  = Path(tempfile.mkdtemp(prefix="pptx_auto_"))
            tpl_dir   = temp_dir / "templates"
            media_dir = temp_dir / "media"
            tpl_dir.mkdir()
            media_dir.mkdir()

            # ── 3. Write input template file (user-uploaded PPTX) ──────────
            if template_bytes is not None:
                root_tpl = spec.get("root_template", "input.pptx")
                (tpl_dir / root_tpl).write_bytes(template_bytes)
                logger.debug(
                    "Wrote template: %s (%d bytes)", root_tpl, len(template_bytes)
                )

            # ── 4. Copy any named builtin templates referenced in spec ──────
            self._copy_builtin_templates(spec, tpl_dir)

            # ── 5. Write extra images into media/ ──────────────────────────
            if extra_images:
                for img_name, img_bytes in extra_images.items():
                    (media_dir / img_name).write_bytes(img_bytes)
                    logger.debug(
                        "Wrote media: %s (%d bytes)", img_name, len(img_bytes)
                    )

            # ── 6. Write spec.json + runner + package.json ─────────────────
            (temp_dir / "spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temp_dir / "automizer_runner.js").write_text(
                _AUTOMIZER_RUNNER, encoding="utf-8"
            )
            (temp_dir / "package.json").write_text(
                json.dumps({"name": "pptx-auto", "version": "1.0.0"}),
                encoding="utf-8",
            )

            # ── 7. Symlink node_modules from persistent cache (O(1)) ───────
            nm_link = temp_dir / "node_modules"
            try:
                os.symlink(str(modules_path), str(nm_link))
            except OSError:
                logger.debug("symlink failed — falling back to copytree")
                shutil.copytree(str(modules_path), str(nm_link))

            # ── 8. Execute Node.js ─────────────────────────────────────────
            proc = subprocess.run(
                ["node", "automizer_runner.js"],
                cwd=str(temp_dir),
                capture_output=True,
                timeout=timeout,
            )

            stdout = proc.stdout.decode(errors="replace").strip()
            stderr = proc.stderr.decode(errors="replace").strip()

            # Split WARN lines (non-fatal) from hard errors
            warnings: List[str] = []
            error_lines: List[str] = []
            for ln in stderr.splitlines():
                if ln.startswith("WARN:"):
                    warnings.append(ln[5:].strip())
                else:
                    error_lines.append(ln)

            if proc.returncode != 0:
                err_msg = "\n".join(error_lines) if error_lines else (stderr or stdout)
                return AutomizerResult(
                    False,
                    error=f"Node.js automizer failed: {err_msg}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                    warnings=warnings,
                )

            # ── 9. Retrieve generated file ─────────────────────────────────
            filename = spec.get("filename") or "output.pptx"
            out_path = temp_dir / filename

            if not out_path.exists():
                pptx_files = sorted(temp_dir.glob("*.pptx"))
                if pptx_files:
                    out_path = pptx_files[0]
                    filename = out_path.name
                else:
                    return AutomizerResult(
                        False,
                        error=(
                            f"Output .pptx not found. "
                            f"stdout={stdout!r}  stderr={stderr!r}"
                        ),
                        exec_time_ms=round((time.time() - start) * 1000, 2),
                        warnings=warnings,
                    )

            data    = out_path.read_bytes()
            elapsed = round((time.time() - start) * 1000, 2)
            logger.info(
                "AutomizerSandbox ✓  %s  (%.1f KB, %.0f ms, %d warning(s))",
                filename, len(data) / 1024, elapsed, len(warnings),
            )
            if warnings:
                logger.debug("AutomizerSandbox warnings: %s", warnings)

            return AutomizerResult(
                True,
                data=data,
                filename=filename,
                exec_time_ms=elapsed,
                warnings=warnings,
            )

        except subprocess.TimeoutExpired:
            return AutomizerResult(
                False,
                error=f"Node.js timed out after {timeout} s",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except FileNotFoundError:
            return AutomizerResult(
                False,
                error="Node.js not found — ensure node is installed and on PATH",
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        except Exception as exc:
            logger.error("AutomizerSandbox error: %s", exc, exc_info=True)
            return AutomizerResult(
                False,
                error=str(exc),
                exec_time_ms=round((time.time() - start) * 1000, 2),
            )
        finally:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _copy_builtin_templates(
        self, spec: Dict[str, Any], tpl_dir: Path
    ) -> None:
        """
        Copy any builtin Potomac template PPTX files referenced by the spec
        into the temp templates/ directory.  Skips if the builtin dir doesn't
        exist yet (Phase 2 — templates are created separately).
        """
        if not _BUILTIN_TPL_DIR.exists():
            return

        needed: set = set()

        root = spec.get("root_template")
        if root and root != "input.pptx":
            needed.add(root)

        for slide in spec.get("slides", []):
            src = slide.get("source_file")
            if src and src != "input.pptx":
                needed.add(src)

        for sm in spec.get("slide_modifications", []):
            for m in sm.get("modifications", []):
                src = m.get("source_file")
                if src and src != "input.pptx":
                    needed.add(src)

        for name in needed:
            candidate = _BUILTIN_TPL_DIR / name
            dest      = tpl_dir / name
            if candidate.exists() and not dest.exists():
                shutil.copy2(candidate, dest)
                logger.debug("Copied builtin template: %s", name)
            elif not candidate.exists():
                logger.debug(
                    "Builtin template '%s' not found in %s — "
                    "user must provide it via template_bytes.",
                    name, _BUILTIN_TPL_DIR,
                )
