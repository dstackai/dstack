from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_job,
    create_job_metrics_point,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_job_runtime_data,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


class TestGetJobMetrics:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.get(
            f"/api/project/{project.name}/metrics/job/test",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_metrics(self, test_db, session: AsyncSession, client: AsyncClient):
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
        jpd = get_job_provisioning_data(
            cpu_count=128, memory_gib=256, gpu_count=2, gpu_memory_gib=32
        )
        offer = get_instance_offer_with_availability(
            cpu_count=64, memory_gib=128, gpu_count=1, gpu_memory_gib=32
        )
        jrd = get_job_runtime_data(offer=offer)
        job = await create_job(
            session=session,
            run=run,
            job_provisioning_data=jpd,
            job_runtime_data=jrd,
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            cpu_usage_micro=2 * 1_000_000,
            memory_usage_bytes=256,
            memory_working_set_bytes=128,
            gpus_memory_usage_bytes=[256],
            gpus_util_percent=[2],
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 15, tzinfo=timezone.utc),
            cpu_usage_micro=4 * 1_000_000,
            memory_usage_bytes=512,
            memory_working_set_bytes=256,
            gpus_memory_usage_bytes=[512],
            gpus_util_percent=[6],
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 25, tzinfo=timezone.utc),
            cpu_usage_micro=10 * 1_000_000,
            memory_usage_bytes=1024,
            memory_working_set_bytes=512,
            gpus_memory_usage_bytes=[1024],
            gpus_util_percent=[10],
        )
        response = await client.get(
            f"/api/project/{project.name}/metrics/job/{run.run_name}",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        # Returns one last sample by default. Filtering is tested in services/test_metrics.py
        assert response.json() == {
            "metrics": [
                {
                    "name": "cpu_usage_percent",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [60],
                },
                {
                    "name": "memory_usage_bytes",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [1024],
                },
                {
                    "name": "memory_working_set_bytes",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [512],
                },
                {
                    "name": "cpus_detected_num",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [64],
                },
                {
                    "name": "memory_total_bytes",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [137438953472],
                },
                {
                    "name": "gpus_detected_num",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [1],
                },
                {
                    "name": "gpu_memory_total_bytes",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [34359738368],
                },
                {
                    "name": "gpu_memory_usage_bytes_gpu0",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [1024],
                },
                {
                    "name": "gpu_util_percent_gpu0",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [10],
                },
            ]
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_ignores_deleted_runs(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        deleted_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            deleted=True,
        )
        active_run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
        )
        await create_job(session=session, run=deleted_run, job_num=0)
        await create_job(session=session, run=deleted_run, job_num=1)
        await create_job(session=session, run=active_run, job_num=0)
        response_job_0 = await client.get(
            f"/api/project/{project.name}/metrics/job/test-run",
            params={"job_num": 0},
            headers=get_auth_headers(user.token),
        )
        response_job_1 = await client.get(
            f"/api/project/{project.name}/metrics/job/test-run",
            params={"job_num": 1},
            headers=get_auth_headers(user.token),
        )
        # Only deleted_run has job_num=1, but it's deleted
        assert response_job_1.status_code == 400
        assert response_job_1.json()["detail"][0]["code"] == "resource_not_exists"
        # job_num=0 is taken from active_run
        assert response_job_0.status_code == 200
        assert response_job_0.json() == {"metrics": []}
