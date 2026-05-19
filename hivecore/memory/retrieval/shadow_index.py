"""DuckDB-backed shadow index for high-performance memory retrieval.

The shadow index is a secondary, machine-optimised representation of the
memory corpus that coexists with the human-readable Markdown files.

Architecture
------------
- Markdown files remain the **source of truth** (human-readable, editable,
  git-committable).
- Every write to ``FileMemory`` or ``VectorMemory`` also writes to the
  DuckDB shadow index.
- The ``HybridRetriever`` queries the shadow index for BM25-style full-text
  search instead of scanning Markdown files at query time.

Why DuckDB?
-----------
- Zero-server, file-based (``~/.hivecore/shadow.duckdb``).
- Built-in full-text search (FTS) extension — orders-of-magnitude faster
  than the in-memory BM25 implementation for large corpora (>10k entries).
- SQL interface allows efficient filtered queries (by memory type, date
  range, source) without loading all entries into Python memory.
- Graceful fallback: if DuckDB is not installed, the manager falls back to
  the existing in-process BM25Index.

Usage
-----
The ``ShadowIndex`` is initialised by ``MemoryManager`` and updated on every
``store()`` call.  Querying is done via ``search_text()``.  The index can be
rebuilt at any time from the SQLite vector store with ``rebuild()``.

DuckDB is an optional dependency::

    pip install hivecore[shadow]     # or: pip install duckdb
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DUCKDB_AVAILABLE: bool | None = None


def _check_duckdb() -> bool:
    global _DUCKDB_AVAILABLE
    if _DUCKDB_AVAILABLE is None:
        try:
            import duckdb  # noqa: F401
            _DUCKDB_AVAILABLE = True
        except ImportError:
            _DUCKDB_AVAILABLE = False
    return _DUCKDB_AVAILABLE


# DDL for the shadow table
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS shadow_memory (
    id          VARCHAR PRIMARY KEY,
    content     VARCHAR NOT NULL,
    mem_type    VARCHAR DEFAULT 'episodic',
    source      VARCHAR DEFAULT '',
    importance  DOUBLE  DEFAULT 0.5,
    created_at  DOUBLE  DEFAULT 0.0
);
"""

# DuckDB full-text search setup (requires the fts extension, built in ≥0.8)
_INSTALL_FTS = "INSTALL fts; LOAD fts;"
_CREATE_FTS  = "PRAGMA create_fts_index('shadow_memory', 'id', 'content', overwrite=1);"


