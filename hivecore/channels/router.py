"""Message router - routes messages between channels and the agent.

Normalizes incoming messages from any channel, sends them to the agent,
and routes responses back to the originating channel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from hivecore.channels.base import BaseChannel

logger = logging.getLogger(__name__)


class ChannelRouter:
    """Central message router for multi-channel access.

    Routes messages between communication channels and the agent:
    1. Receives messages from any channel
    2. Normalizes them to the internal format
    3. Sends to the agent for processing
    4. Routes the response back to the originating channel
    """

    def __init__(self, agent: Any = None) -> None:
        self._agent = agent
        self._channels: dict[str, BaseChannel] = {}
        self._running = False

    def register_channel(self, name: str, channel: BaseChannel) -> None:
        """Register a communication channel.

        Args:
            name: Channel identifier.
            channel: The channel instance.
        """
        channel.set_message_handler(self._handle_incoming)
        self._channels[name] = channel
        logger.debug("Registered channel: %s", name)

    async def start_all(self) -> None:
        """Start all registered channels."""
        self._running = True
        tasks = []
        for name, channel in self._channels.items():
            try:
                tasks.append(asyncio.create_task(channel.start()))
                logger.info("Starting channel: %s", name)
            except Exception as e:
                logger.error("Failed to start channel %s: %s", name, e)

        if tasks:
            # Don't await -- channels run in background
            for task in tasks:
                task.add_done_callback(self._channel_done_callback)

    async def stop_all(self) -> None:
        """Stop all registered channels."""
        self._running = False
        for name, channel in self._channels.items():
            try:
                await channel.stop()
                logger.info("Stopped channel: %s", name)
            except Exception as e:
                logger.error("Error stopping channel %s: %s", name, e)

    async def _handle_incoming(
        self,
        channel_name: str,
        sender_id: str,
        message_text: str,
        **kwargs: Any,
    ) -> None:
        """Handle an incoming message from any channel.

        Args:
            channel_name: Source channel name.
            sender_id: Sender identifier.
            message_text: Message content.
        """
        if not self._agent:
            logger.warning("No agent configured for router")
            return

        logger.debug("Incoming from %s (%s): %s", channel_name, sender_id, message_text[:100])

        try:
            # Process through agent
            response = await self._agent.run(message_text)

            # Route response back
            channel = self._channels.get(channel_name)
            if channel:
                await channel.send_message(
                    content=response.content,
                    recipient=sender_id,
                )
        except Exception as e:
            logger.error("Error processing message from %s: %s", channel_name, e)

            # Try to send error response
            channel = self._channels.get(channel_name)
            if channel:
                try:
                    await channel.send_message(
                        content=f"Sorry, I encountered an error: {str(e)[:200]}",
                        recipient=sender_id,
                    )
                except Exception:
                    pass

    async def send_to_channel(
        self,
        channel_name: str,
        content: str,
        recipient: Optional[str] = None,
    ) -> bool:
        """Send a message to a specific channel (for scheduled tasks).

        Args:
            channel_name: Target channel.
            content: Message content.
            recipient: Optional recipient.

        Returns:
            True if sent successfully.
        """
        channel = self._channels.get(channel_name)
        if not channel:
            logger.warning("Channel not found: %s", channel_name)
            return False

        try:
            await channel.send_message(content=content, recipient=recipient)
            return True
        except Exception as e:
            logger.error("Failed to send to %s: %s", channel_name, e)
            return False

    def _channel_done_callback(self, task: asyncio.Task) -> None:
        """Handle channel task completion."""
        if task.exception():
            logger.error("Channel task failed: %s", task.exception())

    def list_channels(self) -> list[dict[str, Any]]:
        """List all registered channels and their status."""
        return [
            {
                "name": name,
                "type": channel.__class__.__name__,
                "connected": channel.is_connected,
            }
            for name, channel in self._channels.items()
        ]
