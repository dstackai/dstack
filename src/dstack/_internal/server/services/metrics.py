import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.metrics import JobMetrics, Metric
from dstack._internal.server.models import JobMetricsPoint, JobModel, ProjectModel
from dstack._internal.server.services.jobs import list_run_job_models


async def get_job_metrics(
    session: AsyncSession,
    project: ProjectModel,
    run_name: str,
    replica_num: int,
    job_num: int,
) -> JobMetrics:
    job_models = await list_run_job_models(
        session=session,
        project=project,
        run_name=run_name,
        replica_num=replica_num,
        job_num=job_num,
    )
    if len(job_models) == 0:
        raise ResourceNotExistsError("Found no job with given parameters")
    job_model = job_models[-1]
    job_metrics = await _get_job_metrics(
        session=session,
        job_model=job_model,
    )
    return job_metrics


async def _get_job_metrics(
    session: AsyncSession,
    job_model: JobModel,
) -> JobMetrics:
    res = await session.execute(
        select(JobMetricsPoint)
        .where(JobMetricsPoint.job_id == job_model.id)
        .order_by(JobMetricsPoint.timestamp_micro.desc())
        .limit(2)
    )
    points = res.scalars().all()
    if len(points) < 2:
        return JobMetrics(metrics=[])
    last_point = points[0]
    prev_point = points[1]
    return _calculate_job_metrics(last_point, prev_point)


def _calculate_job_metrics(last_point: JobMetricsPoint, prev_point: JobMetricsPoint) -> JobMetrics:
    metrics = []
    timestamp = _unix_time_micro_to_datetime(last_point.timestamp_micro)
    metrics.append(
        Metric(
            name="cpu_usage_percent",
            timestamps=[timestamp],
            values=[_get_cpu_usage(last_point, prev_point)],
        )
    )
    metrics.append(
        Metric(
            name="memory_usage_bytes",
            timestamps=[timestamp],
            values=[last_point.memory_usage_bytes],
        )
    )
    metrics.append(
        Metric(
            name="memory_working_set_bytes",
            timestamps=[timestamp],
            values=[last_point.memory_working_set_bytes],
        )
    )

    gpus_memory_usage_bytes = json.loads(last_point.gpus_memory_usage_bytes)
    gpus_util_percent = json.loads(last_point.gpus_util_percent)
    gpus_detected_num = len(gpus_memory_usage_bytes)
    metrics.append(
        Metric(
            name="gpus_detected_num",
            timestamps=[timestamp],
            values=[gpus_detected_num],
        )
    )
    for i in range(gpus_detected_num):
        metrics.append(
            Metric(
                name=f"gpu_memory_usage_bytes_gpu{i}",
                timestamps=[timestamp],
                values=[gpus_memory_usage_bytes[i]],
            )
        )
        metrics.append(
            Metric(
                name=f"gpu_util_percent_gpu{i}",
                timestamps=[timestamp],
                values=[gpus_util_percent[i]],
            )
        )
    return JobMetrics(metrics=metrics)


def _get_cpu_usage(last_point: JobMetricsPoint, prev_point: JobMetricsPoint) -> int:
    window = last_point.timestamp_micro - prev_point.timestamp_micro
    return round((last_point.cpu_usage_micro - prev_point.cpu_usage_micro) / window * 100)


def _unix_time_micro_to_datetime(unix_time_ms: int) -> datetime:
    return datetime.fromtimestamp(unix_time_ms / 1_000_000, tz=timezone.utc)
