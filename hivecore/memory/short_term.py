"""Short-term memory: conversation buffer with sliding window.

Manages the active conversation context that gets sent to the LLM.
Handles windowing, token-based truncation, and summarization triggers.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Optional

from hivecore.core.messages import Message, Role

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Sliding window conversation buffer.

    Maintains a fixed-size window of recent messages. When the window
    fills up or token count exceeds the threshold, older messages are
    summarized and compacted.
    """

    def __init__(
        self,
        max_messages: int = 50,
        compaction_token_threshold: int = 4000,
    ) -> None:
        self.max_messages = max_messages
        self.compaction_token_threshold = compaction_token_threshold
        self._messages: deque[Message] = deque(maxlen=max_messages)
        self._system_message: Optional[Message] = None

    def add(self, message: Message) -> None:
        """Add a message to the buffer.

        Args:
            message: The message to add.
        """
        if message.role == Role.SYSTEM:
            self._system_message = message
        else:
            self._messages.append(message)

    def get_messages(self) -> list[Message]:
        """Get all messages in the buffer, system message first.

        Returns:
            Ordered list of messages for LLM context.
        """
        messages = []
        if self._system_message:
            messages.append(self._system_message)
        messages.extend(self._messages)
        return messages

    @property
    def total_tokens(self) -> int:
        """Estimate total tokens in the buffer."""
        total = 0
        if self._system_message:
            total += self._system_message.token_estimate
        total += sum(m.token_estimate for m in self._messages)
        return total

    @property
    def needs_compaction(self) -> bool:
        """Check if the buffer should be compacted."""
        return (
            len(self._messages) >= self.max_messages - 5
            or self.total_tokens > self.compaction_token_threshold
        )

    def get_messages_for_compaction(self, keep_recent: int = 10) -> list[Message]:
        """Get older messages that should be compacted/summarized.

        Args:
            keep_recent: Number of recent messages to keep.

        Returns:
            List of messages to be compacted.
        """
        messages = list(self._messages)
        if len(messages) <= keep_recent:
            return []
        return messages[:-keep_recent]

    def compact(self, summary: str, keep_recent: int = 10) -> None:
        """Replace older messages with a summary.

        Args:
            summary: Summary of the compacted messages.
            keep_recent: Number of recent messages to keep.
        """
        messages = list(self._messages)
        if len(messages) <= keep_recent:
            return

        recent = messages[-keep_recent:]
        self._messages.clear()

        # Add summary as a system-like context message
        summary_msg = Message.assistant(
            content=f"[Previous conversation summary]\n{summary}"
        )
        self._messages.append(summary_msg)

        for msg in recent:
            self._messages.append(msg)

        logger.debug(
            "Compacted %d messages into summary, kept %d recent",
            len(messages) - keep_recent,
            keep_recent,
        )

    def clear(self) -> None:
        """Clear all messages except the system message."""
        self._messages.clear()

    @property
    def message_count(self) -> int:
        """Number of non-system messages in the buffer."""
        return len(self._messages)
