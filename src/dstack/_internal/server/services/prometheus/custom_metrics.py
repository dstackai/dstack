import itertools
import json
from collections import defaultdict
from collections.abc import Generator, Iterable
from typing import ClassVar
from uuid import UUID

from prometheus_client import Metric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus, RunSpec, RunStatus
from dstack._internal.server.models import (
    InstanceModel,
    JobMetricsPoint,
    JobModel,
    JobPrometheusMetrics,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services.instances import get_instance_offer
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_runtime_data
from dstack._internal.utils.common import get_current_datetime


async def get_metrics(session: AsyncSession) -> str:
    metrics_iter = itertools.chain(
        await get_instance_metrics(session),
        await get_run_metrics(session),
        await get_job_metrics(session),
    )
    return "\n".join(_render_metrics(metrics_iter)) + "\n"


async def get_instance_metrics(session: AsyncSession) -> Iterable[Metric]:
    res = await session.execute(
        select(InstanceModel)
        .join(ProjectModel)
        .where(
            InstanceModel.deleted == False,
            InstanceModel.status.in_(
                [
                    InstanceStatus.PROVISIONING,
                    InstanceStatus.IDLE,
                    InstanceStatus.BUSY,
                    InstanceStatus.TERMINATING,
                ]
            ),
        )
        .order_by(ProjectModel.name, InstanceModel.name)
        .options(
            joinedload(InstanceModel.project),
            joinedload(InstanceModel.fleet),
        )
    )
    instances = res.unique().scalars().all()
    metrics = _InstanceMetrics()
    now = get_current_datetime()
    for instance in instances:
        fleet = instance.fleet
        offer = get_instance_offer(instance)
        gpu = ""
        gpu_count = 0
        if offer is not None and len(offer.instance.resources.gpus) > 0:
            gpu = offer.instance.resources.gpus[0].name
            gpu_count = len(offer.instance.resources.gpus)
        labels: dict[str, str] = {
            "dstack_project_name": instance.project.name,
            "dstack_fleet_name": fleet.name if fleet is not None else "",
            "dstack_fleet_id": str(fleet.id) if fleet is not None else "",
            "dstack_instance_name": str(instance.name),
            "dstack_instance_id": str(instance.id),
            "dstack_instance_type": offer.instance.name if offer is not None else "",
            "dstack_backend": instance.backend.value if instance.backend is not None else "",
            "dstack_gpu": gpu,
        }
        duration = (now - instance.created_at).total_seconds()
        metrics.add_sample(_INSTANCE_DURATION, labels, duration)
        metrics.add_sample(_INSTANCE_PRICE, labels, instance.price or 0.0)
        metrics.add_sample(_INSTANCE_GPU_COUNT, labels, gpu_count)
    return metrics.values()


async def get_run_metrics(session: AsyncSession) -> Iterable[Metric]:
    res = await session.execute(
        select(ProjectModel.name, UserModel.name, RunModel.status, func.count(RunModel.id))
        .join_from(RunModel, ProjectModel)
        .join_from(RunModel, UserModel, RunModel.user_id == UserModel.id)
        .group_by(ProjectModel.name, UserModel.name, RunModel.status)
        .order_by(ProjectModel.name, UserModel.name, RunModel.status)
    )
    projects: dict[str, dict[str, dict[RunStatus, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for project_name, user_name, status, count in res.all():
        projects[project_name][user_name][status] = count
    metrics = _RunMetrics()
    for project_name, users in projects.items():
        for user_name, statuses in users.items():
            labels: dict[str, str] = {
                "dstack_project_name": project_name,
                "dstack_user_name": user_name,
            }
            metrics.add_sample(_RUN_COUNT_TOTAL, labels, sum(statuses.values()))
            metrics.add_sample(_RUN_COUNT_TERMINATED, labels, statuses[RunStatus.TERMINATED])
            metrics.add_sample(_RUN_COUNT_FAILED, labels, statuses[RunStatus.FAILED])
            metrics.add_sample(_RUN_COUNT_DONE, labels, statuses[RunStatus.DONE])
    return metrics.values()


async def get_job_metrics(session: AsyncSession) -> Iterable[Metric]:
    res = await session.execute(
        select(JobModel)
        .join(ProjectModel)
        .where(
            JobModel.status.in_(
                [
                    JobStatus.PROVISIONING,
                    JobStatus.PULLING,
                    JobStatus.RUNNING,
                    JobStatus.TERMINATING,
                ]
            )
        )
        .order_by(ProjectModel.name, JobModel.job_name)
        .options(
            joinedload(JobModel.project),
            joinedload(JobModel.run).joinedload(RunModel.user),
        )
    )
    jobs = res.scalars().all()
    job_ids = {job.id for job in jobs}
    job_metrics_points = await _get_job_metrics_points(session, job_ids)
    job_prometheus_metrics = await _get_job_prometheus_metrics(session, job_ids)

    metrics = _JobMetrics()
    now = get_current_datetime()
    for job in jobs:
        jpd = get_job_provisioning_data(job)
        if jpd is None:
            continue
        jrd = get_job_runtime_data(job)
        resources = jpd.instance_type.resources
        price = jpd.price
        if jrd is not None and jrd.offer is not None:
            resources = jrd.offer.instance.resources
            price = jrd.offer.price
        gpus = resources.gpus
        cpus = resources.cpus
        run_spec = RunSpec.__response__.parse_raw(job.run.run_spec)
        labels = {
            "dstack_project_name": job.project.name,
            "dstack_user_name": job.run.user.name,
            "dstack_run_name": job.run_name,
            "dstack_run_id": str(job.run_id),
            "dstack_job_name": job.job_name,
            "dstack_job_id": str(job.id),
            "dstack_job_num": str(job.job_num),
            "dstack_replica_num": str(job.replica_num),
            "dstack_run_type": run_spec.configuration.type,
            "dstack_backend": jpd.get_base_backend().value,
            "dstack_gpu": gpus[0].name if gpus else "",
        }
        duration = (now - job.submitted_at).total_seconds()
        metrics.add_sample(_JOB_DURATION, labels, duration)
        metrics.add_sample(_JOB_PRICE, labels, price)
        metrics.add_sample(_JOB_GPU_COUNT, labels, len(gpus))
        metrics.add_sample(_JOB_CPU_COUNT, labels, cpus)
        metrics.add_sample(_JOB_MEMORY_TOTAL, labels, resources.memory_mib * 1024 * 1024)
        jmp = job_metrics_points.get(job.id)
        if jmp is not None:
            metrics.add_sample(_JOB_CPU_TIME, labels, jmp.cpu_usage_micro / 1_000_000)
            metrics.add_sample(_JOB_MEMORY_USAGE, labels, jmp.memory_usage_bytes)
            metrics.add_sample(_JOB_MEMORY_WORKING_SET, labels, jmp.memory_working_set_bytes)
            if gpus:
                gpu_memory_total = gpus[0].memory_mib * 1024 * 1024
                for gpu_num, (gpu_util, gpu_memory_usage) in enumerate(
                    zip(
                        json.loads(jmp.gpus_util_percent),
                        json.loads(jmp.gpus_memory_usage_bytes),
                    )
                ):
                    gpu_labels = labels.copy()
                    gpu_labels["dstack_gpu_num"] = gpu_num
                    metrics.add_sample(_JOB_GPU_USAGE_RATIO, gpu_labels, gpu_util / 100)
                    metrics.add_sample(_JOB_GPU_MEMORY_TOTAL, gpu_labels, gpu_memory_total)
                    metrics.add_sample(_JOB_GPU_MEMORY_USAGE, gpu_labels, gpu_memory_usage)
        jpm = job_prometheus_metrics.get(job.id)
        if jpm is not None:
            for metric in text_string_to_metric_families(jpm.text):
                metrics.add_metric(metric, labels)
    return metrics.values()


_COUNTER = "counter"
_GAUGE = "gauge"

_INSTANCE_DURATION = "dstack_instance_duration_seconds_total"
_INSTANCE_PRICE = "dstack_instance_price_dollars_per_hour"
_INSTANCE_GPU_COUNT = "dstack_instance_gpu_count"
_RUN_COUNT_TOTAL = "dstack_run_count_total"
_RUN_COUNT_TERMINATED = "dstack_run_count_terminated_total"
_RUN_COUNT_FAILED = "dstack_run_count_failed_total"
_RUN_COUNT_DONE = "dstack_run_count_done_total"
_JOB_DURATION = "dstack_job_duration_seconds_total"
_JOB_PRICE = "dstack_job_price_dollars_per_hour"
_JOB_GPU_COUNT = "dstack_job_gpu_count"
_JOB_CPU_COUNT = "dstack_job_cpu_count"
_JOB_CPU_TIME = "dstack_job_cpu_time_seconds_total"
_JOB_MEMORY_TOTAL = "dstack_job_memory_total_bytes"
_JOB_MEMORY_USAGE = "dstack_job_memory_usage_bytes"
_JOB_MEMORY_WORKING_SET = "dstack_job_memory_working_set_bytes"
_JOB_GPU_USAGE_RATIO = "dstack_job_gpu_usage_ratio"
_JOB_GPU_MEMORY_TOTAL = "dstack_job_gpu_memory_total_bytes"
_JOB_GPU_MEMORY_USAGE = "dstack_job_gpu_memory_usage_bytes"


class _Metrics(dict[str, Metric]):
    metrics: ClassVar[list[tuple[str, str, str]]]

    def __init__(self):
        super().__init__()
        for name, typ, documentation in self.metrics:
            self[name] = Metric(name=name, documentation=documentation, typ=typ)

    def add_sample(self, name: str, labels: dict[str, str], value: float) -> None:
        # NOTE: Keeps reference to labels.
        self[name].add_sample(name=name, labels=labels, value=value)

    def add_metric(self, metric: Metric, labels: dict[str, str]) -> None:
        # NOTE: Modifies and keeps reference to metric.
        name = metric.name
        samples = metric.samples
        stored_metric = self.get(name)
        if stored_metric is None:
            stored_metric = metric
            stored_metric.samples = []
            self[name] = stored_metric
        for sample in samples:
            sample.labels.update(labels)
            # text_string_to_metric_families "fixes" counter names appending _total,
            # we rebuild Sample to revert this
            stored_metric.samples.append(Sample(name, *sample[1:]))


class _InstanceMetrics(_Metrics):
    metrics = [
        (_INSTANCE_DURATION, _COUNTER, "Total seconds the instance is running"),
        (_INSTANCE_PRICE, _GAUGE, "Instance price, USD/hour"),
        (_INSTANCE_GPU_COUNT, _GAUGE, "Instance GPU count"),
    ]


class _RunMetrics(_Metrics):
    metrics = [
        (_RUN_COUNT_TOTAL, _COUNTER, "Total runs count"),
        (_RUN_COUNT_TERMINATED, _COUNTER, "Terminated runs count"),
        (_RUN_COUNT_FAILED, _COUNTER, "Failed runs count"),
        (_RUN_COUNT_DONE, _COUNTER, "Done runs count"),
    ]


class _JobMetrics(_Metrics):
    metrics = [
        (_JOB_DURATION, _COUNTER, "Total seconds the job is running"),
        (_JOB_PRICE, _GAUGE, "Job instance price, USD/hour"),
        (_JOB_GPU_COUNT, _GAUGE, "Job GPU count"),
        (_JOB_CPU_COUNT, _GAUGE, "Job CPU count"),
        (_JOB_CPU_TIME, _COUNTER, "Total CPU time consumed by the job, seconds"),
        (_JOB_MEMORY_TOTAL, _GAUGE, "Total memory allocated for the job, bytes"),
        (_JOB_MEMORY_USAGE, _GAUGE, "Memory used by the job (including cache), bytes"),
        (_JOB_MEMORY_WORKING_SET, _GAUGE, "Memory used by the job (not including cache), bytes"),
        (_JOB_GPU_USAGE_RATIO, _GAUGE, "Job GPU usage, percent (as 0.0-1.0)"),
        (_JOB_GPU_MEMORY_TOTAL, _GAUGE, "Total GPU memory allocated for the job, bytes"),
        (_JOB_GPU_MEMORY_USAGE, _GAUGE, "GPU memory used by the job, bytes"),
    ]


async def _get_job_metrics_points(
    session: AsyncSession, job_ids: Iterable[UUID]
) -> dict[UUID, JobMetricsPoint]:
    subquery = select(
        JobMetricsPoint,
        func.row_number()
        .over(
            partition_by=JobMetricsPoint.job_id,
            order_by=JobMetricsPoint.timestamp_micro.desc(),
        )
        .label("row_number"),
    ).subquery()
    res = await session.execute(
        select(aliased(JobMetricsPoint, subquery)).where(
            subquery.c.row_number == 1,
            subquery.c.job_id.in_(job_ids),
        )
    )
    return {p.job_id: p for p in res.scalars().all()}


async def _get_job_prometheus_metrics(
    session: AsyncSession, job_ids: Iterable[UUID]
) -> dict[UUID, JobPrometheusMetrics]:
    res = await session.execute(
        select(JobPrometheusMetrics).where(JobPrometheusMetrics.job_id.in_(job_ids))
    )
    return {p.job_id: p for p in res.scalars().all()}


def _render_metrics(metrics: Iterable[Metric]) -> Generator[str, None, None]:
    for metric in metrics:
        if not metric.samples:
            continue
        yield f"# HELP {metric.name} {metric.documentation}"
        yield f"# TYPE {metric.name} {metric.type}"
        for sample in metric.samples:
            parts: list[str] = [f"{sample.name}{{"]
            parts.extend(",".join(f'{name}="{value}"' for name, value in sample.labels.items()))
            parts.append(f"}} {float(sample.value)}")
            # text_string_to_metric_families converts milliseconds to float seconds
            if isinstance(sample.timestamp, float):
                parts.append(f" {int(sample.timestamp * 1000)}")
            yield "".join(parts)
