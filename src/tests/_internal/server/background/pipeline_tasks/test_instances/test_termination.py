import datetime as dt
from contextlib import contextmanager
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import BackendError, NotYetTerminated
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus, InstanceTerminationReason
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.background.pipeline_tasks.instances import (
    termination as instances_termination,
)
from dstack._internal.server.testing.common import create_instance, create_project
from tests._internal.server.background.pipeline_tasks.test_instances.helpers import (
    instance_to_pipeline_item,
    lock_instance,
    process_instance,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestTermination:
    @staticmethod
    @contextmanager
    def mock_terminate_in_backend(error: Optional[Exception] = None):
        backend = Mock()
        backend.TYPE = BackendType.VERDA
        terminate_instance = backend.compute.return_value.terminate_instance
        if error is not None:
            terminate_instance.side_effect = error
        with patch.object(
            instances_termination.backends_services,
            "get_project_backend_by_type",
            AsyncMock(return_value=backend),
        ):
            yield terminate_instance

    async def test_terminate(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            minutes=-19
        )
        await session.commit()

        with self.mock_terminate_in_backend() as mock:
            await process_instance(session, worker, instance)
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
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATING,
        )
        lock_instance(instance)
        await session.commit()
        item = instance_to_pipeline_item(instance)
        instance.deleted = True
        instance.termination_reason = InstanceTerminationReason.IDLE_TIMEOUT
        instance.last_job_processed_at = instance.deleted_at = dt.datetime.now(
            dt.timezone.utc
        ) + dt.timedelta(minutes=-19)
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
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            freeze_time(initial_time + dt.timedelta(minutes=2)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED

    async def test_terminate_not_retries_if_too_early(
        self,
        test_db,
        session: AsyncSession,
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
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        instance.last_processed_at = initial_time
        await session.commit()

        with (
            freeze_time(initial_time + dt.timedelta(minutes=1, seconds=11)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_not_called()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

    async def test_terminate_on_termination_deadline(
        self,
        test_db,
        session: AsyncSession,
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
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATING

        with (
            freeze_time(initial_time + dt.timedelta(minutes=15, seconds=55)),
            self.mock_terminate_in_backend(error=None) as mock,
        ):
            await process_instance(session, worker, instance)
            mock.assert_called_once()
        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
