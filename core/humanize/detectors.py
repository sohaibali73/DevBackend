"""
AI-detector ensemble used by the humanizer to decide whether to keep iterating.

Three detectors:
  • binoculars  — Binoculars-style perplexity ratio between an "observer" and
                  a "performer" GPT-2 model. Higher ratio → more human.
  • gltr        — Top-K token-rank histogram. Lots of top-1 picks → more AI.
  • roberta     — Hugging Face roberta-base-openai-detector. Returns p(AI).

All three lazy-load on first use. Models are cached on the Railway volume:
    $STORAGE_ROOT/models/hf_cache/

The heavy stack (transformers + torch) is OPTIONAL. If unavailable, each
detector returns `None` and the pipeline falls back to the lightweight
statistical score from `core.styles.stats.ai_detection_score`.

Final aggregator combines available signals into a 0..1 ai_detection score
where 1.0 = "very AI-like".
"""

from __future__ import annotations

import logging
import math
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

_DEVICE = "cpu"
_MAX_TOKENS = 512  # truncate long inputs for speed

_CACHE_DIR = os.path.join(os.getenv("STORAGE_ROOT", "/data"), "models", "hf_cache")
try:
    os.makedirs(_CACHE_DIR, exist_ok=True)
except OSError:
    pass
os.environ.setdefault("HF_HOME", _CACHE_DIR)
os.environ.setdefault("TRANSFORMERS_CACHE", _CACHE_DIR)

# -----------------------------------------------------------------------------
# Lazy loaders
# -----------------------------------------------------------------------------

_LOCK = threading.Lock()
_LOADED: Dict[str, Any] = {}


def _try_import_torch():
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _load_gpt2_pair():
    """Two GPT-2 models for Binoculars: observer (smaller) + performer (larger)."""
    if "gpt2_pair" in _LOADED:
        return _LOADED["gpt2_pair"]
    if not _try_import_torch():
        _LOADED["gpt2_pair"] = None
        return None
    with _LOCK:
        if "gpt2_pair" in _LOADED:
            return _LOADED["gpt2_pair"]
        try:
            from transformers import GPT2LMHeadModel, GPT2TokenizerFast
            tok = GPT2TokenizerFast.from_pretrained("gpt2", cache_dir=_CACHE_DIR)
            obs = GPT2LMHeadModel.from_pretrained("gpt2", cache_dir=_CACHE_DIR).eval()
            # "performer" — slightly larger if memory allows; fall back to gpt2
            try:
                perf = GPT2LMHeadModel.from_pretrained(
                    "gpt2-medium", cache_dir=_CACHE_DIR
                ).eval()
            except Exception as e:
                logger.warning("gpt2-medium unavailable, using gpt2 for both: %s", e)
                perf = obs
            _LOADED["gpt2_pair"] = (tok, obs, perf)
            logger.info("✓ Loaded GPT-2 pair for Binoculars detector")
        except Exception as e:
            logger.warning("Could not load GPT-2 pair: %s", e)
            _LOADED["gpt2_pair"] = None
        return _LOADED["gpt2_pair"]


def _load_roberta_detector():
    if "roberta" in _LOADED:
        return _LOADED["roberta"]
    if not _try_import_torch():
        _LOADED["roberta"] = None
        return None
    with _LOCK:
        if "roberta" in _LOADED:
            return _LOADED["roberta"]
        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
            )
            name = "roberta-base-openai-detector"
            tok = AutoTokenizer.from_pretrained(name, cache_dir=_CACHE_DIR)
            mdl = AutoModelForSequenceClassification.from_pretrained(
                name, cache_dir=_CACHE_DIR
            ).eval()
            _LOADED["roberta"] = (tok, mdl)
            logger.info("✓ Loaded roberta-base-openai-detector")
        except Exception as e:
            logger.warning("Could not load roberta-base-openai-detector: %s", e)
            _LOADED["roberta"] = None
        return _LOADED["roberta"]


# -----------------------------------------------------------------------------
# Binoculars-style perplexity ratio
# -----------------------------------------------------------------------------

def binoculars_ratio(text: str) -> Optional[float]:
    """
    Returns observer_perplexity / performer_cross_perplexity.
    Lower ratio → more AI-like. None if models unavailable.
    """
    pair = _load_gpt2_pair()
    if not pair:
        return None
    try:
        import torch
        tok, obs, perf = pair
        ids = tok(
            text or "", return_tensors="pt", truncation=True, max_length=_MAX_TOKENS
        ).input_ids.to(_DEVICE)
        if ids.shape[1] < 8:
            return None
        with torch.no_grad():
            obs_loss = obs(ids, labels=ids).loss.item()
            perf_loss = perf(ids, labels=ids).loss.item()
        # Convert losses to perplexities; use cross-perplexity proxy
        obs_ppl  = math.exp(min(obs_loss, 12))
        perf_ppl = math.exp(min(perf_loss, 12))
        if perf_ppl <= 0:
            return None
        return obs_ppl / perf_ppl
    except Exception as e:
        logger.warning("binoculars_ratio failed: %s", e)
        return None


