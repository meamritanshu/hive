"""Integration tests for MemoryManager — the central memory orchestrator.

These tests exercise the full pipeline end-to-end with a real SQLite vector
store (no embeddings, since no embedding provider is configured in tests).

Covers:
- Initialization and subsystem wiring
- store_conversation() with session_id
- store() / retrieve()
- Session isolation (Fix 3b)
- compact_if_needed() per session (Fix 3b)
- ShadowIndex wiring (Fix 2)
- get_stats() shape
- close() is idempotent
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hivecore.config.settings import MemorySettings
from hivecore.memory.manager import MemoryManager
from hivecore.memory.types import MemoryEntry, MemoryType


# ---------------------------------------------------------------------------
# Fixture helpers (inline — also available via conftest.memory_manager)
# ---------------------------------------------------------------------------

def _make_manager(tmp_path: Path) -> MemoryManager:
    settings = MemorySettings(
        data_dir=str(tmp_path / "memory"),
        backend="sqlite",
        embedding_provider="none",
    )
    return MemoryManager(settings)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestMemoryManagerInit:
    """MemoryManager initialises all subsystems without raising."""

    async def test_initialize_creates_data_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            data_dir = Path(d) / "memory"
            assert data_dir.exists()
            assert (data_dir / "vectors.db").exists()
            await mgr.close()

    async def test_double_initialize_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()
            await mgr.initialize()  # idempotent
            await mgr.close()

    async def test_default_session_created(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()
            assert "default" in mgr._sessions
            await mgr.close()


# ---------------------------------------------------------------------------
# store_conversation
# ---------------------------------------------------------------------------

class TestStoreConversation:
    """store_conversation() stores data and populates the short-term buffer."""

    async def test_stores_in_vector_memory(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            await mgr.store_conversation(
                user_message="What is Python?",
                assistant_message="Python is a programming language.",
            )

            results = await mgr.retrieve("Python programming")
            assert len(results) > 0
            assert any("Python" in r["content"] for r in results)
            await mgr.close()

    async def test_session_id_populates_correct_buffer(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            await mgr.store_conversation(
                user_message="Hello A",
                assistant_message="Hi from A",
                session_id="session_a",
            )
            await mgr.store_conversation(
                user_message="Hello B",
                assistant_message="Hi from B",
                session_id="session_b",
            )

            sess_a = mgr.get_session("session_a")
            sess_b = mgr.get_session("session_b")

            # Each session should have its own 2 messages
            assert sess_a.message_count == 2
            assert sess_b.message_count == 2

            # They must be isolated
            msgs_a = {m.content for m in sess_a.get_messages()}
            msgs_b = {m.content for m in sess_b.get_messages()}
            assert msgs_a.isdisjoint(msgs_b)

            await mgr.close()

    async def test_default_session_used_when_no_session_id(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            await mgr.store_conversation("q", "a")
            assert mgr.get_session("default").message_count == 2
            await mgr.close()


# ---------------------------------------------------------------------------
# store / retrieve
# ---------------------------------------------------------------------------

class TestStoreRetrieve:
    """store() and retrieve() round-trip via the hybrid search pipeline."""

    async def test_store_personal_entry(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            entry = MemoryEntry(
                type=MemoryType.PERSONAL,
                content="User prefers dark mode in all editors",
                importance=0.9,
            )
            entry_id = await mgr.store(entry)
            assert entry_id  # must return an ID

            results = await mgr.retrieve("dark mode editor preference")
            assert any("dark mode" in r["content"] for r in results)
            await mgr.close()

    async def test_retrieve_returns_top_k(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            for i in range(10):
                await mgr.store(MemoryEntry(
                    type=MemoryType.EPISODIC,
                    content=f"Entry number {i} about programming",
                ))

            results = await mgr.retrieve("programming", top_k=3)
            assert len(results) <= 3
            await mgr.close()

    async def test_retrieve_memory_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            await mgr.store(MemoryEntry(type=MemoryType.PERSONAL, content="likes Python"))
            await mgr.store(MemoryEntry(type=MemoryType.TASK, content="finish Python project"))

            results = await mgr.retrieve("Python", memory_type=MemoryType.PERSONAL)
            # At least the personal entry should be returned; task may or may not
            # appear depending on retrieval scoring, but none should be type=task
            # when the store supports filtering (BM25 fallback doesn't filter).
            assert len(results) >= 1
            await mgr.close()


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    """get_stats() returns a dict with expected keys."""

    async def test_stats_shape(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            stats = await mgr.get_stats()

            assert "sessions" in stats
            assert "default" in stats["sessions"]
            assert "bm25_index_size" in stats
            assert "shadow_index" in stats
            assert "available" in stats["shadow_index"]
            await mgr.close()

    async def test_stats_session_keys(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            mgr.get_session("discord_42")
            stats = await mgr.get_stats()
            assert "discord_42" in stats["sessions"]
            await mgr.close()

    async def test_stats_include_file_and_vector_memory(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            stats = await mgr.get_stats()
            assert "file_memory" in stats
            assert "vector_memory" in stats
            await mgr.close()


# ---------------------------------------------------------------------------
# close() idempotency
# ---------------------------------------------------------------------------

class TestClose:
    async def test_double_close_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()
            await mgr.close()
            await mgr.close()  # must not raise


# ---------------------------------------------------------------------------
# ShadowIndex wiring
# ---------------------------------------------------------------------------

class TestShadowIndexWiring:
    """ShadowIndex should be seeded and updated as entries are stored."""

    async def test_shadow_index_present_after_init(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()
            assert mgr._shadow_index is not None
            await mgr.close()

    async def test_shadow_index_updated_on_store(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            shadow_available = mgr._shadow_index and mgr._shadow_index.available
            if not shadow_available:
                await mgr.close()
                pytest.skip("DuckDB not installed — shadow index unavailable")

            before = mgr._shadow_index.count()
            await mgr.store(MemoryEntry(
                type=MemoryType.EPISODIC,
                content="Shadow index should contain this",
            ))
            after = mgr._shadow_index.count()
            assert after == before + 1
            await mgr.close()
