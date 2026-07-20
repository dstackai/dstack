import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.core.models.gateways import (
    GatewayReplicaStatus,
    GatewayStatus,
)
from dstack._internal.server.background.pipeline_tasks.gateways import (
    _MAX_REPLICA_SCALE_ATTEMPTS,
    GatewayFetcher,
    GatewayPipeline,
    GatewayPipelineItem,
    GatewayWorker,
)
from dstack._internal.server.models import GatewayComputeModel, GatewayModel
from dstack._internal.server.services.gateways import get_gateway_compute_models
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


async def _fetch_all_gateway_computes(
    session: AsyncSession, gateway_id: uuid.UUID
) -> list[GatewayComputeModel]:
    res = await session.execute(
        select(GatewayModel)
        .where(GatewayModel.id == gateway_id)
        .options(selectinload(GatewayModel.gateway_computes))
        .options(selectinload(GatewayModel.gateway_compute))
    )
    gateway = res.unique().scalar_one()
    return get_gateway_compute_models(gateway)


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

        running_with_missing_replica = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="running-with-missing-replica",
            status=GatewayStatus.RUNNING,
            last_processed_at=stale - timedelta(seconds=4),
        )

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

        failed = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="failed",
            status=GatewayStatus.FAILED,
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
            running_with_missing_replica.id,
            just_created.id,
        }
        assert {(item.id, item.status, item.to_be_deleted) for item in items} == {
            (submitted.id, GatewayStatus.SUBMITTED, False),
            (provisioning.id, GatewayStatus.PROVISIONING, False),
            (to_be_deleted.id, GatewayStatus.RUNNING, True),
            (running_with_missing_replica.id, GatewayStatus.RUNNING, False),
            (just_created.id, GatewayStatus.SUBMITTED, False),
        }

        for gateway in [
            submitted,
            provisioning,
            to_be_deleted,
            running_with_missing_replica,
            just_created,
            failed,
            recent,
            locked,
        ]:
            await session.refresh(gateway)

        fetched_gateways = [
            submitted,
            provisioning,
            to_be_deleted,
            running_with_missing_replica,
            just_created,
        ]
        assert all(gateway.lock_owner == GatewayPipeline.__name__ for gateway in fetched_gateways)
        assert all(gateway.lock_expires_at is not None for gateway in fetched_gateways)
        assert all(gateway.lock_token is not None for gateway in fetched_gateways)
        assert len({gateway.lock_token for gateway in fetched_gateways}) == 1

        assert failed.lock_owner is None
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

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_fetch_excludes_running_gateway_when_replica_count_matches(
        self, test_db, session: AsyncSession, fetcher: GatewayFetcher, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        stale = get_current_datetime() - timedelta(minutes=1)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
            last_processed_at=stale,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.RUNNING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert items == []

    async def test_fetch_includes_running_gateway_with_pending_scale_attempt_even_if_count_matches(
        self, test_db, session: AsyncSession, fetcher: GatewayFetcher
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        stale = get_current_datetime() - timedelta(minutes=1)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
            last_processed_at=stale,
        )
        await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        gateway.replica_scale_attempt = 1
        await session.commit()

        items = await fetcher.fetch(limit=10)
        assert {item.id for item in items} == {gateway.id}

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_fetch_includes_running_gateway_when_replica_count_not_matches(
        self, test_db, session: AsyncSession, fetcher: GatewayFetcher, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        stale = get_current_datetime() - timedelta(minutes=1)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
            last_processed_at=stale,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.RUNNING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)
        assert {item.id for item in items} == {gateway.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerSubmitted:
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_submitted_to_provisioning(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayWorker,
        populate_configuration: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.SUBMITTED,
            replicas=2,
            populate_configuration=populate_configuration,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.PROVISIONING
        computes = sorted(
            await _fetch_all_gateway_computes(session, gateway.id), key=lambda c: c.replica_num
        )
        assert len(computes) == 2
        assert computes[0].status == GatewayReplicaStatus.SUBMITTED
        assert computes[0].replica_num == 0
        assert computes[1].status == GatewayReplicaStatus.SUBMITTED
        assert computes[1].replica_num == 1
        assert all(c.ip_address is None for c in computes)


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
            replicas=2,
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
            replicas=2,
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

    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_still_provisioning_when_scale_out_adds_new_replicas(
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
            replicas=2,
            populate_configuration=populate_configuration,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                ip_address="1.1.1.1",
                status=GatewayReplicaStatus.RUNNING,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_compute_id = gateway_compute.id
        else:
            await create_gateway_compute(
                session,
                gateway_id=gateway.id,
                ip_address="1.1.1.1",
                status=GatewayReplicaStatus.RUNNING,
                replica_num=0,
                populate_configuration=populate_configuration,
            )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.PROVISIONING
        computes = sorted(
            await _fetch_all_gateway_computes(session, gateway.id), key=lambda c: c.replica_num
        )
        assert [c.replica_num for c in computes] == [0, 1]
        assert computes[1].status == GatewayReplicaStatus.SUBMITTED
        assert gateway.replica_scale_attempt == 1
        assert gateway.last_replica_scale_attempt_at is not None
        events = await list_events(session)
        assert len(events) == 0

    async def test_provisioning_to_running_when_scale_in_removes_surplus_replicas(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            replicas=1,
        )
        older = await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="1.1.1.1",
            status=GatewayReplicaStatus.PROVISIONING,
            replica_num=0,
        )
        older.created_at = datetime(2025, 1, 1)
        newer = await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="2.2.2.2",
            status=GatewayReplicaStatus.RUNNING,
            replica_num=1,
        )
        newer.created_at = datetime(2025, 1, 2)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        await session.refresh(older)
        await session.refresh(newer)
        assert older.scale_in is True
        assert newer.scale_in is False
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed PROVISIONING -> RUNNING"

    async def test_ignores_previously_scaled_in_replica_when_determining_status(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            replicas=1,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="1.1.1.1",
            status=GatewayReplicaStatus.RUNNING,
            replica_num=0,
        )
        scaled_in_compute = await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address="2.2.2.2",
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
            replica_num=1,
        )
        scaled_in_compute.scale_in = True
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed PROVISIONING -> RUNNING"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerRunning:
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_no_scaling_when_replica_count_matches(
        self, test_db, session: AsyncSession, worker: GatewayWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.RUNNING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            await create_gateway_compute(
                session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                replica_num=0,
            )
        gateway.replica_scale_attempt = 3
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        original_last_processed_at = gateway.last_processed_at
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        assert gateway.last_processed_at > original_last_processed_at
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 1
        assert computes[0].scale_in is False
        assert gateway.replica_scale_attempt == 0  # The desired count is met, reset counter

    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_scales_out_when_desired_replica_count_increased(
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
            replicas=3,
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
                replica_num=0,
                populate_configuration=populate_configuration,
            )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        computes = sorted(
            await _fetch_all_gateway_computes(session, gateway.id), key=lambda c: c.replica_num
        )
        assert [c.replica_num for c in computes] == [0, 1, 2]
        assert [c.status for c in computes] == [
            GatewayReplicaStatus.RUNNING,
            GatewayReplicaStatus.SUBMITTED,
            GatewayReplicaStatus.SUBMITTED,
        ]
        assert gateway.replica_scale_attempt == 1
        assert gateway.last_replica_scale_attempt_at is not None

    async def test_scales_in_oldest_replicas_when_desired_replica_count_decreased(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
        )
        compute0 = await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        compute0.created_at = datetime(2025, 1, 1)
        compute1 = await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=1
        )
        compute1.created_at = datetime(2025, 1, 2)
        compute2 = await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=2
        )
        compute2.created_at = datetime(2025, 1, 3)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        await session.refresh(compute0)
        await session.refresh(compute1)
        await session.refresh(compute2)
        assert compute0.scale_in is True
        assert compute1.scale_in is True
        assert compute2.scale_in is False

    async def test_scale_in_prefers_less_advanced_replicas_over_older_running_ones(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
        )
        running = await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        running.created_at = datetime(2025, 1, 1)
        submitted = await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.SUBMITTED,
            replica_num=1,
            ip_address=None,
            instance_id=None,
            region=None,
            configuration=get_gateway_compute_configuration().json(),
        )
        submitted.created_at = datetime(2025, 1, 2)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(running)
        await session.refresh(submitted)
        assert running.scale_in is False
        assert submitted.scale_in is True

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_no_scaling_for_legacy_gateway_without_desired_replica_count(
        self, test_db, session: AsyncSession, worker: GatewayWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.RUNNING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            await create_gateway_compute(
                session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
            )
        gateway.desired_replica_count = None
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 1
        assert computes[0].scale_in is False

    async def test_scale_out_skipped_before_retry_delay_elapses(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = 1
        gateway.last_replica_scale_attempt_at = get_current_datetime()
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 1
        assert gateway.replica_scale_attempt == 1

    async def test_scale_out_retries_after_retry_delay_elapses(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = 1
        gateway.last_replica_scale_attempt_at = get_current_datetime() - timedelta(minutes=5)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 2
        assert gateway.replica_scale_attempt == 2

    async def test_scale_out_stops_after_reaching_attempt_limit(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = _MAX_REPLICA_SCALE_ATTEMPTS
        gateway.last_replica_scale_attempt_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 1
        assert gateway.replica_scale_attempt == _MAX_REPLICA_SCALE_ATTEMPTS
        events = await list_events(session)
        assert len(events) == 0

    async def test_scale_out_emits_event_on_reaching_attempt_limit(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = _MAX_REPLICA_SCALE_ATTEMPTS - 1
        gateway.last_replica_scale_attempt_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        # Last allowed attempt still creates the missing replica
        assert len(computes) == 2
        assert gateway.replica_scale_attempt == _MAX_REPLICA_SCALE_ATTEMPTS
        events = await list_events(session)
        assert len(events) == 1
        assert "final replica scale-out attempt" in events[0].message

    async def test_attempt_counter_not_reset_while_replacement_replica_still_provisioning(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=1,
        )
        await create_gateway_compute(
            session,
            gateway_id=gateway.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.PROVISIONING,
            replica_num=0,
            configuration=get_gateway_compute_configuration().json(),
        )
        gateway.replica_scale_attempt = 2
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        assert gateway.replica_scale_attempt == 2

    async def test_attempt_counter_resets_and_scales_out_immediately_after_in_place_update(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = _MAX_REPLICA_SCALE_ATTEMPTS
        gateway.last_replica_scale_attempt_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        # updated after previous scale attempt
        gateway.last_update_at = datetime(2025, 1, 2, 3, 5, tzinfo=timezone.utc)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 5, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 2
        assert gateway.replica_scale_attempt == 1

    async def test_attempt_counter_not_reset_when_update_precedes_last_scale_attempt(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            replicas=2,
        )
        await create_gateway_compute(
            session, gateway_id=gateway.id, status=GatewayReplicaStatus.RUNNING, replica_num=0
        )
        gateway.replica_scale_attempt = _MAX_REPLICA_SCALE_ATTEMPTS
        gateway.last_replica_scale_attempt_at = get_current_datetime()
        gateway.last_update_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        await worker.process(_gateway_to_pipeline_item(gateway))

        await session.refresh(gateway)
        computes = await _fetch_all_gateway_computes(session, gateway.id)
        assert len(computes) == 1
        assert gateway.replica_scale_attempt == _MAX_REPLICA_SCALE_ATTEMPTS


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
            replicas=2,
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
