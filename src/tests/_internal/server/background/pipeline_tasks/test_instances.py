import asyncio
import datetime as dt
import logging
import uuid
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional
from unittest.mock import AsyncMock, Mock, call, patch

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
    SSHProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
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
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus
from dstack._internal.server.background.pipeline_tasks import instances as instances_pipeline
from dstack._internal.server.background.pipeline_tasks.instances import (
    InstanceFetcher,
    InstancePipeline,
    InstancePipelineItem,
    InstanceWorker,
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
    create_compute_group,
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
    list_events,
)
from dstack._internal.utils.common import get_current_datetime

pytestmark = pytest.mark.usefixtures("image_config_mock")
LOCK_EXPIRES_AT = dt.datetime(2025, 1, 2, 3, 4, tzinfo=dt.timezone.utc)


@pytest.fixture
def fetcher() -> InstanceFetcher:
    return InstanceFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=dt.timedelta(seconds=10),
        lock_timeout=dt.timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> InstanceWorker:
    return InstanceWorker(queue=asyncio.Queue(), heartbeater=Mock())


@pytest.fixture
def host_info() -> dict:
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
def deploy_instance_mock(monkeypatch: pytest.MonkeyPatch, host_info: dict) -> Mock:
    mock = Mock(return_value=(InstanceCheck(reachable=True), host_info, GoArchType.AMD64))
    monkeypatch.setattr(instances_pipeline, "_deploy_instance", mock)
    return mock


def _instance_to_pipeline_item(instance_model: InstanceModel) -> InstancePipelineItem:
    assert instance_model.lock_token is not None
    assert instance_model.lock_expires_at is not None
    return InstancePipelineItem(
        __tablename__=instance_model.__tablename__,
        id=instance_model.id,
        lock_token=instance_model.lock_token,
        lock_expires_at=instance_model.lock_expires_at,
        prev_lock_expired=False,
        status=instance_model.status,
    )


def _lock_instance(instance_model: InstanceModel) -> None:
    instance_model.lock_token = uuid.uuid4()
    instance_model.lock_expires_at = LOCK_EXPIRES_AT
    instance_model.lock_owner = InstancePipeline.__name__


