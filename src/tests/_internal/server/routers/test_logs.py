import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import create_project, create_user, get_auth_headers


class TestPollLogs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/logs/poll",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_logs(
        self, test_db, test_log_storage: FileLogStorage, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        runner_log_path = (
            test_log_storage.root
            / "projects"
            / project.name
            / "logs"
            / "test_run"
            / "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"
            / "runner.log"
        )
        runner_log_path.parent.mkdir(parents=True, exist_ok=True)
        runner_log_path.write_text(
            '{"timestamp": "2023-10-06T10:01:53.234234+00:00", "log_source": "stdout", "message": "Hello"}\n'
            '{"timestamp": "2023-10-06T10:01:53.234235+00:00", "log_source": "stdout", "message": "World"}\n'
            '{"timestamp": "2023-10-06T10:01:53.234236+00:00", "log_source": "stdout", "message": "!"}\n'
        )
        response = await client.post(
            f"/api/project/{project.name}/logs/poll",
            headers=get_auth_headers(user.token),
            json={
                "run_name": "test_run",
                "job_submission_id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
                "diagnose": True,
            },
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "logs": [
                {
                    "timestamp": "2023-10-06T10:01:53.234234+00:00",
                    "log_source": "stdout",
                    "message": "SGVsbG8=",
                },
                {
                    "timestamp": "2023-10-06T10:01:53.234235+00:00",
                    "log_source": "stdout",
                    "message": "V29ybGQ=",
                },
                {
                    "timestamp": "2023-10-06T10:01:53.234236+00:00",
                    "log_source": "stdout",
                    "message": "IQ==",
                },
            ],
            "next_token": None,
        }
        response = await client.post(
            f"/api/project/{project.name}/logs/poll",
            headers=get_auth_headers(user.token),
            json={
                "run_name": "test_run",
                "job_submission_id": "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
                "start_time": "2023-10-06T10:01:53.234235+00:00",
                "diagnose": True,
            },
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "logs": [
                {
                    "timestamp": "2023-10-06T10:01:53.234236+00:00",
                    "log_source": "stdout",
                    "message": "IQ==",
                },
            ],
            "next_token": None,
        }
