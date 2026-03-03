"""Skill CLI command handler."""

from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()


def handle_skill(
    list_skills: bool = False,
    install: Optional[str] = None,
    info: Optional[str] = None,
) -> None:
    """Handle skill management commands."""
    from hivecore.skills.registry import SkillRegistry

    registry = SkillRegistry()

    if install:
        console.print(f"[yellow]Installing skill:[/yellow] {install}")
        try:
            registry.install(install)
            console.print(f"[green]Skill '{install}' installed successfully.[/green]")
        except Exception as e:
            console.print(f"[red]Error installing skill:[/red] {e}")
        return

    if info:
        skill = registry.get(info)
        if skill is None:
            console.print(f"[red]Skill '{info}' not found.[/red]")
            return
        console.print(f"[bold]{skill.name}[/bold]")
        console.print(f"  Description: {skill.description}")
        console.print(f"  Version: {skill.version}")
        console.print(f"  Author: {skill.author}")
        if skill.dependencies:
            console.print(f"  Dependencies: {', '.join(skill.dependencies)}")
        return

    # Default: list all skills
    skills = registry.list_all()
    if not skills:
        console.print("[dim]No skills installed. Use --install to add skills.[/dim]")
        return

    table = Table(title="Installed Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Version", style="green")
    table.add_column("Status", style="yellow")

    for skill in skills:
        table.add_row(skill.name, skill.description, skill.version, skill.status)

    console.print(table)
