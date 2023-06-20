import asyncio

from apscheduler.events import EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.hub.background.tasks.resubmit_jobs import resubmit_jobs


def start_background_tasks():
    def _error_listner(event: JobExecutionEvent):
        if isinstance(event.exception, asyncio.CancelledError):
            scheduler.shutdown()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(resubmit_jobs, IntervalTrigger(seconds=60))
    scheduler.add_listener(_error_listner, EVENT_JOB_ERROR)
    scheduler.start()
