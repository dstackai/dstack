import asyncio
import uuid
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import VolumeMountPoint, VolumeStatus
from dstack._internal.server.background.pipeline_tasks.jobs_submitted import (
    JobSubmittedFetcher,
    JobSubmittedPipeline,
    JobSubmittedPipelineItem,
    JobSubmittedWorker,
)
from dstack._internal.server.models import JobModel
from dstack._internal.server.testing.common import (
    create_export,
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_volume,
    get_fleet_spec,
    get_job_provisioning_data,
    get_run_spec,
    get_ssh_fleet_configuration,
    get_volume_provisioning_data,
)
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")


@pytest.fixture
def fetcher() -> JobSubmittedFetcher:
    return JobSubmittedFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=4),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> JobSubmittedWorker:
    return JobSubmittedWorker(queue=Mock(), heartbeater=Mock())


def _lock_job_foreign(job_model: JobModel) -> None:
    job_model.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = "OtherPipeline"


def _lock_job_expired_same_owner(job_model: JobModel) -> None:
    job_model.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobSubmittedPipeline.__name__


def _lock_job(job_model: JobModel) -> None:
    job_model.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
    job_model.lock_token = uuid.uuid4()
    job_model.lock_owner = JobSubmittedPipeline.__name__


def _job_to_pipeline_item(job_model: JobModel) -> JobSubmittedPipelineItem:
    assert job_model.lock_token is not None
    assert job_model.lock_expires_at is not None
    return JobSubmittedPipelineItem(
        __tablename__=job_model.__tablename__,
        id=job_model.id,
        lock_expires_at=job_model.lock_expires_at,
        lock_token=job_model.lock_token,
        prev_lock_expired=False,
        instance_assigned=job_model.instance_assigned,
    )


async def _process_job(
    session: AsyncSession,
    worker: JobSubmittedWorker,
    job_model: JobModel,
) -> None:
    _lock_job(job_model)
    await session.commit()
    await worker.process(_job_to_pipeline_item(job_model))


