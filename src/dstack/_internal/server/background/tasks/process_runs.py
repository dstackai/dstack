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
    JobStatus,
    JobTerminationReason,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel, RunModel
from dstack._internal.server.services.jobs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
)
from dstack._internal.server.services.runs import (
    create_job_model_for_new_submission,
    fmt,
    process_terminating_run,
    run_model_to_run,
)
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
PROCESSING_INTERVAL = datetime.timedelta(seconds=5)
JOB_ERROR_CODES_TO_RETRY = {
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
            runs: List[RunModel] = res.scalars().all()
            PROCESSING_RUNS_IDS.update(run.id for run in runs)

    futures = [
        process_single_run(run.id, [job.id for job in run.jobs if not job.removed]) for run in runs
    ]
    for future in asyncio.as_completed(futures):
        try:
            run_id = await future
            PROCESSING_RUNS_IDS.remove(run_id)  # unlock job processing as soon as possible
        except Exception as e:
            logger.error("Unexpected run processing error", exc_info=e)

    PROCESSING_RUNS_IDS.difference_update(
        run.id for run in runs
    )  # ensure that all runs are unlocked


async def process_single_run(run_id: uuid.UUID, job_ids: List[uuid.UUID]) -> uuid.UUID:
    jobs_ids_set = set(job_ids)
    while True:  # let job processing complete
        async with RUNNING_PROCESSING_JOBS_LOCK:
            if not RUNNING_PROCESSING_JOBS_IDS & jobs_ids_set:
                break
            await asyncio.sleep(0.1)

    async with get_session_ctx() as session:
        run = await session.get(RunModel, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        if run.status == RunStatus.PENDING:
            await process_pending_run(session, run)
        elif run.status in {RunStatus.SUBMITTED, RunStatus.STARTING, RunStatus.RUNNING}:
            await process_active_run(session, run)
        elif run.status == RunStatus.TERMINATING:
            await process_terminating_run(session, run)
        elif run.status.is_finished():
            pass
        else:
            raise ValueError(f"Unexpected run status {run.status}")

        run.last_processed_at = get_current_datetime()
        await session.commit()

    return run_id


async def process_pending_run(session: AsyncSession, run_model: RunModel):
    """Jobs are not created yet"""

    # TODO(egor-s): consider retry delay
    # TODO(egor-s): respect min_replicas and auto-scaling

    await session.execute(
        sa.select(RunModel)
        .where(RunModel.id == run_model.id)
        .execution_options(populate_existing=True)
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
    )
    run = run_model_to_run(run_model)

    for replica_num, job_models in group_jobs_by_replica_latest(run_model.jobs):
        for job_model in job_models:
            new_job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=run.jobs[job_model.job_num],
                status=JobStatus.SUBMITTED,
            )
            session.add(new_job_model)
        break  # TODO(egor-s): add replicas support

    run_model.status = RunStatus.SUBMITTED
    logger.info("%s: run status has changed PENDING -> SUBMITTED", fmt(run_model))


async def process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, starting, or running.
    We handle fails, scaling, and status changes.
    """
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    retry_policy = run_spec.profile.retry_policy or ProfileRetryPolicy()

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
                # the job is starting
                replica_statuses.add(RunStatus.STARTING)
            elif job.status == JobStatus.SUBMITTED:
                # the job is submitted
                replica_statuses.add(RunStatus.SUBMITTED)
            elif (
                job.status == JobStatus.FAILED
            ):  # TODO(egor-s): or terminating with specific statuses
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
            if not replica_needs_retry or can_retry_single_job(run_spec):
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
    elif RunStatus.STARTING in run_statuses:
        new_status = RunStatus.STARTING
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
        pass  # TODO(egor-s): retry replicas

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
    if retry_policy.retry and job.termination_reason in JOB_ERROR_CODES_TO_RETRY:
        instance = await session.get(InstanceModel, job.used_instance_id)
        instance_offer = InstanceOffer.parse_raw(instance.offer)
        if instance_offer.instance.resources.spot:
            return True

    return False


async def is_retry_limit_exceeded(
    session: AsyncSession, job: JobModel, retry_policy: ProfileRetryPolicy
) -> bool:
    if (
        retry_policy.limit is not None
        and get_current_datetime() - job.submitted_at
        > datetime.timedelta(seconds=retry_policy.limit)
    ):
        return True
    return False


def can_retry_single_job(run_spec: RunSpec) -> bool:
    # TODO(egor-s): handle independent and interconnected clusters
    return False
