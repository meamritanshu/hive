"""Tests for the memory system."""

import tempfile
from pathlib import Path

import pytest

from hivecore.memory.long_term.file_memory import FileMemory
from hivecore.memory.retrieval.hybrid import BM25Index, HybridRetriever
from hivecore.memory.short_term import ShortTermMemory
from hivecore.memory.types import MemoryEntry, MemoryType


class TestShortTermMemory:
    """Tests for ShortTermMemory."""

    def test_add_and_get(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory(max_messages=10)
        stm.add(Message.user("Hello"))
        stm.add(Message.assistant("Hi!"))

        messages = stm.get_messages()
        assert len(messages) == 2

    def test_system_message_separate(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory()
        stm.add(Message.system("System prompt"))
        stm.add(Message.user("User msg"))

        messages = stm.get_messages()
        assert len(messages) == 2  # system + user
        assert messages[0].role.value == "system"

    def test_sliding_window(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory(max_messages=5)
        for i in range(10):
            stm.add(Message.user(f"Message {i}"))

        assert stm.message_count == 5
        messages = stm.get_messages()
        assert messages[0].content == "Message 5"

    def test_compaction_detection(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory(max_messages=10, compaction_token_threshold=100)
        for i in range(8):
            stm.add(Message.user(f"Message {i} with some extra text to increase tokens"))

        assert stm.needs_compaction

    def test_compact(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory(max_messages=20)
        for i in range(15):
            stm.add(Message.user(f"Message {i}"))

        stm.compact("Summary of first 5 messages", keep_recent=10)
        messages = stm.get_messages()
        # Should have: summary message + 10 recent messages
        assert len(messages) == 11

    def test_clear(self) -> None:
        from hivecore.core.messages import Message

        stm = ShortTermMemory()
        stm.add(Message.system("Keep"))
        stm.add(Message.user("Remove"))
        stm.clear()
        assert stm.message_count == 0
        # System message is preserved separately
        messages = stm.get_messages()
        assert len(messages) == 1


class TestFileMemory:
    """Tests for FileMemory."""

    @pytest.mark.asyncio
    async def test_initialize_creates_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileMemory(Path(tmpdir) / "memory")
            await fm.initialize()
            assert (Path(tmpdir) / "memory" / "daily").exists()
            assert (Path(tmpdir) / "memory" / "knowledge").exists()
            assert (Path(tmpdir) / "memory" / "MEMORY.md").exists()

    @pytest.mark.asyncio
    async def test_store_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileMemory(Path(tmpdir) / "memory")
            await fm.initialize()
            await fm.store_conversation("What is Python?", "Python is a programming language.")

            daily_files = list((Path(tmpdir) / "memory" / "daily").glob("*.md"))
            assert len(daily_files) == 1

            content = daily_files[0].read_text()
            assert "What is Python?" in content
            assert "Python is a programming language" in content

    @pytest.mark.asyncio
    async def test_store_memory_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileMemory(Path(tmpdir) / "memory")
            await fm.initialize()

            entry = MemoryEntry(
                type=MemoryType.PERSONAL,
                content="User prefers dark mode.",
            )
            await fm.store(entry)

            personal_file = Path(tmpdir) / "memory" / "knowledge" / "personal.md"
            content = personal_file.read_text()
            assert "dark mode" in content

    @pytest.mark.asyncio
    async def test_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileMemory(Path(tmpdir) / "memory")
            await fm.initialize()
            await fm.store_conversation("Tell me about Rust", "Rust is a systems programming language.")
            await fm.store_conversation("What is Go?", "Go is a compiled language by Google.")

            results = await fm.search("Rust programming")
            assert len(results) > 0
            assert any("Rust" in r["content"] for r in results)

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fm = FileMemory(Path(tmpdir) / "memory")
            await fm.initialize()
            stats = await fm.get_stats()
            assert "daily_logs" in stats
            assert "total_size_kb" in stats


class TestBM25Index:
    """Tests for BM25Index."""

    def test_build_and_search(self) -> None:
        index = BM25Index()
        docs = [
            {"id": "1", "content": "Python is a great programming language"},
            {"id": "2", "content": "JavaScript runs in the browser"},
            {"id": "3", "content": "Rust is a systems programming language"},
        ]
        index.build(docs)
        assert index.size == 3

        results = index.search("programming language")
        assert len(results) > 0
        # Python and Rust both mention "programming language"
        result_ids = {r["id"] for r in results}
        assert "1" in result_ids or "3" in result_ids

    def test_empty_index(self) -> None:
        index = BM25Index()
        results = index.search("anything")
        assert results == []

    def test_add_document(self) -> None:
        index = BM25Index()
        index.build([{"id": "1", "content": "Hello world"}])
        assert index.size == 1

        index.add_document({"id": "2", "content": "Goodbye world"})
        assert index.size == 2


class TestHybridRetriever:
    """Tests for HybridRetriever."""

    def test_merge_results(self) -> None:
        retriever = HybridRetriever(vector_weight=0.7, bm25_weight=0.3)

        vector_results = [
            {"id": "a", "content": "Result A", "score": 0.9},
            {"id": "b", "content": "Result B", "score": 0.7},
        ]
        bm25_results = [
            {"id": "b", "content": "Result B", "score": 3.5},
            {"id": "c", "content": "Result C", "score": 2.1},
        ]

        merged = retriever.merge_results(vector_results, bm25_results, top_k=3)
        assert len(merged) == 3

        # "b" appears in both, should have highest score
        ids = [r["id"] for r in merged]
        assert ids[0] == "b"

    def test_empty_inputs(self) -> None:
        retriever = HybridRetriever()
        merged = retriever.merge_results([], [])
        assert merged == []


class TestMemoryEntry:
    """Tests for MemoryEntry."""

    def test_create_entry(self) -> None:
        entry = MemoryEntry(
            type=MemoryType.PERSONAL,
            content="User likes dark mode",
            tags=["preference", "ui"],
        )
        assert entry.type == MemoryType.PERSONAL
        assert entry.content == "User likes dark mode"
        assert len(entry.tags) == 2
        assert entry.id  # auto-generated

    def test_to_context_string(self) -> None:
        entry = MemoryEntry(
            type=MemoryType.TASK,
            content="Completed data migration successfully",
        )
        ctx = entry.to_context_string()
        assert "[task]" in ctx
        assert "data migration" in ctx


# ---------------------------------------------------------------------------
# Fix 3b: Session-keyed ShortTermMemory via MemoryManager
# ---------------------------------------------------------------------------

class TestSessionKeyedShortTermMemory:
    """Tests for the session-keyed ShortTermMemory introduced in Fix 3b."""

    def test_default_session_exists(self) -> None:
        """MemoryManager always has a 'default' session after construction."""
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()
        stm = mgr.get_session("default")
        assert stm is not None
        # The _short_term compat property should return the same object
        assert mgr._short_term is stm

    def test_get_session_creates_new(self) -> None:
        """get_session() creates a new ShortTermMemory on first access."""
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()
        sess_a = mgr.get_session("channel_abc")
        assert sess_a is not None
        assert "channel_abc" in mgr._sessions

    def test_get_session_returns_same_instance(self) -> None:
        """Repeated calls with the same key return the exact same object."""
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()
        s1 = mgr.get_session("discord_42")
        s2 = mgr.get_session("discord_42")
        assert s1 is s2

    def test_sessions_are_isolated(self) -> None:
        """Messages added to one session do not appear in another."""
        from hivecore.core.messages import Message
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()

        sess_a = mgr.get_session("a")
        sess_b = mgr.get_session("b")

        sess_a.add(Message.user("Hello from A"))
        assert sess_a.message_count == 1
        assert sess_b.message_count == 0

    def test_multiple_sessions_tracked(self) -> None:
        """All sessions appear in mgr._sessions."""
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()
        for sid in ["cli", "discord", "telegram"]:
            mgr.get_session(sid)
        for sid in ["cli", "discord", "telegram", "default"]:
            assert sid in mgr._sessions

    def test_default_compat_property(self) -> None:
        """The _short_term property is a backward-compatible alias for 'default'."""
        from hivecore.core.messages import Message
        from hivecore.memory.manager import MemoryManager
        mgr = MemoryManager()
        mgr._short_term.add(Message.user("via compat"))
        assert mgr.get_session("default").message_count == 1
