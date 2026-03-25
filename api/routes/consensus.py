"""
consensus.py
=============
POST /consensus/validate  — run a prompt through multiple models and
                            return a scored consensus result.
GET  /consensus/models    — list models available for consensus based
                            on which server-side API keys are configured.

Uses server-side API keys from environment variables (Settings) so the
feature works without users needing to configure their own keys.
"""

from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_id
from config import get_settings
from core.consensus_engine import run_consensus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consensus", tags=["consensus"])

# ─── request / response models ────────────────────────────────────────────────

class ConsensusModelConfig(BaseModel):
    model_id: str
    provider: str
    api_key:  str | None = None   # optional per-request override

class ConsensusMessage(BaseModel):
    role:    str   # "user" | "assistant" | "system"
    content: str

class ConsensusRequest(BaseModel):
    messages:           list[ConsensusMessage]
    models:             list[ConsensusModelConfig] = Field(min_length=2, max_length=8)
    max_tokens:         int   = Field(default=1024, ge=64, le=4096)
    majority_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

# ─── helpers ──────────────────────────────────────────────────────────────────

def _server_api_keys() -> dict[str, str]:
    """Return server-side API keys from environment settings."""
    s = get_settings()
    return {
        "anthropic":      s.anthropic_api_key      or "",
        "openai":         s.openai_api_key          or "",
        "openrouter":     s.openrouter_api_key      or "",
        "vercel_gateway": s.vercel_gateway_api_key  or "",
    }


def _resolve_key(provider: str, override: str | None = None) -> str:
    """Return API key for provider: explicit override > server-side env key."""
    if override:
        return override
    return _server_api_keys().get(provider, "")


def _get_registry():
    """Lazy import to avoid circular deps."""
    try:
        from core.llm.registry import LLMProviderRegistry
        return LLMProviderRegistry.get_instance()
    except Exception as e:
        logger.error(f"Failed to load LLM registry: {e}")
        return None


# Static fallback model lists per provider — shown when registry is unavailable
_FALLBACK_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-opus-4-5",
        "claude-sonnet-4-5",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1",
        "o1-mini",
        "o3-mini",
    ],
    "openrouter": [
        "openai/gpt-4o",
        "anthropic/claude-opus-4-6",
        "google/gemini-pro-1.5",
        "meta-llama/llama-3.1-70b-instruct",
    ],
}

# ─── routes ───────────────────────────────────────────────────────────────────

@router.post("/validate")
async def consensus_validate(
    body: ConsensusRequest,
    _user_id: str = Depends(get_current_user_id),   # auth check only
):
    """
    Run the provided messages through all listed models in parallel.
    Uses server-side API keys from environment variables.
    Returns a ConsensusResult with scores, per-model responses, and
    a synthesised answer.
    """
    registry = _get_registry()
    if not registry:
        raise HTTPException(status_code=503, detail="LLM registry unavailable")

    # Build model configs using server-side keys
    model_configs: list[dict[str, Any]] = []
    for m in body.models:
        api_key = _resolve_key(m.provider, m.api_key)
        if not api_key:
            logger.warning(
                f"No server-side API key for provider={m.provider}, "
                f"model={m.model_id} — skipping"
            )
            continue
        model_configs.append({
            "model_id": m.model_id,
            "provider": m.provider,
            "api_key":  api_key,
        })

    if len(model_configs) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least 2 models with valid API keys are required. "
                "Ensure the server has ANTHROPIC_API_KEY (and optionally "
                "OPENAI_API_KEY / OPENROUTER_API_KEY) set."
            ),
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
    _user_id: str = Depends(get_current_user_id),   # auth check only
):
    """
    Return all models available for consensus, grouped by provider.
    A provider is considered "unlocked" (selectable) if the server has
    the corresponding API key set in environment variables.
    """
    server_keys = _server_api_keys()
    user_has_keys = {
        provider: bool(key)
        for provider, key in server_keys.items()
    }

    # Try to get the full live model list from the registry
    try:
        from core.llm import get_registry

        # Build a minimal api_keys dict so the registry initialises properly
        api_keys_for_registry = {
            "claude":         server_keys["anthropic"],
            "openai":         server_keys["openai"],
            "openrouter":     server_keys["openrouter"],
            "vercel_gateway": server_keys["vercel_gateway"],
        }
        registry = get_registry(api_keys_for_registry)

        # Refresh OpenRouter live models if key is present
        if server_keys.get("openrouter"):
            try:
                or_provider = registry.get_provider("openrouter")
                if or_provider and hasattr(or_provider, "refresh_models"):
                    await or_provider.refresh_models()
            except Exception:
                pass

        models_by_provider: dict[str, list[str]] = registry.list_models()

    except Exception as exc:
        logger.warning(f"consensus_models: registry unavailable ({exc}), using fallback list")
        # Graceful fallback: static lists for each unlocked provider
        models_by_provider = {
            provider: _FALLBACK_MODELS.get(provider, [])
            for provider, has_key in user_has_keys.items()
            if has_key and _FALLBACK_MODELS.get(provider)
        }

    return JSONResponse(content={
        "models":        models_by_provider,
        "user_has_keys": user_has_keys,
    })
