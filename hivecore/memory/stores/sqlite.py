"""SQLite-based vector store.

Uses SQLite for metadata storage and a simple in-memory cosine similarity
search for vectors. For production workloads, switch to ChromaDB.

This provides a zero-dependency vector search that works offline.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class SQLiteVectorStore:
    """SQLite-backed vector store with in-memory cosine similarity.

    Stores embeddings as JSON arrays in SQLite. Performs brute-force
    cosine similarity search, which is fine for up to ~100k entries.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database and tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding TEXT,
                metadata TEXT DEFAULT '{}',
                created_at REAL DEFAULT 0,
                updated_at REAL DEFAULT 0
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_created
            ON memories(created_at DESC)
        """)
        await self._db.commit()
        logger.debug("SQLite vector store initialized at %s", self.db_path)

    async def upsert(
        self,
        id: str,
        content: str,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update a memory entry.

        Args:
            id: Unique entry ID.
            content: Text content.
            embedding: Vector embedding (optional).
            metadata: Additional metadata.
        """
        assert self._db is not None

        now = time.time()
        embedding_json = json.dumps(embedding) if embedding else None
        metadata_json = json.dumps(metadata or {})

        await self._db.execute(
            """
            INSERT INTO memories (id, content, embedding, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content = excluded.content,
                embedding = excluded.embedding,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (id, content, embedding_json, metadata_json, now, now),
        )
        await self._db.commit()

    async def search(
        self,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        filter_metadata: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar entries.

        If a query embedding is provided, uses cosine similarity.
        Falls back to text keyword search otherwise.

        Args:
            query_embedding: Query vector for semantic search.
            query_text: Fallback text for keyword search.
            top_k: Number of results.
            filter_metadata: Metadata filters.

        Returns:
            List of result dicts with id, content, metadata, score.
        """
        assert self._db is not None

        # Fetch candidates
        query = "SELECT id, content, embedding, metadata FROM memories"
        params: list[Any] = []

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT 1000"

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        results = []
        for row in rows:
            entry_id, content, embedding_json, metadata_json = row
            metadata = json.loads(metadata_json) if metadata_json else {}
            score = 0.0

            if query_embedding and embedding_json:
                entry_embedding = json.loads(embedding_json)
                score = _cosine_similarity(query_embedding, entry_embedding)
            elif query_text:
                # Fallback: simple keyword matching
                query_terms = query_text.lower().split()
                content_lower = content.lower()
                matches = sum(1 for t in query_terms if t in content_lower)
                score = matches / max(len(query_terms), 1)

            results.append({
                "id": entry_id,
                "content": content,
                "metadata": metadata,
                "score": score,
            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, id: str) -> bool:
        """Delete an entry by ID."""
        assert self._db is not None

        cursor = await self._db.execute("DELETE FROM memories WHERE id = ?", (id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_all(
        self,
        filter_metadata: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List all entries, optionally filtered."""
        assert self._db is not None

        query = "SELECT id, content, metadata FROM memories"
        params: list[Any] = []

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                params.append(value)
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "id": row[0],
                "content": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
            }
            for row in rows
        ]

    async def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        assert self._db is not None

        async with self._db.execute("SELECT COUNT(*) FROM memories") as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 0

        async with self._db.execute(
            "SELECT COUNT(*) FROM memories WHERE embedding IS NOT NULL"
        ) as cursor:
            row = await cursor.fetchone()
            embedded_count = row[0] if row else 0

        return {
            "backend": "sqlite",
            "total_entries": count,
            "embedded_entries": embedded_count,
            "db_path": str(self.db_path),
        }

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None


class ChromaDBStore:
    """ChromaDB-backed vector store.

    Requires the chromadb optional dependency.
    Provides better performance for large memory collections.
    """

    def __init__(self, collection_name: str = "hivecore_memory", persist_dir: str | None = None) -> None:
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self._client = None
        self._collection = None

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            import chromadb
        except ImportError:
            raise ImportError(
                "ChromaDB is not installed. Install it with: pip install hivecore[chromadb]"
            )

        if self.persist_dir:
            self._client = chromadb.PersistentClient(path=self.persist_dir)
        else:
            self._client = chromadb.Client()

        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.debug("ChromaDB store initialized: %s", self.collection_name)

    async def upsert(
        self,
        id: str,
        content: str,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update an entry."""
        assert self._collection is not None

        kwargs: dict[str, Any] = {
            "ids": [id],
            "documents": [content],
        }
        if embedding:
            kwargs["embeddings"] = [embedding]
        if metadata:
            # ChromaDB requires flat metadata values
            flat_meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                         for k, v in metadata.items()}
            kwargs["metadatas"] = [flat_meta]

        self._collection.upsert(**kwargs)

    async def search(
        self,
        query_embedding: list[float] | None = None,
        query_text: str | None = None,
        top_k: int = 10,
        filter_metadata: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar entries."""
        assert self._collection is not None

        kwargs: dict[str, Any] = {"n_results": top_k}
        if query_embedding:
            kwargs["query_embeddings"] = [query_embedding]
        elif query_text:
            kwargs["query_texts"] = [query_text]
        else:
            return []

        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = self._collection.query(**kwargs)

        entries = []
        if results["ids"] and results["ids"][0]:
            for i, entry_id in enumerate(results["ids"][0]):
                entries.append({
                    "id": entry_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": 1.0 - (results["distances"][0][i] if results["distances"] else 1.0),
                })
        return entries

    async def delete(self, id: str) -> bool:
        """Delete an entry."""
        assert self._collection is not None
        try:
            self._collection.delete(ids=[id])
            return True
        except Exception:
            return False

    async def list_all(
        self,
        filter_metadata: dict[str, str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List all entries."""
        assert self._collection is not None

        kwargs: dict[str, Any] = {"limit": limit}
        if filter_metadata:
            kwargs["where"] = filter_metadata

        results = self._collection.get(**kwargs)

        entries = []
        if results["ids"]:
            for i, entry_id in enumerate(results["ids"]):
                entries.append({
                    "id": entry_id,
                    "content": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })
        return entries

    async def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        assert self._collection is not None
        return {
            "backend": "chromadb",
            "total_entries": self._collection.count(),
            "collection": self.collection_name,
        }

    async def close(self) -> None:
        """Close the ChromaDB client."""
        self._client = None
        self._collection = None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
