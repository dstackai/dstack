import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import ANY, AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import ComputeWithGatewaySupport
from dstack._internal.core.errors import BackendError, GatewayError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.gateways import (
    ACMGatewayCertificate,
    GatewayReplicaProvisioningData,
    GatewayReplicaStatus,
    GatewayStatus,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus, RunStatus, ServiceSpec
from dstack._internal.proxy.gateway.schemas.services import ServiceListItem, ServiceListReplicaItem
from dstack._internal.server.background.pipeline_tasks.gateway_replicas import (
    GatewayReplicaFetcher,
    GatewayReplicaPipeline,
    GatewayReplicaPipelineItem,
    GatewayReplicaWorker,
)
from dstack._internal.server.models import (
    GatewayReplicaModel,
    ServiceRegistrationModel,
    ServiceReplicaRegistrationModel,
)
from dstack._internal.server.testing.common import (
    AsyncContextManager,
    ComputeMockSpec,
    create_backend,
    create_fleet,
    create_gateway,
    create_gateway_replica,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_gateway_replica_configuration,
    get_job_provisioning_data,
    get_run_spec,
    list_events,
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


def _replica_to_pipeline_item(
    replica: GatewayReplicaModel,
) -> GatewayReplicaPipelineItem:
    assert replica.lock_token is not None
    assert replica.lock_expires_at is not None
    return GatewayReplicaPipelineItem(
        __tablename__=replica.__tablename__,
        id=replica.id,
        lock_token=replica.lock_token,
        lock_expires_at=replica.lock_expires_at,
        prev_lock_expired=False,
        status=replica.status,
    )


def _lock_replica(replica: GatewayReplicaModel) -> None:
    replica.lock_token = uuid.uuid4()
    replica.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)


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
            replicas=7,
        )
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        submitted = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            last_processed_at=stale - timedelta(seconds=3),
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        provisioning = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.PROVISIONING,
            last_processed_at=stale - timedelta(seconds=2),
        )
        terminating = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
            last_processed_at=stale - timedelta(seconds=1),
        )
        running = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=stale,
        )
        terminated = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.TERMINATED,
            active=False,
            last_processed_at=stale,
        )
        recent = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.SUBMITTED,
            ip_address=None,
            instance_id=None,
            region=None,
            last_processed_at=now,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        recent.created_at = now - timedelta(minutes=2)
        recent.last_processed_at = now
        locked = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.SUBMITTED,
            ip_address=None,
            instance_id=None,
            region=None,
            last_processed_at=stale + timedelta(seconds=1),
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            submitted.id,
            provisioning.id,
            terminating.id,
            running.id,
        }
        assert {(item.id, item.status) for item in items} == {
            (submitted.id, GatewayReplicaStatus.SUBMITTED),
            (provisioning.id, GatewayReplicaStatus.PROVISIONING),
            (terminating.id, GatewayReplicaStatus.TERMINATING),
            (running.id, GatewayReplicaStatus.RUNNING),
        }

        for replica in [submitted, provisioning, terminating, running, terminated, recent, locked]:
            await session.refresh(replica)

        fetched = [submitted, provisioning, terminating, running]
        assert all(c.lock_owner == GatewayReplicaPipeline.__name__ for c in fetched)
        assert all(c.lock_expires_at is not None for c in fetched)
        assert all(c.lock_token is not None for c in fetched)
        assert len({c.lock_token for c in fetched}) == 1

        assert terminated.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_includes_recent_replica_with_skip_min_processing_interval(
        self, test_db, session: AsyncSession, fetcher: GatewayReplicaFetcher
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        now = get_current_datetime()
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=now,
        )
        replica.skip_min_processing_interval = True
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [replica.id]
        await session.refresh(replica)
        assert not replica.skip_min_processing_interval

    @pytest.mark.parametrize(
        "gateway_status,to_be_deleted",
        [
            (GatewayStatus.FAILED, False),
            (GatewayStatus.RUNNING, True),
        ],
    )
    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_fetch_includes_running_replica_needing_cleanup(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_replica: bool,
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
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == replica.id
        assert items[0].status == GatewayReplicaStatus.RUNNING

    async def test_fetch_includes_running_replica_with_hard_deleted_gateway(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
    ):
        # A replica whose gateway was hard-deleted (orphaned). The fetcher should
        # pick it up so the worker can log the error.
        stale = get_current_datetime() - timedelta(minutes=1)
        replica = await create_gateway_replica(
            session=session,
            gateway_id=None,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=stale,
        )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == replica.id
        assert items[0].status == GatewayReplicaStatus.RUNNING

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_fetch_includes_running_replica_with_healthy_gateway(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
        legacy_replica: bool,
    ):
        # Healthy running replicas are still fetched periodically so the worker
        # can run gateway state sync (see _process_running_item).
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        stale = get_current_datetime() - timedelta(minutes=1)
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                last_processed_at=stale,
            )
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == replica.id
        assert items[0].status == GatewayReplicaStatus.RUNNING

    async def test_fetch_includes_running_replica_marked_for_scale_in(
        self,
        test_db,
        session: AsyncSession,
        fetcher: GatewayReplicaFetcher,
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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.RUNNING,
            last_processed_at=stale,
        )
        replica.scale_in = True
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert len(items) == 1
        assert items[0].id == replica.id
        assert items[0].status == GatewayReplicaStatus.RUNNING


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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway_replica.return_value = (
                GatewayReplicaProvisioningData(
                    instance_id="i-1234567890",
                    ip_address="2.2.2.2",
                    region="us",
                )
            )
            await worker.process(_replica_to_pipeline_item(replica))
            aws.compute.return_value.create_gateway_replica.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.PROVISIONING
        assert replica.ip_address == "2.2.2.2"
        assert replica.instance_id == "i-1234567890"
        assert replica.region == "us"

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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway_replica.side_effect = BackendError(
                "Some error"
            )
            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            m.return_value = []
            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            await worker.process(_replica_to_pipeline_item(replica))
            m.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            await worker.process(_replica_to_pipeline_item(replica))
            m.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            aws = Mock()
            m.return_value = [(backend, aws)]
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.create_gateway_replica.side_effect = RuntimeError(
                "Unexpected!"
            )
            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.status_message == "Unexpected error"
        assert replica.active is False
        assert replica.deleted is True

    async def test_submitted_to_terminated_when_scaled_in(
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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            ip_address=None,
            instance_id=None,
            region=None,
            status=GatewayReplicaStatus.SUBMITTED,
            configuration=get_gateway_replica_configuration().model_dump_json(),
        )
        replica.scale_in = True
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as m:
            await worker.process(_replica_to_pipeline_item(replica))
            m.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True
        assert replica.status_message == "Scaled in"


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
    @pytest.mark.parametrize("legacy_replica", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_running_to_terminating(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_replica: bool,
        populate_configuration: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=gateway_status,
            populate_configuration=populate_configuration,
        )
        gateway.to_be_deleted = to_be_deleted
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.RUNNING,
                active=True,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.RUNNING,
                active=True,
                populate_configuration=populate_configuration,
            )
        _lock_replica(replica)
        await session.commit()

        await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False

    async def test_running_to_terminating_when_scaled_in(
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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            status=GatewayReplicaStatus.RUNNING,
            active=True,
        )
        replica.scale_in = True
        _lock_replica(replica)
        await session.commit()

        await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False
        assert replica.status_message == "Scaled in"


