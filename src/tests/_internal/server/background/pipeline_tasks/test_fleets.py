import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.fleets import (
    FleetNodesSpec,
    FleetStatus,
    InstanceGroupPlacement,
)
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.runs import RunStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.background.pipeline_tasks import fleets as fleets_pipeline
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
    get_fleet_configuration,
    get_fleet_spec,
    get_job_provisioning_data,
    get_ssh_fleet_configuration,
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


async def _lock_fleet_for_processing(session: AsyncSession, fleet: FleetModel) -> None:
    fleet.lock_token = uuid.uuid4()
    fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
    await session.commit()


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
    async def test_skips_instance_locking_for_ssh_fleet(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(conf=get_ssh_fleet_configuration()),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        original_last_processed_at = fleet.last_processed_at
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        instance.lock_token = uuid.uuid4()
        instance.lock_expires_at = datetime(2025, 1, 2, 3, 5, tzinfo=timezone.utc)
        instance.lock_owner = "OtherPipeline"
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(instance)
        assert not fleet.deleted
        assert fleet.lock_owner is None
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        assert fleet.last_processed_at > original_last_processed_at
        assert instance.lock_owner == "OtherPipeline"

    async def test_skips_instance_locking_when_fleet_is_not_ready_for_consolidation(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=spec,
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        original_last_processed_at = fleet.last_processed_at
        original_last_consolidated_at = datetime.now(timezone.utc)
        fleet.consolidation_attempt = 1
        fleet.last_consolidated_at = original_last_consolidated_at
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        instance.lock_token = uuid.uuid4()
        instance.lock_expires_at = datetime(2025, 1, 2, 3, 5, tzinfo=timezone.utc)
        instance.lock_owner = "OtherPipeline"
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(instance)
        assert not fleet.deleted
        assert fleet.consolidation_attempt == 1
        assert fleet.last_consolidated_at == original_last_consolidated_at
        assert fleet.lock_owner is None
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        assert fleet.last_processed_at > original_last_processed_at
        assert instance.lock_owner == "OtherPipeline"

    async def test_resets_fleet_lock_when_not_all_instances_can_be_locked(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        spec = get_fleet_spec()
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
        locked_elsewhere = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=1,
        )
        original_last_processed_at = fleet.last_processed_at
        fleet.lock_token = uuid.uuid4()
        fleet.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        fleet.lock_owner = FleetPipeline.__name__
        locked_elsewhere.lock_token = uuid.uuid4()
        locked_elsewhere.lock_expires_at = datetime(2025, 1, 2, 3, 5, tzinfo=timezone.utc)
        locked_elsewhere.lock_owner = "OtherPipeline"
        await session.commit()

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(locked_elsewhere)
        assert fleet.lock_owner == FleetPipeline.__name__
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        assert fleet.last_processed_at > original_last_processed_at
        assert locked_elsewhere.lock_owner == "OtherPipeline"

    async def test_unlocks_instances_after_consolidation(
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
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=0,
        )
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(instance)
        assert instance.lock_owner is None
        assert instance.lock_token is None
        assert instance.lock_expires_at is None

    async def test_unlocks_instances_when_fleet_lock_token_changes_after_processing(
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
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            instance_num=0,
        )
        await _lock_fleet_for_processing(session, fleet)

        async def mock_process_fleet(*args, **kwargs):
            fleet_model = args[0]
            fleet_model.lock_token = uuid.uuid4()
            return fleets_pipeline._ProcessResult()

        with patch.object(
            fleets_pipeline,
            "_process_fleet",
            AsyncMock(side_effect=mock_process_fleet),
        ):
            await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(instance)
        assert instance.lock_owner is None
        assert instance.lock_token is None
        assert instance.lock_expires_at is None

    async def test_syncs_initial_current_master_for_cluster_fleet(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=2, target=2, max=2),
                )
            ),
        )
        first_instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=1,
        )
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.current_master_instance_id == first_instance.id

    async def test_keeps_current_master_when_it_is_still_active(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=2, target=2, max=2),
                )
            ),
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        current_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PROVISIONING,
            job_provisioning_data=get_job_provisioning_data(),
            instance_num=1,
        )
        fleet.current_master_instance_id = current_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.current_master_instance_id == current_master.id

    async def test_promotes_provisioned_survivor_when_current_master_terminated(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=2),
                )
            ),
        )
        terminated_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        provisioned_survivor = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            job_provisioning_data=get_job_provisioning_data(),
            instance_num=1,
        )
        fleet.current_master_instance_id = terminated_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(terminated_master)
        assert terminated_master.deleted
        assert fleet.current_master_instance_id == provisioned_survivor.id

    async def test_promotes_next_bootstrap_candidate_when_current_master_terminated(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=2),
                )
            ),
        )
        terminated_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        next_candidate = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=1,
        )
        fleet.current_master_instance_id = terminated_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.current_master_instance_id == next_candidate.id

    async def test_does_not_elect_terminating_bootstrap_candidate_as_master(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=3),
                )
            ),
        )
        terminated_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATING,
            job_provisioning_data=None,
            offer=None,
            instance_num=1,
        )
        pending_candidate = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=2,
        )
        fleet.current_master_instance_id = terminated_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.current_master_instance_id == pending_candidate.id

    async def test_clears_current_master_for_non_cluster_fleet(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        fleet.current_master_instance_id = instance.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        assert fleet.current_master_instance_id is None

    async def test_syncs_current_master_after_creating_missing_instances(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=2, target=2, max=2),
                )
            ),
        )
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        instances = (
            (
                await session.execute(
                    select(InstanceModel)
                    .where(InstanceModel.fleet_id == fleet.id, InstanceModel.deleted == False)
                    .order_by(InstanceModel.instance_num, InstanceModel.created_at)
                )
            )
            .scalars()
            .all()
        )
        assert len(instances) == 2
        assert fleet.current_master_instance_id == instances[0].id

    async def test_prefers_surviving_instance_over_new_replacement_for_master_election(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=2, target=2, max=2),
                )
            ),
        )
        terminated_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        surviving_instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=1,
        )
        fleet.current_master_instance_id = terminated_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(terminated_master)
        await session.refresh(surviving_instance)
        non_deleted_instances = (
            (
                await session.execute(
                    select(InstanceModel)
                    .where(InstanceModel.fleet_id == fleet.id, InstanceModel.deleted == False)
                    .order_by(InstanceModel.instance_num, InstanceModel.created_at)
                )
            )
            .scalars()
            .all()
        )

        assert terminated_master.deleted
        assert fleet.current_master_instance_id == surviving_instance.id
        assert len(non_deleted_instances) == 2
        assert any(
            instance.id != surviving_instance.id and instance.instance_num == 0
            for instance in non_deleted_instances
        )

    async def test_min_zero_failed_master_terminates_unprovisioned_siblings(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=0, target=3, max=3),
                )
            ),
        )
        failed_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        failed_master.termination_reason = InstanceTerminationReason.NO_OFFERS
        sibling1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=1,
        )
        sibling2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=2,
        )
        fleet.current_master_instance_id = failed_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(failed_master)
        await session.refresh(sibling1)
        await session.refresh(sibling2)
        assert failed_master.deleted
        assert sibling1.status == InstanceStatus.TERMINATED
        assert sibling2.status == InstanceStatus.TERMINATED
        assert sibling1.termination_reason == InstanceTerminationReason.MASTER_FAILED
        assert sibling2.termination_reason == InstanceTerminationReason.MASTER_FAILED
        assert fleet.current_master_instance_id is None

    async def test_min_zero_failed_master_preserves_provisioned_survivor(
        self, test_db, session: AsyncSession, worker: FleetWorker
    ):
        project = await create_project(session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=0, target=2, max=2),
                )
            ),
        )
        failed_master = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATED,
            job_provisioning_data=None,
            offer=None,
            instance_num=0,
        )
        failed_master.termination_reason = InstanceTerminationReason.NO_OFFERS
        provisioned_survivor = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            job_provisioning_data=get_job_provisioning_data(),
            instance_num=1,
        )
        pending_sibling = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            job_provisioning_data=None,
            offer=None,
            instance_num=2,
        )
        fleet.current_master_instance_id = failed_master.id
        await _lock_fleet_for_processing(session, fleet)

        await worker.process(_fleet_to_pipeline_item(fleet))

        await session.refresh(fleet)
        await session.refresh(provisioned_survivor)
        await session.refresh(pending_sibling)
        assert provisioned_survivor.status == InstanceStatus.IDLE
        assert pending_sibling.status == InstanceStatus.PENDING
        assert pending_sibling.termination_reason is None
        assert fleet.current_master_instance_id == provisioned_survivor.id

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
