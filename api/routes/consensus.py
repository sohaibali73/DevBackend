"""
consensus.py
=============
POST /consensus/validate  — run a prompt through multiple models and
                            return a scored consensus result.
GET  /consensus/models    — list models available for consensus (subset
                            of /chat/models filtered to providers the
                            user has API keys for).
"""

from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from core.consensus_engine import run_consensus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consensus", tags=["consensus"])

# ─── request / response models ────────────────────────────────────────────────

class ConsensusModelConfig(BaseModel):
    model_id:  str
    provider:  str
    api_key:   str | None = None   # overrides user profile key when provided

class ConsensusMessage(BaseModel):
    role:    str   # "user" | "assistant" | "system"
    content: str

class ConsensusRequest(BaseModel):
    messages:           list[ConsensusMessage]
    models:             list[ConsensusModelConfig] = Field(min_length=2, max_length=8)
    max_tokens:         int   = Field(default=1024, ge=64, le=4096)
    majority_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _resolve_api_key(provider: str, user: dict | None) -> str | None:
    """Pull the right API key from the user profile for a given provider."""
    if not user:
        return None
    key_map = {
        "anthropic":      user.get("claude_api_key")      or user.get("anthropic_api_key"),
        "openai":         user.get("openai_api_key"),
        "openrouter":     user.get("openrouter_api_key"),
        "vercel_gateway": user.get("vercel_gateway_api_key"),
    }
    return key_map.get(provider)


def _get_registry():
    """Lazy import to avoid circular deps."""
    try:
        from core.llm.registry import LLMProviderRegistry
        return LLMProviderRegistry.get_instance()
    except Exception as e:
        logger.error(f"Failed to load LLM registry: {e}")
        return None

# ─── routes ───────────────────────────────────────────────────────────────────

@router.post("/validate")
async def consensus_validate(
    body: ConsensusRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Run the provided messages through all listed models in parallel.
    Returns a ConsensusResult with scores, per-model responses, and
    a synthesised answer.
    """
    registry = _get_registry()
    if not registry:
        raise HTTPException(status_code=503, detail="LLM registry unavailable")

    # Build model configs, injecting user API keys where not explicitly provided
    model_configs: list[dict[str, Any]] = []
    for m in body.models:
        api_key = m.api_key or _resolve_api_key(m.provider, current_user)
        if not api_key:
            logger.warning(f"No API key for provider={m.provider}, model={m.model_id} — skipping")
            continue
        model_configs.append({
            "model_id": m.model_id,
            "provider": m.provider,
            "api_key":  api_key,
        })

    if len(model_configs) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 models with valid API keys are required for consensus."
        )

    messages = [{"role": msg.role, "content": msg.content} for msg in body.messages]

    try:
        result = await run_consensus(
            registry=registry,
            model_configs=model_configs,
            messages=messages,
            max_tokens=body.max_tokens,
            majority_threshold=body.majority_threshold,
        )
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Consensus validation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Consensus failed: {str(e)}")


@router.get("/models")
async def consensus_models(
    current_user: dict = Depends(get_current_user),
):
    """
    Return the subset of models the user can actually use for consensus
    (i.e. they have API keys configured for those providers).
    """
    try:
        from api.routes.chat import _get_available_models
        models_by_provider, user_has_keys = await _get_available_models(current_user)
    except Exception:
        # Fallback: return empty
        models_by_provider = {}
        user_has_keys = {}

    # Only include providers where the user has a key
    consensus_models: dict[str, list[str]] = {
        p: lst for p, lst in models_by_provider.items()
        if user_has_keys.get(p, False)
    }

    return JSONResponse(content={
        "models":        consensus_models,
        "user_has_keys": user_has_keys,
    })
