"""Abstract channel interface.

Defines the contract that all communication channels must implement.
Each channel (Discord, Telegram, Web, iMessage) adapts its platform's
API to this unified interface.
"""

from __future__ import annotations

import abc
from typing import Any, Optional


class BaseChannel(abc.ABC):
    """Abstract base class for communication channels.

    All channel adapters must implement this interface to integrate
    with HiveCore's message routing system.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Channel identifier name."""
        ...

    @abc.abstractmethod
    async def start(self) -> None:
        """Start the channel connection/listener."""
        ...

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop the channel connection/listener."""
        ...

    @abc.abstractmethod
    async def send_message(
        self,
        content: str,
        recipient: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a message through this channel.

        Args:
            content: Message text content.
            recipient: Optional target recipient/channel ID.
            **kwargs: Channel-specific parameters.
        """
        ...

    @abc.abstractmethod
    async def send_file(
        self,
        file_path: str,
        recipient: Optional[str] = None,
        caption: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a file through this channel.

        Args:
            file_path: Path to the file to send.
            recipient: Optional target recipient/channel ID.
            caption: Optional file caption.
            **kwargs: Channel-specific parameters.
        """
        ...

    def set_message_handler(self, handler: Any) -> None:
        """Set the callback for incoming messages.

        The handler receives (channel_name, sender_id, message_text).
        """
        self._message_handler = handler

    @property
    def is_connected(self) -> bool:
        """Whether the channel is currently connected."""
        return False
