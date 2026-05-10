"""APScheduler setup for the daily digest job."""

import logging
from typing import Callable, Coroutine, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
DIGEST_JOB_ID = "daily_digest"


def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton scheduler, creating it on first call."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=settings.timezone)
    return _scheduler


def setup_scheduler(
    run_digest_job: Callable[[], Coroutine[Any, Any, None]],
    hour: int | None = None,
    minute: int | None = None,
) -> AsyncIOScheduler:
    """Register the daily digest cron job and return the scheduler.

    Args:
        run_digest_job: Async callable that executes the full digest pipeline.
        hour:           Override hour (defaults to settings.digest_hour).
        minute:         Override minute (defaults to settings.digest_minute).
    """
    h = hour if hour is not None else settings.digest_hour
    m = minute if minute is not None else settings.digest_minute

    scheduler = get_scheduler()

    # Remove existing job so we can reschedule without duplicates
    if scheduler.get_job(DIGEST_JOB_ID):
        scheduler.remove_job(DIGEST_JOB_ID)

    trigger = CronTrigger(hour=h, minute=m, timezone=settings.timezone)
    scheduler.add_job(
        run_digest_job,
        trigger=trigger,
        id=DIGEST_JOB_ID,
        name="Daily AI news digest",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Digest scheduled at %02d:%02d (%s)", h, m, settings.timezone)
    return scheduler


def reschedule_digest(
    run_digest_job: Callable[[], Coroutine[Any, Any, None]],
    time_str: str,
) -> None:
    """Update the cron trigger to a new HH:MM time string."""
    h, m = map(int, time_str.split(":"))
    setup_scheduler(run_digest_job, hour=h, minute=m)
    logger.info("Rescheduled digest to %02d:%02d", h, m)


def next_run_time() -> str | None:
    """Return ISO formatted next run time, or None if not scheduled."""
    scheduler = get_scheduler()
    job = scheduler.get_job(DIGEST_JOB_ID)
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
    return None
