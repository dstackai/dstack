import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.metrics import JobMetrics, Metric
from dstack._internal.server.models import JobMetricsPoint, JobModel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def get_job_metrics(
    session: AsyncSession,
    job_model: JobModel,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> JobMetrics:
    """
    Returns metrics ordered from the latest to the earliest.

    Expected usage:
        * limit=100 — get the latest 100 points
        * after=<now - 1 hour> — get points for the last one hour
        * before=<earliest timestamp from the last batch>, limit=100 ­— paginate back in history
    """
    stmt = (
        select(JobMetricsPoint)
        .where(JobMetricsPoint.job_id == job_model.id)
        .order_by(JobMetricsPoint.timestamp_micro.desc())
    )
    if after is not None:
        # we need +1 point for cpu_usage_percent, thus >=
        stmt = stmt.where(JobMetricsPoint.timestamp_micro >= _datetime_to_unix_time_micro(after))
    if before is not None:
        stmt = stmt.where(JobMetricsPoint.timestamp_micro < _datetime_to_unix_time_micro(before))
    if limit is not None:
        # +1 for cpu_usage_percent
        stmt = stmt.limit(limit + 1)
    res = await session.execute(stmt)
    points = res.scalars().all()
    # we need at least 2 points to calculate cpu_usage_percent
    if len(points) < 2:
        return JobMetrics(metrics=[])
    return _calculate_job_metrics(points)


def _calculate_job_metrics(points: Sequence[JobMetricsPoint]) -> JobMetrics:
    timestamps: list[datetime] = []
    cpu_usage_points: list[int] = []
    memory_usage_points: list[int] = []
    memory_working_set_points: list[int] = []
    gpus_memory_usage_points: defaultdict[int, list[int]] = defaultdict(list)
    gpus_util_points: defaultdict[int, list[int]] = defaultdict(list)

    gpus_detected_num: Optional[int] = None
    gpus_detected_num_mismatch: bool = False
    for point, prev_point in zip(points, points[1:]):
        timestamps.append(_unix_time_micro_to_datetime(point.timestamp_micro))
        cpu_usage_points.append(_get_cpu_usage(point, prev_point))
        memory_usage_points.append(point.memory_usage_bytes)
        memory_working_set_points.append(point.memory_working_set_bytes)
        gpus_memory_usage = json.loads(point.gpus_memory_usage_bytes)
        gpus_util = json.loads(point.gpus_util_percent)
        if gpus_detected_num is None:
            gpus_detected_num = len(gpus_memory_usage)
        if len(gpus_memory_usage) != gpus_detected_num or len(gpus_util) != gpus_detected_num:
            gpus_detected_num_mismatch = True
        if not gpus_detected_num_mismatch:
            for i in range(gpus_detected_num):
                gpus_memory_usage_points[i].append(gpus_memory_usage[i])
                gpus_util_points[i].append(gpus_util[i])

    metrics: list[Metric] = [
        Metric(
            name="cpu_usage_percent",
            timestamps=timestamps,
            values=cpu_usage_points,
        ),
        Metric(
            name="memory_usage_bytes",
            timestamps=timestamps,
            values=memory_usage_points,
        ),
        Metric(
            name="memory_working_set_bytes",
            timestamps=timestamps,
            values=memory_working_set_points,
        ),
    ]
    if gpus_detected_num_mismatch:
        # If number of GPUs changed in the time window, skip GPU metrics altogether, otherwise
        # results can be unpredictable (e.g, one GPU takes place of another, as they are
        # identified by an array index only).
        logger.warning("gpus_detected_num mismatch, skipping GPU metrics")
    else:
        metrics.append(
            # As gpus_detected_num expected to be constant, we add only two points — the latest
            # and the earliest in the batch
            Metric(
                name="gpus_detected_num",
                timestamps=[timestamps[0], timestamps[-1]]
                if len(timestamps) > 1
                else [timestamps[0]],
                values=[gpus_detected_num, gpus_detected_num]
                if len(timestamps) > 1
                else [gpus_detected_num],
            )
        )
        for index, gpu_memory_usage_points in gpus_memory_usage_points.items():
            metrics.append(
                Metric(
                    name=f"gpu_memory_usage_bytes_gpu{index}",
                    timestamps=timestamps,
                    values=gpu_memory_usage_points,
                )
            )
        for index, gpu_util_points in gpus_util_points.items():
            metrics.append(
                Metric(
                    name=f"gpu_util_percent_gpu{index}",
                    timestamps=timestamps,
                    values=gpu_util_points,
                )
            )
    return JobMetrics(metrics=metrics)


def _get_cpu_usage(last_point: JobMetricsPoint, prev_point: JobMetricsPoint) -> int:
    window = last_point.timestamp_micro - prev_point.timestamp_micro
    if window == 0:
        return 0
    return round((last_point.cpu_usage_micro - prev_point.cpu_usage_micro) / window * 100)


def _unix_time_micro_to_datetime(unix_time_ms: int) -> datetime:
    return datetime.fromtimestamp(unix_time_ms / 1_000_000, tz=timezone.utc)


def _datetime_to_unix_time_micro(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)
