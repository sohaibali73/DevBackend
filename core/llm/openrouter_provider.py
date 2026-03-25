"""
OpenRouter Provider
===================
OpenRouter provides unified API access to 100+ models (Llama, Mistral,
Gemini, Claude, GPT, etc.) through a single OpenAI-compatible endpoint.

This provider extends OpenAIProvider since OpenRouter uses the same API format.
The only differences are:
  - Different base_url
  - Extra headers for attribution
  - Different model list
"""

import os
import logging
from typing import List

from core.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common OpenRouter models (curated selection)
# ---------------------------------------------------------------------------

OPENROUTER_MODELS = [
    # Meta Llama
    "meta-llama/llama-3.1-405b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.3-70b-instruct",
    # Mistral
    "mistralai/mistral-large",
    "mistralai/mistral-medium",
    "mistralai/mistral-small",
    "mistralai/codestral",
    # Google
    "google/gemini-pro-1.5",
    "google/gemini-flash-1.5",
    # Anthropic via OpenRouter
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "anthropic/claude-3-haiku",
    # OpenAI via OpenRouter
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    # Others
    "deepseek/deepseek-chat",
    "deepseek/deepseek-coder",
    "qwen/qwen-2.5-72b-instruct",
    "cohere/command-r-plus",
    "01-ai/yi-large",
]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    """
    OpenRouter provider — extends OpenAIProvider.

    OpenRouter uses the same API format as OpenAI, so we inherit all
    streaming, chat, tool normalization, and message conversion logic.
    We only override:
      - provider_name
      - supported_models
      - base_url
      - extra headers
    """

    def __init__(self, api_key: str):
        # OpenRouter uses OpenAI-compatible API with a different base URL
        super().__init__(api_key=api_key, base_url=OPENROUTER_BASE_URL)
        # Store the key for header setup
        self._api_key = api_key

    @property
    def provider_name(self) -> str:
        return "openrouter"

    @property
    def supported_models(self) -> List[str]:
        return list(OPENROUTER_MODELS)

    def _get_extra_headers(self) -> dict:
        """
        OpenRouter requires extra headers for attribution and ranking.
        """
        return {
            "HTTP-Referer": os.getenv("FRONTEND_URL", "https://potomac.ai"),
            "X-Title": "Analyst by Potomac",
        }