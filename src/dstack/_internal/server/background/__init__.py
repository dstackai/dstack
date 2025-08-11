from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_fleets import process_fleets
from dstack._internal.server.background.tasks.process_gateways import (
    process_gateways,
    process_gateways_connections,
)
from dstack._internal.server.background.tasks.process_idle_volumes import process_idle_volumes
from dstack._internal.server.background.tasks.process_instances import (
    delete_instance_health_checks,
    process_instances,
)
from dstack._internal.server.background.tasks.process_metrics import (
    collect_metrics,
    delete_metrics,
)
from dstack._internal.server.background.tasks.process_placement_groups import (
    process_placement_groups,
)
from dstack._internal.server.background.tasks.process_probes import process_probes
from dstack._internal.server.background.tasks.process_prometheus_metrics import (
    collect_prometheus_metrics,
    delete_prometheus_metrics,
)
from dstack._internal.server.background.tasks.process_running_jobs import process_running_jobs
from dstack._internal.server.background.tasks.process_runs import process_runs
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from dstack._internal.server.background.tasks.process_terminating_jobs import (
    process_terminating_jobs,
)
from dstack._internal.server.background.tasks.process_volumes import process_submitted_volumes

_scheduler = AsyncIOScheduler()


def get_scheduler() -> AsyncIOScheduler:
    return _scheduler


def start_background_tasks() -> AsyncIOScheduler:
    # We try to process as many resources as possible without exhausting DB connections.
    #
    # Quick tasks can process multiple resources per transaction.
    # Potentially long tasks process one resource per transaction
    # to avoid holding locks for all the resources if one is slow to process.
    # Still, the next batch won't be processed unless all resources are processed,
    # so larger batches do not increase processing rate linearly.
    #
    # The interval, batch_size, and max_instances determine background tasks processing rates.
    # By default, one server replica can handle:
    #
    # * 150 active jobs with 2 minutes processing latency
    # * 150 active runs with 2 minutes processing latency
    # * 150 active instances with 2 minutes processing latency
    #
    # These latency numbers do not account for provisioning time,
    # so it may be slower if a backend is slow to provision.
    #
    # Users can set SERVER_BACKGROUND_PROCESSING_FACTOR to process more resources per replica.
    # They also need to increase max db connections on the client side and db side.
    #
    # In-memory locking via locksets does not guarantee
    # that the first waiting for the lock will acquire it.
    # The jitter is needed to give all tasks a chance to acquire locks.

    _scheduler.add_job(process_probes, IntervalTrigger(seconds=3, jitter=1))
    _scheduler.add_job(collect_metrics, IntervalTrigger(seconds=10), max_instances=1)
    _scheduler.add_job(delete_metrics, IntervalTrigger(minutes=5), max_instances=1)
    if settings.ENABLE_PROMETHEUS_METRICS:
        _scheduler.add_job(
            collect_prometheus_metrics, IntervalTrigger(seconds=10), max_instances=1
        )
        _scheduler.add_job(delete_prometheus_metrics, IntervalTrigger(minutes=5), max_instances=1)
    _scheduler.add_job(process_gateways_connections, IntervalTrigger(seconds=15))
    _scheduler.add_job(process_gateways, IntervalTrigger(seconds=10, jitter=2), max_instances=5)
    _scheduler.add_job(
        process_submitted_volumes, IntervalTrigger(seconds=10, jitter=2), max_instances=5
    )
    _scheduler.add_job(
        process_idle_volumes, IntervalTrigger(seconds=60, jitter=10), max_instances=1
    )
    _scheduler.add_job(process_placement_groups, IntervalTrigger(seconds=30, jitter=5))
    _scheduler.add_job(
        process_fleets,
        IntervalTrigger(seconds=10, jitter=2),
        max_instances=1,
    )
    _scheduler.add_job(delete_instance_health_checks, IntervalTrigger(minutes=5), max_instances=1)
    for replica in range(settings.SERVER_BACKGROUND_PROCESSING_FACTOR):
        # Add multiple copies of tasks if requested.
        # max_instances=1 for additional copies to avoid running too many tasks.
        # Move other tasks here when they need per-replica scaling.
        _scheduler.add_job(
            process_submitted_jobs,
            IntervalTrigger(seconds=4, jitter=2),
            kwargs={"batch_size": 5},
            max_instances=4 if replica == 0 else 1,
        )
        _scheduler.add_job(
            process_running_jobs,
            IntervalTrigger(seconds=4, jitter=2),
            kwargs={"batch_size": 5},
            max_instances=2 if replica == 0 else 1,
        )
        _scheduler.add_job(
            process_terminating_jobs,
            IntervalTrigger(seconds=4, jitter=2),
            kwargs={"batch_size": 5},
            max_instances=2 if replica == 0 else 1,
        )
        _scheduler.add_job(
            process_runs,
            IntervalTrigger(seconds=2, jitter=1),
            kwargs={"batch_size": 5},
            max_instances=2 if replica == 0 else 1,
        )
        _scheduler.add_job(
            process_instances,
            IntervalTrigger(seconds=4, jitter=2),
            kwargs={"batch_size": 5},
            max_instances=2 if replica == 0 else 1,
        )
    _scheduler.start()
    return _scheduler