async def _get_job(session: AsyncSession, job_id) -> JobModel:
    res = await session.execute(
        select(JobModel)
        .where(JobModel.id == job_id)
        .options(joinedload(JobModel.instance))
        .options(joinedload(JobModel.fleet))
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobSubmittedFetcher:
    async def test_fetch_selects_eligible_jobs_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        assignment_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=2),
            instance_assigned=False,
        )
        provisioning_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=1),
            instance_assigned=True,
            job_num=1,
        )
        fresh_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=now,
            last_processed_at=now,
            job_num=2,
        )
        waiting_master = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=3),
            last_processed_at=stale - timedelta(seconds=3),
            waiting_master_job=True,
            job_num=3,
        )
        recent_retry = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=4),
            last_processed_at=now - timedelta(seconds=1),
            job_num=4,
        )
        foreign_locked = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            submitted_at=stale - timedelta(minutes=5),
            last_processed_at=stale - timedelta(seconds=4),
            job_num=5,
        )
        _lock_job_foreign(foreign_locked)
        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert [item.id for item in items] == [
            assignment_job.id,
            provisioning_job.id,
            fresh_job.id,
        ]
        assert [(item.id, item.instance_assigned) for item in items] == [
            (assignment_job.id, False),
            (provisioning_job.id, True),
            (fresh_job.id, False),
        ]

        for job in [
            assignment_job,
            provisioning_job,
            fresh_job,
            waiting_master,
            recent_retry,
            foreign_locked,
        ]:
            await session.refresh(job)

        fetched_jobs = [assignment_job, provisioning_job, fresh_job]
        assert all(job.lock_owner == JobSubmittedPipeline.__name__ for job in fetched_jobs)
        assert all(job.lock_expires_at is not None for job in fetched_jobs)
        assert all(job.lock_token is not None for job in fetched_jobs)
        assert len({job.lock_token for job in fetched_jobs}) == 1

        assert waiting_master.lock_owner is None
        assert recent_retry.lock_owner is None
        assert foreign_locked.lock_owner == "OtherPipeline"

    async def test_fetch_orders_by_priority_then_last_processed_at(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        now = get_current_datetime()

        low_priority_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="low-priority-run",
            priority=1,
        )
        high_priority_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="high-priority-run",
            priority=10,
        )

        low_priority_job = await create_job(
            session=session,
            run=low_priority_run,
            submitted_at=now - timedelta(minutes=3),
            last_processed_at=now - timedelta(minutes=2),
        )
        newer_high_priority_job = await create_job(
            session=session,
            run=high_priority_run,
            submitted_at=now - timedelta(minutes=4),
            last_processed_at=now - timedelta(minutes=1),
        )
        older_high_priority_job = await create_job(
            session=session,
            run=high_priority_run,
            submitted_at=now - timedelta(minutes=5),
            last_processed_at=now - timedelta(minutes=2, seconds=30),
            job_num=1,
        )

        items = await fetcher.fetch(limit=3)

        assert [item.id for item in items] == [
            older_high_priority_job.id,
            newer_high_priority_job.id,
            low_priority_job.id,
        ]

    async def test_fetch_retries_expired_same_owner_lock_and_respects_limit(
        self, test_db, session: AsyncSession, fetcher: JobSubmittedFetcher
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        now = get_current_datetime()
        stale = now - timedelta(minutes=1)

        oldest = await create_job(
            session=session,
            run=run,
            submitted_at=stale - timedelta(minutes=2),
            last_processed_at=stale - timedelta(seconds=2),
        )
        expired_same_owner = await create_job(
            session=session,
            run=run,
            submitted_at=stale - timedelta(minutes=1),
            last_processed_at=stale - timedelta(seconds=1),
            job_num=1,
        )
        newest = await create_job(
            session=session,
            run=run,
            submitted_at=stale,
            last_processed_at=stale,
            job_num=2,
        )
        _lock_job_expired_same_owner(expired_same_owner)
        await session.commit()

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, expired_same_owner.id]

        await session.refresh(expired_same_owner)
        assert expired_same_owner.lock_owner == JobSubmittedPipeline.__name__
        assert expired_same_owner.lock_token is not None
        assert expired_same_owner.lock_expires_at is not None

        await session.refresh(newest)
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestJobSubmittedWorker:
    async def test_unlocks_assigned_job_stub(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run, instance_assigned=True)
        last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.last_processed_at == last_processed_at
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_ignores_lock_token_mismatch(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)
        _lock_job(job)
        await session.commit()
        item = _job_to_pipeline_item(job)

        job.lock_token = uuid.uuid4()
        await session.commit()

        await worker.process(item)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.lock_token is not None

    async def test_assigns_job_to_instance(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)
        previous_last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        await session.refresh(instance)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance.id
        assert job.used_instance_id == instance.id
        assert job.fleet_id == fleet.id
        assert job.job_provisioning_data == instance.job_provisioning_data
        assert job.job_runtime_data is not None
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert instance.status == InstanceStatus.BUSY
        assert instance.busy_blocks == 1

    async def test_assigns_job_to_imported_fleet(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        exporter_user = await create_user(
            session, name="exporter-user", global_role=GlobalRole.USER
        )
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(
            session, name="exporter-project", owner=exporter_user
        )
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        repo = await create_repo(session=session, project_id=importer_project.id)
        fleet = await create_fleet(
            session=session,
            project=exporter_project,
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        instance = await create_instance(
            session=session,
            project=exporter_project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[fleet],
        )
        run = await create_run(
            session=session,
            project=importer_project,
            repo=repo,
            user=importer_user,
        )
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance.id
        assert job.fleet_id == fleet.id

    async def test_assigns_job_to_specific_fleet(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_1 = await create_fleet(session=session, project=project, name="fleet-1")
        fleet_2 = await create_fleet(session=session, project=project, name="fleet-2")
        await create_instance(
            session=session,
            project=project,
            fleet=fleet_1,
            status=InstanceStatus.IDLE,
            name="fleet-1-instance",
        )
        instance_2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet_2,
            status=InstanceStatus.IDLE,
            name="fleet-2-instance",
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(name="default", fleets=[fleet_2.name]),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance_2.id
        assert job.fleet_id == fleet_2.id

    async def test_defers_job_while_waiting_for_master_provisioning(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration = TaskConfiguration(nodes=2, commands=["echo"])
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        await create_job(
            session=session,
            run=run,
            job_num=0,
            waiting_master_job=False,
        )
        job = await create_job(
            session=session,
            run=run,
            job_num=1,
            waiting_master_job=False,
        )
        previous_last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert not job.instance_assigned
        assert job.instance_id is None
        assert job.fleet_id is None
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_defers_job_while_waiting_for_run_fleet_assignment(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration = TaskConfiguration(nodes=2, commands=["echo"])
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        await create_job(
            session=session,
            run=run,
            job_num=0,
            instance_assigned=True,
            job_provisioning_data=get_job_provisioning_data(),
            waiting_master_job=False,
        )
        job = await create_job(
            session=session,
            run=run,
            job_num=1,
            waiting_master_job=False,
        )
        previous_last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert not job.instance_assigned
        assert job.fleet_id is None
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_terminates_job_when_volume_preparation_fails(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        volume = await create_volume(
            session=session,
            project=project,
            user=user,
            status=VolumeStatus.ACTIVE,
            volume_provisioning_data=get_volume_provisioning_data(),
        )
        volume.to_be_deleted = True
        await session.commit()
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.volumes = [VolumeMountPoint(name=volume.name, path="/volume")]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.VOLUME_ERROR
        assert job.termination_reason_message is not None
        assert "marked for deletion" in job.termination_reason_message
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_terminates_job_when_specified_fleets_cannot_be_used(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            profile=Profile(name="default", fleets=["missing-fleet"]),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        assert job.termination_reason_message == "Failed to use specified fleets"

    async def test_terminates_job_when_no_matching_fleet_and_autocreated_disabled(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        assert job.termination_reason_message is not None
        assert "No matching fleet found" in job.termination_reason_message

    async def test_marks_job_assigned_without_fleet_when_autocreated_enabled(
        self,
        test_db,
        session: AsyncSession,
        worker: JobSubmittedWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(FeatureFlags, "AUTOCREATED_FLEETS_ENABLED", True)
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.fleet_id is None
        assert job.instance_id is None
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_resets_lock_for_retry_when_existing_instance_offer_cannot_be_locked(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        instance.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
        instance.lock_token = uuid.uuid4()
        instance.lock_owner = "OtherPipeline"
        await session.commit()

        run = await create_run(session=session, project=project, repo=repo, user=user)
        job = await create_job(session=session, run=run)
        previous_last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(instance)
        assert job.status == JobStatus.SUBMITTED
        assert not job.instance_assigned
        assert job.instance_id is None
        assert job.used_instance_id is None
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner == JobSubmittedPipeline.__name__
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert instance.status == InstanceStatus.IDLE
        assert instance.busy_blocks == 0
