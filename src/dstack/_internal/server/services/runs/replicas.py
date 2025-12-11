from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus, JobTerminationReason, RunSpec
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services import events
from dstack._internal.server.services.jobs import (
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
    switch_job_status,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.runs import create_job_model_for_new_submission, logger
from dstack._internal.server.services.secrets import get_project_secrets_mapping


async def retry_run_replica_jobs(
    session: AsyncSession, run_model: RunModel, latest_jobs: List[JobModel], *, only_failed: bool
):
    # FIXME: Handle getting image configuration errors or skip it.
    secrets = await get_project_secrets_mapping(
        session=session,
        project=run_model.project,
    )
    new_jobs = await get_jobs_from_run_spec(
        run_spec=RunSpec.__response__.parse_raw(run_model.run_spec),
        secrets=secrets,
        replica_num=latest_jobs[0].replica_num,
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
        # nothing to do
        return

    logger.info(
        "%s: scaling %s %s replica(s)",
        fmt(run_model),
        "UP" if replicas_diff > 0 else "DOWN",
        abs(replicas_diff),
    )

    # lists of (importance, is_out_of_date, replica_num, jobs)
    active_replicas = []
    inactive_replicas = []

    for replica_num, replica_jobs in group_jobs_by_replica_latest(run_model.jobs):
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

    # sort by is_out_of_date (up-to-date first), importance (desc), and replica_num (asc)
    active_replicas.sort(key=lambda r: (r[1], -r[0], r[2]))
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    if replicas_diff < 0:
        for _, _, _, replica_jobs in reversed(active_replicas[-abs(replicas_diff) :]):
            # scale down the less important replicas first
            for job in replica_jobs:
                if job.status.is_finished() or job.status == JobStatus.TERMINATING:
                    continue
                job.status = JobStatus.TERMINATING
                job.termination_reason = JobTerminationReason.SCALED_DOWN
                # background task will process the job later
    else:
        scheduled_replicas = 0

        # rerun inactive replicas
        for _, _, _, replica_jobs in inactive_replicas:
            if scheduled_replicas == replicas_diff:
                break
            await retry_run_replica_jobs(session, run_model, replica_jobs, only_failed=False)
            scheduled_replicas += 1

        secrets = await get_project_secrets_mapping(
            session=session,
            project=run_model.project,
        )

        for replica_num in range(
            len(active_replicas) + scheduled_replicas, len(active_replicas) + replicas_diff
        ):
            # FIXME: Handle getting image configuration errors or skip it.
            jobs = await get_jobs_from_run_spec(
                run_spec=run_spec,
                secrets=secrets,
                replica_num=replica_num,
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
