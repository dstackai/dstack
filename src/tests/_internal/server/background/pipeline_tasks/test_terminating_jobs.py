import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.background.pipeline_tasks.jobs_terminating import (
    JobTerminatingFetcher,
    JobTerminatingPipeline,
    JobTerminatingPipelineItem,
    JobTerminatingWorker,
    _get_related_instance_lock_owner,
)
from dstack._internal.server.models import InstanceModel, JobModel, VolumeAttachmentModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_volume,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_volume_configuration,
    get_volume_provisioning_data,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime


@pytest.fixture
def worker() -> JobTerminatingWorker:
    return JobTerminatingWorker(queue=Mock(), heartbeater=Mock())


@pytest.fixture
def fetcher() -> JobTerminatingFetcher:
    return JobTerminatingFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=15),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


def _job_to_pipeline_item(job_model: JobModel) -> JobTerminatingPipelineItem:
    assert job_model.lock_token is not None
    assert job_model.lock_expires_at is not None
    return JobTerminatingPipelineItem(
        __tablename__=job_model.__tablename__,
        id=job_model.id,
        lock_token=job_model.lock_token,
        lock_expires_at=job_model.lock_expires_at,
        prev_lock_expired=False,
        volumes_detached_at=job_model.volumes_detached_at,
    )


def _lock_job(job_model: JobModel):
    job_model.lock_token = uuid.uuid4()
    job_model.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
    job_model.lock_owner = JobTerminatingPipeline.__name__


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestJobTerminatingFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobTerminatingFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        terminating = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=2),
        )
        past_remove_at = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=1),
        )
        past_remove_at.remove_at = stale
        past_remove_at.volumes_detached_at = stale - timedelta(seconds=30)

        future_remove_at = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale,
        )
        future_remove_at.remove_at = now + timedelta(minutes=1)

        non_terminating = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale,
        )

        recent = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=now,
        )

        locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale + timedelta(seconds=1),
        )
        locked.lock_expires_at = now + timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"

        expired_same_owner = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale + timedelta(seconds=2),
        )
        expired_same_owner.lock_expires_at = stale
        expired_same_owner.lock_token = uuid.uuid4()
        expired_same_owner.lock_owner = JobTerminatingPipeline.__name__
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            terminating.id,
            past_remove_at.id,
            expired_same_owner.id,
        ]
        assert {(item.id, item.volumes_detached_at) for item in items} == {
            (terminating.id, None),
            (past_remove_at.id, past_remove_at.volumes_detached_at),
            (expired_same_owner.id, None),
        }

        for job in [
            terminating,
            past_remove_at,
            future_remove_at,
            non_terminating,
            recent,
            locked,
            expired_same_owner,
        ]:
            await session.refresh(job)

        fetched_jobs = [terminating, past_remove_at, expired_same_owner]
        assert all(job.lock_owner == JobTerminatingPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert future_remove_at.lock_owner is None
        assert non_terminating.lock_owner is None
        assert recent.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_returns_oldest_jobs_first_up_to_limit(
        self, test_db, session: AsyncSession, fetcher: JobTerminatingFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()

        oldest = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=5),
            last_processed_at=now - timedelta(minutes=3),
        )
        middle = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=4),
            last_processed_at=now - timedelta(minutes=2),
        )
        newest = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            submitted_at=now - timedelta(minutes=3),
            last_processed_at=now - timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == JobTerminatingPipeline.__name__
        assert middle.lock_owner == JobTerminatingPipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock")
