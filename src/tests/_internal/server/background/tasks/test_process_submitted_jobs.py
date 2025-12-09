from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceStatus,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
)
from dstack._internal.core.models.volumes import (
    InstanceMountPoint,
    VolumeAttachmentData,
    VolumeMountPoint,
    VolumeStatus,
)
from dstack._internal.server.background.tasks.process_submitted_jobs import (
    _prepare_job_runtime_data,
    process_submitted_jobs,
)
from dstack._internal.server.models import (
    ComputeGroupModel,
    InstanceModel,
    JobModel,
    PlacementGroupModel,
    VolumeAttachmentModel,
)
from dstack._internal.server.settings import JobNetworkMode
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_instance,
    create_job,
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
    get_volume_provisioning_data,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


class TestProcessSubmittedJobs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ["backend", "privileged"],
        [
            [BackendType.AWS, False],
            [BackendType.AWS, True],
            [BackendType.RUNPOD, False],
        ],
    )
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisions_job(
        self,
        test_db,
        session: AsyncSession,
        backend: BackendType,
        privileged: bool,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.privileged = privileged
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability(
            backend=backend,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = backend
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_job_when_privileged_true_and_no_offers_with_create_instance_support(
        self,
        test_db,
        session: AsyncSession,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.privileged = True
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability(
            backend=BackendType.RUNPOD,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.RUNPOD
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
                datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
                await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_not_called()
            backend_mock.compute.return_value.run_job.assert_not_called()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_job_when_instance_mounts_and_no_offers_with_create_instance_support(
        self,
        test_db,
        session: AsyncSession,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.volumes = [InstanceMountPoint.parse("/root/.cache:/cache")]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability(
            backend=BackendType.RUNPOD,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.RUNPOD
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
                datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
                await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_not_called()
            backend_mock.compute.return_value.run_job.assert_not_called()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisions_job_with_optional_instance_volume_not_attached(
        self,
        test_db,
        session: AsyncSession,
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.volumes = [
            InstanceMountPoint(instance_path="/root/.cache", path="/cache", optional=True)
        ]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability(
            backend=BackendType.RUNPOD,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.RUNPOD
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            await process_submitted_jobs()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_job_when_no_capacity(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                profile=Profile(
                    name="default",
                ),
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=datetime(2023, 1, 2, 3, 0, 0, tzinfo=timezone.utc),
            instance_assigned=True,
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
            await process_submitted_jobs()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assignes_job_to_instance(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.SUBMITTED
        assert (
            job.instance_assigned and job.instance is not None and job.instance.id == instance.id
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_does_no_reuse_unavailable_instances(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        fleet = await create_fleet(session=session, project=project)
        # busy
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.BUSY,
        )
        # unreachable
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            unreachable=True,
        )
        # fatal health issue
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            health_status=HealthStatus.FAILURE,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )

        await process_submitted_jobs()

        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_instance_with_volumes(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
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
            status=InstanceStatus.IDLE,
            backend=BackendType.AWS,
            region="us-east-1",
        )
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run_spec.configuration.volumes = [
            VolumeMountPoint(name=volume.name, path="/volume"),
            InstanceMountPoint(instance_path="/root/.data", path="/data"),
            InstanceMountPoint(instance_path="/root/.cache", path="/cache", optional=True),
        ]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )

        with patch("dstack._internal.server.services.backends.get_project_backend_by_type") as m:
            backend_mock = Mock()
            m.return_value = backend_mock
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.attach_volume.return_value = VolumeAttachmentData()
            # Submitted jobs processing happens in two steps
            await process_submitted_jobs()
            await process_submitted_jobs()

        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(
            select(JobModel).options(
                joinedload(JobModel.instance)
                .joinedload(InstanceModel.volume_attachments)
                .joinedload(VolumeAttachmentModel.volume)
            )
        )
        job = res.unique().scalar_one()
        assert job.status == JobStatus.PROVISIONING
        assert (
            job.instance_assigned and job.instance is not None and job.instance.id == instance.id
        )
        assert job.instance.volume_attachments[0].volume == volume

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_shared_instance(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        offer = get_instance_offer_with_availability(gpu_count=8, cpu_count=64, memory_gib=128)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.blocks = 4
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            offer=offer,
            total_blocks=4,
            busy_blocks=1,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.SUBMITTED
        assert (
            job.instance_assigned and job.instance is not None and job.instance.id == instance.id
        )
        assert instance.total_blocks == 4
        assert instance.busy_blocks == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_multi_node_job_to_shared_instance(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        offer = get_instance_offer_with_availability(gpu_count=8, cpu_count=64, memory_gib=128)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            backend=BackendType.AWS,
            offer=offer,
            total_blocks=4,
            busy_blocks=0,
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
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance is not None
        assert job.instance.id == instance.id
        assert instance.total_blocks == 4
        assert instance.busy_blocks == 4

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_cannot_assign_multi_node_job_to_partially_busy_shared_instance(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        offer = get_instance_offer_with_availability(gpu_count=8, cpu_count=64, memory_gib=128)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
            backend=BackendType.AWS,
            offer=offer,
            total_blocks=4,
            busy_blocks=1,
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
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        await session.refresh(instance)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        assert instance.total_blocks == 4
        assert instance.busy_blocks == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_specific_fleet(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_a = await create_fleet(session=session, project=project, name="a")
        await create_instance(session=session, project=project, fleet=fleet_a, price=1.0)
        fleet_b = await create_fleet(session=session, project=project, name="b")
        await create_instance(session=session, project=project, fleet=fleet_b, price=2.0)
        fleet_c = await create_fleet(session=session, project=project, name="c")
        await create_instance(session=session, project=project, fleet=fleet_c, price=3.0)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        # When more than one fleet is requested, the cheapest one is selected
        run_spec.configuration.fleets = ["c", "b"]
        run = await create_run(
            session=session, project=project, repo=repo, user=user, run_spec=run_spec
        )
        job = await create_job(session=session, run=run)

        await process_submitted_jobs()

        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.SUBMITTED
        assert job.instance is not None
        assert job.instance.fleet == fleet_b

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_new_instance_in_existing_non_empty_fleet(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=2)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=0,
            status=InstanceStatus.BUSY,
        )
        fleet.instances.append(instance)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        run.fleet = fleet
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        await session.commit()

        offer = get_instance_offer_with_availability(
            backend=BackendType.AWS,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()

        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None
        assert job.instance.instance_num == 1
        assert job.instance.fleet_id == fleet.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_fails_if_run_cannot_fit_into_fleet(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=3)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        instance1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=0,
            status=InstanceStatus.BUSY,
            busy_blocks=1,
        )
        instance2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=1,
            status=InstanceStatus.IDLE,
            busy_blocks=0,
        )
        fleet.instances.append(instance1)
        fleet.instances.append(instance2)
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration = TaskConfiguration(nodes=3, commands=["echo"])
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await session.commit()
        await process_submitted_jobs()
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        assert job.instance_id is None
        assert job.fleet_id is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_elastic_empty_fleet_with_backend_offers_if_fleets_unspecified(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec1 = get_fleet_spec()
        fleet_spec1.configuration.nodes = FleetNodesSpec(min=0, target=0, max=1)
        fleet1 = await create_fleet(
            session=session, project=project, spec=fleet_spec1, name="fleet"
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock]
            await process_submitted_jobs()
        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.instance_id is None
        assert job.fleet_id == fleet1.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_elastic_empty_fleet_if_fleets_specified(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=1)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec, name="fleet")
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.fleets = [fleet.name]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job.instance_assigned
        assert job.instance_id is None
        assert job.fleet_id == fleet.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_elastic_non_empty_busy_fleet_if_fleets_specified(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=1, target=1, max=2)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec, name="fleet")
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=0,
            status=InstanceStatus.BUSY,
            total_blocks=1,
            busy_blocks=1,
        )
        run_spec = get_run_spec(repo_id=repo.name)
        run_spec.configuration.fleets = [fleet.name]
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job.instance_assigned
        assert job.instance_id is None
        assert job.fleet_id == fleet.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_new_instance_in_existing_empty_fleet(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=1)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            fleet=fleet,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability(
            backend=BackendType.AWS,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()

        await session.refresh(job)
        res = await session.execute(select(JobModel).options(joinedload(JobModel.instance)))
        job = res.unique().scalar_one()
        assert job.status == JobStatus.PROVISIONING
        assert job.instance is not None
        assert job.instance.instance_num == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_assigns_job_to_optimal_fleet(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet1 = await create_fleet(session=session, project=project)
        fleet2 = await create_fleet(session=session, project=project)
        fleet3 = await create_fleet(session=session, project=project)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet1,
            instance_num=0,
            status=InstanceStatus.BUSY,
            price=1,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet2,
            instance_num=0,
            status=InstanceStatus.IDLE,
            price=2,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet3,
            instance_num=0,
            status=InstanceStatus.IDLE,
            price=3,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job.status == JobStatus.SUBMITTED
        assert job.instance_assigned
        assert job.fleet_id == fleet2.id

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_picks_high_priority_jobs_first(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        run1 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            priority=10,
        )
        job1 = await create_job(
            session=session,
            run=run1,
            instance_assigned=True,
            instance=instance,
        )
        run2 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            priority=0,
        )
        job2 = await create_job(
            session=session, run=run2, instance_assigned=True, instance=instance
        )
        run3 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            priority=100,
        )
        job3 = await create_job(
            session=session,
            run=run3,
            instance_assigned=True,
            instance=instance,
        )
        await process_submitted_jobs()
        await session.refresh(job3)
        assert job3.status == JobStatus.PROVISIONING
        await process_submitted_jobs()
        await session.refresh(job1)
        assert job1.status == JobStatus.PROVISIONING
        await process_submitted_jobs()
        await session.refresh(job2)
        assert job2.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisions_compute_group(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        run_name = "test-run"
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name=run_name,
        )
        run_spec.configuration = TaskConfiguration(nodes=2, commands=["echo"])
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name=run_name,
            run_spec=run_spec,
        )
        job1 = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
            job_num=0,
            status=JobStatus.SUBMITTED,
            waiting_master_job=False,
        )
        job2 = await create_job(
            session=session,
            run=run,
            instance_assigned=False,
            job_num=1,
            status=JobStatus.SUBMITTED,
            waiting_master_job=True,
        )
        offer = get_instance_offer_with_availability(
            backend=BackendType.RUNPOD,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.RUNPOD
            compute_mock.get_offers.return_value = [offer]
            jpds = [
                get_job_provisioning_data(),
                get_job_provisioning_data(),
            ]
            compute_mock.run_jobs.return_value = get_compute_group_provisioning_data(
                job_provisioning_datas=jpds
            )
            await process_submitted_jobs()
            m.assert_called_once()
            compute_mock.get_offers.assert_called_once()
            compute_mock.run_jobs.assert_called_once()
        await session.refresh(job1)
        await session.refresh(job2)
        assert job1.status == JobStatus.PROVISIONING
        assert job2.status == JobStatus.PROVISIONING
        res = await session.execute(select(ComputeGroupModel))
        assert res.scalar() is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisioning_master_job_respects_cluster_placement_in_non_empty_fleet(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session)
        user = await create_user(session)
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
        )
        job = await create_job(
            session=session,
            run=run,
            fleet=fleet,
            instance_assigned=True,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            offer1 = get_instance_offer_with_availability(region="eu-west-2")
            offer2 = get_instance_offer_with_availability(region="eu-west-1")
            backend_mock.compute.return_value.get_offers.return_value = [offer1, offer2]
            backend_mock.compute.return_value.run_job.return_value = get_job_provisioning_data()
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()
            selected_offer = backend_mock.compute.return_value.run_job.call_args[0][2]
            assert selected_offer.region == "eu-west-1"
        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_placement_group(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=None)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            fleet=fleet,
            run_name="test-run",
            run_spec=run_spec,
        )
        job = await create_job(
            session=session,
            run=run,
            instance_assigned=True,
        )
        offer = get_instance_offer_with_availability()
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            backend_mock.TYPE = BackendType.AWS
            compute_mock = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value = compute_mock
            m.return_value = [backend_mock]
            compute_mock.get_offers.return_value = [offer]
            compute_mock.run_job.return_value = get_job_provisioning_data()
            compute_mock.create_placement_group.return_value = (
                get_placement_group_provisioning_data()
            )
            await process_submitted_jobs()
            m.assert_called_once()
            compute_mock.get_offers.assert_called_once()
            compute_mock.run_job.assert_called_once()
            compute_mock.create_placement_group.assert_called_once()
            pg_arg = compute_mock.run_job.call_args[0][6]
            assert isinstance(pg_arg, PlacementGroup)
        placement_group = (await session.execute(select(PlacementGroupModel))).scalar()
        assert placement_group is not None
        await session.refresh(job)
        assert job.status == JobStatus.PROVISIONING


@pytest.mark.parametrize(
    ["job_network_mode", "blocks", "multinode", "network_mode", "constraints_are_set"],
    [
        pytest.param(
            JobNetworkMode.HOST_FOR_MULTINODE_ONLY,
            2,
            False,
            NetworkMode.BRIDGE,
            True,
            id="host-for-multinode-only--half-of-instance",
        ),
        pytest.param(
            JobNetworkMode.HOST_FOR_MULTINODE_ONLY,
            4,
            False,
            NetworkMode.BRIDGE,
            False,
            id="host-for-multinode-only--entire-instance",
        ),
        pytest.param(
            JobNetworkMode.HOST_FOR_MULTINODE_ONLY,
            4,
            True,
            NetworkMode.HOST,
            False,
            id="host-for-multinode-only--entire-instance--multinode",
        ),
        pytest.param(
            JobNetworkMode.HOST_WHEN_POSSIBLE,
            2,
            False,
            NetworkMode.BRIDGE,
            True,
            id="host-when-possible--half-of-instance",
        ),
        pytest.param(
            JobNetworkMode.HOST_WHEN_POSSIBLE,
            4,
            False,
            NetworkMode.HOST,
            False,
            id="host-when-possible--entire-instance",
        ),
        pytest.param(
            JobNetworkMode.HOST_WHEN_POSSIBLE,
            4,
            True,
            NetworkMode.HOST,
            False,
            id="host-when-possible--entire-instance--multinode",
        ),
        pytest.param(
            JobNetworkMode.FORCED_BRIDGE,
            2,
            False,
            NetworkMode.BRIDGE,
            True,
            id="forced-bridge--half-of-instance",
        ),
        pytest.param(
            JobNetworkMode.FORCED_BRIDGE,
            4,
            False,
            NetworkMode.BRIDGE,
            False,
            id="forced-bridge--entire-instance",
        ),
        pytest.param(
            JobNetworkMode.FORCED_BRIDGE,
            4,
            True,
            NetworkMode.BRIDGE,
            False,
            id="forced-bridge--entire-instance--multinode",
        ),
    ],
)
def test_prepare_job_runtime_data(
    monkeypatch: pytest.MonkeyPatch,
    job_network_mode: JobNetworkMode,
    blocks: int,
    multinode: bool,
    network_mode: NetworkMode,
    constraints_are_set: bool,
):
    monkeypatch.setattr("dstack._internal.server.settings.JOB_NETWORK_MODE", job_network_mode)
    offer = get_instance_offer_with_availability(blocks=blocks, total_blocks=4)
    jrd = _prepare_job_runtime_data(offer=offer, multinode=multinode)
    assert jrd.network_mode == network_mode
    if constraints_are_set:
        assert jrd.gpu is not None
        assert jrd.cpu is not None
        assert jrd.memory is not None
    else:
        assert jrd.gpu is None
        assert jrd.cpu is None
        assert jrd.memory is None
