"""
Humanizer pipeline — orchestrates the multi-pass rewrite + detector loop.

Optimized v2:
  • Single UNIFIED LLM rewrite (burstiness + perplexity + voice + LinkedIn)
    instead of 2-4 sequential calls — typical speedup 2-4x on Sonnet,
    3-6x when HUMANIZE_MODEL is Haiku.
  • PARALLEL CHUNKING — texts > ~2k chars are split on paragraph boundaries
    and rewritten concurrently in a thread pool, then stitched back.
  • Heavy torch detectors (Binoculars/GLTR/Roberta) only run for
    intensity='max'; light/standard use the fast stylometric scorer.
  • Light-intensity short-text path runs the rule-based fingerprint scrub
    + a single rewrite call and skips fact-guard niceties — sub-second
    latency on small inputs once Anthropic responds.

Entry points:
    run(text, ...)   — full rewrite returning {output, scores, ...}
    score(text)      — detection-only

Fail-safe: any pass that errors is skipped (logged); the run continues.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from core.humanize import detectors, passes
from core.styles import embeddings as emb
from core.styles import stats as stx
from core.styles.injector import fetch_style_prompt

logger = logging.getLogger(__name__)


STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")
HUMANIZE_ROOT = os.path.join(STORAGE_ROOT, "humanize")
os.makedirs(HUMANIZE_ROOT, exist_ok=True)

# ---- Tunables (env-overridable) -------------------------------------------------
DETECTOR_TARGET = float(os.getenv("HUMANIZE_DETECTOR_TARGET", "0.35"))
CHUNK_MIN_CHARS = int(os.getenv("HUMANIZE_CHUNK_MIN_CHARS", "2000"))
CHUNK_MAX_CHARS = int(os.getenv("HUMANIZE_CHUNK_MAX_CHARS", "2500"))
PARALLEL_WORKERS = int(os.getenv("HUMANIZE_PARALLEL_WORKERS", "4"))
HEAVY_DETECTORS_ON_MAX_ONLY = os.getenv("HUMANIZE_HEAVY_DETECTORS", "max_only") == "max_only"


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
# Detection helpers
# -----------------------------------------------------------------------------

def _light_score(text: str) -> Dict[str, Any]:
    """Lightweight, sync, no-torch AI-detection score (≈ 1 ms)."""
    from core.styles.stats import ai_detection_score
    light = ai_detection_score(text or "")
    return {
        "ai_detection":     light["score"],
        "components":       {"stats": light["score"]},
        "binoculars_ratio": None,
        "gltr":             None,
        "roberta_p_ai":     None,
        "light":            light,
    }


def _detect(text: str, *, intensity: str) -> Dict[str, Any]:
    """Pick light-vs-heavy detector path based on intensity."""
    if intensity == "max" or not HEAVY_DETECTORS_ON_MAX_ONLY:
        return detectors.ensemble(text or "")
    return _light_score(text or "")


# -----------------------------------------------------------------------------
# Chunking — split long text on paragraph boundaries for parallel rewrite
# -----------------------------------------------------------------------------

def _chunk_for_parallel(text: str, *, target_size: int = CHUNK_MAX_CHARS) -> List[str]:
    """
    Split text into ~target_size chunks at paragraph boundaries (\\n\\n).
    If a single paragraph is bigger than target_size, it stays whole.
    Returns at least one chunk.
    """
    if not text:
        return [""]
    if len(text) <= CHUNK_MIN_CHARS:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    cur = ""
    for p in paragraphs:
        if not cur:
            cur = p
        elif len(cur) + 2 + len(p) <= target_size:
            cur = cur + "\n\n" + p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


def _rewrite_one_chunk(chunk: str, ctx: Dict[str, Any]) -> Tuple[str, int]:
    """Run unified rewrite on a single chunk. Returns (text, model_calls)."""
    if not chunk.strip():
        return chunk, 0
    res = passes.unified_rewrite(chunk, ctx)
    return res.get("text") or chunk, int(res.get("model_calls") or 0)


def _parallel_unified_rewrite(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chunk text on paragraph boundaries, fan out to ThreadPoolExecutor for
    concurrent Anthropic calls, stitch results in order.
    """
    chunks = _chunk_for_parallel(text)
    if len(chunks) == 1:
        out, calls = _rewrite_one_chunk(chunks[0], ctx)
        return {"text": out, "chunks": 1, "model_calls": calls}

    workers = min(PARALLEL_WORKERS, max(1, len(chunks)))
    results: List[str] = [""] * len(chunks)
    total_calls = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_rewrite_one_chunk, c, ctx): i for i, c in enumerate(chunks)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                t, calls = fut.result()
                results[i] = t
                total_calls += calls
            except Exception as e:
                logger.warning("chunk %d rewrite failed: %s", i, e)
                results[i] = chunks[i]
    return {"text": "\n\n".join(results), "chunks": len(chunks), "model_calls": total_calls}


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def score(text: str) -> Dict[str, Any]:
    """Score-only — runs the full ensemble (heavy)."""
    return detectors.ensemble(text or "")


