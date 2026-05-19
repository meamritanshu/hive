"""Agent lifecycle management.

Handles startup, shutdown, health checks, and the overall
orchestration of all HiveCore subsystems.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from hivecore.config.settings import HiveSettings, get_settings

logger = logging.getLogger(__name__)


async def start_workstation(
    host: str = "127.0.0.1",
    port: int = 8088,
    no_web: bool = False,
    config_path: str | None = None,
) -> None:
    """Start the HiveCore workstation.

    Initializes and starts all subsystems:
    1. Configuration loading
    2. Agent initialization (LLM, tools, memory)
    3. Skill loading
    4. Channel connections
    5. Scheduler
    6. Web console (if enabled)

    Args:
        host: Web console host.
        port: Web console port.
        no_web: If True, skip starting the web console.
        config_path: Optional path to config file.
    """
    from pathlib import Path

    from hivecore.core.agent import Agent
    from hivecore.skills.loader import SkillLoader

    # Load settings
    settings = get_settings(Path(config_path) if config_path else None)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Starting HiveCore workstation...")

    # Initialize agent
    agent = Agent(settings=settings)
    await agent.initialize()
    logger.info("Agent initialized.")

    # Load skills
    skill_loader = SkillLoader([settings.skills.directory])
    skills = await skill_loader.load_all()
    for skill in skills:
        for tool in skill.get_tools():
            agent.register_tool(tool)
    logger.info("Loaded %d skills.", len(skills))

    # Start scheduler
    if settings.scheduler.enabled:
        from hivecore.automation.scheduler import Scheduler

        scheduler = Scheduler()

        async def _skill_executor(skill_name: str, params: dict) -> str:
            # ReAct loop or just run the tool directly
            tool = agent._tools.get(skill_name)
            if tool:
                return await tool.execute(**params)
            return f"Error: Skill {skill_name} not found"

        scheduler.set_skill_executor(_skill_executor)
        scheduler.start()
        logger.info("Scheduler started.")

    # Start channel connections
    await _start_channels(settings, agent)

    # Start web console
    if not no_web:
        await _start_web_server(host, port, agent, settings)
    else:
        # Keep running without web console
        logger.info("Running without web console. Press Ctrl+C to stop.")
        stop_event = asyncio.Event()

        def _signal_handler() -> None:
            stop_event.set()

        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGINT, _signal_handler)
            loop.add_signal_handler(signal.SIGTERM, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

        await stop_event.wait()

    # Shutdown
    logger.info("Shutting down HiveCore...")
    await agent.shutdown()
    if settings.scheduler.enabled:
        scheduler.stop()
    logger.info("HiveCore stopped.")


async def _start_web_server(
    host: str,
    port: int,
    agent: Agent,
    settings: HiveSettings,
) -> None:
    """Start the FastAPI web console."""
    import uvicorn

    from hivecore.web.api.app import create_app

    app = create_app(agent=agent, settings=settings)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _start_channels(settings: HiveSettings, agent: Agent) -> None:
    """Start configured communication channels."""
    from hivecore.channels.router import ChannelRouter

    router = ChannelRouter(agent=agent)

    # Start Discord if configured
    if settings.channels.discord.enabled:
        try:
            from hivecore.channels.discord_bot import DiscordChannel

            discord = DiscordChannel(
                token=settings.channels.discord.token or "",
                guild_ids=settings.channels.discord.guild_ids,
            )
            router.register_channel("discord", discord)
            logger.info("Discord channel registered.")
        except ImportError:
            logger.warning("discord.py not installed. Skipping Discord channel.")

    # Start Telegram if configured
    if settings.channels.telegram.enabled:
        try:
            from hivecore.channels.telegram_bot import TelegramChannel

            telegram = TelegramChannel(
                token=settings.channels.telegram.token or "",
                allowed_chat_ids=settings.channels.telegram.allowed_chat_ids,
            )
            router.register_channel("telegram", telegram)
            logger.info("Telegram channel registered.")
        except ImportError:
            logger.warning("python-telegram-bot not installed. Skipping Telegram channel.")

    # Start all registered channels
    await router.start_all()
