import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    BackendError,
    VolumeDeletionPending,
    VolumeProvisioningError,
    VolumeProvisioningPending,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.volumes import (
    MassedComputeVolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.server.background.pipeline_tasks import volumes as volumes_pipeline
from dstack._internal.server.background.pipeline_tasks.volumes import (
    VolumeFetcher,
    VolumePipeline,
    VolumePipelineItem,
    VolumeWorker,
)
from dstack._internal.server.models import VolumeModel
from dstack._internal.server.services.volumes import delete_volumes
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_project,
    create_user,
    create_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
    list_events,
    mock_lease,
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

        backend_mock = Mock()
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend_mock),
        ) as get_backend_mock:
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.return_value = VolumeProvisioningData(
                backend=BackendType.AWS,
                volume_id="vol-1234",
                size_gb=100,
            )

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

        backend_mock = Mock()
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend_mock),
        ) as get_backend_mock:
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.register_volume.return_value = (
                VolumeProvisioningData(
                    backend=BackendType.AWS,
                    volume_id="vol-external-123",
                    size_gb=100,
                )
            )

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
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(None),
        ) as get_backend_mock:
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

        backend_mock = Mock()
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend_mock),
        ) as get_backend_mock:
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.create_volume.side_effect = BackendError(
                "Some error"
            )

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.create_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.status == VolumeStatus.FAILED
        assert volume.status_message == "Some error"
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume status changed SUBMITTED -> FAILED (Some error)"

    @pytest.mark.parametrize("external", [False, True])
    async def test_reconciles_massedcompute_volume_until_ready(
        self,
        test_db,
        session: AsyncSession,
        worker: VolumeWorker,
        fetcher: VolumeFetcher,
        external,
    ):
        volume_id = str(uuid.uuid4())
        volume = await create_volume(
            session,
            await create_project(session),
            await create_user(session),
            configuration=MassedComputeVolumeConfiguration(
                name="data", volume_id=volume_id if external else None
            ),
        )
        ready = VolumeProvisioningData(
            backend=BackendType.MASSEDCOMPUTE,
            volume_id=volume_id,
            size_gb=None,
            attachable=False,
            detachable=False,
        )
        compute = Mock(spec=ComputeMockSpec)
        provision = compute.register_volume if external else compute.create_volume
        provision.side_effect = [
            VolumeProvisioningPending("Storage creating", volume_id),
            VolumeProvisioningPending("Storage status unavailable"),
            ready,
        ]
        backend = Mock()
        backend.compute.return_value = compute
        with (
            patch.object(
                volumes_pipeline.backends_cache,
                "lease_project_backend_by_type",
                mock_lease(backend),
            ),
            time_machine.travel(get_current_datetime(), tick=False) as clock,
        ):
            for message in ("Storage creating", "Storage status unavailable"):
                (item,) = await fetcher.fetch(1)
                await worker.process(item)
                await session.refresh(volume)
                assert volume.status == (
                    VolumeStatus.SUBMITTED if external else VolumeStatus.PROVISIONING
                )
                assert volume.status_message == message
                assert volume.lock_token is None
                assert volume.volume_provisioning_data is not None
                assert (
                    VolumeProvisioningData.model_validate_json(
                        volume.volume_provisioning_data
                    ).volume_id
                    == volume_id
                )
                await session.commit()
                clock.shift(timedelta(seconds=16))

            (item,) = await fetcher.fetch(1)
            await worker.process(item)

        assert provision.call_args.kwargs["volume"].volume_id == volume_id
        await session.refresh(volume)
        assert volume.status == VolumeStatus.ACTIVE
        assert volume.status_message is None
        assert volume.volume_provisioning_data == ready.model_dump_json()
        assert [event.message for event in await list_events(session)] == (
            ["Volume status changed SUBMITTED -> ACTIVE"]
            if external
            else [
                "Volume status changed SUBMITTED -> PROVISIONING",
                "Volume status changed PROVISIONING -> ACTIVE",
            ]
        )

    @pytest.mark.parametrize(
        ("lost_first_reply", "allocated_id", "expected_status"),
        [
            (False, None, VolumeStatus.FAILED),
            (True, None, VolumeStatus.PROVISIONING),
            (False, "allocated-id", VolumeStatus.FAILED),
        ],
    )
    async def test_deletes_after_massedcompute_create_error(
        self,
        test_db,
        session: AsyncSession,
        worker: VolumeWorker,
        fetcher: VolumeFetcher,
        lost_first_reply: bool,
        allocated_id: str | None,
        expected_status: VolumeStatus,
    ):
        project = await create_project(session)
        user = await create_user(session)
        volume = await create_volume(
            session, project, user, configuration=MassedComputeVolumeConfiguration(name="data")
        )
        backend = Mock()
        compute = backend.compute.return_value = Mock(spec=ComputeMockSpec)
        errors: list[BackendError] = [VolumeProvisioningError("Create failed", allocated_id)]
        if lost_first_reply:
            errors.insert(0, VolumeProvisioningPending("Lost reply"))
        compute.create_volume.side_effect = errors
        with (
            patch.object(
                volumes_pipeline.backends_cache,
                "lease_project_backend_by_type",
                mock_lease(backend),
            ),
            time_machine.travel(get_current_datetime(), tick=False) as clock,
        ):
            for _ in errors:
                (item,) = await fetcher.fetch(1)
                await worker.process(item)
                clock.shift(timedelta(seconds=16))
            assert [
                call.kwargs["volume"].status for call in compute.create_volume.call_args_list
            ] == (
                [VolumeStatus.SUBMITTED, VolumeStatus.PROVISIONING]
                if lost_first_reply
                else [VolumeStatus.SUBMITTED]
            )
            await session.refresh(volume)
            assert volume.status == expected_status
            assert volume.status_message == "Create failed"
            await delete_volumes(session, project, [volume.name], user)

            if lost_first_reply:
                # This rejection applies only to the retry. Reconcile the original
                # request by name and commit its recovered ID before deleting it.
                compute.delete_volume.side_effect = [
                    VolumeDeletionPending("Found volume", "recovered-id"),
                    None,
                ]
                (item,) = await fetcher.fetch(1)
                await worker.process(item)
                await session.refresh(volume)
                assert not volume.deleted
                assert compute.delete_volume.call_args.kwargs["volume"].volume_id is None
                await session.commit()
                clock.shift(timedelta(seconds=16))

            (item,) = await fetcher.fetch(1)
            await worker.process(item)

        await session.refresh(volume)
        assert volume.deleted
        if allocated_id or lost_first_reply:
            assert compute.delete_volume.call_args.kwargs["volume"].volume_id == (
                allocated_id or "recovered-id"
            )
        else:
            compute.delete_volume.assert_not_called()

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
    @pytest.mark.parametrize(
        ("status", "external_id"),
        [(VolumeStatus.SUBMITTED, None), (VolumeStatus.ACTIVE, "external-id")],
    )
    async def test_deletes_unsubmitted_or_external_massedcompute_volume_locally(
        self,
        test_db,
        session: AsyncSession,
        worker: VolumeWorker,
        fetcher: VolumeFetcher,
        status,
        external_id,
    ):
        volume = await create_volume(
            session,
            await create_project(session),
            await create_user(session),
            configuration=MassedComputeVolumeConfiguration(name="data", volume_id=external_id),
            status=status,
            volume_provisioning_data=(
                VolumeProvisioningData(
                    backend=BackendType.MASSEDCOMPUTE, volume_id=external_id, size_gb=None
                )
                if external_id
                else None
            ),
        )
        volume.to_be_deleted = True
        await session.commit()

        with patch.object(
            volumes_pipeline.backends_cache, "lease_project_backend_by_type"
        ) as lease:
            (item,) = await fetcher.fetch(1)
            await worker.process(item)
            lease.assert_not_called()

        await session.refresh(volume)
        assert volume.deleted
        assert volume.deleted_at is not None
        assert [event.message for event in await list_events(session)] == ["Volume deleted"]

    @pytest.mark.parametrize("volume_id", [None, "known-id"])
    async def test_confirms_massedcompute_deletion_before_forgetting_volume(
        self,
        test_db,
        session: AsyncSession,
        worker: VolumeWorker,
        fetcher: VolumeFetcher,
        volume_id,
    ):
        volume = await create_volume(
            session,
            await create_project(session),
            await create_user(session),
            configuration=MassedComputeVolumeConfiguration(name="data"),
            status=VolumeStatus.PROVISIONING if volume_id is None else VolumeStatus.ACTIVE,
            volume_provisioning_data=(
                VolumeProvisioningData(
                    backend=BackendType.MASSEDCOMPUTE, volume_id=volume_id, size_gb=None
                )
                if volume_id
                else None
            ),
        )
        volume.to_be_deleted = True
        await session.commit()
        backend = Mock()
        compute = Mock(spec=ComputeMockSpec)
        backend.compute.return_value = compute
        compute.delete_volume.side_effect = [
            VolumeDeletionPending("Still deleting", None if volume_id else "recovered-id"),
            RuntimeError("Storage unavailable"),
            None,
        ]

        with time_machine.travel(get_current_datetime(), tick=False) as clock:
            for available_backend in (None, backend, backend):
                with patch.object(
                    volumes_pipeline.backends_cache,
                    "lease_project_backend_by_type",
                    mock_lease(available_backend),
                ):
                    (item,) = await fetcher.fetch(1)
                    await worker.process(item)
                await session.refresh(volume)
                assert volume.to_be_deleted and not volume.deleted
                assert volume.deleted_at is None
                assert volume.status_message
                assert await list_events(session) == []
                await session.commit()
                clock.shift(timedelta(seconds=16))
            with patch.object(
                volumes_pipeline.backends_cache,
                "lease_project_backend_by_type",
                mock_lease(backend),
            ):
                (item,) = await fetcher.fetch(1)
                await worker.process(item)

        requested = compute.delete_volume.call_args.kwargs["volume"]
        assert requested.id == volume.id
        assert requested.volume_id == (volume_id or "recovered-id")
        await session.refresh(volume)
        assert volume.deleted and volume.deleted_at is not None
        assert [event.message for event in await list_events(session)] == ["Volume deleted"]

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

        backend_mock = Mock()
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend_mock),
        ) as get_backend_mock:
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)

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
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type"
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
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(None),
        ) as get_backend_mock:
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

        backend_mock = Mock()
        with patch(
            "dstack._internal.server.services.backends.cache.lease_project_backend_by_type",
            mock_lease(backend_mock),
        ) as get_backend_mock:
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.delete_volume.side_effect = BackendError(
                "Delete failed"
            )

            await worker.process(_volume_to_pipeline_item(volume))

            get_backend_mock.assert_called_once()
            backend_mock.compute.return_value.delete_volume.assert_called_once()

        await session.refresh(volume)
        assert volume.deleted is True
        assert volume.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Volume deleted"
