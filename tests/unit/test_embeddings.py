"""Unit tests for EmbeddingGenerator (memory/index/embeddings.py).

Coverage targets:
- embed([]) → returns []
- embed(texts) with provider="local" → _embed_local
- embed(texts) with provider="ollama" → _embed_ollama
- embed(texts) with default/api provider → _embed_api
- _embed_local: lazy model load, ImportError when sentence_transformers missing
- _embed_ollama: mocked httpx; multiple texts
- _embed_api: mocked litellm.aembedding; api_key forwarded; exception re-raised
- dimension property for known and unknown models
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivecore.memory.index.embeddings import EmbeddingGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_litellm_response(vectors: list[list[float]]) -> MagicMock:
    response = MagicMock()
    response.data = [{"embedding": v} for v in vectors]
    return response


# ---------------------------------------------------------------------------
# embed() — empty list guard
# ---------------------------------------------------------------------------

class TestEmbedEmpty:
    async def test_empty_list_returns_empty(self) -> None:
        gen = EmbeddingGenerator()
        result = await gen.embed([])
        assert result == []


# ---------------------------------------------------------------------------
# Helpers for litellm mocking (litellm may not be installed)
# ---------------------------------------------------------------------------

import sys
import contextlib

@contextlib.contextmanager
def _mock_litellm(aembedding_mock: AsyncMock):
    """Inject a fake litellm module so patch() can find litellm.aembedding."""
    fake_litellm = MagicMock()
    fake_litellm.aembedding = aembedding_mock
    with patch.dict(sys.modules, {"litellm": fake_litellm}):
        yield fake_litellm


# ---------------------------------------------------------------------------
# _embed_api (default provider)
# ---------------------------------------------------------------------------

class TestEmbedApi:
    async def test_calls_litellm_aembedding(self) -> None:
        gen = EmbeddingGenerator(provider="openai", model="text-embedding-3-small")
        expected = [[0.1, 0.2], [0.3, 0.4]]
        mock_response = _make_litellm_response(expected)
        mock_fn = AsyncMock(return_value=mock_response)

        with _mock_litellm(mock_fn):
            result = await gen.embed(["hello", "world"])

        assert result == expected

    async def test_api_key_forwarded_when_set(self) -> None:
        gen = EmbeddingGenerator(
            provider="openai",
            model="text-embedding-3-small",
            api_key="sk-test",
        )
        mock_response = _make_litellm_response([[1.0]])
        mock_fn = AsyncMock(return_value=mock_response)

        with _mock_litellm(mock_fn):
            await gen.embed(["text"])

        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("api_key") == "sk-test"

    async def test_api_key_omitted_when_none(self) -> None:
        gen = EmbeddingGenerator(provider="openai", model="text-embedding-3-small", api_key=None)
        mock_response = _make_litellm_response([[1.0]])
        mock_fn = AsyncMock(return_value=mock_response)

        with _mock_litellm(mock_fn):
            await gen.embed(["text"])

        call_kwargs = mock_fn.call_args.kwargs
        assert "api_key" not in call_kwargs

    async def test_exception_is_reraised(self) -> None:
        gen = EmbeddingGenerator(provider="openai", model="text-embedding-3-small")
        mock_fn = AsyncMock(side_effect=RuntimeError("api error"))

        with _mock_litellm(mock_fn):
            with pytest.raises(RuntimeError, match="api error"):
                await gen.embed(["text"])


# ---------------------------------------------------------------------------
# _embed_local (provider="local")
# ---------------------------------------------------------------------------

class TestEmbedLocal:
    async def test_raises_import_error_when_not_installed(self) -> None:
        gen = EmbeddingGenerator(provider="local", model="all-MiniLM-L6-v2")

        with patch("builtins.__import__", side_effect=ImportError("no sentence_transformers")):
            with pytest.raises(ImportError, match="sentence-transformers"):
                await gen.embed(["hello"])

    async def test_uses_sentence_transformer(self) -> None:
        gen = EmbeddingGenerator(provider="local", model="all-MiniLM-L6-v2")

        # Mock the SentenceTransformer class and its encode method
        mock_model = MagicMock()
        mock_model.encode.return_value = [MagicMock(tolist=lambda: [0.1, 0.2])]

        mock_st_module = MagicMock()
        mock_st_module.SentenceTransformer.return_value = mock_model

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            result = await gen.embed(["hello"])

        assert isinstance(result, list)
        assert len(result) == 1

    async def test_model_loaded_lazily_and_cached(self) -> None:
        gen = EmbeddingGenerator(provider="local", model="all-MiniLM-L6-v2")
        assert gen._local_model is None

        vec = MagicMock()
        vec.tolist.return_value = [0.5, 0.5]
        mock_model = MagicMock()
        mock_model.encode.return_value = [vec]

        mock_st_module = MagicMock()
        mock_st_module.SentenceTransformer.return_value = mock_model

        with patch.dict("sys.modules", {"sentence_transformers": mock_st_module}):
            await gen.embed(["first call"])
            assert gen._local_model is mock_model
            # Second call must not recreate the model
            await gen.embed(["second call"])

        assert mock_st_module.SentenceTransformer.call_count == 1


# ---------------------------------------------------------------------------
# _embed_ollama (provider="ollama")
# ---------------------------------------------------------------------------

class TestEmbedOllama:
    async def test_posts_to_ollama_api(self) -> None:
        gen = EmbeddingGenerator(provider="ollama", model="nomic-embed-text")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await gen.embed(["hello"])

        assert result == [[0.1, 0.2, 0.3]]
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "localhost:11434" in call_kwargs.args[0]

    async def test_multiple_texts_multiple_posts(self) -> None:
        gen = EmbeddingGenerator(provider="ollama", model="nomic-embed-text")

        call_count = {"n": 0}

        async def _post(url: str, json: dict) -> MagicMock:
            call_count["n"] += 1
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"embedding": [float(call_count["n"])]}
            return resp

        mock_client = AsyncMock()
        mock_client.post.side_effect = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await gen.embed(["a", "b", "c"])

        assert len(result) == 3
        assert mock_client.post.call_count == 3


# ---------------------------------------------------------------------------
# dimension property
# ---------------------------------------------------------------------------

class TestDimension:
    @pytest.mark.parametrize("model,expected_dim", [
        ("text-embedding-3-small", 1536),
        ("text-embedding-3-large", 3072),
        ("text-embedding-ada-002", 1536),
        ("all-MiniLM-L6-v2", 384),
        ("all-mpnet-base-v2", 768),
    ])
    def test_known_models(self, model: str, expected_dim: int) -> None:
        gen = EmbeddingGenerator(model=model)
        assert gen.dimension == expected_dim

    def test_unknown_model_returns_default(self) -> None:
        gen = EmbeddingGenerator(model="some-unknown-model-xyz")
        assert gen.dimension == 768
