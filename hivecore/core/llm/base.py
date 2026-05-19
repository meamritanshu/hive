"""Abstract LLM provider interface.

Defines the contract that all LLM providers must implement. The framework
uses LiteLLM as the default unified provider, but this interface allows
for custom implementations.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from typing import Any

from hivecore.core.messages import Message


class LLMProvider(abc.ABC):
    """Abstract base class for LLM providers.

    All LLM integrations must implement this interface. The default
    implementation (LiteLLMProvider) wraps LiteLLM for broad model support.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 120,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.api_base = api_base
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.extra_kwargs = kwargs

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send messages to the LLM and get a complete response.

        Args:
            messages: Conversation messages.
            tools: Optional tool/function definitions in OpenAI format.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The assistant's response as a Message.
        """
        ...

    @abc.abstractmethod
    async def complete_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Send messages and stream the response token by token.

        Args:
            messages: Conversation messages.
            tools: Optional tool/function definitions in OpenAI format.
            **kwargs: Additional provider-specific parameters.

        Yields:
            Individual tokens/chunks of the response.
        """
        ...

    @abc.abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        ...

    def get_model_info(self) -> dict[str, Any]:
        """Return metadata about the configured model."""
        return {
            "model": self.model,
            "provider": self.__class__.__name__,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