class ShadowIndex:
    """DuckDB-backed full-text shadow index over all memory entries.

    Falls back gracefully to a no-op if DuckDB is not installed; the
    ``HybridRetriever`` will then rely solely on the in-process BM25Index.

    Attributes:
        db_path: Path to the DuckDB database file.
        available: True if DuckDB is installed and the index is active.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Any = None  # duckdb.DuckDBPyConnection
        self.available: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open (or create) the DuckDB database and ensure the schema exists."""
        if not _check_duckdb():
            logger.info(
                "DuckDB not installed — shadow index disabled. "
                "Install with: pip install duckdb"
            )
            return

        import duckdb

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = duckdb.connect(str(self.db_path))
            self._conn.execute(_CREATE_TABLE)
            # Attempt to set up FTS (non-fatal if it fails on older DuckDB)
            try:
                self._conn.execute(_INSTALL_FTS)
                self._conn.execute(_CREATE_FTS)
                logger.debug("DuckDB FTS index created on shadow_memory.content")
            except Exception as fts_err:
                logger.debug(
                    "DuckDB FTS setup failed (non-fatal, LIKE search will be used): %s",
                    fts_err,
                )
            self.available = True
            logger.info("Shadow index initialised at %s", self.db_path)
        except Exception as e:
            logger.warning("Shadow index failed to initialise: %s — falling back.", e)
            self._conn = None
            self.available = False

    async def close(self) -> None:
        """Close the DuckDB connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        self.available = False

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        id: str,
        content: str,
        mem_type: str = "episodic",
        source: str = "",
        importance: float = 0.5,
        created_at: float = 0.0,
    ) -> None:
        """Insert or update a single entry in the shadow index.

        This is a **synchronous** call — it is intentionally cheap and is
        designed to be called inline from async memory write paths without
        spawning a thread.  DuckDB in-process writes are fast enough that
        blocking is not a concern for personal-scale usage.

        Args:
            id: Unique memory entry ID.
            content: Text content to index.
            mem_type: Memory type string (e.g. 'episodic', 'personal').
            source: Origin source string (e.g. 'conversation', 'compaction').
            importance: Relevance score hint (0.0–1.0).
            created_at: Unix timestamp of entry creation.
        """
        if not self.available or self._conn is None:
            return

        try:
            self._conn.execute(
                """
                INSERT INTO shadow_memory (id, content, mem_type, source, importance, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    content    = excluded.content,
                    mem_type   = excluded.mem_type,
                    source     = excluded.source,
                    importance = excluded.importance,
                    created_at = excluded.created_at
                """,
                [id, content, mem_type, source, importance, created_at],
            )
        except Exception as e:
            logger.debug("Shadow index upsert failed (non-fatal): %s", e)

    def delete(self, id: str) -> None:
        """Remove an entry from the shadow index."""
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute("DELETE FROM shadow_memory WHERE id = ?", [id])
        except Exception as e:
            logger.debug("Shadow index delete failed (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search_text(
        self,
        query: str,
        top_k: int = 10,
        mem_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full-text search over the shadow index.

        Uses DuckDB FTS if available; falls back to ``LIKE`` pattern
        matching on older DuckDB versions.

        Args:
            query: Search query string.
            top_k: Maximum number of results.
            mem_type: Optional memory type filter.

        Returns:
            List of dicts with keys: id, content, mem_type, score.
        """
        if not self.available or self._conn is None:
            return []

        try:
            return self._fts_search(query, top_k, mem_type)
        except Exception:
            # FTS index may not exist on this DuckDB version; try LIKE
            try:
                return self._like_search(query, top_k, mem_type)
            except Exception as e:
                logger.debug("Shadow index search failed (non-fatal): %s", e)
                return []

    def _fts_search(
        self, query: str, top_k: int, mem_type: str | None
    ) -> list[dict[str, Any]]:
        """Search using DuckDB's built-in FTS MATCH operator."""
        type_filter = "AND mem_type = ?" if mem_type else ""
        params: list[Any] = [query]
        if mem_type:
            params.append(mem_type)
        params.append(top_k)

        sql = f"""
        SELECT id, content, mem_type,
               fts_main_shadow_memory.match_bm25(id, ?) AS score
        FROM shadow_memory
        WHERE score IS NOT NULL
          {type_filter}
        ORDER BY score DESC
        LIMIT ?
        """
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {"id": r[0], "content": r[1], "mem_type": r[2], "score": float(r[3] or 0)}
            for r in rows
        ]

    def _like_search(
        self, query: str, top_k: int, mem_type: str | None
    ) -> list[dict[str, Any]]:
        """Fallback full-text search using LIKE pattern matching."""
        terms = query.lower().split()
        if not terms:
            return []

        conditions = " AND ".join(
            "lower(content) LIKE ?" for _ in terms
        )
        params: list[Any] = [f"%{t}%" for t in terms]
        type_filter = ""
        if mem_type:
            type_filter = "AND mem_type = ?"
            params.append(mem_type)
        params.append(top_k)

        sql = f"""
        SELECT id, content, mem_type, importance AS score
        FROM shadow_memory
        WHERE ({conditions}) {type_filter}
        ORDER BY score DESC, created_at DESC
        LIMIT ?
        """
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {"id": r[0], "content": r[1], "mem_type": r[2], "score": float(r[3] or 0)}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def rebuild(self, documents: list[dict[str, Any]]) -> int:
        """Rebuild the entire shadow index from a list of document dicts.

        Args:
            documents: List of dicts with at minimum ``id`` and ``content``.
                       Optional keys: ``mem_type``, ``source``, ``importance``,
                       ``created_at``.

        Returns:
            Number of documents indexed.
        """
        if not self.available or self._conn is None:
            return 0

        try:
            self._conn.execute("DELETE FROM shadow_memory")
            for doc in documents:
                self.upsert(
                    id=doc["id"],
                    content=doc.get("content", ""),
                    mem_type=doc.get("mem_type", doc.get("type", "episodic")),
                    source=doc.get("source", ""),
                    importance=float(doc.get("importance", 0.5)),
                    created_at=float(doc.get("created_at", 0.0)),
                )
            # Recreate FTS index after bulk insert
            try:
                self._conn.execute(_CREATE_FTS)
            except Exception:
                pass
            logger.info("Shadow index rebuilt with %d documents", len(documents))
            return len(documents)
        except Exception as e:
            logger.warning("Shadow index rebuild failed: %s", e)
            return 0

    def count(self) -> int:
        """Return the number of entries in the shadow index."""
        if not self.available or self._conn is None:
            return 0
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM shadow_memory").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
