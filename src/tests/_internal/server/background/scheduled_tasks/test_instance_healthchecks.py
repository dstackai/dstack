from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.background.scheduled_tasks.instance_healthchecks import (
    delete_instance_healthchecks,
)
from dstack._internal.server.models import InstanceHealthCheckModel, InstanceStatus
from dstack._internal.server.testing.common import (
    create_instance,
    create_instance_health_check,
    create_project,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestDeleteInstanceHealthChecks:
    async def test_deletes_instance_health_checks(
        self, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.IDLE
        )
        # 30 minutes
        monkeypatch.setattr(
            "dstack._internal.server.settings.SERVER_INSTANCE_HEALTH_TTL_SECONDS", 1800
        )
        now = get_current_datetime()
        # old check
        await create_instance_health_check(
            session=session, instance=instance, collected_at=now - timedelta(minutes=40)
        )
        # recent check
        check = await create_instance_health_check(
            session=session, instance=instance, collected_at=now - timedelta(minutes=20)
        )

        await delete_instance_healthchecks()

        res = await session.execute(select(InstanceHealthCheckModel))
        all_checks = res.scalars().all()
        assert len(all_checks) == 1
        assert all_checks[0] == check
