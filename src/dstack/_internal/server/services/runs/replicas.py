from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from dstack._internal.core.models.configurations import ReplicaGroup, ServiceConfiguration
from dstack._internal.core.models.routers import RouterType
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason, RunSpec
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import (
    get_job_provisioning_data,
    get_job_spec,
    group_jobs_by_replica_latest,
)

#   ROUTER_NOT_PROVISIONED — router job exists but its internal_ip is not yet
#                            known. The condition is transient; the caller
#                            should defer this worker and retry on the next
#                            pipeline tick (subject to a wait timeout — see
#                            ROUTER_PROVISIONING_WAIT_TIMEOUT_SECONDS in
#                            jobs_running.py).
#
#   ROUTER_FAILED          — router job has reached a terminal state
#                            (TERMINATING/TERMINATED/FAILED/ABORTED/DONE).
#                            The condition is permanent; the caller should
#                            stop deferring and terminate this worker with a
#                            clear reason — waiting longer cannot recover the
#                            run because the router will not come back with a
#                            fresh internal_ip.
ROUTER_NOT_PROVISIONED: Dict[str, str] = {}
ROUTER_FAILED: Dict[str, str] = {}


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


def get_router_replica_group(run_spec: RunSpec) -> Optional[ReplicaGroup]:
    """Return the (single) replica group with a `router:` field, or None.

    `validate_at_most_one_router_replica_group` guarantees at most one such
    group exists, so we can safely return on the first match.
    """
    cfg = run_spec.configuration
    if not isinstance(cfg, ServiceConfiguration):
        return None
    for g in cfg.replica_groups:
        if g.router is not None:
            return g
    return None


def get_router_replica_num(run_spec: RunSpec) -> Optional[int]:
    """Return the global replica_num assigned to the router replica group, or
    None if the run has no router replica group. Used by _fetch_run_model in
    pipeline_tasks/jobs_running.py to load the router replica's job alongside
    the worker's own same-replica siblings, so get_router_env_for_job can see the
    router's status / internal_ip.
    """
    cfg = run_spec.configuration
    if not isinstance(cfg, ServiceConfiguration):
        return None
    global_replica_num = 0
    for group in cfg.replica_groups:
        if group.router is not None:
            return global_replica_num
        assert group.count.min is not None
        global_replica_num += group.count.min
    return None


def find_router_job(run_model: RunModel, router_group_name: str) -> Optional[JobModel]:
    for j in run_model.jobs:
        if job_belongs_to_group(j, router_group_name):
            return j
    return None


def get_router_env_for_job(
    run_model: RunModel, run_spec: RunSpec, job_model: JobModel
) -> Optional[Dict[str, str]]:
    """Compute env vars exposing the router replica's address to a worker job.

    Returns one of four values, each communicating a distinct outcome:

      None                    -> not applicable. Either the run has no router
                                 replica group, or this job IS the router
                                 replica. Caller does nothing.
      ROUTER_NOT_PROVISIONED  -> router job exists but has no internal_ip yet.

      ROUTER_FAILED           -> router job has reached a terminal state and
                                 can never expose an internal_ip. Caller terminates
                                 this worker; waiting cannot
                                 recover.
      {"DSTACK_ROUTER_..."}   -> ready-to-merge env dict containing the
                                 router replica's internal IP.
    """
    router_group = get_router_replica_group(run_spec)
    if router_group is None or router_group.name is None:
        return None
    # DSTACK_ROUTER_INTERNAL_IP is Dynamo-specific. SGLang workers
    # are registered via the worker-sync pipeline (ServiceRouterWorkerSyncModel)
    if router_group.router is None or router_group.router.type != RouterType.DYNAMO:
        return None
    if job_belongs_to_group(job_model, router_group.name):
        # Router replica itself doesn't need to be told its own IP.
        return None

    router_job = find_router_job(run_model, router_group.name)
    if router_job is None:
        # No router job yet — the run was just submitted and jobs haven't
        # been materialized. Treat as "not provisioned" so the caller defers.
        return ROUTER_NOT_PROVISIONED

    # If the router has reached a terminal state, the worker cannot recover
    # by waiting — the router will not come back with a fresh internal_ip
    # under the same job. Surface this as ROUTER_FAILED so the caller can
    # stop the wait loop and terminate the worker with a clear reason.
    if router_job.status == JobStatus.TERMINATING or router_job.status.is_finished():
        return ROUTER_FAILED

    # Router is alive but may not yet have been assigned a machine.
    jpd = get_job_provisioning_data(router_job)
    if jpd is None or not jpd.internal_ip:
        return ROUTER_NOT_PROVISIONED

    return {"DSTACK_ROUTER_INTERNAL_IP": jpd.internal_ip}
