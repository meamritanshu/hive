"""Shared pytest fixtures for the HiveCore test suite.

Fixtures defined here are available in all test files automatically.
Session-scoped fixtures are used for expensive objects (e.g. temp directories
that survive the whole test session).  Function-scoped fixtures (default) are
used for stateful objects that must be fresh per test.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from hivecore.config.settings import HiveSettings, MemorySettings


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_dir() -> Generator[Path, None, None]:
    """Yield a fresh temporary directory, cleaned up after each test."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture()
def memory_settings(tmp_dir: Path) -> MemorySettings:
    """Return a MemorySettings instance pointing at a temp data directory."""
    return MemorySettings(
        data_dir=str(tmp_dir / "memory"),
        backend="sqlite",
        embedding_provider="none",
    )


@pytest.fixture()
def hive_settings(tmp_dir: Path) -> HiveSettings:
    """Return a minimal HiveSettings instance for testing."""
    return HiveSettings()


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------

def make_llm_mock(content: str = "Mock response", tool_calls: list[Any] | None = None):
    """Return a mock LLMProvider whose ``complete()`` returns a fixed Message."""
    from hivecore.core.messages import Message

    mock = AsyncMock()
    response_msg = Message.assistant(content)
    if tool_calls:
        response_msg.tool_calls = tool_calls
    mock.complete = AsyncMock(return_value=response_msg)
    return mock


@pytest.fixture()
def mock_llm():
    """LLM mock that always returns 'Mock response' with no tool calls."""
    return make_llm_mock()


# ---------------------------------------------------------------------------
# Memory manager (integration-grade, no embeddings)
# ---------------------------------------------------------------------------

@pytest.fixture()
async def memory_manager(memory_settings: MemorySettings):
    """Fully initialised MemoryManager backed by SQLite, no embeddings."""
    from hivecore.memory.manager import MemoryManager

    mgr = MemoryManager(memory_settings)
    await mgr.initialize()
    yield mgr
    await mgr.close()


# ---------------------------------------------------------------------------
# Agent fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
async def agent(mock_llm):
    """Agent instance with a mocked LLM, no memory, no external calls."""
    from hivecore.core.agent import Agent

    a = Agent(llm_provider=mock_llm)
    await a.initialize()
    yield a
    await a.shutdown()
