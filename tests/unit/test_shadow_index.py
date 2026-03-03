"""Unit tests for ShadowIndex (memory/retrieval/shadow_index.py).

Coverage targets:
- _check_duckdb() — both paths (available / not available)
- ShadowIndex.__init__
- initialize() — DuckDB unavailable, DuckDB available + FTS success, FTS failure, connect failure
- close()
- upsert() — unavailable guard, happy path, exception swallowed
- delete() — unavailable guard, happy path, exception swallowed
- search_text() — unavailable guard, FTS path, LIKE fallback, both fail
- _like_search() — empty query, single term, multi-term, mem_type filter
- _fts_search() — basic, mem_type filter
- rebuild() — unavailable guard, happy path, exception during rebuild
- count() — unavailable guard, happy path, exception
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import hivecore.memory.retrieval.shadow_index as si_module
from hivecore.memory.retrieval.shadow_index import ShadowIndex


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_available_index(tmp_path: Path) -> ShadowIndex:
    """Return a ShadowIndex with a real in-memory DuckDB-like connection.

    We use a *real sqlite3* connection as a stand-in so tests run without
    duckdb installed: the SQL is identical for the operations we test.
    """
    idx = ShadowIndex(tmp_path / "shadow.duckdb")

    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shadow_memory (
            id          TEXT PRIMARY KEY,
            content     TEXT NOT NULL,
            mem_type    TEXT DEFAULT 'episodic',
            source      TEXT DEFAULT '',
            importance  REAL DEFAULT 0.5,
            created_at  REAL DEFAULT 0.0
        )
        """
    )
    conn.commit()

    # Wrap with a minimal fetchall/execute interface expected by ShadowIndex
    idx._conn = _Sqlite3Adapter(conn)
    idx.available = True
    return idx


