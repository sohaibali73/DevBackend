"""
LLM Provider Package
====================
Multi-provider support for Yang. Allows using Anthropic, OpenAI, OpenRouter,
Vercel AI Gateway, and other providers through a unified interface.

Usage:
    from core.llm import get_registry, get_provider_for_model
    
    registry = get_registry(api_keys)
    provider = get_provider_for_model("gpt-4o", api_keys)
    
    # Stream a response
    async for chunk in provider.stream_chat(messages, model="gpt-4o"):
        print(chunk)

The Anthropic provider wraps existing ClaudeAFLEngine code — zero breaking changes.
"""

from core.llm.base import BaseLLMProvider, LLMResponse, StreamChunk
from core.llm.registry import LLMProviderRegistry

# Singleton registry — initialized once per process when get_registry() is called
_registry: "LLMProviderRegistry | None" = None
_registry_keys_hash: str = ""


def get_registry(api_keys: dict) -> LLMProviderRegistry:
    """
    Get or create the singleton provider registry, initializing providers
    from the provided API keys.

    Args:
        api_keys: Dict of provider keys, e.g.
                  {"claude": "sk-...", "openai": "sk-...", "openrouter": "sk-..."}

    Returns:
        LLMProviderRegistry with available providers registered.
    """
    global _registry, _registry_keys_hash

    # Rebuild registry if keys changed (e.g. user updated their keys mid-session)
    keys_hash = str(sorted(api_keys.items()))
    if _registry is not None and keys_hash == _registry_keys_hash:
        return _registry

    _registry = LLMProviderRegistry()
    _registry_keys_hash = keys_hash

    # Register Anthropic provider (always attempt — uses existing Claude code)
    if api_keys.get("claude"):
        try:
            from core.llm.anthropic_provider import AnthropicProvider
            _registry.register_provider(
                "anthropic", AnthropicProvider(api_keys["claude"])
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to register Anthropic provider: %s", e
            )

    # Register OpenAI provider
    if api_keys.get("openai"):
        try:
            from core.llm.openai_provider import OpenAIProvider
            _registry.register_provider(
                "openai", OpenAIProvider(api_keys["openai"])
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to register OpenAI provider: %s", e
            )

    # Register OpenRouter provider
    if api_keys.get("openrouter"):
        try:
            from core.llm.openrouter_provider import OpenRouterProvider
            _registry.register_provider(
                "openrouter", OpenRouterProvider(api_keys["openrouter"])
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to register OpenRouter provider: %s", e
            )

    return _registry


def get_provider_for_model(model: str, api_keys: dict) -> BaseLLMProvider:
    """
    Convenience function: get the right provider for a model string.

    Args:
        model: Model identifier, e.g. "claude-sonnet-4-6", "gpt-4o",
               "meta-llama/llama-3.1-405b-instruct"
        api_keys: Dict of provider keys.

    Returns:
        The BaseLLMProvider that handles this model.

    Raises:
        ValueError: If no provider is available for the model and no fallback exists.
    """
    registry = get_registry(api_keys)
    return registry.get_provider_for_model(model)


__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "StreamChunk",
    "LLMProviderRegistry",
    "get_registry",
    "get_provider_for_model",
]