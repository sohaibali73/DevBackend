"""
PPTX Intelligence API
=====================
Computer-vision powered presentation understanding, merging, reconstruction,
and real-time revision.

All endpoints accept a mix of:
  • Direct file uploads (multipart)
  • Previously-stored file_ids
  • Free-text context / instructions

Endpoints
---------
POST /pptx/interpret-task      NLP → auto-execute (merge / analyze / reconstruct)
POST /pptx/analyze             Upload decks → per-slide preview + analysis
POST /pptx/merge               Cherry-pick slides from multiple decks → new .pptx
POST /pptx/reconstruct         Static-image slides → native editable PPTX
POST /pptx/revise              Apply revision instruction to a previous result
GET  /pptx/preview/{job}/{idx} Serve a rendered slide PNG
GET  /pptx/status/{job_id}     Poll job progress
POST /pptx/element-library/upload   Add InDesign assets to the matching library
GET  /pptx/element-library/catalog  List available library elements
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse

from api.dependencies import get_current_user_id
from core.sandbox.automizer_sandbox import AutomizerSandbox
from core.sandbox.pptx_sandbox import PptxSandbox
from core.sandbox.pptx_reviser import PptxReviser
from core.vision.element_matcher import ElementMatcher, get_element_matcher
from core.vision.reconstruction_engine import ReconstructionEngine
from core.vision.revision_engine import RevisionEngine
from core.vision.slide_renderer import SlideRenderer
from core.vision.streaming_pipeline import StreamingPipeline
from core.vision.vision_engine import VisionEngine

router = APIRouter(prefix="/pptx", tags=["PPTX Intelligence"])
logger = logging.getLogger(__name__)

# ── Storage roots ─────────────────────────────────────────────────────────────
_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_JOB_STORE    = _STORAGE_ROOT / "pptx_jobs"
_JOB_STORE.mkdir(parents=True, exist_ok=True)

# ── File size limit for intelligence endpoints (100 MB) ───────────────────────
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# ── Supported upload types ────────────────────────────────────────────────────
_SUPPORTED_TYPES = {
    ".pptx", ".ppt", ".pdf", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".webp",
    ".docx", ".txt", ".md",
}

# ── Module-level singletons ───────────────────────────────────────────────────
_renderer        = SlideRenderer(render_dpi=150)
_vision          = VisionEngine()
_reconstructor   = ReconstructionEngine()


# =============================================================================
# Job helpers
# =============================================================================

def _new_job_id() -> str:
    return str(uuid.uuid4())


def _job_dir(job_id: str) -> Path:
    d = _JOB_STORE / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_job_meta(job_id: str, meta: Dict[str, Any]) -> None:
    (_job_dir(job_id) / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_job_meta(job_id: str) -> Optional[Dict[str, Any]]:
    p = _job_dir(job_id) / "meta.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _update_job_status(job_id: str, status: str, **extra) -> None:
    meta = _read_job_meta(job_id) or {}
    meta["status"] = status
    meta.update(extra)
    _write_job_meta(job_id, meta)


def _save_slide_preview(job_id: str, slide_index: int, png_bytes: bytes) -> str:
    """Save a slide PNG to the job dir and return its key."""
    key = f"slide_{slide_index:04d}.png"
    (_job_dir(job_id) / key).write_bytes(png_bytes)
    return key


def _save_output_pptx(job_id: str, pptx_bytes: bytes, filename: str) -> str:
    """Save the generated PPTX to the job dir."""
    out_path = _job_dir(job_id) / filename
    out_path.write_bytes(pptx_bytes)
    return str(out_path)


# =============================================================================
# File ingestion helper
# =============================================================================

async def _ingest_uploads(
    files: List[UploadFile],
    file_ids: List[str],
    user_id: str,
) -> List[Dict[str, Any]]:
    """
    Read all uploaded files + resolve file_ids from the volume.

    Returns a list of:
    {
        "filename": str,
        "file_type": str,     # extension without dot
        "bytes": bytes,
        "source": "upload" | "file_id",
    }
    """
    ingested: List[Dict[str, Any]] = []

    # ── Direct uploads ────────────────────────────────────────────────────────
    for uf in files:
        if not uf.filename:
            continue
        data = await uf.read()
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File '{uf.filename}' exceeds 100 MB limit.",
            )
        ext = Path(uf.filename).suffix.lower()
        if ext not in _SUPPORTED_TYPES and ext != "":
            logger.warning("Unsupported file type: %s", ext)
        ingested.append({
            "filename": uf.filename,
            "file_type": ext.lstrip(".") or "bin",
            "bytes": data,
            "source": "upload",
        })

    # ── file_id references (already on volume) ────────────────────────────────
    if file_ids:
        try:
            from db.supabase_client import get_supabase
            db = get_supabase()
            for fid in file_ids:
                row = db.table("file_uploads").select(
                    "storage_path, original_filename, content_type"
                ).eq("id", fid).eq("user_id", user_id).limit(1).execute()
                if not row.data:
                    logger.warning("file_id not found: %s", fid)
                    continue
                r = row.data[0]
                path = Path(r["storage_path"])
                if not path.exists():
                    logger.warning("Storage path missing: %s", path)
                    continue
                data = path.read_bytes()
                fname = r["original_filename"] or path.name
                ext = Path(fname).suffix.lower()
                ingested.append({
                    "filename": fname,
                    "file_type": ext.lstrip(".") or "bin",
                    "bytes": data,
                    "source": "file_id",
                    "file_id": fid,
                })
        except Exception as exc:
            logger.warning("file_id resolution failed: %s", exc)

    return ingested


# =============================================================================
# POST /pptx/interpret-task
# =============================================================================

@router.post("/interpret-task")
async def interpret_task(
    files:        List[UploadFile] = File(default=[]),
    file_ids:     str = Form(default="[]"),
    context_text: str = Form(default=""),
    instructions: str = Form(default="{}"),
    analyze:      bool = Form(default=True),
    user_id:      str = Depends(get_current_user_id),
):
    """
    The one-shot intelligent endpoint.

    1. Ingest all uploaded files + file_ids
    2. Claude reads the task description and identifies the action
       (merge / analyze / reconstruct / create)
    3. Renders slide previews for all uploaded decks
    4. Executes the identified action
    5. Returns job status + preview images + download URL

    Accepts
    -------
    files        : one or more PPTX / PDF / HTML files
    file_ids     : JSON array of previously-uploaded file IDs ["uuid1", ...]
    context_text : task description, boss email, Slack message, etc.
    instructions : optional JSON overrides (e.g., {"slide_range": [15, 19]})
    analyze      : if True, also run Vision analysis on all slides
    """
    job_id = _new_job_id()
    start  = time.time()

    try:
        fid_list = json.loads(file_ids) if file_ids.strip() else []
    except Exception:
        fid_list = []

    try:
        extra_instr = json.loads(instructions) if instructions.strip() else {}
    except Exception:
        extra_instr = {}

    # ── 1. Ingest files ───────────────────────────────────────────────────────
    ingested = await _ingest_uploads(files, fid_list, user_id)

    if not ingested and not context_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Provide at least one file or context_text.",
        )

    _write_job_meta(job_id, {
        "status": "running",
        "action": "interpret",
        "user_id": user_id,
        "files": [f["filename"] for f in ingested],
        "context_preview": context_text[:200],
        "created_at": time.time(),
    })

    # ── 2. Render previews for all decks ──────────────────────────────────────
    manifests: List[Dict[str, Any]] = []
    render_tasks = []
    for fi in ingested:
        if fi["file_type"] in ("pptx", "ppt", "pdf", "html", "htm",
                               "png", "jpg", "jpeg", "webp"):
            render_tasks.append((fi["filename"], fi["file_type"], fi["bytes"]))

    rendered_manifests = []
    for fname, ftype, fbytes in render_tasks:
        manifest = await _renderer.render(
            file_bytes=fbytes, file_type=ftype, filename=fname
        )
        rendered_manifests.append((fname, manifest))
        manifests.append({
            "filename": fname,
            "file_type": ftype,
            "slide_count": manifest.slide_count,
            "success": manifest.success,
            "error": manifest.error,
        })
        # Save previews to job dir
        for slide in manifest.slides:
            _save_slide_preview(job_id, slide.index, slide.image_bytes)

    # ── 3. Claude interprets the task ─────────────────────────────────────────
    file_names = [fi["filename"] for fi in ingested]
    task_plan: Dict[str, Any] = {}

    if context_text.strip() and len(ingested) > 0:
        try:
            task_plan = await _vision.describe_task(
                context_text=context_text,
                file_names=file_names,
                slide_manifests=manifests,
            )
        except Exception as exc:
            logger.warning("Task interpretation failed: %s", exc)
            task_plan = {
                "action": "analyze",
                "description": "Could not interpret task — showing analysis",
                "confidence": 0.0,
            }
    elif not context_text.strip():
        task_plan = {
            "action": "analyze",
            "description": "No task description — showing slide previews",
            "confidence": 1.0,
        }

    # Apply manual overrides from instructions param
    if extra_instr:
        task_plan.update(extra_instr)

    action = task_plan.get("action", "analyze")

    # ── 4. Execute the identified action ──────────────────────────────────────
    result: Dict[str, Any] = {
        "job_id": job_id,
        "action": action,
        "task_interpretation": task_plan,
        "files": manifests,
        "previews": _build_preview_urls(job_id, rendered_manifests),
        "elapsed_ms": round((time.time() - start) * 1000),
    }

    if action == "merge" and len(ingested) >= 2:
        merge_result = await _execute_merge(
            job_id=job_id,
            ingested=ingested,
            task_plan=task_plan,
        )
        result.update(merge_result)

    elif action == "reconstruct":
        recon_result = await _execute_reconstruct(
            job_id=job_id,
            ingested=ingested,
            task_plan=task_plan,
            rendered_manifests=rendered_manifests,
        )
        result.update(recon_result)

    elif action == "analyze" and analyze:
        analysis_result = await _execute_analyze(
            job_id=job_id,
            rendered_manifests=rendered_manifests,
            context=context_text,
        )
        result.update(analysis_result)

    _update_job_status(job_id, "complete", **result)
    result["elapsed_ms"] = round((time.time() - start) * 1000)
    return result


# =============================================================================
# POST /pptx/analyze
# =============================================================================

@router.post("/analyze")
async def analyze_presentations(
    files:        List[UploadFile] = File(default=[]),
    file_ids:     str = Form(default="[]"),
    context_text: str = Form(default=""),
    slide_range:  str = Form(default=""),
    vision:       bool = Form(default=True),
    user_id:      str = Depends(get_current_user_id),
):
    """
    Upload one or more decks, render all slides, and optionally run
    Claude Vision analysis on each slide.

    Returns per-slide previews (base64) and structured analyses.
    """
    job_id = _new_job_id()
    start  = time.time()

    fid_list = _safe_json(file_ids, [])
    sr_tuple = _parse_slide_range(slide_range)

    ingested = await _ingest_uploads(files, fid_list, user_id)
    if not ingested:
        raise HTTPException(status_code=400, detail="No files provided.")

    results = []
    for fi in ingested:
        manifest = await _renderer.render(
            file_bytes=fi["bytes"],
            file_type=fi["file_type"],
            filename=fi["filename"],
            slide_range=sr_tuple,
        )

        slide_data = []
        for slide in manifest.slides:
            _save_slide_preview(job_id, slide.index, slide.image_bytes)
            slide_data.append({
                "index": slide.index,
                "preview_url": f"/pptx/preview/{job_id}/{slide.index}",
                "preview_b64": slide.data_uri,
                "width_px": slide.width_px,
                "height_px": slide.height_px,
                "source_type": slide.source_type,
            })

        analyses = []
        if vision and manifest.success:
            try:
                vision_analyses = await _vision.analyze_manifest(
                    manifest,
                    extra_context=context_text,
                    concurrency=3,
                    fast_mode=True,
                )
                analyses = [a.to_dict() for a in vision_analyses]
            except Exception as exc:
                logger.warning("Vision analysis failed: %s", exc)

        results.append({
            "filename": fi["filename"],
            "file_type": fi["file_type"],
            "slide_count": manifest.slide_count,
            "slides": slide_data,
            "analyses": analyses,
            "render_strategy": manifest.render_strategy,
            "error": manifest.error,
        })

    return {
        "job_id": job_id,
        "action": "analyze",
        "files": results,
        "elapsed_ms": round((time.time() - start) * 1000),
    }


# =============================================================================
# POST /pptx/merge
# =============================================================================

@router.post("/merge")
async def merge_presentations(
    files:            List[UploadFile] = File(default=[]),
    file_ids:         str = Form(default="[]"),
    context_text:     str = Form(default=""),
    merge_spec:       str = Form(default="{}"),
    output_filename:  str = Form(default="merged_presentation.pptx"),
    user_id:          str = Depends(get_current_user_id),
):
    """
    Cherry-pick slides from one or more decks and assemble a new presentation.

    merge_spec (JSON) — describes the assembly:
    {
      "sources": [
        {
          "filename": "meet_potomac.pptx",   // matches uploaded file name
          "slide_range": [15, 19],           // 1-based inclusive, null = all
          "label": "source"                  // "source" | "target"
        },
        {
          "filename": "composite_details.pptx",
          "slide_range": null,
          "label": "target"
        }
      ],
      "output_order": [
        { "ref": "target", "slides": "all" },
        { "ref": "source", "slides": [15, 16, 17, 18, 19] }
      ]
    }

    If merge_spec is empty and context_text is provided, Claude will interpret
    the context and determine the merge automatically.
    """
    job_id = _new_job_id()
    start  = time.time()

    fid_list = _safe_json(file_ids, [])
    spec     = _safe_json(merge_spec, {})

    ingested = await _ingest_uploads(files, fid_list, user_id)
    if not ingested:
        raise HTTPException(status_code=400, detail="No files provided.")

    _write_job_meta(job_id, {"status": "running", "action": "merge"})

    # If no merge_spec + context_text, let Claude figure it out
    if not spec and context_text.strip():
        task_plan = await _vision.describe_task(
            context_text=context_text,
            file_names=[f["filename"] for f in ingested],
        )
        spec = _task_plan_to_merge_spec(task_plan, ingested)

    result = await _execute_merge(
        job_id=job_id,
        ingested=ingested,
        task_plan=spec,
        output_filename=output_filename,
    )

    result["job_id"] = job_id
    result["elapsed_ms"] = round((time.time() - start) * 1000)
    _update_job_status(job_id, "complete", **result)
    return result


# =============================================================================
# POST /pptx/reconstruct
# =============================================================================

@router.post("/reconstruct")
async def reconstruct_presentation(
    files:         List[UploadFile] = File(default=[]),
    file_ids:      str = Form(default="[]"),
    slide_range:   str = Form(default=""),
    context_text:  str = Form(default=""),
    force_embed:   bool = Form(default=False),
    user_id:       str = Depends(get_current_user_id),
):
    """
    Convert static-image slides to native editable pptxgenjs elements.

    Uses Claude Vision to understand each slide, then ReconstructionEngine
    to map it to a native pptx_sandbox spec.

    force_embed : if True, always embed original images (no reconstruction attempt)
    """
    job_id = _new_job_id()
    start  = time.time()

    fid_list = _safe_json(file_ids, [])
    sr_tuple = _parse_slide_range(slide_range)

    ingested = await _ingest_uploads(files, fid_list, user_id)
    if not ingested:
        raise HTTPException(status_code=400, detail="No files provided.")

    _write_job_meta(job_id, {"status": "running", "action": "reconstruct"})

    rendered_manifests = []
    for fi in ingested:
        if fi["file_type"] in ("pptx", "ppt", "pdf"):
            m = await _renderer.render(
                file_bytes=fi["bytes"],
                file_type=fi["file_type"],
                filename=fi["filename"],
                slide_range=sr_tuple,
            )
            rendered_manifests.append((fi["filename"], m))

    result = await _execute_reconstruct(
        job_id=job_id,
        ingested=ingested,
        task_plan={},
        rendered_manifests=rendered_manifests,
        force_embed=force_embed,
    )

    result["job_id"] = job_id
    result["elapsed_ms"] = round((time.time() - start) * 1000)
    _update_job_status(job_id, "complete", **result)
    return result


# =============================================================================
# POST /pptx/revise
# =============================================================================

@router.post("/revise")
async def revise_presentation(
    job_id:      str = Form(...),
    instruction: str = Form(...),
    user_id:     str = Depends(get_current_user_id),
):
    """
    Apply a revision instruction to a previously-generated presentation.

    Reads the previous job's output .pptx, interprets the instruction,
    re-runs the relevant modifications, and returns updated previews.
    """
    meta = _read_job_meta(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    job_dir = _job_dir(job_id)
    pptx_files = sorted(job_dir.glob("*.pptx"))
    if not pptx_files:
        raise HTTPException(status_code=404, detail="No PPTX output found in job.")

    pptx_bytes = pptx_files[0].read_bytes()

    # Understand revision intent
    task_plan = await _vision.describe_task(
        context_text=instruction,
        file_names=[pptx_files[0].name],
    )

    new_job_id = _new_job_id()
    _write_job_meta(new_job_id, {
        "status": "running",
        "action": "revise",
        "parent_job": job_id,
        "instruction": instruction,
    })

    if task_plan.get("action") == "merge":
        # Re-merge with new parameters
        ingested = [{"filename": pptx_files[0].name,
                     "file_type": "pptx", "bytes": pptx_bytes}]
        result = await _execute_merge(
            job_id=new_job_id, ingested=ingested, task_plan=task_plan
        )
    else:
        # Update mode: apply global text replacements based on instruction
        sandbox = AutomizerSandbox()
        auto_result = sandbox.run(
            spec={
                "mode": "update",
                "root_template": "input.pptx",
                "filename": f"revised_{pptx_files[0].name}",
                "global_replacements": [],
                "slide_modifications": [],
            },
            template_bytes=pptx_bytes,
        )
        if auto_result.success:
            pptx_path = _save_output_pptx(
                new_job_id, auto_result.data, auto_result.filename
            )
            result = {"output_pptx": f"/pptx/download/{new_job_id}", "success": True}
        else:
            result = {"success": False, "error": auto_result.error}

    result["job_id"] = new_job_id
    result["parent_job"] = job_id
    _update_job_status(new_job_id, "complete", **result)
    return result


# =============================================================================
# GET /pptx/preview/{job_id}/{slide_index}
# =============================================================================

@router.get("/preview/{job_id}/{slide_index}")
async def get_slide_preview(
    job_id:      str,
    slide_index: int,
    user_id:     str = Depends(get_current_user_id),
):
    """Serve a rendered slide PNG image."""
    png_path = _job_dir(job_id) / f"slide_{slide_index:04d}.png"
    if not png_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Preview for slide {slide_index} not found in job {job_id}.",
        )
    return Response(
        content=png_path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# =============================================================================
# GET /pptx/download/{job_id}
# =============================================================================

@router.get("/download/{job_id}")
async def download_pptx(
    job_id:  str,
    user_id: str = Depends(get_current_user_id),
):
    """Download the .pptx output of a completed job."""
    job_dir = _job_dir(job_id)
    pptx_files = sorted(job_dir.glob("*.pptx"))
    if not pptx_files:
        raise HTTPException(status_code=404, detail="No PPTX output found.")
    out = pptx_files[0]
    return Response(
        content=out.read_bytes(),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": f'attachment; filename="{out.name}"',
            "Cache-Control": "no-cache",
        },
    )


# =============================================================================
# GET /pptx/status/{job_id}
# =============================================================================

@router.get("/status/{job_id}")
async def get_job_status(
    job_id:  str,
    user_id: str = Depends(get_current_user_id),
):
    """Poll job status."""
    meta = _read_job_meta(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return meta


# =============================================================================
# POST /pptx/element-library/upload
# =============================================================================

@router.post("/element-library/upload")
async def upload_library_elements(
    files:    List[UploadFile] = File(...),
    category: str = Form(default="icons"),
    tags:     str = Form(default=""),
    user_id:  str = Depends(get_current_user_id),
):
    """
    Upload InDesign-exported PNG assets to the Potomac design element library.

    category : icons | logos | backgrounds | badges | dividers | shapes
    tags     : comma-separated tag list (e.g., "hexagon,strategy,yellow")
    """
    matcher  = get_element_matcher()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    added    = []

    for uf in files:
        if not uf.filename:
            continue
        if not uf.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue

        data = await uf.read()
        if len(data) > 10 * 1024 * 1024:   # 10 MB per element
            logger.warning("Element file too large: %s", uf.filename)
            continue

        try:
            elem = matcher.add_element(
                img_bytes=data,
                filename=uf.filename,
                category=category,
                tags=tag_list or None,
            )
            added.append({
                "filename": elem.filename,
                "category": elem.category,
                "tags": elem.tags,
                "width_px": elem.width_px,
                "height_px": elem.height_px,
            })
        except Exception as exc:
            logger.error("Failed to add element %s: %s", uf.filename, exc)

    return {
        "added": added,
        "total_added": len(added),
        "library_total": matcher.element_count,
    }


# =============================================================================
# GET /pptx/element-library/catalog
# =============================================================================

@router.get("/element-library/catalog")
async def get_library_catalog(
    user_id: str = Depends(get_current_user_id),
):
    """Return a summary of all design elements in the Potomac library."""
    matcher = get_element_matcher()
    return matcher.get_catalog()


# =============================================================================
# POST /pptx/element-library/rebuild-index
# =============================================================================

@router.post("/element-library/rebuild-index")
async def rebuild_element_index(
    user_id: str = Depends(get_current_user_id),
):
    """Force a full re-index of the element library (admin operation)."""
    loop = asyncio.get_event_loop()
    matcher = get_element_matcher()
    count = await loop.run_in_executor(None, matcher.build_index, True)
    return {"indexed": count, "message": f"Re-indexed {count} design elements."}


# =============================================================================
# Internal execution helpers
# =============================================================================

async def _execute_merge(
    job_id:          str,
    ingested:        List[Dict[str, Any]],
    task_plan:       Dict[str, Any],
    output_filename: str = "merged_presentation.pptx",
) -> Dict[str, Any]:
    """
    Use AutomizerSandbox in assembly mode to merge slides.
    Works even if all slides are static images — copies pixel-perfectly.
    """
    # Build a map from filename → bytes
    file_map: Dict[str, bytes] = {fi["filename"]: fi["bytes"] for fi in ingested}

    source_file = task_plan.get("source_file")
    target_file = task_plan.get("target_file")
    slide_range_raw = task_plan.get("slide_range")
    insert_after    = task_plan.get("insert_after_slide")
    out_filename    = task_plan.get("output_filename") or output_filename

    # ── Build slide spec for AutomizerSandbox ─────────────────────────────────
    slides_spec = []

    # Determine which files are available
    pptx_files = [fi for fi in ingested if fi["file_type"] in ("pptx", "ppt")]

    if not pptx_files:
        return {
            "success": False,
            "error": "No PPTX files found for merge operation.",
        }

    if len(pptx_files) == 1:
        # Only one file — analyze and return as-is
        single = pptx_files[0]
        _save_output_pptx(job_id, single["bytes"], out_filename)
        return {
            "success": True,
            "note": "Only one PPTX provided — returned as-is.",
            "output_filename": out_filename,
            "download_url": f"/pptx/download/{job_id}",
        }

    # ── Identify target (root / base) and source (donor) ─────────────────────
    target_fi = None
    source_fi = None

    if target_file and source_file:
        # Claude identified them
        for fi in pptx_files:
            if fi["filename"] == target_file:
                target_fi = fi
            if fi["filename"] == source_file:
                source_fi = fi
    else:
        # Heuristic: first file = target (base), second = source (donor)
        target_fi = pptx_files[0]
        source_fi = pptx_files[1] if len(pptx_files) > 1 else pptx_files[0]

    if not target_fi or not source_fi:
        target_fi = pptx_files[0]
        source_fi = pptx_files[-1]

    # ── Determine slide count of source ───────────────────────────────────────
    source_slide_count = SlideRenderer.get_slide_count(source_fi["bytes"])
    if source_slide_count == 0:
        source_slide_count = 30  # safe fallback

    # ── Build source slide selection ──────────────────────────────────────────
    if slide_range_raw and isinstance(slide_range_raw, list) and len(slide_range_raw) == 2:
        sr_start, sr_end = int(slide_range_raw[0]), int(slide_range_raw[1])
    else:
        sr_start, sr_end = 1, source_slide_count  # all slides

    # ── Determine target slide count ──────────────────────────────────────────
    target_slide_count = SlideRenderer.get_slide_count(target_fi["bytes"])
    if target_slide_count == 0:
        target_slide_count = 30

    insert_at = insert_after if insert_after else target_slide_count

    # ── Automizer assembly spec ────────────────────────────────────────────────
    # All target slides first (preserving order)
    for i in range(1, target_slide_count + 1):
        slides_spec.append({
            "source_file": target_fi["filename"],
            "slide_number": i,
            "modifications": [],
        })
        if i == insert_at:
            # Insert source slides here
            for j in range(sr_start, sr_end + 1):
                slides_spec.append({
                    "source_file": source_fi["filename"],
                    "slide_number": j,
                    "modifications": [],
                })

    # If insert_at >= target_slide_count, source slides go at the end
    if not insert_after or insert_after >= target_slide_count:
        for j in range(sr_start, sr_end + 1):
            slides_spec.append({
                "source_file": source_fi["filename"],
                "slide_number": j,
                "modifications": [],
            })

    automizer_spec = {
        "mode": "assembly",
        "filename": out_filename,
        "root_template": target_fi["filename"],
        "remove_existing_slides": True,
        "slides": slides_spec,
    }

    # ── Run in executor (blocking I/O) ────────────────────────────────────────
    sandbox = AutomizerSandbox()
    loop = asyncio.get_event_loop()

    def _run():
        return sandbox.run(
            spec=automizer_spec,
            template_bytes=target_fi["bytes"],
            extra_images={source_fi["filename"]: source_fi["bytes"]}
            if source_fi != target_fi else None,
        )

    # AutomizerSandbox.run() needs templates directory with both PPTX files
    # We pass target as template_bytes and source as extra — but automizer
    # needs PPTX files in templates/, not the extra_images media dir.
    # Use a simpler approach: write both to a temp dir via the sandbox.
    auto_result = await loop.run_in_executor(None, _run_automizer_merge,
                                             automizer_spec,
                                             target_fi, source_fi)

    if auto_result.success:
        pptx_path = _save_output_pptx(job_id, auto_result.data, out_filename)
        # Render previews of the merged output
        merged_manifest = await _renderer.render(
            file_bytes=auto_result.data,
            file_type="pptx",
            filename=out_filename,
        )
        for slide in merged_manifest.slides:
            _save_slide_preview(job_id, slide.index, slide.image_bytes)

        preview_urls = [
            f"/pptx/preview/{job_id}/{s.index}"
            for s in merged_manifest.slides
        ]

        return {
            "success": True,
            "action": "merge",
            "output_filename": out_filename,
            "download_url": f"/pptx/download/{job_id}",
            "slide_count": merged_manifest.slide_count,
            "preview_urls": preview_urls,
            "source_file": source_fi["filename"],
            "target_file": target_fi["filename"],
            "slides_merged": list(range(sr_start, sr_end + 1)),
            "description": task_plan.get("description", ""),
            "warnings": auto_result.warnings,
        }
    else:
        return {
            "success": False,
            "error": auto_result.error,
            "action": "merge",
        }


def _run_automizer_merge(spec, target_fi, source_fi):
    """
    Blocking helper that configures AutomizerSandbox with both PPTX files
    as named templates.

    AutomizerSandbox copies builtin templates + writes template_bytes as
    root_template.  We pass target as the root and inject source via the
    run() extra mechanism.  Since AutomizerSandbox only accepts one extra
    bytes arg (root template), we override _copy_builtin_templates by
    writing source bytes ourselves via a patched sandbox subclass.
    """
    import shutil
    import tempfile
    from pathlib import Path
    import subprocess, json, os

    # Use the automizer sandbox directly but manually write both template files
    from core.sandbox.automizer_sandbox import (
        _UNIFIED_CACHE,
        _AUTOMIZER_RUNNER,
        _ensure_automizer_modules,
        AutomizerResult,
    )

    modules_path = _ensure_automizer_modules()
    if not modules_path:
        return AutomizerResult(False, error="pptx-automizer npm unavailable")

    start = time.time()
    temp_dir = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="pptx_merge_"))
        tpl_dir  = temp_dir / "templates"
        tpl_dir.mkdir()
        (temp_dir / "media").mkdir()

        # Write BOTH template files
        (tpl_dir / target_fi["filename"]).write_bytes(target_fi["bytes"])
        if source_fi["filename"] != target_fi["filename"]:
            (tpl_dir / source_fi["filename"]).write_bytes(source_fi["bytes"])

        (temp_dir / "spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (temp_dir / "automizer_runner.js").write_text(
            _AUTOMIZER_RUNNER, encoding="utf-8"
        )
        (temp_dir / "package.json").write_text(
            json.dumps({"name": "pptx-merge", "version": "1.0.0"}),
            encoding="utf-8",
        )

        nm_link = temp_dir / "node_modules"
        try:
            os.symlink(str(modules_path), str(nm_link))
        except OSError:
            shutil.copytree(str(modules_path), str(nm_link))

        proc = subprocess.run(
            ["node", "automizer_runner.js"],
            cwd=str(temp_dir),
            capture_output=True,
            timeout=180,
        )

        stdout = proc.stdout.decode(errors="replace").strip()
        stderr = proc.stderr.decode(errors="replace").strip()
        warnings = [ln[5:].strip() for ln in stderr.splitlines() if ln.startswith("WARN:")]
        errors   = [ln for ln in stderr.splitlines() if not ln.startswith("WARN:")]

        if proc.returncode != 0:
            return AutomizerResult(
                False,
                error="\n".join(errors) or stderr or stdout,
                exec_time_ms=round((time.time() - start) * 1000, 2),
                warnings=warnings,
            )

        filename = spec.get("filename", "output.pptx")
        out_path = temp_dir / filename
        if not out_path.exists():
            pptx_files = sorted(temp_dir.glob("*.pptx"))
            if pptx_files:
                out_path = pptx_files[0]
                filename = out_path.name
            else:
                return AutomizerResult(
                    False,
                    error=f"Output not found. stdout={stdout!r}",
                    exec_time_ms=round((time.time() - start) * 1000, 2),
                )

        data = out_path.read_bytes()
        return AutomizerResult(
            True, data=data, filename=filename,
            exec_time_ms=round((time.time() - start) * 1000, 2),
            warnings=warnings,
        )

    except Exception as exc:
        return AutomizerResult(False, error=str(exc))
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def _execute_reconstruct(
    job_id:             str,
    ingested:           List[Dict[str, Any]],
    task_plan:          Dict[str, Any],
    rendered_manifests: List = None,
    force_embed:        bool = False,
) -> Dict[str, Any]:
    """
    Vision-analyze all slides, then reconstruct as native pptxgenjs elements.
    """
    rendered_manifests = rendered_manifests or []
    if not rendered_manifests:
        for fi in ingested:
            if fi["file_type"] in ("pptx", "ppt", "pdf"):
                m = await _renderer.render(
                    file_bytes=fi["bytes"],
                    file_type=fi["file_type"],
                    filename=fi["filename"],
                )
                rendered_manifests.append((fi["filename"], m))

    all_specs = []
    all_analyses = []

    for fname, manifest in rendered_manifests:
        if not manifest.success:
            continue

        # Vision analysis
        analyses = await _vision.analyze_manifest(
            manifest, extra_context=f"File: {fname}", concurrency=3
        )
        all_analyses.extend([a.to_dict() for a in analyses])

        # Build image map for reconstruction
        image_map = {s.index: s.image_bytes for s in manifest.slides}

        # Reconstruct each slide
        specs = _reconstructor.build_spec_batch(
            analyses=analyses,
            slide_images=image_map,
        )
        all_specs.extend(specs)

    if not all_specs:
        return {
            "success": False,
            "error": "No slides could be reconstructed.",
        }

    # Generate PPTX from reconstructed specs
    sandbox = PptxSandbox()
    pptx_spec = {
        "title": task_plan.get("output_filename", "Reconstructed Presentation").replace(".pptx", ""),
        "slides": all_specs,
    }

    loop = asyncio.get_event_loop()
    pptx_result = await loop.run_in_executor(None, sandbox.generate, pptx_spec)

    if pptx_result.success:
        out_filename = "reconstructed_presentation.pptx"
        _save_output_pptx(job_id, pptx_result.data, out_filename)

        # Render previews of result
        merged_manifest = await _renderer.render(
            file_bytes=pptx_result.data, file_type="pptx", filename=out_filename
        )
        for slide in merged_manifest.slides:
            _save_slide_preview(job_id, slide.index, slide.image_bytes)

        preview_urls = [f"/pptx/preview/{job_id}/{s.index}" for s in merged_manifest.slides]

        return {
            "success": True,
            "action": "reconstruct",
            "slide_count": len(all_specs),
            "output_filename": out_filename,
            "download_url": f"/pptx/download/{job_id}",
            "preview_urls": preview_urls,
            "analyses": all_analyses,
        }
    else:
        return {
            "success": False,
            "action": "reconstruct",
            "error": pptx_result.error,
            "analyses": all_analyses,
        }


async def _execute_analyze(
    job_id:             str,
    rendered_manifests: List,
    context:            str,
) -> Dict[str, Any]:
    """Run fast Vision analysis across all rendered slides."""
    all_analyses = []
    for fname, manifest in rendered_manifests:
        if not manifest.success:
            continue
        try:
            analyses = await _vision.analyze_manifest(
                manifest, extra_context=context, concurrency=3, fast_mode=True
            )
            all_analyses.extend([a.to_dict() for a in analyses])
        except Exception as exc:
            logger.warning("Vision analysis failed for %s: %s", fname, exc)

    return {
        "action": "analyze",
        "analyses": all_analyses,
        "total_slides_analyzed": len(all_analyses),
    }


# =============================================================================
# Utility functions
# =============================================================================

def _safe_json(s: str, default):
    if not s or not s.strip():
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def _parse_slide_range(s: str):
    """Parse "15-19" or "15,19" or "" into (15, 19) or None."""
    if not s or not s.strip():
        return None
    s = s.strip()
    m = re.match(r"(\d+)\s*[-,]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)", s)
    if m:
        n = int(m.group(1))
        return n, n
    return None


def _task_plan_to_merge_spec(
    task_plan: Dict[str, Any],
    ingested:  List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Convert a VisionEngine task plan dict to a merge execution spec."""
    return {
        "source_file":       task_plan.get("source_file"),
        "target_file":       task_plan.get("target_file"),
        "slide_range":       task_plan.get("slide_range"),
        "insert_after_slide": task_plan.get("insert_after_slide"),
        "output_filename":   task_plan.get("output_filename", "merged.pptx"),
        "description":       task_plan.get("description", ""),
    }


