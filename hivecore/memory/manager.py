"""Memory Manager - orchestrates all memory subsystems.

The central coordinator for HiveCore's memory system, managing:
- Short-term conversation buffer
- File-based long-term memory (Markdown)
- Vector-based semantic memory (SQLite/ChromaDB)
- Memory compaction and retrieval
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hivecore.config.settings import MemorySettings
from hivecore.memory.git_sync import MemoryGitSync
from hivecore.memory.index.embeddings import EmbeddingGenerator
from hivecore.memory.long_term.compactor import MemoryCompactor
from hivecore.memory.long_term.file_memory import FileMemory
from hivecore.memory.long_term.vector_memory import VectorMemory
from hivecore.memory.retrieval.hybrid import BM25Index, HybridRetriever
from hivecore.memory.retrieval.shadow_index import ShadowIndex
from hivecore.memory.short_term import ShortTermMemory
from hivecore.memory.stores.sqlite import SQLiteVectorStore
from hivecore.memory.types import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class MemoryManager:
    """Central memory manager for HiveCore.

    Orchestrates the dual memory system:
    1. File-based memory: Human-readable Markdown files for daily logs,
       knowledge categories, and portable memory export.
    2. Vector memory: Semantic search over all memory entries using
       embeddings for context-aware retrieval.

    Also manages:
    - Short-term conversation buffer with sliding window
    - Memory compaction (summarizing old conversations)
    - Hybrid retrieval (vector + BM25 keyword search)
    """

    def __init__(self, settings: MemorySettings | None = None) -> None:
        self.settings = settings or MemorySettings()
        self._file_memory: FileMemory | None = None
        self._vector_memory: VectorMemory | None = None
        # Session-keyed short-term buffers.  A "default" session is always
        # present for callers that do not supply a session_id.
        self._sessions: dict[str, ShortTermMemory] = {
            "default": ShortTermMemory(
                max_messages=self.settings.max_short_term_messages,
                compaction_token_threshold=self.settings.compaction_threshold,
            )
        }
        self._hybrid_retriever = HybridRetriever(
            vector_weight=self.settings.vector_weight,
            bm25_weight=self.settings.bm25_weight,
        )
        self._bm25_index = BM25Index()
        self._shadow_index: ShadowIndex | None = None
        self._embedder: EmbeddingGenerator | None = None
        self._compactor = MemoryCompactor()
        self._git_sync: MemoryGitSync | None = None
        self._initialized = False

    def get_session(self, session_id: str) -> ShortTermMemory:
        """Return the ShortTermMemory buffer for *session_id*, creating it on first access.

        Args:
            session_id: Arbitrary string key — e.g. ``"discord_123"``, ``"cli_local"``.

        Returns:
            The session's :class:`ShortTermMemory` instance.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = ShortTermMemory(
                max_messages=self.settings.max_short_term_messages,
                compaction_token_threshold=self.settings.compaction_threshold,
            )
            logger.debug("Created new ShortTermMemory for session '%s'", session_id)
        return self._sessions[session_id]

    @property
    def _short_term(self) -> ShortTermMemory:
        """Backward-compatible accessor returning the 'default' session buffer."""
        return self._sessions["default"]

    async def initialize(self) -> None:
        """Initialize all memory subsystems."""
        if self._initialized:
            return

        data_dir = Path(self.settings.data_dir)

        # Initialize file memory
        self._file_memory = FileMemory(data_dir)
        await self._file_memory.initialize()

        # Initialize embedding generator
        try:
            self._embedder = EmbeddingGenerator(
                provider=self.settings.embedding_provider,
                model=self.settings.embedding_model,
            )
        except Exception as e:
            logger.warning("Embedding generator setup failed: %s. Vector search disabled.", e)
            self._embedder = None

        # Initialize vector store based on backend setting
        if self.settings.backend == "chromadb":
            try:
                from hivecore.memory.stores.sqlite import ChromaDBStore
                store = ChromaDBStore(persist_dir=str(data_dir / "chromadb"))
            except ImportError:
                logger.warning("ChromaDB not available, falling back to SQLite.")
                store = SQLiteVectorStore(data_dir / "vectors.db")
        else:
            store = SQLiteVectorStore(data_dir / "vectors.db")

        await store.initialize()

        embedding_fn = self._embedder.embed if self._embedder else None
        self._vector_memory = VectorMemory(store=store, embedding_fn=embedding_fn)

        # Initialize DuckDB shadow index (graceful no-op if duckdb not installed)
        self._shadow_index = ShadowIndex(data_dir / "shadow.duckdb")
        await self._shadow_index.initialize()

        # Initialize git-based memory versioning (graceful no-op if git absent)
        self._git_sync = MemoryGitSync(data_dir)
        await self._git_sync.initialize()

        # Build BM25 index from existing entries (also seeds the shadow index)
        try:
            entries = await store.list_all(limit=5000)
            if entries:
                self._bm25_index.build(entries)
                logger.debug("BM25 index built with %d entries", self._bm25_index.size)
                # Seed shadow index if it is empty (first run after upgrade)
                if self._shadow_index.available and self._shadow_index.count() == 0:
                    await self._shadow_index.rebuild(entries)
                    logger.debug("Shadow index seeded with %d entries", len(entries))
        except Exception as e:
            logger.warning("Index build failed: %s", e)

        self._initialized = True
        logger.info("Memory manager initialized (backend=%s, data_dir=%s)",
                     self.settings.backend, data_dir)

    async def store_conversation(
        self,
        user_message: str,
        assistant_message: str,
        session_id: str = "default",
    ) -> None:
        """Store a conversation turn in both file and vector memory.

        Args:
            user_message: The user's message.
            assistant_message: The agent's response.
            session_id: Channel / session identifier.  Defaults to ``"default"``.
        """
        # Keep short-term buffer up-to-date for this session
        stm = self.get_session(session_id)
        from hivecore.core.messages import Message
        stm.add(Message.user(user_message))
        stm.add(Message.assistant(assistant_message))
        # Store in file memory
        if self._file_memory:
            await self._file_memory.store_conversation(user_message, assistant_message)

        # Store as episodic memory in vector store
        if self._vector_memory:
            entry = MemoryEntry(
                type=MemoryType.EPISODIC,
                content=f"User: {user_message}\nAssistant: {assistant_message}",
                source="conversation",
            )
            await self._vector_memory.add(entry)

            # Update in-process BM25 index
            self._bm25_index.add_document({
                "id": entry.id,
                "content": entry.content,
            })
            # Update shadow index
            if self._shadow_index:
                self._shadow_index.upsert(
                    id=entry.id,
                    content=entry.content,
                    mem_type=entry.type.value,
                    source=entry.source,
                )

    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry in all systems.

        Args:
            entry: The memory entry to store.

        Returns:
            The entry ID.
        """
        if self._file_memory:
            await self._file_memory.store(entry)

        entry_id = entry.id
        if self._vector_memory:
            entry_id = await self._vector_memory.add(entry)
            self._bm25_index.add_document({
                "id": entry.id,
                "content": entry.content,
            })
            if self._shadow_index:
                self._shadow_index.upsert(
                    id=entry.id,
                    content=entry.content,
                    mem_type=entry.type.value,
                    source=getattr(entry, "source", ""),
                    importance=getattr(entry, "importance", 0.5),
                )

        return entry_id

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        memory_type: MemoryType | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant memories using hybrid search.

        Combines vector similarity and BM25 keyword search for
        comprehensive retrieval.

        Args:
            query: Search query.
            top_k: Number of results (defaults to settings).
            memory_type: Optional filter by memory type.

        Returns:
            List of memory dicts sorted by relevance.
        """
        k = top_k or self.settings.retrieval_top_k
        results: list[dict[str, Any]] = []

        # Vector search
        vector_results: list[dict[str, Any]] = []
        if self._vector_memory:
            try:
                search_results = await self._vector_memory.search(
                    query=query, top_k=k, memory_type=memory_type,
                )
                vector_results = [
                    {
                        "id": r.entry.id,
                        "content": r.entry.content,
                        "type": r.entry.type.value,
                        "score": r.relevance_score,
                    }
                    for r in search_results
                ]
            except Exception as e:
                logger.warning("Vector search failed: %s", e)

        # BM25 / shadow index search
        # Prefer DuckDB shadow index (handles large corpora efficiently);
        # fall back to in-process BM25Index when shadow index is unavailable.
        if self._shadow_index and self._shadow_index.available:
            bm25_results = self._shadow_index.search_text(
                query,
                top_k=k,
                mem_type=memory_type.value if memory_type else None,
            )
        else:
            bm25_results = self._bm25_index.search(query, top_k=k)

        # Hybrid merge
        if vector_results or bm25_results:
            results = self._hybrid_retriever.merge_results(
                vector_results=vector_results,
                bm25_results=bm25_results,
                top_k=k,
            )

        # Also include file-based search results
        if self._file_memory and len(results) < k:
            try:
                file_results = await self._file_memory.search(
                    query, max_results=k - len(results)
                )
                for fr in file_results:
                    if not any(r["content"] == fr["content"] for r in results):
                        results.append(fr)
            except Exception as e:
                logger.warning("File memory search failed: %s", e)

        return results[:k]

    async def get_context_for_prompt(self, query: str, max_tokens: int = 2000) -> str:
        """Get formatted memory context for injection into the agent's prompt.

        Args:
            query: The user's current query.
            max_tokens: Approximate token budget for context.

        Returns:
            Formatted context string.
        """
        memories = await self.retrieve(query)
        if not memories:
            return ""

        context_parts = []
        total_tokens = 0

        for mem in memories:
            content = mem.get("content", "")
            mem_type = mem.get("type", "general")
            tokens = len(content) // 4  # rough estimate

            if total_tokens + tokens > max_tokens:
                break

            context_parts.append(f"[{mem_type}] {content[:500]}")
            total_tokens += tokens

        return "\n".join(context_parts)

    async def compact_if_needed(self, session_id: str = "default") -> bool:
        """Check if compaction is needed for *session_id* and perform it.

        Args:
            session_id: The session to inspect.  Defaults to ``"default"``.

        Returns:
            True if compaction was performed.
        """
        stm = self.get_session(session_id)
        if not stm.needs_compaction:
            return False

        messages = stm.get_messages_for_compaction()
        if not messages:
            return False

        # Summarize old messages
        summary = await self._compactor.summarize_messages(messages)

        # Store summary as a memory entry
        await self.store(
            MemoryEntry(
                type=MemoryType.EPISODIC,
                content=summary,
                summary=summary,
                source="compaction",
                importance=0.7,
            )
        )

        # Extract and store facts
        facts = await self._compactor.extract_facts(messages)
        for fact in facts:
            await self.store(
                MemoryEntry(
                    type=MemoryType.FACTUAL,
                    content=fact,
                    source="fact_extraction",
                    importance=0.8,
                )
            )

        # Compact the short-term buffer
        stm.compact(summary)

        logger.info(
            "Memory compaction complete for session '%s': %d messages -> summary + %d facts",
            session_id, len(messages), len(facts),
        )

        # Persist compaction artefacts to git
        if self._git_sync:
            import datetime
            week_label = datetime.date.today().strftime("%Y-W%W")
            await self._git_sync.commit(
                f"chore: compaction {week_label} session={session_id}"
            )

        return True

    async def get_stats(self) -> dict[str, Any]:
        """Get comprehensive memory statistics."""
        stats: dict[str, Any] = {
            "sessions": {
                sid: {
                    "messages": stm.message_count,
                    "tokens_estimate": stm.total_tokens,
                    "needs_compaction": stm.needs_compaction,
                }
                for sid, stm in self._sessions.items()
            },
            "bm25_index_size": self._bm25_index.size,
            "shadow_index": {
                "available": self._shadow_index.available if self._shadow_index else False,
                "entries": self._shadow_index.count() if self._shadow_index else 0,
            },
        }

        if self._file_memory:
            stats["file_memory"] = await self._file_memory.get_stats()

        if self._vector_memory:
            stats["vector_memory"] = await self._vector_memory.get_stats()

        return stats

    async def close(self) -> None:
        """Shut down all memory subsystems."""
        if self._vector_memory:
            await self._vector_memory.close()
        if self._shadow_index:
            await self._shadow_index.close()
        self._initialized = False
        logger.info("Memory manager shut down.")
