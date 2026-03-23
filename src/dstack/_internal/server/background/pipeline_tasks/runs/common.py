"""Shared helpers for run pipeline state modules."""

import json
from datetime import datetime
from typing import Optional

from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    ServiceConfiguration,
)
from dstack._internal.core.models.runs import JobStatus, RunSpec
from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import get_job_spec, get_jobs_from_run_spec
from dstack._internal.server.services.runs import create_job_model_for_new_submission
from dstack._internal.server.services.runs.replicas import build_replica_lists
from dstack._internal.server.services.services.autoscalers import get_service_scaler

PerGroupDesiredCounts = dict[str, int]
"""Maps group_name → desired replica count"""


def compute_desired_replica_counts(
    run_model: RunModel,
    configuration: ServiceConfiguration,
    gateway_stats: Optional[PerWindowStats],
    last_scaled_at: Optional[datetime],
) -> tuple[int, PerGroupDesiredCounts]:
    """Returns (total_desired, per_group_desired_counts)."""
    replica_groups = configuration.replica_groups
    prev_counts: PerGroupDesiredCounts = (
        json.loads(run_model.desired_replica_counts) if run_model.desired_replica_counts else {}
    )
    if (
        prev_counts == {}
        and len(replica_groups) == 1
        and replica_groups[0].name == DEFAULT_REPLICA_GROUP_NAME
    ):
        # Special case to avoid dropping the replica count to group.count.min
        # when a 0.20.7+ server first processes a service created by a pre-0.20.7 server.
        # TODO: remove once most users upgrade to 0.20.7+.
        prev_counts = {DEFAULT_REPLICA_GROUP_NAME: run_model.desired_replica_count}
    desired_counts: PerGroupDesiredCounts = {}
    total = 0
    for group in replica_groups:
        scaler = get_service_scaler(group.count, group.scaling)
        assert group.name is not None, "Group name is always set"
        group_desired = scaler.get_desired_count(
            current_desired_count=prev_counts.get(group.name, group.count.min or 0),
            stats=gateway_stats,
            last_scaled_at=last_scaled_at,
        )
        desired_counts[group.name] = group_desired
        total += group_desired
    return total, desired_counts


async def build_scale_up_job_models(
    run_model: RunModel,
    run_spec: RunSpec,
    secrets: dict,
    replicas_diff: int,
    group_name: Optional[str] = None,
    replica_num_start: Optional[int] = None,
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
        if replica_num_start is not None:
            first_replica_num = replica_num_start
        else:
            first_replica_num = max((job.replica_num for job in run_model.jobs), default=-1) + 1
        new_replicas_needed = replicas_diff - scheduled_replicas
        for i in range(new_replicas_needed):
            new_replica_num = first_replica_num + i
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
