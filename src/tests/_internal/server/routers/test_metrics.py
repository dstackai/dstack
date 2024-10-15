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
)


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
        job = await create_job(
            session=session,
            run=run,
        )
        await create_job_metrics_point(
            session=session,
            job_model=job,
            timestamp=datetime(2023, 1, 2, 3, 4, 15, tzinfo=timezone.utc),
            cpu_usage_micro=4 * 1_000_000,
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
                    "name": "gpus_detected_num",
                    "timestamps": ["2023-01-02T03:04:25+00:00"],
                    "values": [1],
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
