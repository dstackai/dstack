import datetime as dt
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional
from unittest.mock import Mock, patch

import gpuhunt
import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    BackendError,
    NoCapacityError,
    NotYetTerminated,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import InstanceGroupPlacement
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobStatus,
)
from dstack._internal.server.background.tasks.process_instances import (
    HealthStatus,
    process_instances,
)
from dstack._internal.server.models import PlacementGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_fleet_configuration,
    get_fleet_spec,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_placement_group_provisioning_data,
    get_remote_connection_info,
)
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")


class TestCheckShim:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_transitions_provisioning_on_ready(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        instance.termination_deadline = get_current_datetime() + dt.timedelta(days=1)
        instance.health_status = "ssh connect problem"

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None
        assert instance.health_status is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_transitions_provisioning_on_terminating(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        instance.started_at = get_current_datetime() + dt.timedelta(minutes=-20)
        instance.health_status = "ssh connect problem"

        await session.commit()

        health_reason = "Shim problem"

        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=False, reason=health_reason)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline is not None
        assert instance.health_status == health_reason

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_transitions_provisioning_on_busy(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
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
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        instance.termination_deadline = get_current_datetime().replace(
            tzinfo=dt.timezone.utc
        ) + dt.timedelta(days=1)
        instance.health_status = "ssh connect problem"

        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            instance=instance,
        )

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)
        await session.refresh(job)

        assert instance is not None
        assert instance.status == InstanceStatus.BUSY
        assert instance.termination_deadline is None
        assert instance.health_status is None
        assert job.instance == instance

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_start_termination_deadline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        health_status = "SSH connection fail"
        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=False, reason=health_status)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is not None
        assert instance.termination_deadline.replace(
            tzinfo=dt.timezone.utc
        ) > get_current_datetime() + dt.timedelta(minutes=19)
        assert instance.health_status == health_status

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_stop_termination_deadline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        instance.termination_deadline = get_current_datetime() + dt.timedelta(minutes=19)
        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None
        assert instance.health_status is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_terminate_instance_by_dedaline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        termination_deadline_time = get_current_datetime() + dt.timedelta(minutes=-19)
        instance.termination_deadline = termination_deadline_time
        await session.commit()

        health_status = "Not ok"
        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=False, reason=health_status)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATING
        assert (
            instance.termination_deadline.replace(tzinfo=dt.timezone.utc)
            == termination_deadline_time
        )
        assert instance.termination_reason == "Termination deadline"
        assert instance.health_status == health_status

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ["termination_policy", "has_job"],
        [
            pytest.param(TerminationPolicy.DESTROY_AFTER_IDLE, False, id="destroy-no-job"),
            pytest.param(TerminationPolicy.DESTROY_AFTER_IDLE, True, id="destroy-with-job"),
            pytest.param(TerminationPolicy.DONT_DESTROY, False, id="dont-destroy-no-job"),
            pytest.param(TerminationPolicy.DONT_DESTROY, True, id="dont-destroy-with-job"),
        ],
    )
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_process_ureachable_state(
        self,
        test_db,
        session: AsyncSession,
        termination_policy: TerminationPolicy,
        has_job: bool,
    ):
        # see https://github.com/dstackai/dstack/issues/2041
        project = await create_project(session=session)
        if has_job:
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
                status=JobStatus.SUBMITTED,
            )
        else:
            job = None
        instance = await create_instance(
            session=session,
            project=project,
            created_at=get_current_datetime(),
            termination_policy=termination_policy,
            status=InstanceStatus.IDLE,
            unreachable=True,
            job=job,
        )

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert not instance.unreachable


class TestTerminateIdleTime:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate_by_idle_timeout(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.IDLE
        )
        instance.termination_idle_time = 300
        instance.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()
        await process_instances()
        await session.refresh(instance)
        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "Idle timeout"


class TestSSHInstanceTerminateProvisionTimeoutExpired:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate_by_idle_timeout(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime() - dt.timedelta(days=100),
        )
        instance.remote_connection_info = "{}"
        await session.commit()

        await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "Provisioning timeout expired"


