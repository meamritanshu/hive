"""HiveCore CLI - main entry point."""


import typer
from rich.console import Console
from rich.panel import Panel

from hivecore import __version__

app = typer.Typer(
    name="hivecore",
    help="HiveCore - A local-first agentic workstation framework.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold blue]HiveCore[/bold blue] v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", help="Show version and exit.", callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """HiveCore - Your personal AI agent workstation."""


@app.command()
def start(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind the web console."),
    port: int = typer.Option(8088, "--port", "-p", help="Port for the web console."),
    no_web: bool = typer.Option(False, "--no-web", help="Start without the web console."),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file."),
) -> None:
    """Start the HiveCore workstation."""
    import asyncio

    from hivecore.runtime.lifecycle import start_workstation

    console.print(
        Panel(
            f"[bold blue]HiveCore[/bold blue] v{__version__}\n"
            f"Web console: http://{host}:{port}",
            title="Starting HiveCore",
            border_style="blue",
        )
    )
    asyncio.run(start_workstation(host=host, port=port, no_web=no_web, config_path=config))


@app.command()
def chat(
    message: str | None = typer.Argument(None, help="Message to send to the agent."),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model to use."),
) -> None:
    """Start an interactive chat session with the agent."""
    import asyncio

    from hivecore.cli.interactive import interactive_chat

    asyncio.run(interactive_chat(message=message, model_override=model))


@app.command()
def config(
    show: bool = typer.Option(False, "--show", "-s", help="Show current configuration."),
    init: bool = typer.Option(False, "--init", help="Initialize configuration interactively."),
    set_value: str | None = typer.Option(
        None, "--set", help="Set a config value (key=value)."
    ),
) -> None:
    """Manage HiveCore configuration."""
    from hivecore.cli.commands.config_cmd import handle_config

    handle_config(show=show, init=init, set_value=set_value)


@app.command(name="skill")
def skill_cmd(
    list_skills: bool = typer.Option(False, "--list", "-l", help="List installed skills."),
    install: str | None = typer.Option(None, "--install", "-i", help="Install a skill."),
    info: str | None = typer.Option(None, "--info", help="Show skill details."),
) -> None:
    """Manage agent skills."""
    from hivecore.cli.commands.skill_cmd import handle_skill

    handle_skill(list_skills=list_skills, install=install, info=info)


@app.command(name="schedule")
def schedule_cmd(
    list_jobs: bool = typer.Option(False, "--list", "-l", help="List scheduled jobs."),
    add: str | None = typer.Option(None, "--add", help="Add a scheduled job (JSON)."),
    remove: str | None = typer.Option(None, "--remove", help="Remove a job by ID."),
) -> None:
    """Manage scheduled tasks and automation."""
    from hivecore.cli.commands.schedule_cmd import handle_schedule

    handle_schedule(list_jobs=list_jobs, add=add, remove=remove)


@app.command()
def status() -> None:
    """Show the current status of the HiveCore workstation."""
    from hivecore.cli.commands.status_cmd import handle_status

    handle_status()


if __name__ == "__main__":
    app()
