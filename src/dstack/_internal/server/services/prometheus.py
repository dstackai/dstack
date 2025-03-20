import itertools
from collections.abc import Generator, Iterable
from datetime import timezone

from prometheus_client import Metric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus, RunSpec
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    JobPrometheusMetrics,
    ProjectModel,
    RunModel,
)
from dstack._internal.server.services.instances import get_instance_offer
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_runtime_data
from dstack._internal.utils.common import get_current_datetime

_INSTANCE_DURATION = "dstack_instance_duration_seconds_total"
_INSTANCE_PRICE = "dstack_instance_price_dollars_per_hour"
_INSTANCE_GPU_COUNT = "dstack_instance_gpu_count"
_JOB_DURATION = "dstack_job_duration_seconds_total"
_JOB_PRICE = "dstack_job_price_dollars_per_hour"
_JOB_GPU_COUNT = "dstack_job_gpu_count"


async def get_metrics(session: AsyncSession) -> str:
    metrics_iter = itertools.chain(
        await get_instance_metrics(session),
        await get_job_metrics(session),
        await get_job_gpu_metrics(session),
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
    metrics: dict[str, Metric] = {
        _INSTANCE_DURATION: Metric(
            name=_INSTANCE_DURATION,
            documentation="Total seconds the instance is running",
            typ="counter",
        ),
        _INSTANCE_PRICE: Metric(
            name=_INSTANCE_PRICE, documentation="Instance price, USD/hour", typ="gauge"
        ),
        _INSTANCE_GPU_COUNT: Metric(
            name=_INSTANCE_GPU_COUNT, documentation="Instance GPU count", typ="gauge"
        ),
    }
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
        duration = (now - instance.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        metrics[_INSTANCE_DURATION].add_sample(
            name=_INSTANCE_DURATION, labels=labels, value=duration
        )
        metrics[_INSTANCE_PRICE].add_sample(
            name=_INSTANCE_PRICE, labels=labels, value=instance.price or 0.0
        )
        metrics[_INSTANCE_GPU_COUNT].add_sample(
            name=_INSTANCE_GPU_COUNT, labels=labels, value=gpu_count
        )
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
    metrics: dict[str, Metric] = {
        _JOB_DURATION: Metric(
            name=_JOB_DURATION, documentation="Total seconds the job is running", typ="counter"
        ),
        _JOB_PRICE: Metric(
            name=_JOB_PRICE, documentation="Job instance price, USD/hour", typ="gauge"
        ),
        _JOB_GPU_COUNT: Metric(name=_JOB_GPU_COUNT, documentation="Job GPU count", typ="gauge"),
    }
    now = get_current_datetime()
    for job in jobs:
        jpd = get_job_provisioning_data(job)
        if jpd is None:
            continue
        jrd = get_job_runtime_data(job)
        gpus = jpd.instance_type.resources.gpus
        price = jpd.price
        if jrd is not None and jrd.offer is not None:
            gpus = jrd.offer.instance.resources.gpus
            price = jrd.offer.price
        run_spec = RunSpec.__response__.parse_raw(job.run.run_spec)
        labels = _get_job_labels(job)
        labels["dstack_run_type"] = run_spec.configuration.type
        labels["dstack_backend"] = jpd.get_base_backend().value
        labels["dstack_gpu"] = gpus[0].name if gpus else ""
        duration = (now - job.submitted_at.replace(tzinfo=timezone.utc)).total_seconds()
        metrics[_JOB_DURATION].add_sample(name=_JOB_DURATION, labels=labels, value=duration)
        metrics[_JOB_PRICE].add_sample(name=_JOB_PRICE, labels=labels, value=price)
        metrics[_JOB_GPU_COUNT].add_sample(name=_JOB_GPU_COUNT, labels=labels, value=len(gpus))
    return metrics.values()


async def get_job_gpu_metrics(session: AsyncSession) -> Iterable[Metric]:
    res = await session.execute(
        select(JobPrometheusMetrics)
        .join(JobModel)
        .join(ProjectModel)
        .where(JobModel.status.in_([JobStatus.RUNNING]))
        .order_by(ProjectModel.name, JobModel.job_name)
        .options(
            joinedload(JobPrometheusMetrics.job).joinedload(JobModel.project),
            joinedload(JobPrometheusMetrics.job)
            .joinedload(JobModel.run)
            .joinedload(RunModel.user),
        )
    )
    metrics_models = res.scalars().all()
    return _parse_and_enrich_job_gpu_metrics(metrics_models)


async def get_project_metrics(session: AsyncSession, project: ProjectModel) -> str:
    res = await session.execute(
        select(JobPrometheusMetrics)
        .join(JobModel)
        .where(
            JobModel.project_id == project.id,
            JobModel.status.in_([JobStatus.RUNNING]),
        )
        .order_by(JobModel.job_name)
        .options(
            joinedload(JobPrometheusMetrics.job).joinedload(JobModel.project),
            joinedload(JobPrometheusMetrics.job)
            .joinedload(JobModel.run)
            .joinedload(RunModel.user),
        )
    )
    metrics_models = res.scalars().all()
    return "\n".join(_render_metrics(_parse_and_enrich_job_gpu_metrics(metrics_models))) + "\n"


def _parse_and_enrich_job_gpu_metrics(
    metrics_models: Iterable[JobPrometheusMetrics],
) -> Iterable[Metric]:
    metrics: dict[str, Metric] = {}
    for metrics_model in metrics_models:
        for metric in text_string_to_metric_families(metrics_model.text):
            samples = metric.samples
            metric.samples = []
            name = metric.name
            metric = metrics.setdefault(name, metric)
            for sample in samples:
                labels = sample.labels
                labels.update(_get_job_labels(metrics_model.job))
                # text_string_to_metric_families "fixes" counter names appending _total,
                # we rebuild Sample to revert this
                metric.samples.append(Sample(name, labels, *sample[2:]))
    return metrics.values()


def _get_job_labels(job: JobModel) -> dict[str, str]:
    return {
        "dstack_project_name": job.project.name,
        "dstack_user_name": job.run.user.name,
        "dstack_run_name": job.run_name,
        "dstack_run_id": str(job.run_id),
        "dstack_job_name": job.job_name,
        "dstack_job_id": str(job.id),
        "dstack_job_num": str(job.job_num),
        "dstack_replica_num": str(job.replica_num),
    }


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
