from datetime import timedelta

from sqlalchemy import delete

from dstack._internal.server import settings
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import InstanceHealthCheckModel
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime


@sentry_utils.instrument_scheduled_task
async def delete_instance_healthchecks():
    now = get_current_datetime()
    cutoff = now - timedelta(seconds=settings.SERVER_INSTANCE_HEALTH_TTL_SECONDS)
    async with get_session_ctx() as session:
        await session.execute(
            delete(InstanceHealthCheckModel).where(InstanceHealthCheckModel.collected_at < cutoff)
        )
        await session.commit()
