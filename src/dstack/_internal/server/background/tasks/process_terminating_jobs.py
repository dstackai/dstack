import uuid

from sqlalchemy import or_, select

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs import (
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    process_terminating_job,
)
from dstack._internal.server.services.runs import PROCESSING_RUNS_IDS, PROCESSING_RUNS_LOCK
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_terminating_jobs():
    async with get_session_ctx() as session:
        async with PROCESSING_RUNS_LOCK, TERMINATING_PROCESSING_JOBS_LOCK:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.id.not_in(TERMINATING_PROCESSING_JOBS_IDS),
                    JobModel.status == JobStatus.TERMINATING,
                    JobModel.run_id.not_in(PROCESSING_RUNS_IDS),
                    or_(JobModel.remove_at.is_(None), JobModel.remove_at < get_current_datetime()),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)
            )
            job_model = res.scalar()
            if job_model is None:
                return
            TERMINATING_PROCESSING_JOBS_IDS.add(job_model.id)
    try:
        await _process_job(job_id=job_model.id)
    finally:
        TERMINATING_PROCESSING_JOBS_IDS.remove(job_model.id)


async def _process_job(job_id: uuid.UUID):
    async with get_session_ctx() as session:
        res = await session.execute(select(JobModel).where(JobModel.id == job_id))
        job_model = res.scalar_one()
        await process_terminating_job(session, job_model)
        job_model.last_processed_at = get_current_datetime()
        await session.commit()
