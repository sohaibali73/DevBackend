"""
Vercel AI Gateway Provider
==========================
Vercel AI Gateway provides a unified API to access hundreds of models
through a single endpoint with one API key.

Uses OpenAI-compatible API format:
  Base URL: https://ai-gateway.vercel.sh/v1
  API Key: AI_GATEWAY_API_KEY (single key from Vercel)
  Models: provider/model format (e.g. "anthropic/claude-opus-4.6")

This provider extends OpenAIProvider since Vercel Gateway uses the
same API format as OpenAI.
"""

import os
import logging
from typing import List

from core.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

VERCEL_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

VERCEL_GATEWAY_MODELS = [
    "anthropic/claude-opus-4.6",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-5.4",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "xai/grok-4.1-fast-non-reasoning",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "meta/llama-4-maverick",
    "meta/llama-4-scout",
    "mistral/mistral-large",
    "deepseek/deepseek-chat-v3",
]


class VercelGatewayProvider(OpenAIProvider):
    """
    Vercel AI Gateway provider.
    Uses a single API key to access hundreds of models.
    Extends OpenAIProvider since the gateway uses OpenAI-compatible API format.
    """

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url=VERCEL_GATEWAY_BASE_URL)

    @property
    def provider_name(self) -> str:
        return "vercel_gateway"

    @property
    def supported_models(self) -> List[str]:
        return list(VERCEL_GATEWAY_MODELS)