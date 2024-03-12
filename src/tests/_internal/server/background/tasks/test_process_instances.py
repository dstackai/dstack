import datetime as dt
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.profiles import Profile, TerminationPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobStatus, RetryPolicy
from dstack._internal.server.background.tasks.process_instances import (
    HealthStatus,
    process_instances,
    terminate_idle_instance,
)
from dstack._internal.server.background.tasks.process_instances import (
    create_instance as task_create_instance,
)
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
)
from dstack._internal.utils.common import get_current_datetime


class TestCheckShim:
    @pytest.mark.asyncio
    async def test_check_shim_transitions_provisioning_on_ready(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(
            session, project, pool, status=InstanceStatus.PROVISIONING
        )
        instance.termination_deadline = get_current_datetime() + dt.timedelta(days=1)
        instance.health_status = "ssh connect problem"

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None
        assert instance.health_status is None

    @pytest.mark.asyncio
    async def test_check_shim_transitions_provisioning_on_terminating(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(
            session, project, pool, status=InstanceStatus.PROVISIONING
        )
        instance.started_at = get_current_datetime() + dt.timedelta(minutes=-20)
        instance.health_status = "ssh connect problem"

        await session.commit()

        health_reason = "Shim problem"

        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=False, reason=health_reason)
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATING
        assert instance.termination_deadline is not None
        assert instance.health_status == health_reason

    @pytest.mark.asyncio
    async def test_check_shim_transitions_provisioning_on_busy(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await create_pool(session, project)
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

        instance = await create_instance(
            session, project, pool, status=InstanceStatus.PROVISIONING
        )
        instance.termination_deadline = get_current_datetime().replace(
            tzinfo=dt.timezone.utc
        ) + dt.timedelta(days=1)
        instance.health_status = "ssh connect problem"
        instance.job = job

        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.BUSY
        assert instance.termination_deadline is None
        assert instance.health_status is None
        assert instance.job == job

    @pytest.mark.asyncio
    async def test_check_shim_start_termination_deadline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool, status=InstanceStatus.IDLE)

        health_status = "SSH connection fail"
        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
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
    async def test_check_shim_stop_termination_deadline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool, status=InstanceStatus.IDLE)
        instance.termination_deadline = get_current_datetime() + dt.timedelta(minutes=19)
        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
        ) as healthcheck:
            healthcheck.return_value = HealthStatus(healthy=True, reason="OK")
            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.IDLE
        assert instance.termination_deadline is None
        assert instance.health_status is None

    @pytest.mark.asyncio
    async def test_check_shim_terminate_instance_by_dedaline(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool, status=InstanceStatus.IDLE)
        termination_deadline_time = get_current_datetime() + dt.timedelta(minutes=-19)
        instance.termination_deadline = termination_deadline_time
        await session.commit()

        health_status = "Not ok"
        with patch(
            "dstack._internal.server.background.tasks.process_instances.instance_healthcheck"
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


class TestIdleTime:
    @pytest.mark.asyncio
    async def test_terminate_by_idle_timeout(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool, status=InstanceStatus.IDLE)
        instance.termination_idle_time = 300
        instance.termination_policy = TerminationPolicy.DESTROY_AFTER_IDLE
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances.terminate_job_provisioning_data_instance"
        ):
            await terminate_idle_instance()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "Idle timeout"


class TestTerminate:
    @pytest.mark.asyncio
    async def test_terminate(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool, status=InstanceStatus.TERMINATING)

        reason = "some reason"
        instance.termination_reason = reason
        instance.last_job_processed_at = get_current_datetime() + dt.timedelta(minutes=-19)
        await session.commit()

        with patch(
            "dstack._internal.server.background.tasks.process_instances.backends_services.get_project_backends"
        ) as get_backends:
            backend = Mock()
            backend.TYPE = BackendType.DATACRUNCH
            backend.compute.return_value.terminate_instance.return_value = Mock()

            get_backends.return_value = [backend]

            await process_instances()

        await session.refresh(instance)

        assert instance is not None
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "some reason"
        assert instance.deleted == True
        assert instance.deleted_at is not None
        assert instance.finished_at is not None


class TestCreateInstance:
    @pytest.mark.asyncio
    async def test_create_instance(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)

        instance = await create_instance(session, project, pool)

        with patch(
            "dstack._internal.server.background.tasks.process_instances.get_create_instance_offers"
        ) as get_create_instance_offers:
            offer = InstanceOfferWithAvailability(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                ),
                region="us",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )

            backend_mock = Mock()
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.create_instance.return_value = LaunchedInstanceInfo(
                instance_id="instance_id",
                region="us",
                ip_address="1.1.1.1",
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
            )
            get_create_instance_offers.return_value = [(backend_mock, offer)]

            await task_create_instance(instance_id=instance.id)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_expire_retry_duration(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)
        profile = Profile(name="test_profile", retry_policy=RetryPolicy(retry=True, limit=123))
        instance = await create_instance(
            session, project, pool, profile=profile, status=InstanceStatus.TERMINATING
        )

        await task_create_instance(instance_id=instance.id)

        await session.refresh(instance)

        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == "The retry's duration expired"

    @pytest.mark.asyncio
    async def test_retry_delay(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        pool = await create_pool(session, project)
        profile = Profile(name="test_profile", retry_policy=RetryPolicy(retry=True, limit=123))
        print(profile.retry_policy)
        instance = await create_instance(
            session,
            project,
            pool,
            created_at=get_current_datetime(),
            profile=profile,
            status=InstanceStatus.TERMINATING,
        )

        last_retry = get_current_datetime() - dt.timedelta(seconds=10)
        instance.last_retry_at = last_retry
        session.add(instance)
        await session.commit()

        await task_create_instance(instance_id=instance.id)
        await session.refresh(instance)

        assert instance.last_retry_at.replace(tzinfo=dt.timezone.utc) == last_retry
