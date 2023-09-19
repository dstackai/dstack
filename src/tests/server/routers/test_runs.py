from datetime import datetime, timezone
from typing import Dict
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.services.projects import add_project_member
from tests.server.common import create_project, create_repo, create_user, get_auth_headers

client = TestClient(app)


def get_dev_env_run_dict(
    run_id: str,
    job_id: str,
    project_name: str,
    username: str,
    submitted_at: str,
    run_name: str = "run_name",
    repo_id: str = "test_repo",
) -> Dict:
    return {
        "id": run_id,
        "project_name": project_name,
        "user": username,
        "submitted_at": submitted_at,
        "run_spec": {
            "configuration": {
                "build": [],
                "cache": [],
                "entrypoint": None,
                "env": {},
                "home_dir": "/root",
                "ide": "vscode",
                "image": None,
                "init": [],
                "ports": [],
                "python": "3.7",
                "registry_auth": None,
                "setup": [],
                "type": "dev-environment",
            },
            "configuration_path": "dstack.yaml",
            "profile": {
                "backends": ["local", "aws", "azure", "gcp", "lambda"],
                "default": False,
                "max_duration": "off",
                "max_price": None,
                "name": "string",
                "resources": {"cpu": 2, "gpu": None, "memory": 8192, "shm_size": None},
                "retry_policy": {"limit": None, "retry": False},
                "spot_policy": "spot",
            },
            "repo_code_hash": None,
            "repo_data": {"repo_dir": "/repo", "repo_type": "local"},
            "repo_id": repo_id,
            "run_name": run_name,
            "ssh_key_pub": "ssh_key",
            "working_dir": ".",
        },
        "jobs": [
            {
                "job_spec": {
                    "app_specs": [],
                    "commands": [
                        "/usr/sbin/sshd -p 10022 " "-o " "PermitUserEnvironment=yes",
                        "cat",
                    ],
                    "entrypoint": ["/bin/bash", "-i", "-c"],
                    "env": {},
                    "gateway": None,
                    "home_dir": "/root",
                    "image_name": "dstackai/base:py3.7-0.4rc3-cuda-11.8",
                    "job_name": f"{run_name}-0",
                    "job_num": 0,
                    "max_duration": None,
                    "registry_auth": None,
                    "requirements": {
                        "cpus": 2,
                        "gpus": None,
                        "max_price": None,
                        "memory_mib": 8192,
                        "shm_size_mib": None,
                        "spot": True,
                    },
                    "retry_policy": {"limit": None, "retry": False},
                    "setup": [
                        "sed -i "
                        '"s/.*PasswordAuthentication.*/PasswordAuthentication '
                        'no/g" /etc/ssh/sshd_config',
                        "mkdir -p /run/sshd ~/.ssh",
                        "chmod 700 ~/.ssh",
                        "touch ~/.ssh/authorized_keys",
                        "chmod 600 " "~/.ssh/authorized_keys",
                        "rm -rf /etc/ssh/ssh_host_*",
                        'echo "ssh_key" >> ' "~/.ssh/authorized_keys",
                        "env >> ~/.ssh/environment",
                        'echo "export PATH=$PATH" >> ' "~/.profile",
                        "ssh-keygen -A > /dev/null",
                        "if [ ! -d "
                        '~/.vscode-server/bin/"1" ]; '
                        "then if [ $(uname -m) = "
                        '"aarch64" ]; then '
                        'arch="arm64"; else '
                        'arch="x64"; fi && mkdir -p '
                        "/tmp && wget -q "
                        "--show-progress "
                        '"https://update.code.visualstudio.com/commit:1/server-linux-$arch/stable" '
                        "-O "
                        '"/tmp/vscode-server-linux-$arch.tar.gz" '
                        "&& mkdir -vp "
                        '~/.vscode-server/bin/"1" && '
                        "tar --no-same-owner -xz "
                        "--strip-components=1 -C "
                        '~/.vscode-server/bin/"1" -f '
                        '"/tmp/vscode-server-linux-$arch.tar.gz" '
                        "&& rm "
                        '"/tmp/vscode-server-linux-$arch.tar.gz" '
                        "&& "
                        'PATH="$PATH":~/.vscode-server/bin/"1"/bin '
                        "code-server "
                        "--install-extension "
                        '"ms-python.python" '
                        "--install-extension "
                        '"ms-toolsai.jupyter"; fi',
                        "(pip install -q "
                        "--no-cache-dir ipykernel 2> "
                        '/dev/null) || echo "no pip, '
                        'ipykernel was not installed"',
                        "echo ''",
                        "echo To open in VS Code " "Desktop, use link below:",
                        "echo ''",
                        f"echo '  vscode://vscode-remote/ssh-remote+{run_name}/workflow'",
                        "echo ''",
                        f"echo 'To connect via SSH, use: `ssh {run_name}`'",
                        "echo ''",
                        "echo -n 'To exit, press " "Ctrl+C.'",
                    ],
                    "working_dir": ".",
                },
                "job_submissions": [
                    {
                        "id": job_id,
                        "submission_num": 0,
                        "submitted_at": submitted_at,
                        "status": "submitted",
                        "job_provisioning_data": None,
                    }
                ],
            }
        ],
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
        run_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        submitted_at_formatted = "2023-01-02T03:04:00+00:00"
        repo = await create_repo(session=session, project_id=project.id)
        run_dict = get_dev_env_run_dict(
            run_id=str(run_id),
            job_id=str(run_id),
            project_name=project.name,
            username=user.name,
            submitted_at=submitted_at_formatted,
            run_name="test-run",
            repo_id=repo.name,
        )
        body = {"run_spec": run_dict["run_spec"]}
        with patch("uuid.uuid4") as uuid_mock, patch(
            "dstack._internal.utils.common.get_current_datetime"
        ) as datetime_mock:
            uuid_mock.return_value = run_id
            datetime_mock.return_value = submitted_at
            response = client.post(
                f"/api/project/{project.name}/runs/submit",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == run_dict
        res = await session.execute(select(RunModel))
        run = res.scalar()
        assert run is not None
        res = await session.execute(select(JobModel))
        job = res.scalar()
        assert job is not None
