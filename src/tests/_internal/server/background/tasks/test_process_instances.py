import datetime as dt
import logging
from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from typing import Optional
from unittest.mock import MagicMock, Mock, call, patch

import gpuhunt
import pytest
import pytest_asyncio
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import GoArchType
from dstack._internal.core.errors import (
    BackendError,
    NoCapacityError,
    NotYetTerminated,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import InstanceGroupPlacement
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceTerminationReason,
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
    delete_instance_health_checks,
    process_instances,
)
from dstack._internal.server.models import (
    InstanceHealthCheckModel,
    InstanceModel,
    PlacementGroupModel,
)
from dstack._internal.server.schemas.health.dcgm import DCGMHealthResponse, DCGMHealthResult
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import (
    ComponentInfo,
    ComponentName,
    ComponentStatus,
    HealthcheckResponse,
    InstanceHealthResponse,
    TaskListItem,
    TaskListResponse,
    TaskStatus,
)
from dstack._internal.server.services.runner.client import ComponentList, ShimClient
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_instance,
    create_instance_health_check,
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

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=True)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

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

        await session.commit()

        health_reason = "Shim problem"

        with patch(
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=False, message=health_reason)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline is not None

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

        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.SUBMITTED,
            instance=instance,
        )

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=True)
            await process_instances()

        await session.refresh(instance)
        await session.refresh(job)

        assert instance is not None
        assert instance.status == InstanceStatus.BUSY
        assert instance.termination_deadline is None
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
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=False, message=health_status)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is not None
        assert instance.termination_deadline.replace(
            tzinfo=dt.timezone.utc
        ) > get_current_datetime() + dt.timedelta(minutes=19)

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
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=True)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_terminate_instance_by_deadline(self, test_db, session: AsyncSession):
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
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=False, message=health_status)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline == termination_deadline_time
        assert instance.termination_reason == InstanceTerminationReason.UNREACHABLE

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
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=True)
            await process_instances()
            healthcheck.assert_called()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert not instance.unreachable

    @pytest.mark.asyncio
    @pytest.mark.parametrize("health_status", [HealthStatus.HEALTHY, HealthStatus.FAILURE])
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_switch_to_unreachable_state(
        self, test_db, session: AsyncSession, health_status: HealthStatus
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            unreachable=False,
            health_status=health_status,
        )

        with patch(
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(reachable=False)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable
        # Should keep the previous status
        assert instance.health == health_status

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_check_shim_check_instance_health(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            unreachable=False,
            health_status=HealthStatus.HEALTHY,
        )
        health_response = InstanceHealthResponse(
            dcgm=DCGMHealthResponse(
                overall_health=DCGMHealthResult.DCGM_HEALTH_RESULT_WARN, incidents=[]
            )
        )

        with patch(
            "dstack._internal.server.background.tasks.process_instances._check_instance_inner"
        ) as healthcheck:
            healthcheck.return_value = InstanceCheck(
                reachable=True, health_response=health_response
            )
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert not instance.unreachable
        assert instance.health == HealthStatus.WARNING

        res = await session.execute(select(InstanceHealthCheckModel))
        health_check = res.scalars().one()
        assert health_check.status == HealthStatus.WARNING
        assert health_check.response == health_response.json()


@pytest.mark.usefixtures("disable_maybe_install_components", "turn_off_keep_shim_tasks_setting")
class TestRemoveDanglingTasks:
    @pytest.fixture
    def disable_maybe_install_components(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances._maybe_install_components",
            Mock(return_value=None),
        )

    @pytest.fixture
    def turn_off_keep_shim_tasks_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dstack._internal.server.settings.SERVER_KEEP_SHIM_TASKS", False)

    @pytest.fixture
    def ssh_tunnel_mock(self) -> Generator[Mock, None, None]:
        with patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock:
            yield SSHTunnelMock

    @pytest.fixture
    def shim_client_mock(self) -> Generator[Mock, None, None]:
        with patch("dstack._internal.server.services.runner.client.ShimClient") as ShimClientMock:
            yield ShimClientMock.return_value

    @pytest.mark.asyncio
    async def test_terminates_and_removes_dangling_tasks(
        self, test_db, session: AsyncSession, ssh_tunnel_mock, shim_client_mock: Mock
    ):
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
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
            status=JobStatus.RUNNING,
            instance=instance,
        )
        dangling_task_id_1 = "fe138b77-d0b1-49d3-8c9f-2dfe78ece727"
        dangling_task_id_2 = "8b016a75-41de-44f1-91ff-c9b63d2caa1d"
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            tasks=[
                TaskListItem(id=str(job.id), status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_1, status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_2, status=TaskStatus.TERMINATED),
            ]
        )
        await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.BUSY

        shim_client_mock.terminate_task.assert_called_once_with(
            task_id=dangling_task_id_1, reason=None, message=None, timeout=0
        )
        assert shim_client_mock.remove_task.call_count == 2
        shim_client_mock.remove_task.assert_has_calls(
            [call(task_id=dangling_task_id_1), call(task_id=dangling_task_id_2)]
        )

    @pytest.mark.asyncio
    async def test_terminates_and_removes_dangling_tasks_legacy_shim(
        self, test_db, session: AsyncSession, ssh_tunnel_mock, shim_client_mock: Mock
    ):
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
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
            status=JobStatus.RUNNING,
            instance=instance,
        )
        dangling_task_id_1 = "fe138b77-d0b1-49d3-8c9f-2dfe78ece727"
        dangling_task_id_2 = "8b016a75-41de-44f1-91ff-c9b63d2caa1d"
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            ids=[str(job.id), dangling_task_id_1, dangling_task_id_2]
        )
        await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.BUSY

        assert shim_client_mock.terminate_task.call_count == 2
        shim_client_mock.terminate_task.assert_has_calls(
            [
                call(task_id=dangling_task_id_1, reason=None, message=None, timeout=0),
                call(task_id=dangling_task_id_2, reason=None, message=None, timeout=0),
            ]
        )
        assert shim_client_mock.remove_task.call_count == 2
        shim_client_mock.remove_task.assert_has_calls(
            [call(task_id=dangling_task_id_1), call(task_id=dangling_task_id_2)]
        )


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
        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT


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
        assert instance.termination_reason == InstanceTerminationReason.PROVISIONING_TIMEOUT


