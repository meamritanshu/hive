"""Status CLI command handler."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def handle_status() -> None:
    """Show workstation status."""
    from hivecore import __version__
    from hivecore.config.settings import get_settings

    settings = get_settings()

    status_info = (
        f"[bold blue]HiveCore[/bold blue] v{__version__}\n\n"
        f"Model: {settings.llm.model}\n"
        f"Provider: {settings.llm.provider}\n"
        f"Memory backend: {settings.memory.backend}\n"
        f"Data directory: {settings.memory.data_dir}\n"
        f"Skills directory: {settings.skills.directory}"
    )

    console.print(Panel(status_info, title="Workstation Status", border_style="blue"))

    # Show channels
    table = Table(title="Channels")
    table.add_column("Channel", style="cyan")
    table.add_column("Status", style="green")

    table.add_row("Web Console", "[green]Available[/green]")
    table.add_row("Discord", _check_channel_status("discord"))
    table.add_row("Telegram", _check_channel_status("telegram"))
    table.add_row("iMessage", _check_channel_status("imessage"))

    console.print(table)


def _check_channel_status(channel: str) -> str:
    """Check if a channel is configured and available."""
    try:
        from hivecore.config.settings import get_settings

        settings = get_settings()
        channel_config = getattr(settings.channels, channel, None)
        if channel_config and channel_config.enabled:
            return "[green]Enabled[/green]"
        return "[dim]Disabled[/dim]"
    except Exception:
        return "[dim]Not configured[/dim]"