async def _process_instance(
    session: AsyncSession, worker: InstanceWorker, instance_model: InstanceModel
) -> None:
    _lock_instance(instance_model)
    await session.commit()
    await worker.process(_instance_to_pipeline_item(instance_model))


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestInstanceFetcher:
    async def test_fetch_selects_eligible_instances_and_sets_lock_fields(
        self, test_db, session: AsyncSession, fetcher: InstanceFetcher
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(session=session, project=project)
        compute_group = await create_compute_group(session=session, project=project, fleet=fleet)
        now = get_current_datetime()
        stale = now - dt.timedelta(minutes=1)

        pending = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            last_processed_at=stale - dt.timedelta(seconds=5),
        )
        provisioning = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
            name="provisioning",
            last_processed_at=stale - dt.timedelta(seconds=4),
        )
        busy = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
            name="busy",
            last_processed_at=stale - dt.timedelta(seconds=3),
        )
        idle = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="idle",
            last_processed_at=stale - dt.timedelta(seconds=2),
        )
        terminating = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
            name="terminating",
            last_processed_at=stale - dt.timedelta(seconds=1),
        )

        deleted = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="deleted",
            last_processed_at=stale,
        )
        deleted.deleted = True

        recent = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="recent",
            last_processed_at=now,
        )

        terminating_compute_group = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
            name="terminating-compute-group",
            last_processed_at=stale + dt.timedelta(seconds=1),
        )
        terminating_compute_group.compute_group = compute_group

        locked = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            name="locked",
            last_processed_at=stale + dt.timedelta(seconds=2),
        )
        locked.lock_expires_at = now + dt.timedelta(minutes=1)
        locked.lock_token = uuid.uuid4()
        locked.lock_owner = "OtherPipeline"

        await session.commit()

        items = await fetcher.fetch(limit=10)

        assert {item.id for item in items} == {
            pending.id,
            provisioning.id,
            busy.id,
            idle.id,
            terminating.id,
        }
        assert {item.status for item in items} == {
            InstanceStatus.PENDING,
            InstanceStatus.PROVISIONING,
            InstanceStatus.BUSY,
            InstanceStatus.IDLE,
            InstanceStatus.TERMINATING,
        }

        for instance in [
            pending,
            provisioning,
            busy,
            idle,
            terminating,
            deleted,
            recent,
            terminating_compute_group,
            locked,
        ]:
            await session.refresh(instance)

        expected_lock_owner = InstancePipeline.__name__
        fetched_instances = [pending, provisioning, busy, idle, terminating]
        assert all(instance.lock_owner == expected_lock_owner for instance in fetched_instances)
        assert all(instance.lock_expires_at is not None for instance in fetched_instances)
        assert all(instance.lock_token is not None for instance in fetched_instances)
        assert len({instance.lock_token for instance in fetched_instances}) == 1

        assert deleted.lock_owner is None
        assert recent.lock_owner is None
        assert terminating_compute_group.lock_owner is None
        assert locked.lock_owner == "OtherPipeline"

    async def test_fetch_respects_order_and_limit(
        self, test_db, session: AsyncSession, fetcher: InstanceFetcher
    ):
        project = await create_project(session=session)
        now = get_current_datetime()

        oldest = await create_instance(
            session=session,
            project=project,
            name="oldest",
            last_processed_at=now - dt.timedelta(minutes=3),
        )
        middle = await create_instance(
            session=session,
            project=project,
            name="middle",
            last_processed_at=now - dt.timedelta(minutes=2),
        )
        newest = await create_instance(
            session=session,
            project=project,
            name="newest",
            last_processed_at=now - dt.timedelta(minutes=1),
        )

        items = await fetcher.fetch(limit=2)

        assert [item.id for item in items] == [oldest.id, middle.id]

        await session.refresh(oldest)
        await session.refresh(middle)
        await session.refresh(newest)

        assert oldest.lock_owner == InstancePipeline.__name__
        assert middle.lock_owner == InstancePipeline.__name__
        assert newest.lock_owner is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestInstanceWorker:
    @staticmethod
    @contextmanager
    def mock_terminate_in_backend(error: Optional[Exception] = None):
        backend = Mock()
        backend.TYPE = BackendType.VERDA
        terminate_instance = backend.compute.return_value.terminate_instance
        if error is not None:
            terminate_instance.side_effect = error
        with patch.object(
            instances_pipeline.backends_services,
            "get_project_backend_by_type",
            AsyncMock(return_value=backend),
        ):
            yield terminate_instance

    async def test_process_skips_when_lock_token_changes(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
        )

        _lock_instance(instance)
        await session.commit()
        item = _instance_to_pipeline_item(instance)
        new_lock_token = uuid.uuid4()
        instance.lock_token = new_lock_token
        await session.commit()

        await worker.process(item)
        await session.refresh(instance)

        assert instance.lock_token == new_lock_token
        assert instance.lock_owner == InstancePipeline.__name__

    async def test_process_unlocks_and_updates_last_processed_at_after_check(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PROVISIONING,
        )
        before_processed_at = instance.last_processed_at

        monkeypatch.setattr(
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.lock_expires_at is None
        assert instance.lock_token is None
        assert instance.lock_owner is None
        assert instance.last_processed_at > before_processed_at

    async def test_check_shim_transitions_provisioning_on_ready(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

    async def test_check_shim_transitions_provisioning_on_terminating(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="Shim problem")),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline is not None

    async def test_check_shim_transitions_provisioning_on_busy(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        await session.refresh(job)

        assert instance.status == InstanceStatus.BUSY
        assert instance.termination_deadline is None
        assert job.instance == instance

    async def test_check_shim_start_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="SSH connection fail")),
        )
        await _process_instance(session, worker, instance)

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
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="SSH connection fail")),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.unreachable is True
        assert instance.termination_deadline is None

    async def test_check_shim_stop_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await _process_instance(session, worker, instance)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None

    async def test_check_shim_terminate_instance_by_deadline(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False, message="Not ok")),
        )
        await _process_instance(session, worker, instance)

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
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=True)),
        )
        await _process_instance(session, worker, instance)

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
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(return_value=InstanceCheck(reachable=False)),
        )
        await _process_instance(session, worker, instance)

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
        fetcher: InstanceFetcher,
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
            instances_pipeline,
            "_check_instance_inner",
            Mock(
                return_value=InstanceCheck(
                    reachable=True,
                    health_response=health_response,
                )
            ),
        )
        await _process_instance(session, worker, instance)

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
        fetcher: InstanceFetcher,
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

        await _process_instance(session, worker, instance)
        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT

    async def test_pending_ssh_instance_terminates_on_provision_timeout(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime() - dt.timedelta(days=100),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.PROVISIONING_TIMEOUT

    async def test_terminate(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await _process_instance(session, worker, instance)
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.IDLE_TIMEOUT
        assert instance.deleted is True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None

    async def test_terminates_terminating_deleted_instance(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        _lock_instance(instance)
        await session.commit()
        item = _instance_to_pipeline_item(instance)
        instance.deleted = True
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = instance.deleted_at = (
            get_current_datetime() + dt.timedelta(minutes=-19)
        )
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await worker.process(item)
            mock.assert_called_once()

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.deleted is True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None

    @pytest.mark.parametrize(
        "error", [BackendError("err"), RuntimeError("err"), NotYetTerminated("")]
    )
    async def test_terminate_retry(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        error: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=error) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            freeze_time(initial_time + dt.timedelta(minutes=2)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    async def test_terminate_not_retries_if_too_early(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        instance.last_processed_at = initial_time
        await session.commit()

        with (
            freeze_time(initial_time + dt.timedelta(minutes=1, seconds=11)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_not_called()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

    async def test_terminate_on_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        initial_time = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        instance.last_job_processed_at = initial_time
        instance.last_processed_at = initial_time - dt.timedelta(minutes=1)
        await session.commit()

        with (
            freeze_time(initial_time + dt.timedelta(minutes=1)),
            self.mock_terminate_in_backend(error=BackendError("err")) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            freeze_time(initial_time + dt.timedelta(minutes=15, seconds=55)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await _process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    @pytest.mark.parametrize(
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="cpu-instance-auto-max-cpu"),
        ],
    )
    async def test_creates_instance(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
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
                        cpus=cpus,
                        memory_mib=131072,
                        spot=False,
                        gpus=[gpu] * gpus,
                    ),
                ),
                region="us",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
                total_blocks=expected_blocks,
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

            await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_tries_second_offer_if_first_fails(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        err: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
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
            backend=offer.backend,
            region=offer.region,
            price=offer.price,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock, gcp_mock]
            await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        aws_mock.compute.return_value.create_instance.assert_called_once()
        assert instance.backend == BackendType.GCP

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_fails_if_all_offers_fail(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        err: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock]
            await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.NO_OFFERS

    async def test_fails_if_no_offers(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            await _process_instance(session, worker, instance)

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
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        placement: Optional[InstanceGroupPlacement],
        expected_termination_reasons: dict[str, int],
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=placement, nodes=FleetNodesSpec(min=4, target=4, max=4)
                )
            ),
        )
        instances = [
            await create_instance(
                session=session,
                project=project,
                fleet=fleet,
                status=InstanceStatus.PENDING,
                offer=None,
                job_provisioning_data=None,
                instance_num=index,
                created_at=get_current_datetime() + dt.timedelta(seconds=index),
            )
            for index in range(4)
        ]
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            for instance in sorted(instances, key=lambda i: (i.instance_num, i.created_at)):
                await _process_instance(session, worker, instance)

        termination_reasons = defaultdict(int)
        for instance in instances:
            await session.refresh(instance)
            assert instance.status == InstanceStatus.TERMINATED
            termination_reasons[instance.termination_reason] += 1
        assert termination_reasons == expected_termination_reasons

    @pytest.mark.parametrize(
        ("placement", "should_create"),
        [
            pytest.param(InstanceGroupPlacement.CLUSTER, True, id="placement-cluster"),
            pytest.param(None, False, id="no-placement"),
        ],
    )
    async def test_create_placement_group_if_placement_cluster(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        placement: Optional[InstanceGroupPlacement],
        should_create: bool,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=placement, nodes=FleetNodesSpec(min=1, target=1, max=1)
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
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
            await _process_instance(session, worker, instance)

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
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        can_reuse: bool,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=1),
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
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
            await _process_instance(session, worker, instance)

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
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        err: Exception,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=1),
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
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
                return get_placement_group_provisioning_data()
            raise err

        backend_mock.compute.return_value.create_placement_group = create_placement_group_method
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert instance.offer
        assert "good-offer" in instance.offer
        assert "bad-offer" not in instance.offer
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        assert len(placement_groups) == 1

    @pytest.mark.parametrize(
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="cpu-instance-auto-max-cpu"),
        ],
    )
    async def test_adds_ssh_instance(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
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

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.IDLE
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0
        deploy_instance_mock.assert_called_once()

    async def test_retries_ssh_instance_if_provisioning_fails(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        deploy_instance_mock: Mock,
    ):
        deploy_instance_mock.side_effect = SSHProvisioningError("Expected")
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PENDING
        assert instance.termination_reason is None

    async def test_terminates_ssh_instance_if_deploy_fails_unexpectedly(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        deploy_instance_mock: Mock,
    ):
        deploy_instance_mock.side_effect = RuntimeError("Unexpected")
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert instance.termination_reason_message == "Unexpected error when adding SSH instance"

    async def test_terminates_ssh_instance_if_key_is_invalid(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            instances_pipeline,
            "_ssh_keys_to_pkeys",
            Mock(side_effect=ValueError("Bad key")),
        )
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert instance.termination_reason_message == "Unsupported private SSH key type"

    async def test_terminates_ssh_instance_if_internal_ip_cannot_be_resolved_from_network(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
    ):
        host_info["addresses"] = ["192.168.100.100/24"]
        project = await create_project(session=session)
        job_provisioning_data = get_job_provisioning_data(
            dockerized=True,
            backend=BackendType.REMOTE,
            internal_ip=None,
        )
        job_provisioning_data.instance_network = "10.0.0.0/24"
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            job_provisioning_data=job_provisioning_data,
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert (
            instance.termination_reason_message
            == "Failed to locate internal IP address on the given network"
        )

    async def test_terminates_ssh_instance_if_internal_ip_is_not_in_host_interfaces(
        self,
        test_db,
        session: AsyncSession,
        fetcher: InstanceFetcher,
        worker: InstanceWorker,
        host_info: dict,
        deploy_instance_mock: Mock,
    ):
        host_info["addresses"] = ["192.168.100.100/24"]
        project = await create_project(session=session)
        job_provisioning_data = get_job_provisioning_data(
            dockerized=True,
            backend=BackendType.REMOTE,
            internal_ip="10.0.0.20",
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            created_at=get_current_datetime(),
            remote_connection_info=get_remote_connection_info(),
            job_provisioning_data=job_provisioning_data,
        )
        await session.commit()

        await _process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.ERROR
        assert (
            instance.termination_reason_message
            == "Specified internal IP not found among instance interfaces"
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("turn_off_keep_shim_tasks_setting")
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestRemoveDanglingTasks:
    @pytest.fixture
    def turn_off_keep_shim_tasks_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dstack._internal.server.settings.SERVER_KEEP_SHIM_TASKS", False)

    async def test_terminates_and_removes_dangling_tasks(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
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
        shim_client_mock = Mock(spec_set=ShimClient)
        shim_client_mock.is_api_v2_supported.return_value = True
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            tasks=[
                TaskListItem(id=str(job.id), status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_1, status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_2, status=TaskStatus.TERMINATED),
            ]
        )
        await session.refresh(instance, attribute_names=["jobs"])

        instances_pipeline.remove_dangling_tasks_from_instance(shim_client_mock, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.BUSY

        shim_client_mock.terminate_task.assert_called_once_with(
            task_id=dangling_task_id_1,
            reason=None,
            message=None,
            timeout=0,
        )
        assert shim_client_mock.remove_task.call_count == 2
        shim_client_mock.remove_task.assert_has_calls(
            [call(task_id=dangling_task_id_1), call(task_id=dangling_task_id_2)]
        )

    async def test_terminates_and_removes_dangling_tasks_legacy_shim(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
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
        shim_client_mock = Mock(spec_set=ShimClient)
        shim_client_mock.is_api_v2_supported.return_value = True
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            ids=[str(job.id), dangling_task_id_1, dangling_task_id_2]
        )
        await session.refresh(instance, attribute_names=["jobs"])

        instances_pipeline.remove_dangling_tasks_from_instance(shim_client_mock, instance)

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
        caplog.set_level(level=logging.DEBUG, logger=instances_pipeline.__name__)
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
        monkeypatch.setattr(instances_pipeline, "get_dstack_runner_version", mock)
        return mock

    @pytest.fixture
    def get_dstack_runner_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/runner")
        monkeypatch.setattr(instances_pipeline, "get_dstack_runner_download_url", mock)
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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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
        monkeypatch.setattr(instances_pipeline, "get_dstack_shim_version", mock)
        return mock

    @pytest.fixture
    def get_dstack_shim_download_url_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value="https://example.com/shim")
        monkeypatch.setattr(instances_pipeline, "get_dstack_shim_download_url", mock)
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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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
        monkeypatch.setattr(instances_pipeline, "_maybe_install_runner", mock)
        return mock

    @pytest.fixture
    def maybe_install_shim_mock(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock(return_value=False)
        monkeypatch.setattr(instances_pipeline, "_maybe_install_shim", mock)
        return mock

    async def test_up_to_date(self, test_db, instance: InstanceModel, shim_client_mock: Mock):
        shim_client_mock.get_version_string.return_value = self.EXPECTED_VERSION
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_no_shim_component_info(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_components.return_value = ComponentList()
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()

    async def test_outdated_shutdown_requested(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = True

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_called_once_with(force=False)

    async def test_outdated_but_task_wont_survive_restart(
        self, test_db, instance: InstanceModel, shim_client_mock: Mock
    ):
        shim_client_mock.get_version_string.return_value = "outdated"
        shim_client_mock.is_safe_to_restart.return_value = False

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

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

        instances_pipeline._maybe_install_components(instance, shim_client_mock)

        shim_client_mock.get_components.assert_called_once()
        shim_client_mock.shutdown.assert_not_called()
