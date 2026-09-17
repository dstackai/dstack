import datetime as dt
import logging
from typing import ClassVar, Optional
from unittest.mock import Mock

import pytest
import pytest_asyncio
import requests
from gpuhunt import AcceleratorVendor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal import settings
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.fleets import FleetNodesSpec
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    GpuDriverInfo,
    InstanceStatus,
    InstanceTerminationReason,
)
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.background.pipeline_tasks.instances import check as instances_check
from dstack._internal.server.background.pipeline_tasks.instances.common import (
    InstanceUpdateMap,
    set_gpu_driver_update,
)
from dstack._internal.server.models import InstanceHealthCheckModel, InstanceModel
from dstack._internal.server.schemas.health.dcgm import DCGMHealthResponse, DCGMHealthResult
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import (
    ComponentInfo,
    ComponentName,
    ComponentStatus,
    HealthcheckResponse,
    InstanceHealthResponse,
    InstanceInfoResponse,
    TaskListResponse,
)
from dstack._internal.server.services.runner.client import ComponentList, ShimClient
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_fleet_configuration,
    get_fleet_spec,
    get_job_provisioning_data,
    get_remote_connection_info,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.server.background.pipeline_tasks.test_instances.helpers import (
    process_instance,
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestCheckInstance:
    async def test_check_shim_transitions_provisioning_on_ready(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        instance.termination_deadline = get_current_datetime() + dt.timedelta(days=1)
        await session.commit()

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

    async def test_check_shim_transitions_provisioning_on_terminating(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        instance.started_at = get_current_datetime() + dt.timedelta(minutes=-20)
        await session.commit()

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="Shim problem")),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline is not None

    async def test_check_shim_transitions_provisioning_on_busy(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, repo=repo, user=user)
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

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)
        await session.refresh(job)

        assert instance.status == InstanceStatus.BUSY
        assert instance.termination_deadline is None
        assert job.instance == instance

    @pytest.mark.parametrize(
        "stored_version",
        [
            pytest.param(None, id="driver-not-yet-known"),
            pytest.param("550.90.07", id="driver-upgraded-on-the-host"),
        ],
    )
    async def test_check_shim_stores_gpu_driver(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
        stored_version: Optional[str],
    ):
        project = await create_project(session=session)
        job_provisioning_data = get_job_provisioning_data(dockerized=True, gpu_count=1)
        if stored_version is not None:
            job_provisioning_data.gpu_driver = GpuDriverInfo(
                vendor=AcceleratorVendor.NVIDIA, version=stored_version
            )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            job_provisioning_data=job_provisioning_data,
        )
        await session.commit()

        check_instance_inner_mock = Mock(
            return_value=InstanceCheck(
                reachable=True,
                gpu_driver=GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15"),
            )
        )
        monkeypatch.setattr(instances_check, "_check_instance_inner", check_instance_inner_mock)
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert check_instance_inner_mock.call_args.kwargs["check_instance_info"]
        assert instance.job_provisioning_data is not None
        jpd = validate_json_extra_ignore(JobProvisioningData, instance.job_provisioning_data)
        assert jpd.gpu_driver is not None
        assert jpd.gpu_driver.vendor == AcceleratorVendor.NVIDIA
        assert jpd.gpu_driver.version == "570.86.15"

    async def test_check_shim_does_not_request_instance_info_without_gpus(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            job_provisioning_data=get_job_provisioning_data(dockerized=True, gpu_count=0),
        )
        await session.commit()

        check_instance_inner_mock = Mock(return_value=InstanceCheck(reachable=True))
        monkeypatch.setattr(instances_check, "_check_instance_inner", check_instance_inner_mock)
        await process_instance(session, worker, instance)

        assert not check_instance_inner_mock.call_args.kwargs["check_instance_info"]

    async def test_check_shim_start_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            unreachable=False,
        )

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="SSH connection fail")),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is True
        assert instance.termination_deadline is not None
        assert instance.termination_deadline.replace(
            tzinfo=dt.timezone.utc
        ) > get_current_datetime() + dt.timedelta(minutes=19)

    async def test_check_shim_does_not_start_termination_deadline_with_ssh_instance(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            unreachable=False,
            remote_connection_info=get_remote_connection_info(),
        )

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="SSH connection fail")),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is True
        assert instance.termination_deadline is None

    async def test_check_shim_stop_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        instance.termination_deadline = get_current_datetime() + dt.timedelta(minutes=19)
        await session.commit()

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

    async def test_check_shim_terminate_instance_by_deadline(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        termination_deadline_time = get_current_datetime() + dt.timedelta(minutes=-19)
        instance.termination_deadline = termination_deadline_time
        await session.commit()

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="Not ok")),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline == termination_deadline_time
        assert instance.termination_reason == InstanceTerminationReason.UNREACHABLE

    @pytest.mark.parametrize(
        ["termination_policy", "has_job"],
        [
            pytest.param(TerminationPolicy.DESTROY_AFTER_IDLE, False, id="destroy-no-job"),
            pytest.param(TerminationPolicy.DESTROY_AFTER_IDLE, True, id="destroy-with-job"),
            pytest.param(TerminationPolicy.DONT_DESTROY, False, id="dont-destroy-no-job"),
            pytest.param(TerminationPolicy.DONT_DESTROY, True, id="dont-destroy-with-job"),
        ],
    )
    async def test_check_shim_process_unreachable_state(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
        termination_policy: TerminationPolicy,
        has_job: bool,
    ):
        project = await create_project(session=session)
        if has_job:
            user = await create_user(session=session)
            repo = await create_repo(session=session, project_id=project.id)
            run = await create_run(session=session, project=project, repo=repo, user=user)
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

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)
        events = await list_events(session)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is False
        assert len(events) == 1
        assert events[0].message == "Instance became reachable"

    @pytest.mark.parametrize("health_status", [HealthStatus.HEALTHY, HealthStatus.FAILURE])
    async def test_check_shim_switch_to_unreachable_state(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
        health_status: HealthStatus,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            unreachable=False,
            health_status=health_status,
        )

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False)),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)
        events = await list_events(session)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is True
        assert instance.health == health_status
        assert len(events) == 1
        assert events[0].message == "Instance became unreachable"

    async def test_check_shim_check_instance_health(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
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
                overall_health=DCGMHealthResult.DCGM_HEALTH_RESULT_WARN,
                incidents=[],
            )
        )

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(
                return_value=InstanceCheck(
                    reachable=True,
                    health_response=health_response,
                )
            ),
        )
        await process_instance(session, worker, instance)

        await session.refresh(instance)
        events = await list_events(session)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is False
        assert instance.health == HealthStatus.WARNING
        assert len(events) == 1
        assert events[0].message == "Instance health changed HEALTHY -> WARNING"

        res = await session.execute(select(InstanceHealthCheckModel))
        health_check = res.scalars().one()
        assert health_check.status == HealthStatus.WARNING
        assert health_check.response == health_response.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessIdleTimeout:
    async def test_does_not_terminate_by_idle_timeout_when_fleet_at_min_nodes(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                get_fleet_configuration(nodes=FleetNodesSpec(min=1, target=1, max=1))
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        instance.termination_idle_time = 300
        instance.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        monkeypatch.setattr(
            instances_check,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )

        await process_instance(session, worker, instance)
        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_reason is None

    async def test_terminates_by_idle_timeout_when_fleet_above_min_nodes(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(
            session=session,
            project=project,
            spec=get_fleet_spec(
                get_fleet_configuration(nodes=FleetNodesSpec(min=1, target=2, max=2))
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.IDLE,
        )
        instance.termination_idle_time = 300
        instance.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        await process_instance(session, worker, instance)
        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT

    async def test_terminate_by_idle_timeout(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )
        instance.termination_idle_time = 300
        instance.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        await process_instance(session, worker, instance)
        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class BaseTestMaybeInstallComponents:
    EXPECTED_VERSION = "0.20.1"

    @pytest_asyncio.fixture
    async def instance(self, session: AsyncSession) -> InstanceModel:
        project = await create_project(session=session)
        return await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )

    @pytest.fixture
    def component_list(self) -> ComponentList:
        return ComponentList()

    @pytest.fixture
    def debug_task_log(self, caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
        caplog.set_level(level=logging.DEBUG, logger=instances_check.__name__)
        return caplog

    @pytest.fixture
    def shim_client_mock(
        self,
        monkeypatch: pytest.MonkeyPatch,
        component_list: ComponentList,
    ) -> Mock:
        mock = Mock(spec_set=ShimClient)
        mock.healthcheck.return_value = HealthcheckResponse(
            service="dstack-shim",
            version=self.EXPECTED_VERSION,
        )
        mock.get_instance_health.return_value = InstanceHealthResponse()
        mock.get_instance_info.return_value = None
        mock.get_components.return_value = component_list
        mock.list_tasks.return_value = TaskListResponse(tasks=[])
        mock.is_safe_to_restart.return_value = False
        monkeypatch.setattr(
            "dstack._internal.server.services.runner.client.ShimClient.from_address",
            Mock(return_value=mock),
        )
        return mock


@pytest.mark.usefixtures("version_mock", "download_url_mock")
class BaseTestMaybeInstallComponent(BaseTestMaybeInstallComponents):
    """
    Shared tests for `_maybe_install_runner` and `_maybe_install_shim`. The two must behave
    identically -- only the version getter, the download URL getter, and the install call differ.
    """

    COMPONENT_NAME: ClassVar[ComponentName]
    DOWNLOAD_URL: ClassVar[str]
    ALLOW_DOWNGRADE_SETTING: ClassVar[str]

    @pytest.fixture
    def component_info(self) -> ComponentInfo:
        return ComponentInfo(
            name=self.COMPONENT_NAME,
            version=self.EXPECTED_VERSION,
            status=ComponentStatus.INSTALLED,
        )

    @pytest.fixture
    def component_list(self, component_info: ComponentInfo) -> ComponentList:
        components = ComponentList()
        components.add(component_info)
        return components

    @pytest.fixture
    def version_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        raise NotImplementedError

    @pytest.fixture
    def download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        raise NotImplementedError

    @pytest.fixture
    def install_mock(self, shim_client_mock: Mock) -> Mock:
        raise NotImplementedError

    @pytest.fixture(autouse=True)
    def allow_downgrade_settings(
        self, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The settings are read from the environment at import time, so they must be pinned in
        # both directions -- otherwise the tests fail for developers who have the variables set
        # in their environment and run `pytest` directly, without env isolation.
        monkeypatch.setattr(settings, "DSTACK_RUNNER_ALLOW_DOWNGRADE", False)
        monkeypatch.setattr(settings, "DSTACK_SHIM_ALLOW_DOWNGRADE", False)
        if request.node.get_closest_marker("allow_downgrade") is not None:
            monkeypatch.setattr(settings, self.ALLOW_DOWNGRADE_SETTING, True)

    def assert_installed(self, install_mock: Mock, download_url_mock: Mock) -> None:
        download_url_mock.assert_called_once_with(arch=None, version=self.EXPECTED_VERSION)
        install_mock.assert_called_once_with(self.DOWNLOAD_URL)

    def assert_installing_logged(self, log: pytest.LogCaptureFixture, installed_version: str):
        expected = (
            f"{self.COMPONENT_NAME.value}: installing {installed_version!r}"
            f" -> {self.EXPECTED_VERSION!r} from {self.DOWNLOAD_URL}"
        )
        assert expected in log.text

    async def test_cannot_determine_expected_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        install_mock: Mock,
        version_mock: Mock,
    ):
        version_mock.return_value = None

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        install_mock.assert_not_called()

    async def test_cannot_parse_expected_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        install_mock: Mock,
        version_mock: Mock,
    ):
        version_mock.return_value = "latest"

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"{self.COMPONENT_NAME.value}: failed to parse expected_version: 'latest'"
            in debug_task_log.text
        )
        install_mock.assert_not_called()

    @pytest.mark.parametrize("installed_version", ["0.20.1", "0.20.1.0"])
    async def test_expected_version_already_installed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
        installed_version: str,
    ):
        # `0.20.1.0` is the same version as `0.20.1` according to PyPA
        component_info.version = installed_version

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"{self.COMPONENT_NAME.value}: expected version already installed"
            in debug_task_log.text
        )
        shim_client_mock.get_components.assert_called_once()
        install_mock.assert_not_called()

    @pytest.mark.parametrize("status", [ComponentStatus.NOT_INSTALLED, ComponentStatus.ERROR])
    async def test_install_not_installed_or_error(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
        download_url_mock: Mock,
        status: ComponentStatus,
    ):
        component_info.version = ""
        component_info.status = status

        instances_check._maybe_install_components(instance, shim_client_mock)

        self.assert_installing_logged(debug_task_log, "")
        shim_client_mock.get_components.assert_called_once()
        self.assert_installed(install_mock, download_url_mock)

    async def test_install_older_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
        download_url_mock: Mock,
    ):
        component_info.version = "0.19.40"

        instances_check._maybe_install_components(instance, shim_client_mock)

        self.assert_installing_logged(debug_task_log, "0.19.40")
        shim_client_mock.get_components.assert_called_once()
        self.assert_installed(install_mock, download_url_mock)

    async def test_skips_newer_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
    ):
        component_info.version = "0.21.0"

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"{self.COMPONENT_NAME.value}: newer version already installed" in debug_task_log.text
        )
        shim_client_mock.get_components.assert_called_once()
        install_mock.assert_not_called()

    @pytest.mark.allow_downgrade
    async def test_installs_newer_version_if_downgrade_allowed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
        download_url_mock: Mock,
    ):
        component_info.version = "0.21.0"

        instances_check._maybe_install_components(instance, shim_client_mock)

        self.assert_installing_logged(debug_task_log, "0.21.0")
        self.assert_installed(install_mock, download_url_mock)

    async def test_skips_unparsable_installed_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
    ):
        # dev builds report `latest`, assuming that it's the newest version
        component_info.version = "latest"

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"{self.COMPONENT_NAME.value}: cannot parse installed_version, skipping the install"
            in debug_task_log.text
        )
        shim_client_mock.get_components.assert_called_once()
        install_mock.assert_not_called()

    @pytest.mark.allow_downgrade
    async def test_installs_unparsable_installed_version_if_downgrade_allowed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
        download_url_mock: Mock,
    ):
        component_info.version = "latest"

        instances_check._maybe_install_components(instance, shim_client_mock)

        self.assert_installing_logged(debug_task_log, "latest")
        self.assert_installed(install_mock, download_url_mock)

    async def test_already_installing(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        component_info: ComponentInfo,
        install_mock: Mock,
    ):
        component_info.version = "0.19.40"
        component_info.status = ComponentStatus.INSTALLING

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert f"{self.COMPONENT_NAME.value}: already being installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        install_mock.assert_not_called()


