from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.background.tasks.process_placement_groups import (
    process_placement_groups,
)
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_placement_group,
    create_project,
)


class TestProcessPlacementGroups:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_placement_groups(self, test_db, session: AsyncSession):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
        )
        placement_group1 = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="test1-pg",
        )
        placement_group2 = await create_placement_group(
            session=session, project=project, fleet=fleet, name="test2-pg", fleet_deleted=True
        )
        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            aws_mock = Mock()
            m.return_value = aws_mock
            aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            await process_placement_groups()
            aws_mock.compute.return_value.delete_placement_group.assert_called_once()
        await session.refresh(placement_group1)
        await session.refresh(placement_group2)
        assert not placement_group1.deleted
        assert placement_group2.deleted
