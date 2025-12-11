from datetime import datetime
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_events import delete_events
from dstack._internal.server.models import EventModel
from dstack._internal.server.services import events
from dstack._internal.server.testing.common import create_user


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_deletes_old_events(test_db, session: AsyncSession) -> None:
    user = await create_user(session=session)
    for i in range(10):
        with freeze_time(datetime(2026, 1, 1, i)):
            events.emit(
                session,
                message=f"Event {i}",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(user)],
            )
    await session.commit()

    res = await session.execute(select(EventModel))
    all_events = res.scalars().all()
    assert len(all_events) == 10

    with (
        patch.multiple(settings, SERVER_EVENTS_TTL_SECONDS=5 * 3600),
        freeze_time(datetime(2026, 1, 1, 10)),
    ):
        await delete_events()

    res = await session.execute(select(EventModel).order_by(EventModel.recorded_at))
    remaining_events = res.scalars().all()
    assert len(remaining_events) == 5
    assert [e.message for e in remaining_events] == [
        "Event 5",
        "Event 6",
        "Event 7",
        "Event 8",
        "Event 9",
    ]
