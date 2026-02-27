import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.fleets import FleetNodesSpec, FleetStatus
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import RunStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.fleets import (
    FleetWorker,
)
from dstack._internal.server.models import FleetModel, InstanceModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_placement_group,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_fleet_spec,
)


@pytest.fixture
def worker() -> FleetWorker:
    return FleetWorker(queue=Mock(), heartbeater=Mock())


def _fleet_to_pipeline_item(fleet: FleetModel) -> PipelineItem:
    assert fleet.lock_token is not None
    assert fleet.lock_expires_at is not None
    return PipelineItem(
        __tablename__=fleet.__tablename__,
        id=fleet.id,
        lock_token=fleet.lock_token,
        lock_expires_at=fleet.lock_expires_at,
        prev_lock_expired=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestFleetWorker:
    async def test_deletes_empty_autocreated_fleet(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.autocreated = True
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.deleted

    async def test_deletes_terminating_user_fleet(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.autocreated = False
        fleet = await create_fleet(
            session=session,
            project=project,
            status=FleetStatus.TERMINATING,
        )

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.deleted

    async def test_does_not_delete_fleet_with_active_run(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
        )
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            status=RunStatus.RUNNING,
        )
        fleet.runs.append(run)

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert not fleet.deleted

    async def test_does_not_delete_fleet_with_instance(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
        )
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        fleet.instances.append(instance)

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert not fleet.deleted

    async def test_consolidation_creates_missing_instances(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.configuration.nodes = FleetNodesSpec(min=2, target=2, max=2)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=1,
        )

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        instances = (await session.execute(select(InstanceModel))).scalars().all()
        assert len(instances) == 2
        assert {i.instance_num for i in instances} == {0, 1}
        assert fleet.consolidation_attempt == 1

    async def test_consolidation_terminates_redundant_instances(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=1)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            instance_num=0,
        )
        instance2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=1,
        )
        instance3 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            instance_num=2,
        )

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(instance1)
        await session.refresh(instance2)
        await session.refresh(instance3)
        assert instance1.status == InstanceStatus.BUSY
        assert instance2.status == InstanceStatus.TERMINATING
        assert instance3.deleted
        assert fleet.consolidation_attempt == 1

    async def test_consolidation_attempt_increments_when_over_max_and_no_idle_instances(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=1)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            instance_num=0,
        )
        instance2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            instance_num=1,
        )

        fleet.consolidation_attempt = 2
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(instance1)
        await session.refresh(instance2)
        assert instance1.status == InstanceStatus.BUSY
        assert instance2.status == InstanceStatus.BUSY
        assert fleet.consolidation_attempt == 3

    async def test_marks_placement_groups_fleet_deleted_on_fleet_delete(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            status=FleetStatus.TERMINATING,
        )
        placement_group1 = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="test-pg-1",
        )
        placement_group2 = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="test-pg-2",
        )

        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(placement_group1)
        await session.refresh(placement_group2)
        assert fleet.deleted
        assert placement_group1.fleet_deleted
        assert placement_group2.fleet_deleted

    async def test_consolidation_respects_retry_delay(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.configuration.nodes = FleetNodesSpec(min=2, target=2, max=2)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=0,
        )
        fleet.consolidation_attempt = 1
        fleet.last_consolidated_at = datetime.now(timezone.utc)
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        instances = (
            (
                await session.execute(
                    select(InstanceModel).where(
                        InstanceModel.fleet_id == fleet.id,
                        InstanceModel.deleted == False,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(instances) == 1
        assert fleet.consolidation_attempt == 1
        assert not fleet.deleted

    async def test_consolidation_attempt_resets_when_no_changes(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=1)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=0,
        )
        fleet.consolidation_attempt = 3
        previous_last_consolidated_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        fleet.last_consolidated_at = previous_last_consolidated_at
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        instances = (
            (
                await session.execute(
                    select(InstanceModel).where(
                        InstanceModel.fleet_id == fleet.id,
                        InstanceModel.deleted == False,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(instances) == 1
        assert fleet.consolidation_attempt == 0
        assert fleet.last_consolidated_at is not None
        assert fleet.last_consolidated_at > previous_last_consolidated_at
