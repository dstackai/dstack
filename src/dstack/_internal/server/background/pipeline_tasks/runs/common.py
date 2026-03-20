"""Shared helpers for run pipeline state modules."""

from typing import Optional

from dstack._internal.core.models.runs import JobStatus, RunSpec
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import get_job_spec, get_jobs_from_run_spec
from dstack._internal.server.services.runs import create_job_model_for_new_submission
from dstack._internal.server.services.runs.replicas import build_replica_lists


async def build_scale_up_job_models(
    run_model: RunModel,
    run_spec: RunSpec,
    secrets: dict,
    replicas_diff: int,
    group_name: Optional[str] = None,
) -> list[JobModel]:
    """Build new JobModel instances for scaling up."""
    if replicas_diff <= 0:
        return []

    _, inactive_replicas = build_replica_lists(run_model, group_filter=group_name)
    new_job_models: list[JobModel] = []
    scheduled_replicas = 0

    # Retry inactive replicas first.
    for _, _, replica_num, replica_jobs in inactive_replicas:
        if scheduled_replicas == replicas_diff:
            break
        job_spec = get_job_spec(replica_jobs[0])
        replica_group_name = job_spec.replica_group
        new_jobs = await get_jobs_from_run_spec(
            run_spec=run_spec,
            secrets=secrets,
            replica_num=replica_num,
            replica_group_name=replica_group_name,
        )
        for old_job_model, new_job in zip(replica_jobs, new_jobs):
            job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=new_job,
                status=JobStatus.SUBMITTED,
            )
            job_model.submission_num = old_job_model.submission_num + 1
            new_job_models.append(job_model)
        scheduled_replicas += 1

    # Create new replicas for the remainder
    if scheduled_replicas < replicas_diff:
        max_replica_num = max((job.replica_num for job in run_model.jobs), default=-1)
        new_replicas_needed = replicas_diff - scheduled_replicas
        for i in range(new_replicas_needed):
            new_replica_num = max_replica_num + 1 + i
            new_jobs = await get_jobs_from_run_spec(
                run_spec=run_spec,
                secrets=secrets,
                replica_num=new_replica_num,
                replica_group_name=group_name,
            )
            for new_job in new_jobs:
                job_model = create_job_model_for_new_submission(
                    run_model=run_model,
                    job=new_job,
                    status=JobStatus.SUBMITTED,
                )
                new_job_models.append(job_model)

    return new_job_models