class _Sqlite3Adapter:
    """Thin adapter that makes sqlite3 look like duckdb for these tests."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: list[Any] | None = None) -> "_Sqlite3Adapter":
        # DuckDB upsert syntax uses `excluded.` — rewrite for sqlite3
        sql = sql.replace(
            "ON CONFLICT (id) DO UPDATE SET\n                    content    = excluded.content,\n                    mem_type   = excluded.mem_type,\n                    source     = excluded.source,\n                    importance = excluded.importance,\n                    created_at = excluded.created_at",
            "ON CONFLICT(id) DO UPDATE SET "
            "content=excluded.content, mem_type=excluded.mem_type, "
            "source=excluded.source, importance=excluded.importance, "
            "created_at=excluded.created_at",
        )
        self._cur = self._conn.execute(sql, params or [])
        self._conn.commit()
        return self

    def fetchall(self) -> list[Any]:
        return self._cur.fetchall()

    def fetchone(self) -> Any:
        return self._cur.fetchone()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# _check_duckdb
# ---------------------------------------------------------------------------

class TestCheckDuckdb:
    def test_returns_true_when_duckdb_importable(self) -> None:
        # Reset the cache so the check actually runs
        original = si_module._DUCKDB_AVAILABLE
        si_module._DUCKDB_AVAILABLE = None
        try:
            with patch.dict("sys.modules", {"duckdb": MagicMock()}):
                result = si_module._check_duckdb()
            assert result is True
        finally:
            si_module._DUCKDB_AVAILABLE = original

    def test_returns_false_when_duckdb_missing(self) -> None:
        original = si_module._DUCKDB_AVAILABLE
        si_module._DUCKDB_AVAILABLE = None
        try:
            with patch.dict("sys.modules", {"duckdb": None}):
                with patch("builtins.__import__", side_effect=ImportError("no duckdb")):
                    result = si_module._check_duckdb()
            assert result is False
        finally:
            si_module._DUCKDB_AVAILABLE = original

    def test_caches_result(self) -> None:
        """Second call must not re-import; it returns the cached value."""
        original = si_module._DUCKDB_AVAILABLE
        si_module._DUCKDB_AVAILABLE = True
        try:
            result = si_module._check_duckdb()
            assert result is True
        finally:
            si_module._DUCKDB_AVAILABLE = original


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestShadowIndexInit:
    def test_defaults(self, tmp_dir: Path) -> None:
        path = tmp_dir / "shadow.duckdb"
        idx = ShadowIndex(path)
        assert idx.db_path == path
        assert idx._conn is None
        assert idx.available is False


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------

class TestInitialize:
    async def test_no_duckdb_sets_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        with patch.object(si_module, "_check_duckdb", return_value=False):
            await idx.initialize()
        assert idx.available is False
        assert idx._conn is None

    async def test_duckdb_connect_failure_sets_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        mock_duckdb = MagicMock()
        mock_duckdb.connect.side_effect = RuntimeError("disk full")
        with patch.object(si_module, "_check_duckdb", return_value=True):
            with patch.dict("sys.modules", {"duckdb": mock_duckdb}):
                with patch("hivecore.memory.retrieval.shadow_index.duckdb", mock_duckdb, create=True):
                    # Patch the import inside the function
                    import importlib
                    with patch("builtins.__import__") as mock_import:
                        def _import(name, *args, **kwargs):
                            if name == "duckdb":
                                return mock_duckdb
                            return importlib.__import__(name, *args, **kwargs)
                        mock_import.side_effect = _import
                        await idx.initialize()
        assert idx.available is False

    async def test_duckdb_fts_failure_still_available(self, tmp_dir: Path) -> None:
        """FTS setup failure is non-fatal; index should still be available."""
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")

        mock_conn = MagicMock()
        # First execute (_CREATE_TABLE) succeeds; FTS executes raise
        execute_calls = [None]  # call counter
        def execute_side_effect(sql, *args, **kwargs):
            if "fts" in sql.lower() or "INSTALL" in sql or "PRAGMA" in sql:
                raise RuntimeError("fts not supported")
            return mock_conn

        mock_conn.execute.side_effect = execute_side_effect
        mock_duckdb = MagicMock()
        mock_duckdb.connect.return_value = mock_conn

        with patch.object(si_module, "_check_duckdb", return_value=True):
            with patch("builtins.__import__") as mock_import:
                import importlib as _il
                def _imp(name, *args, **kwargs):
                    if name == "duckdb":
                        return mock_duckdb
                    return _il.__import__(name, *args, **kwargs)
                mock_import.side_effect = _imp
                await idx.initialize()

        # available should be True even if FTS failed
        assert idx.available is True


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

class TestClose:
    async def test_close_resets_state(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        assert idx.available is True
        await idx.close()
        assert idx._conn is None
        assert idx.available is False

    async def test_close_when_already_closed(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        # Should not raise even when _conn is None
        await idx.close()
        assert idx.available is False

    async def test_close_swallows_exception(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        mock_conn = MagicMock()
        mock_conn.close.side_effect = RuntimeError("close error")
        idx._conn = mock_conn
        idx.available = True
        await idx.close()  # must not raise
        assert idx._conn is None
        assert idx.available is False


# ---------------------------------------------------------------------------
# upsert()
# ---------------------------------------------------------------------------

class TestUpsert:
    def test_noop_when_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        # Must not raise
        idx.upsert("id1", "content")

    def test_inserts_record(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("id1", "hello world", mem_type="episodic", importance=0.8)
        assert idx.count() == 1

    def test_updates_existing(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("id1", "original")
        idx.upsert("id1", "updated")
        assert idx.count() == 1
        results = idx._like_search("updated", top_k=5, mem_type=None)
        assert results[0]["content"] == "updated"

    def test_exception_swallowed(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("db error")
        idx._conn = mock_conn
        idx.available = True
        idx.upsert("id1", "content")  # must not raise


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def test_noop_when_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        idx.delete("nonexistent")  # must not raise

    def test_removes_record(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("id1", "to be deleted")
        assert idx.count() == 1
        idx.delete("id1")
        assert idx.count() == 0

    def test_delete_nonexistent_is_noop(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.delete("does_not_exist")  # must not raise

    def test_exception_swallowed(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("db error")
        idx._conn = mock_conn
        idx.available = True
        idx.delete("id1")  # must not raise


# ---------------------------------------------------------------------------
# _like_search()
# ---------------------------------------------------------------------------

class TestLikeSearch:
    def _populated(self, tmp_dir: Path) -> ShadowIndex:
        idx = _make_available_index(tmp_dir)
        idx.upsert("a1", "the quick brown fox", mem_type="episodic", importance=0.9)
        idx.upsert("a2", "lazy dog sleeps", mem_type="personal", importance=0.5)
        idx.upsert("a3", "quick lazy cat", mem_type="episodic", importance=0.7)
        return idx

    def test_empty_query_returns_empty(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        results = idx._like_search("", top_k=5, mem_type=None)
        assert results == []

    def test_single_term(self, tmp_dir: Path) -> None:
        idx = self._populated(tmp_dir)
        results = idx._like_search("quick", top_k=10, mem_type=None)
        ids = {r["id"] for r in results}
        assert "a1" in ids
        assert "a3" in ids
        assert "a2" not in ids

    def test_multi_term_intersection(self, tmp_dir: Path) -> None:
        idx = self._populated(tmp_dir)
        results = idx._like_search("quick lazy", top_k=10, mem_type=None)
        ids = {r["id"] for r in results}
        # "quick lazy cat" matches both terms; others only one
        assert "a3" in ids
        assert "a1" not in ids

    def test_mem_type_filter(self, tmp_dir: Path) -> None:
        idx = self._populated(tmp_dir)
        results = idx._like_search("lazy", top_k=10, mem_type="personal")
        ids = {r["id"] for r in results}
        assert "a2" in ids
        assert "a3" not in ids

    def test_result_structure(self, tmp_dir: Path) -> None:
        idx = self._populated(tmp_dir)
        results = idx._like_search("fox", top_k=5, mem_type=None)
        assert len(results) == 1
        r = results[0]
        assert set(r.keys()) == {"id", "content", "mem_type", "score"}
        assert isinstance(r["score"], float)

    def test_top_k_limits_results(self, tmp_dir: Path) -> None:
        idx = self._populated(tmp_dir)
        results = idx._like_search("a", top_k=1, mem_type=None)
        assert len(results) <= 1


# ---------------------------------------------------------------------------
# search_text() — delegates to _fts_search then _like_search fallback
# ---------------------------------------------------------------------------

class TestSearchText:
    def test_returns_empty_when_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        assert idx.search_text("query") == []

    def test_fts_success_path(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        fake_results = [{"id": "x", "content": "c", "mem_type": "e", "score": 1.0}]
        with patch.object(idx, "_fts_search", return_value=fake_results) as mock_fts:
            result = idx.search_text("query", top_k=5)
        mock_fts.assert_called_once_with("query", 5, None)
        assert result == fake_results

    def test_fts_failure_falls_back_to_like(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("b1", "fallback content", mem_type="episodic")

        with patch.object(idx, "_fts_search", side_effect=RuntimeError("no fts")):
            results = idx.search_text("fallback", top_k=5)

        assert any(r["id"] == "b1" for r in results)

    def test_both_fail_returns_empty(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        with patch.object(idx, "_fts_search", side_effect=RuntimeError("fts fail")):
            with patch.object(idx, "_like_search", side_effect=RuntimeError("like fail")):
                result = idx.search_text("anything")
        assert result == []

    def test_mem_type_forwarded(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        with patch.object(idx, "_fts_search", return_value=[]) as mock_fts:
            idx.search_text("q", top_k=3, mem_type="personal")
        mock_fts.assert_called_once_with("q", 3, "personal")


# ---------------------------------------------------------------------------
# rebuild()
# ---------------------------------------------------------------------------

class TestRebuild:
    async def test_noop_when_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        count = await idx.rebuild([{"id": "x", "content": "y"}])
        assert count == 0

    async def test_replaces_all_documents(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("old1", "old content")
        idx.upsert("old2", "old content 2")

        docs = [
            {"id": "new1", "content": "new content A"},
            {"id": "new2", "content": "new content B", "mem_type": "personal"},
        ]
        count = await idx.rebuild(docs)
        assert count == 2
        assert idx.count() == 2

    async def test_returns_zero_on_exception(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(tmp_dir / "shadow.duckdb")
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("rebuild error")
        idx._conn = mock_conn
        idx.available = True
        count = await idx.rebuild([{"id": "x", "content": "y"}])
        assert count == 0

    async def test_optional_fields_defaulted(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        # Minimal doc with only id and content
        await idx.rebuild([{"id": "min1", "content": "minimal"}])
        results = idx._like_search("minimal", top_k=5, mem_type=None)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# count()
# ---------------------------------------------------------------------------

class TestCount:
    def test_zero_when_unavailable(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(Path("/nonexistent/path.duckdb"))
        assert idx.count() == 0

    def test_count_after_upserts(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("c1", "aaa")
        idx.upsert("c2", "bbb")
        assert idx.count() == 2

    def test_count_after_delete(self, tmp_dir: Path) -> None:
        idx = _make_available_index(tmp_dir)
        idx.upsert("c1", "aaa")
        idx.delete("c1")
        assert idx.count() == 0

    def test_count_exception_returns_zero(self, tmp_dir: Path) -> None:
        idx = ShadowIndex(Path("/x/y.duckdb"))
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("error")
        idx._conn = mock_conn
        idx.available = True
        assert idx.count() == 0
