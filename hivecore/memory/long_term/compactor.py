"""Memory compaction and summarization.

Handles compressing old conversation history into concise summaries
to manage context window usage while preserving important information.

Tiered Memory Architecture
--------------------------
Memory is stored in three tiers of increasing compression:

Tier 1 – Raw (last 7 days)
    Full episodic logs preserved verbatim.  These are the freshest memories
    and are kept at full fidelity for detailed recall.

Tier 2 – Condensed (weekly summaries, 8–90 days)
    At the end of each week, Tier 1 entries are compressed into a weekly
    summary paragraph using the LLM.  Lossy by design — preserves the gist
    without storing every exchange.

Tier 3 – Entities (permanent knowledge, >90 days)
    Facts, preferences, people, places, and ongoing projects are extracted
    from Tier 2 summaries and promoted to the ``knowledge/`` Markdown files
    (``personal.md``, ``tasks.md``, ``tools.md``) as permanent, named
    entities.  Tier 2 summaries older than 90 days are then deleted.

The ``TieredMemoryCompactor`` implements this pipeline.  The legacy
``MemoryCompactor`` class is kept for backward compatibility.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from hivecore.core.messages import Message

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier age thresholds (seconds)
# ---------------------------------------------------------------------------
TIER1_MAX_AGE_DAYS = 7
TIER2_MAX_AGE_DAYS = 90


# ---------------------------------------------------------------------------
# Legacy compactor (kept for backward compatibility)
# ---------------------------------------------------------------------------

class MemoryCompactor:
    """Compacts conversation history into summaries.

    Uses the LLM to summarize older conversation messages,
    reducing token usage while preserving key information.
    """

    SUMMARIZE_PROMPT = (
        "Summarize the following conversation history. Focus on:\n"
        "1. Key decisions and outcomes\n"
        "2. User preferences revealed\n"
        "3. Important facts learned\n"
        "4. Tasks completed or pending\n\n"
        "Be concise but preserve all important context.\n\n"
        "Conversation:\n{conversation}\n\n"
        "Summary:"
    )

    EXTRACT_FACTS_PROMPT = (
        "Extract key facts and user preferences from this conversation.\n"
        "Format as a bullet list. Only include significant, reusable information.\n\n"
        "Conversation:\n{conversation}\n\n"
        "Key facts:"
    )

    def __init__(self, llm_provider: Any = None) -> None:
        self._llm = llm_provider

    async def summarize_messages(self, messages: list[Message]) -> str:
        """Summarize a list of messages into a concise summary."""
        if not messages:
            return ""

        conversation_text = self._format_messages(messages)

        if self._llm:
            try:
                prompt = self.SUMMARIZE_PROMPT.format(conversation=conversation_text)
                response = await self._llm.complete(messages=[Message.user(prompt)])
                return response.content
            except Exception as e:
                logger.warning("LLM summarization failed: %s. Falling back to truncation.", e)

        return self._truncate_summary(conversation_text)

    async def extract_facts(self, messages: list[Message]) -> list[str]:
        """Extract key facts and preferences from messages."""
        if not messages:
            return []

        conversation_text = self._format_messages(messages)

        if self._llm:
            try:
                prompt = self.EXTRACT_FACTS_PROMPT.format(conversation=conversation_text)
                response = await self._llm.complete(messages=[Message.user(prompt)])
                facts = []
                for line in response.content.split("\n"):
                    line = line.strip()
                    if line.startswith(("- ", "* ", "• ")):
                        facts.append(line[2:].strip())
                    elif line and line[0].isdigit() and len(line) > 2 and line[1] == ".":
                        facts.append(line[2:].strip())
                return facts
            except Exception as e:
                logger.warning("Fact extraction failed: %s", e)

        return []

    def _format_messages(self, messages: list[Message]) -> str:
        lines = []
        for msg in messages:
            role = msg.role.value.capitalize()
            content = msg.content[:500]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _truncate_summary(self, text: str, max_length: int = 500) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."


# ---------------------------------------------------------------------------
# Tiered compactor
# ---------------------------------------------------------------------------

class TieredMemoryCompactor:
    """Implements three-tier memory compaction for long-running agents.

    Tier progression
    ----------------
    - **Tier 1 → Tier 2**: Weekly summaries.  At the end of each 7-day
      window, all Tier 1 (raw episodic) entries older than
      ``TIER1_MAX_AGE_DAYS`` are summarised into a single Tier 2 entry.
      The originals are then deleted from the vector store.

    - **Tier 2 → Tier 3 (entity extraction)**: Tier 2 entries older than
      ``TIER2_MAX_AGE_DAYS`` are processed to extract named entities and
      facts.  Extracted facts are written to the appropriate ``knowledge/``
      Markdown category (personal, task, tool).  The Tier 2 entry is then
      deleted.

    Usage
    -----
    Call ``run_compaction_cycle(memory_manager)`` from the ``Heartbeat``
    or ``Scheduler`` on a regular interval (e.g. daily).

    Parameters
    ----------
    llm_provider:
        An ``LLMProvider`` instance used for summarisation and extraction.
        If None, falls back to simple truncation.
    """

    # Prompts -----------------------------------------------------------

    WEEKLY_SUMMARY_PROMPT = (
        "You are compacting a week of conversation logs into a concise summary.\n"
        "Focus on:\n"
        "1. The main topics discussed\n"
        "2. Decisions made and outcomes\n"
        "3. User preferences and patterns revealed\n"
        "4. Pending tasks or open questions\n\n"
        "Write 3-5 sentences maximum. Be factual and dense.\n\n"
        "Logs:\n{logs}\n\n"
        "Weekly summary:"
    )

    ENTITY_EXTRACTION_PROMPT = (
        "Extract permanent knowledge from the following weekly summary.\n"
        "Categorise each fact as one of: personal, task, or tool.\n\n"
        "Format:\n"
        "  personal: <fact about the user, their life, preferences>\n"
        "  task: <ongoing project, goal, or recurring task>\n"
        "  tool: <tool, skill, or workflow the user relies on>\n\n"
        "Only include facts that are likely to remain relevant long-term.\n"
        "One fact per line. If no facts apply, respond with 'none'.\n\n"
        "Summary:\n{summary}\n\n"
        "Extracted facts:"
    )

    def __init__(self, llm_provider: Any = None) -> None:
        self._llm = llm_provider
        self._base_compactor = MemoryCompactor(llm_provider)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run_compaction_cycle(self, memory_manager: Any) -> dict[str, int]:
        """Run one full tiered compaction cycle.

        Args:
            memory_manager: A ``MemoryManager`` instance providing access to
                all memory stores.

        Returns:
            Dict summarising what was processed::

                {
                    "tier1_compacted": 42,   # raw entries summarised
                    "tier2_promoted": 3,      # weekly summaries promoted to entities
                    "entities_extracted": 12, # new entity facts stored
                }
        """
        stats: dict[str, int] = {
            "tier1_compacted": 0,
            "tier2_promoted": 0,
            "entities_extracted": 0,
        }

        stats["tier1_compacted"] = await self._compact_tier1_to_tier2(memory_manager)
        promoted, entities = await self._compact_tier2_to_tier3(memory_manager)
        stats["tier2_promoted"] = promoted
        stats["entities_extracted"] = entities

        if any(stats.values()):
            logger.info(
                "Tiered compaction cycle complete: %s", stats
            )
            # Auto-commit to git if MemoryGitSync is wired up
            git_sync = getattr(memory_manager, "_git_sync", None)
            if git_sync is not None:
                import datetime
                week_label = datetime.date.today().strftime("%Y-W%W")
                await git_sync.commit(f"chore: weekly compaction {week_label}")

        return stats

    # ------------------------------------------------------------------
    # Tier 1 → Tier 2
    # ------------------------------------------------------------------

    async def _compact_tier1_to_tier2(self, memory_manager: Any) -> int:
        """Summarise raw episodic entries older than TIER1_MAX_AGE_DAYS.

        Groups entries by ISO week and creates one weekly summary per group.
        Original entries are deleted after summarisation.

        Returns:
            Number of raw entries compacted.
        """
        from hivecore.memory.types import MemoryEntry, MemoryType

        cutoff = time.time() - TIER1_MAX_AGE_DAYS * 86400

        # Fetch all episodic tier-1 entries from the vector store
        if memory_manager._vector_memory is None:
            return 0

        try:
            store = memory_manager._vector_memory._store
            all_entries = await store.list_all(
                filter_metadata={"mem_type": "episodic", "tier": "1"},
                limit=10000,
            )
        except Exception as e:
            logger.warning("Tier 1 compaction: failed to fetch entries: %s", e)
            return 0

        # Filter to entries older than the cutoff
        old_entries = [
            e for e in all_entries
            if float(e.get("metadata", {}).get("created_at", time.time())) < cutoff
        ]

        if not old_entries:
            return 0

        # Group by ISO year-week
        week_groups: dict[str, list[dict[str, Any]]] = {}
        for entry in old_entries:
            ts = float(entry.get("metadata", {}).get("created_at", time.time()))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
            week_groups.setdefault(week_key, []).append(entry)

        compacted_count = 0
        for week_key, entries in week_groups.items():
            try:
                # Build a text block for the week
                logs = "\n---\n".join(e.get("content", "") for e in entries)
                summary = await self._summarise_week(logs)

                # Store as a Tier 2 entry
                tier2_entry = MemoryEntry(
                    type=MemoryType.EPISODIC,
                    content=summary,
                    source="weekly_compaction",
                )
                # Tag with tier and week for downstream processing
                {
                    "id": tier2_entry.id,
                    "content": summary,
                    "mem_type": "episodic",
                    "tier": "2",
                    "week": week_key,
                    "created_at": time.time(),
                }
                await store.upsert(
                    id=tier2_entry.id,
                    content=summary,
                    metadata={
                        "mem_type": "episodic",
                        "tier": "2",
                        "week": week_key,
                        "created_at": time.time(),
                    },
                )

                # Delete originals
                for entry in entries:
                    await store.delete(entry["id"])

                compacted_count += len(entries)
                logger.debug(
                    "Compacted %d Tier 1 entries for %s into weekly summary",
                    len(entries),
                    week_key,
                )
            except Exception as e:
                logger.warning("Tier 1 compaction failed for week %s: %s", week_key, e)

        return compacted_count

    async def _summarise_week(self, logs: str) -> str:
        """Use the LLM to produce a weekly summary, with truncation fallback."""
        if self._llm:
            try:
                prompt = self.WEEKLY_SUMMARY_PROMPT.format(logs=logs[:8000])
                response = await self._llm.complete(messages=[Message.user(prompt)])
                return response.content.strip()
            except Exception as e:
                logger.warning("Weekly summarisation LLM failed: %s", e)
        # Fallback: return first 500 chars
        return logs[:500] + ("..." if len(logs) > 500 else "")

    # ------------------------------------------------------------------
    # Tier 2 → Tier 3 (entity extraction)
    # ------------------------------------------------------------------

    async def _compact_tier2_to_tier3(
        self, memory_manager: Any
    ) -> tuple[int, int]:
        """Promote old Tier 2 weekly summaries to permanent knowledge entities.

        For each Tier 2 entry older than ``TIER2_MAX_AGE_DAYS``:
        1. Extract named entities/facts via the LLM.
        2. Write facts to the appropriate ``knowledge/`` Markdown file.
        3. Delete the Tier 2 entry from the vector store.

        Returns:
            (number of Tier 2 entries promoted, total entities extracted)
        """
        from hivecore.memory.types import MemoryEntry, MemoryType

        cutoff = time.time() - TIER2_MAX_AGE_DAYS * 86400

        if memory_manager._vector_memory is None:
            return 0, 0

        try:
            store = memory_manager._vector_memory._store
            tier2_entries = await store.list_all(
                filter_metadata={"tier": "2"},
                limit=1000,
            )
        except Exception as e:
            logger.warning("Tier 2 promotion: failed to fetch entries: %s", e)
            return 0, 0

        old_tier2 = [
            e for e in tier2_entries
            if float(e.get("metadata", {}).get("created_at", time.time())) < cutoff
        ]

        if not old_tier2:
            return 0, 0

        promoted = 0
        total_entities = 0

        for entry in old_tier2:
            try:
                summary = entry.get("content", "")
                facts = await self._extract_entities(summary)

                for category, text in facts:
                    mem_type = {
                        "personal": MemoryType.PERSONAL,
                        "task": MemoryType.TASK,
                        "tool": MemoryType.TOOL,
                    }.get(category, MemoryType.PERSONAL)

                    fact_entry = MemoryEntry(
                        type=mem_type,
                        content=text,
                        source="entity_extraction",
                    )
                    await memory_manager.store(fact_entry)
                    total_entities += 1

                    # Write to the knowledge Markdown file as well
                    if memory_manager._file_memory:
                        try:
                            await memory_manager._file_memory.store(fact_entry)
                        except Exception:
                            pass

                # Delete the Tier 2 entry
                await store.delete(entry["id"])
                promoted += 1
                logger.debug(
                    "Promoted Tier 2 entry %s → %d entities", entry["id"], len(facts)
                )
            except Exception as e:
                logger.warning(
                    "Tier 2 promotion failed for entry %s: %s", entry.get("id"), e
                )

        return promoted, total_entities

    async def _extract_entities(
        self, summary: str
    ) -> list[tuple[str, str]]:
        """Extract categorised entity facts from a weekly summary.

        Returns:
            List of ``(category, fact_text)`` tuples where category is one of
            ``"personal"``, ``"task"``, or ``"tool"``.
        """
        if not self._llm:
            return []

        try:
            prompt = self.ENTITY_EXTRACTION_PROMPT.format(summary=summary[:4000])
            response = await self._llm.complete(messages=[Message.user(prompt)])
            facts: list[tuple[str, str]] = []
            for line in response.content.split("\n"):
                line = line.strip()
                if not line or line.lower() == "none":
                    continue
                for category in ("personal", "task", "tool"):
                    prefix = f"{category}:"
                    if line.lower().startswith(prefix):
                        text = line[len(prefix):].strip()
                        if text:
                            facts.append((category, text))
                        break
            return facts
        except Exception as e:
            logger.warning("Entity extraction LLM failed: %s", e)
            return []
