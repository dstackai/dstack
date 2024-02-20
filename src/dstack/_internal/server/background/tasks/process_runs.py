import asyncio
import itertools
import uuid
from typing import Iterable, List, Tuple

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.jobs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_runs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK:
            res = await session.execute(
                sa.select(RunModel).where(
                    # TODO(egor-s): filter by processing_finished flag
                    # TODO(egor-s): filter by last_processed_at
                    RunModel.id.not_in(PROCESSING_RUNS_IDS),
                )
            )
            runs: List[RunModel] = res.scalars()
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

        # TODO(egor-s) update run.last_processed_at
        await session.commit()

    return run_id


async def process_pending_run(session: AsyncSession, run: RunModel):
    """Jobs are not created yet"""
    pass  # TODO(ego-s): do we need pending status?


async def process_active_run(session: AsyncSession, run: RunModel):
    """
    Run is submitted, starting, or running.
    We handle fails, scaling, and status changes.
    """

    # TODO(egor-s): consider using Counter instead of a copy-pasting
    any_replica_ok = False
    any_replica_submitted = False
    any_replica_starting = False
    any_replica_running = False

    # TODO(egor-s): collect replicas count and statuses for auto-scaling
    for replica_num, submission_num, jobs in group_jobs_by_replica_latest(run.jobs):
        any_job_failed = False
        any_job_terminated = False
        any_job_submitted = False
        any_job_starting = False
        any_job_running = False

        for job in jobs:
            if job.status == JobStatus.FAILED:
                any_job_failed = True
            elif job.status == JobStatus.TERMINATED:
                any_job_terminated = True
            elif job.status == JobStatus.SUBMITTED:
                any_job_submitted = True
            elif job.status in {JobStatus.PROVISIONING, JobStatus.PULLING}:
                any_job_starting = True
            elif job.status == JobStatus.RUNNING:
                any_job_running = True

        if not (any_job_failed or any_job_terminated):
            replica_ok = True
        else:
            replica_ok = False  # TODO(egor-s)
            # replica_ok = handle_cluster_node_failure()

        if replica_ok:
            any_replica_ok = True
            if any_job_running:
                any_replica_running = True
            elif any_job_starting:
                any_replica_starting = True
            elif any_job_submitted:
                any_replica_submitted = True
            else:
                pass  # replica is done

    if not any_replica_ok:
        # TODO(egor-s): handle scale-to-zero
        # TODO(egor-s): consider retry policy
        run.status = JobStatus.PENDING
    elif any_replica_running:
        run.status = JobStatus.RUNNING
    elif any_replica_starting:
        run.status = JobStatus.PROVISIONING
    elif any_replica_submitted:
        run.status = JobStatus.SUBMITTED
    else:
        # all replicas are ok and done
        run.status = JobStatus.DONE


async def process_finished_run(session: AsyncSession, run: RunModel):
    """Done, failed, or terminated. Stop all jobs, unregister the service"""
    for job in run.jobs:
        if not job.status.is_finished():
            job.status = JobStatus.TERMINATED
            # TODO(egor-s): set job.error_code
    # TODO(egor-s): unregister the service
    # TODO(egor-s): set run.processing_finished flag


def group_jobs_by_replica_latest(
    jobs: List[JobModel],
) -> Iterable[Tuple[int, int, List[JobModel]]]:
    """
    Args:
        jobs: unsorted list of jobs

    Yields:
        latest replicas (replica_num, submission_num, jobs)
    """
    jobs = sorted(
        jobs, key=lambda j: (1111, j.submission_num, j.job_num)
    )  # TODO(egor-s): use j.replica_num
    for replica_num, all_replica_jobs in itertools.groupby(
        jobs, key=lambda j: 1111
    ):  # TODO(egor-s): use j.replica_num
        # take only the latest submission
        # all_replica_jobs is not empty by design, but we need to initialize the variables
        submission_num, replica_jobs = -1, []
        for submission_num, replica_jobs_iter in itertools.groupby(
            all_replica_jobs, key=lambda j: j.submission_num
        ):
            replica_jobs = list(replica_jobs_iter)
        yield replica_num, submission_num, replica_jobs
