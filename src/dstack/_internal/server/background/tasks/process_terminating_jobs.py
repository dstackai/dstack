import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs import (
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    job_model_to_job_submission,
    terminate_job_submission_instance,
)
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

TERMINATE_JOB_INTERVAL = datetime.timedelta(seconds=15)


async def process_terminating_jobs():
    async with get_session_ctx() as session:
        async with TERMINATING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status == JobStatus.TERMINATING,
                    JobModel.id.not_in(TERMINATING_PROCESSING_JOBS_IDS),
                    JobModel.last_processed_at < get_current_datetime() - TERMINATE_JOB_INTERVAL,
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)  # TODO(egor-s) process multiple at once
            )
            job_model = res.scalar()
            if job_model is None:
                return
            TERMINATING_PROCESSING_JOBS_IDS.add(job_model.id)
    try:
        await _process_job(job_id=job_model.id)
    finally:
        TERMINATING_PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id):
    async with get_session_ctx() as session:
        res = await session.execute(
            select(JobModel).where(JobModel.id == job_id).options(joinedload(JobModel.project))
        )
        job_model = res.scalar_one()
        job_submission = job_model_to_job_submission(job_model)
        await terminate_job_submission_instance(
            project=job_model.project,
            job_submission=job_submission,
        )
        job_model.status = JobStatus.TERMINATED
        job_model.last_processed_at = get_current_datetime()
        logger.debug("Job %s is terminated", job_model.job_name)
        await session.commit()
