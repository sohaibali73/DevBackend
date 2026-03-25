"""
LLM Provider Registry
=====================
Central registry that maps model strings to provider instances.

Model string formats:
  - "claude-sonnet-4-6"              → AnthropicProvider
  - "gpt-4o"                         → OpenAIProvider
  - "meta-llama/llama-3.1-405b"      → OpenRouterProvider
  - "anthropic/claude-3.5-sonnet"    → OpenRouterProvider (if registered)

The registry is created once per process (via get_registry() in __init__.py)
and reused across all requests.
"""

import logging
from typing import Dict, List, Optional

from core.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """
    Maps model identifiers to their provider instances.

    Providers register themselves with a list of supported models.
    When a model is requested, the registry looks up which provider handles it.
    """

    def __init__(self):
        self._providers: Dict[str, BaseLLMProvider] = {}
        # model_id → provider_name (exact match)
        self._model_map: Dict[str, str] = {}
        # provider_name → list of model prefixes for prefix matching
        self._prefix_map: Dict[str, List[str]] = {}
        self._default_provider: str = "anthropic"

    def register_provider(self, name: str, provider: BaseLLMProvider) -> None:
        """
        Register a provider and index its supported models.

        Args:
            name: Provider identifier (e.g. "anthropic", "openai").
            provider: The provider instance.
        """
        self._providers[name] = provider

        # Index all supported models for exact lookup
        for model in provider.supported_models:
            self._model_map[model] = name

        # Build prefix list for fallback matching
        # e.g. "claude-" → "anthropic", "gpt-" → "openai"
        prefixes = set()
        for model in provider.supported_models:
            # Use the first segment before "/" or "-" as prefix
            if "/" in model:
                prefixes.add(model.split("/")[0] + "/")
            elif "-" in model:
                prefixes.add(model.split("-")[0] + "-")
        self._prefix_map[name] = list(prefixes)

        logger.info(
            "Registered provider '%s' with %d models",
            name, len(provider.supported_models),
        )

    def get_provider_for_model(self, model: str) -> BaseLLMProvider:
        """
        Resolve a model string to its provider instance.

        Lookup order:
        1. Exact match in _model_map
        2. Prefix match (e.g. "claude-anything" → anthropic)
        3. Fall back to default provider

        Args:
            model: Model identifier string.

        Returns:
            The BaseLLMProvider that handles this model.

        Raises:
            ValueError: If no providers are registered at all.
        """
        if not self._providers:
            raise ValueError(
                "No LLM providers registered. "
                "Make sure at least one API key is configured."
            )

        # 1. Exact match
        provider_name = self._model_map.get(model)
        if provider_name and provider_name in self._providers:
            return self._providers[provider_name]

        # 2. Prefix match — check each provider's prefixes
        for pname, prefixes in self._prefix_map.items():
            if pname in self._providers:
                for prefix in prefixes:
                    if model.startswith(prefix):
                        logger.debug(
                            "Model '%s' matched prefix '%s' → provider '%s'",
                            model, prefix, pname,
                        )
                        return self._providers[pname]

        # 3. Fallback to default
        if self._default_provider in self._providers:
            logger.warning(
                "No exact or prefix match for model '%s', "
                "falling back to default provider '%s'",
                model, self._default_provider,
            )
            return self._providers[self._default_provider]

        # 4. Last resort: return the first available provider
        first = next(iter(self._providers.values()))
        logger.warning(
            "No match for model '%s' and default provider unavailable, "
            "using first available: '%s'",
            model, first.provider_name,
        )
        return first

    def get_provider(self, name: str) -> Optional[BaseLLMProvider]:
        """
        Get a provider by its name.

        Args:
            name: Provider identifier (e.g. "anthropic").

        Returns:
            The provider instance, or None if not registered.
        """
        return self._providers.get(name)

    def list_models(self) -> Dict[str, List[str]]:
        """
        List all available models grouped by provider.

        Returns:
            Dict mapping provider names to their model lists.
            e.g. {"anthropic": ["claude-opus-4-6", ...], "openai": ["gpt-4o", ...]}
        """
        result = {}
        for name, provider in self._providers.items():
            result[name] = provider.supported_models
        return result

    def list_providers(self) -> List[str]:
        """List registered provider names."""
        return list(self._providers.keys())

    def has_provider(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers

    @property
    def default_provider(self) -> str:
        """Get the default provider name."""
        return self._default_provider

    @default_provider.setter
    def default_provider(self, name: str) -> None:
        """Set the default provider (used when model string doesn't match)."""
        self._default_provider = name

    def __repr__(self) -> str:
        providers = ", ".join(self._providers.keys())
        model_count = len(self._model_map)
        return (
            f"<LLMProviderRegistry providers=[{providers}] "
            f"models={model_count} default={self._default_provider}>"
        )