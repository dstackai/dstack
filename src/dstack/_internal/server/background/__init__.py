from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server.background.tasks.process_gateways import process_gateways
from dstack._internal.server.background.tasks.process_instances import (
    process_instances,
    terminate_idle_instance,
)
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.background.tasks.process_runs import process_runs
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from dstack._internal.server.background.tasks.process_terminating_jobs import (
    process_terminating_jobs,
)

_scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start_background_tasks() -> AsyncIOScheduler:
    _scheduler.add_job(process_submitted_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_running_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_terminating_jobs, IntervalTrigger(seconds=2))
    _scheduler.add_job(process_instances, IntervalTrigger(seconds=5))
    _scheduler.add_job(terminate_idle_instance, IntervalTrigger(seconds=10))
    _scheduler.add_job(process_runs, IntervalTrigger(seconds=1))
    _scheduler.add_job(process_gateways, IntervalTrigger(seconds=15))
    _scheduler.start()
    return _scheduler
