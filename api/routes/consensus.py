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

from api.dependencies import get_current_user, get_user_api_keys
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

def _resolve_api_key(provider: str, api_keys: dict) -> str | None:
    """Pull the right API key from the resolved api_keys dict for a given provider."""
    key_map = {
        "anthropic":      api_keys.get("claude") or api_keys.get("anthropic"),
        "openai":         api_keys.get("openai"),
        "openrouter":     api_keys.get("openrouter"),
        "vercel_gateway": api_keys.get("vercel_gateway"),
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
    api_keys: dict = Depends(get_user_api_keys),
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
        api_key = m.api_key or _resolve_api_key(m.provider, api_keys)
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
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Return all available models grouped by provider, exactly like GET /chat/models.
    The frontend uses user_has_keys to decide which rows are selectable.
    """
    try:
        from core.llm import get_registry

        registry = get_registry(api_keys)

        # Refresh OpenRouter live model list if the user has a key
        if api_keys.get("openrouter"):
            try:
                or_provider = registry.get_provider("openrouter")
                if or_provider and hasattr(or_provider, "refresh_models"):
                    await or_provider.refresh_models()
            except Exception:
                pass

        models_by_provider = registry.list_models()

        user_has_keys = {
            "anthropic":      bool(api_keys.get("claude")),
            "openai":         bool(api_keys.get("openai")),
            "openrouter":     bool(api_keys.get("openrouter")),
            "vercel_gateway": bool(api_keys.get("vercel_gateway")),
        }

    except Exception as exc:
        logger.error(f"consensus_models: registry failed — {exc}", exc_info=True)
        # Graceful fallback: return static Claude list so UI is never blank
        models_by_provider = {
            "anthropic": [
                "claude-opus-4-6",
                "claude-sonnet-4-6",
                "claude-opus-4-5",
                "claude-sonnet-4-5",
            ]
        }
        user_has_keys = {
            "anthropic":      bool(api_keys.get("claude")),
            "openai":         False,
            "openrouter":     False,
            "vercel_gateway": False,
        }

    return JSONResponse(content={
        "models":        models_by_provider,
        "user_has_keys": user_has_keys,
    })