def _build_preview_urls(
    job_id:             str,
    rendered_manifests: List,
) -> Dict[str, List[str]]:
    """Build preview URL map keyed by filename."""
    result = {}
    for fname, manifest in rendered_manifests:
        result[fname] = [
            f"/pptx/preview/{job_id}/{s.index}"
            for s in manifest.slides
        ]
    return result


# =============================================================================
# ██████╗ ██╗  ██╗ █████╗ ███████╗███████╗    ██████╗
# ██╔══██╗██║  ██║██╔══██╗██╔════╝██╔════╝    ╚════██╗
# ██████╔╝███████║███████║███████╗█████╗           ██╔╝
# ██╔═══╝ ██╔══██║██╔══██║╚════██║██╔══╝          ██╔╝
# ██║     ██║  ██║██║  ██║███████║███████╗        ██████╗
# ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝        ╚═════╝
# PHASE 2 ENDPOINTS — SSE Streaming + Smart Revision + Slide Grid + Comparison
# =============================================================================

# =============================================================================
# POST /pptx/stream/interpret-task  (SSE)
# =============================================================================

@router.post("/stream/interpret-task")
async def stream_interpret_task(
    files:        List[UploadFile] = File(default=[]),
    file_ids:     str = Form(default="[]"),
    context_text: str = Form(default=""),
    run_vision:   bool = Form(default=True),
    user_id:      str = Depends(get_current_user_id),
):
    """
    **Streaming version of /pptx/interpret-task** — real-time SSE events.

    Returns `text/event-stream`.  Each slide preview is emitted the moment
    it finishes rendering — no waiting for the full deck to complete.

    Event types emitted:
        slide_preview     — PNG ready for one slide (includes preview_b64)
        task_interpreted  — Claude understood the task
        slide_analysis    — Claude Vision result per slide (if run_vision=True)
        merge_complete    — merged .pptx is ready (if action=merge)
        reconstruct_complete — reconstructed .pptx ready
        analysis_complete — all Vision analyses done
        done              — final event with elapsed_ms
        error             — non-fatal or fatal error
        status            — progress message

    Frontend usage:
        const src = new EventSource('/pptx/stream/interpret-task', {
          withCredentials: true
        });
        // OR via fetch with ReadableStream for POST:
        const resp = await fetch('/pptx/stream/interpret-task', {
          method: 'POST',
          body: formData,
          headers: { Authorization: `Bearer ${token}` },
        });
        const reader = resp.body.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = new TextDecoder().decode(value);
          const events = text.split('\\n\\n').filter(Boolean);
          for (const e of events) {
            const data = JSON.parse(e.replace('data: ', ''));
            // handle data.type ...
          }
        }
    """
    fid_list = _safe_json(file_ids, [])
    ingested = await _ingest_uploads(files, fid_list, user_id)

    if not ingested and not context_text.strip():
        raise HTTPException(status_code=400, detail="Provide at least one file or context_text.")

    job_id   = _new_job_id()
    pipeline = StreamingPipeline()

    async def event_generator():
        async for event in pipeline.stream_interpret_task(
            job_id=job_id,
            ingested=ingested,
            context_text=context_text,
            run_vision=run_vision,
        ):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",     # disable Nginx buffering
            "X-Job-Id":          job_id,   # frontend can read this from headers
        },
    )


