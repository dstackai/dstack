import asyncio
import uuid
from datetime import datetime, timedelta, timezone
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
    FleetFetcher,
    FleetPipeline,
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
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> FleetWorker:
    return FleetWorker(queue=Mock(), heartbeater=Mock())


@pytest.fixture
def fetcher() -> FleetFetcher:
    return FleetFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=60),
        lock_timeout=timedelta(seconds=20),
        heartbeater=Mock(),
    )


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
class TestFleetFetcher:
    async def test_fetch_selects_eligible_fleets_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: FleetFetcher
    ):
        project = await create_project(session)
        now = get_current_datetime()

        stale = await create_fleet(
            session=session,
            project=project,
            last_processed_at=now - timedelta(minutes=3),
        )
        just_created = await create_fleet(
            session=session,
            project=project,
            created_at=now,
            last_processed_at=now,
            name="just-created",
        )
        deleted = await create_fleet(
            session=session,
            project=project,
            deleted=True,
            name="deleted",
            last_processed_at=now - timedelta(minutes=2),
        )
        recent = await create_fleet(
            session=session,
            project=project,
            created_at=now - timedelta(minutes=2),
            last_processed_at=now,
            name="recent",
        )
        locked = await create_fleet(
            session=session,
            project=project,
            name="locked",
            last_processed_at=now - timedelta(minutes=1, seconds=1),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {stale.id, just_created.id}

        for fleet in [stale, just_created, deleted, recent, locked]:
            await session.refresh(fleet)

        assert stale.lock_owner == FleetPipeline.__name__
        assert just_created.lock_owner == FleetPipeline.__name__
        assert stale.lock_expires_at is not None
        assert just_created.lock_expires_at is not None
        assert stale.lock_token is not None
        assert just_created.lock_token is not None
        assert len({stale.lock_token, just_created.lock_token}) == 1

        assert deleted.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_fleets_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: FleetFetcher
    ):
        project = await create_project(session)
        now = get_current_datetime()

        oldest = await create_fleet(
            session=session,
            project=project,
            name="oldest",
            last_processed_at=now - timedelta(minutes=4),
        )
        middle = await create_fleet(
            session=session,
            project=project,
            name="middle",
            last_processed_at=now - timedelta(minutes=3),
        )
        newest = await create_fleet(
            session=session,
            project=project,
            name="newest",
            last_processed_at=now - timedelta(minutes=2),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == FleetPipeline.__name__
        assert middle.lock_owner == FleetPipeline.__name__
        assert newest.lock_owner is None


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
        last_consolidated_at = fleet.last_consolidated_at
        assert last_consolidated_at
        assert last_consolidated_at > previous_last_consolidated_at