class TestTerminate:
    @staticmethod
    @contextmanager
    def mock_terminate_in_backend(error: Optional[Exception] = None):
        backend = Mock()
        backend.TYPE = BackendType.DATACRUNCH
        terminate_instance = backend.compute.return_value.terminate_instance
        if error is not None:
            terminate_instance.side_effect = error
        with patch(
            "dstack._internal.server.background.tasks.process_instances.backends_services.get_project_backend_by_type"
        ) as get_backend:
            get_backend.return_value = backend
            yield terminate_instance

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.TERMINATING
        )
        reason = "some reason"
        instance.termination_reason = reason
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await process_instances()
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "some reason"
        assert instance.deleted == True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "error", [BackendError("err"), RuntimeError("err"), NotYetTerminated("")]
    )
    async def test_terminate_retry(self, test_db, session: AsyncSession, error: Exception):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.TERMINATING
        )
        instance.termination_reason = "some reason"
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        await session.commit()

        # First attempt fails
        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=error) as mock,
        ):
            await process_instances()
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        # Second attempt succeeds
        with (
            freeze_time(initial_time + dt.timedelta(minutes=2)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instances()
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate_not_retries_if_too_early(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.TERMINATING
        )
        instance.termination_reason = "some reason"
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        await session.commit()

        # First attempt fails
        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await process_instances()
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        # 3 seconds later - too early for the second attempt, nothing happens
        with (
            freeze_time(initial_time + dt.timedelta(minutes=1, seconds=3)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instances()
            mock.assert_not_called()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate_on_termination_deadline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.TERMINATING
        )
        instance.termination_reason = "some reason"
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        await session.commit()

        # First attempt fails
        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await process_instances()
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        # Second attempt fails too, but it's the last attempt because the deadline is close
        with (
            freeze_time(initial_time + dt.timedelta(minutes=15, seconds=55)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instances()
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db")
class TestCreateInstance:
    @pytest.mark.parametrize(
        # requested_blocks = None means `auto` (as many as possible)
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            # GPU instances
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            # CPU instances
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="gpu-instance-auto-max-cpu"),
        ],
    )
    async def test_creates_instance(
        self,
        session: AsyncSession,
        cpus: int,
        gpus: int,
        requested_blocks: Optional[int],
        expected_blocks: int,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            total_blocks=requested_blocks,
            busy_blocks=0,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            gpu = Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA)
            offer = InstanceOfferWithAvailability(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(
                        cpus=cpus, memory_mib=131072, spot=False, gpus=[gpu] * gpus
                    ),
                ),
                region="us",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.get_offers_cached.return_value = [offer]
            backend_mock.compute.return_value.create_instance.return_value = JobProvisioningData(
                backend=offer.backend,
                instance_type=offer.instance,
                instance_id="instance_id",
                hostname="1.1.1.1",
                internal_ip=None,
                region=offer.region,
                price=offer.price,
                username="ubuntu",
                ssh_port=22,
                ssh_proxy=None,
                dockerized=True,
                backend_data=None,
            )

            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_tries_second_offer_if_first_fails(self, session: AsyncSession, err: Exception):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.PENDING
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers_cached.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        gcp_mock = Mock()
        gcp_mock.TYPE = BackendType.GCP
        offer = get_instance_offer_with_availability(backend=BackendType.GCP, price=2.0)
        gcp_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        gcp_mock.compute.return_value.get_offers_cached.return_value = [offer]
        gcp_mock.compute.return_value.create_instance.return_value = get_job_provisioning_data(
            backend=offer.backend, region=offer.region, price=offer.price
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock, gcp_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        aws_mock.compute.return_value.create_instance.assert_called_once()
        assert instance.backend == BackendType.GCP

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_fails_if_all_offers_fail(self, session: AsyncSession, err: Exception):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.PENDING
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers_cached.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "All offers failed"

    async def test_fails_if_no_offers(self, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.PENDING
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "No offers found"

    @pytest.mark.parametrize(
        ("placement", "expected_termination_reasons"),
        [
            pytest.param(
                InstanceGroupPlacement.CLUSTER,
                {"No offers found": 1, "Master instance failed to start": 3},
                id="cluster",
            ),
            pytest.param(
                None,
                {"No offers found": 4},
                id="non-cluster",
            ),
        ],
    )
    async def test_terminates_cluster_instances_if_master_not_created(
        self,
        session: AsyncSession,
        placement: Optional[InstanceGroupPlacement],
        expected_termination_reasons: dict[str, int],
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(conf=get_fleet_configuration(placement=placement, nodes=4)),
        )
        instances = [
            await create_instance(
                session=session,
                project=project,
                fleet=fleet,
                status=InstanceStatus.PENDING,
                backend=None,
                region=None,
                offer=None,
                job_provisioning_data=None,
            )
            for _ in range(4)
        ]
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            for _ in range(4):
                await process_instances()

        termination_reasons = defaultdict(int)
        for instance in instances:
            await session.refresh(instance)
            assert instance.status == InstanceStatus.TERMINATED
            termination_reasons[instance.termination_reason] += 1
        assert termination_reasons == expected_termination_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db")
class TestPlacementGroups:
    @pytest.mark.parametrize(
        ("placement", "should_create"),
        [
            pytest.param(InstanceGroupPlacement.CLUSTER, True, id="placement-cluster"),
            pytest.param(None, False, id="no-placement"),
        ],
    )
    async def test_create_placement_group_if_placement_cluster(
        self,
        session: AsyncSession,
        placement: Optional[InstanceGroupPlacement],
        should_create: bool,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(conf=get_fleet_configuration(placement=placement, nodes=1)),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            backend=None,
            region=None,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers_cached.return_value = [
            get_instance_offer_with_availability()
        ]
        backend_mock.compute.return_value.create_instance.return_value = (
            get_job_provisioning_data()
        )
        backend_mock.compute.return_value.create_placement_group.return_value = (
            get_placement_group_provisioning_data()
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        if should_create:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 1
            assert len(placement_groups) == 1
        else:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 0
            assert len(placement_groups) == 0

    @pytest.mark.parametrize("can_reuse", [True, False])
    async def test_reuses_placement_group_between_offers_if_the_group_is_suitable(
        self, session: AsyncSession, can_reuse: bool
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(placement=InstanceGroupPlacement.CLUSTER, nodes=1)
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            backend=None,
            region=None,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers_cached.return_value = [
            get_instance_offer_with_availability(instance_type="bad-offer-1"),
            get_instance_offer_with_availability(instance_type="bad-offer-2"),
            get_instance_offer_with_availability(instance_type="good-offer"),
        ]

        def create_instance_method(
            instance_offer: InstanceOfferWithAvailability, *args, **kwargs
        ) -> JobProvisioningData:
            if instance_offer.instance.name == "good-offer":
                return get_job_provisioning_data()
            raise NoCapacityError()

        backend_mock.compute.return_value.create_instance = create_instance_method
        backend_mock.compute.return_value.create_placement_group.return_value = (
            get_placement_group_provisioning_data()
        )
        backend_mock.compute.return_value.is_suitable_placement_group.return_value = can_reuse
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        if can_reuse:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 1
            assert len(placement_groups) == 1
        else:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 3
            assert len(placement_groups) == 3
            to_be_deleted_count = sum(pg.fleet_deleted for pg in placement_groups)
            assert to_be_deleted_count == 2

    @pytest.mark.parametrize("err", [NoCapacityError(), RuntimeError()])
    async def test_handles_create_placement_group_errors(
        self, session: AsyncSession, err: Exception
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(placement=InstanceGroupPlacement.CLUSTER, nodes=1)
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            backend=None,
            region=None,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers_cached.return_value = [
            get_instance_offer_with_availability(instance_type="bad-offer"),
            get_instance_offer_with_availability(instance_type="good-offer"),
        ]
        backend_mock.compute.return_value.create_instance.return_value = (
            get_job_provisioning_data()
        )

        def create_placement_group_method(
            placement_group: PlacementGroup, master_instance_offer: InstanceOffer
        ) -> PlacementGroupProvisioningData:
            if master_instance_offer.instance.name == "good-offer":
                return get_job_provisioning_data()
            raise err

        backend_mock.compute.return_value.create_placement_group = create_placement_group_method
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert "good-offer" in instance.offer
        assert "bad-offer" not in instance.offer
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        assert len(placement_groups) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "deploy_instance_mock")
class TestAddSSHInstance:
    @pytest.fixture
    def host_info(self) -> dict:
        return {
            "gpu_vendor": "nvidia",
            "gpu_name": "T4",
            "gpu_memory": 16384,
            "gpu_count": 1,
            "addresses": ["192.168.100.100/24"],
            "disk_size": 260976517120,
            "cpus": 32,
            "memory": 33544130560,
        }

    @pytest.fixture
    def deploy_instance_mock(self, monkeypatch: pytest.MonkeyPatch, host_info: dict):
        mock = Mock(return_value=(HealthStatus(healthy=True, reason="OK"), host_info, "amd64"))
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances._deploy_instance", mock
        )
        return mock

    @pytest.mark.parametrize(
        # requested_blocks = None means `auto` (as many as possible)
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            # GPU instances
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            # CPU instances
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="gpu-instance-auto-max-cpu"),
        ],
    )
    @pytest.mark.usefixtures("deploy_instance_mock")
    async def test_adds_ssh_instance(
        self,
        session: AsyncSession,
        host_info: dict,
        cpus: int,
        gpus: int,
        requested_blocks: Optional[int],
        expected_blocks: int,
    ):
        host_info["cpus"] = cpus
        host_info["gpu_count"] = gpus
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            total_blocks=requested_blocks,
            busy_blocks=0,
        )
        await session.commit()

        await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.IDLE
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0
