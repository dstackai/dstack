from datetime import timedelta

from pydantic import parse_raw_as
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import InstanceStatus, JobStatus
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceModel, JobModel
from dstack._internal.server.services.jobs import PROCESSING_POOL_IDS, PROCESSING_POOL_LOCK
from dstack._internal.utils.logging import get_logger

PENDING_JOB_RETRY_INTERVAL = timedelta(seconds=60)

logger = get_logger(__name__)


async def process_pools():

    async with get_session_ctx() as session:
        async with PROCESSING_POOL_LOCK:
            res = await session.scalars(
                select(InstanceModel).where(
                    InstanceModel.status.in_([InstanceStatus.READY, InstanceStatus.FAILED]),
                    InstanceModel.id.not_in(PROCESSING_POOL_IDS),
                )
            )
            instances = res.all()
            if not instances:
                return

            PROCESSING_POOL_IDS.update(i.id for i in instances)

    try:
        for inst in instances:
            await _terminate_instance(inst)
    finally:
        PROCESSING_POOL_IDS.difference_update(i.id for i in instances)


async def _terminate_instance(instance: InstanceModel):
    pass
