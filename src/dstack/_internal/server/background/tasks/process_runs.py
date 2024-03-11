import asyncio
import datetime
import itertools
import uuid
from typing import Iterable, List, Optional, Set, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.instances import InstanceOffer
from dstack._internal.core.models.profiles import ProfileRetryPolicy
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel, RunModel
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    get_jobs_from_run_spec,
)
from dstack._internal.server.services.runs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    create_job_model_for_new_submission,
    fmt,
    process_terminating_run,
    run_model_to_run,
)
from dstack._internal.server.utils.common import wait_unlock
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
PROCESSING_INTERVAL = datetime.timedelta(seconds=2)
JOB_TERMINATION_REASONS_TO_RETRY = {
    JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
}


async def process_runs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK:
            res = await session.execute(
                sa.select(RunModel).where(
                    RunModel.status.not_in(RunStatus.finished_statuses()),
                    RunModel.last_processed_at < get_current_datetime() - PROCESSING_INTERVAL,
                    RunModel.id.not_in(PROCESSING_RUNS_IDS),
                )
            )
            runs = res.scalars().all()
            PROCESSING_RUNS_IDS.update(run.id for run in runs)

    futures = [process_single_run(run.id, [job.id for job in run.jobs]) for run in runs]
    try:
        for future in asyncio.as_completed(futures):
            run_id = await future
            PROCESSING_RUNS_IDS.remove(run_id)  # unlock job processing as soon as possible
    finally:
        PROCESSING_RUNS_IDS.difference_update(
            run.id for run in runs
        )  # ensure that all runs are unlocked


async def process_single_run(run_id: uuid.UUID, job_ids: List[uuid.UUID]) -> uuid.UUID:
    jobs_ids_set = set(job_ids)
    await wait_unlock(SUBMITTED_PROCESSING_JOBS_LOCK, SUBMITTED_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(RUNNING_PROCESSING_JOBS_LOCK, RUNNING_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(
        TERMINATING_PROCESSING_JOBS_LOCK, TERMINATING_PROCESSING_JOBS_IDS, jobs_ids_set
    )

    async with get_session_ctx() as session:
        run = await session.get(RunModel, run_id)
        if run is None:
            logger.error(f"Run {run_id} not found")
            return run_id

        if run.status == RunStatus.PENDING:
            await process_pending_run(session, run)
        elif run.status in {RunStatus.SUBMITTED, RunStatus.PROVISIONING, RunStatus.RUNNING}:
            await process_active_run(session, run)
        elif run.status == RunStatus.TERMINATING:
            await process_terminating_run(session, run)
        else:
            logger.error("%s: unexpected status %s", fmt(run), run.status.name)
            run.status = RunStatus.TERMINATING
            run.termination_reason = RunTerminationReason.SERVER_ERROR

        run.last_processed_at = get_current_datetime()
        await session.commit()

    return run_id


async def process_pending_run(session: AsyncSession, run_model: RunModel):
    """Jobs are not created yet"""

    # TODO(egor-s): consider retry delay

    await session.execute(
        sa.select(RunModel)
        .where(RunModel.id == run_model.id)
        .execution_options(populate_existing=True)
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
    )
    run = run_model_to_run(run_model)

    replicas = 1
    if run.run_spec.configuration.type == "service":
        # TODO(egor-s): consider max for auto-scaling
        replicas = run.run_spec.configuration.replicas.min or 0

    scheduled_replicas = 0
    # Resubmit existing replicas
    for replica_num, replica_jobs in itertools.groupby(
        run.jobs, key=lambda j: j.job_spec.replica_num
    ):
        if scheduled_replicas >= replicas:
            break
        scheduled_replicas += 1
        for job in replica_jobs:
            new_job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=job,
                status=JobStatus.SUBMITTED,
            )
            session.add(new_job_model)
    # Create missing replicas
    for replica_num in range(scheduled_replicas, replicas):
        jobs = get_jobs_from_run_spec(run.run_spec, replica_num=replica_num)
        for job in jobs:
            job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=job,
                status=JobStatus.SUBMITTED,
            )
            session.add(job_model)

    run_model.status = RunStatus.SUBMITTED
    logger.info("%s: run status has changed PENDING -> SUBMITTED", fmt(run_model))


