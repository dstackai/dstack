import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.gateways import (
    GatewayProvisioningData,
    GatewayReplicaStatus,
    GatewayStatus,
)
from dstack._internal.server.background.pipeline_tasks.gateway_replicas import (
    GatewayReplicaFetcher,
    GatewayReplicaPipeline,
    GatewayReplicaPipelineItem,
    GatewayReplicaWorker,
)
from dstack._internal.server.models import GatewayComputeModel
from dstack._internal.server.testing.common import (
    AsyncContextManager,
    ComputeMockSpec,
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
    get_gateway_compute_configuration,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> GatewayReplicaWorker:
    return GatewayReplicaWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.fixture
def fetcher() -> GatewayReplicaFetcher:
    return GatewayReplicaFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _compute_to_pipeline_item(
    compute: GatewayComputeModel,
) -> GatewayReplicaPipelineItem:
    assert compute.lock_token is not None
    assert compute.lock_expires_at is not None
    return GatewayReplicaPipelineItem(
        __tablename__=compute.__tablename__,
        id=compute.id,
        lock_token=compute.lock_token,
        lock_expires_at=compute.lock_expires_at,
        prev_lock_expired=False,
        status=compute.status,
    )


def _lock_compute(compute: GatewayComputeModel) -> None:
    compute.lock_token = uuid.uuid4()
    compute.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaFetcher:
    async def test_fetch_selects_eligible_replicas_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: GatewayReplicaFetcher
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        submitted = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            last_processed_at=stale - timedelta(seconds=3),
            configuration=get_gateway_compute_configuration().json(),
        )
        provisioning = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.PROVISIONING,
            last_processed_at=stale - timedelta(seconds=2),
        )
        terminating = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
            last_processed_at=stale - timedelta(seconds=1),
        )
        running = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=stale,
        )
        terminated = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.TERMINATED,
            active=False,
            last_processed_at=stale,
        )
        recent = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.SUBMITTED,
            ip_address=None,
            instance_id=None,
            region=None,
            last_processed_at=now,
            configuration=get_gateway_compute_configuration().json(),
        )
        recent.created_at = now - timedelta(minutes=2)
        recent.last_processed_at = now
        locked = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.SUBMITTED,
            ip_address=None,
            instance_id=None,
            region=None,
            last_processed_at=stale + timedelta(seconds=1),
            configuration=get_gateway_compute_configuration().json(),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {submitted.id, provisioning.id, terminating.id}
        assert {(item.id, item.status) for item in items} == {
            (submitted.id, GatewayReplicaStatus.SUBMITTED),
            (provisioning.id, GatewayReplicaStatus.PROVISIONING),
            (terminating.id, GatewayReplicaStatus.TERMINATING),
        }

        for compute in [submitted, provisioning, terminating, running, terminated, recent, locked]:
            await session.refresh(compute)

        fetched = [submitted, provisioning, terminating]
        assert all(c.lock_owner == GatewayReplicaPipeline.__name__ for c in fetched)
        assert all(c.lock_expires_at is not None for c in fetched)
        assert all(c.lock_token is not None for c in fetched)
        assert len({c.lock_token for c in fetched}) == 1

        assert running.lock_owner is None
        assert terminated.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    @pytest.mark.parametrize(
        "gateway_status,to_be_deleted",
        [
            (GatewayStatus.FAILED, False),
            (GatewayStatus.RUNNING, True),
        ],
    )
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_fetch_includes_running_replica_needing_cleanup(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_compute: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=gateway_status,
        )
        gateway.to_be_deleted = to_be_deleted
        stale = get_current_datetime() - timedelta(minutes=1)
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == compute.id
        assert items[0].status == GatewayReplicaStatus.RUNNING

    async def test_fetch_includes_running_replica_with_hard_deleted_gateway(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
    ):
        # A compute whose gateway was hard-deleted (orphaned). The fetcher should
        # pick it up so the worker can log the error.
        stale = get_current_datetime() - timedelta(minutes=1)
        compute = await create_gateway_compute(
            session=session,
            gateway_id=None,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=stale,
        )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == compute.id
        assert items[0].status == GatewayReplicaStatus.RUNNING

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_fetch_excludes_running_replica_with_healthy_gateway(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
        legacy_compute: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        stale = get_current_datetime() - timedelta(minutes=1)
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
            gateway.gateway_compute_id = compute.id
        else:
            await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerSubmitted:
    async def test_submitted_to_provisioning(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway.return_value = GatewayProvisioningData(
                instance_id="i-1234567890",
                ip_address="2.2.2.2",
                region="us",
            )
            await worker.process(_compute_to_pipeline_item(compute))
            aws.compute.return_value.create_gateway.assert_called_once()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.PROVISIONING
        assert compute.ip_address == "2.2.2.2"
        assert compute.instance_id == "i-1234567890"
        assert compute.region == "us"

    async def test_submitted_backend_error_marks_terminated(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway.side_effect = BackendError("Some error")
            await worker.process(_compute_to_pipeline_item(compute))

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    async def test_submitted_backend_not_available_marks_terminated(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            m.return_value = []
            await worker.process(_compute_to_pipeline_item(compute))

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    async def test_submitted_skips_provisioning_if_gateway_to_be_deleted(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        gateway.to_be_deleted = True
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            await worker.process(_compute_to_pipeline_item(compute))
            m.assert_not_called()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    async def test_submitted_skips_provisioning_if_gateway_failed(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            await worker.process(_compute_to_pipeline_item(compute))
            m.assert_not_called()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    async def test_submitted_unexpected_error_marks_terminated(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        compute = await create_gateway_compute(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_compute_configuration().json(),
        )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway.side_effect = RuntimeError("Unexpected!")
            await worker.process(_compute_to_pipeline_item(compute))

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.status_message == "Unexpected error"
        assert compute.active is False
        assert compute.deleted is True


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerRunning:
    @pytest.mark.parametrize(
        "gateway_status,to_be_deleted",
        [
            (GatewayStatus.FAILED, False),
            (GatewayStatus.RUNNING, True),
        ],
    )
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_running_to_terminating(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_compute: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=gateway_status,
        )
        gateway.to_be_deleted = to_be_deleted
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                active=True,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                active=True,
            )
        _lock_compute(compute)
        await session.commit()

        await worker.process(_compute_to_pipeline_item(compute))

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATING
        assert compute.active is False


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerProvisioning:
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_provisioning_to_running(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
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
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
        ) as pool_add:
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            await worker.process(_compute_to_pipeline_item(compute))
            pool_add.assert_called_once()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.RUNNING
        assert compute.active is True

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_provisioning_to_terminating_if_connect_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
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
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.connect_to_gateway_with_retry"
        ) as connect_mock:
            connect_mock.return_value = None
            await worker.process(_compute_to_pipeline_item(compute))
            connect_mock.assert_called_once()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATING
        assert compute.active is False
        assert compute.status_message == "Failed to connect to gateway"

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_provisioning_to_terminating_if_configure_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
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
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_compute(compute)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.connect_to_gateway_with_retry"
            ) as connect_mock,
            patch("dstack._internal.server.services.gateways.configure_gateway") as configure_mock,
        ):
            connect_mock.return_value = MagicMock()
            configure_mock.side_effect = Exception("Configure failed")
            await worker.process(_compute_to_pipeline_item(compute))
            connect_mock.assert_called_once()
            configure_mock.assert_called_once()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATING
        assert compute.active is False
        assert compute.status_message == "Failed to configure gateway"

    @pytest.mark.parametrize(
        "gateway_status,to_be_deleted",
        [
            (GatewayStatus.FAILED, False),
            (GatewayStatus.RUNNING, True),
        ],
    )
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_provisioning_to_terminating_if_gateway_needs_cleanup(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_compute: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=gateway_status,
        )
        gateway.to_be_deleted = to_be_deleted
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.gateway_replicas._connect_and_configure_gateway_replica"
        ) as connect_mock:
            await worker.process(_compute_to_pipeline_item(compute))
            connect_mock.assert_not_called()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATING
        assert compute.active is False


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerTerminating:
    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_terminating_to_terminated(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_compute(compute)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ) as remove_mock,
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_compute_to_pipeline_item(compute))

            get_backends_mock.assert_called_once()
            backend_mock.compute.return_value.terminate_gateway.assert_called_once()
            remove_mock.assert_called_once_with(compute.ip_address)

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_terminating_to_terminated_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_compute(compute)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as get_backends_mock:
            get_backends_mock.return_value = []
            await worker.process(_compute_to_pipeline_item(compute))

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_terminating_to_terminated_with_no_instance_id(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                instance_id=None,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                instance_id=None,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_compute(compute)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ) as remove_mock,
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_compute_to_pipeline_item(compute))

            backend_mock.compute.return_value.terminate_gateway.assert_not_called()
            remove_mock.assert_not_called()

        await session.refresh(compute)
        assert compute.status == GatewayReplicaStatus.TERMINATED
        assert compute.active is False
        assert compute.deleted is True

    @pytest.mark.parametrize("legacy_compute", [False, True])
    async def test_terminating_retries_if_terminate_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_compute: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_compute:
            compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_compute_id = compute.id
        else:
            compute = await create_gateway_compute(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_compute(compute)
        original_last_processed_at = compute.last_processed_at
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ) as remove_mock,
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.terminate_gateway.side_effect = Exception(
                "Terminate failed"
            )
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_compute_to_pipeline_item(compute))

            get_backends_mock.assert_called_once()
            backend_mock.compute.return_value.terminate_gateway.assert_called_once()
            remove_mock.assert_not_called()

        await session.refresh(compute)
        # Not TERMINATED, should retry termination
        assert compute.status == GatewayReplicaStatus.TERMINATING
        assert compute.last_processed_at > original_last_processed_at
        assert compute.lock_token is None
        assert compute.lock_expires_at is None
        assert compute.lock_owner is None
