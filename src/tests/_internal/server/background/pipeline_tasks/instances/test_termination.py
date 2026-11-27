import datetime as dt
from contextlib import contextmanager
from typing import Optional, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
import time_machine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    BackendError,
    NotYetTerminated,
    SSHError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import OrphanCleanupMode
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.background.pipeline_tasks.instances import (
    termination as instances_termination,
)
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    VolumeAttachmentModel,
)
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_instance,
    create_project,
    create_user,
    create_volume,
    get_job_provisioning_data,
    get_volume_configuration,
    list_events,
    mock_lease,
)
from tests._internal.server.background.pipeline_tasks.instances.helpers import (
    instance_to_pipeline_item,
    lock_instance,
    process_instance,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestTermination:
    @staticmethod
    @contextmanager
    def mock_terminate_in_backend(error: Optional[Exception] = None):
        backend = Mock()
        backend.TYPE = BackendType.VERDA
        terminate_instance = backend.compute.return_value.terminate_instance
        if error is not None:
            terminate_instance.side_effect = error
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend),
        ):
            yield terminate_instance

    async def test_terminate(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            minutes=-19
        )
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await process_instance(session, worker, instance)
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT
        assert instance.deleted is True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None

    async def test_terminate_wakes_fleet(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        await session.commit()

        with self.mock_terminate_in_backend():
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        await session.refresh(fleet)
        assert instance.deleted is True
        assert fleet.skip_min_processing_interval
        cast(Mock, worker._pipeline_hinter.hint_fetch).assert_called_with(FleetModel.__name__)

    async def test_terminates_terminating_deleted_instance(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        lock_instance(instance)
        await session.commit()
        item = instance_to_pipeline_item(instance)
        instance.deleted = True
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = instance.deleted_at = dt.datetime.now(
            dt.timezone.utc
        ) + dt.timedelta(minutes=-19)
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await worker.process(item)
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.deleted is True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None

    @pytest.mark.parametrize(
        "error",
        [
            BackendError("err"),
            RuntimeError("err"),
            NotYetTerminated(""),
        ],
    )
    async def test_terminate_retry(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        error: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=1), tick=False),
            self.mock_terminate_in_backend(error=error) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=2), tick=False),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    async def test_terminate_not_retries_if_too_early(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=1), tick=False),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        instance.last_processed_at = initial_time
        await session.commit()

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=1, seconds=11), tick=False),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_not_called()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

    async def test_terminate_on_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=1), tick=False),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=15, seconds=55), tick=False),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    async def test_flushes_and_releases_vm_volume_attachments(
        self, test_db, session: AsyncSession, worker: InstanceWorker
    ):
        project = await create_project(session)
        user = await create_user(session)
        volume = await create_volume(session, project, user)
        other_volume = await create_volume(
            session, project, user, configuration=get_volume_configuration(name="other")
        )
        jpd = get_job_provisioning_data(backend=BackendType.MASSEDCOMPUTE)
        jpd.volume_mounts = {volume.id: "/persistent/checkpoints"}
        instance = await create_instance(
            session,
            project,
            status=InstanceStatus.TERMINATING,
            volumes=[volume, other_volume],
            job_provisioning_data=jpd,
        )
        now = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.first_termination_retry_at = now - dt.timedelta(minutes=16)
        instance.last_termination_retry_at = instance.first_termination_retry_at
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        await session.commit()

        compute = Mock(spec=ComputeMockSpec)
        compute.get_volume_mounts_to_sync.side_effect = [
            ["/persistent/checkpoints"],
            ["/persistent/checkpoints"],
            None,
        ]
        compute.terminate_instance.side_effect = NotYetTerminated("Deletion submitted")
        backend = Mock()
        backend.compute.return_value = compute
        conn = AsyncMock()
        conn.sync_volume_mounts.side_effect = [SSHError("flush failed"), None]
        with (
            patch(
                "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
                mock_lease(backend),
            ),
            patch.object(
                instances_termination.instance_connection_pool, "get_or_open", return_value=conn
            ),
        ):
            with time_machine.travel(now, tick=False):
                await process_instance(session, worker, instance)
            compute.terminate_instance.assert_not_called()
            await session.refresh(instance)
            assert instance.status == InstanceStatus.TERMINATING
            attachment = select(VolumeAttachmentModel.volume_id).where(
                VolumeAttachmentModel.instance_id == instance.id
            )
            assert set(await session.scalars(attachment)) == {volume.id, other_volume.id}
            assert any(
                "Volume attachments retained" in e.message for e in await list_events(session)
            )
            with time_machine.travel(now + dt.timedelta(minutes=1), tick=False):
                await process_instance(session, worker, instance)
            compute.terminate_instance.assert_called_once()
            with time_machine.travel(now + dt.timedelta(minutes=2), tick=False):
                await process_instance(session, worker, instance)
            compute.terminate_instance.assert_called_once()
            assert conn.sync_volume_mounts.await_count == 2
            assert list(await session.scalars(attachment)) == [other_volume.id]
            await session.refresh(instance)
            assert instance.status == InstanceStatus.TERMINATED

    async def test_emits_event_if_all_termination_attempts_failed(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=1), tick=False),
            self.mock_terminate_in_backend(error=BackendError("err")),
        ):
            await process_instance(session, worker, instance)
        assert not any("Failed all attempts" in e.message for e in await list_events(session))

        with (
            time_machine.travel(initial_time + dt.timedelta(minutes=15, seconds=55), tick=False),
            self.mock_terminate_in_backend(error=BackendError("quota exceeded")),
        ):
            await process_instance(session, worker, instance)
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        messages = [e.message for e in await list_events(session)]
        assert any(
            "Failed all attempts to terminate instance in the backend" in m
            and "quota exceeded" in m
            for m in messages
        )


class TestIsDeletedByOrphanCleanup:
    @pytest.mark.parametrize(
        ("mode", "provider_ref", "backend", "expected"),
        [
            (OrphanCleanupMode.DELETE, "abc123def456", BackendType.AWS, True),
            (OrphanCleanupMode.REPORT, "abc123def456", BackendType.AWS, False),
            (OrphanCleanupMode.OFF, "abc123def456", BackendType.AWS, False),
            (OrphanCleanupMode.DELETE, None, BackendType.AWS, False),
            (OrphanCleanupMode.DELETE, "abc123def456", BackendType.LAMBDA, False),
        ],
    )
    def test_is_deleted_by_orphan_cleanup(
        self,
        mode: OrphanCleanupMode,
        provider_ref: Optional[str],
        backend: BackendType,
        expected: bool,
    ):
        instance = InstanceModel(provider_ref=provider_ref)
        job_provisioning_data = get_job_provisioning_data(backend=backend)
        with patch.object(settings, "ORPHAN_CLEANUP_MODE", mode):
            assert (
                instances_termination._is_to_be_deleted_by_orphan_cleanup(
                    instance, job_provisioning_data
                )
                == expected
            )
