from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from dstack._internal.core.models.configurations import ReplicaGroup, ServiceConfiguration
from dstack._internal.core.models.gateways import GatewayReplicaStatus
from dstack._internal.core.models.routers import RouterType
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason, RunSpec
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.gateways import get_gateway_compute_models
from dstack._internal.server.services.jobs import (
    get_job_provisioning_data,
    get_job_spec,
    group_jobs_by_replica_latest,
)


@dataclass
class GroupRolloutState:
    active_replicas: List[Tuple[int, bool, int, List[JobModel]]]
    inactive_replicas: List[Tuple[int, bool, int, List[JobModel]]]
    has_out_of_date_replicas: bool
    non_terminated_replica_count: int
    not_receiving_traffic_out_of_date_replica_count: int
    receiving_traffic_non_terminating_replica_count: int


class RouterEnvStatus(str, Enum):
    """Outcomes returned from get_router_env_for_job() when no env dict is
    appropriate. Each value carries a distinct caller-side action.

    Using an enum (rather than empty-dict sentinels) means callers can rely
    on either `is` or `==` to compare — both yield correct, unambiguous
    results — and stray dicts from elsewhere can never accidentally match.

      NOT_PROVISIONED — router job exists but its internal_ip is not yet
                        known. Transient; caller should defer this worker
                        and retry on the next pipeline tick (subject to
                        ROUTER_PROVISIONING_WAIT_TIMEOUT_SECONDS in
                        jobs_running.py).
      FAILED          — router job has reached a terminal state
                        (TERMINATING/TERMINATED/FAILED/ABORTED/DONE).
                        Permanent; caller should stop deferring and
                        terminate this worker — waiting longer cannot
                        recover because the router will not come back with
                        a fresh internal_ip.
    """

    NOT_PROVISIONED = "not_provisioned"
    FAILED = "failed"


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
        elif not is_replica_receiving_traffic(run_model, replica_jobs):
            # all jobs are running, but not receiving traffic, the replica is active and has the importance of 2
            active_replicas.append((2, is_out_of_date, replica_num, replica_jobs))
        else:
            # all jobs are running and receiving traffic, the replica is active and has the importance of 3
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
    not_receiving_traffic_out_of_date_replica_count = 0
    receiving_traffic_non_terminating_replica_count = 0

    for _, jobs in group_jobs_by_replica_latest(run_model.jobs):
        if not job_belongs_to_group(jobs[0], group.name):
            continue

        if any(not j.status.is_finished() for j in jobs):
            non_terminated_replica_nums.add(jobs[0].replica_num)

        receiving_traffic = is_replica_receiving_traffic(run_model, jobs)

        if (
            any(j.deployment_num < run_model.deployment_num for j in jobs)
            and any(
                j.status not in [JobStatus.TERMINATING] + JobStatus.finished_statuses()
                for j in jobs
            )
            and not receiving_traffic
        ):
            not_receiving_traffic_out_of_date_replica_count += 1

        if receiving_traffic and all(j.status != JobStatus.TERMINATING for j in jobs):
            receiving_traffic_non_terminating_replica_count += 1

    return GroupRolloutState(
        active_replicas=active_replicas,
        inactive_replicas=inactive_replicas,
        has_out_of_date_replicas=has_out_of_date_replicas(run_model, group_filter=group.name),
        non_terminated_replica_count=len(non_terminated_replica_nums),
        not_receiving_traffic_out_of_date_replica_count=(
            not_receiving_traffic_out_of_date_replica_count
        ),
        receiving_traffic_non_terminating_replica_count=(
            receiving_traffic_non_terminating_replica_count
        ),
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


def is_replica_receiving_traffic(run_model: RunModel, jobs: list[JobModel]) -> bool:
    # Only job_num=0 is supposed to receive service requests
    job = jobs[0]
    if not job.ready:
        # waiting for probes to pass
        return False
    if not job.registered:
        # served by the service's router replica
        return True
    if run_model.gateway is None:
        # served by the in-server proxy
        return True
    running_gateway_replica_ids = {
        replica.id
        for replica in get_gateway_compute_models(run_model.gateway)
        if replica.status == GatewayReplicaStatus.RUNNING
    }
    if not running_gateway_replica_ids:
        return False
    registration_by_replica_id = {
        r.gateway_replica_id: r for r in job.service_replica_registrations
    }
    for replica_id in running_gateway_replica_ids:
        registration = registration_by_replica_id.get(replica_id)
        if registration is None or not registration.is_registered:
            return False
    return True


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


def find_router_job(run_model: RunModel, router_group_name: str) -> Optional[JobModel]:
    for j in run_model.jobs:
        if job_belongs_to_group(j, router_group_name):
            return j
    return None


def get_router_env_for_job(
    run_model: RunModel, run_spec: RunSpec, job_model: JobModel
) -> Optional[Union[Dict[str, str], RouterEnvStatus]]:
    """Compute env vars exposing the router replica's address to a worker job.

    Returns one of four values, each communicating a distinct outcome:

      None                                -> not applicable. Either the
                                             run has no router replica
                                             group, or this job IS the
                                             router replica. Caller does
                                             nothing.
      RouterEnvStatus.NOT_PROVISIONED     -> router job exists but has no
                                             internal_ip yet. Caller defers.
      RouterEnvStatus.FAILED              -> router job has reached a
                                             terminal state and can never
                                             expose an internal_ip. Caller
                                             terminates this worker;
                                             waiting cannot recover.
      {"DSTACK_ROUTER_INTERNAL_IP": ...}  -> ready-to-merge env dict
                                             containing the router
                                             replica's internal IP.
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
        # The router's latest submission is in a terminal state and was
        # filtered out by _fetch_run_model's not-terminated predicate.
        return RouterEnvStatus.FAILED

    # If the router has reached a terminal state, the worker cannot recover
    # by waiting — the router will not come back with a fresh internal_ip
    # under the same job. Surface this as FAILED so the caller can stop
    # the wait loop and terminate the worker with a clear reason.
    if router_job.status == JobStatus.TERMINATING or router_job.status.is_finished():
        return RouterEnvStatus.FAILED

    # Router is alive but may not yet have been assigned a machine.
    jpd = get_job_provisioning_data(router_job)
    if jpd is None or not jpd.internal_ip:
        return RouterEnvStatus.NOT_PROVISIONED

    return {"DSTACK_ROUTER_INTERNAL_IP": jpd.internal_ip}
