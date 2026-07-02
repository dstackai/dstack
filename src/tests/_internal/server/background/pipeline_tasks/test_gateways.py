import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.core.errors import BackendNotAvailable
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import (
    GatewayConfiguration,
    GatewayReplicaStatus,
    GatewayStatus,
)
from dstack._internal.server.background.pipeline_tasks.gateways import (
    GatewayFetcher,
    GatewayPipeline,
    GatewayPipelineItem,
    GatewayWorker,
)
from dstack._internal.server.models import GatewayModel
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
    get_gateway_compute_configuration,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> GatewayWorker:
    return GatewayWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.fixture
def fetcher() -> GatewayFetcher:
    return GatewayFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _gateway_to_pipeline_item(gateway_model: GatewayModel) -> GatewayPipelineItem:
    assert gateway_model.lock_token is not None
    assert gateway_model.lock_expires_at is not None
    return GatewayPipelineItem(
        __tablename__=gateway_model.__tablename__,
        id=gateway_model.id,
        lock_token=gateway_model.lock_token,
        lock_expires_at=gateway_model.lock_expires_at,
        prev_lock_expired=False,
        status=gateway_model.status,
        to_be_deleted=gateway_model.to_be_deleted,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayFetcher:
    async def test_fetch_selects_eligible_gateways_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: GatewayFetcher
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        submitted = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="submitted",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=stale - timedelta(seconds=3),
        )
        provisioning = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="provisioning",
            status=GatewayStatus.PROVISIONING,
            last_processed_at=stale - timedelta(seconds=2),
        )
        to_be_deleted = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="to-be-deleted",
            status=GatewayStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=1),
        )
        to_be_deleted.to_be_deleted = True

        just_created = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="just-created",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=now,
        )
        just_created.created_at = now
        just_created.last_processed_at = now

        ineligible_status = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="ineligible-status",
            status=GatewayStatus.RUNNING,
            last_processed_at=stale,
        )
        recent = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="recent",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=now,
        )
        recent.created_at = now - timedelta(minutes=2)
        recent.last_processed_at = now

        locked = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="locked",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=stale + timedelta(seconds=1),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            submitted.id,
            provisioning.id,
            to_be_deleted.id,
            just_created.id,
        }
        assert {(item.id, item.status, item.to_be_deleted) for item in items} == {
            (submitted.id, GatewayStatus.SUBMITTED, False),
            (provisioning.id, GatewayStatus.PROVISIONING, False),
            (to_be_deleted.id, GatewayStatus.RUNNING, True),
            (just_created.id, GatewayStatus.SUBMITTED, False),
        }

        for gateway in [
            submitted,
            provisioning,
            to_be_deleted,
            just_created,
            ineligible_status,
            recent,
            locked,
        ]:
            await session.refresh(gateway)

        fetched_gateways = [submitted, provisioning, to_be_deleted, just_created]
        assert all(gateway.lock_owner == GatewayPipeline.__name__ for gateway in fetched_gateways)
        assert all(gateway.lock_expires_at is not None for gateway in fetched_gateways)
        assert all(gateway.lock_token is not None for gateway in fetched_gateways)
        assert len({gateway.lock_token for gateway in fetched_gateways}) == 1

        assert ineligible_status.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_gateways_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: GatewayFetcher
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        now = get_current_datetime()

        oldest = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="oldest",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="middle",
            status=GatewayStatus.PROVISIONING,
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="newest",
            status=GatewayStatus.SUBMITTED,
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == GatewayPipeline.__name__
        assert middle.lock_owner == GatewayPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerSubmitted:
    async def test_submitted_to_provisioning(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.SUBMITTED,
        )
        config = GatewayConfiguration(
            name=gateway.name,
            backend=BackendType.AWS,
            region=gateway.region,
            replicas=2,
        )
        gateway.configuration = config.json()
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_with_model_by_type_or_error"
        ) as m:
            m.return_value = (backend, Mock())
            await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        res = await session.execute(
            select(GatewayModel)
            .where(GatewayModel.id == gateway.id)
            .options(selectinload(GatewayModel.gateway_computes))
        )
        gateway = res.unique().scalar_one()
        assert gateway.status == GatewayStatus.PROVISIONING
        computes = sorted(gateway.gateway_computes, key=lambda c: c.replica_num)
        assert len(computes) == 2
        assert computes[0].status == GatewayReplicaStatus.SUBMITTED
        assert computes[0].replica_num == 0
        assert computes[1].status == GatewayReplicaStatus.SUBMITTED
        assert computes[1].replica_num == 1
        assert all(c.ip_address is None for c in computes)

    async def test_marks_gateway_as_failed_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.SUBMITTED,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_with_model_by_type_or_error"
        ) as m:
            m.side_effect = BackendNotAvailable()
            await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.FAILED
        assert gateway.status_message == "Backend not available"
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Gateway status changed SUBMITTED -> FAILED (Backend not available)"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerProvisioning:
    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_provisioning_to_running(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayWorker,
        legacy_compute: bool,
        populate_configuration: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            populate_configuration=populate_configuration,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.RUNNING,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_compute_id = gateway_compute.id
        else:
            await create_gateway_compute(
                session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                populate_configuration=populate_configuration,
            )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed PROVISIONING -> RUNNING"

    async def test_provisioning_to_running_with_multiple_replicas(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="1.1.1.1",
            status=GatewayReplicaStatus.RUNNING,
            replica_num=0,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="2.2.2.2",
            status=GatewayReplicaStatus.RUNNING,
            replica_num=1,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed PROVISIONING -> RUNNING"

    async def test_still_provisioning_if_not_all_replicas_running(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="1.1.1.1",
            status=GatewayReplicaStatus.RUNNING,
            replica_num=0,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="2.2.2.2",
            status=GatewayReplicaStatus.PROVISIONING,
            replica_num=1,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        original_last_processed_at = gateway.last_processed_at
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.PROVISIONING
        assert gateway.last_processed_at > original_last_processed_at
        events = await list_events(session)
        assert len(events) == 0

    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize(
        "replica_status", [GatewayReplicaStatus.TERMINATING, GatewayReplicaStatus.TERMINATED]
    )
    async def test_marks_gateway_as_failed_if_replica_failed(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayWorker,
        legacy_compute: bool,
        replica_status: GatewayReplicaStatus,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=replica_status,
                active=False,
            )
            gateway.gateway_compute_id = gateway_compute.id
        else:
            await create_gateway_compute(
                session,
                gateway_id=gateway.id,
                status=replica_status,
                active=False,
            )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.FAILED
        assert gateway.status_message == "Failed to provision gateway replica"
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Gateway status changed PROVISIONING -> FAILED (Failed to provision gateway replica)"
        )

    async def test_still_provisioning_with_submitted_replica(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        original_last_processed_at = gateway.last_processed_at
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.PROVISIONING
        assert gateway.last_processed_at > original_last_processed_at
        events = await list_events(session)
        assert len(events) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerDeleted:
    async def test_deletes_gateway_with_no_computes(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.to_be_deleted = True
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        res = await session.execute(select(GatewayModel.id).where(GatewayModel.id == gateway.id))
        assert res.scalar_one_or_none() is None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway deleted"

    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_deletes_gateway_when_all_replicas_terminated(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayWorker,
        legacy_compute: bool,
        populate_configuration: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            populate_configuration=populate_configuration,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATED,
                active=False,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_compute_id = gateway_compute.id
        else:
            await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.TERMINATED,
                active=False,
                populate_configuration=populate_configuration,
            )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.to_be_deleted = True
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        res = await session.execute(select(GatewayModel.id).where(GatewayModel.id == gateway.id))
        assert res.scalar_one_or_none() is None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway deleted"

    @pytest.mark.parametrize(
        "replica_status",
        [
            GatewayReplicaStatus.SUBMITTED,
            GatewayReplicaStatus.PROVISIONING,
            GatewayReplicaStatus.RUNNING,
            GatewayReplicaStatus.TERMINATING,
        ],
    )
    async def test_waits_when_replicas_not_yet_terminated(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayWorker,
        replica_status: GatewayReplicaStatus,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
            status=replica_status,
            active=False,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.lock_owner = "GatewayPipeline"
        gateway.to_be_deleted = True
        original_last_processed_at = gateway.last_processed_at
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        res = await session.execute(select(GatewayModel.id).where(GatewayModel.id == gateway.id))
        assert res.scalar_one_or_none() is not None
        await session.refresh(gateway)
        assert gateway.to_be_deleted is True
        assert gateway.last_processed_at > original_last_processed_at
        assert gateway.lock_token is None
        assert gateway.lock_expires_at is None
        assert gateway.lock_owner is None
        events = await list_events(session)
        assert len(events) == 0

    async def test_deletes_gateway_with_multiple_replicas_all_terminated(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
            ip_address="1.1.1.1",
            status=GatewayReplicaStatus.TERMINATED,
            active=False,
            replica_num=0,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
            ip_address="2.2.2.2",
            status=GatewayReplicaStatus.TERMINATED,
            active=False,
            replica_num=1,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.to_be_deleted = True
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        res = await session.execute(select(GatewayModel.id).where(GatewayModel.id == gateway.id))
        assert res.scalar_one_or_none() is None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway deleted"
