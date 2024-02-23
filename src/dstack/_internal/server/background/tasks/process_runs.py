import asyncio
import datetime
import itertools
import uuid
from typing import Iterable, List, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.instances import InstanceOffer
from dstack._internal.core.models.profiles import ProfileRetryPolicy
from dstack._internal.core.models.runs import JobErrorCode, JobStatus, RunSpec
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
    run_model_to_run,
)
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
PROCESSING_INTERVAL = datetime.timedelta(seconds=5)
JOB_ERROR_CODES_TO_RETRY = {
    JobErrorCode.INTERRUPTED_BY_NO_CAPACITY,
    JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY,
}


async def process_runs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK:
            res = await session.execute(
                sa.select(RunModel).where(
                    RunModel.processing_finished == False,
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

        if run.status == JobStatus.PENDING:
            await process_pending_run(session, run)
        elif run.status in {JobStatus.SUBMITTED, JobStatus.PROVISIONING, JobStatus.RUNNING}:
            await process_active_run(session, run)
        elif run.status.is_finished():
            await process_finished_run(session, run)
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

    run_model.status = JobStatus.SUBMITTED
    logger.info("%s: run status has changed PENDING -> SUBMITTED", fmt(run_model))


async def process_active_run(session: AsyncSession, run_model: RunModel):
    """
    Run is submitted, starting, or running.
    We handle fails, scaling, and status changes.
    """
    run_spec = RunSpec.parse_raw(run_model.run_spec)
    retry_policy = run_spec.profile.retry_policy or ProfileRetryPolicy()

    any_replica_failed = False
    replicas_to_retry: List[Tuple[int, List[JobModel]]] = []
    any_replica_submitted = False
    any_replica_starting = False
    any_replica_running = False
    any_replica_done = False

    # TODO(egor-s): collect replicas count and statuses for auto-scaling
    for replica_num, jobs in group_jobs_by_replica_latest(run_model.jobs):
        any_job_failed = False
        any_job_failed_retryable = False
        any_job_submitted = False
        any_job_starting = False
        any_job_running = False
        all_jobs_terminated = True
        all_jobs_done = True

        for job in jobs:
            if job.status == JobStatus.FAILED:
                if not await is_job_retryable(
                    session, job, retry_policy
                ):  # critical, can't recover
                    any_job_failed = True
                    break
                any_job_failed_retryable = True
            elif job.status == JobStatus.SUBMITTED:
                any_job_submitted = True
            elif job.status in {JobStatus.PROVISIONING, JobStatus.PULLING}:
                any_job_starting = True
            elif job.status == JobStatus.RUNNING:
                any_job_running = True

            if job.status != JobStatus.DONE:
                all_jobs_done = False
            if job.status != JobStatus.TERMINATED:
                all_jobs_terminated = False

        if any_job_failed:  # critical, can't recover
            any_replica_failed = True
            break
        if any_job_failed_retryable:
            replicas_to_retry.append((replica_num, jobs))
        elif all_jobs_terminated:
            pass  # the replica was scaled down, ignore it
        else:
            any_replica_submitted = any_replica_submitted or any_job_submitted
            any_replica_starting = any_replica_starting or any_job_starting
            any_replica_running = any_replica_running or any_job_running
            any_replica_done = any_replica_done or all_jobs_done

    if any_replica_failed:
        new_status = JobStatus.FAILED
    elif not (any_replica_submitted or any_replica_starting or any_replica_running):
        if any_replica_done:
            new_status = JobStatus.DONE
        else:
            new_status = JobStatus.PENDING
    else:
        # TODO(egor-s): retry failed replicas while other replicas are active, terminate jobs if needed
        # TODO(egor-s): perform auto-scaling
        if any_replica_running:
            new_status = JobStatus.RUNNING
        elif any_replica_starting:
            new_status = JobStatus.PROVISIONING
        elif any_replica_submitted:
            new_status = JobStatus.SUBMITTED
        else:
            raise ValueError("Unexpected state")

    if run_model.status != new_status:
        logger.info(
            "%s: run status has changed %s -> %s",
            fmt(run_model),
            run_model.status.name,
            new_status.name,
        )
        run_model.status = new_status


async def process_finished_run(session: AsyncSession, run: RunModel):
    """Done, failed, or terminated. Stop all jobs, unregister the service"""
    for job in run.jobs:
        if not job.status.is_finished():
            logger.info("%s is %s: terminating job %s", fmt(run), run.status.name, job.job_name)
            job.status = JobStatus.TERMINATED
            # TODO(egor-s): set job.error_code
    # TODO(egor-s): unregister the service
    run.processing_finished = True


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


def fmt(run: RunModel) -> str:
    """Format a run for logging"""
    return f"({run.id.hex[:6]}){run.run_name}"


async def is_job_retryable(
    session: AsyncSession, job: JobModel, retry_policy: ProfileRetryPolicy
) -> bool:
    if not retry_policy.retry:
        return False
    if job.error_code not in JOB_ERROR_CODES_TO_RETRY:
        return False
    if (
        retry_policy.limit is not None
        and get_current_datetime() - job.submitted_at
        > datetime.timedelta(seconds=retry_policy.limit)
    ):
        return False

    # instance is not loaded by default, so we have to load it explicitly
    instance = await session.get(InstanceModel, job.used_instance_id)
    instance_offer = InstanceOffer.parse_raw(instance.offer)
    if not instance_offer.instance.resources.spot:
        return False
    return True
