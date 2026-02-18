import uuid
from datetime import datetime, timedelta
from typing import Optional

import sqlalchemy.exc
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import joinedload

from dstack._internal.core.consts import DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    JobPrometheusMetrics,
    ProjectModel,
)
from dstack._internal.server.services.instances import get_instance_ssh_private_keys
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_runtime_data
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.utils import sentry_utils
from dstack._internal.server.utils.common import gather_map_async
from dstack._internal.utils.common import batched, get_current_datetime, get_or_error, run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


MAX_JOBS_FETCHED = 100
BATCH_SIZE = 10
MIN_COLLECT_INTERVAL_SECONDS = 9
# 10 minutes should be more than enough to scrape metrics, and, in any case,
# 10 minutes old metrics has little to no value
METRICS_TTL_SECONDS = 600


@sentry_utils.instrument_background_task
async def collect_prometheus_metrics():
    now = get_current_datetime()
    cutoff = now - timedelta(seconds=MIN_COLLECT_INTERVAL_SECONDS)
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel)
            .join(JobPrometheusMetrics, isouter=True)
            .where(
                JobModel.status.in_([JobStatus.RUNNING]),
                or_(
                    JobPrometheusMetrics.job_id.is_(None),
                    JobPrometheusMetrics.collected_at < cutoff,
                ),
            )
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
        await _collect_jobs_metrics(batch, now)


@sentry_utils.instrument_background_task
async def delete_prometheus_metrics():
    now = get_current_datetime()
    cutoff = now - timedelta(seconds=METRICS_TTL_SECONDS)
    async with get_session_ctx() as session:
        await session.execute(
            delete(JobPrometheusMetrics).where(JobPrometheusMetrics.collected_at < cutoff)
        )
        await session.commit()


async def _collect_jobs_metrics(job_models: list[JobModel], collected_at: datetime):
    results = await gather_map_async(job_models, _collect_job_metrics, return_exceptions=True)
    async with get_session_ctx() as session:
        for job_model, result in results:
            if result is None:
                continue
            if isinstance(result, BaseException):
                logger.error(
                    "Failed to collect job %s Prometheus metrics: %r", job_model.job_name, result
                )
                continue
            res = await session.execute(
                update(JobPrometheusMetrics)
                .where(JobPrometheusMetrics.job_id == job_model.id)
                .values(
                    collected_at=collected_at,
                    text=result,
                )
                .returning(JobPrometheusMetrics)
            )
            metrics = res.scalar()
            if metrics is None:
                metrics = JobPrometheusMetrics(
                    job_id=job_model.id,
                    collected_at=collected_at,
                    text=result,
                )
                try:
                    async with session.begin_nested():
                        session.add(metrics)
                except sqlalchemy.exc.IntegrityError:
                    # Concurrent server replica already committed, ignoring
                    pass
        await session.commit()


async def _collect_job_metrics(job_model: JobModel) -> Optional[str]:
    jpd = get_job_provisioning_data(job_model)
    if jpd is None:
        return None
    if not jpd.dockerized:
        # Container-based backend, no shim
        return None
    ssh_private_keys = get_instance_ssh_private_keys(get_or_error(job_model.instance))
    jrd = get_job_runtime_data(job_model)
    try:
        res = await run_async(
            _pull_job_metrics,
            ssh_private_keys,
            jpd,
            jrd,
            job_model.id,
        )
    except Exception:
        logger.exception("Failed to collect job %s Prometheus metrics", job_model.job_name)
        return None

    if isinstance(res, bool):
        logger.warning(
            "Failed to connect to job %s to collect Prometheus metrics", job_model.job_name
        )
        return None

    if res is None:
        # Either not supported by shim or exporter is not available
        return None

    return res


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _pull_job_metrics(ports: dict[int, int], task_id: uuid.UUID) -> Optional[str]:
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    return shim_client.get_task_metrics(task_id)