# =============================================================================
# POST /pptx/stream/analyze  (SSE — analyze only)
# =============================================================================

@router.post("/stream/analyze")
async def stream_analyze(
    files:        List[UploadFile] = File(default=[]),
    file_ids:     str = Form(default="[]"),
    context_text: str = Form(default=""),
    slide_range:  str = Form(default=""),
    user_id:      str = Depends(get_current_user_id),
):
    """
    Streaming analysis endpoint. Streams `slide_preview` events immediately
    as each slide renders, then `slide_analysis` events as Claude processes them.
    """
    fid_list = _safe_json(file_ids, [])
    sr_tuple = _parse_slide_range(slide_range)

    ingested = await _ingest_uploads(files, fid_list, user_id)
    if not ingested:
        raise HTTPException(status_code=400, detail="No files provided.")

    job_id   = _new_job_id()
    pipeline = StreamingPipeline()

    async def event_generator():
        # Render + stream previews
        rendered_manifests = []
        for fi in ingested:
            if fi["file_type"] not in ("pptx", "ppt", "pdf", "png", "jpg", "jpeg"):
                continue
            manifest = await pipeline._renderer.render(
                file_bytes=fi["bytes"],
                file_type=fi["file_type"],
                filename=fi["filename"],
                slide_range=sr_tuple,
            )
            rendered_manifests.append((fi["filename"], manifest))

            if not manifest.success:
                from core.vision.streaming_pipeline import _sse_error
                yield _sse_error(job_id, f"Render failed: {manifest.error}")
                continue

            from core.vision.streaming_pipeline import _sse, _save_slide_preview
            for slide in manifest.slides:
                _save_slide_preview(job_id, slide.index, slide.image_bytes)
                yield _sse(
                    "slide_preview", job_id,
                    slide_index=slide.index,
                    total_slides=manifest.slide_count,
                    filename=fi["filename"],
                    preview_b64=slide.data_uri,
                    preview_url=f"/pptx/preview/{job_id}/{slide.index}",
                    width_px=slide.width_px,
                    height_px=slide.height_px,
                )
                await asyncio.sleep(0)

        # Stream vision analysis
        async for event in pipeline._stream_vision_analysis(
            job_id=job_id,
            rendered_manifests=rendered_manifests,
            context=context_text,
        ):
            yield event

        from core.vision.streaming_pipeline import _sse
        yield _sse("done", job_id, success=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "X-Job-Id":          job_id,
        },
    )