class TestMaybeInstallRunner(BaseTestMaybeInstallComponent):
    COMPONENT_NAME = ComponentName.RUNNER
    DOWNLOAD_URL = "https://example.com/runner"
    ALLOW_DOWNGRADE_SETTING = "DSTACK_RUNNER_ALLOW_DOWNGRADE"

    @pytest.fixture
    def version_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.EXPECTED_VERSION)
        monkeypatch.setattr(instances_check, "get_dstack_runner_version", mock)
        return mock

    @pytest.fixture
    def download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.DOWNLOAD_URL)
        monkeypatch.setattr(instances_check, "get_dstack_runner_download_url", mock)
        return mock

    @pytest.fixture
    def install_mock(self, shim_client_mock: Mock) -> Mock:
        return shim_client_mock.install_runner


class TestMaybeInstallShim(BaseTestMaybeInstallComponent):
    COMPONENT_NAME = ComponentName.SHIM
    DOWNLOAD_URL = "https://example.com/shim"
    ALLOW_DOWNGRADE_SETTING = "DSTACK_SHIM_ALLOW_DOWNGRADE"

    @pytest.fixture
    def version_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.EXPECTED_VERSION)
        monkeypatch.setattr(instances_check, "get_dstack_shim_version", mock)
        return mock

    @pytest.fixture
    def download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=self.DOWNLOAD_URL)
        monkeypatch.setattr(instances_check, "get_dstack_shim_download_url", mock)
        return mock

    @pytest.fixture
    def install_mock(self, shim_client_mock: Mock) -> Mock:
        return shim_client_mock.install_shim


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
        monkeypatch.setattr(instances_check, "_maybe_install_runner", mock)
        return mock

    @pytest.fixture
    def maybe_install_shim_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=False)
        monkeypatch.setattr(instances_check, "_maybe_install_shim", mock)
        return mock

    async def test_up_to_date(self, test_db, instance: InstanceModel, shim_client_mock: Mock):
        shim_client_mock.get_version_string.return_value = self.EXPECTED_VERSION
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_no_shim_component_info(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value = ComponentList()
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_shutdown_requested(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_called_once_with(force=False)

    async def test_outdated_but_task_wont_survive_restart(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = False

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_runner_installation_in_progress(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
        component_list: ComponentList,
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        runner_info = component_list.runner
        assert runner_info is not None
        runner_info.status = ComponentStatus.INSTALLING

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_shim_installation_in_progress(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
        component_list: ComponentList,
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        shim_info = component_list.shim
        assert shim_info is not None
        shim_info.status = ComponentStatus.INSTALLING

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_runner_installation_requested(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
        maybe_install_runner_mock: Mock,
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        maybe_install_runner_mock.return_value = True

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_but_shim_installation_requested(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
        maybe_install_shim_mock: Mock,
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True
        maybe_install_shim_mock.return_value = True

        instances_check._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()


class TestSetGpuDriverUpdate:
    def test_noop_without_driver(self):
        jpd = get_job_provisioning_data(dockerized=True)
        update_map = InstanceUpdateMap()
        assert not set_gpu_driver_update(
            update_map=update_map,
            job_provisioning_data=jpd,
            gpu_driver=None,
        )
        assert update_map == {}

    def test_noop_when_driver_unchanged(self):
        jpd = get_job_provisioning_data(dockerized=True)
        jpd.gpu_driver = GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15")
        update_map = InstanceUpdateMap()
        assert not set_gpu_driver_update(
            update_map=update_map,
            job_provisioning_data=jpd,
            gpu_driver=GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15"),
        )
        assert update_map == {}

    @pytest.mark.parametrize("current_version", [None, "550.90.07"])
    def test_sets_new_or_changed_driver(self, current_version):
        jpd = get_job_provisioning_data(dockerized=True)
        if current_version is not None:
            jpd.gpu_driver = GpuDriverInfo(
                vendor=AcceleratorVendor.NVIDIA, version=current_version
            )
        update_map = InstanceUpdateMap()
        assert set_gpu_driver_update(
            update_map=update_map,
            job_provisioning_data=jpd,
            gpu_driver=GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15"),
        )
        assert "job_provisioning_data" in update_map
        parsed = validate_json_extra_ignore(
            JobProvisioningData, update_map["job_provisioning_data"]
        )
        assert parsed.gpu_driver is not None
        assert parsed.gpu_driver.version == "570.86.15"


class TestShouldCheckInstanceInfo:
    def _should_check(self, gpu_count: int, driver_known: bool) -> bool:
        jpd = get_job_provisioning_data(dockerized=True, gpu_count=gpu_count)
        if driver_known:
            jpd.gpu_driver = GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15")
        return instances_check._should_check_instance_info(jpd)

    def test_no_gpus(self):
        assert not self._should_check(gpu_count=0, driver_known=False)

    def test_gpus_without_known_driver(self):
        assert self._should_check(gpu_count=1, driver_known=False)

    def test_gpus_with_known_driver(self):
        # Shim restarts after a driver upgrade, which the server may not observe,
        # so a known driver is re-requested to detect the change
        assert self._should_check(gpu_count=1, driver_known=True)


class TestGetGpuDriver(BaseTestMaybeInstallComponents):
    async def test_returns_reported_driver(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_instance_info.return_value = InstanceInfoResponse(
            gpu_vendor="nvidia", gpu_driver_version="570.86.15"
        )

        gpu_driver = instances_check._get_gpu_driver(instance, shim_client_mock)

        assert gpu_driver == GpuDriverInfo(vendor=AcceleratorVendor.NVIDIA, version="570.86.15")

    async def test_returns_none_if_driver_not_detected(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_instance_info.return_value = InstanceInfoResponse()

        assert instances_check._get_gpu_driver(instance, shim_client_mock) is None

    async def test_returns_none_on_request_error(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_instance_info.side_effect = requests.RequestException("boom")

        assert instances_check._get_gpu_driver(instance, shim_client_mock) is None

    async def test_returns_none_on_unknown_gpu_vendor(
        self,
        test_db,
        instance: InstanceModel,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_instance_info.return_value = InstanceInfoResponse(
            gpu_vendor="quantumx", gpu_driver_version="1.2.3"
        )

        assert instances_check._get_gpu_driver(instance, shim_client_mock) is None