# -----------------------------------------------------------------------------
# GLTR top-K rank histogram
# -----------------------------------------------------------------------------

def gltr_score(text: str) -> Optional[Dict[str, float]]:
    """
    Returns {top1_pct, top10_pct, top100_pct, ai_score}.
    Higher top1_pct → more AI-like. None if model unavailable.
    """
    pair = _load_gpt2_pair()
    if not pair:
        return None
    try:
        import torch
        tok, obs, _perf = pair
        ids = tok(
            text or "", return_tensors="pt", truncation=True, max_length=_MAX_TOKENS
        ).input_ids.to(_DEVICE)
        if ids.shape[1] < 8:
            return None
        with torch.no_grad():
            logits = obs(ids).logits  # [1, T, V]
        # For each predicted token (shifted), find the rank of the actual token
        shift_logits = logits[:, :-1, :]
        shift_targets = ids[:, 1:]
        # rank = number of tokens with higher logit than the actual one
        gathered = shift_logits.gather(2, shift_targets.unsqueeze(-1)).squeeze(-1)
        ranks = (shift_logits > gathered.unsqueeze(-1)).sum(dim=-1)  # [1, T-1]
        ranks = ranks.flatten().tolist()
        n = max(1, len(ranks))
        t1   = sum(1 for r in ranks if r < 1)   / n
        t10  = sum(1 for r in ranks if r < 10)  / n
        t100 = sum(1 for r in ranks if r < 100) / n

        # Compose ai_score: heavy weight on top-10
        ai_score = max(0.0, min(1.0, 0.2 * t1 + 0.6 * t10 + 0.2 * t100))
        return {
            "top1_pct":   round(t1, 3),
            "top10_pct":  round(t10, 3),
            "top100_pct": round(t100, 3),
            "ai_score":   round(ai_score, 3),
        }
    except Exception as e:
        logger.warning("gltr_score failed: %s", e)
        return None


# -----------------------------------------------------------------------------
# Roberta detector
# -----------------------------------------------------------------------------

def roberta_score(text: str) -> Optional[float]:
    """
    Returns p(AI-generated) ∈ [0,1] from roberta-base-openai-detector.
    None if model unavailable.
    """
    rb = _load_roberta_detector()
    if not rb:
        return None
    try:
        import torch
        tok, mdl = rb
        ids = tok(
            text or "", return_tensors="pt", truncation=True, max_length=_MAX_TOKENS
        ).to(_DEVICE)
        with torch.no_grad():
            logits = mdl(**ids).logits
            probs = torch.softmax(logits, dim=-1).squeeze().tolist()
        # roberta-base-openai-detector: label 0=Real, 1=Fake (AI-generated)
        if isinstance(probs, list) and len(probs) >= 2:
            return float(probs[1])
        return None
    except Exception as e:
        logger.warning("roberta_score failed: %s", e)
        return None


# -----------------------------------------------------------------------------
# Aggregator
# -----------------------------------------------------------------------------

def ensemble(text: str) -> Dict[str, Any]:
    """
    Run available detectors, plus the always-on lightweight stats score, and
    aggregate into a single 0..1 ai_detection probability + per-detector
    diagnostics.
    """
    from core.styles.stats import ai_detection_score
    light = ai_detection_score(text or "")

    bino = binoculars_ratio(text or "")        # higher = more human
    gltr = gltr_score(text or "")              # ai_score: higher = more AI
    rob  = roberta_score(text or "")           # higher = more AI

    components: Dict[str, float] = {"stats": light["score"]}

    bino_ai: Optional[float] = None
    if bino is not None:
        # Map ratio ∈ (0, ~3+) to AI-likelihood.
        # Heuristic: ratio ≥ 1.0 → human-like (≤0.4); ratio < 0.7 → AI (≥0.6).
        # Smooth with logistic.
        x = (1.0 - bino)
        bino_ai = 1.0 / (1.0 + math.exp(-4.0 * x))
        components["binoculars"] = round(bino_ai, 3)

    if gltr is not None:
        components["gltr"] = gltr["ai_score"]

    if rob is not None:
        components["roberta"] = round(rob, 3)

    # Weighted average — prefer heavy detectors when available
    weights = {"stats": 0.30, "binoculars": 0.25, "gltr": 0.20, "roberta": 0.25}
    used_weight = 0.0
    weighted_sum = 0.0
    for k, v in components.items():
        w = weights.get(k, 0.0)
        used_weight += w
        weighted_sum += w * v
    score = weighted_sum / used_weight if used_weight > 0 else light["score"]

    return {
        "ai_detection":     round(score, 3),
        "components":       components,
        "binoculars_ratio": bino,
        "gltr":             gltr,
        "roberta_p_ai":     rob,
        "light":            light,
    }
