"""Unit tests for the LLM provider registry (core/llm/registry.py).

Coverage targets:
- register_provider()
- get_provider() — known provider, unknown provider raises ValueError
- list_providers()
- _ensure_default_providers() — idempotent, registers expected names
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import hivecore.core.llm.registry as reg_module
from hivecore.core.llm.registry import (
    _PROVIDER_REGISTRY,
    get_provider,
    list_providers,
    register_provider,
)
from hivecore.config.settings import LLMSettings
from hivecore.core.llm.base import LLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeProvider(LLMProvider):
    """Minimal concrete LLMProvider for testing."""

    def __init__(self, **kwargs: Any) -> None:
        # Save the raw kwargs before super().__init__ consumes them
        self.init_kwargs = dict(kwargs)
        super().__init__(**kwargs)

    async def complete(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:  # type: ignore[override]
        return MagicMock()

    async def complete_stream(self, messages: Any, tools: Any = None, **kwargs: Any) -> Any:  # type: ignore[override]
        return MagicMock()

    async def embed(self, texts: Any) -> Any:  # type: ignore[override]
        return []


def _clean_registry():
    """Context manager that saves/restores the registry around a test."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        original = dict(_PROVIDER_REGISTRY)
        _PROVIDER_REGISTRY.clear()
        try:
            yield
        finally:
            _PROVIDER_REGISTRY.clear()
            _PROVIDER_REGISTRY.update(original)

    return _ctx()


# ---------------------------------------------------------------------------
# register_provider
# ---------------------------------------------------------------------------

class TestRegisterProvider:
    def test_registers_by_name(self) -> None:
        with _clean_registry():
            register_provider("myprovider", _FakeProvider)
            assert "myprovider" in _PROVIDER_REGISTRY
            assert _PROVIDER_REGISTRY["myprovider"] is _FakeProvider

    def test_name_lowercased(self) -> None:
        with _clean_registry():
            register_provider("MyProvider", _FakeProvider)
            assert "myprovider" in _PROVIDER_REGISTRY

    def test_overwrites_existing(self) -> None:
        with _clean_registry():
            register_provider("dup", _FakeProvider)

            class _AnotherProvider(_FakeProvider):
                pass

            register_provider("dup", _AnotherProvider)
            assert _PROVIDER_REGISTRY["dup"] is _AnotherProvider


# ---------------------------------------------------------------------------
# get_provider
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_unknown_provider_raises(self) -> None:
        with _clean_registry():
            register_provider("known", _FakeProvider)
            settings = LLMSettings(provider="unknown_xyz")
            with pytest.raises(ValueError, match="unknown_xyz"):
                get_provider(settings)

    def test_known_provider_returns_instance(self) -> None:
        with _clean_registry():
            register_provider("fake", _FakeProvider)
            settings = LLMSettings(
                provider="fake",
                model="test-model",
                temperature=0.5,
            )
            instance = get_provider(settings)
            assert isinstance(instance, _FakeProvider)

    def test_kwargs_forwarded_to_provider(self) -> None:
        with _clean_registry():
            register_provider("fake", _FakeProvider)
            settings = LLMSettings(
                provider="fake",
                model="gpt-4",
                temperature=0.7,
                max_tokens=512,
            )
            instance = get_provider(settings)
            assert instance.init_kwargs["model"] == "gpt-4"
            assert instance.init_kwargs["temperature"] == 0.7
            assert instance.init_kwargs["max_tokens"] == 512

    def test_error_message_lists_available(self) -> None:
        with _clean_registry():
            register_provider("alpha", _FakeProvider)
            register_provider("beta", _FakeProvider)
            settings = LLMSettings(provider="gamma")
            with pytest.raises(ValueError) as exc_info:
                get_provider(settings)
            msg = str(exc_info.value)
            assert "alpha" in msg
            assert "beta" in msg

    def test_provider_name_case_insensitive(self) -> None:
        with _clean_registry():
            register_provider("mybackend", _FakeProvider)
            settings = LLMSettings(provider="MyBackend")
            instance = get_provider(settings)
            assert isinstance(instance, _FakeProvider)


# ---------------------------------------------------------------------------
# list_providers
# ---------------------------------------------------------------------------

class TestListProviders:
    def test_returns_sorted_list(self) -> None:
        with _clean_registry():
            register_provider("zzz", _FakeProvider)
            register_provider("aaa", _FakeProvider)
            register_provider("mmm", _FakeProvider)
            names = list_providers()
            assert names == sorted(names)

    def test_returns_list_type(self) -> None:
        with _clean_registry():
            register_provider("one", _FakeProvider)
            result = list_providers()
            assert isinstance(result, list)

    def test_includes_registered_names(self) -> None:
        with _clean_registry():
            register_provider("p1", _FakeProvider)
            register_provider("p2", _FakeProvider)
            names = list_providers()
            assert "p1" in names
            assert "p2" in names


# ---------------------------------------------------------------------------
# _ensure_default_providers — via list_providers() on empty registry
# ---------------------------------------------------------------------------

class TestEnsureDefaultProviders:
    def test_default_providers_registered(self) -> None:
        """Starting from an empty registry, list_providers() must populate defaults."""
        original = dict(_PROVIDER_REGISTRY)
        _PROVIDER_REGISTRY.clear()
        try:
            # Mock litellm_provider to avoid importing the real one
            fake_litellm = MagicMock()
            fake_litellm.LiteLLMProvider = _FakeProvider
            fake_litellm.OllamaProvider = _FakeProvider
            with patch.dict("sys.modules", {
                "hivecore.core.llm.litellm_provider": fake_litellm,
            }):
                names = list_providers()
            assert "litellm" in names
            assert "openai" in names
            assert "anthropic" in names
            assert "ollama" in names
        finally:
            _PROVIDER_REGISTRY.clear()
            _PROVIDER_REGISTRY.update(original)

    def test_idempotent_when_already_populated(self) -> None:
        """_ensure_default_providers must not overwrite an already-populated registry."""
        with _clean_registry():
            register_provider("existing", _FakeProvider)
            # Call list_providers twice
            names1 = list_providers()
            names2 = list_providers()
            assert names1 == names2
            # The manually registered provider should still be present
            assert "existing" in list_providers()
