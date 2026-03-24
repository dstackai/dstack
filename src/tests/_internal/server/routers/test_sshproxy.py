import os
from typing import Optional

import pytest
from httpx import AsyncClient
from pytest_unordered import unordered
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientErrorCode
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.runs import (
    JobStatus,
)
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    create_user_public_key,
    get_auth_headers,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_run_spec,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock", "test_db")
class TestGetUpstream:
    @pytest.fixture
    def token(self) -> str:
        token_var = "DSTACK_SSHPROXY_API_TOKEN"
        token = os.getenv(token_var)
        assert token is not None, f"{token_var} must be set via pytest-env"
        return token

    async def test_returns_40x_if_no_api_token_provided(self, client: AsyncClient):
        response = await client.post("/api/sshproxy/get_upstream")

        assert response.status_code in [401, 403]

    async def test_returns_40x_if_api_token_is_not_valid(self, client: AsyncClient):
        response = await client.post(
            "/api/sshproxy/get_upstream", headers=get_auth_headers("invalid-token")
        )

        assert response.status_code in [401, 403]

    async def test_returns_resource_not_exists_if_upstream_id_is_not_uuid(
        self, client: AsyncClient, token: str
    ):
        response = await client.post(
            "/api/sshproxy/get_upstream",
            headers=get_auth_headers(token),
            json={"id": "some-string"},
        )

        assert response.json()["detail"][0]["code"] == ServerClientErrorCode.RESOURCE_NOT_EXISTS

    async def test_returns_resource_not_exists_if_job_is_not_running(
        self,
        session: AsyncSession,
        client: AsyncClient,
        token: str,
    ):
        project = await create_project(session=session)
        instance = await create_instance(session=session, project=project)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(session=session, project=project, user=user, repo=repo)
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            status=JobStatus.TERMINATING,
        )

        response = await client.post(
            "/api/sshproxy/get_upstream",
            headers=get_auth_headers(token),
            json={"id": str(job.id)},
        )

        assert response.json()["detail"][0]["code"] == ServerClientErrorCode.RESOURCE_NOT_EXISTS

    async def test_response(
        self,
        session: AsyncSession,
        client: AsyncClient,
        token: str,
    ):
        project = await create_project(session=session, ssh_private_key="project-key")
        instance = await create_instance(
            session=session, project=project, backend=BackendType.RUNPOD
        )
        user = await create_user(session=session, ssh_public_key="user-key")
        await create_user_public_key(
            session=session, user=user, fingerprint="SHA256:fp1", key="user-uploaded-key-1"
        )
        await create_user_public_key(
            session=session, user=user, fingerprint="SHA256:fp2", key="user-uploaded-key-2"
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(repo_id=repo.name, ssh_key_pub="run-spec-key")
        run = await create_run(
            session=session, project=project, user=user, repo=repo, run_spec=run_spec
        )
        jpd = get_job_provisioning_data(
            dockerized=False,
            backend=BackendType.RUNPOD,
            hostname="100.100.100.100",
            username="root",
            ssh_port=32768,
            ssh_proxy=None,
        )
        jrd = get_job_runtime_data(username="test-user")
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
            job_runtime_data=jrd,
            status=JobStatus.RUNNING,
        )

        response = await client.post(
            "/api/sshproxy/get_upstream",
            headers=get_auth_headers(token),
            json={"id": str(job.id)},
        )

        assert response.json() == {
            "hosts": [
                {
                    "host": "100.100.100.100",
                    "port": 32768,
                    "private_key": "project-key",
                    "user": "test-user",
                },
            ],
            "authorized_keys": unordered(
                [
                    "user-key",
                    "user-uploaded-key-1",
                    "user-uploaded-key-2",
                    "run-spec-key",
                ]
            ),
        }

    @pytest.mark.parametrize(
        ["jrd_user", "conf_user", "expected_user"],
        [
            pytest.param("jrd", "conf", "jrd", id="from-runner"),
            pytest.param(None, "conf", "conf", id="from-configuration"),
            pytest.param(None, None, "root", id="default"),
        ],
    )
    async def test_username_fallbacks(
        self,
        session: AsyncSession,
        client: AsyncClient,
        token: str,
        jrd_user: Optional[str],
        conf_user: Optional[str],
        expected_user: str,
    ):
        project = await create_project(session=session, ssh_private_key="project-key")
        instance = await create_instance(session=session, project=project, backend=BackendType.AWS)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        configuration = DevEnvironmentConfiguration(ide="vscode", user=conf_user)
        run_spec = get_run_spec(repo_id=repo.name, configuration=configuration)
        run = await create_run(
            session=session, project=project, user=user, repo=repo, run_spec=run_spec
        )
        jpd = get_job_provisioning_data(dockerized=True, backend=BackendType.AWS, username="root")
        jrd = get_job_runtime_data(username=jrd_user)
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
            job_runtime_data=jrd,
            status=JobStatus.RUNNING,
        )

        response = await client.post(
            "/api/sshproxy/get_upstream",
            headers=get_auth_headers(token),
            json={"id": str(job.id)},
        )

        assert response.json()["hosts"][-1]["user"] == expected_user
