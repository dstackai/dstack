from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.background.tasks.process_prometheus_metrics import (
    collect_prometheus_metrics,
    delete_prometheus_metrics,
)
from dstack._internal.server.models import JobModel, JobPrometheusMetrics
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_job_prometheus_metrics,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestCollectPrometheusMetrics:
    @pytest_asyncio.fixture
    async def job(self, request: pytest.FixtureRequest, session: AsyncSession) -> JobModel:
        dockerized: bool
        marker = request.node.get_closest_marker("dockerized")
        if marker is None:
            dockerized = True
        else:
            dockerized = marker.args[0]
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
            job_provisioning_data=get_job_provisioning_data(dockerized=dockerized),
            instance_assigned=True,
            instance=instance,
        )
        return job

    @pytest.fixture
    def ssh_tunnel_mock(self) -> Generator[Mock, None, None]:
        with patch("dstack._internal.server.services.runner.ssh.SSHTunnel") as SSHTunnelMock:
            yield SSHTunnelMock

    @pytest.fixture
    def shim_client_mock(self) -> Generator[Mock, None, None]:
        with patch("dstack._internal.server.services.runner.client.ShimClient") as ShimClientMock:
            yield ShimClientMock.return_value

    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    async def test_inserts_new_record(
        self, session: AsyncSession, job: JobModel, ssh_tunnel_mock: Mock, shim_client_mock: Mock
    ):
        shim_client_mock.get_task_metrics.return_value = "# prom response"

        await collect_prometheus_metrics()

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.get_task_metrics.assert_called_once()
        res = await session.execute(
            select(JobPrometheusMetrics).where(JobPrometheusMetrics.job_id == job.id)
        )
        metrics = res.scalar_one()
        assert metrics.text == "# prom response"
        assert metrics.collected_at == datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc)

    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    async def test_updates_record(
        self, session: AsyncSession, job: JobModel, ssh_tunnel_mock: Mock, shim_client_mock: Mock
    ):
        metrics = await create_job_prometheus_metrics(
            session=session,
            job=job,
            collected_at=datetime(2023, 1, 2, 3, 5, 0),
            text="# prom old response",
        )
        shim_client_mock.get_task_metrics.return_value = "# prom new response"

        await collect_prometheus_metrics()

        ssh_tunnel_mock.assert_called_once()
        shim_client_mock.get_task_metrics.assert_called_once()
        res = await session.execute(
            select(JobPrometheusMetrics)
            .where(JobPrometheusMetrics.job_id == job.id)
            .execution_options(populate_existing=True)
        )
        metrics = res.scalar_one()
        assert metrics.text == "# prom new response"
        assert metrics.collected_at == datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc)

    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    async def test_skips_recently_updated(
        self, session: AsyncSession, job: JobModel, ssh_tunnel_mock: Mock, shim_client_mock: Mock
    ):
        metrics = await create_job_prometheus_metrics(
            session=session,
            job=job,
            collected_at=datetime(2023, 1, 2, 3, 5, 15),
            text="# prom old response",
        )
        shim_client_mock.get_task_metrics.return_value = "# prom new response"

        await collect_prometheus_metrics()

        ssh_tunnel_mock.assert_not_called()
        shim_client_mock.get_task_metrics.assert_not_called()
        res = await session.execute(
            select(JobPrometheusMetrics)
            .where(JobPrometheusMetrics.job_id == job.id)
            .execution_options(populate_existing=True)
        )
        metrics = res.scalar_one()
        assert metrics.text == "# prom old response"
        assert metrics.collected_at == datetime(2023, 1, 2, 3, 5, 15, tzinfo=timezone.utc)

    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    @pytest.mark.dockerized(False)
    async def test_skips_non_dockerized_jobs(
        self, session: AsyncSession, job: JobModel, ssh_tunnel_mock: Mock, shim_client_mock: Mock
    ):
        await collect_prometheus_metrics()

        ssh_tunnel_mock.assert_not_called()
        shim_client_mock.get_task_metrics.assert_not_called()
        res = await session.execute(
            select(JobPrometheusMetrics).where(JobPrometheusMetrics.job_id == job.id)
        )
        metrics = res.scalar_one_or_none()
        assert metrics is None


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestDeletePrometheusMetrics:
    @freeze_time(datetime(2023, 1, 2, 3, 5, 20, tzinfo=timezone.utc))
    async def test_deletes_old_metrics(self, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_1 = await create_run(
            session=session, project=project, repo=repo, user=user, run_name="run-1"
        )
        job_1 = await create_job(session=session, run=run_1)
        # old metrics
        await create_job_prometheus_metrics(
            session=session,
            job=job_1,
            collected_at=datetime(2023, 1, 2, 2, 3, 30),
        )
        run_2 = await create_run(
            session=session, project=project, repo=repo, user=user, run_name="run-2"
        )
        job_2 = await create_job(session=session, run=run_2)
        # recent metrics
        metrics_2 = await create_job_prometheus_metrics(
            session=session,
            job=job_2,
            collected_at=datetime(2023, 1, 2, 3, 5, 0),
        )

        await delete_prometheus_metrics()

        res = await session.execute(
            select(JobPrometheusMetrics).join(JobModel).where(JobModel.project_id == project.id)
        )
        all_metrics = res.scalars().all()
        assert len(all_metrics) == 1
        assert all_metrics[0] == metrics_2
