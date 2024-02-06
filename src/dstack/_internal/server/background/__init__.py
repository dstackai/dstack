from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server.background.tasks.process_finished_jobs import process_finished_jobs
from dstack._internal.server.background.tasks.process_pending_jobs import process_pending_jobs
from dstack._internal.server.background.tasks.process_pools import (
    process_pools,
    terminate_idle_instance,
)
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs

_scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start_background_tasks() -> AsyncIOScheduler:
    _scheduler.add_job(process_submitted_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_running_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_finished_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_pending_jobs, IntervalTrigger(seconds=10))
    _scheduler.add_job(process_pools, IntervalTrigger(seconds=10))
    _scheduler.add_job(terminate_idle_instance, IntervalTrigger(seconds=10))
    _scheduler.start()
    return _scheduler
