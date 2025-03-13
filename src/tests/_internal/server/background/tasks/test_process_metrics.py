from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server import settings
from dstack._internal.server.background.tasks.process_metrics import (
    collect_metrics,
    delete_metrics,
)
from dstack._internal.server.models import JobMetricsPoint
from dstack._internal.server.schemas.runner import GPUMetrics, MetricsResponse
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_job_metrics_point,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


class TestCollectMetrics:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_collects_metrics(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
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
            job_provisioning_data=get_job_provisioning_data(),
            instance_assigned=True,
            instance=instance,
        )
        with (
            patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock,
            patch(
                "dstack._internal.server.services.runner.client.RunnerClient"
            ) as RunnerClientMock,
        ):
            runner_client_mock = RunnerClientMock.return_value
            runner_client_mock.get_metrics.return_value = MetricsResponse(
                timestamp_micro=1,
                cpu_usage_micro=2,
                memory_usage_bytes=3,
                memory_working_set_bytes=4,
                gpus=[
                    GPUMetrics(
                        gpu_memory_usage_bytes=0,
                        gpu_util_percent=0,
                    )
                ],
            )
            await collect_metrics()
            SSHTunnelMock.assert_called_once()
            runner_client_mock.get_metrics.assert_called_once()
        res = await session.execute(select(JobMetricsPoint))
        metrics_point = res.scalar_one()
        assert metrics_point.job_id == job.id


class TestDeleteMetrics:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    async def test_deletes_old_metrics(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
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
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 10, tzinfo=timezone.utc),
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 20, tzinfo=timezone.utc),
        )
        last_metric = await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 5, 10, tzinfo=timezone.utc),
        )
        with patch.object(settings, "SERVER_METRICS_TTL_SECONDS", 15):
            await delete_metrics()
        res = await session.execute(select(JobMetricsPoint))
        points = res.scalars().all()
        assert len(points) == 1
        assert points[0].id == last_metric.id
