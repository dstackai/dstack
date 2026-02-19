import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.gateways import GatewayProvisioningData, GatewayStatus
from dstack._internal.server.background.pipeline_tasks.gateways import (
    GatewayPipelineItem,
    GatewayWorker,
)
from dstack._internal.server.testing.common import (
    AsyncContextManager,
    ComputeMockSpec,
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
    list_events,
)


@pytest.fixture
def worker() -> GatewayWorker:
    return GatewayWorker(queue=Mock(), heartbeater=Mock())


def _gateway_to_pipeline_item(gateway_model) -> GatewayPipelineItem:
    assert gateway_model.lock_token is not None
    assert gateway_model.lock_expires_at is not None
    return GatewayPipelineItem(
        __tablename__=gateway_model.__tablename__,
        id=gateway_model.id,
        lock_token=gateway_model.lock_token,
        lock_expires_at=gateway_model.lock_expires_at,
        prev_lock_expired=False,
        status=gateway_model.status,
    )


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
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backend_with_model_by_type_or_error"
        ) as m:
            aws = Mock()
            m.return_value = (backend, aws)
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway.return_value = GatewayProvisioningData(
                instance_id="i-1234567890",
                ip_address="2.2.2.2",
                region="us",
            )
            await worker.process(_gateway_to_pipeline_item(gateway))
            m.assert_called_once()
            aws.compute.return_value.create_gateway.assert_called_once()

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.PROVISIONING
        assert gateway.gateway_compute is not None
        assert gateway.gateway_compute.ip_address == "2.2.2.2"
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed SUBMITTED -> PROVISIONING"

    async def test_marks_gateway_as_failed_if_gateway_creation_errors(
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
            aws = Mock()
            m.return_value = (backend, aws)
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway.side_effect = BackendError("Some error")
            await worker.process(_gateway_to_pipeline_item(gateway))
            m.assert_called_once()
            aws.compute.return_value.create_gateway.assert_called_once()

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.FAILED
        assert gateway.status_message == "Some error"
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed SUBMITTED -> FAILED (Some error)"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayWorkerProvisioning:
    async def test_provisioning_to_running(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway_compute = await create_gateway_compute(session)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            status=GatewayStatus.PROVISIONING,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
        ) as pool_add:
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            await worker.process(_gateway_to_pipeline_item(gateway))
            pool_add.assert_called_once()

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.RUNNING
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway status changed PROVISIONING -> RUNNING"

    async def test_marks_gateway_as_failed_if_fails_to_connect(
        self, test_db, session: AsyncSession, worker: GatewayWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway_compute = await create_gateway_compute(session)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            status=GatewayStatus.PROVISIONING,
        )
        gateway.lock_token = uuid.uuid4()
        gateway.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.connect_to_gateway_with_retry"
        ) as connect_to_gateway_with_retry_mock:
            connect_to_gateway_with_retry_mock.return_value = None
            await worker.process(_gateway_to_pipeline_item(gateway))
            connect_to_gateway_with_retry_mock.assert_called_once()

        await session.refresh(gateway)
        assert gateway.status == GatewayStatus.FAILED
        assert gateway.status_message == "Failed to connect to gateway"
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Gateway status changed PROVISIONING -> FAILED (Failed to connect to gateway)"
        )
