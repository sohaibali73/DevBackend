"""Reverse Engineer routes — analyse chart images and text descriptions."""

import os
import logging
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel

from api.dependencies import get_current_user_id, get_user_api_keys
from db.supabase_client import get_supabase

router = APIRouter(prefix="/reverse-engineer", tags=["Reverse Engineer"])
logger = logging.getLogger(__name__)

_STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class DescriptionRequest(BaseModel):
    description: str


# ──────────────────────────────────────────────────────────────────────────────
# Upload image
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_chart_image(
    image: UploadFile = File(...),
    description: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Upload a chart image for reverse-engineering analysis."""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (jpeg, png, webp, gif)")

    content = await image.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large — maximum 20 MB")

    db = get_supabase()
    analysis_id = str(uuid.uuid4())

    # Save image to Railway volume
    upload_dir = os.path.join(_STORAGE_ROOT, "uploads", user_id, "reverse_engineer")
    os.makedirs(upload_dir, exist_ok=True)
    image_path = os.path.join(upload_dir, f"{analysis_id}_{image.filename or 'chart.png'}")

    try:
        with open(image_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.error(f"Could not save image: {e}")
        image_path = None  # Continue without disk storage

    # Persist analysis record
    try:
        db.table("reverse_analyses").insert({
            "id": analysis_id,
            "user_id": user_id,
            "image_path": image_path,
            "description": description,
            "status": "processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"reverse_analyses table may not exist: {e}")

    # Run AI analysis if Claude key available
    patterns = []
    strategy = {}
    status = "processing"
    error_msg = None

    if api_keys.get("claude"):
        try:
            import anthropic
            import base64

            client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])
            b64_image = base64.standard_b64encode(content).decode("utf-8")
            media_type = image.content_type or "image/png"

            prompt = (
                "Analyse this trading chart image. Identify:\n"
                "1. Chart patterns (e.g. head & shoulders, double top, triangles)\n"
                "2. Trend direction and key price levels\n"
                "3. Any visible indicators and their settings\n"
                "4. Possible entry/exit signals\n"
                "Suggest an AmiBroker AFL strategy that would capture these patterns.\n"
                "Return a JSON object with keys: patterns (array), strategy_name, entry_rules (array), "
                "exit_rules (array), afl_code_skeleton (string), confidence (0-1)."
            )

            if description:
                prompt += f"\n\nUser notes: {description}"

            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

            import json as _json
            raw_text = response.content[0].text

            # Try to extract JSON from the response
            try:
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                result_data = _json.loads(raw_text)
                patterns = result_data.get("patterns", [])
                strategy = {
                    "name": result_data.get("strategy_name", "Pattern Strategy"),
                    "entry_rules": result_data.get("entry_rules", []),
                    "exit_rules": result_data.get("exit_rules", []),
                    "afl_code": result_data.get("afl_code_skeleton", ""),
                }
                confidence = float(result_data.get("confidence", 0.75))
            except Exception:
                # Fallback: store raw text as single pattern
                patterns = [{"type": "analysis", "description": raw_text[:500], "confidence": 0.7}]
                strategy = {"name": "Pattern Strategy", "entry_rules": [], "exit_rules": [], "afl_code": ""}
                confidence = 0.7

            status = "completed"

            # Update DB record
            try:
                db.table("reverse_analyses").update({
                    "status": "completed",
                    "progress": 100,
                    "patterns": patterns,
                    "strategy": strategy,
                    "confidence": confidence,
                }).eq("id", analysis_id).execute()
            except Exception:
                pass

        except Exception as e:
            error_msg = str(e)
            status = "failed"
            logger.error(f"Image analysis failed: {e}")
            try:
                db.table("reverse_analyses").update({"status": "failed", "error": error_msg}).eq("id", analysis_id).execute()
            except Exception:
                pass
    else:
        # No API key — return processing status, user must poll
        status = "processing"

    response_body = {
        "success": True,
        "analysis_id": analysis_id,
        "status": status,
        "estimated_time": 0 if status == "completed" else 30,
    }

    if status == "completed":
        response_body["detected_patterns"] = patterns
        response_body["suggested_strategy"] = strategy

    if error_msg:
        response_body["error"] = error_msg

    return response_body


# ──────────────────────────────────────────────────────────────────────────────
# Get analysis results
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{analysis_id}/results")
async def get_analysis_results(
    analysis_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Poll for reverse-engineering analysis results."""
    db = get_supabase()

    try:
        result = db.table("reverse_analyses").select("*").eq("id", analysis_id).eq("user_id", user_id).limit(1).execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    rec = result.data[0]
    status = rec.get("status", "processing")

    if status == "processing":
        return {
            "analysis_id": analysis_id,
            "status": "processing",
            "progress": rec.get("progress", 0),
        }
    elif status == "failed":
        return {
            "analysis_id": analysis_id,
            "status": "failed",
            "error": rec.get("error", "Analysis failed"),
        }
    else:
        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "detected_patterns": rec.get("patterns") or [],
            "suggested_strategy": rec.get("strategy") or {},
            "confidence_score": rec.get("confidence", 0.0),
        }


