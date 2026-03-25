"""
Vercel AI Gateway Provider
==========================
Vercel AI Gateway provides access to models from all major providers
through a single OpenAI-compatible endpoint with one API key.

Base URL:  https://ai-gateway.vercel.sh/v1
API Key:   AI_GATEWAY_API_KEY  (single Vercel key)
Model IDs: "provider/model-id" format  (e.g. "anthropic/claude-3-7-sonnet-20250219")

Supported provider prefixes:
  anthropic, openai, google, meta-llama, mistral, x-ai, deepseek,
  cohere, amazon, perplexity, together

Full model list: https://sdk.vercel.ai/providers/ai-sdk-providers/gateway
"""

import logging
from typing import List

from core.llm.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

VERCEL_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

# ---------------------------------------------------------------------------
# Comprehensive Vercel AI Gateway model list.
# Format: "provider/model-id"  (exactly as the gateway expects it)
# Source: https://sdk.vercel.ai/providers/ai-sdk-providers/gateway
# ---------------------------------------------------------------------------

VERCEL_GATEWAY_MODELS: List[str] = [

    # ── Anthropic ────────────────────────────────────────────────────────────
    "anthropic/claude-opus-4-5",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-3-7-sonnet-20250219",
    "anthropic/claude-3-7-sonnet-latest",
    "anthropic/claude-3-5-sonnet-20241022",
    "anthropic/claude-3-5-sonnet-latest",
    "anthropic/claude-3-5-haiku-20241022",
    "anthropic/claude-3-5-haiku-latest",
    "anthropic/claude-3-opus-20240229",
    "anthropic/claude-3-sonnet-20240229",
    "anthropic/claude-3-haiku-20240307",

    # ── OpenAI ───────────────────────────────────────────────────────────────
    "openai/gpt-4o-2024-11-20",
    "openai/gpt-4o-2024-08-06",
    "openai/gpt-4o",
    "openai/gpt-4o-mini-2024-07-18",
    "openai/gpt-4o-mini",
    "openai/gpt-4-turbo-2024-04-09",
    "openai/gpt-4-turbo",
    "openai/gpt-4",
    "openai/gpt-3.5-turbo-0125",
    "openai/gpt-3.5-turbo",
    "openai/o1-2024-12-17",
    "openai/o1",
    "openai/o1-mini-2024-09-12",
    "openai/o1-mini",
    "openai/o1-preview-2024-09-12",
    "openai/o1-preview",
    "openai/o3",
    "openai/o3-mini",
    "openai/o4-mini",

    # ── Google Gemini ─────────────────────────────────────────────────────────
    "google/gemini-2.5-pro-preview-05-06",
    "google/gemini-2.5-pro-exp-03-25",
    "google/gemini-2.5-flash-preview-04-17",
    "google/gemini-2.5-flash-preview",
    "google/gemini-2.0-flash-001",
    "google/gemini-2.0-flash",
    "google/gemini-2.0-flash-lite-001",
    "google/gemini-2.0-flash-thinking-exp-01-21",
    "google/gemini-1.5-pro-002",
    "google/gemini-1.5-pro",
    "google/gemini-1.5-flash-002",
    "google/gemini-1.5-flash",
    "google/gemini-1.5-flash-8b",

    # ── Meta Llama ────────────────────────────────────────────────────────────
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-405b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3-70b-instruct",
    "meta-llama/llama-3-8b-instruct",

    # ── Mistral ───────────────────────────────────────────────────────────────
    "mistral/mistral-large-2411",
    "mistral/mistral-large-latest",
    "mistral/mistral-small-2501",
    "mistral/mistral-small-latest",
    "mistral/mistral-saba-latest",
    "mistral/codestral-2501",
    "mistral/codestral-latest",
    "mistral/pixtral-large-2411",
    "mistral/mistral-7b-instruct-v0.3",
    "mistral/mixtral-8x7b-instruct-v0.1",
    "mistral/mixtral-8x22b-instruct-v0.1",

    # ── xAI Grok ─────────────────────────────────────────────────────────────
    "x-ai/grok-3-beta",
    "x-ai/grok-3-fast-beta",
    "x-ai/grok-3-mini-beta",
    "x-ai/grok-3-mini-fast-beta",
    "x-ai/grok-2-1212",
    "x-ai/grok-2-vision-1212",
    "x-ai/grok-beta",

    # ── DeepSeek ─────────────────────────────────────────────────────────────
    "deepseek/deepseek-chat",
    "deepseek/deepseek-reasoner",

    # ── Cohere ───────────────────────────────────────────────────────────────
    "cohere/command-r-plus-08-2024",
    "cohere/command-r-plus",
    "cohere/command-r-08-2024",
    "cohere/command-r",

    # ── Amazon Bedrock (via Gateway) ─────────────────────────────────────────
    "amazon/nova-pro-v1:0",
    "amazon/nova-lite-v1:0",
    "amazon/nova-micro-v1:0",
    "amazon/titan-text-express-v1",

    # ── Perplexity ────────────────────────────────────────────────────────────
    "perplexity/sonar-pro",
    "perplexity/sonar",
    "perplexity/sonar-reasoning",
    "perplexity/sonar-reasoning-pro",

    # ── Together AI ───────────────────────────────────────────────────────────
    "together/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
    "together/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
    "together/mistralai/Mixtral-8x7B-Instruct-v0.1",

    # ── Groq ─────────────────────────────────────────────────────────────────
    "groq/llama-3.3-70b-versatile",
    "groq/llama-3.1-70b-versatile",
    "groq/llama-3.1-8b-instant",
    "groq/mixtral-8x7b-32768",
    "groq/gemma2-9b-it",
]


class VercelGatewayProvider(OpenAIProvider):
    """
    Vercel AI Gateway provider.

    Uses a single Vercel API key to access 100+ models from all major
    providers. Extends OpenAIProvider since the gateway uses the
    OpenAI-compatible API format.
    """

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url=VERCEL_GATEWAY_BASE_URL)

    @property
    def provider_name(self) -> str:
        return "vercel_gateway"

    @property
    def supported_models(self) -> List[str]:
        return list(VERCEL_GATEWAY_MODELS)
