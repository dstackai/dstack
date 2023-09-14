import json
from typing import Dict
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import RepoModel
from dstack._internal.server.services.projects import add_project_member
from tests.server.common import create_project, create_repo, create_user, get_auth_headers

client = TestClient(app)


def get_run_spec(
    run_name: str = "run_name",
    repo_id: str = "test_repo",
) -> Dict:
    return {
        "run_name": run_name,
        "repo_id": repo_id,
        "repo_data": {
            "repo_type": "local",
            "repo_dir": "/repo",
        },
        "repo_code_hash": None,
        "configuration_path": "dstack.yaml",
        "configuration": {
            "type": "dev-environment",
            "image": None,
            "entrypoint": None,
            "home_dir": "/root",
            "registry_auth": None,
            "python": "3.7",
            "env": {},
            "build": [],
            "setup": [],
            "cache": [],
            "ports": [],
            "ide": "vscode",
            "init": [],
        },
        "profile": {
            "name": "string",
            "backends": ["local", "aws", "azure", "gcp", "lambda"],
            "resources": {
                "memory": 8192,
                "cpu": 2,
                "gpu": None,
                "shm_size": None,
            },
            "spot_policy": "spot",
            "retry_policy": {
                "retry": False,
                "limit": None,
            },
            "max_duration": "off",
            "max_price": None,
            "default": False,
        },
        "ssh_key_pub": "ssh_key",
    }


class TestSubmitRun:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        response = client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_submits_run(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(repo_id=repo.name)
        body = {"run_spec": run_spec}
        run_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        with patch("uuid.uuid4") as m:
            m.return_value = run_id
            response = client.post(
                f"/api/project/{project.name}/runs/submit",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "id": str(run_id),
            "project_name": project.name,
            "user": user.name,
            "run_spec": run_spec,
            "jobs": [],
        }

    @pytest.mark.asyncio
    async def test_returns_repos(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        response = client.post(
            f"/api/project/{project.name}/repos/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "repo_id": repo.name,
                "repo_info": json.loads(repo.info),
            }
        ]
