"""Discord channel adapter.

Integrates with Discord using discord.py for bot-based communication.
Requires: pip install hivecore[discord]
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from hivecore.channels.base import BaseChannel

logger = logging.getLogger(__name__)


class DiscordChannel(BaseChannel):
    """Discord bot channel adapter.

    Connects to Discord as a bot and routes messages through
    the HiveCore message router.
    """

    def __init__(
        self,
        token: str,
        guild_ids: Optional[list[str]] = None,
    ) -> None:
        self._token = token
        self._guild_ids = guild_ids or []
        self._bot = None
        self._message_handler = None
        self._connected = False

    @property
    def name(self) -> str:
        return "discord"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the Discord bot."""
        try:
            import discord
            from discord.ext import commands
        except ImportError:
            raise ImportError("discord.py not installed. Install with: pip install hivecore[discord]")

        intents = discord.Intents.default()
        intents.message_content = True

        self._bot = commands.Bot(command_prefix="!", intents=intents)

        @self._bot.event
        async def on_ready() -> None:
            self._connected = True
            logger.info("Discord bot connected as %s", self._bot.user)

        @self._bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author == self._bot.user:
                return

            # Check if bot is mentioned or in DM
            is_mentioned = self._bot.user in message.mentions if self._bot.user else False
            is_dm = isinstance(message.channel, discord.DMChannel)

            if is_mentioned or is_dm:
                # Remove mention from content
                content = message.content
                if self._bot.user:
                    content = content.replace(f"<@{self._bot.user.id}>", "").strip()

                if self._message_handler and content:
                    await self._message_handler(
                        channel_name="discord",
                        sender_id=str(message.channel.id),
                        message_text=content,
                        discord_message=message,
                    )

        await self._bot.start(self._token)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        if self._bot:
            await self._bot.close()
            self._connected = False

    async def send_message(
        self,
        content: str,
        recipient: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a message to a Discord channel."""
        if not self._bot:
            return

        if recipient:
            channel = self._bot.get_channel(int(recipient))
            if channel:
                # Split long messages (Discord has 2000 char limit)
                for chunk in _chunk_message(content, 2000):
                    await channel.send(chunk)

    async def send_file(
        self,
        file_path: str,
        recipient: Optional[str] = None,
        caption: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a file to a Discord channel."""
        import discord

        if not self._bot or not recipient:
            return

        channel = self._bot.get_channel(int(recipient))
        if channel:
            await channel.send(content=caption, file=discord.File(file_path))


class TelegramChannel(BaseChannel):
    """Telegram bot channel adapter.

    Connects to Telegram using python-telegram-bot.
    Requires: pip install hivecore[telegram]
    """

    def __init__(
        self,
        token: str,
        allowed_chat_ids: Optional[list[int]] = None,
    ) -> None:
        self._token = token
        self._allowed_chat_ids = allowed_chat_ids or []
        self._app = None
        self._message_handler = None
        self._connected = False

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the Telegram bot."""
        try:
            from telegram import Update
            from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
        except ImportError:
            raise ImportError(
                "python-telegram-bot not installed. Install with: pip install hivecore[telegram]"
            )

        self._app = ApplicationBuilder().token(self._token).build()

        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.message or not update.message.text:
                return

            chat_id = update.message.chat_id
            if self._allowed_chat_ids and chat_id not in self._allowed_chat_ids:
                return

            if self._message_handler:
                await self._message_handler(
                    channel_name="telegram",
                    sender_id=str(chat_id),
                    message_text=update.message.text,
                )

        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        self._connected = True
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._connected = False

    async def send_message(
        self,
        content: str,
        recipient: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a message to a Telegram chat."""
        if not self._app or not recipient:
            return

        # Split long messages (Telegram has 4096 char limit)
        for chunk in _chunk_message(content, 4096):
            await self._app.bot.send_message(chat_id=int(recipient), text=chunk)

    async def send_file(
        self,
        file_path: str,
        recipient: Optional[str] = None,
        caption: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Send a file to a Telegram chat."""
        if not self._app or not recipient:
            return

        with open(file_path, "rb") as f:
            await self._app.bot.send_document(
                chat_id=int(recipient), document=f, caption=caption
            )


def _chunk_message(content: str, max_length: int) -> list[str]:
    """Split a message into chunks that fit within a platform's limit."""
    if len(content) <= max_length:
        return [content]

    chunks = []
    while content:
        if len(content) <= max_length:
            chunks.append(content)
            break
        # Try to split at a newline
        split_pos = content.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        chunks.append(content[:split_pos])
        content = content[split_pos:].lstrip("\n")

    return chunks