# =============================================================================
# POST /pptx/smart-revise
# =============================================================================

@router.post("/smart-revise")
async def smart_revise(
    files:           List[UploadFile] = File(default=[]),
    file_ids:        str = Form(default="[]"),
    job_id:          str = Form(default=""),
    instruction:     str = Form(...),
    output_filename: str = Form(default=""),
    extra_context:   str = Form(default=""),
    preview:         bool = Form(default=False),
    user_id:         str = Depends(get_current_user_id),
):
    """
    **Intelligent revision** — parse a natural language instruction with Claude
    and execute targeted operations on a PPTX without regenerating it from scratch.

    Supports operations via `PptxReviser` (fast, no subprocess):
      - find_replace: "Change Q1 2025 to Q2 2025 everywhere"
      - delete_slide: "Remove slide 7"
      - reorder_slides: "Move slide 10 to position 2"
      - update_table: "Update row 2, col 3 on slide 8 to 14.2x"
      - append_slides: "Add a summary slide at the end"

    And operations via `AutomizerSandbox` (structural):
      - set_text: "Set the title shape on slide 3 to 'New Title'"
      - replace_tagged: "Replace {{QUARTER}} with Q2 2025"

    File sources (pick one):
      - files[]: upload the PPTX directly
      - file_ids: reference a previously uploaded file
      - job_id: use the .pptx output of a previous job

    preview=True: parse the instruction and return the operation list
                  WITHOUT executing (dry run for UI confirmation)
    """
    start = time.time()

    # ── Resolve PPTX source ───────────────────────────────────────────────────
    pptx_bytes: Optional[bytes] = None
    source_filename = "revised_presentation.pptx"

    if files:
        pptx_files_uploaded = [f for f in files if f.filename and
                                f.filename.lower().endswith((".pptx", ".ppt"))]
        if pptx_files_uploaded:
            data = await pptx_files_uploaded[0].read()
            pptx_bytes = data
            source_filename = pptx_files_uploaded[0].filename or source_filename

    if pptx_bytes is None and file_ids.strip() and file_ids != "[]":
        fid_list = _safe_json(file_ids, [])
        if fid_list:
            ingested = await _ingest_uploads([], fid_list, user_id)
            pptx_ingested = [fi for fi in ingested if fi["file_type"] in ("pptx", "ppt")]
            if pptx_ingested:
                pptx_bytes = pptx_ingested[0]["bytes"]
                source_filename = pptx_ingested[0]["filename"]

    if pptx_bytes is None and job_id.strip():
        job_pptx = sorted(_job_dir(job_id).glob("*.pptx")) if job_id else []
        if job_pptx:
            pptx_bytes = job_pptx[0].read_bytes()
            source_filename = job_pptx[0].name

    if pptx_bytes is None:
        raise HTTPException(status_code=400,
                            detail="Provide a PPTX file, file_id, or job_id.")

    out_filename = output_filename or f"revised_{source_filename}"
    engine = RevisionEngine()

    # ── Preview mode (parse only) ─────────────────────────────────────────────
    if preview:
        slide_count = SlideRenderer.get_slide_count(pptx_bytes)
        ops = await engine.parse_only(instruction, slide_count, extra_context)
        return {
            "preview": True,
            "instruction": instruction,
            "parsed_operations": ops,
            "operation_count": len(ops),
            "slide_count": slide_count,
            "elapsed_ms": round((time.time() - start) * 1000),
        }

    # ── Execute revision ──────────────────────────────────────────────────────
    result = await engine.smart_revise(
        pptx_bytes=pptx_bytes,
        instruction=instruction,
        output_filename=out_filename,
        extra_context=extra_context,
    )

    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "operations": result.operations,
            "elapsed_ms": round((time.time() - start) * 1000),
        }

    # Save output
    new_job_id = _new_job_id()
    _save_output_pptx(new_job_id, result.pptx_bytes, out_filename)

    # Render previews of revised deck
    revised_manifest = await _renderer.render(
        file_bytes=result.pptx_bytes, file_type="pptx", filename=out_filename
    )
    for slide in revised_manifest.slides:
        _save_slide_preview(new_job_id, slide.index, slide.image_bytes)

    preview_urls = [f"/pptx/preview/{new_job_id}/{s.index}" for s in revised_manifest.slides]

    return {
        "success": True,
        "job_id": new_job_id,
        "instruction": instruction,
        "operations": result.operations,
        "operation_count": len(result.operations),
        "summary": result.summary,
        "output_filename": out_filename,
        "download_url": f"/pptx/download/{new_job_id}",
        "slide_count": revised_manifest.slide_count,
        "preview_urls": preview_urls,
        "exec_time_ms": result.exec_time_ms,
        "elapsed_ms": round((time.time() - start) * 1000),
    }


