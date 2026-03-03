import datetime as dt
import logging
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.core.models.profiles import TerminationPolicy
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.background.pipeline_tasks.instances import check as instances_check
from dstack._internal.server.models import InstanceHealthCheckModel, InstanceModel
from dstack._internal.server.schemas.health.dcgm import DCGMHealthResponse, DCGMHealthResult
from dstack._internal.server.schemas.instances import InstanceCheck
from dstack._internal.server.schemas.runner import (
    ComponentInfo,
    ComponentName,
    ComponentStatus,
    HealthcheckResponse,
    InstanceHealthResponse,
    TaskListResponse,
)
from dstack._internal.server.services.runner.client import ComponentList, ShimClient
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
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
class TestInstanceCheck:
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
        assert health_check.response == health_response.json()

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
        mock.get_components.return_value = component_list
        mock.list_tasks.return_value = TaskListResponse(tasks=[])
        mock.is_safe_to_restart.return_value = False
        monkeypatch.setattr(
            "dstack._internal.server.services.runner.client.ShimClient",
            Mock(return_value=mock),
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
        monkeypatch.setattr(instances_check, "get_dstack_runner_version", mock)
        return mock

    @pytest.fixture
    def get_dstack_runner_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/runner")
        monkeypatch.setattr(instances_check, "get_dstack_runner_download_url", mock)
        return mock

    async def test_cannot_determine_expected_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_version_mock: Mock,
    ):
        get_dstack_runner_version_mock.return_value = None

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert "Cannot determine the expected runner version" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_not_called()

    async def test_expected_version_already_installed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_components.return_value.runner.version = self.EXPECTED_VERSION

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert "expected runner version already installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_not_called()

    @pytest.mark.parametrize("status", [ComponentStatus.NOT_INSTALLED, ComponentStatus.ERROR])
    async def test_install_not_installed_or_error(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_download_url_mock: Mock,
        status: ComponentStatus,
    ):
        shim_client_mock.get_components.return_value.runner.version = ""
        shim_client_mock.get_components.return_value.runner.status = status

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert f"installing runner (no version) -> {self.EXPECTED_VERSION}" in debug_task_log.text
        get_dstack_runner_download_url_mock.assert_called_once_with(
            arch=None,
            version=self.EXPECTED_VERSION,
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_called_once_with(
            get_dstack_runner_download_url_mock.return_value
        )

    @pytest.mark.parametrize("installed_version", ["0.19.40", "0.21.0", "dev"])
    async def test_install_installed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_runner_download_url_mock: Mock,
        installed_version: str,
    ):
        shim_client_mock.get_components.return_value.runner.version = installed_version

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"installing runner {installed_version} -> {self.EXPECTED_VERSION}"
            in debug_task_log.text
        )
        get_dstack_runner_download_url_mock.assert_called_once_with(
            arch=None,
            version=self.EXPECTED_VERSION,
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_runner.assert_called_once_with(
            get_dstack_runner_download_url_mock.return_value
        )

    async def test_already_installing(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_components.return_value.runner.version = "dev"
        shim_client_mock.get_components.return_value.runner.status = ComponentStatus.INSTALLING

        instances_check._maybe_install_components(instance, shim_client_mock)

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
        monkeypatch.setattr(instances_check, "get_dstack_shim_version", mock)
        return mock

    @pytest.fixture
    def get_dstack_shim_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/shim")
        monkeypatch.setattr(instances_check, "get_dstack_shim_download_url", mock)
        return mock

    async def test_cannot_determine_expected_version(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_version_mock: Mock,
    ):
        get_dstack_shim_version_mock.return_value = None

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert "Cannot determine the expected shim version" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_not_called()

    async def test_expected_version_already_installed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_components.return_value.shim.version = self.EXPECTED_VERSION

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert "expected shim version already installed" in debug_task_log.text
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_not_called()

    @pytest.mark.parametrize("status", [ComponentStatus.NOT_INSTALLED, ComponentStatus.ERROR])
    async def test_install_not_installed_or_error(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_download_url_mock: Mock,
        status: ComponentStatus,
    ):
        shim_client_mock.get_components.return_value.shim.version = ""
        shim_client_mock.get_components.return_value.shim.status = status

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert f"installing shim (no version) -> {self.EXPECTED_VERSION}" in debug_task_log.text
        get_dstack_shim_download_url_mock.assert_called_once_with(
            arch=None,
            version=self.EXPECTED_VERSION,
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_called_once_with(
            get_dstack_shim_download_url_mock.return_value
        )

    @pytest.mark.parametrize("installed_version", ["0.19.40", "0.21.0", "dev"])
    async def test_install_installed(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
        get_dstack_shim_download_url_mock: Mock,
        installed_version: str,
    ):
        shim_client_mock.get_components.return_value.shim.version = installed_version

        instances_check._maybe_install_components(instance, shim_client_mock)

        assert (
            f"installing shim {installed_version} -> {self.EXPECTED_VERSION}"
            in debug_task_log.text
        )
        get_dstack_shim_download_url_mock.assert_called_once_with(
            arch=None,
            version=self.EXPECTED_VERSION,
        )
        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.install_shim.assert_called_once_with(
            get_dstack_shim_download_url_mock.return_value
        )

    async def test_already_installing(
        self,
        test_db,
        instance: InstanceModel,
        debug_task_log: pytest.LogCaptureFixture,
        shim_client_mock: Mock,
    ):
        shim_client_mock.get_components.return_value.shim.version = "dev"
        shim_client_mock.get_components.return_value.shim.status = ComponentStatus.INSTALLING

        instances_check._maybe_install_components(instance, shim_client_mock)

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
