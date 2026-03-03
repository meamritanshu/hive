"""File-based memory storage.

Stores memories as human-readable Markdown files in the .hivecore/memory/
directory. This is the "memory as files" approach inspired by ReMe,
making memories portable, editable, and version-controllable.

Directory structure:
    .hivecore/memory/
    ├── MEMORY.md              # Long-term consolidated memory
    ├── daily/
    │   ├── 2026-03-01.md      # Daily conversation logs
    │   ├── 2026-03-02.md
    │   └── ...
    └── knowledge/
        ├── personal.md        # User preferences & personal info
        ├── tasks.md           # Task execution history
        └── tools.md           # Tool usage patterns
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Optional

from hivecore.memory.types import MemoryEntry, MemoryType

logger = logging.getLogger(__name__)


class FileMemory:
    """File-based long-term memory storage.

    Stores memories as Markdown files that are:
    - Human-readable and editable
    - Portable (just copy the directory)
    - Git-friendly (can version control your memory)
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.daily_dir = data_dir / "daily"
        self.knowledge_dir = data_dir / "knowledge"
        self.main_memory_file = data_dir / "MEMORY.md"

    async def initialize(self) -> None:
        """Create directory structure if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        # Create main memory file if it doesn't exist
        if not self.main_memory_file.exists():
            header = (
                "# HiveCore Long-Term Memory\n\n"
                "This file contains consolidated long-term memory entries.\n"
                "You can edit this file manually.\n\n"
                f"Created: {datetime.datetime.now().isoformat()}\n\n"
                "---\n\n"
            )
            self.main_memory_file.write_text(header, encoding="utf-8")

        # Create knowledge category files
        for category in ("personal", "tasks", "tools"):
            path = self.knowledge_dir / f"{category}.md"
            if not path.exists():
                path.write_text(
                    f"# {category.title()} Knowledge\n\n"
                    f"Auto-managed by HiveCore. You can edit this file.\n\n---\n\n",
                    encoding="utf-8",
                )

    async def store(self, entry: MemoryEntry) -> None:
        """Store a memory entry to the appropriate file.

        Args:
            entry: The memory entry to store.
        """
        # Store in daily log
        await self._append_to_daily_log(entry)

        # Store in category-specific knowledge file
        if entry.type in (MemoryType.PERSONAL, MemoryType.TASK, MemoryType.TOOL):
            await self._append_to_knowledge(entry)

    async def store_conversation(
        self,
        user_message: str,
        assistant_message: str,
    ) -> None:
        """Store a conversation turn in the daily log.

        Args:
            user_message: The user's message.
            assistant_message: The agent's response.
        """
        today = datetime.date.today().isoformat()
        daily_file = self.daily_dir / f"{today}.md"

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        entry_text = (
            f"\n### {timestamp}\n\n"
            f"**User:** {user_message}\n\n"
            f"**Agent:** {assistant_message}\n\n"
            f"---\n"
        )

        if daily_file.exists():
            content = daily_file.read_text(encoding="utf-8")
            content += entry_text
        else:
            content = (
                f"# Daily Log - {today}\n\n"
                f"---\n"
                f"{entry_text}"
            )

        daily_file.write_text(content, encoding="utf-8")

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Search memory files for relevant content.

        Uses simple keyword matching on file contents.
        For semantic search, use VectorMemory instead.

        Args:
            query: Search query.
            max_results: Maximum results to return.

        Returns:
            List of matching memory dicts.
        """
        results = []
        query_lower = query.lower()
        query_terms = query_lower.split()

        # Search daily logs (most recent first)
        daily_files = sorted(self.daily_dir.glob("*.md"), reverse=True)
        for daily_file in daily_files[:30]:  # Last 30 days
            content = daily_file.read_text(encoding="utf-8")
            if any(term in content.lower() for term in query_terms):
                # Extract relevant sections
                sections = content.split("###")
                for section in sections[1:]:  # Skip header
                    if any(term in section.lower() for term in query_terms):
                        results.append({
                            "content": section.strip()[:500],
                            "type": "episodic",
                            "source": daily_file.name,
                            "relevance": _simple_relevance(section, query_terms),
                        })
                        if len(results) >= max_results:
                            break
            if len(results) >= max_results:
                break

        # Search knowledge files
        for knowledge_file in self.knowledge_dir.glob("*.md"):
            content = knowledge_file.read_text(encoding="utf-8")
            if any(term in content.lower() for term in query_terms):
                category = knowledge_file.stem
                sections = content.split("\n## ")
                for section in sections[1:]:
                    if any(term in section.lower() for term in query_terms):
                        results.append({
                            "content": section.strip()[:500],
                            "type": category,
                            "source": knowledge_file.name,
                            "relevance": _simple_relevance(section, query_terms),
                        })

        # Sort by relevance
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:max_results]

    async def get_recent_context(self, days: int = 3, max_entries: int = 20) -> str:
        """Get recent conversation context from daily logs.

        Args:
            days: Number of days to look back.
            max_entries: Maximum entries to return.

        Returns:
            Formatted string of recent context.
        """
        entries = []
        today = datetime.date.today()

        for i in range(days):
            date = today - datetime.timedelta(days=i)
            daily_file = self.daily_dir / f"{date.isoformat()}.md"
            if daily_file.exists():
                content = daily_file.read_text(encoding="utf-8")
                sections = content.split("###")
                for section in sections[-max_entries:]:
                    if section.strip():
                        entries.append(section.strip()[:300])

        return "\n---\n".join(entries) if entries else ""

    async def _append_to_daily_log(self, entry: MemoryEntry) -> None:
        """Append a memory entry to today's daily log."""
        today = datetime.date.today().isoformat()
        daily_file = self.daily_dir / f"{today}.md"

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        entry_text = (
            f"\n### {timestamp} [{entry.type.value}]\n\n"
            f"{entry.content}\n\n"
            f"---\n"
        )

        if daily_file.exists():
            content = daily_file.read_text(encoding="utf-8")
            content += entry_text
        else:
            content = f"# Daily Log - {today}\n\n---\n{entry_text}"

        daily_file.write_text(content, encoding="utf-8")

    async def _append_to_knowledge(self, entry: MemoryEntry) -> None:
        """Append to the appropriate knowledge category file."""
        category_map = {
            MemoryType.PERSONAL: "personal",
            MemoryType.TASK: "tasks",
            MemoryType.TOOL: "tools",
        }
        category = category_map.get(entry.type, "personal")
        knowledge_file = self.knowledge_dir / f"{category}.md"

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        new_content = f"\n## {timestamp}\n\n{entry.content}\n\n"

        content = knowledge_file.read_text(encoding="utf-8")
        content += new_content
        knowledge_file.write_text(content, encoding="utf-8")

    async def get_stats(self) -> dict[str, Any]:
        """Get file memory statistics."""
        daily_count = len(list(self.daily_dir.glob("*.md")))
        total_size = sum(f.stat().st_size for f in self.data_dir.rglob("*.md"))

        return {
            "daily_logs": daily_count,
            "total_size_kb": total_size / 1024,
            "knowledge_files": len(list(self.knowledge_dir.glob("*.md"))),
            "data_dir": str(self.data_dir),
        }


def _simple_relevance(text: str, query_terms: list[str]) -> float:
    """Calculate a simple relevance score based on term frequency."""
    text_lower = text.lower()
    if not query_terms:
        return 0.0
    matches = sum(1 for term in query_terms if term in text_lower)
    return matches / len(query_terms)
