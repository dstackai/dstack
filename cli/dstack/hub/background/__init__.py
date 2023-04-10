from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack.hub.background.tasks.resubmit_jobs import resubmit_jobs


def start_background_tasks():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(resubmit_jobs, IntervalTrigger(seconds=60))
    scheduler.start()