class TestTerminate:
    @staticmethod
    @contextmanager
    def mock_terminate_in_backend(error: Optional[Exception] = None):
        backend = Mock()
        backend.TYPE = BackendType.VERDA
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
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await process_instances()
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT
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
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
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
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
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
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
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
            backend_mock.compute.return_value.get_offers.return_value = [offer]
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
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        gcp_mock = Mock()
        gcp_mock.TYPE = BackendType.GCP
        offer = get_instance_offer_with_availability(backend=BackendType.GCP, price=2.0)
        gcp_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        gcp_mock.compute.return_value.get_offers.return_value = [offer]
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
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock]
            await process_instances()

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.NO_OFFERS

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
        assert instance.termination_reason == InstanceTerminationReason.NO_OFFERS

    @pytest.mark.parametrize(
        ("placement", "expected_termination_reasons"),
        [
            pytest.param(
                InstanceGroupPlacement.CLUSTER,
                {
                    InstanceTerminationReason.NO_OFFERS: 1,
                    InstanceTerminationReason.MASTER_FAILED: 3,
                },
                id="cluster",
            ),
            pytest.param(
                None,
                {InstanceTerminationReason.NO_OFFERS: 4},
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
        backend_mock.compute.return_value.get_offers.return_value = [
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
        backend_mock.compute.return_value.get_offers.return_value = [
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
        backend_mock.compute.return_value.get_offers.return_value = [
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
        mock = Mock(return_value=(InstanceCheck(reachable=True), host_info, GoArchType.AMD64))
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


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestDeleteInstanceHealthChecks:
    async def test_deletes_instance_health_checks(
        self, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.IDLE
        )
        # 30 minutes
        monkeypatch.setattr(
            "dstack._internal.server.settings.SERVER_INSTANCE_HEALTH_TTL_SECONDS", 1800
        )
        now = get_current_datetime()
        # old check
        await create_instance_health_check(
            session=session, instance=instance, collected_at=now - dt.timedelta(minutes=40)
        )
        # recent check
        check = await create_instance_health_check(
            session=session, instance=instance, collected_at=now - dt.timedelta(minutes=20)
        )

        await delete_instance_health_checks()

        res = await session.execute(select(InstanceHealthCheckModel))
        all_checks = res.scalars().all()
        assert len(all_checks) == 1
        assert all_checks[0] == check


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "instance", "ssh_tunnel_mock", "shim_client_mock")
class BaseTestMaybeInstallComponents:
    EXPECTED_VERSION = "0.20.1"

    @pytest_asyncio.fixture
    async def instance(self, session: AsyncSession) -> InstanceModel:
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.BUSY
        )
        return instance

    @pytest.fixture
    def component_list(self) -> ComponentList:
        return ComponentList()

    @pytest.fixture
    def debug_task_log(self, caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
        caplog.set_level(
            level=logging.DEBUG,
            logger="dstack._internal.server.background.tasks.process_instances",
        )
        return caplog

    @pytest.fixture
    def ssh_tunnel_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dstack._internal.server.services.runner.ssh.SSHTunnel", MagicMock())

    @pytest.fixture
    def shim_client_mock(
        self,
        monkeypatch: pytest.MonkeyPatch,
        component_list: ComponentList,
    ) -> Mock:
        mock = Mock(spec_set=ShimClient)
        mock.healthcheck.return_value = HealthcheckResponse(
            service="dstack-shim", version=self.EXPECTED_VERSION
        )
        mock.get_instance_health.return_value = InstanceHealthResponse()
        mock.get_components.return_value = component_list
        mock.list_tasks.return_value = TaskListResponse(tasks=[])
        mock.is_safe_to_restart.return_value = False
        monkeypatch.setattr(
            "dstack._internal.server.services.runner.client.ShimClient", Mock(return_value=mock)
        )
        return mock


@pytest.mark.usefixtures("get_dstack_runner_version_mock")
class TestMaybeInstallRunner(BaseTestMaybeInstallComponents):
    @pytest.fixture
    def component_list(self) -> ComponentList:
        components = ComponentList()
        components.add(
            ComponentInfo(
                name=ComponentName.RUNNER,
                version=self.EXPECTED_VERSION,
                status=ComponentStatus.INSTALLED,
            ),
        )
        return components

    @pytest.fixture
    def get_dstack_runner_version_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.EXPECTED_VERSION)
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances.get_dstack_runner_version",
            mock,
        )
        return mock

    @pytest.fixture
    def get_dstack_runner_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/runner")
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances.get_dstack_runner_download_url",
            mock,
        )
        return mock

    async def test_cannot_determine_expected_version(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_version_mock: Mock,
    ):
        get_dstack_runner_version_mock.return_value = None

        await process_instances()

        assert "Cannot determine the expected runner version" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_not_called()

    async def test_expected_version_already_installed(
        self, debug_task_log: pytest.LogCaptureFixture, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value.runner.version = self.EXPECTED_VERSION

        await process_instances()

        assert "expected runner version already installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_not_called()

    @pytest.mark.parametrize("status", [ComponentStatus.NOT_INSTALLED, ComponentStatus.ERROR])
    async def test_install_not_installed_or_error(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_download_url_mock: Mock,
        status: ComponentStatus,
    ):
        shim_client_mock.get_components.return_value.runner.version = ""
        shim_client_mock.get_components.return_value.runner.status = status

        await process_instances()

        assert f"installing runner (no version) -> {self.EXPECTED_VERSION}" in debug_task_log.text
        get_dstack_runner_download_url_mock.assert_called_once_with(
            arch=None, version=self.EXPECTED_VERSION
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_called_once_with(
            get_dstack_runner_download_url_mock.return_value
        )

    @pytest.mark.parametrize("installed_version", ["0.19.40", "0.21.0", "dev"])
    async def test_install_installed(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_download_url_mock: Mock,
        installed_version: str,
    ):
        shim_client_mock.get_components.return_value.runner.version = installed_version

        await process_instances()

        assert (
            f"installing runner {installed_version} -> {self.EXPECTED_VERSION}"
            in debug_task_log.text
        )
        get_dstack_runner_download_url_mock.assert_called_once_with(
            arch=None, version=self.EXPECTED_VERSION
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_called_once_with(
            get_dstack_runner_download_url_mock.return_value
        )

    async def test_already_installing(
        self, debug_task_log: pytest.LogCaptureFixture, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value.runner.version = "dev"
        shim_client_mock.get_components.return_value.runner.status = ComponentStatus.INSTALLING

        await process_instances()

        assert "runner is already being installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_not_called()


@pytest.mark.usefixtures("get_dstack_shim_version_mock")
class TestMaybeInstallShim(BaseTestMaybeInstallComponents):
    @pytest.fixture
    def component_list(self) -> ComponentList:
        components = ComponentList()
        components.add(
            ComponentInfo(
                name=ComponentName.SHIM,
                version=self.EXPECTED_VERSION,
                status=ComponentStatus.INSTALLED,
            ),
        )
        return components

    @pytest.fixture
    def get_dstack_shim_version_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.EXPECTED_VERSION)
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances.get_dstack_shim_version",
            mock,
        )
        return mock

    @pytest.fixture
    def get_dstack_shim_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/shim")
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances.get_dstack_shim_download_url",
            mock,
        )
        return mock

    async def test_cannot_determine_expected_version(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_version_mock: Mock,
    ):
        get_dstack_shim_version_mock.return_value = None

        await process_instances()

        assert "Cannot determine the expected shim version" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_not_called()

    async def test_expected_version_already_installed(
        self, debug_task_log: pytest.LogCaptureFixture, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value.shim.version = self.EXPECTED_VERSION

        await process_instances()

        assert "expected shim version already installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_not_called()

    @pytest.mark.parametrize("status", [ComponentStatus.NOT_INSTALLED, ComponentStatus.ERROR])
    async def test_install_not_installed_or_error(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_download_url_mock: Mock,
        status: ComponentStatus,
    ):
        shim_client_mock.get_components.return_value.shim.version = ""
        shim_client_mock.get_components.return_value.shim.status = status

        await process_instances()

        assert f"installing shim (no version) -> {self.EXPECTED_VERSION}" in debug_task_log.text
        get_dstack_shim_download_url_mock.assert_called_once_with(
            arch=None, version=self.EXPECTED_VERSION
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_called_once_with(
            get_dstack_shim_download_url_mock.return_value
        )

    @pytest.mark.parametrize("installed_version", ["0.19.40", "0.21.0", "dev"])
    async def test_install_installed(
        self,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_download_url_mock: Mock,
        installed_version: str,
    ):
        shim_client_mock.get_components.return_value.shim.version = installed_version

        await process_instances()

        assert (
            f"installing shim {installed_version} -> {self.EXPECTED_VERSION}"
            in debug_task_log.text
        )
        get_dstack_shim_download_url_mock.assert_called_once_with(
            arch=None, version=self.EXPECTED_VERSION
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_called_once_with(
            get_dstack_shim_download_url_mock.return_value
        )

    async def test_already_installing(
        self, debug_task_log: pytest.LogCaptureFixture, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value.shim.version = "dev"
        shim_client_mock.get_components.return_value.shim.status = ComponentStatus.INSTALLING

        await process_instances()

        assert "shim is already being installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_not_called()


@pytest.mark.usefixtures("maybe_install_runner_mock", "maybe_install_shim_mock")
class TestMaybeRestartShim(BaseTestMaybeInstallComponents):
    @pytest.fixture
    def component_list(self) -> ComponentList:
        components = ComponentList()
        components.add(
            ComponentInfo(
                name=ComponentName.RUNNER,
                version=self.EXPECTED_VERSION,
                status=ComponentStatus.INSTALLED,
            ),
        )
        components.add(
            ComponentInfo(
                name=ComponentName.SHIM,
                version=self.EXPECTED_VERSION,
                status=ComponentStatus.INSTALLED,
            ),
        )
        return components

    @pytest.fixture
    def maybe_install_runner_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=False)
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances._maybe_install_runner",
            mock,
        )
        return mock

    @pytest.fixture
    def maybe_install_shim_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=False)
        monkeypatch.setattr(
            "dstack._internal.server.background.tasks.process_instances._maybe_install_shim",
            mock,
        )
        return mock

    async def test_up_to_date(self, shim_client_mock: Mock):
        shim_client_mock.get_version_string.return_value = self.EXPECTED_VERSION
        shim_client_mock.is_safe_to_restart.return_value = True

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_no_shim_component_info(self, shim_client_mock: Mock):
        shim_client_mock.get_components.return_value = ComponentList()
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_shutdown_requested(self, shim_client_mock: Mock):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_called_once_with(force=False)

    async def test_outdated_but_task_wont_survive_restart(self, shim_client_mock: Mock):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = False

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_runner_installation_in_progress(
        self, shim_client_mock: Mock, component_list: ComponentList
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        runner_info = component_list.runner
        assert runner_info is not None
        runner_info.status = ComponentStatus.INSTALLING

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_shim_installation_in_progress(
        self, shim_client_mock: Mock, component_list: ComponentList
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        shim_info = component_list.shim
        assert shim_info is not None
        shim_info.status = ComponentStatus.INSTALLING

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_runner_installation_requested(
        self, shim_client_mock: Mock, maybe_install_runner_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        maybe_install_runner_mock.return_value = True

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_shim_installation_requested(
        self, shim_client_mock: Mock, maybe_install_shim_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        maybe_install_shim_mock.return_value = True

        await process_instances()

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()
