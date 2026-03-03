"""Tests for the SQLite vector store."""

import tempfile
from pathlib import Path

import pytest

from hivecore.memory.stores.sqlite import SQLiteVectorStore


class TestSQLiteVectorStore:
    """Tests for SQLiteVectorStore."""

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()
            stats = await store.get_stats()
            assert stats["total_entries"] == 0
            await store.close()

    @pytest.mark.asyncio
    async def test_upsert_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()

            await store.upsert(
                id="entry1",
                content="Python is a programming language",
                metadata={"type": "factual"},
            )
            await store.upsert(
                id="entry2",
                content="JavaScript runs in browsers",
                metadata={"type": "factual"},
            )

            results = await store.search(query_text="Python programming", top_k=5)
            assert len(results) > 0
            assert any(r["id"] == "entry1" for r in results)

            await store.close()

    @pytest.mark.asyncio
    async def test_upsert_with_embedding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()

            embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
            await store.upsert(
                id="vec1",
                content="Test content",
                embedding=embedding,
                metadata={"type": "test"},
            )

            # Search with embedding
            query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
            results = await store.search(query_embedding=query_embedding, top_k=1)
            assert len(results) == 1
            assert results[0]["score"] > 0.99  # Almost identical

            await store.close()

    @pytest.mark.asyncio
    async def test_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()

            await store.upsert(id="to_delete", content="Delete me")
            result = await store.delete("to_delete")
            assert result is True

            entries = await store.list_all()
            assert len(entries) == 0

            await store.close()

    @pytest.mark.asyncio
    async def test_metadata_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()

            await store.upsert(id="1", content="Personal preference", metadata={"type": "personal"})
            await store.upsert(id="2", content="Task history", metadata={"type": "task"})

            results = await store.search(
                query_text="preference",
                filter_metadata={"type": "personal"},
            )
            assert all(r["metadata"]["type"] == "personal" for r in results if r["score"] > 0)

            await store.close()

    @pytest.mark.asyncio
    async def test_list_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteVectorStore(Path(tmpdir) / "test.db")
            await store.initialize()

            for i in range(5):
                await store.upsert(id=f"entry_{i}", content=f"Content {i}")

            entries = await store.list_all()
            assert len(entries) == 5

            # Test with limit
            limited = await store.list_all(limit=3)
            assert len(limited) == 3

            await store.close()
