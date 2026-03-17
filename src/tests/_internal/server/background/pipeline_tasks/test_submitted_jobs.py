import asyncio
import uuid
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import JobStatus, JobTerminationReason
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import (
    VolumeAttachmentData,
    VolumeMountPoint,
    VolumeStatus,
)
from dstack._internal.server.background.pipeline_tasks.jobs_submitted import (
    JobSubmittedFetcher,
    JobSubmittedPipeline,
    JobSubmittedPipelineItem,
    JobSubmittedWorker,
)
from dstack._internal.server.models import (
    ComputeGroupModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    VolumeAttachmentModel,
)
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_export,
    create_fleet,
    create_instance,
    create_job,
    create_placement_group,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_volume,
    get_compute_group_provisioning_data,
    get_fleet_spec,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_placement_group_provisioning_data,
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


async def _get_placement_groups(
    session: AsyncSession,
    fleet_id: uuid.UUID,
) -> list[PlacementGroupModel]:
    res = await session.execute(
        select(PlacementGroupModel)
        .where(PlacementGroupModel.fleet_id == fleet_id)
        .execution_options(populate_existing=True)
    )
    return list(res.scalars().all())


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
        # submitted_at == last_processed_at bypasses the min_processing_interval filter
        # so freshly submitted jobs are picked up immediately
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
    async def test_provisions_assigned_job_on_existing_instance(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            busy_blocks=1,
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            instance_assigned=True,
            job_provisioning_data=get_job_provisioning_data(dockerized=True),
        )
        previous_last_processed_at = job.last_processed_at

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.PROVISIONING
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance.id
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_provisions_new_capacity_for_assigned_job(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
        )
        job = await create_job(session=session, run=run, instance_assigned=True)

        offer = get_instance_offer_with_availability(backend=BackendType.AWS)
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data(
                dockerized=True,
                backend=BackendType.AWS,
            )

            await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None
        assert job.instance.fleet_id == fleet.id
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None

    async def test_provisioning_master_job_respects_cluster_placement_in_non_empty_fleet(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            backend=BackendType.AWS,
            job_provisioning_data=get_job_provisioning_data(region="eu-west-1"),
        )
        configuration = TaskConfiguration(image="debian", nodes=2)
        run_spec = get_run_spec(run_name="run", repo_id=repo.name, configuration=configuration)
        run = await create_run(
            session=session,
            run_name="run",
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
            fleet=fleet,
        )
        job = await create_job(session=session, run=run, instance_assigned=True)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            offer_1 = get_instance_offer_with_availability(
                backend=BackendType.AWS,
                region="eu-west-2",
            )
            offer_2 = get_instance_offer_with_availability(
                backend=BackendType.AWS,
                region="eu-west-1",
            )
            backend_mock.compute.return_value.get_offers.return_value = [offer_1, offer_2]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data(
                backend=BackendType.AWS,
            )

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(fleet)
        assert job.status == JobStatus.PROVISIONING
        assert fleet.lock_owner is None
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        backend_mock.compute.return_value.run_job.assert_called_once()
        selected_offer = backend_mock.compute.return_value.run_job.call_args[0][2]
        assert selected_offer.region == "eu-west-1"

    async def test_creates_placement_group_for_cluster_fleet(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name="test-run",
            run_spec=get_run_spec(run_name="test-run", repo_id=repo.name),
        )
        job = await create_job(session=session, run=run, instance_assigned=True)
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            compute_mock.get_offers.return_value = [offer]
            compute_mock.run_job.return_value = get_job_provisioning_data(
                backend=BackendType.AWS,
            )
            compute_mock.create_placement_group.return_value = (
                get_placement_group_provisioning_data()
            )

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(fleet)
        assert job.status == JobStatus.PROVISIONING
        assert fleet.lock_owner is None
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        compute_mock.create_placement_group.assert_called_once()
        compute_mock.run_job.assert_called_once()
        assert isinstance(compute_mock.run_job.call_args[0][6], PlacementGroup)
        placement_group = (await session.execute(select(PlacementGroupModel))).scalar()
        assert placement_group is not None

    async def test_marks_unused_existing_placement_groups_for_cleanup(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        selected_pg = await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="selected-pg",
        )
        await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="stale-pg",
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name="test-run",
            run_spec=get_run_spec(run_name="test-run", repo_id=repo.name),
        )
        job = await create_job(session=session, run=run, instance_assigned=True)
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            compute_mock.get_offers.return_value = [offer]
            compute_mock.is_suitable_placement_group.side_effect = (
                lambda placement_group, _: placement_group.name == selected_pg.name
            )
            compute_mock.run_job.return_value = get_job_provisioning_data(
                backend=BackendType.AWS,
            )

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING
        placement_groups = await _get_placement_groups(session=session, fleet_id=fleet.id)
        assert {placement_group.name for placement_group in placement_groups} == {
            "selected-pg",
            "stale-pg",
        }
        placement_groups_by_name = {
            placement_group.name: placement_group for placement_group in placement_groups
        }
        assert not placement_groups_by_name["selected-pg"].fleet_deleted
        assert placement_groups_by_name["stale-pg"].fleet_deleted
        compute_mock.create_placement_group.assert_not_called()

    async def test_marks_new_and_existing_placement_groups_for_cleanup_on_failed_provisioning(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_placement_group(
            session=session,
            project=project,
            fleet=fleet,
            name="existing-pg",
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name="test-run",
            run_spec=get_run_spec(run_name="test-run", repo_id=repo.name),
        )
        job = await create_job(session=session, run=run, instance_assigned=True)
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            compute_mock.get_offers.return_value = [offer]
            compute_mock.is_suitable_placement_group.return_value = False
            compute_mock.create_placement_group.return_value = (
                get_placement_group_provisioning_data()
            )
            compute_mock.run_job.side_effect = BackendError("boom")

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        placement_groups = await _get_placement_groups(session=session, fleet_id=fleet.id)
        assert len(placement_groups) == 2
        placement_groups_by_name = {
            placement_group.name: placement_group for placement_group in placement_groups
        }
        assert placement_groups_by_name["existing-pg"].fleet_deleted
        new_placement_groups = [
            placement_group
            for placement_group in placement_groups
            if placement_group.name != "existing-pg"
        ]
        assert len(new_placement_groups) == 1
        assert new_placement_groups[0].fleet_deleted
        compute_mock.create_placement_group.assert_called_once()

    async def test_resets_lock_for_retry_when_cluster_master_fleet_lock_is_unavailable(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        fleet.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
        fleet.lock_token = uuid.uuid4()
        fleet.lock_owner = "OtherPipeline:cluster-master"
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
        )
        job = await create_job(session=session, run=run, instance_assigned=True)
        previous_last_processed_at = job.last_processed_at
        await session.commit()

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            await _process_job(session=session, worker=worker, job_model=job)
            m.assert_not_called()

        await session.refresh(job)
        await session.refresh(fleet)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.last_processed_at > previous_last_processed_at
        assert job.lock_owner == JobSubmittedPipeline.__name__
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert fleet.lock_owner == "OtherPipeline:cluster-master"
        assert fleet.lock_token is not None
        assert fleet.lock_expires_at is not None

    async def test_reclaims_stale_related_cluster_master_fleet_lock(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
        )
        job = await create_job(session=session, run=run, instance_assigned=True)
        fleet.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
        fleet.lock_token = uuid.uuid4()
        fleet.lock_owner = f"{JobSubmittedPipeline.__name__}:{job.id}"
        await session.commit()

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [
                get_instance_offer_with_availability(backend=BackendType.AWS)
            ]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data(
                backend=BackendType.AWS,
            )

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(fleet)
        assert job.status == JobStatus.PROVISIONING
        assert fleet.lock_owner is None
        assert fleet.lock_token is None
        assert fleet.lock_expires_at is None
        backend_mock.compute.return_value.run_job.assert_called_once()

    async def test_processes_assignment_and_provisioning_in_separate_passes(
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

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance.id

        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.PROVISIONING
        assert job.instance_assigned
        assert job.instance is not None and job.instance.id == instance.id

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

    async def test_provisions_compute_group(
        self, test_db, session: AsyncSession, worker: JobSubmittedWorker
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration = TaskConfiguration(nodes=2, commands=["echo"])
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_spec=run_spec,
        )
        job1 = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
            job_num=0,
            waiting_master_job=False,
        )
        job2 = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
            job_num=1,
            waiting_master_job=True,
        )

        offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.get_offers.return_value = [offer]
            compute_mock.run_jobs.return_value = get_compute_group_provisioning_data(
                job_provisioning_datas=[
                    get_job_provisioning_data(dockerized=True, backend=BackendType.RUNPOD),
                    get_job_provisioning_data(dockerized=True, backend=BackendType.RUNPOD),
                ]
            )

            await _process_job(session=session, worker=worker, job_model=job1)

        await session.refresh(job1)
        await session.refresh(job2)
        assert job1.status == JobStatus.PROVISIONING
        assert job2.status == JobStatus.PROVISIONING
        res = await session.execute(select(ComputeGroupModel))
        assert res.scalar_one_or_none() is not None

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
        # lock_owner is intentionally preserved so the fetcher can distinguish
        # an in-progress lock from a reset that came from this pipeline
        assert job.lock_owner == JobSubmittedPipeline.__name__
        assert job.lock_token is None
        assert job.lock_expires_at is None
        assert instance.status == InstanceStatus.IDLE
        assert instance.busy_blocks == 0

    async def test_attaches_volume_on_existing_instance(
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
            backend=BackendType.AWS,
            region="us-east-1",
        )
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            busy_blocks=1,
            backend=BackendType.AWS,
            region="us-east-1",
        )
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.volumes = [VolumeMountPoint(name=volume.name, path="/volume")]
        run = await create_run(
            session=session, project=project, repo=repo, user=user, run_spec=run_spec
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            instance_assigned=True,
        )

        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.attach_volume.return_value = VolumeAttachmentData()

            await _process_job(session=session, worker=worker, job_model=job)

        res = await session.execute(
            select(JobModel)
            .where(JobModel.id == job.id)
            .options(
                joinedload(JobModel.instance)
                .joinedload(InstanceModel.volume_attachments)
                .joinedload(VolumeAttachmentModel.volume)
            )
            .execution_options(populate_existing=True)
        )
        job = res.unique().scalar_one()
        await session.refresh(volume)
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None
        assert len(job.instance.volume_attachments) == 1
        assert job.instance.volume_attachments[0].volume_id == volume.id
        assert volume.lock_owner is None
        assert volume.lock_token is None
        assert volume.lock_expires_at is None
        backend_mock.compute.return_value.attach_volume.assert_called_once()

    async def test_terminates_job_when_volume_is_locked_for_processing(
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
            backend=BackendType.AWS,
            region="us-east-1",
        )
        volume.lock_expires_at = get_current_datetime() + timedelta(minutes=1)
        volume.lock_token = uuid.uuid4()
        volume.lock_owner = "OtherPipeline"
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            busy_blocks=1,
            backend=BackendType.AWS,
            region="us-east-1",
        )
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.volumes = [VolumeMountPoint(name=volume.name, path="/volume")]
        run = await create_run(
            session=session, project=project, repo=repo, user=user, run_spec=run_spec
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            instance_assigned=True,
        )
        await session.commit()

        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(volume)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.VOLUME_ERROR
        assert job.termination_reason_message is not None
        assert "locked for processing" in job.termination_reason_message
        assert volume.lock_owner == "OtherPipeline"
        assert volume.lock_token is not None
        assert volume.lock_expires_at is not None
        backend_mock.compute.return_value.attach_volume.assert_not_called()

    async def test_reclaims_stale_related_volume_lock(
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
            backend=BackendType.AWS,
            region="us-east-1",
        )
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
            busy_blocks=1,
            backend=BackendType.AWS,
            region="us-east-1",
        )
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.volumes = [VolumeMountPoint(name=volume.name, path="/volume")]
        run = await create_run(
            session=session, project=project, repo=repo, user=user, run_spec=run_spec
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            instance_assigned=True,
        )
        volume.lock_expires_at = get_current_datetime() - timedelta(minutes=1)
        volume.lock_token = uuid.uuid4()
        volume.lock_owner = f"{JobSubmittedPipeline.__name__}:{job.id}"
        await session.commit()

        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.attach_volume.return_value = VolumeAttachmentData()

            await _process_job(session=session, worker=worker, job_model=job)

        await session.refresh(job)
        await session.refresh(volume)
        assert job.status == JobStatus.PROVISIONING
        assert volume.lock_owner is None
        assert volume.lock_token is None
        assert volume.lock_expires_at is None
        backend_mock.compute.return_value.attach_volume.assert_called_once()

    async def test_provisions_new_capacity_with_autocreated_fleet(
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

        # First pass: no fleet found, mark instance_assigned=True with no fleet
        await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.fleet_id is None

        # Second pass: provision new capacity and autocreate fleet
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data(
                dockerized=True,
                backend=BackendType.AWS,
            )

            await _process_job(session=session, worker=worker, job_model=job)

        job = await _get_job(session, job.id)
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None
        assert job.fleet_id is not None
        assert job.lock_owner is None
        assert job.lock_token is None
        assert job.lock_expires_at is None
