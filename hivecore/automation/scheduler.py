"""Task scheduler using APScheduler.

Manages cron-based scheduled tasks that run skills
and push results to configured channels.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """Represents a scheduled job."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    cron_expr: str = ""
    skill_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    channel: Optional[str] = None
    enabled: bool = True
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None
    last_result: Optional[str] = None


class Scheduler:
    """Cron-based task scheduler.

    Uses APScheduler to manage periodic task execution.
    Jobs run skills and can push results to configured channels.
    """

    def __init__(self) -> None:
        self._scheduler = None
        self._jobs: dict[str, ScheduledJob] = {}
        self._skill_executor: Optional[Callable] = None

    def start(self) -> None:
        """Start the scheduler."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            self._scheduler = AsyncIOScheduler()
            self._scheduler.start()
            logger.info("Scheduler started.")

            # Re-add any existing jobs
            for job in self._jobs.values():
                if job.enabled:
                    self._add_apscheduler_job(job)

        except ImportError:
            logger.warning("APScheduler not installed. Scheduler disabled.")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    def set_skill_executor(self, executor: Callable) -> None:
        """Set the function to call when executing a skill.

        Args:
            executor: Async function(skill_name, params) -> result.
        """
        self._skill_executor = executor

    def add_job(
        self,
        name: str,
        cron_expr: str,
        skill_name: str,
        params: Optional[dict[str, Any]] = None,
        channel: Optional[str] = None,
    ) -> str:
        """Add a scheduled job.

        Args:
            name: Job display name.
            cron_expr: Cron expression (e.g., "0 8 * * *" for daily at 8am).
            skill_name: Name of the skill to execute.
            params: Parameters to pass to the skill.
            channel: Channel to push results to.

        Returns:
            The job ID.
        """
        job = ScheduledJob(
            name=name,
            cron_expr=cron_expr,
            skill_name=skill_name,
            params=params or {},
            channel=channel,
        )
        self._jobs[job.id] = job

        if self._scheduler and job.enabled:
            self._add_apscheduler_job(job)

        logger.info("Added scheduled job: %s (%s) -> %s", name, cron_expr, skill_name)
        return job.id

    def remove_job(self, job_id: str) -> None:
        """Remove a scheduled job.

        Args:
            job_id: The job ID to remove.

        Raises:
            KeyError: If the job is not found.
        """
        if job_id not in self._jobs:
            raise KeyError(f"Job not found: {job_id}")

        del self._jobs[job_id]

        if self._scheduler:
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass

        logger.info("Removed scheduled job: %s", job_id)

    def list_jobs(self) -> list[ScheduledJob]:
        """List all scheduled jobs."""
        return list(self._jobs.values())

    def _add_apscheduler_job(self, job: ScheduledJob) -> None:
        """Add a job to the APScheduler."""
        if not self._scheduler:
            return

        from apscheduler.triggers.cron import CronTrigger

        try:
            parts = job.cron_expr.split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                )
            else:
                logger.error("Invalid cron expression: %s", job.cron_expr)
                return

            self._scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                id=job.id,
                name=job.name,
                kwargs={"job": job},
                replace_existing=True,
            )

            # Update next run time
            scheduler_job = self._scheduler.get_job(job.id)
            if scheduler_job:
                job.next_run = scheduler_job.next_run_time

        except Exception as e:
            logger.error("Failed to schedule job %s: %s", job.id, e)

    async def _execute_job(self, job: ScheduledJob) -> None:
        """Execute a scheduled job."""
        logger.info("Executing scheduled job: %s (skill=%s)", job.name, job.skill_name)

        job.last_run = datetime.now()

        if self._skill_executor:
            try:
                result = await self._skill_executor(job.skill_name, job.params)
                job.last_result = str(result)[:1000]
                logger.info("Job %s completed successfully", job.name)
            except Exception as e:
                job.last_result = f"Error: {e}"
                logger.error("Job %s failed: %s", job.name, e)
        else:
            job.last_result = "Error: No skill executor configured"
            logger.warning("No skill executor configured for scheduler")