# =============================================================================
# GET /pptx/slides/{job_id}  — Slide grid / picker
# =============================================================================

@router.get("/slides/{job_id}")
async def get_slide_grid(
    job_id:   str,
    b64:      bool = False,    # include base64 in response (can be large)
    user_id:  str = Depends(get_current_user_id),
):
    """
    Return all rendered slide thumbnails for a job as a grid manifest.

    The frontend uses this to display a visual slide picker so users can
    click to select which slides to include in a merge or review.

    b64=True includes base64-encoded PNGs in the response (convenient but large).
    b64=False (default) returns only preview_url references.
    """
    job_dir = _job_dir(job_id)
    png_files = sorted(job_dir.glob("slide_*.png"), key=lambda p: p.name)

    if not png_files:
        raise HTTPException(status_code=404, detail=f"No slide previews found for job {job_id}.")

    slides = []
    for p in png_files:
        # Parse slide index from filename: slide_0015.png → 15
        try:
            idx = int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            idx = len(slides) + 1

        entry: Dict[str, Any] = {
            "index":       idx,
            "preview_url": f"/pptx/preview/{job_id}/{idx}",
            "filename":    p.name,
            "size_bytes":  p.stat().st_size,
        }

        if b64:
            import base64 as _b64
            entry["preview_b64"] = "data:image/png;base64," + _b64.b64encode(
                p.read_bytes()
            ).decode()

        slides.append(entry)

    meta = _read_job_meta(job_id) or {}
    return {
        "job_id":      job_id,
        "slide_count": len(slides),
        "slides":      slides,
        "action":      meta.get("action"),
        "status":      meta.get("status"),
        "download_url": f"/pptx/download/{job_id}"
        if sorted(job_dir.glob("*.pptx")) else None,
    }


