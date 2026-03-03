"""LLM provider registry.

Manages the creation and retrieval of LLM provider instances based on
configuration. Supports dynamic provider registration.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Type

from hivecore.config.settings import LLMSettings
from hivecore.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Registry of available providers
_PROVIDER_REGISTRY: dict[str, Type[LLMProvider]] = {}


def register_provider(name: str, provider_class: Type[LLMProvider]) -> None:
    """Register an LLM provider class.

    Args:
        name: Provider name (e.g., 'litellm', 'ollama').
        provider_class: The provider class to register.
    """
    _PROVIDER_REGISTRY[name.lower()] = provider_class
    logger.debug("Registered LLM provider: %s -> %s", name, provider_class.__name__)


def get_provider(settings: LLMSettings) -> LLMProvider:
    """Create an LLM provider instance from settings.

    Args:
        settings: LLM configuration settings.

    Returns:
        An initialized LLMProvider instance.

    Raises:
        ValueError: If the provider is not registered.
    """
    _ensure_default_providers()

    provider_name = settings.provider.lower()
    provider_class = _PROVIDER_REGISTRY.get(provider_name)

    if provider_class is None:
        available = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. Available: {available}"
        )

    kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.api_key,
        "api_base": settings.api_base,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "timeout": settings.timeout,
    }

    return provider_class(**kwargs)


def list_providers() -> list[str]:
    """List all registered provider names."""
    _ensure_default_providers()
    return sorted(_PROVIDER_REGISTRY.keys())


def _ensure_default_providers() -> None:
    """Register the default providers if not already registered."""
    if _PROVIDER_REGISTRY:
        return

    from hivecore.core.llm.litellm_provider import LiteLLMProvider, OllamaProvider

    register_provider("litellm", LiteLLMProvider)
    register_provider("openai", LiteLLMProvider)
    register_provider("anthropic", LiteLLMProvider)
    register_provider("google", LiteLLMProvider)
    register_provider("azure", LiteLLMProvider)
    register_provider("ollama", OllamaProvider)
