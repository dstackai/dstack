from dataclasses import dataclass
from typing import List, Optional, Tuple

from dstack._internal.core.models.configurations import ReplicaGroup
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import (
    get_job_spec,
    group_jobs_by_replica_latest,
)


@dataclass
class GroupRolloutState:
    active_replicas: List[Tuple[int, bool, int, List[JobModel]]]
    inactive_replicas: List[Tuple[int, bool, int, List[JobModel]]]
    has_out_of_date_replicas: bool
    non_terminated_replica_count: int
    unregistered_out_of_date_replica_count: int
    registered_non_terminating_replica_count: int


def build_replica_lists(
    run_model: RunModel,
    group_filter: Optional[str] = None,
) -> Tuple[
    List[Tuple[int, bool, int, List[JobModel]]], List[Tuple[int, bool, int, List[JobModel]]]
]:
    # lists of (importance, is_out_of_date, replica_num, jobs)
    active_replicas: list[tuple[int, bool, int, list[JobModel]]] = []
    inactive_replicas: list[tuple[int, bool, int, list[JobModel]]] = []

    for replica_num, replica_jobs in group_jobs_by_replica_latest(run_model.jobs):
        # Filter by group if specified
        if group_filter is not None:
            if not job_belongs_to_group(replica_jobs[0], group_filter):
                continue

        statuses = set(job.status for job in replica_jobs)
        deployment_num = replica_jobs[0].deployment_num  # same for all jobs
        is_out_of_date = deployment_num < run_model.deployment_num

        if {JobStatus.TERMINATING, *JobStatus.finished_statuses()} & statuses:
            # if there are any terminating or finished jobs, the replica is inactive
            inactive_replicas.append((0, is_out_of_date, replica_num, replica_jobs))
        elif JobStatus.SUBMITTED in statuses:
            # if there are any submitted jobs, the replica is active and has the importance of 0
            active_replicas.append((0, is_out_of_date, replica_num, replica_jobs))
        elif {JobStatus.PROVISIONING, JobStatus.PULLING} & statuses:
            # if there are any provisioning or pulling jobs, the replica is active and has the importance of 1
            active_replicas.append((1, is_out_of_date, replica_num, replica_jobs))
        elif not is_replica_registered(replica_jobs):
            # all jobs are running, but not receiving traffic, the replica is active and has the importance of 2
            active_replicas.append((2, is_out_of_date, replica_num, replica_jobs))
        else:
            # all jobs are running and ready, the replica is active and has the importance of 3
            active_replicas.append((3, is_out_of_date, replica_num, replica_jobs))

    # Sort by is_out_of_date (up-to-date first), importance (desc), and replica_num (asc)
    active_replicas.sort(key=lambda r: (r[1], -r[0], r[2]))

    return active_replicas, inactive_replicas


def get_group_rollout_state(run_model: RunModel, group: ReplicaGroup) -> GroupRolloutState:
    assert group.name is not None, "Group name is always set"
    active_replicas, inactive_replicas = build_replica_lists(
        run_model=run_model,
        group_filter=group.name,
    )

    non_terminated_replica_nums = set()
    unregistered_out_of_date_replica_count = 0
    registered_non_terminating_replica_count = 0

    for _, jobs in group_jobs_by_replica_latest(run_model.jobs):
        if not job_belongs_to_group(jobs[0], group.name):
            continue

        if any(not j.status.is_finished() for j in jobs):
            non_terminated_replica_nums.add(jobs[0].replica_num)

        if (
            any(j.deployment_num < run_model.deployment_num for j in jobs)
            and any(
                j.status not in [JobStatus.TERMINATING] + JobStatus.finished_statuses()
                for j in jobs
            )
            and not is_replica_registered(jobs)
        ):
            unregistered_out_of_date_replica_count += 1

        if is_replica_registered(jobs) and all(j.status != JobStatus.TERMINATING for j in jobs):
            registered_non_terminating_replica_count += 1

    return GroupRolloutState(
        active_replicas=active_replicas,
        inactive_replicas=inactive_replicas,
        has_out_of_date_replicas=has_out_of_date_replicas(run_model, group_filter=group.name),
        non_terminated_replica_count=len(non_terminated_replica_nums),
        unregistered_out_of_date_replica_count=unregistered_out_of_date_replica_count,
        registered_non_terminating_replica_count=registered_non_terminating_replica_count,
    )


def job_belongs_to_group(job: JobModel, group_name: str) -> bool:
    job_spec = get_job_spec(job)
    return job_spec.replica_group == group_name


def has_out_of_date_replicas(run: RunModel, group_filter: Optional[str] = None) -> bool:
    for job in run.jobs:
        # Filter jobs by group if specified
        if group_filter is not None:
            if not job_belongs_to_group(job, group_filter):
                continue
        if job.deployment_num < run.deployment_num and not (
            job.status.is_finished() or job.termination_reason == JobTerminationReason.SCALED_DOWN
        ):
            return True
    return False


def is_replica_registered(jobs: list[JobModel]) -> bool:
    # Only job_num=0 is supposed to receive service requests
    return jobs[0].registered