# =============================================================================
# POST /pptx/compare  — Deck similarity comparison
# =============================================================================

@router.post("/compare")
async def compare_decks(
    files:        List[UploadFile] = File(...),
    file_ids:     str = Form(default="[]"),
    threshold:    float = Form(default=0.85),   # similarity threshold 0-1
    user_id:      str = Depends(get_current_user_id),
):
    """
    Compare two presentation decks and identify similar / duplicate slides.

    Returns a similarity matrix and a list of matched slide pairs with scores.
    Useful for:
    - Finding duplicate content between decks before merging
    - Identifying which slides have been updated between versions
    - Detecting brand-inconsistent slides

    threshold : minimum perceptual similarity (0–1) to flag as a match (default 0.85)

    Response:
    {
      "deck_a": { "filename": "...", "slide_count": 19 },
      "deck_b": { "filename": "...", "slide_count": 32 },
      "matches": [
        { "deck_a_slide": 1, "deck_b_slide": 5, "score": 0.97, "type": "identical" },
        { "deck_a_slide": 3, "deck_b_slide": 8, "score": 0.88, "type": "similar" }
      ],
      "unique_to_a": [2, 4, 6, ...],   # slides only in deck A
      "unique_to_b": [1, 3, 7, ...]    # slides only in deck B
    }
    """
    start = time.time()
    fid_list = _safe_json(file_ids, [])
    ingested = await _ingest_uploads(files, fid_list, user_id)

    pptx_ingested = [fi for fi in ingested if fi["file_type"] in ("pptx", "ppt", "pdf")]
    if len(pptx_ingested) < 2:
        raise HTTPException(status_code=400, detail="Provide exactly 2 files to compare.")

    deck_a_fi = pptx_ingested[0]
    deck_b_fi = pptx_ingested[1]

    # Render both decks
    manifest_a = await _renderer.render(
        file_bytes=deck_a_fi["bytes"], file_type=deck_a_fi["file_type"],
        filename=deck_a_fi["filename"],
    )
    manifest_b = await _renderer.render(
        file_bytes=deck_b_fi["bytes"], file_type=deck_b_fi["file_type"],
        filename=deck_b_fi["filename"],
    )

    if not manifest_a.success or not manifest_b.success:
        return {
            "error": f"Render failed: {manifest_a.error or manifest_b.error}"
        }

    # Compute perceptual hashes for all slides in both decks
    loop = asyncio.get_event_loop()
    hashes_a = await loop.run_in_executor(
        None, _hash_slides, manifest_a.slides
    )
    hashes_b = await loop.run_in_executor(
        None, _hash_slides, manifest_b.slides
    )

    # Find matches using Hamming distance on pHash
    matches = []
    matched_a: set = set()
    matched_b: set = set()

    for idx_a, (h_a, slide_a) in enumerate(zip(hashes_a, manifest_a.slides)):
        best_score = 0.0
        best_idx_b = -1
        for idx_b, (h_b, slide_b) in enumerate(zip(hashes_b, manifest_b.slides)):
            if not h_a or not h_b:
                continue
            distance = _hamming_distance(h_a, h_b)
            score = max(0.0, 1.0 - distance / 64.0)
            if score > best_score:
                best_score = score
                best_idx_b = idx_b

        if best_score >= threshold and best_idx_b >= 0:
            match_type = "identical" if best_score >= 0.98 else "similar"
            matches.append({
                "deck_a_slide": slide_a.index,
                "deck_b_slide": manifest_b.slides[best_idx_b].index,
                "score": round(best_score, 4),
                "type": match_type,
            })
            matched_a.add(slide_a.index)
            matched_b.add(manifest_b.slides[best_idx_b].index)

    unique_to_a = [s.index for s in manifest_a.slides if s.index not in matched_a]
    unique_to_b = [s.index for s in manifest_b.slides if s.index not in matched_b]

    return {
        "deck_a": {
            "filename":    deck_a_fi["filename"],
            "slide_count": manifest_a.slide_count,
        },
        "deck_b": {
            "filename":    deck_b_fi["filename"],
            "slide_count": manifest_b.slide_count,
        },
        "threshold":    threshold,
        "matches":      sorted(matches, key=lambda m: m["score"], reverse=True),
        "match_count":  len(matches),
        "unique_to_a":  unique_to_a,
        "unique_to_b":  unique_to_b,
        "elapsed_ms":   round((time.time() - start) * 1000),
    }


