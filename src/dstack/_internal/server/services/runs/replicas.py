from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import ReplicaGroup
from dstack._internal.core.models.runs import JobSpec, JobStatus, JobTerminationReason, RunSpec
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.jobs import (
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
    switch_job_status,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import (
    create_job_model_for_new_submission,
    logger,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping


async def retry_run_replica_jobs(
    session: AsyncSession, run_model: RunModel, latest_jobs: List[JobModel], *, only_failed: bool
):
    # FIXME: Handle getting image configuration errors or skip it.
    secrets = await get_project_secrets_mapping(
        session=session,
        project=run_model.project,
    )

    # Determine replica group from existing job
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    job_spec = JobSpec.parse_raw(latest_jobs[0].job_spec_data)
    replica_group_name = job_spec.replica_group

    new_jobs = await get_jobs_from_run_spec(
        run_spec=run_spec,
        secrets=secrets,
        replica_num=latest_jobs[0].replica_num,
        replica_group_name=replica_group_name,
    )
    assert len(new_jobs) == len(latest_jobs), (
        "Changing the number of jobs within a replica is not yet supported"
    )
    for job_model, new_job in zip(latest_jobs, new_jobs):
        if not (job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING):
            if only_failed:
                # No need to resubmit, skip
                continue
            # The job is not finished, but we have to retry all jobs. Terminate it
            job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
            job_model.termination_reason_message = "Replica is to be retried"
            switch_job_status(session, job_model, JobStatus.TERMINATING)

        new_job_model = create_job_model_for_new_submission(
            run_model=run_model,
            job=new_job,
            status=JobStatus.SUBMITTED,
        )
        # dirty hack to avoid passing all job submissions
        new_job_model.submission_num = job_model.submission_num + 1
        session.add(new_job_model)
        events.emit(
            session,
            f"Job created when re-running replica. Status: {new_job_model.status.upper()}",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(new_job_model)],
        )


def is_replica_registered(jobs: list[JobModel]) -> bool:
    # Only job_num=0 is supposed to receive service requests
    return jobs[0].registered


async def scale_run_replicas(session: AsyncSession, run_model: RunModel, replicas_diff: int):
    if replicas_diff == 0:
        return

    logger.info(
        "%s: scaling %s %s replica(s)",
        fmt(run_model),
        "UP" if replicas_diff > 0 else "DOWN",
        abs(replicas_diff),
    )

    active_replicas, inactive_replicas = _build_replica_lists(run_model, run_model.jobs)
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    if replicas_diff < 0:
        _scale_down_replicas(session, active_replicas, abs(replicas_diff))
    else:
        await _scale_up_replicas(
            session,
            run_model,
            active_replicas,
            inactive_replicas,
            replicas_diff,
            run_spec,
            group_name=None,
        )


def _build_replica_lists(
    run_model: RunModel,
    jobs: List[JobModel],
    group_filter: Optional[str] = None,
) -> Tuple[
    List[Tuple[int, bool, int, List[JobModel]]], List[Tuple[int, bool, int, List[JobModel]]]
]:
    # lists of (importance, is_out_of_date, replica_num, jobs)
    active_replicas: list[tuple[int, bool, int, list[JobModel]]] = []
    inactive_replicas: list[tuple[int, bool, int, list[JobModel]]] = []

    for replica_num, replica_jobs in group_jobs_by_replica_latest(jobs):
        # Filter by group if specified
        if group_filter is not None:
            try:
                job_spec = JobSpec.parse_raw(replica_jobs[0].job_spec_data)
                if job_spec.replica_group != group_filter:
                    continue
            except Exception:
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


def _scale_down_replicas(
    session: AsyncSession,
    active_replicas: List[Tuple[int, bool, int, List[JobModel]]],
    count: int,
) -> None:
    """Scale down by terminating the least important replicas"""
    if count <= 0:
        return

    for _, _, _, replica_jobs in reversed(active_replicas[-count:]):
        for job in replica_jobs:
            if job.status.is_finished() or job.status == JobStatus.TERMINATING:
                continue
            job.termination_reason = JobTerminationReason.SCALED_DOWN
            switch_job_status(session, job, JobStatus.TERMINATING, events.SystemActor())
            # background task will process the job later


async def _scale_up_replicas(
    session: AsyncSession,
    run_model: RunModel,
    active_replicas: List[Tuple[int, bool, int, List[JobModel]]],
    inactive_replicas: List[Tuple[int, bool, int, List[JobModel]]],
    replicas_diff: int,
    run_spec: RunSpec,
    group_name: Optional[str] = None,
) -> None:
    """Scale up by retrying inactive replicas and creating new ones"""
    if replicas_diff <= 0:
        return

    scheduled_replicas = 0

    # Retry inactive replicas first
    for _, _, _, replica_jobs in inactive_replicas:
        if scheduled_replicas == replicas_diff:
            break
        await retry_run_replica_jobs(session, run_model, replica_jobs, only_failed=False)
        scheduled_replicas += 1

    # Create new replicas
    if scheduled_replicas < replicas_diff:
        secrets = await get_project_secrets_mapping(
            session=session,
            project=run_model.project,
        )

        max_replica_num = max((job.replica_num for job in run_model.jobs), default=-1)

        new_replicas_needed = replicas_diff - scheduled_replicas
        for i in range(new_replicas_needed):
            new_replica_num = max_replica_num + 1 + i
            jobs = await get_jobs_from_run_spec(
                run_spec=run_spec,
                secrets=secrets,
                replica_num=new_replica_num,
                replica_group_name=group_name,
            )
            for job in jobs:
                job_model = create_job_model_for_new_submission(
                    run_model=run_model,
                    job=job,
                    status=JobStatus.SUBMITTED,
                )
                session.add(job_model)
                events.emit(
                    session,
                    f"Job created on new replica submission. Status: {job_model.status.upper()}",
                    actor=events.SystemActor(),
                    targets=[events.Target.from_model(job_model)],
                )
                # Append to run_model.jobs so that when processing later replica groups in the same
                # transaction, run_model.jobs includes jobs from previously processed groups.
                run_model.jobs.append(job_model)


async def scale_run_replicas_per_group(
    session: AsyncSession,
    run_model: RunModel,
    replicas: List[ReplicaGroup],
    desired_replica_counts: Dict[str, int],
) -> None:
    """Scale each replica group independently"""
    if not replicas:
        return

    for group in replicas:
        if group.name is None:
            continue
        group_desired = desired_replica_counts.get(group.name, group.count.min or 0)

        # Build replica lists filtered by this group
        active_replicas, inactive_replicas = _build_replica_lists(
            run_model=run_model, jobs=run_model.jobs, group_filter=group.name
        )

        # Count active replicas
        active_group_count = len(active_replicas)
        group_diff = group_desired - active_group_count

        if group_diff != 0:
            # Check if rolling deployment is in progress for THIS GROUP
            from dstack._internal.server.background.tasks.process_runs import (
                _has_out_of_date_replicas,
            )

            group_has_out_of_date = _has_out_of_date_replicas(run_model, group_filter=group.name)

            # During rolling deployment, don't scale down old replicas
            # Let rolling deployment handle stopping old replicas
            if group_diff < 0 and group_has_out_of_date:
                # Skip scaling down during rolling deployment
                continue
            await scale_run_replicas_for_group(
                session=session,
                run_model=run_model,
                group=group,
                replicas_diff=group_diff,
                run_spec=RunSpec.__response__.parse_raw(run_model.run_spec),
                active_replicas=active_replicas,
                inactive_replicas=inactive_replicas,
            )


async def scale_run_replicas_for_group(
    session: AsyncSession,
    run_model: RunModel,
    group: ReplicaGroup,
    replicas_diff: int,
    run_spec: RunSpec,
    active_replicas: List[Tuple[int, bool, int, List[JobModel]]],
    inactive_replicas: List[Tuple[int, bool, int, List[JobModel]]],
) -> None:
    """Scale a specific replica group up or down"""
    if replicas_diff == 0:
        return

    logger.info(
        "%s: scaling %s %s replica(s) for group '%s'",
        fmt(run_model),
        "UP" if replicas_diff > 0 else "DOWN",
        abs(replicas_diff),
        group.name,
    )

    if replicas_diff < 0:
        _scale_down_replicas(session, active_replicas, abs(replicas_diff))
    else:
        await _scale_up_replicas(
            session=session,
            run_model=run_model,
            active_replicas=active_replicas,
            inactive_replicas=inactive_replicas,
            replicas_diff=replicas_diff,
            run_spec=run_spec,
            group_name=group.name,
        )
