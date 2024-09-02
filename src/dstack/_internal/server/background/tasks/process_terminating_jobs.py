from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs import (
    process_terminating_job,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_terminating_jobs():
    lock, lockset = get_locker().get_lockset(JobModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.id.not_in(lockset),
                    JobModel.status == JobStatus.TERMINATING,
                    or_(JobModel.remove_at.is_(None), JobModel.remove_at < get_current_datetime()),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job_model = res.scalar()
            if job_model is None:
                return
            lockset.add(job_model.id)
        try:
            job_model_id = job_model.id
            await _process_job(session=session, job_model=job_model)
        finally:
            lockset.difference_update([job_model_id])


async def _process_job(session: AsyncSession, job_model: JobModel):
    await process_terminating_job(session, job_model)
    job_model.last_processed_at = get_current_datetime()
    await session.commit()
