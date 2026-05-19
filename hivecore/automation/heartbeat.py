"""Heartbeat system for periodic check-ins and digests.

The heartbeat runs at a configurable interval and can:
- Generate daily digests
- Check for pending tasks
- Run health checks
- Push summaries to channels
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class Heartbeat:
    """Periodic heartbeat system.

    Runs at a configurable interval to perform background
    tasks like digest generation, health checks, and
    proactive notifications.
    """

    def __init__(
        self,
        interval_seconds: int = 3600,
        on_beat: Callable | None = None,
    ) -> None:
        self.interval_seconds = interval_seconds
        self._on_beat = on_beat
        self._scheduler = None
        self._last_beat: datetime | None = None
        self._beat_count: int = 0

    def start(self, scheduler: Any) -> None:
        """Register the heartbeat with the scheduler.

        Args:
            scheduler: The APScheduler instance.
        """
        from apscheduler.triggers.interval import IntervalTrigger

        self._scheduler = scheduler
        scheduler.add_job(
            self._beat,
            trigger=IntervalTrigger(seconds=self.interval_seconds),
            id="heartbeat",
            name="HiveCore Heartbeat",
            replace_existing=True,
        )
        logger.info("Heartbeat started (interval=%ds)", self.interval_seconds)

    async def _beat(self) -> None:
        """Execute a heartbeat cycle."""
        self._last_beat = datetime.now()
        self._beat_count += 1

        logger.debug("Heartbeat #%d at %s", self._beat_count, self._last_beat)

        if self._on_beat:
            try:
                await self._on_beat()
            except Exception as e:
                logger.error("Heartbeat callback failed: %s", e)

    def get_status(self) -> dict[str, Any]:
        """Get heartbeat status."""
        return {
            "interval_seconds": self.interval_seconds,
            "last_beat": self._last_beat.isoformat() if self._last_beat else None,
            "beat_count": self._beat_count,
        }
