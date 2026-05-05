"""
Humanizer pipeline — orchestrates the multi-pass rewrite + detector loop.

Entry points:
    run(text, *, api_key, intensity, seo_target, style_profile_id, user_id, ...)
        → dict with output, scores, passes_summary, run_id

    score(text)
        → ai-detection-only (no rewriting)

A full run:
    1. Stylometric stats (input)
    2. Fingerprint scrub (rule-based, deterministic)
    3. Burstiness pass (LLM)
    4. Perplexity injection (LLM)
    5. Style transfer (LLM, only if voice_profile available)
    6. LinkedIn SEO pass (LLM, only if seo_target == 'linkedin')
    7. Detector ensemble — if score above threshold, retry burstiness +
       perplexity passes once more (up to MAX_RETRIES).
    8. Fact guard (entity/number diff)
    9. Style fidelity score (cosine vs. style centroid)
   10. Persist run (DB + volume), return result.

The pipeline is fail-safe: any pass that fails is skipped (logged) and the
run continues. The user gets *some* improvement even if Anthropic is down.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from core.humanize import detectors, passes
from core.styles import embeddings as emb
from core.styles import stats as stx
from core.styles.injector import fetch_style_prompt

logger = logging.getLogger(__name__)


STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
HUMANIZE_ROOT = os.path.join(STORAGE_ROOT, "humanize")
os.makedirs(HUMANIZE_ROOT, exist_ok=True)

MAX_RETRIES = 3
DETECTOR_TARGET = 0.35   # final ai_detection ≤ 0.35 → "passed"


# -----------------------------------------------------------------------------
# DB
# -----------------------------------------------------------------------------

def _db():
    from db.supabase_client import get_supabase
    return get_supabase()


def _persist_run(
    *,
    run_id: str,
    user_id: str,
    project_id: Optional[str],
    conversation_id: Optional[str],
    style_profile_id: Optional[str],
    intensity: str,
    seo_target: Optional[str],
    preserve_facts: bool,
    input_text: str,
    output_text: str,
    final_scores: Dict[str, Any],
    passes_summary: List[Dict[str, Any]],
    detector_retries: int,
    duration_ms: int,
    status: str,
    error: Optional[str],
    full_trace: Dict[str, Any],
) -> Optional[str]:
    """Insert/update studio_humanization_runs and dump full trace to volume."""
    db = _db()

    # Dump full trace to volume
    volume_path = os.path.join(HUMANIZE_ROOT, f"{run_id}.json")
    try:
        with open(volume_path, "w", encoding="utf-8") as f:
            json.dump(full_trace, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("could not write humanize trace to volume: %s", e)
        volume_path = None

    in_words = stx.stats(input_text).get("word_count", 0)
    out_words = stx.stats(output_text).get("word_count", 0)

    row = {
        "id":               run_id,
        "user_id":          user_id,
        "project_id":       project_id,
        "conversation_id":  conversation_id,
        "style_profile_id": style_profile_id,
        "intensity":        intensity,
        "seo_target":       seo_target,
        "preserve_facts":   preserve_facts,
        "input_text":       input_text[:8000],
        "output_text":      output_text[:8000],
        "input_word_count": in_words,
        "output_word_count": out_words,
        "final_scores":     final_scores,
        "passes_summary":   passes_summary,
        "detector_retries": detector_retries,
        "volume_path":      volume_path,
        "status":           status,
        "error":            error,
        "duration_ms":      duration_ms,
    }
    try:
        db.table("studio_humanization_runs").upsert(row, on_conflict="id").execute()
    except Exception as e:
        logger.warning("could not persist humanization run %s: %s", run_id, e)
    return volume_path


# -----------------------------------------------------------------------------
# Run a single pass with timing + scoring
# -----------------------------------------------------------------------------

def _run_pass(
    name: str,
    fn,
    text: str,
    ctx: Dict[str, Any],
    *,
    score: bool = False,
) -> Dict[str, Any]:
    t0 = time.time()
    try:
        result = fn(text, ctx)
        new_text = result["text"] if isinstance(result, dict) and "text" in result else result
        extra = {k: v for k, v in (result or {}).items() if k != "text"} if isinstance(result, dict) else {}
    except Exception as e:
        logger.warning("pass %s failed: %s", name, e)
        new_text = text
        extra = {"error": str(e)}
    dt = int((time.time() - t0) * 1000)

    summary: Dict[str, Any] = {
        "pass":     name,
        "ms":       dt,
        "len_in":   len(text),
        "len_out":  len(new_text),
        "changed":  bool(new_text != text),
        **extra,
    }
    if score:
        summary["ai_detection_after"] = detectors.ensemble(new_text)["ai_detection"]
    return {"text": new_text, "summary": summary}


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def score(text: str) -> Dict[str, Any]:
    """Score-only — no rewriting. Returns the full detector ensemble output."""
    return detectors.ensemble(text or "")


def run(
    *,
    text: str,
    api_key: str,
    user_id: str,
    project_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    style_profile_id: Optional[str] = None,
    intensity: str = "standard",       # 'light' | 'standard' | 'max'
    seo_target: Optional[str] = None,  # 'linkedin' | None
    preserve_facts: bool = True,
    annotate_lost_facts: bool = False,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the full humanizer pipeline. Returns:
        {
          "run_id":          str,
          "output":          str,
          "input":           str,
          "scores":          {...},
          "passes_summary":  [...],
          "lost_facts":      {...},
          "duration_ms":     int,
        }
    """
    if not text or not text.strip():
        raise ValueError("empty text")

    run_id = str(uuid.uuid4())
    started = time.time()

    voice_prompt = (
        fetch_style_prompt(style_profile_id, user_id) if style_profile_id else None
    )

    ctx = {
        "api_key":             api_key,
        "voice_system_prompt": voice_prompt,
        "seo_target":          seo_target,
        "preserve_facts":      preserve_facts,
        "annotate_lost_facts": annotate_lost_facts,
        "original_text":       text,
        "intensity":           intensity,
        "seed":                seed if seed is not None else (hash(run_id) & 0xFFFFFFFF),
        "run_id":              run_id,
    }

    initial_scores = detectors.ensemble(text)
    initial_stats  = stx.stats(text)

    summary: List[Dict[str, Any]] = []
    cur = text

    # 1. Fingerprint scrub
    r = _run_pass("fingerprint_scrub", passes.fingerprint_scrub, cur, ctx, score=False)
    cur = r["text"]; summary.append(r["summary"])

    # 2 + 3. Burstiness + perplexity (with detector retry loop on intensity=standard/max)
    max_inner_retries = {"light": 0, "standard": 1, "max": 2}.get(intensity, 1)
    retries_used = 0
    for attempt in range(max_inner_retries + 1):
        r = _run_pass("burstiness", passes.burstiness_pass, cur, ctx, score=False)
        cur = r["text"]; summary.append(r["summary"])

        r = _run_pass("perplexity", passes.perplexity_injection, cur, ctx, score=True)
        cur = r["text"]; summary.append(r["summary"])

        ai = r["summary"].get("ai_detection_after", 1.0)
        if ai is None or ai <= DETECTOR_TARGET:
            break
        retries_used = attempt + 1
        # Crank up the seed entropy on retry
        ctx["seed"] = (ctx["seed"] * 1103515245 + 12345) & 0xFFFFFFFF

    # 4. Style transfer (voice clone) — single pass
    if voice_prompt:
        r = _run_pass("style_transfer", passes.style_transfer, cur, ctx, score=False)
        cur = r["text"]; summary.append(r["summary"])

    # 5. LinkedIn SEO
    if seo_target == "linkedin":
        r = _run_pass("linkedin_seo", passes.linkedin_seo, cur, ctx, score=False)
        cur = r["text"]; summary.append(r["summary"])

    # 6. Fact guard
    fg = passes.fact_guard(cur, ctx)
    cur = fg["text"]
    summary.append({"pass": "fact_guard", "lost": fg["lost"]})

    # 7. Final scoring + style fidelity
    final = detectors.ensemble(cur)
    fidelity = None
    if style_profile_id:
        try:
            db = _db()
            row = (
                db.table("studio_writing_styles")
                .select("embedding")
                .eq("id", style_profile_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if row.data and row.data[0].get("embedding"):
                v = emb.embed(cur)
                fidelity = round(emb.cosine(v, list(row.data[0]["embedding"])), 4)
        except Exception as e:
            logger.warning("style fidelity scoring failed: %s", e)

    final_scores = {
        "ai_detection":     final["ai_detection"],
        "components":       final["components"],
        "binoculars_ratio": final.get("binoculars_ratio"),
        "gltr":             final.get("gltr"),
        "roberta_p_ai":     final.get("roberta_p_ai"),
        "style_fidelity":   fidelity,
        "stats_in":         initial_stats,
        "stats_out":        stx.stats(cur),
        "ai_detection_in":  initial_scores["ai_detection"],
    }

    duration_ms = int((time.time() - started) * 1000)

    # 8. Persist
    _persist_run(
        run_id=run_id,
        user_id=user_id,
        project_id=project_id,
        conversation_id=conversation_id,
        style_profile_id=style_profile_id,
        intensity=intensity,
        seo_target=seo_target,
        preserve_facts=preserve_facts,
        input_text=text,
        output_text=cur,
        final_scores=final_scores,
        passes_summary=summary,
        detector_retries=retries_used,
        duration_ms=duration_ms,
        status="succeeded",
        error=None,
        full_trace={
            "run_id":         run_id,
            "input":          text,
            "output":         cur,
            "passes":         summary,
            "final_scores":   final_scores,
            "ctx": {
                "intensity":         intensity,
                "seo_target":        seo_target,
                "style_profile_id":  style_profile_id,
                "voice_prompt_used": bool(voice_prompt),
            },
        },
    )

    return {
        "run_id":          run_id,
        "output":          cur,
        "input":           text,
        "scores":          final_scores,
        "passes_summary":  summary,
        "lost_facts":      fg["lost"],
        "detector_retries": retries_used,
        "duration_ms":     duration_ms,
    }
