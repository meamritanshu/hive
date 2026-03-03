"""Memory type definitions.

Defines the different types of memory entries and their schemas.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Types of long-term memory."""

    PERSONAL = "personal"       # User preferences, habits, personal info
    TASK = "task"               # Task execution history, procedures
    TOOL = "tool"               # Tool usage patterns, successful approaches
    EPISODIC = "episodic"       # Conversation summaries, event logs
    FACTUAL = "factual"         # Learned facts, knowledge base entries


class MemoryEntry(BaseModel):
    """A single memory entry stored in the memory system."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: MemoryType = Field(default=MemoryType.EPISODIC)
    content: str = Field(description="The memory content.")
    summary: Optional[str] = Field(
        default=None, description="Compressed summary of the memory."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="conversation", description="Source of the memory.")
    importance: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Importance score (0-1)."
    )
    embedding: Optional[list[float]] = Field(
        default=None, description="Vector embedding of the content."
    )
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    access_count: int = Field(default=0, description="Number of times this memory was retrieved.")

    def to_context_string(self) -> str:
        """Format this memory for injection into the agent's context."""
        time_str = time.strftime("%Y-%m-%d", time.localtime(self.created_at))
        return f"[{self.type.value}] ({time_str}) {self.summary or self.content}"


class MemorySearchResult(BaseModel):
    """Result from a memory search/retrieval operation."""

    entry: MemoryEntry
    relevance_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Relevance score from retrieval."
    )
    source: str = Field(
        default="vector",
        description="Retrieval source (vector, bm25, hybrid)."
    )