def _get_client_mock(mock_gateway_connection: AsyncMock) -> AsyncMock:
    return mock_gateway_connection.return_value.client.return_value.__aenter__.return_value


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerRunningStateSync:
    """
    Covers `_process_running_item`'s gateway state sync: registering/unregistering
    services and replicas so the gateway matches expected DB state, and recording
    the outcome in `ServiceRegistrationModel`/`ServiceReplicaRegistrationModel`.
    """

    pytestmark = pytest.mark.usefixtures("image_config_mock")

    async def _create_service_run_and_job(
        self,
        session: AsyncSession,
        project,
        repo,
        user,
        gateway,
        run_name: str,
        run_status: RunStatus = RunStatus.RUNNING,
        job_status: JobStatus = JobStatus.RUNNING,
        job_registered: bool = True,
        replica_num: int = 0,
        service_url: Optional[str] = None,
    ):
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_name,
            status=run_status,
            run_spec=get_run_spec(
                run_name=run_name,
                repo_id=repo.name,
                configuration=ServiceConfiguration(port=80, image="ubuntu"),
            ),
            gateway=gateway,
        )
        run.service_spec = ServiceSpec(
            url=service_url or f"https://{run_name}.example.com"
        ).model_dump_json()
        await session.commit()
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY, fleet=fleet
        )
        job = await create_job(
            session=session,
            run=run,
            status=job_status,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
            instance_assigned=True,
            registered=job_registered,
            ready=job_registered,
            replica_num=replica_num,
        )
        return run, job

    async def test_registers_new_service_and_replica(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
            ssh_private_key="replica-private-key",
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="test-service"
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = []

        await worker.process(_replica_to_pipeline_item(replica))

        mock_gateway_connection.assert_called_once_with(
            hostname=replica.ip_address, id_rsa="replica-private-key"
        )
        client_mock.register_service.assert_called_once_with(
            project=project.name,
            run_id=run.id,
            run_name="test-service",
            domain="test-service.example.com",
            service_https=ANY,
            gateway_https=ANY,
            auth=ANY,
            client_max_body_size=ANY,
            options={},
            rate_limits=[],
            ssh_private_key=project.ssh_private_key,
            has_router_replica=False,
        )
        client_mock.register_replica.assert_called_once_with(
            project=project.name,
            run_name="test-service",
            configuration=ANY,
            job_spec=ANY,
            job_submission=ANY,
            instance_project_ssh_private_key=None,
            ssh_head_proxy=None,
            ssh_head_proxy_private_key=None,
        )
        assert client_mock.register_replica.call_args.kwargs["job_submission"].id == job.id
        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()

        service_registration = (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.run_id == run.id,
                    ServiceRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert service_registration.is_registered is True
        assert service_registration.register_attempt == 0
        assert service_registration.register_status_message is None

        replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_registration.is_registered is True

        events = await list_events(session)
        assert {e.message for e in events} == {
            f"Service registered on gateway replica {replica.replica_num}",
            f"Service replica registered on gateway replica {replica.replica_num}",
        }

    async def test_unregisters_dangling_service_and_stale_replica(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        # A live, still-expected service with one live replica and one stale
        # replica (of the same run) that the gateway still thinks is registered.
        run1, job1 = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="live-service"
        )
        stale_job = await create_job(
            session=session,
            run=run1,
            status=JobStatus.TERMINATED,
            registered=False,
            replica_num=1,
        )
        # A finished run whose service is still (erroneously) registered on the gateway.
        run2, _ = await self._create_service_run_and_job(
            session,
            project,
            repo,
            user,
            gateway,
            run_name="dangling-service",
            run_status=RunStatus.TERMINATED,
            job_status=JobStatus.TERMINATED,
            job_registered=False,
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run1.id.hex,
                project_name=project.name,
                run_name="live-service",
                replicas=[
                    ServiceListReplicaItem(id=job1.id.hex),
                    ServiceListReplicaItem(id=stale_job.id.hex),
                ],
            ),
            ServiceListItem(
                id=run2.id.hex,
                project_name=project.name,
                run_name="dangling-service",
                replicas=[],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.register_service.assert_not_called()
        client_mock.register_replica.assert_not_called()
        client_mock.unregister_service.assert_called_once_with(
            project=project.name, run_name="dangling-service"
        )
        client_mock.unregister_replica.assert_called_once_with(
            project=project.name, run_name="live-service", job_id=stale_job.id
        )

        run1_registration = (
            (
                await session.execute(
                    select(ServiceRegistrationModel).where(
                        ServiceRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {r.run_id for r in run1_registration} == {run1.id}
        assert all(r.is_registered for r in run1_registration)

        replica_registrations = (
            (
                await session.execute(
                    select(ServiceReplicaRegistrationModel).where(
                        ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {r.job_id for r in replica_registrations} == {job1.id}
        assert all(r.is_registered for r in replica_registrations)

        events = await list_events(session)
        assert {e.message for e in events} == {
            f"Service unregistered from gateway replica {replica.replica_num}",
            f"Service replica unregistered from gateway replica {replica.replica_num}",
        }

    async def test_deletes_registration_models_for_unregistered_service_and_replica(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        # A live, still-expected service with one live replica and one stale
        # replica (of the same run) that the gateway still thinks is registered.
        run1, job1 = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="live-service"
        )
        stale_job = await create_job(
            session=session,
            run=run1,
            status=JobStatus.TERMINATED,
            registered=False,
            replica_num=1,
        )
        # A finished run whose service is still (erroneously) registered on the gateway.
        run2, _ = await self._create_service_run_and_job(
            session,
            project,
            repo,
            user,
            gateway,
            run_name="dangling-service",
            run_status=RunStatus.TERMINATED,
            job_status=JobStatus.TERMINATED,
            job_registered=False,
        )
        # Pre-existing registration records for everything currently on the
        # gateway, including the ones about to be unregistered.
        live_service_registration = ServiceRegistrationModel(
            run_id=run1.id, gateway_replica_id=replica.id, is_registered=True
        )
        live_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job1.id, gateway_replica_id=replica.id, is_registered=True
        )
        stale_replica_registration = ServiceReplicaRegistrationModel(
            job_id=stale_job.id, gateway_replica_id=replica.id, is_registered=True
        )
        dangling_service_registration = ServiceRegistrationModel(
            run_id=run2.id, gateway_replica_id=replica.id, is_registered=True
        )
        session.add_all(
            [
                live_service_registration,
                live_replica_registration,
                stale_replica_registration,
                dangling_service_registration,
            ]
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run1.id.hex,
                project_name=project.name,
                run_name="live-service",
                replicas=[
                    ServiceListReplicaItem(id=job1.id.hex),
                    ServiceListReplicaItem(id=stale_job.id.hex),
                ],
            ),
            ServiceListItem(
                id=run2.id.hex,
                project_name=project.name,
                run_name="dangling-service",
                replicas=[],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.unregister_service.assert_called_once_with(
            project=project.name, run_name="dangling-service"
        )
        client_mock.unregister_replica.assert_called_once_with(
            project=project.name, run_name="live-service", job_id=stale_job.id
        )

        remaining_service_registrations = (
            (
                await session.execute(
                    select(ServiceRegistrationModel).where(
                        ServiceRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {r.run_id for r in remaining_service_registrations} == {run1.id}
        assert {r.id for r in remaining_service_registrations} == {live_service_registration.id}

        remaining_replica_registrations = (
            (
                await session.execute(
                    select(ServiceReplicaRegistrationModel).where(
                        ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {r.job_id for r in remaining_replica_registrations} == {job1.id}
        assert {r.id for r in remaining_replica_registrations} == {live_replica_registration.id}

        # The registration records for the now-unregistered service and replica
        # are gone
        assert (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.id == dangling_service_registration.id,
                )
            )
        ).scalar_one_or_none() is None
        assert (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.id == stale_replica_registration.id,
                )
            )
        ).scalar_one_or_none() is None

    async def test_unregisters_replicas_of_dangling_service_without_extra_gateway_call(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        # A finished run whose service and replica are still (erroneously)
        # registered on the gateway, including a stale DB registration record
        # left over from before the run finished.
        run, job = await self._create_service_run_and_job(
            session,
            project,
            repo,
            user,
            gateway,
            run_name="dangling-service",
            run_status=RunStatus.TERMINATED,
            job_status=JobStatus.TERMINATED,
            job_registered=False,
        )
        stale_service_registration = ServiceRegistrationModel(
            run_id=run.id, gateway_replica_id=replica.id, is_registered=True
        )
        stale_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job.id, gateway_replica_id=replica.id, is_registered=True
        )
        session.add_all([stale_service_registration, stale_replica_registration])
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="dangling-service",
                replicas=[ServiceListReplicaItem(id=job.id.hex)],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.unregister_service.assert_called_once_with(
            project=project.name, run_name="dangling-service"
        )
        # The replica is implicitly unregistered along with the service - no
        # separate unregister_replica call, which would fail anyway since the
        # service is already gone.
        client_mock.unregister_replica.assert_not_called()

        # Both registration records are dropped in this same tick, rather than
        # being kept around as `is_registered=True` until the next tick.
        assert (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.id == stale_service_registration.id,
                )
            )
        ).scalar_one_or_none() is None
        assert (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.id == stale_replica_registration.id,
                )
            )
        ).scalar_one_or_none() is None

        events = await list_events(session)
        assert {e.message for e in events} == {
            f"Service unregistered from gateway replica {replica.replica_num}",
            f"Service replica unregistered from gateway replica {replica.replica_num}",
        }

    async def test_no_gateway_calls_when_state_already_in_sync(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="synced-service"
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="synced-service",
                replicas=[ServiceListReplicaItem(id=job.id.hex)],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.register_service.assert_not_called()
        client_mock.register_replica.assert_not_called()
        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()
        client_mock.set_service_id.assert_not_called()

        # Registration records are still (re)created to reflect the confirmed state,
        # even though no gateway calls were needed this tick.
        service_registration = (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.run_id == run.id,
                    ServiceRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert service_registration.is_registered is True
        replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_registration.is_registered is True

        # No events since nothing actually changed from the gateway's perspective.
        assert not await list_events(session)

    async def test_recovers_legacy_service_id_by_matching_replica(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="legacy-service"
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            # Pre-0.21.0 gateways report services without an id.
            ServiceListItem(
                id=None,
                project_name=project.name,
                run_name="legacy-service",
                replicas=[ServiceListReplicaItem(id=job.id.hex)],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.set_service_id.assert_called_once_with(
            project=project.name, run_name="legacy-service", run_id=run.id
        )
        client_mock.register_service.assert_not_called()
        client_mock.register_replica.assert_not_called()
        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()

    async def test_unregisters_and_reregisters_legacy_service_without_id_and_replicas(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="legacy-service"
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            # A legacy entry with no ID and no replicas: there's nothing to match
            # it against, so it cannot be told apart from genuine garbage and must
            # be unregistered. The real, still-expected run gets registered fresh.
            ServiceListItem(
                id=None,
                project_name=project.name,
                run_name="legacy-service",
                replicas=[],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.set_service_id.assert_not_called()
        client_mock.unregister_service.assert_called_once_with(
            project=project.name, run_name="legacy-service"
        )
        client_mock.register_service.assert_called_once_with(
            project=project.name,
            run_id=run.id,
            run_name="legacy-service",
            domain=ANY,
            service_https=ANY,
            gateway_https=ANY,
            auth=ANY,
            client_max_body_size=ANY,
            options={},
            rate_limits=[],
            ssh_private_key=project.ssh_private_key,
            has_router_replica=False,
        )
        client_mock.register_replica.assert_called_once_with(
            project=project.name,
            run_name="legacy-service",
            configuration=ANY,
            job_spec=ANY,
            job_submission=ANY,
            instance_project_ssh_private_key=None,
            ssh_head_proxy=None,
            ssh_head_proxy_private_key=None,
        )

        service_registration = (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.run_id == run.id,
                    ServiceRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert service_registration.is_registered is True
        replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_registration.is_registered is True

        # No unregistration event: the dangling legacy entry has no ID, so it can't
        # be tied to a run for event targeting (only the fresh registration is).
        events = await list_events(session)
        assert {e.message for e in events} == {
            f"Service registered on gateway replica {replica.replica_num}",
            f"Service replica registered on gateway replica {replica.replica_num}",
        }

    async def test_does_nothing_when_in_sync_and_registrations_already_exist(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="synced-service"
        )
        existing_service_registration = ServiceRegistrationModel(
            run_id=run.id,
            gateway_replica_id=replica.id,
            is_registered=True,
            register_attempt=0,
        )
        existing_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job.id,
            gateway_replica_id=replica.id,
            is_registered=True,
            register_attempt=0,
        )
        session.add_all([existing_service_registration, existing_replica_registration])
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="synced-service",
                replicas=[ServiceListReplicaItem(id=job.id.hex)],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.register_service.assert_not_called()
        client_mock.register_replica.assert_not_called()
        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()
        client_mock.set_service_id.assert_not_called()

        service_registrations = (
            (
                await session.execute(
                    select(ServiceRegistrationModel).where(
                        ServiceRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(service_registrations) == 1
        assert service_registrations[0].id == existing_service_registration.id
        assert service_registrations[0].is_registered is True
        assert service_registrations[0].register_attempt == 0

        replica_registrations = (
            (
                await session.execute(
                    select(ServiceReplicaRegistrationModel).where(
                        ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(replica_registrations) == 1
        assert replica_registrations[0].id == existing_replica_registration.id
        assert replica_registrations[0].is_registered is True
        assert replica_registrations[0].register_attempt == 0

        assert not await list_events(session)

    async def test_reconciles_out_of_sync_registration_models(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="drifted-service"
        )
        # Local bookkeeping incorrectly thinks these failed to register, but the
        # gateway actually already has them registered (e.g. the server crashed
        # right after a successful registration, before it could record that).
        stale_service_registration = ServiceRegistrationModel(
            run_id=run.id,
            gateway_replica_id=replica.id,
            is_registered=False,
            register_attempt=3,
            register_status_message="stale error",
        )
        stale_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job.id,
            gateway_replica_id=replica.id,
            is_registered=False,
            register_attempt=2,
            register_status_message="stale replica error",
        )
        session.add_all([stale_service_registration, stale_replica_registration])
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="drifted-service",
                replicas=[ServiceListReplicaItem(id=job.id.hex)],
            ),
        ]

        await worker.process(_replica_to_pipeline_item(replica))

        # The gateway already reports it registered, so nothing needs to be
        # (re)registered - only the local bookkeeping needs correcting.
        client_mock.register_service.assert_not_called()
        client_mock.register_replica.assert_not_called()
        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()

        await session.refresh(stale_service_registration)
        await session.refresh(stale_replica_registration)
        assert stale_service_registration.is_registered is True
        assert stale_service_registration.register_attempt == 0
        assert stale_service_registration.register_status_message is None
        assert stale_replica_registration.is_registered is True
        assert stale_replica_registration.register_attempt == 0
        assert stale_replica_registration.register_status_message is None

        # No events: as far as the gateway is concerned nothing changed, we only
        # corrected stale local state.
        assert not await list_events(session)

    @pytest.mark.parametrize(
        (
            "make_error",
            "expected_service_register_status_message",
            "expected_replica_register_status_message",
        ),
        [
            pytest.param(
                GatewayError,
                "boom service",
                "boom replica",
                id="gateway_error",
            ),
            pytest.param(
                Exception,
                "Unexpected error",
                "Unexpected error",
                id="unexpected_error",
            ),
        ],
    )
    async def test_propagates_registration_errors_and_increments_register_attempt(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
        make_error: type[Exception],
        expected_service_register_status_message: str,
        expected_replica_register_status_message: str,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run_replica_fails, job_replica_fails = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="replica-fails"
        )
        run_service_fails, job_service_fails = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="service-fails"
        )
        # Simulate two earlier failed attempts to register this service.
        existing_registration = ServiceRegistrationModel(
            run_id=run_service_fails.id,
            gateway_replica_id=replica.id,
            is_registered=False,
            register_attempt=2,
            register_status_message="earlier error",
        )
        session.add(existing_registration)
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = []

        async def register_service_side_effect(**kwargs):
            if kwargs["run_name"] == "service-fails":
                raise make_error("boom service")

        async def register_replica_side_effect(**kwargs):
            if kwargs["run_name"] == "replica-fails":
                raise make_error("boom replica")

        client_mock.register_service.side_effect = register_service_side_effect
        client_mock.register_replica.side_effect = register_replica_side_effect

        await worker.process(_replica_to_pipeline_item(replica))

        client_mock.unregister_service.assert_not_called()
        client_mock.unregister_replica.assert_not_called()
        assert client_mock.register_service.call_count == 2
        # register_replica is only attempted for the run whose service registration
        # succeeded.
        client_mock.register_replica.assert_called_once_with(
            project=project.name,
            run_name="replica-fails",
            configuration=ANY,
            job_spec=ANY,
            job_submission=ANY,
            instance_project_ssh_private_key=None,
            ssh_head_proxy=None,
            ssh_head_proxy_private_key=None,
        )

        replica_fails_registration = (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.run_id == run_replica_fails.id,
                    ServiceRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_fails_registration.is_registered is True
        assert replica_fails_registration.register_attempt == 0
        assert replica_fails_registration.register_status_message is None

        replica_fails_replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job_replica_fails.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_fails_replica_registration.is_registered is False
        assert replica_fails_replica_registration.register_attempt == 1
        assert (
            replica_fails_replica_registration.register_status_message
            == expected_replica_register_status_message
        )

        await session.refresh(existing_registration)
        assert existing_registration.is_registered is False
        assert existing_registration.register_attempt == 3
        assert (
            existing_registration.register_status_message
            == expected_service_register_status_message
        )

        # A service's replicas are never attempted once its own registration failed.
        service_fails_replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job_service_fails.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one_or_none()
        assert service_fails_replica_registration is None

        events = await list_events(session)
        assert {e.message for e in events} == {
            f"Service registered on gateway replica {replica.replica_num}",
            (
                f"Encountered service registration error on gateway replica "
                f"{replica.replica_num}: {expected_service_register_status_message}"
            ),
            (
                f"Encountered service replica registration error on gateway replica "
                f"{replica.replica_num}: {expected_replica_register_status_message}"
            ),
        }

    async def test_does_not_emit_duplicate_registration_error_event_for_unchanged_error(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="replica-fails"
        )

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = []
        client_mock.register_replica.side_effect = GatewayError("boom replica")

        # First tick: the replica registration fails, recording the error and
        # emitting one error event.
        _lock_replica(replica)
        await session.commit()
        await worker.process(_replica_to_pipeline_item(replica))

        replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_registration.register_attempt == 1
        assert replica_registration.register_status_message == "boom replica"

        error_message = (
            f"Encountered service replica registration error on gateway replica "
            f"{replica.replica_num}: boom replica"
        )
        events_after_first_tick = await list_events(session)
        assert [e.message for e in events_after_first_tick].count(error_message) == 1

        # Second tick: the replica registration fails again with the exact same
        # error. `register_attempt` keeps incrementing, but no duplicate event is
        # emitted since nothing new happened from the user's perspective.
        await session.refresh(replica)
        _lock_replica(replica)
        await session.commit()
        await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica_registration)
        assert replica_registration.register_attempt == 2
        assert replica_registration.register_status_message == "boom replica"

        events_after_second_tick = await list_events(session)
        assert [e.message for e in events_after_second_tick].count(error_message) == 1

    @pytest.mark.parametrize(
        ("make_error", "expected_service_status_message", "expected_replica_status_message"),
        [
            pytest.param(
                GatewayError,
                "boom service",
                "boom replica",
                id="gateway_error",
            ),
            pytest.param(
                Exception,
                "Unexpected error",
                "Unexpected error",
                id="unexpected_error",
            ),
        ],
    )
    async def test_propagates_unregistration_errors_and_increments_unregister_attempt(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
        make_error: type[Exception],
        expected_service_status_message: str,
        expected_replica_status_message: str,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        # A live, still-expected service with one live replica and one stale
        # replica (of the same run) that the gateway still thinks is registered.
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="live-service"
        )
        stale_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATED,
            registered=False,
            replica_num=1,
        )
        # A finished run whose service is still (erroneously) registered on the gateway.
        dangling_run, _ = await self._create_service_run_and_job(
            session,
            project,
            repo,
            user,
            gateway,
            run_name="dangling-service",
            run_status=RunStatus.TERMINATED,
            job_status=JobStatus.TERMINATED,
            job_registered=False,
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="live-service",
                replicas=[
                    ServiceListReplicaItem(id=job.id.hex),
                    ServiceListReplicaItem(id=stale_job.id.hex),
                ],
            ),
            ServiceListItem(
                id=dangling_run.id.hex,
                project_name=project.name,
                run_name="dangling-service",
                replicas=[],
            ),
        ]
        client_mock.unregister_service.side_effect = make_error("boom service")
        client_mock.unregister_replica.side_effect = make_error("boom replica")

        await worker.process(_replica_to_pipeline_item(replica))

        # Both remain registered as far as the gateway is concerned, since we
        # failed to remove them - only the unregister bookkeeping changes.
        dangling_registration = (
            await session.execute(
                select(ServiceRegistrationModel).where(
                    ServiceRegistrationModel.run_id == dangling_run.id,
                    ServiceRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert dangling_registration.is_registered is True
        assert dangling_registration.unregister_attempt == 1
        assert dangling_registration.unregister_status_message == expected_service_status_message

        stale_replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == stale_job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert stale_replica_registration.is_registered is True
        assert stale_replica_registration.unregister_attempt == 1
        assert (
            stale_replica_registration.unregister_status_message == expected_replica_status_message
        )

        events = await list_events(session)
        assert {e.message for e in events} == {
            (
                f"Encountered service unregistration error on gateway replica "
                f"{replica.replica_num}: {expected_service_status_message}"
            ),
            (
                f"Encountered service replica unregistration error on gateway replica "
                f"{replica.replica_num}: {expected_replica_status_message}"
            ),
        }

    async def test_does_not_emit_duplicate_unregistration_error_event_for_unchanged_error(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        mock_gateway_connection: AsyncMock,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
        )
        run, job = await self._create_service_run_and_job(
            session, project, repo, user, gateway, run_name="live-service"
        )
        stale_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATED,
            registered=False,
            replica_num=1,
        )
        _lock_replica(replica)
        await session.commit()

        client_mock = _get_client_mock(mock_gateway_connection)
        client_mock.list_services.return_value = [
            ServiceListItem(
                id=run.id.hex,
                project_name=project.name,
                run_name="live-service",
                replicas=[
                    ServiceListReplicaItem(id=job.id.hex),
                    ServiceListReplicaItem(id=stale_job.id.hex),
                ],
            ),
        ]
        client_mock.unregister_replica.side_effect = GatewayError("boom replica")

        # First tick: unregistering the stale replica fails, recording the error
        # and emitting one error event.
        await worker.process(_replica_to_pipeline_item(replica))

        replica_registration = (
            await session.execute(
                select(ServiceReplicaRegistrationModel).where(
                    ServiceReplicaRegistrationModel.job_id == stale_job.id,
                    ServiceReplicaRegistrationModel.gateway_replica_id == replica.id,
                )
            )
        ).scalar_one()
        assert replica_registration.unregister_attempt == 1
        assert replica_registration.unregister_status_message == "boom replica"

        error_message = (
            f"Encountered service replica unregistration error on gateway replica "
            f"{replica.replica_num}: boom replica"
        )
        events_after_first_tick = await list_events(session)
        assert [e.message for e in events_after_first_tick].count(error_message) == 1

        # Second tick: unregistering fails again with the exact same error.
        # `unregister_attempt` keeps incrementing, but no duplicate event is
        # emitted since nothing new happened from the user's perspective.
        await session.refresh(replica)
        _lock_replica(replica)
        await session.commit()
        await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica_registration)
        assert replica_registration.unregister_attempt == 2
        assert replica_registration.unregister_status_message == "boom replica"

        events_after_second_tick = await list_events(session)
        assert [e.message for e in events_after_second_tick].count(error_message) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerProvisioning:
    @pytest.mark.parametrize("legacy_replica", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_provisioning_to_running(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        legacy_replica: bool,
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
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
                populate_configuration=populate_configuration,
            )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
        ) as pool_add:
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            await worker.process(_replica_to_pipeline_item(replica))
            pool_add.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.RUNNING
        assert replica.active is True

    async def test_provisioning_to_running_registers_with_load_balancer(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname="gateway-lb.example.com",
            backend_data="lb-backend-data",
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.PROVISIONING,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
            ) as pool_add,
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
        ):
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            register_mock = (
                backend_mock.compute.return_value.register_gateway_replica_with_load_balancer
            )
            register_mock.assert_called_once()
            call_args = register_mock.call_args.args
            assert call_args[0] == replica.instance_id
            assert call_args[1].gateway_name == gateway.name
            assert call_args[2] == "lb-backend-data"

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.RUNNING
        assert replica.active is True

    async def test_provisioning_skips_load_balancer_registration_without_hostname(
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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.PROVISIONING,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
            ) as pool_add,
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
        ):
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())

            await worker.process(_replica_to_pipeline_item(replica))

            get_backends_mock.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.RUNNING
        assert replica.active is True

    async def test_provisioning_to_terminating_when_load_balancer_registration_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname="gateway-lb.example.com",
            backend_data="lb-backend-data",
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.PROVISIONING,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
            ) as pool_add,
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
        ):
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.register_gateway_replica_with_load_balancer.side_effect = Exception(
                "boom"
            )
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False
        assert replica.status_message == "Error registering with load balancer"

    async def test_provisioning_to_terminating_when_backend_does_not_support_load_balancer(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname="gateway-lb.example.com",
            backend_data="lb-backend-data",
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.PROVISIONING,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
            ) as pool_add,
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
        ):
            pool_add.return_value = MagicMock()
            pool_add.return_value.client.return_value = MagicMock(AsyncContextManager())
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeWithGatewaySupport)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False
        assert replica.status_message == "Backend does not support load balancer operations"

    async def test_provisioning_waits_for_pending_acm_gateway_migration(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname=None,  # migration not yet performed
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.PROVISIONING,
            hostname_deprecated_readonly="legacy-lb.example.com",
        )
        _lock_replica(replica)
        original_last_processed_at = replica.last_processed_at
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
        ) as pool_add:
            await worker.process(_replica_to_pipeline_item(replica))
            pool_add.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.PROVISIONING
        assert replica.last_processed_at > original_last_processed_at
        assert replica.lock_token is None

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_provisioning_to_terminating_if_connect_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_replica: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.gateways.connect_to_gateway_replica_with_retry"
        ) as connect_mock:
            connect_mock.return_value = None
            await worker.process(_replica_to_pipeline_item(replica))
            connect_mock.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False
        assert replica.status_message == "Failed to connect to gateway replica"

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_provisioning_to_terminating_if_configure_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_replica: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.PROVISIONING,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.gateways.connect_to_gateway_replica_with_retry"
            ) as connect_mock,
            patch(
                "dstack._internal.server.services.gateways.configure_gateway_replica"
            ) as configure_mock,
        ):
            connect_mock.return_value = MagicMock()
            configure_mock.side_effect = Exception("Configure failed")
            await worker.process(_replica_to_pipeline_item(replica))
            connect_mock.assert_called_once()
            configure_mock.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False
        assert replica.status_message == "Failed to configure gateway replica"

    @pytest.mark.parametrize(
        "gateway_status,to_be_deleted",
        [
            (GatewayStatus.FAILED, False),
            (GatewayStatus.RUNNING, True),
        ],
    )
    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_provisioning_to_terminating_if_gateway_needs_cleanup(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        gateway_status: GatewayStatus,
        to_be_deleted: bool,
        legacy_replica: bool,
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
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                status=GatewayReplicaStatus.PROVISIONING,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                status=GatewayReplicaStatus.PROVISIONING,
            )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.gateway_replicas._connect_and_configure_gateway_replica"
        ) as connect_mock:
            await worker.process(_replica_to_pipeline_item(replica))
            connect_mock.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.active is False


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestGatewayReplicaWorkerTerminating:
    @pytest.mark.parametrize("legacy_replica", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_terminating_to_terminated(
        self,
        test_db,
        session: AsyncSession,
        worker: GatewayReplicaWorker,
        legacy_replica: bool,
        populate_configuration: bool,
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
            populate_configuration=populate_configuration,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
                populate_configuration=populate_configuration,
            )
        _lock_replica(replica)
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

            await worker.process(_replica_to_pipeline_item(replica))

            get_backends_mock.assert_called_once()
            backend_mock.compute.return_value.terminate_gateway_replica.assert_called_once()
            remove_mock.assert_called_once_with(replica.ip_address)

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

    async def test_terminating_to_terminated_deletes_only_own_registration_records(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
        )
        replica_to_terminate = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
            replica_num=0,
        )
        other_replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.RUNNING,
            ip_address="2.2.2.2",
            instance_id="i-eeeeeeeeee",
            replica_num=1,
        )
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)
        terminated_service_registration = ServiceRegistrationModel(
            run_id=run.id, gateway_replica_id=replica_to_terminate.id, is_registered=True
        )
        terminated_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job.id, gateway_replica_id=replica_to_terminate.id, is_registered=True
        )
        other_service_registration = ServiceRegistrationModel(
            run_id=run.id, gateway_replica_id=other_replica.id, is_registered=True
        )
        other_replica_registration = ServiceReplicaRegistrationModel(
            job_id=job.id, gateway_replica_id=other_replica.id, is_registered=True
        )
        session.add_all(
            [
                terminated_service_registration,
                terminated_replica_registration,
                other_service_registration,
                other_replica_registration,
            ]
        )
        _lock_replica(replica_to_terminate)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ),
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica_to_terminate))

        await session.refresh(replica_to_terminate)
        assert replica_to_terminate.status == GatewayReplicaStatus.TERMINATED
        assert replica_to_terminate.deleted is True

        remaining_service_registration = (
            (await session.execute(select(ServiceRegistrationModel))).scalars().one()
        )
        assert remaining_service_registration.gateway_replica_id == other_replica.id
        remaining_replica_registration = (
            (await session.execute(select(ServiceReplicaRegistrationModel))).scalars().one()
        )
        assert remaining_replica_registration.gateway_replica_id == other_replica.id

    async def test_terminating_deregisters_from_load_balancer_before_terminating(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname="gateway-lb.example.com",
            backend_data="lb-backend-data",
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ),
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            deregister_mock = (
                backend_mock.compute.return_value.deregister_gateway_replica_from_load_balancer
            )
            deregister_mock.assert_called_once()
            call_args = deregister_mock.call_args.args
            assert call_args[0] == replica.instance_id
            assert call_args[1].gateway_name == gateway.name
            assert call_args[2] == "lb-backend-data"
            backend_mock.compute.return_value.terminate_gateway_replica.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

    async def test_terminating_proceeds_when_load_balancer_deregistration_raises(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname="gateway-lb.example.com",
            backend_data="lb-backend-data",
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ),
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.deregister_gateway_replica_from_load_balancer.side_effect = Exception(
                "boom"
            )
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            backend_mock.compute.return_value.terminate_gateway_replica.assert_called_once()
            deregister_mock = (
                backend_mock.compute.return_value.deregister_gateway_replica_from_load_balancer
            )
            deregister_mock.assert_called_once()

        await session.refresh(replica)
        # Deregistration failures do not block termination: the load balancer is expected
        # to eventually deregister the (now-terminated) target automatically.
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

    async def test_terminating_skips_deregistration_when_gateway_has_no_hostname(
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
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
        )
        _lock_replica(replica)
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends_with_models"
            ) as get_backends_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.gateway_replicas.gateway_connections_pool.remove"
            ),
        ):
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            backend_mock.compute.return_value.deregister_gateway_replica_from_load_balancer.assert_not_called()
            backend_mock.compute.return_value.terminate_gateway_replica.assert_called_once()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED

    async def test_terminating_waits_for_pending_acm_gateway_migration(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.RUNNING,
            certificate=ACMGatewayCertificate(arn="arn:aws:acm:us:1:certificate/x"),
            hostname=None,  # migration not yet performed by the gateway pipeline
        )
        replica = await create_gateway_replica(
            session=session,
            gateway_id=gateway.id,
            backend_id=backend.id,
            status=GatewayReplicaStatus.TERMINATING,
            active=False,
            hostname_deprecated_readonly="legacy-lb.example.com",
        )
        _lock_replica(replica)
        original_last_processed_at = replica.last_processed_at
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as get_backends_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            backend_mock.compute.return_value.terminate_gateway_replica.assert_not_called()
            backend_mock.compute.return_value.deregister_gateway_replica_from_load_balancer.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.last_processed_at > original_last_processed_at
        assert replica.lock_token is None

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_terminating_to_terminated_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_replica: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_replica(replica)
        await session.commit()

        with patch(
            "dstack._internal.server.services.backends.get_project_backends_with_models"
        ) as get_backends_mock:
            get_backends_mock.return_value = []
            await worker.process(_replica_to_pipeline_item(replica))

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_terminating_to_terminated_with_no_instance_id(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_replica: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                backend_id=backend.id,
                instance_id=None,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                instance_id=None,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_replica(replica)
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

            await worker.process(_replica_to_pipeline_item(replica))

            backend_mock.compute.return_value.terminate_gateway_replica.assert_not_called()
            remove_mock.assert_not_called()

        await session.refresh(replica)
        assert replica.status == GatewayReplicaStatus.TERMINATED
        assert replica.active is False
        assert replica.deleted is True

    @pytest.mark.parametrize("legacy_replica", [False, True])
    async def test_terminating_retries_if_terminate_fails(
        self, test_db, session: AsyncSession, worker: GatewayReplicaWorker, legacy_replica: bool
    ):
        project = await create_project(session=session)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            status=GatewayStatus.FAILED,
        )
        if legacy_replica:
            replica = await create_gateway_replica(
                session=session,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
            gateway.gateway_replica_id = replica.id
        else:
            replica = await create_gateway_replica(
                session=session,
                gateway_id=gateway.id,
                backend_id=backend.id,
                status=GatewayReplicaStatus.TERMINATING,
                active=False,
            )
        _lock_replica(replica)
        original_last_processed_at = replica.last_processed_at
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
            backend_mock.compute.return_value.terminate_gateway_replica.side_effect = Exception(
                "Terminate failed"
            )
            get_backends_mock.return_value = [(backend, backend_mock)]

            await worker.process(_replica_to_pipeline_item(replica))

            get_backends_mock.assert_called_once()
            backend_mock.compute.return_value.terminate_gateway_replica.assert_called_once()
            remove_mock.assert_not_called()

        await session.refresh(replica)
        # Not TERMINATED, should retry termination
        assert replica.status == GatewayReplicaStatus.TERMINATING
        assert replica.last_processed_at > original_last_processed_at
        assert replica.lock_token is None
        assert replica.lock_expires_at is None
        assert replica.lock_owner is None
