from datetime import timedelta

from sqlalchemy import delete

from dstack._internal.server import settings
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import EventModel
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime


@sentry_utils.instrument_background_task
async def delete_events():
    cutoff = get_current_datetime() - timedelta(seconds=settings.SERVER_EVENTS_TTL_SECONDS)
    stmt = delete(EventModel).where(EventModel.recorded_at < cutoff)
    async with get_session_ctx() as session:
        await session.execute(stmt)
