"""Integration tests for TieredMemoryCompactor — Fix 2 tiered compaction.

These tests verify the full Tier 1 → Tier 2 → Tier 3 pipeline using a
real SQLite store, with an LLM provider mocked so no API calls are made.

Covers:
- run_compaction_cycle() stats dict shape
- Tier 1 entries older than 7 days are summarised into Tier 2
- Tier 2 entries older than 90 days are promoted to entity facts
- LLM fallback (no LLM configured) does not raise
- Git commit is attempted after a non-empty compaction cycle
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivecore.config.settings import MemorySettings
from hivecore.memory.long_term.compactor import (
    TIER1_MAX_AGE_DAYS,
    TIER2_MAX_AGE_DAYS,
    TieredMemoryCompactor,
)
from hivecore.memory.manager import MemoryManager
from hivecore.memory.types import MemoryEntry, MemoryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path: Path) -> MemoryManager:
    settings = MemorySettings(
        data_dir=str(tmp_path / "memory"),
        backend="sqlite",
        embedding_provider="none",
    )
    return MemoryManager(settings)


def _make_llm_mock(summary: str = "Weekly summary text") -> AsyncMock:
    """Return a mock LLM that returns a fixed summary for any prompt."""
    from hivecore.core.messages import Message
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value=Message.assistant(summary))
    return mock


async def _insert_old_tier1_entry(
    mgr: MemoryManager,
    content: str,
    age_days: float,
) -> None:
    """Insert an episodic entry directly into the vector store with an old timestamp."""
    store = mgr._vector_memory._store  # type: ignore[union-attr]
    old_ts = time.time() - age_days * 86400
    entry = MemoryEntry(type=MemoryType.EPISODIC, content=content)
    await store.upsert(
        id=entry.id,
        content=content,
        metadata={
            "mem_type": "episodic",
            "tier": "1",
            "created_at": old_ts,
        },
    )


async def _insert_old_tier2_entry(
    mgr: MemoryManager,
    content: str,
    age_days: float,
    week: str = "2025-W01",
) -> None:
    """Insert a tier-2 weekly summary directly with an old timestamp."""
    store = mgr._vector_memory._store  # type: ignore[union-attr]
    old_ts = time.time() - age_days * 86400
    entry = MemoryEntry(type=MemoryType.EPISODIC, content=content)
    await store.upsert(
        id=entry.id,
        content=content,
        metadata={
            "mem_type": "episodic",
            "tier": "2",
            "week": week,
            "created_at": old_ts,
        },
    )


# ---------------------------------------------------------------------------
# run_compaction_cycle — stats shape
# ---------------------------------------------------------------------------

class TestCompactionCycleStats:
    """run_compaction_cycle() always returns the expected stats dict."""

    async def test_empty_store_returns_zero_stats(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            compactor = TieredMemoryCompactor()
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats == {
                "tier1_compacted": 0,
                "tier2_promoted": 0,
                "entities_extracted": 0,
            }
            await mgr.close()

    async def test_stats_keys_always_present(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock())
            stats = await compactor.run_compaction_cycle(mgr)

            assert "tier1_compacted" in stats
            assert "tier2_promoted" in stats
            assert "entities_extracted" in stats
            await mgr.close()


# ---------------------------------------------------------------------------
# Tier 1 → Tier 2 compaction
# ---------------------------------------------------------------------------

class TestTier1Compaction:
    """Old Tier 1 entries are summarised into a Tier 2 weekly summary."""

    async def test_recent_entries_not_compacted(self) -> None:
        """Entries younger than TIER1_MAX_AGE_DAYS must not be compacted."""
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            # Insert a fresh entry (1 day old)
            await _insert_old_tier1_entry(mgr, "Fresh entry", age_days=1)

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock())
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier1_compacted"] == 0
            await mgr.close()

    async def test_old_entries_compacted(self) -> None:
        """Entries older than TIER1_MAX_AGE_DAYS are grouped and summarised."""
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            # Insert 3 old entries all in the same ISO week
            old_days = TIER1_MAX_AGE_DAYS + 2
            for i in range(3):
                await _insert_old_tier1_entry(
                    mgr, f"Old conversation {i}", age_days=old_days
                )

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock("Summary"))
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier1_compacted"] == 3
            await mgr.close()

    async def test_compaction_without_llm_uses_fallback(self) -> None:
        """Without an LLM, compaction falls back to truncation (no exception)."""
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            old_days = TIER1_MAX_AGE_DAYS + 2
            await _insert_old_tier1_entry(mgr, "Old entry no LLM", age_days=old_days)

            compactor = TieredMemoryCompactor(llm_provider=None)
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier1_compacted"] == 1
            await mgr.close()


# ---------------------------------------------------------------------------
# Tier 2 → Tier 3 entity promotion
# ---------------------------------------------------------------------------

class TestTier2Promotion:
    """Old Tier 2 summaries are promoted to entity facts."""

    async def test_recent_tier2_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            # Insert a tier-2 entry that is only 30 days old (< TIER2_MAX_AGE_DAYS)
            await _insert_old_tier2_entry(
                mgr, "Recent weekly summary", age_days=30
            )

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock())
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier2_promoted"] == 0
            await mgr.close()

    async def test_old_tier2_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            old_days = TIER2_MAX_AGE_DAYS + 5
            await _insert_old_tier2_entry(
                mgr, "Old weekly summary to promote", age_days=old_days
            )

            entity_response = "personal: User prefers Python\ntask: Finish migration"
            compactor = TieredMemoryCompactor(
                llm_provider=_make_llm_mock(entity_response)
            )
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier2_promoted"] == 1
            assert stats["entities_extracted"] >= 1
            await mgr.close()

    async def test_entity_extraction_none_response(self) -> None:
        """LLM responding 'none' should extract 0 entities."""
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            old_days = TIER2_MAX_AGE_DAYS + 5
            await _insert_old_tier2_entry(
                mgr, "Generic summary with no extractable facts", age_days=old_days
            )

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock("none"))
            stats = await compactor.run_compaction_cycle(mgr)

            assert stats["tier2_promoted"] == 1
            assert stats["entities_extracted"] == 0
            await mgr.close()


# ---------------------------------------------------------------------------
# Git commit integration
# ---------------------------------------------------------------------------

class TestCompactionGitCommit:
    """After a non-empty cycle, run_compaction_cycle attempts a git commit."""

    async def test_git_commit_called_on_nonempty_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            old_days = TIER1_MAX_AGE_DAYS + 2
            await _insert_old_tier1_entry(mgr, "Commit test entry", age_days=old_days)

            git_mock = AsyncMock()
            git_mock.commit = AsyncMock(return_value=True)
            mgr._git_sync = git_mock

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock("Summary"))
            await compactor.run_compaction_cycle(mgr)

            git_mock.commit.assert_called_once()
            commit_msg: str = git_mock.commit.call_args[0][0]
            assert "compaction" in commit_msg.lower()
            await mgr.close()

    async def test_git_commit_not_called_on_empty_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            mgr = _make_manager(Path(d))
            await mgr.initialize()

            git_mock = AsyncMock()
            git_mock.commit = AsyncMock(return_value=False)
            mgr._git_sync = git_mock

            compactor = TieredMemoryCompactor(llm_provider=_make_llm_mock())
            await compactor.run_compaction_cycle(mgr)

            git_mock.commit.assert_not_called()
            await mgr.close()