# ──────────────────────────────────────────────────────────────────────────────
# From text description
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/from-description")
async def analyse_from_description(
    request: DescriptionRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Reverse-engineer a trading strategy from a text description."""
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key required")

    db = get_supabase()
    analysis_id = str(uuid.uuid4())

    import anthropic
    import json as _json

    client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

    prompt = (
        f"The user describes a trading strategy:\n\n{request.description}\n\n"
        "Extract the key trading patterns, rules, and indicators. "
        "Return a JSON object with keys: "
        "patterns (array of {type, description, confidence}), "
        "strategy (object with name, entry_rules array, exit_rules array, afl_code string), "
        "confidence (0-1 number)."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        try:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            result_data = _json.loads(raw_text)
            patterns = result_data.get("patterns", [])
            strategy = result_data.get("strategy", {})
            confidence = float(result_data.get("confidence", 0.8))
        except Exception:
            patterns = [{"type": "description", "description": raw_text[:300], "confidence": 0.7}]
            strategy = {"name": "Custom Strategy", "entry_rules": [], "exit_rules": [], "afl_code": ""}
            confidence = 0.7

        # Persist record
        try:
            db.table("reverse_analyses").insert({
                "id": analysis_id,
                "user_id": user_id,
                "description": request.description,
                "status": "completed",
                "progress": 100,
                "patterns": patterns,
                "strategy": strategy,
                "confidence": confidence,
                "created_at": datetime.utcnow().isoformat(),
            }).execute()
        except Exception:
            pass

        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "detected_patterns": patterns,
            "suggested_strategy": strategy,
            "confidence_score": confidence,
        }

    except Exception as e:
        logger.error(f"Description analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# List user analyses
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_analyses(
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List the user's reverse-engineer analyses."""
    db = get_supabase()
    try:
        result = (
            db.table("reverse_analyses")
            .select("id, description, status, confidence, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        total_res = db.table("reverse_analyses").select("id", count="exact").eq("user_id", user_id).execute()
        total = total_res.count or 0
        return {"analyses": result.data or [], "total": total, "has_more": total > offset + limit}
    except Exception as e:
        logger.warning(f"reverse_analyses table may not exist: {e}")
        return {"analyses": [], "total": 0, "has_more": False}


# ──────────────────────────────────────────────────────────────────────────────
# Generate AFL from existing analysis
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/generate-code/{analysis_id}")
async def generate_code_from_analysis(
    analysis_id: str,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Generate complete AFL code from a completed analysis."""
    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key required")

    db = get_supabase()

    try:
        result = db.table("reverse_analyses").select("*").eq("id", analysis_id).eq("user_id", user_id).limit(1).execute()
    except Exception:
        raise HTTPException(status_code=404, detail="Analysis not found")

    if not result.data:
        raise HTTPException(status_code=404, detail="Analysis not found")

    rec = result.data[0]
    if rec.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Analysis not yet completed")

    patterns = rec.get("patterns") or []
    strategy = rec.get("strategy") or {}

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

    prompt = (
        f"Generate complete AmiBroker AFL code based on these detected patterns and strategy:\n\n"
        f"Patterns: {patterns}\n\nStrategy: {strategy}\n\n"
        "Generate production-ready AFL code with:\n"
        "- Buy/Sell/Short/Cover signals\n"
        "- SetPositionSize and SetTradeDelays\n"
        "- Proper exploration and chart plotting\n"
        "Return ONLY the AFL code."
    )

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        afl_code = response.content[0].text

        # Strip code block markers
        if "```" in afl_code:
            parts = afl_code.split("```")
            for part in parts:
                clean = part.strip()
                if clean.startswith("afl") or clean.startswith("//"):
                    afl_code = clean
                    break

        return {
            "analysis_id": analysis_id,
            "afl_code": afl_code,
            "strategy_name": strategy.get("name", "Pattern Strategy"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {str(e)}")
