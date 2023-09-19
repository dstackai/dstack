import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx, session_decorator
from dstack._internal.server.models import JobModel

_PROCESSING_JOBS_LOCK = asyncio.Lock()
_PROCESSING_JOBS_IDS = set()


async def process_running_jobs():
    async with get_session_ctx() as session:
        async with _PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_([JobStatus.PROVISIONING, JobStatus.RUNNING]),
                    JobModel.id.not_in(_PROCESSING_JOBS_IDS),
                )
                .order_by(JobModel.last_processed_at.desc())
                .limit(1)  # TODO process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return

            _PROCESSING_JOBS_IDS.add(job_model.id)

    try:
        await _process_job(session=session, job_model=job_model)
    finally:
        async with _PROCESSING_JOBS_LOCK:
            _PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_model: JobModel):
    async with get_session_ctx() as session:
        if job_model.status == JobStatus.PROVISIONING:
            _process_provisioning_job(session=session, job_model=job_model)
        else:
            _process_running_job(session=session, job_model=job_model)


async def _process_provisioning_job(session: AsyncSession, job_model: JobModel):
    # Ping runner. Return if not available.
    # Submit job
    # Upload code
    # Run job
    # Update job status to RUNNING
    # call _process_running_job
    pass


async def _process_running_job(session: AsyncSession, job_model: JobModel):
    # Pull job logs and status updates until DONE/FAILED/TERMINATED
    # Update job
    # If retry is active, update job status to PENDING.
    pass
