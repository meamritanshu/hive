"""LiteLLM-based unified LLM provider.

This is the default provider that wraps LiteLLM to support 100+ LLM APIs
with a single interface: OpenAI, Anthropic, Google, Ollama, Azure, Together,
OpenRouter, and more.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from hivecore.core.llm.base import LLMProvider
from hivecore.core.messages import Message, ToolCall

logger = logging.getLogger(__name__)


class LiteLLMProvider(LLMProvider):
    """LLM provider using LiteLLM for universal model access.

    Supports any model that LiteLLM supports, including:
    - OpenAI (gpt-4o, gpt-4-turbo, etc.)
    - Anthropic (claude-3-opus, claude-3-sonnet, etc.)
    - Google (gemini-pro, gemini-1.5-pro, etc.)
    - Ollama (llama3, mistral, etc. via ollama/model-name)
    - Azure OpenAI (azure/deployment-name)
    - OpenRouter (openrouter/model-name)
    - Together AI (together_ai/model-name)
    - And 100+ more providers
    """

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Message:
        """Send messages to the LLM via LiteLLM and get a response."""
        import litellm

        llm_messages = [m.to_llm_format() for m in messages]

        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": llm_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
        }

        if self.api_key:
            call_kwargs["api_key"] = self.api_key
        if self.api_base:
            call_kwargs["api_base"] = self.api_base
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        call_kwargs.update(self.extra_kwargs)
        call_kwargs.update(kwargs)

        try:
            response = await litellm.acompletion(**call_kwargs)
        except Exception as e:
            logger.error("LLM completion failed: %s", e)
            raise

        choice = response.choices[0]
        msg = choice.message

        # Parse tool calls if present
        tool_calls: list[ToolCall] = []
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    args = {"raw": tc.function.arguments}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )

        return Message.assistant(
            content=msg.content or "",
            tool_calls=tool_calls if tool_calls else None,
        )

    async def complete_stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream response tokens from the LLM via LiteLLM."""
        import litellm

        llm_messages = [m.to_llm_format() for m in messages]

        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": llm_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "stream": True,
        }

        if self.api_key:
            call_kwargs["api_key"] = self.api_key
        if self.api_base:
            call_kwargs["api_base"] = self.api_base
        if tools:
            call_kwargs["tools"] = tools
            call_kwargs["tool_choice"] = "auto"

        call_kwargs.update(self.extra_kwargs)
        call_kwargs.update(kwargs)

        try:
            response = await litellm.acompletion(**call_kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using LiteLLM's embedding API."""
        import litellm

        call_kwargs: dict[str, Any] = {
            "model": self.extra_kwargs.get("embedding_model", "text-embedding-3-small"),
            "input": texts,
        }

        if self.api_key:
            call_kwargs["api_key"] = self.api_key

        try:
            response = await litellm.aembedding(**call_kwargs)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error("Embedding generation failed: %s", e)
            raise


class OllamaProvider(LiteLLMProvider):
    """Convenience wrapper for Ollama local models.

    Automatically prefixes model names with 'ollama/' for LiteLLM routing
    and sets the default API base to the local Ollama server.
    """

    def __init__(
        self,
        model: str = "llama3",
        api_base: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        # Ensure ollama/ prefix for LiteLLM routing
        if not model.startswith("ollama/"):
            model = f"ollama/{model}"
        super().__init__(model=model, api_base=api_base, **kwargs)
