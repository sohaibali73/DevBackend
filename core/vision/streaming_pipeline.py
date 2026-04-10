"""
StreamingPipeline
=================
Server-Sent Events (SSE) generator for real-time PPTX intelligence operations.

Instead of waiting for everything to complete before returning a response,
this module streams events to the client as each slide renders, analysis
completes, or merge finishes — giving the UI a live update feed.

Event types
-----------
slide_preview       Emitted each time a slide PNG is ready
                    { type, job_id, slide_index, total_slides,
                      filename, source_type, preview_b64, preview_url,
                      width_px, height_px }

slide_analysis      Emitted when Claude Vision analysis completes for a slide
                    { type, job_id, slide_index, analysis: {SlideAnalysis} }

task_interpreted    Emitted after Claude parses the user's instruction
                    { type, job_id, action, task_plan }

merge_complete      Emitted when the merged .pptx is ready
                    { type, job_id, download_url, slide_count, warnings }

reconstruct_slide   Emitted per reconstructed slide
                    { type, job_id, slide_index, strategy, confidence }

done                Final event
                    { type, job_id, elapsed_ms, success }

error               Non-fatal warning or fatal error
                    { type, job_id, message, fatal }

Usage
-----
    from fastapi.responses import StreamingResponse
    from core.vision.streaming_pipeline import StreamingPipeline

    @router.post("/pptx/stream/interpret-task")
    async def stream_interpret(files=File(...), context_text=Form("")):
        job_id = str(uuid.uuid4())
        pipeline = StreamingPipeline()
        return StreamingResponse(
            pipeline.stream_interpret_task(job_id, files, context_text),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",   # disable Nginx buffering
            },
        )
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

# Job storage (same as pptx_intelligence.py)
_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_JOB_STORE    = _STORAGE_ROOT / "pptx_jobs"
_JOB_STORE.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SSE helpers
# =============================================================================

def _sse(event_type: str, job_id: str, **payload) -> str:
    """Format a Server-Sent Event message."""
    data = {"type": event_type, "job_id": job_id, **payload}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_error(job_id: str, message: str, fatal: bool = False) -> str:
    return _sse("error", job_id, message=message, fatal=fatal)


def _sse_heartbeat(job_id: str) -> str:
    """Keep-alive comment line (prevents proxy timeouts)."""
    return f": heartbeat {time.time()}\n\n"


# =============================================================================
# StreamingPipeline
# =============================================================================

class StreamingPipeline:
    """
    Async generator pipeline for real-time PPTX intelligence SSE streaming.

    Each public method returns an async generator that yields SSE-formatted
    strings.  Wire into FastAPI via StreamingResponse.
    """

    def __init__(self):
        from core.vision.slide_renderer import SlideRenderer
        from core.vision.vision_engine import VisionEngine
        from core.vision.reconstruction_engine import ReconstructionEngine
        self._renderer      = SlideRenderer(render_dpi=150)
        self._vision        = VisionEngine()
        self._reconstructor = ReconstructionEngine()

    # ──────────────────────────────────────────────────────────────────────────
    # Main streaming entry point
    # ──────────────────────────────────────────────────────────────────────────

    async def stream_interpret_task(
        self,
        job_id:       str,
        ingested:     List[Dict[str, Any]],   # from _ingest_uploads()
        context_text: str = "",
        run_vision:   bool = True,
    ) -> AsyncGenerator[str, None]:
        """
        Full streaming pipeline:
        1. Render slides for all uploaded files, streaming each preview
        2. Parse user task with Claude
        3. Execute action (merge / reconstruct / analyze)
        4. Emit done
        """
        start = time.time()
        _ensure_job_dir(job_id)

        # ── heartbeat ─────────────────────────────────────────────────────────
        yield _sse_heartbeat(job_id)

        # ── Phase 1: Render all slide previews, streaming each one ────────────
        rendered_manifests: List = []
        file_meta: List[Dict] = []

        for fi in ingested:
            ftype = fi["file_type"]
            if ftype not in ("pptx", "ppt", "pdf", "html", "htm",
                             "png", "jpg", "jpeg", "webp"):
                continue

            manifest = await self._renderer.render(
                file_bytes=fi["bytes"],
                file_type=ftype,
                filename=fi["filename"],
            )
            rendered_manifests.append((fi["filename"], manifest))
            file_meta.append({
                "filename":  fi["filename"],
                "slide_count": manifest.slide_count,
                "success":   manifest.success,
                "error":     manifest.error,
            })

            if not manifest.success:
                yield _sse_error(
                    job_id,
                    f"Render failed for {fi['filename']}: {manifest.error}",
                    fatal=False,
                )
                continue

            # Stream each slide preview as soon as it's ready
            for slide in manifest.slides:
                _save_slide_preview(job_id, slide.index, slide.image_bytes)
                yield _sse(
                    "slide_preview", job_id,
                    slide_index=slide.index,
                    total_slides=manifest.slide_count,
                    filename=fi["filename"],
                    source_type=slide.source_type,
                    preview_b64=slide.data_uri,
                    preview_url=f"/pptx/preview/{job_id}/{slide.index}",
                    width_px=slide.width_px,
                    height_px=slide.height_px,
                )
                await asyncio.sleep(0)   # yield control to event loop

        yield _sse_heartbeat(job_id)

        # ── Phase 2: Parse user task ──────────────────────────────────────────
        task_plan: Dict[str, Any] = {
            "action": "analyze",
            "description": "No task description — showing slide previews",
            "confidence": 1.0,
        }
        action = "analyze"

        file_names = [fi["filename"] for fi in ingested]

        if context_text.strip() and ingested:
            yield _sse("status", job_id, message="Interpreting task with AI…")
            try:
                task_plan = await self._vision.describe_task(
                    context_text=context_text,
                    file_names=file_names,
                    slide_manifests=file_meta,
                )
                action = task_plan.get("action", "analyze")
                yield _sse("task_interpreted", job_id,
                           action=action, task_plan=task_plan)
            except Exception as exc:
                yield _sse_error(job_id, f"Task interpretation failed: {exc}")

        # ── Phase 3: Execute action ───────────────────────────────────────────
        if action == "merge":
            async for event in self._stream_merge(
                job_id=job_id,
                ingested=ingested,
                task_plan=task_plan,
            ):
                yield event

        elif action == "reconstruct":
            async for event in self._stream_reconstruct(
                job_id=job_id,
                rendered_manifests=rendered_manifests,
                run_vision=run_vision,
            ):
                yield event

        elif action == "analyze" and run_vision:
            async for event in self._stream_vision_analysis(
                job_id=job_id,
                rendered_manifests=rendered_manifests,
                context=context_text,
            ):
                yield event

        # ── Phase 4: Done ────────────────────────────────────────────────────
        elapsed = round((time.time() - start) * 1000)
        yield _sse("done", job_id,
                   elapsed_ms=elapsed,
                   success=True,
                   action=action,
                   files=file_meta)

    # ──────────────────────────────────────────────────────────────────────────
    # Merge streaming
    # ──────────────────────────────────────────────────────────────────────────

    async def _stream_merge(
        self,
        job_id:    str,
        ingested:  List[Dict[str, Any]],
        task_plan: Dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        from api.routes.pptx_intelligence import _run_automizer_merge

        yield _sse("status", job_id, message="Assembling merged deck…")

        pptx_files = [fi for fi in ingested if fi["file_type"] in ("pptx", "ppt")]
        if len(pptx_files) < 2:
            yield _sse_error(job_id, "Need at least 2 PPTX files to merge.", fatal=True)
            return

        source_fn = task_plan.get("source_file")
        target_fn = task_plan.get("target_file")
        slide_range_raw = task_plan.get("slide_range")
        out_filename = task_plan.get("output_filename", "merged_presentation.pptx")

        target_fi = next((f for f in pptx_files if f["filename"] == target_fn), pptx_files[0])
        source_fi = next((f for f in pptx_files if f["filename"] == source_fn), pptx_files[-1])

        from core.vision.slide_renderer import SlideRenderer
        target_count = SlideRenderer.get_slide_count(target_fi["bytes"])
        source_count = SlideRenderer.get_slide_count(source_fi["bytes"])

        if slide_range_raw and isinstance(slide_range_raw, list) and len(slide_range_raw) == 2:
            sr_start, sr_end = int(slide_range_raw[0]), int(slide_range_raw[1])
        else:
            sr_start, sr_end = 1, source_count

        slides_spec = []
        for i in range(1, target_count + 1):
            slides_spec.append({"source_file": target_fi["filename"], "slide_number": i, "modifications": []})
        for j in range(sr_start, sr_end + 1):
            slides_spec.append({"source_file": source_fi["filename"], "slide_number": j, "modifications": []})

        automizer_spec = {
            "mode": "assembly",
            "filename": out_filename,
            "root_template": target_fi["filename"],
            "remove_existing_slides": True,
            "slides": slides_spec,
        }

        loop = asyncio.get_event_loop()
        auto_result = await loop.run_in_executor(
            None, _run_automizer_merge, automizer_spec, target_fi, source_fi
        )

        if auto_result.success:
            _save_output_pptx(job_id, auto_result.data, out_filename)

            # Stream previews of merged output
            yield _sse("status", job_id, message="Rendering merged preview…")
            merged_manifest = await self._renderer.render(
                file_bytes=auto_result.data,
                file_type="pptx",
                filename=out_filename,
            )
            for slide in merged_manifest.slides:
                _save_slide_preview(job_id, slide.index, slide.image_bytes)
                yield _sse(
                    "slide_preview", job_id,
                    slide_index=slide.index,
                    total_slides=merged_manifest.slide_count,
                    filename=out_filename,
                    source_type="merged",
                    preview_b64=slide.data_uri,
                    preview_url=f"/pptx/preview/{job_id}/{slide.index}",
                    width_px=slide.width_px,
                    height_px=slide.height_px,
                )
                await asyncio.sleep(0)

            yield _sse(
                "merge_complete", job_id,
                download_url=f"/pptx/download/{job_id}",
                output_filename=out_filename,
                slide_count=merged_manifest.slide_count,
                source_file=source_fi["filename"],
                target_file=target_fi["filename"],
                slides_merged=list(range(sr_start, sr_end + 1)),
                warnings=auto_result.warnings,
            )
        else:
            yield _sse_error(job_id, f"Merge failed: {auto_result.error}", fatal=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Reconstruct streaming
    # ──────────────────────────────────────────────────────────────────────────

    async def _stream_reconstruct(
        self,
        job_id:             str,
        rendered_manifests: List,
        run_vision:         bool = True,
    ) -> AsyncGenerator[str, None]:
        from core.sandbox.pptx_sandbox import PptxSandbox

        all_specs     = []
        all_analyses  = []
        all_images    = {}

        for fname, manifest in rendered_manifests:
            if not manifest.success:
                continue

            for slide_info in manifest.slides:
                all_images[slide_info.index] = slide_info.image_bytes

            if run_vision:
                # Stream per-slide analysis
                sem = asyncio.Semaphore(3)

                async def _analyze(si):
                    async with sem:
                        return await self._vision.analyze_slide(
                            si.image_bytes, si.index,
                            extra_context=f"File: {fname}", fast_mode=True
                        )

                tasks = [_analyze(s) for s in manifest.slides]
                for coro in asyncio.as_completed(tasks):
                    analysis = await coro
                    all_analyses.append(analysis)
                    spec = self._reconstructor.build_spec(
                        analysis, all_images.get(analysis.slide_index)
                    )
                    all_specs.append((analysis.slide_index, spec))
                    yield _sse(
                        "slide_analysis", job_id,
                        slide_index=analysis.slide_index,
                        layout_type=analysis.layout_type,
                        reconstruction_strategy=analysis.reconstruction_strategy,
                        confidence=analysis.reconstruction_confidence,
                        title=analysis.title,
                        analysis=analysis.to_dict(),
                    )
                    await asyncio.sleep(0)
            else:
                for slide_info in manifest.slides:
                    from core.vision.vision_engine import SlideAnalysis
                    dummy = SlideAnalysis(
                        slide_index=slide_info.index,
                        reconstruction_strategy="full_image_embed",
                        reconstruction_confidence=0.0,
                    )
                    spec = self._reconstructor.build_spec(dummy, slide_info.image_bytes)
                    all_specs.append((slide_info.index, spec))

        # Sort specs by slide index
        all_specs_sorted = [s for _, s in sorted(all_specs, key=lambda x: x[0])]

        if not all_specs_sorted:
            yield _sse_error(job_id, "No slides to reconstruct.", fatal=True)
            return

        yield _sse("status", job_id, message="Generating editable PPTX…")
        sandbox = PptxSandbox()
        loop = asyncio.get_event_loop()
        pptx_result = await loop.run_in_executor(
            None, sandbox.generate,
            {"title": "Reconstructed Presentation", "slides": all_specs_sorted}
        )

        if pptx_result.success:
            out_fn = "reconstructed_presentation.pptx"
            _save_output_pptx(job_id, pptx_result.data, out_fn)

            yield _sse("status", job_id, message="Rendering reconstructed preview…")
            prev_manifest = await self._renderer.render(
                file_bytes=pptx_result.data, file_type="pptx", filename=out_fn
            )
            for slide in prev_manifest.slides:
                _save_slide_preview(job_id, slide.index, slide.image_bytes)
                yield _sse(
                    "slide_preview", job_id,
                    slide_index=slide.index,
                    total_slides=prev_manifest.slide_count,
                    filename=out_fn,
                    source_type="reconstructed",
                    preview_b64=slide.data_uri,
                    preview_url=f"/pptx/preview/{job_id}/{slide.index}",
                    width_px=slide.width_px,
                    height_px=slide.height_px,
                )
                await asyncio.sleep(0)

            yield _sse(
                "reconstruct_complete", job_id,
                download_url=f"/pptx/download/{job_id}",
                output_filename=out_fn,
                slide_count=len(all_specs_sorted),
                analyses=[a.to_dict() for a in all_analyses],
            )
        else:
            yield _sse_error(job_id, f"PptxSandbox failed: {pptx_result.error}", fatal=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Vision analysis streaming
    # ──────────────────────────────────────────────────────────────────────────

    async def _stream_vision_analysis(
        self,
        job_id:             str,
        rendered_manifests: List,
        context:            str = "",
    ) -> AsyncGenerator[str, None]:
        total = sum(m.slide_count for _, m in rendered_manifests if m.success)
        analyzed = 0

        for fname, manifest in rendered_manifests:
            if not manifest.success:
                continue

            sem = asyncio.Semaphore(3)

            async def _analyze(si):
                async with sem:
                    return await self._vision.analyze_slide(
                        si.image_bytes, si.index,
                        extra_context=context or f"File: {fname}",
                        fast_mode=True,
                    )

            tasks = [_analyze(s) for s in manifest.slides]
            for coro in asyncio.as_completed(tasks):
                analysis = await coro
                analyzed += 1
                yield _sse(
                    "slide_analysis", job_id,
                    slide_index=analysis.slide_index,
                    filename=fname,
                    total_slides=total,
                    analyzed=analyzed,
                    layout_type=analysis.layout_type,
                    background=analysis.background,
                    title=analysis.title,
                    section_label=analysis.section_label,
                    reconstruction_strategy=analysis.reconstruction_strategy,
                    confidence=analysis.reconstruction_confidence,
                    has_logo=analysis.has_logo,
                    color_palette=analysis.color_palette,
                    analysis=analysis.to_dict(),
                )
                await asyncio.sleep(0)

        yield _sse("analysis_complete", job_id, total_analyzed=analyzed)


# =============================================================================
# Shared job helpers (mirrored from pptx_intelligence.py to avoid circular imports)
# =============================================================================

def _ensure_job_dir(job_id: str) -> Path:
    d = _JOB_STORE / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_slide_preview(job_id: str, slide_index: int, png_bytes: bytes) -> None:
    (_JOB_STORE / job_id / f"slide_{slide_index:04d}.png").write_bytes(png_bytes)


def _save_output_pptx(job_id: str, pptx_bytes: bytes, filename: str) -> None:
    (_JOB_STORE / job_id / filename).write_bytes(pptx_bytes)
