import asyncio
import json
from typing import Dict, List, Optional

from sqlalchemy import Delete, delete, select
from sqlalchemy.orm import joinedload

from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server import settings
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, JobMetricsPoint, JobModel, ProjectModel
from dstack._internal.server.schemas.runner import MetricsResponse
from dstack._internal.server.services.instances import get_instance_ssh_private_keys
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_runtime_data
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import batched, get_current_datetime, get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


MAX_JOBS_FETCHED = 100
BATCH_SIZE = 10
MIN_COLLECT_INTERVAL_SECONDS = 9


@sentry_utils.instrument_background_task
async def collect_metrics():
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel)
            .where(JobModel.status.in_([JobStatus.RUNNING]))
            .options(
                joinedload(JobModel.instance)
                .joinedload(InstanceModel.project)
                .load_only(ProjectModel.ssh_private_key)
            )
            .order_by(JobModel.last_processed_at.asc())
            .limit(MAX_JOBS_FETCHED)
        )
        job_models = res.unique().scalars().all()

    for batch in batched(job_models, BATCH_SIZE):
        await _collect_jobs_metrics(batch)


@sentry_utils.instrument_background_task
async def delete_metrics():
    now_timestamp_micro = int(get_current_datetime().timestamp() * 1_000_000)
    running_timestamp_micro_cutoff = (
        now_timestamp_micro - settings.SERVER_METRICS_RUNNING_TTL_SECONDS * 1_000_000
    )
    finished_timestamp_micro_cutoff = (
        now_timestamp_micro - settings.SERVER_METRICS_FINISHED_TTL_SECONDS * 1_000_000
    )
    await asyncio.gather(
        _execute_delete_statement(
            delete(JobMetricsPoint).where(
                JobMetricsPoint.job_id.in_(
                    select(JobModel.id).where(JobModel.status.in_([JobStatus.RUNNING]))
                ),
                JobMetricsPoint.timestamp_micro < running_timestamp_micro_cutoff,
            )
        ),
        _execute_delete_statement(
            delete(JobMetricsPoint).where(
                JobMetricsPoint.job_id.in_(
                    select(JobModel.id).where(JobModel.status.in_(JobStatus.finished_statuses()))
                ),
                JobMetricsPoint.timestamp_micro < finished_timestamp_micro_cutoff,
            )
        ),
    )


async def _execute_delete_statement(stmt: Delete) -> None:
    async with get_session_ctx() as session:
        await session.execute(stmt)
        await session.commit()


async def _collect_jobs_metrics(job_models: List[JobModel]):
    filtered_job_models = await _filter_recently_collected_jobs(job_models)
    tasks = []
    for job_model in filtered_job_models:
        tasks.append(_collect_job_metrics(job_model))
    points = await asyncio.gather(*tasks)
    async with get_session_ctx() as session:
        for point in points:
            if point is not None:
                session.add(point)
        await session.commit()


async def _filter_recently_collected_jobs(job_models: List[JobModel]) -> List[JobModel]:
    # Skip metrics collection if another replica collected it recently.
    # Two replicas can still collect metrics simultaneously – that's fine since
    # we'll just store some extra metric points in the db.
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobMetricsPoint).where(
                JobMetricsPoint.job_id.in_([j.id for j in job_models]),
                JobMetricsPoint.timestamp_micro > _get_recently_collected_metric_cutoff(),
            )
        )
        recent_points = res.scalars().all()
        recent_job_ids = [p.job_id for p in recent_points]
    return [j for j in job_models if j.id not in recent_job_ids]


def _get_recently_collected_metric_cutoff() -> int:
    now = int(get_current_datetime().timestamp() * 1_000_000)
    cutoff = now - (MIN_COLLECT_INTERVAL_SECONDS * 1_000_000)
    return cutoff


async def _collect_job_metrics(job_model: JobModel) -> Optional[JobMetricsPoint]:
    ssh_private_keys = get_instance_ssh_private_keys(get_or_error(job_model.instance))
    jpd = get_job_provisioning_data(job_model)
    jrd = get_job_runtime_data(job_model)
    if jpd is None:
        return None
    try:
        res = await run_async(
            _pull_runner_metrics,
            ssh_private_keys,
            jpd,
            jrd,
        )
    except Exception:
        logger.exception("Failed to collect job %s metrics", job_model.job_name)
        return None

    if isinstance(res, bool):
        # The job may already be terminated when collecting metrics - that's ok.
        logger.warning("Failed to connect to job %s to collect metrics", job_model.job_name)
        return None

    if res is None:
        logger.warning(
            "Failed to collect job %s metrics. Runner version does not support metrics API.",
            job_model.job_name,
        )
        return None

    gpus_memory_usage_bytes = [g.gpu_memory_usage_bytes for g in res.gpus]
    gpus_util_percent = [g.gpu_util_percent for g in res.gpus]

    return JobMetricsPoint(
        job_id=job_model.id,
        timestamp_micro=res.timestamp_micro,
        cpu_usage_micro=res.cpu_usage_micro,
        memory_usage_bytes=res.memory_usage_bytes,
        memory_working_set_bytes=res.memory_working_set_bytes,
        gpus_memory_usage_bytes=json.dumps(gpus_memory_usage_bytes),
        gpus_util_percent=json.dumps(gpus_util_percent),
    )


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT], retries=1)
def _pull_runner_metrics(
    ports: Dict[int, int],
) -> Optional[MetricsResponse]:
    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    return runner_client.get_metrics()
