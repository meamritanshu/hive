"""Schedule CLI command handler."""

from typing import Optional

from rich.console import Console
from rich.table import Table

console = Console()


def handle_schedule(
    list_jobs: bool = False,
    add: Optional[str] = None,
    remove: Optional[str] = None,
) -> None:
    """Handle scheduled task management commands."""
    import json

    from hivecore.automation.scheduler import Scheduler

    scheduler = Scheduler()

    if add:
        try:
            job_config = json.loads(add)
            job_id = scheduler.add_job(
                name=job_config.get("name", "unnamed"),
                cron_expr=job_config["cron"],
                skill_name=job_config["skill"],
                params=job_config.get("params", {}),
                channel=job_config.get("channel"),
            )
            console.print(f"[green]Job added:[/green] {job_id}")
        except json.JSONDecodeError:
            console.print("[red]Error:[/red] Invalid JSON. Use format: "
                          '\'{"name": "...", "cron": "0 8 * * *", "skill": "news_digest"}\'')
        except KeyError as e:
            console.print(f"[red]Error:[/red] Missing required field: {e}")
        return

    if remove:
        try:
            scheduler.remove_job(remove)
            console.print(f"[green]Job removed:[/green] {remove}")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
        return

    # Default: list jobs
    jobs = scheduler.list_jobs()
    if not jobs:
        console.print("[dim]No scheduled jobs. Use --add to create one.[/dim]")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule", style="green")
    table.add_column("Skill", style="yellow")
    table.add_column("Next Run", style="blue")

    for job in jobs:
        table.add_row(job.id, job.name, job.cron_expr, job.skill_name, str(job.next_run))

    console.print(table)
