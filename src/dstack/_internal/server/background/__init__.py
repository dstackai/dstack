from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server.background.tasks.runs import handle_submitted_jobs


def start_background_tasks() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # scheduler.add_job(handle_submitted_jobs, IntervalTrigger(seconds=2))
    scheduler.start()
    return scheduler
