"""Config CLI command handler."""

from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()


def handle_config(
    show: bool = False,
    init: bool = False,
    set_value: Optional[str] = None,
) -> None:
    """Handle config subcommand."""
    from hivecore.config.settings import get_settings, save_settings

    if init:
        _interactive_init()
        return

    if set_value:
        if "=" not in set_value:
            console.print("[red]Error:[/red] Use format key=value")
            return
        key, value = set_value.split("=", 1)
        settings = get_settings()
        try:
            _set_nested(settings, key.strip(), value.strip())
            save_settings(settings)
            console.print(f"[green]Set[/green] {key.strip()} = {value.strip()}")
        except (AttributeError, KeyError) as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    # Default: show config
    settings = get_settings()
    table = Table(title="HiveCore Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("llm.model", settings.llm.model)
    table.add_row("llm.provider", settings.llm.provider)
    table.add_row("memory.backend", settings.memory.backend)
    table.add_row("memory.data_dir", str(settings.memory.data_dir))
    table.add_row("web.host", settings.web.host)
    table.add_row("web.port", str(settings.web.port))
    table.add_row("skills.directory", str(settings.skills.directory))

    console.print(table)


def _set_nested(obj: object, key: str, value: str) -> None:
    """Set a nested attribute using dot notation."""
    parts = key.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


def _interactive_init() -> None:
    """Run interactive configuration setup."""
    from rich.prompt import Prompt

    from hivecore.config.settings import HiveSettings, save_settings

    console.print("[bold blue]HiveCore Configuration Wizard[/bold blue]\n")

    model = Prompt.ask(
        "Default LLM model",
        default="gpt-4o",
    )
    provider = Prompt.ask(
        "LLM provider",
        choices=["openai", "anthropic", "google", "ollama", "litellm"],
        default="litellm",
    )
    api_key = Prompt.ask("API key (leave blank if using local models)", default="", password=True)
    memory_backend = Prompt.ask(
        "Memory backend",
        choices=["sqlite", "chromadb"],
        default="sqlite",
    )

    settings = HiveSettings()
    settings.llm.model = model
    settings.llm.provider = provider
    if api_key:
        settings.llm.api_key = api_key
    settings.memory.backend = memory_backend

    save_settings(settings)
    console.print("\n[green]Configuration saved![/green]")
