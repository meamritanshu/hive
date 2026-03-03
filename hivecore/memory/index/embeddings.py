"""Embedding generation utilities.

Supports local embeddings (sentence-transformers) and API-based
embeddings (OpenAI, etc.) via LiteLLM.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates text embeddings using configurable backends.

    Supports:
    - API-based: OpenAI, Cohere, etc. via LiteLLM
    - Local: sentence-transformers models
    - Ollama: local embeddings via Ollama API
    """

    def __init__(
        self,
        provider: str = "openai",
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self._local_model = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        if self.provider == "local":
            return await self._embed_local(texts)
        elif self.provider == "ollama":
            return await self._embed_ollama(texts)
        else:
            return await self._embed_api(texts)

    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using LiteLLM's API."""
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": texts,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key

        try:
            response = await litellm.aembedding(**kwargs)
            return [item["embedding"] for item in response.data]
        except Exception as e:
            logger.error("API embedding failed: %s", e)
            raise

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using sentence-transformers."""
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._local_model = SentenceTransformer(self.model)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install hivecore[embeddings-local]"
                )

        embeddings = self._local_model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]

    async def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Ollama's local API."""
        import httpx

        embeddings = []
        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                response = await client.post(
                    "http://localhost:11434/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])

        return embeddings

    @property
    def dimension(self) -> int:
        """Get the embedding dimension for the configured model."""
        known_dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
        }
        return known_dims.get(self.model, 768)
