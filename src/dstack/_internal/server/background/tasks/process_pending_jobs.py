from datetime import timedelta

from sqlalchemy import update

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import JobModel
from dstack._internal.utils import common as common_utils

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)


async def process_pending_jobs():
    async with get_session_ctx() as session:
        now = common_utils.get_current_datetime()
        await session.execute(
            update(JobModel)
            .where(
                JobModel.status.in_([JobStatus.PENDING]),
                JobModel.last_processed_at < now - PENDING_JOB_RETRY_INTERVAL,
            )
            .values(status=JobStatus.SUBMITTED)
        )