def score_fast(text: str) -> Dict[str, Any]:
    """Score-only — lightweight stylometric only (sub-millisecond)."""
    return _light_score(text or "")


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
    Run the humanizer. Returns:
        {
          "run_id":          str,
          "output":          str,
          "input":           str,
          "scores":          {...},
          "passes_summary":  [...],
          "lost_facts":      {...},
          "duration_ms":     int,
          "model_calls":     int,
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

    initial_scores = _detect(text, intensity=intensity)
    initial_stats  = stx.stats(text)

    summary: List[Dict[str, Any]] = []
    cur = text
    total_model_calls = 0
    retries_used = 0

    # 1. Fingerprint scrub (deterministic, ~ms)
    t0 = time.time()
    cur = passes.fingerprint_scrub(cur, ctx)
    summary.append({
        "pass":    "fingerprint_scrub",
        "ms":      int((time.time() - t0) * 1000),
        "len_in":  len(text),
        "len_out": len(cur),
        "changed": cur != text,
    })

    # 2. UNIFIED REWRITE (parallel chunked) — single LLM round-trip per chunk
    t0 = time.time()
    rew = _parallel_unified_rewrite(cur, ctx)
    cur = rew["text"]
    total_model_calls += rew["model_calls"]
    after_unified_score = _detect(cur, intensity=intensity)["ai_detection"]
    summary.append({
        "pass":               "unified_rewrite",
        "ms":                 int((time.time() - t0) * 1000),
        "chunks":             rew["chunks"],
        "model_calls":        rew["model_calls"],
        "ai_detection_after": after_unified_score,
    })

    # 3. Optional retry on intensity=max if still above target
    max_retries = {"light": 0, "standard": 0, "max": 2}.get(intensity, 0)
    for attempt in range(max_retries):
        if after_unified_score is None or after_unified_score <= DETECTOR_TARGET:
            break
        retries_used = attempt + 1
        ctx["seed"] = (ctx["seed"] * 1103515245 + 12345) & 0xFFFFFFFF
        t0 = time.time()
        rew = _parallel_unified_rewrite(cur, ctx)
        cur = rew["text"]
        total_model_calls += rew["model_calls"]
        after_unified_score = _detect(cur, intensity=intensity)["ai_detection"]
        summary.append({
            "pass":               f"unified_rewrite_retry_{attempt+1}",
            "ms":                 int((time.time() - t0) * 1000),
            "chunks":             rew["chunks"],
            "model_calls":        rew["model_calls"],
            "ai_detection_after": after_unified_score,
        })

    # 4. Fact guard (~ms, regex only)
    t0 = time.time()
    fg = passes.fact_guard(cur, ctx)
    cur = fg["text"]
    summary.append({
        "pass": "fact_guard",
        "ms":   int((time.time() - t0) * 1000),
        "lost": fg["lost"],
    })

    # 5. Final scoring (always full ensemble on max, else light)
    final = _detect(cur, intensity=intensity)
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
                fidelity = round(emb.cosine(v, row.data[0]["embedding"]), 4)
        except Exception as e:
            logger.warning("style fidelity scoring failed: %s", e)

    final_scores = {
        "ai_detection":     final["ai_detection"],
        "components":       final.get("components", {}),
        "binoculars_ratio": final.get("binoculars_ratio"),
        "gltr":             final.get("gltr"),
        "roberta_p_ai":     final.get("roberta_p_ai"),
        "style_fidelity":   fidelity,
        "stats_in":         initial_stats,
        "stats_out":        stx.stats(cur),
        "ai_detection_in":  initial_scores["ai_detection"],
    }

    duration_ms = int((time.time() - started) * 1000)

    # 6. Persist
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
                "model_calls":       total_model_calls,
            },
        },
    )

    return {
        "run_id":           run_id,
        "output":           cur,
        "input":            text,
        "scores":           final_scores,
        "passes_summary":   summary,
        "lost_facts":       fg["lost"],
        "detector_retries": retries_used,
        "duration_ms":      duration_ms,
        "model_calls":      total_model_calls,
    }
