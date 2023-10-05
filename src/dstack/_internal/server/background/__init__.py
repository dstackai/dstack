from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server.background.tasks.process_pending_jobs import process_pending_jobs
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs


def start_background_tasks() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(process_submitted_jobs, IntervalTrigger(seconds=2))
    scheduler.add_job(process_running_jobs, IntervalTrigger(seconds=2))
    scheduler.add_job(process_pending_jobs, IntervalTrigger(seconds=10))
    scheduler.start()
    return scheduler