class TestJobTerminatingWorker:
    async def test_terminates_job(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job_provisioning_data = get_job_provisioning_data(dockerized=True)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
            instance=instance,
        )
        _lock_job(job)
        await session.commit()

        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch("dstack._internal.server.services.runner.client.ShimClient") as ShimClientMock,
        ):
            shim_client_mock = ShimClientMock.return_value
            await worker.process(_job_to_pipeline_item(job))
            SSHTunnelMock.assert_called_once()
            shim_client_mock.healthcheck.assert_called_once()

        await session.refresh(job)
        await session.refresh(instance)
        assert job.status == JobStatus.TERMINATED
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert instance.lock_token is None
        assert instance.lock_owner is None

        events = await list_events(session)
        assert any(
            event.message == "Job status changed TERMINATING -> TERMINATED" for event in events
        )

    async def test_detaches_job_volumes(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            volumes=[volume],
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
            instance=instance,
        )
        _lock_job(job)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.jobs_terminating.backends_services.get_project_backend_by_type"
        ) as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.is_volume_detached.return_value = True
            await worker.process(_job_to_pipeline_item(job))
            m.assert_awaited_once()
            backend_mock.compute.return_value.detach_volume.assert_called_once()
            backend_mock.compute.return_value.is_volume_detached.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATED
        await session.refresh(volume)
        assert volume.last_job_processed_at is not None

    async def test_force_detaches_job_volumes(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            volumes=[volume],
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
            instance=instance,
        )
        _lock_job(job)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.jobs_terminating.backends_services.get_project_backend_by_type"
        ) as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.is_volume_detached.return_value = False
            await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.TERMINATING
        assert job.instance is None
        assert job.volumes_detached_at is not None

        _lock_job(job)
        await session.commit()
        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_terminating.backends_services.get_project_backend_by_type"
            ) as m,
            patch(
                "dstack._internal.server.background.pipeline_tasks.jobs_terminating.get_current_datetime"
            ) as datetime_mock,
        ):
            datetime_mock.return_value = job.volumes_detached_at.replace(
                tzinfo=timezone.utc
            ) + timedelta(minutes=30)
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.is_volume_detached.return_value = False
            await worker.process(_job_to_pipeline_item(job))
            backend_mock.compute.return_value.detach_volume.assert_called_once()
            detach_kwargs = backend_mock.compute.return_value.detach_volume.call_args.kwargs
            assert detach_kwargs["force"] is True
            assert detach_kwargs["volume"].id == volume.id
            assert (
                detach_kwargs["provisioning_data"].instance_id == job_provisioning_data.instance_id
            )
            backend_mock.compute.return_value.is_volume_detached.assert_called_once()

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING

        _lock_job(job)
        await session.commit()
        with patch(
            "dstack._internal.server.background.pipeline_tasks.jobs_terminating.backends_services.get_project_backend_by_type"
        ) as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.is_volume_detached.return_value = True
            await worker.process(_job_to_pipeline_item(job))
            backend_mock.compute.return_value.is_volume_detached.assert_called_once()

        await session.refresh(job)
        await session.refresh(instance, ["volume_attachments"])
        res = await session.execute(
            select(InstanceModel)
            .where(InstanceModel.id == instance.id)
            .options(joinedload(InstanceModel.volume_attachments))
            .execution_options(populate_existing=True)
        )
        instance = res.unique().scalar_one()
        assert job.status == JobStatus.TERMINATED
        assert len(instance.volume_attachments) == 0

    async def test_terminates_job_on_shared_instance(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            total_blocks=4,
            busy_blocks=3,
        )
        run = await create_run(session=session, project=project, repo=repo, user=user)
        shared_offer = get_instance_offer_with_availability(blocks=2, total_blocks=4)
        jrd = get_job_runtime_data(offer=shared_offer)
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
            instance=instance,
            job_runtime_data=jrd,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
        )
        _lock_job(job)
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.TERMINATED
        assert job.instance_assigned
        assert job.instance is None
        assert instance.busy_blocks == 1

    async def test_detaches_job_volumes_on_shared_instance(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        volume_conf_1 = get_volume_configuration(name="vol-1")
        volume_1 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_conf_1,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        volume_conf_2 = get_volume_configuration(name="vol-2")
        volume_2 = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            backend=BackendType.AWS,
            configuration=volume_conf_2,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            volumes=[volume_1, volume_2],
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job_provisioning_data = get_job_provisioning_data(dockerized=False)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            submitted_at=datetime(2023, 1, 2, 5, 12, 30, 5, tzinfo=timezone.utc),
            job_provisioning_data=job_provisioning_data,
            job_runtime_data=get_job_runtime_data(volume_names=["vol-1"]),
            instance=instance,
        )
        _lock_job(job)
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.jobs_terminating.backends_services.get_project_backend_by_type"
        ) as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.is_volume_detached.return_value = True

            await worker.process(_job_to_pipeline_item(job))

            backend_mock.compute.return_value.detach_volume.assert_called_once()
            backend_mock.compute.return_value.is_volume_detached.assert_called_once()

        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(
            select(InstanceModel).options(
                joinedload(InstanceModel.volume_attachments).joinedload(
                    VolumeAttachmentModel.volume
                )
            )
        )
        instance = res.unique().scalar_one()
        assert job.status == JobStatus.TERMINATED
        assert len(instance.volume_attachments) == 1
        assert instance.volume_attachments[0].volume == volume_2

    async def test_resets_job_for_retry_if_related_instance_is_locked(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        instance.lock_owner = "OtherPipeline"
        instance.lock_token = uuid.uuid4()
        instance.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            instance=instance,
        )
        _lock_job(job)
        last_processed_before = job.last_processed_at
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner == JobTerminatingPipeline.__name__
        assert job.last_processed_at > last_processed_before

    async def test_resets_job_for_retry_if_related_instance_is_locked_by_another_job(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        other_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            instance=instance,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            instance=instance,
        )
        instance.lock_owner = _get_related_instance_lock_owner(other_job.id)
        instance.lock_token = uuid.uuid4()
        instance.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
        _lock_job(job)
        last_processed_before = job.last_processed_at
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        await session.refresh(instance)
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner == JobTerminatingPipeline.__name__
        assert job.last_processed_at > last_processed_before
        assert instance.lock_owner == _get_related_instance_lock_owner(other_job.id)

    async def test_finishes_job_when_used_instance_is_not_set(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
        )
        _lock_job(job)
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATED
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_retries_detaching_when_used_instance_is_missing(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
        )
        job.instance_id = None
        job.used_instance_id = uuid.uuid4()
        job.volumes_detached_at = get_current_datetime()
        _lock_job(job)
        last_processed_before = job.last_processed_at
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner == JobTerminatingPipeline.__name__
        assert job.last_processed_at > last_processed_before

    async def test_retries_terminating_when_used_instance_is_missing(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
        )
        job.used_instance_id = uuid.uuid4()
        _lock_job(job)
        last_processed_before = job.last_processed_at
        await session.commit()

        await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert job.lock_owner == JobTerminatingPipeline.__name__
        assert job.last_processed_at > last_processed_before

    async def test_keeps_related_instance_locked_on_processing_exception(
        self, test_db, session: AsyncSession, worker: JobTerminatingWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.TERMINATED_BY_USER,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
            instance=instance,
        )
        _lock_job(job)
        job_lock_token = job.lock_token
        await session.commit()

        with patch(
            "dstack._internal.server.background.pipeline_tasks.jobs_terminating._process_terminating_job",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                await worker.process(_job_to_pipeline_item(job))

        await session.refresh(job)
        await session.refresh(instance)
        assert job.lock_token == job_lock_token
        assert job.lock_owner == JobTerminatingPipeline.__name__
        assert instance.lock_token == job_lock_token
        assert instance.lock_owner == _get_related_instance_lock_owner(job.id)
