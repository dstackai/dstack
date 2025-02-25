from collections.abc import Generator, Iterable

from prometheus_client import Metric
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.samples import Sample
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.models import JobModel, JobPrometheusMetrics, ProjectModel


async def get_metrics(session: AsyncSession) -> str:
    res = await session.execute(
        select(JobPrometheusMetrics)
        .join(JobModel)
        .join(ProjectModel)
        .where(JobModel.status.in_([JobStatus.RUNNING]))
        .order_by(ProjectModel.name, JobModel.job_name)
        .options(joinedload(JobPrometheusMetrics.job).joinedload(JobModel.project))
    )
    metrics_models = res.scalars().all()
    return _process_metrics(metrics_models)


async def get_project_metrics(session: AsyncSession, project: ProjectModel) -> str:
    res = await session.execute(
        select(JobPrometheusMetrics)
        .join(JobModel)
        .where(
            JobModel.project_id == project.id,
            JobModel.status.in_([JobStatus.RUNNING]),
        )
        .order_by(JobModel.job_name)
        .options(joinedload(JobPrometheusMetrics.job).joinedload(JobModel.project))
    )
    metrics_models = res.scalars().all()
    return _process_metrics(metrics_models)


def _process_metrics(metrics_models: Iterable[JobPrometheusMetrics]) -> str:
    metrics = _parse_and_enrich_metrics(metrics_models)
    if not metrics:
        return ""
    return "\n".join(_render_metrics(metrics)) + "\n"


def _parse_and_enrich_metrics(metrics_models: Iterable[JobPrometheusMetrics]) -> list[Metric]:
    metrics: dict[str, Metric] = {}
    for metrics_model in metrics_models:
        for metric in text_string_to_metric_families(metrics_model.text):
            samples = metric.samples
            metric.samples = []
            name = metric.name
            metric = metrics.setdefault(name, metric)
            for sample in samples:
                labels = sample.labels
                labels.update(_get_dstack_labels(metrics_model.job))
                # text_string_to_metric_families "fixes" counter names appending _total,
                # we rebuild Sample to revert this
                metric.samples.append(Sample(name, labels, *sample[2:]))
    return list(metrics.values())


def _get_dstack_labels(job: JobModel) -> dict[str, str]:
    return {
        "dstack_project_name": job.project.name,
        "dstack_run_name": job.run_name,
        "dstack_job_name": job.job_name,
        "dstack_job_num": str(job.job_num),
        "dstack_replica_num": str(job.replica_num),
    }


def _render_metrics(metrics: Iterable[Metric]) -> Generator[str, None, None]:
    for metric in metrics:
        yield f"# HELP {metric.name} {metric.documentation}"
        yield f"# TYPE {metric.name} {metric.type}"
        for sample in metric.samples:
            parts: list[str] = [f"{sample.name}{{"]
            parts.extend(",".join(f'{name}="{value}"' for name, value in sample.labels.items()))
            parts.append(f"}} {sample.value}")
            # text_string_to_metric_families converts milliseconds to float seconds
            if isinstance(sample.timestamp, float):
                parts.append(f" {int(sample.timestamp * 1000)}")
            yield "".join(parts)