async def process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, provisioning, or running.
    We handle fails, scaling, and status changes.
    """
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    retry_policy = run_spec.profile.retry_policy or ProfileRetryPolicy()
    retry_single_job = can_retry_single_job(run_spec)

    run_statuses: Set[RunStatus] = set()
    run_termination_reasons: Set[RunTerminationReason] = set()
    replicas_to_retry: List[Tuple[int, List[JobModel]]] = []

    # TODO(egor-s): collect replicas count and statuses for auto-scaling
    for replica_num, jobs in group_jobs_by_replica_latest(run_model.jobs):
        replica_statuses: Set[RunStatus] = set()
        replica_needs_retry = False

        for job in jobs:
            if job.status == JobStatus.DONE or (
                job.status == JobStatus.TERMINATING
                and job.termination_reason == JobTerminationReason.DONE_BY_RUNNER
            ):
                # the job is done or going to be done
                replica_statuses.add(RunStatus.DONE)
            elif job.termination_reason == JobTerminationReason.SCALED_DOWN:
                pass  # the job was scaled down
            elif job.status == JobStatus.RUNNING:
                # the job is running
                replica_statuses.add(RunStatus.RUNNING)
            elif job.status in {JobStatus.PROVISIONING, JobStatus.PULLING}:
                # the job is provisioning
                replica_statuses.add(RunStatus.PROVISIONING)
            elif job.status == JobStatus.SUBMITTED:
                # the job is submitted
                replica_statuses.add(RunStatus.SUBMITTED)
            elif job.status == JobStatus.FAILED or (
                job.status == JobStatus.TERMINATING
                and job.termination_reason
                not in {JobTerminationReason.DONE_BY_RUNNER, JobTerminationReason.SCALED_DOWN}
            ):
                if await is_retry_enabled(session, job, retry_policy):
                    if await is_retry_limit_exceeded(session, job, retry_policy):
                        replica_statuses.add(RunStatus.FAILED)
                        run_termination_reasons.add(RunTerminationReason.RETRY_LIMIT_EXCEEDED)
                    else:
                        # do a retry
                        replica_needs_retry = True
                else:
                    # just failed
                    replica_statuses.add(RunStatus.FAILED)
                    run_termination_reasons.add(RunTerminationReason.JOB_FAILED)
            elif job.status in {JobStatus.TERMINATING, JobStatus.TERMINATED, JobStatus.ABORTED}:
                pass  # unexpected, but let's ignore it
            else:
                raise ValueError(f"Unexpected job status {job.status}")

        if RunStatus.FAILED in replica_statuses:
            run_statuses.add(RunStatus.FAILED)
        else:
            if replica_needs_retry:
                replicas_to_retry.append((replica_num, jobs))
            if not replica_needs_retry or retry_single_job:
                run_statuses.update(replica_statuses)

    termination_reason: Optional[RunTerminationReason] = None
    if RunStatus.FAILED in run_statuses:
        new_status = RunStatus.TERMINATING
        if RunTerminationReason.JOB_FAILED in run_termination_reasons:
            termination_reason = RunTerminationReason.JOB_FAILED
        elif RunTerminationReason.RETRY_LIMIT_EXCEEDED in run_termination_reasons:
            termination_reason = RunTerminationReason.RETRY_LIMIT_EXCEEDED
        else:
            raise ValueError(f"Unexpected termination reason {run_termination_reasons}")
    elif RunStatus.RUNNING in run_statuses:
        new_status = RunStatus.RUNNING
    elif RunStatus.PROVISIONING in run_statuses:
        new_status = RunStatus.PROVISIONING
    elif RunStatus.SUBMITTED in run_statuses:
        new_status = RunStatus.SUBMITTED
    elif RunStatus.DONE in run_statuses and not replicas_to_retry:
        new_status = RunStatus.TERMINATING
        termination_reason = RunTerminationReason.ALL_JOBS_DONE
    else:
        new_status = RunStatus.PENDING

    if new_status not in {RunStatus.TERMINATING, RunStatus.PENDING}:
        # No need to retry if the run is terminating,
        # pending run will retry replicas in `process_pending_run`
        for _, replica_jobs in replicas_to_retry:
            await retry_replica_jobs(
                session, run_model, replica_jobs, only_failed=retry_single_job
            )

    if run_model.status != new_status:
        logger.info(
            "%s: run status has changed %s -> %s",
            fmt(run_model),
            run_model.status.name,
            new_status.name,
        )
        run_model.status = new_status
        run_model.termination_reason = termination_reason


def group_jobs_by_replica_latest(jobs: List[JobModel]) -> Iterable[Tuple[int, List[JobModel]]]:
    """
    Args:
        jobs: unsorted list of jobs

    Yields:
        latest jobs in each replica (replica_num, jobs)
    """
    jobs = sorted(jobs, key=lambda j: (j.replica_num, j.job_num, j.submission_num))
    for replica_num, all_replica_jobs in itertools.groupby(jobs, key=lambda j: j.replica_num):
        replica_jobs: List[JobModel] = []
        for job_num, job_submissions in itertools.groupby(
            all_replica_jobs, key=lambda j: j.job_num
        ):
            # take only the latest submission
            # the latest `submission_num` doesn't have to be the same for all jobs
            *_, latest_job_submission = job_submissions
            replica_jobs.append(latest_job_submission)
        yield replica_num, replica_jobs


async def is_retry_enabled(
    session: AsyncSession, job: JobModel, retry_policy: ProfileRetryPolicy
) -> bool:
    # retry for spot instances only
    if retry_policy.retry and job.termination_reason in JOB_TERMINATION_REASONS_TO_RETRY:
        instance = await session.get(InstanceModel, job.used_instance_id)
        instance_offer = InstanceOffer.parse_raw(instance.offer)
        if instance_offer.instance.resources.spot:
            return True

    return False


async def is_retry_limit_exceeded(
    session: AsyncSession, job: JobModel, retry_policy: ProfileRetryPolicy
) -> bool:
    if retry_policy.limit is not None and get_current_datetime() - job.submitted_at.replace(
        tzinfo=datetime.timezone.utc
    ) > datetime.timedelta(seconds=retry_policy.limit):
        return True
    return False


def can_retry_single_job(run_spec: RunSpec) -> bool:
    # TODO(egor-s): handle independent and interconnected clusters
    return False


async def retry_replica_jobs(
    session: AsyncSession, run_model: RunModel, latest_jobs: List[JobModel], *, only_failed: bool
):
    for job_model in latest_jobs:
        if job_model.termination_reason not in JOB_TERMINATION_REASONS_TO_RETRY:
            if only_failed:
                # No need to resubmit, skip
                continue
            if not (job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING):
                # The job is not finished, but we have to retry all jobs. Terminate it
                job_model.status = JobStatus.TERMINATING
                job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER

        new_job_model = create_job_model_for_new_submission(
            run_model=run_model,
            job=Job(job_spec=JobSpec.parse_raw(job_model.job_spec_data), job_submissions=[]),
            status=JobStatus.SUBMITTED,
        )
        # dirty hack to avoid passing all job submissions
        new_job_model.submission_num = job_model.submission_num + 1
        session.add(new_job_model)
