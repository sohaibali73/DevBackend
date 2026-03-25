"""
OpenRouter Provider
===================
OpenRouter provides unified API access to 300+ models (Llama, Mistral,
Gemini, Claude, GPT, DeepSeek, etc.) through a single OpenAI-compatible
endpoint.

This provider extends OpenAIProvider since OpenRouter uses the same API format.
The only differences are:
  - Different base_url
  - Extra headers for attribution
  - Full model list fetched dynamically from GET /v1/models at startup

Dynamic model fetching
----------------------
Call ``await provider.refresh_models()`` once at startup (or from the
/chat/models endpoint) to populate the full 300+ model list.  Until then,
a comprehensive static fallback list ensures the selector is never empty.
"""

import os
import logging
from typing import List

from core.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Comprehensive static fallback — covers the most popular ~100 models.
# This is shown immediately before the async refresh completes.
# ---------------------------------------------------------------------------

OPENROUTER_MODELS_FALLBACK: List[str] = [
    # ── Meta Llama ──────────────────────────────────────────────────────────
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-405b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3-70b-instruct",
    "meta-llama/llama-3-8b-instruct",
    "meta-llama/codellama-70b-instruct",
    # ── Mistral / Codestral ─────────────────────────────────────────────────
    "mistralai/mistral-large",
    "mistralai/mistral-medium",
    "mistralai/mistral-small",
    "mistralai/mistral-7b-instruct",
    "mistralai/mixtral-8x7b-instruct",
    "mistralai/mixtral-8x22b-instruct",
    "mistralai/codestral",
    "mistralai/codestral-mamba",
    "mistralai/pixtral-12b",
    "mistralai/pixtral-large",
    # ── Google Gemini ───────────────────────────────────────────────────────
    "google/gemini-2.5-pro-preview",
    "google/gemini-2.5-flash-preview",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.0-flash-thinking-exp",
    "google/gemini-pro-1.5",
    "google/gemini-flash-1.5",
    "google/gemini-flash-1.5-8b",
    # ── Anthropic via OpenRouter ─────────────────────────────────────────────
    "anthropic/claude-opus-4",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-3.7-sonnet",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3-opus",
    "anthropic/claude-3-sonnet",
    "anthropic/claude-3-haiku",
    # ── OpenAI via OpenRouter ────────────────────────────────────────────────
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo",
    "openai/gpt-4",
    "openai/gpt-3.5-turbo",
    "openai/o1",
    "openai/o1-mini",
    "openai/o1-preview",
    "openai/o3",
    "openai/o3-mini",
    # ── xAI Grok ───────────────────────────────────────────────────────────
    "x-ai/grok-3",
    "x-ai/grok-3-mini",
    "x-ai/grok-2-1212",
    "x-ai/grok-2-vision-1212",
    "x-ai/grok-beta",
    # ── DeepSeek ───────────────────────────────────────────────────────────
    "deepseek/deepseek-chat-v3",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-r1-zero",
    "deepseek/deepseek-coder",
    "deepseek/deepseek-r1-distill-llama-70b",
    "deepseek/deepseek-r1-distill-qwen-32b",
    # ── Qwen / Alibaba ─────────────────────────────────────────────────────
    "qwen/qwen-2.5-72b-instruct",
    "qwen/qwen-2.5-coder-32b-instruct",
    "qwen/qwen-2-vl-72b-instruct",
    "qwen/qwq-32b-preview",
    "qwen/qwen-max",
    # ── Cohere ─────────────────────────────────────────────────────────────
    "cohere/command-r-plus",
    "cohere/command-r",
    "cohere/command-r-plus-08-2024",
    "cohere/command-r-08-2024",
    # ── Perplexity ─────────────────────────────────────────────────────────
    "perplexity/sonar-pro",
    "perplexity/sonar",
    "perplexity/sonar-reasoning",
    "perplexity/llama-3.1-sonar-large-128k-online",
    # ── 01.AI ──────────────────────────────────────────────────────────────
    "01-ai/yi-large",
    "01-ai/yi-vision",
    # ── NovaSky / Berkeley ─────────────────────────────────────────────────
    "nousresearch/hermes-3-llama-3.1-405b",
    "nousresearch/nous-hermes-2-mixtral-8x7b-dpo",
    # ── Microsoft Phi ──────────────────────────────────────────────────────
    "microsoft/phi-4",
    "microsoft/phi-3.5-mini-128k-instruct",
    "microsoft/phi-3-medium-128k-instruct",
    "microsoft/wizardlm-2-8x22b",
    # ── Amazon Nova ────────────────────────────────────────────────────────
    "amazon/nova-pro-v1",
    "amazon/nova-lite-v1",
    "amazon/nova-micro-v1",
    # ── Nvidia ─────────────────────────────────────────────────────────────
    "nvidia/llama-3.1-nemotron-70b-instruct",
    # ── Together AI ────────────────────────────────────────────────────────
    "togethercomputer/stripedhyena-nous-7b",
]


class OpenRouterProvider(OpenAIProvider):
    """
    OpenRouter provider — extends OpenAIProvider.

    Supports 300+ models. On first call to refresh_models() the full list is
    fetched live from OpenRouter's /v1/models endpoint and cached.
    """

    # Class-level cache shared across instances for the same API key session
    _cached_models: List[str] = []

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        self._api_key = api_key

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def supported_models(self) -> List[str]:
        # Return the dynamically-fetched list if available, else the fallback
        return (
            OpenRouterProvider._cached_models
            if OpenRouterProvider._cached_models
            else list(OPENROUTER_MODELS_FALLBACK)
        )

    async def refresh_models(self) -> List[str]:
        """
        Fetch the full model list from OpenRouter's /v1/models endpoint.

        OpenRouter returns all ~300+ models it currently supports.
        The result is cached at the class level so subsequent calls are instant.

        Returns:
            List of model IDs (e.g. "meta-llama/llama-3.1-405b-instruct").
        """
        try:
            response = await self._client.models.list()
            models = [
                m.id for m in response.data
                if getattr(m, "id", None)
            ]
            if models:
                # Sort by provider prefix then model name for clean display
                models_sorted = sorted(models, key=lambda m: (
                    m.split("/")[0] if "/" in m else "zzz",
                    m
                ))
                OpenRouterProvider._cached_models = models_sorted
                logger.info(
                    "OpenRouter: fetched %d models dynamically", len(models_sorted)
                )
                return models_sorted
        except Exception as e:
            logger.warning(
                "OpenRouter dynamic model fetch failed (using static fallback): %s", e
            )
        return list(OPENROUTER_MODELS_FALLBACK)

    def _get_extra_headers(self) -> dict:
        """OpenRouter requires attribution headers."""
        return {
            "HTTP-Referer": os.getenv("FRONTEND_URL", "https://potomac.ai"),
            "X-Title": "Analyst by Potomac",
        }

    async def validate_connection(self) -> bool:
        """Verify API key and pre-populate model list."""
        try:
            await self.refresh_models()
            return True
        except Exception as e:
            logger.warning("OpenRouter connection validation failed: %s", e)
            return False
