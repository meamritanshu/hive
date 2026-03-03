"""Vector-based memory storage.

Provides semantic search over memories using vector embeddings.
Supports SQLite (default) and ChromaDB backends.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from hivecore.memory.types import MemoryEntry, MemorySearchResult, MemoryType

logger = logging.getLogger(__name__)


class VectorMemory:
    """Vector store backed long-term memory.

    Stores memory entries with their vector embeddings for semantic
    retrieval. Supports multiple memory types:
    - Personal: User preferences and personal info
    - Task: Execution history and procedures
    - Tool: Tool usage patterns
    - Episodic: Conversation summaries
    - Factual: Learned facts and knowledge

    Uses the configured vector store backend (SQLite or ChromaDB).
    """

    def __init__(
        self,
        store: "BaseVectorStore",
        embedding_fn: Any = None,
    ) -> None:
        self._store = store
        self._embedding_fn = embedding_fn

    async def initialize(self) -> None:
        """Initialize the vector store."""
        await self._store.initialize()

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry with its embedding.

        Args:
            entry: The memory entry to store.

        Returns:
            The entry ID.
        """
        # Generate embedding if not provided
        if entry.embedding is None and self._embedding_fn:
            try:
                embeddings = await self._embedding_fn([entry.content])
                entry.embedding = embeddings[0]
            except Exception as e:
                logger.warning("Failed to generate embedding: %s", e)

        await self._store.upsert(
            id=entry.id,
            content=entry.content,
            embedding=entry.embedding,
            metadata={
                "type": entry.type.value,
                "tags": json.dumps(entry.tags),
                "source": entry.source,
                "importance": entry.importance,
                "created_at": entry.created_at,
                "summary": entry.summary or "",
            },
        )

        logger.debug("Added memory entry: %s (type=%s)", entry.id[:8], entry.type.value)
        return entry.id

    async def search(
        self,
        query: str,
        top_k: int = 10,
        memory_type: Optional[MemoryType] = None,
        min_relevance: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Search for relevant memories using semantic similarity.

        Args:
            query: Search query text.
            top_k: Number of results to return.
            memory_type: Optional filter by memory type.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of MemorySearchResult sorted by relevance.
        """
        # Generate query embedding
        query_embedding = None
        if self._embedding_fn:
            try:
                embeddings = await self._embedding_fn([query])
                query_embedding = embeddings[0]
            except Exception as e:
                logger.warning("Failed to generate query embedding: %s", e)

        # Build filter
        filter_dict = {}
        if memory_type:
            filter_dict["type"] = memory_type.value

        # Query vector store
        raw_results = await self._store.search(
            query_embedding=query_embedding,
            query_text=query,
            top_k=top_k,
            filter_metadata=filter_dict if filter_dict else None,
        )

        # Convert to MemorySearchResult
        results = []
        for item in raw_results:
            if item.get("score", 0) < min_relevance:
                continue

            metadata = item.get("metadata", {})
            tags = json.loads(metadata.get("tags", "[]"))

            entry = MemoryEntry(
                id=item["id"],
                type=MemoryType(metadata.get("type", "episodic")),
                content=item["content"],
                summary=metadata.get("summary"),
                tags=tags,
                source=metadata.get("source", "unknown"),
                importance=float(metadata.get("importance", 0.5)),
                created_at=float(metadata.get("created_at", time.time())),
            )

            results.append(
                MemorySearchResult(
                    entry=entry,
                    relevance_score=item.get("score", 0.0),
                    source="vector",
                )
            )

        return results

    async def update(self, entry_id: str, content: str, **metadata: Any) -> None:
        """Update an existing memory entry.

        Args:
            entry_id: ID of the entry to update.
            content: New content.
            **metadata: Additional metadata to update.
        """
        embedding = None
        if self._embedding_fn:
            try:
                embeddings = await self._embedding_fn([content])
                embedding = embeddings[0]
            except Exception:
                pass

        await self._store.upsert(
            id=entry_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
        )

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry.

        Args:
            entry_id: ID of the entry to delete.

        Returns:
            True if deleted, False if not found.
        """
        return await self._store.delete(entry_id)

    async def list_all(
        self, memory_type: Optional[MemoryType] = None, limit: int = 100
    ) -> list[MemoryEntry]:
        """List all memory entries, optionally filtered by type.

        Args:
            memory_type: Optional type filter.
            limit: Maximum entries to return.

        Returns:
            List of MemoryEntry objects.
        """
        filter_dict = {}
        if memory_type:
            filter_dict["type"] = memory_type.value

        raw = await self._store.list_all(
            filter_metadata=filter_dict if filter_dict else None,
            limit=limit,
        )

        entries = []
        for item in raw:
            metadata = item.get("metadata", {})
            entries.append(
                MemoryEntry(
                    id=item["id"],
                    type=MemoryType(metadata.get("type", "episodic")),
                    content=item["content"],
                    summary=metadata.get("summary"),
                    importance=float(metadata.get("importance", 0.5)),
                    created_at=float(metadata.get("created_at", time.time())),
                )
            )
        return entries

    async def get_stats(self) -> dict[str, Any]:
        """Get vector memory statistics."""
        return await self._store.get_stats()

    async def close(self) -> None:
        """Close the vector store connection."""
        await self._store.close()
