from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server import settings
from dstack._internal.server.background.scheduled_tasks.events import delete_events
from dstack._internal.server.background.scheduled_tasks.gateways import (
    init_gateways_in_background,
    process_gateways_connections,
)
from dstack._internal.server.background.scheduled_tasks.idle_volumes import (
    process_idle_volumes,
)
from dstack._internal.server.background.scheduled_tasks.instance_healthchecks import (
    delete_instance_healthchecks,
)
from dstack._internal.server.background.scheduled_tasks.metrics import (
    collect_metrics,
    delete_metrics,
)
from dstack._internal.server.background.scheduled_tasks.offers_catalog import (
    preload_offers_catalog,
)
from dstack._internal.server.background.scheduled_tasks.probes import process_probes
from dstack._internal.server.background.scheduled_tasks.prometheus_metrics import (
    collect_prometheus_metrics,
    delete_prometheus_metrics,
)

_scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start_scheduled_tasks() -> AsyncIOScheduler:
    """
    Start periodic tasks triggered by `apscheduler` at specific times/intervals.
    Suitable for tasks that run infrequently and don't need to lock rows for a long time.
    """
    # DateTrigger() to run one-time init tasks immediately.
    _scheduler.add_job(init_gateways_in_background, DateTrigger(), max_instances=1)
    _scheduler.add_job(preload_offers_catalog, DateTrigger(), max_instances=1)
    _scheduler.add_job(process_probes, IntervalTrigger(seconds=3, jitter=1))
    _scheduler.add_job(collect_metrics, IntervalTrigger(seconds=10), max_instances=1)
    _scheduler.add_job(delete_metrics, IntervalTrigger(minutes=5), max_instances=1)
    _scheduler.add_job(delete_events, IntervalTrigger(minutes=7), max_instances=1)
    _scheduler.add_job(process_gateways_connections, IntervalTrigger(seconds=15))
    _scheduler.add_job(
        process_idle_volumes, IntervalTrigger(seconds=60, jitter=10), max_instances=1
    )
    _scheduler.add_job(delete_instance_healthchecks, IntervalTrigger(minutes=5), max_instances=1)
    if settings.ENABLE_PROMETHEUS_METRICS:
        _scheduler.add_job(
            collect_prometheus_metrics, IntervalTrigger(seconds=10), max_instances=1
        )
        _scheduler.add_job(delete_prometheus_metrics, IntervalTrigger(minutes=5), max_instances=1)
    _scheduler.start()
    return _scheduler
