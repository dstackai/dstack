import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError, BackendNotAvailable
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import VolumeProvisioningData, VolumeStatus
from dstack._internal.server.background.pipeline_tasks import volumes as volumes_pipeline
from dstack._internal.server.background.pipeline_tasks.volumes import (
    VolumeFetcher,
    VolumePipeline,
    VolumePipelineItem,
    VolumeWorker,
)
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_project,
    create_user,
    create_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> VolumeWorker:
    return VolumeWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.fixture
def fetcher() -> VolumeFetcher:
    return VolumeFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _volume_to_pipeline_item(volume_model: VolumeModel) -> VolumePipelineItem:
    assert volume_model.lock_token is not None
    assert volume_model.lock_expires_at is not None
    return VolumePipelineItem(
        __tablename__=volume_model.__tablename__,
        id=volume_model.id,
        lock_token=volume_model.lock_token,
        lock_expires_at=volume_model.lock_expires_at,
        prev_lock_expired=False,
        status=volume_model.status,
        to_be_deleted=volume_model.to_be_deleted,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestVolumeFetcher:
    async def test_fetch_selects_eligible_volumes_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: VolumeFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        submitted = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=2),
        )
        to_be_deleted = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            created_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=1),
        )
        to_be_deleted.to_be_deleted = True

        just_created = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=now,
            last_processed_at=now,
        )

        deleted = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=stale - timedelta(minutes=1),
            last_processed_at=stale,
            deleted_at=stale,
        )
        recent = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=now - timedelta(minutes=2),
            last_processed_at=now,
        )
        locked = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=stale - timedelta(minutes=1),
            last_processed_at=stale + timedelta(seconds=1),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            submitted.id,
            to_be_deleted.id,
            just_created.id,
        }
        assert {(item.id, item.status, item.to_be_deleted) for item in items} == {
            (submitted.id, VolumeStatus.SUBMITTED, False),
            (to_be_deleted.id, VolumeStatus.ACTIVE, True),
            (just_created.id, VolumeStatus.SUBMITTED, False),
        }

        for volume in [submitted, to_be_deleted, just_created, deleted, recent, locked]:
            await session.refresh(volume)

        fetched_volumes = [submitted, to_be_deleted, just_created]
        assert all(volume.lock_owner == VolumePipeline.__name__ for volume in fetched_volumes)
        assert all(volume.lock_expires_at is not None for volume in fetched_volumes)
        assert all(volume.lock_token is not None for volume in fetched_volumes)
        assert len({volume.lock_token for volume in fetched_volumes}) == 1

        assert deleted.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_volumes_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: VolumeFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        now = get_current_datetime()

        oldest = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=now - timedelta(minutes=4),
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=now - timedelta(minutes=3),
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            created_at=now - timedelta(minutes=2),
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == VolumePipeline.__name__
        assert middle.lock_owner == VolumePipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestVolumeWorkerSubmitted:
    async def test_submitted_to_active(self, test_db, session: AsyncSession, worker: VolumeWorker):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.return_value = VolumeProvisioningData(
                backend=BackendType.AWS,
                volume_id="vol-1234",
                size_gb=100,
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_called_once()
            backend_mock.compute.return_value.register_volume.assert_not_called()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
        assert volume.volume_provisioning_data is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> ACTIVE"

    async def test_registers_external_volume(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
            configuration=get_volume_configuration(volume_id="vol-external-123"),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.register_volume.return_value = (
                VolumeProvisioningData(
                    backend=BackendType.AWS,
                    volume_id="vol-external-123",
                    size_gb=100,
                )
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.register_volume.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_not_called()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> ACTIVE"

    async def test_marks_volume_failed_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            get_backend_mock.side_effect = BackendNotAvailable()
            await worker.process(_volume_to_pipeline_item(volume))
            get_backend_mock.assert_called_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Backend not available"
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Volume status changed SUBMITTED -> FAILED (Backend not available)"
        )

    async def test_marks_volume_failed_if_backend_returns_error(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.side_effect = BackendError(
                "Some error"
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Some error"
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> FAILED (Some error)"

    async def test_skips_processing_if_lock_token_changed_before_refetch(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        item = _volume_to_pipeline_item(volume)

        volume.lock_token = uuid.uuid4()
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes._process_submitted_volume"
        ) as process_volume_mock:
            await worker.process(item)
            process_volume_mock.assert_not_awaited()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.SUBMITTED
        events = await list_events(session)
        assert len(events) == 0

    async def test_skips_apply_if_lock_token_changed_after_processing(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.SUBMITTED,
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        await session.commit()

        async def _change_lock_token_and_return_result(_volume_model: VolumeModel):
            volume.lock_token = uuid.uuid4()
            await session.commit()
            return volumes_pipeline._ProcessResult(
                update_map={
                    "status": VolumeStatus.ACTIVE,
                }
            )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes._process_submitted_volume",
            side_effect=_change_lock_token_and_return_result,
        ) as process_volume_mock:
            await worker.process(_volume_to_pipeline_item(volume))
            process_volume_mock.assert_awaited_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.SUBMITTED
        events = await list_events(session)
        assert len(events) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestVolumeWorkerDeleted:
    async def test_marks_volume_deleted(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            volume_provisioning_data=get_volume_provisioning_data(backend=BackendType.AWS),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        volume.to_be_deleted = True
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.delete_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.deleted is True
        assert volume.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume deleted"

    async def test_marks_external_volume_deleted_without_backend_call(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            configuration=get_volume_configuration(volume_id="vol-external-123"),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        volume.to_be_deleted = True
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            await worker.process(_volume_to_pipeline_item(volume))
            get_backend_mock.assert_not_called()

        await session.refresh(volume)
        assert volume.deleted is True
        assert volume.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume deleted"

    async def test_marks_volume_deleted_if_backend_not_available(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            volume_provisioning_data=get_volume_provisioning_data(backend=BackendType.AWS),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        volume.to_be_deleted = True
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            get_backend_mock.side_effect = BackendNotAvailable()
            await worker.process(_volume_to_pipeline_item(volume))
            get_backend_mock.assert_called_once()

        await session.refresh(volume)
        assert volume.deleted is True
        assert volume.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume deleted"

    async def test_marks_volume_deleted_if_backend_delete_errors(
        self, test_db, session: AsyncSession, worker: VolumeWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            volume_provisioning_data=get_volume_provisioning_data(backend=BackendType.AWS),
        )
        volume.lock_token = uuid.uuid4()
        volume.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        volume.to_be_deleted = True
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.volumes.backends_services.get_project_backend_by_type_or_error"
        ) as get_backend_mock:
            backend_mock = Mock()
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.delete_volume.side_effect = BackendError(
                "Delete failed"
            )
            get_backend_mock.return_value = backend_mock

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.delete_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.deleted is True
        assert volume.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume deleted"