def _hash_slides(slides) -> List[Optional[str]]:
    """Compute perceptual hashes for a list of SlideImageInfo objects."""
    from core.vision.element_matcher import _phash
    return [_phash(s.image_bytes) for s in slides]


def _hamming_distance(h1: str, h2: str) -> int:
    """Hamming distance between two hex hash strings."""
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 64


# =============================================================================
# POST /pptx/revision-preview  — Parse instruction without executing
# =============================================================================

@router.post("/revision-preview")
async def revision_preview(
    instruction:  str = Form(...),
    slide_count:  int = Form(default=0),
    extra_context: str = Form(default=""),
    user_id:      str = Depends(get_current_user_id),
):
    """
    Parse a revision instruction and return the operation list WITHOUT executing.

    Use this to show the user what changes would be made before they confirm.

    Response:
    {
      "instruction": "Delete slide 5 and rename Q1 to Q2",
      "operations": [
        { "type": "delete_slide", "slide_index": 4 },
        { "type": "find_replace", "find": "Q1", "replace": "Q2" }
      ],
      "operation_count": 2,
      "human_summary": "Will delete slide 5 and replace all Q1 → Q2 text"
    }
    """
    engine = RevisionEngine()
    ops = await engine.parse_only(instruction, slide_count, extra_context)

    # Build a quick human summary
    op_names = {
        "find_replace": "global text replace",
        "delete_slide": "delete slide",
        "reorder_slides": "reorder slides",
        "update_table": "update table cell",
        "append_slides": "append new slides",
        "update_slide": "update slide content",
        "set_text": "set shape text",
        "replace_tagged": "replace tagged placeholder",
    }
    summary_parts = [op_names.get(op.get("type", ""), op.get("type", "")) for op in ops]
    human_summary = f"Will perform: {', '.join(summary_parts)}" if summary_parts else "No recognized operations"

    return {
        "instruction":     instruction,
        "operations":      ops,
        "operation_count": len(ops),
        "human_summary":   human_summary,
    }
