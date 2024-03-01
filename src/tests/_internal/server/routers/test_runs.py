import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobSpec, JobStatus, Requirements, RunSpec
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.schemas.runs import CreateInstanceRequest
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
)

client = TestClient(app)


def get_dev_env_run_plan_dict(
    project_name: str = "test_project",
    username: str = "test_user",
    run_name: str = "dry-run",
    repo_id: str = "test_repo",
    offers: List[InstanceOfferWithAvailability] = [],
    total_offers: int = 0,
    max_price: Optional[float] = None,
) -> Dict:
    return {
        "project_name": project_name,
        "user": username,
        "run_spec": {
            "configuration": {
                "entrypoint": None,
                "env": {},
                "home_dir": "/root",
                "ide": "vscode",
                "version": None,
                "image": None,
                "init": [],
                "ports": [],
                "python": "3.8",
                "registry_auth": None,
                "setup": [],
                "type": "dev-environment",
                "resources": {
                    "cpu": {"min": 2, "max": None},
                    "memory": {"min": 8.0, "max": None},
                    "disk": None,
                    "gpu": None,
                    "shm_size": None,
                },
            },
            "configuration_path": "dstack.yaml",
            "profile": {
                "backends": ["local", "aws", "azure", "gcp", "lambda"],
                "creation_policy": None,
                "default": False,
                "instance_name": None,
                "max_duration": "off",
                "max_price": None,
                "name": "string",
                "pool_name": DEFAULT_POOL_NAME,
                "retry_policy": {"limit": None, "retry": False},
                "spot_policy": "spot",
                "termination_idle_time": 300,
                "termination_policy": None,
            },
            "repo_code_hash": None,
            "repo_data": {"repo_dir": "/repo", "repo_type": "local"},
            "repo_id": repo_id,
            "run_name": run_name,
            "ssh_key_pub": "ssh_key",
            "working_dir": ".",
        },
        "job_plans": [
            {
                "job_spec": {
                    "app_specs": [],
                    "commands": [
                        "/bin/bash",
                        "-i",
                        "-c",
                        "(echo pip install ipykernel... && "
                        "pip install -q --no-cache-dir "
                        'ipykernel 2> /dev/null) || echo "no '
                        'pip, ipykernel was not installed" '
                        "&& echo '' && echo To open in VS "
                        "Code Desktop, use link below: && "
                        "echo '' && echo '  "
                        "vscode://vscode-remote/ssh-remote+dry-run/workflow' "
                        "&& echo '' && echo 'To connect via "
                        "SSH, use: `ssh dry-run`' && echo '' "
                        "&& echo -n 'To exit, press Ctrl+C.' "
                        "&& tail -f /dev/null",
                    ],
                    "env": {},
                    "gateway": None,
                    "home_dir": "/root",
                    "image_name": "dstackai/base:py3.8-0.4rc4-cuda-12.1",
                    "job_name": f"{run_name}-0",
                    "job_num": 0,
                    "max_duration": None,
                    "pool_name": DEFAULT_POOL_NAME,
                    "registry_auth": None,
                    "requirements": {
                        "resources": {
                            "cpu": {"min": 2, "max": None},
                            "memory": {"min": 8.0, "max": None},
                            "disk": None,
                            "gpu": None,
                            "shm_size": None,
                        },
                        "max_price": None,
                        "spot": True,
                    },
                    "retry_policy": {"limit": None, "retry": False},
                    "working_dir": ".",
                },
                "offers": [json.loads(o.json()) for o in offers],
                "total_offers": total_offers,
                "max_price": max_price,
            }
        ],
    }


def get_dev_env_run_dict(
    run_id: str = "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
    job_id: str = "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
    project_name: str = "test_project",
    username: str = "test_user",
    run_name: str = "run_name",
    repo_id: str = "test_repo",
    submitted_at: str = "2023-01-02T03:04:00+00:00",
    finished_at: str = "2023-01-02T03:04:00+00:00",
) -> Dict:
    return {
        "id": run_id,
        "project_name": project_name,
        "user": username,
        "submitted_at": submitted_at,
        "status": "submitted",
        "run_spec": {
            "configuration": {
                "entrypoint": None,
                "env": {},
                "home_dir": "/root",
                "ide": "vscode",
                "version": None,
                "image": None,
                "init": [],
                "ports": [],
                "python": "3.8",
                "registry_auth": None,
                "setup": [],
                "type": "dev-environment",
                "resources": {
                    "cpu": {"min": 2, "max": None},
                    "memory": {"min": 8.0, "max": None},
                    "disk": None,
                    "gpu": None,
                    "shm_size": None,
                },
            },
            "configuration_path": "dstack.yaml",
            "profile": {
                "backends": ["local", "aws", "azure", "gcp", "lambda"],
                "creation_policy": None,
                "default": False,
                "instance_name": None,
                "max_duration": "off",
                "max_price": None,
                "name": "string",
                "pool_name": DEFAULT_POOL_NAME,
                "retry_policy": {"limit": None, "retry": False},
                "spot_policy": "spot",
                "termination_idle_time": 300,
                "termination_policy": None,
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
                        "/bin/bash",
                        "-i",
                        "-c",
                        "(echo pip install ipykernel... && "
                        "pip install -q --no-cache-dir "
                        'ipykernel 2> /dev/null) || echo "no '
                        'pip, ipykernel was not installed" '
                        "&& echo '' && echo To open in VS "
                        "Code Desktop, use link below: && "
                        "echo '' && echo '  "
                        "vscode://vscode-remote/ssh-remote+test-run/workflow' "
                        "&& echo '' && echo 'To connect via "
                        "SSH, use: `ssh test-run`' && echo '' "
                        "&& echo -n 'To exit, press Ctrl+C.' "
                        "&& tail -f /dev/null",
                    ],
                    "env": {},
                    "gateway": None,
                    "home_dir": "/root",
                    "image_name": "dstackai/base:py3.8-0.4rc4-cuda-12.1",
                    "job_name": f"{run_name}-0",
                    "job_num": 0,
                    "max_duration": None,
                    "pool_name": DEFAULT_POOL_NAME,
                    "registry_auth": None,
                    "requirements": {
                        "resources": {
                            "cpu": {"min": 2, "max": None},
                            "memory": {"min": 8.0, "max": None},
                            "disk": None,
                            "gpu": None,
                            "shm_size": None,
                        },
                        "max_price": None,
                        "spot": True,
                    },
                    "retry_policy": {"limit": None, "retry": False},
                    "working_dir": ".",
                },
                "job_submissions": [
                    {
                        "id": job_id,
                        "submission_num": 0,
                        "submitted_at": submitted_at,
                        "finished_at": finished_at,
                        "status": "submitted",
                        "error_code": None,
                        "job_provisioning_data": None,
                    }
                ],
            }
        ],
        "latest_job_submission": {
            "id": job_id,
            "submission_num": 0,
            "submitted_at": submitted_at,
            "finished_at": finished_at,
            "status": "submitted",
            "error_code": None,
            "job_provisioning_data": None,
        },
        "cost": 0.0,
        "service": None,
    }


class TestListRuns:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/runs/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_lists_runs(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=submitted_at,
        )
        run_spec = RunSpec.parse_raw(run.run_spec)
        job = await create_job(
            session=session,
            run=run,
            submitted_at=submitted_at,
            last_processed_at=submitted_at,
        )
        job_spec = JobSpec.parse_raw(job.job_spec_data)
        response = client.post(
            "/api/runs/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "id": str(run.id),
                "project_name": project.name,
                "user": user.name,
                "submitted_at": submitted_at.isoformat(),
                "status": "submitted",
                "run_spec": run_spec.dict(),
                "jobs": [
                    {
                        "job_spec": job_spec.dict(),
                        "job_submissions": [
                            {
                                "id": str(job.id),
                                "submission_num": 0,
                                "submitted_at": "2023-01-02T03:04:00+00:00",
                                "finished_at": None,
                                "status": "submitted",
                                "error_code": None,
                                "job_provisioning_data": None,
                            }
                        ],
                    }
                ],
                "latest_job_submission": {
                    "id": str(job.id),
                    "submission_num": 0,
                    "submitted_at": "2023-01-02T03:04:00+00:00",
                    "finished_at": None,
                    "status": "submitted",
                    "error_code": None,
                    "job_provisioning_data": None,
                },
                "cost": 0,
                "service": None,
            }
        ]


class TestGetRunPlan:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/runs/get_plan",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_run_plan(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        offers = [
            InstanceOfferWithAvailability(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                ),
                region="us",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )
        ]
        run_plan_dict = get_dev_env_run_plan_dict(
            project_name=project.name,
            username=user.name,
            repo_id=repo.name,
            offers=offers,
            total_offers=1,
            max_price=1.0,
        )
        body = {"run_spec": run_plan_dict["run_spec"]}
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = offers
            response = client.post(
                f"/api/project/{project.name}/runs/get_plan",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == run_plan_dict


class TestSubmitRun:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_submits_run(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
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
            finished_at=None,
            run_name="test-run",
            repo_id=repo.name,
        )
        body = {"run_spec": run_dict["run_spec"]}
        with patch("uuid.uuid4") as uuid_mock, patch(
            "dstack._internal.utils.common.get_current_datetime"
        ) as datetime_mock, patch(
            "dstack._internal.server.services.backends.get_project_backends"
        ) as get_project_backends_mock:
            get_project_backends_mock.return_value = [Mock()]
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

    @pytest.mark.asyncio
    async def test_submits_run_without_run_name(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_dict = get_dev_env_run_dict(
            project_name=project.name,
            username=user.name,
            run_name=None,
            repo_id=repo.name,
        )
        body = {"run_spec": run_dict["run_spec"]}
        with patch("uuid.uuid4") as uuid_mock, patch(
            "dstack._internal.server.services.backends.get_project_backends"
        ) as get_project_backends_mock:
            get_project_backends_mock.return_value = [Mock()]
            uuid_mock.return_value = run_dict["id"]
            response = client.post(
                f"/api/project/{project.name}/runs/submit",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200
        assert response.json()["run_spec"]["run_name"] is not None
        res = await session.execute(select(RunModel))
        run = res.scalar()
        assert run is not None
        res = await session.execute(select(JobModel))
        job = res.scalar()
        assert job is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "run_name",
        [
            "run_with_underscores",
            "RunWithUppercase",
            "тест_ран",
        ],
    )
    async def test_returns_400_if_bad_run_name(
        self, test_db, session: AsyncSession, run_name: str
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_dict = get_dev_env_run_dict(
            project_name=project.name,
            username=user.name,
            run_name=run_name,
            repo_id=repo.name,
        )
        body = {"run_spec": run_dict["run_spec"]}
        with patch("uuid.uuid4") as uuid_mock, patch(
            "dstack._internal.server.services.backends.get_project_backends"
        ) as get_project_backends_mock:
            get_project_backends_mock.return_value = [Mock()]
            uuid_mock.return_value = run_dict["id"]
            response = client.post(
                f"/api/project/{project.name}/runs/submit",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_400_if_repo_does_not_exist(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        run_dict = get_dev_env_run_dict(
            project_name=project.name,
            username=user.name,
            repo_id="repo1234",
        )
        body = {"run_spec": run_dict["run_spec"]}
        response = client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400


class TestStopRuns:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_terminates_submitted_run(self, test_db, session: AsyncSession):
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
        response = client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name], "abort": False},
        )
        assert response.status_code == 200
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_terminates_running_run(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
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
            status=JobStatus.RUNNING,
        )
        with patch("dstack._internal.server.services.jobs._stop_runner") as stop_runner:
            response = client.post(
                f"/api/project/{project.name}/runs/stop",
                headers=get_auth_headers(user.token),
                json={"runs_names": [run.run_name], "abort": False},
            )
            stop_runner.assert_called_once()
        assert response.status_code == 200
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATED
        assert not job.removed

    @pytest.mark.asyncio
    async def test_leaves_finished_runs_unchanged(self, test_db, session: AsyncSession):
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
            status=JobStatus.FAILED,
        )
        response = client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name], "abort": False},
        )
        assert response.status_code == 200
        await session.refresh(job)
        assert job.status == JobStatus.FAILED


class TestDeleteRuns:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/runs/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_deletes_runs(self, test_db, session: AsyncSession):
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
            status=JobStatus.FAILED,
        )
        response = client.post(
            f"/api/project/{project.name}/runs/delete",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name]},
        )
        assert response.status_code == 200
        await session.refresh(run)
        assert run.deleted
        await session.refresh(job)
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_returns_400_if_runs_active(self, test_db, session: AsyncSession):
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
        await create_job(
            session=session,
            run=run,
        )
        response = client.post(
            f"/api/project/{project.name}/runs/delete",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name]},
        )
        assert response.status_code == 400
        res = await session.execute(select(RunModel))
        assert len(res.scalars().all()) == 1
        res = await session.execute(select(JobModel))
        assert len(res.scalars().all()) == 1


class TestCreateInstance:
    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = client.post(
            f"/api/project/{project.name}/runs/create_instance",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_creates_instance(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        request = CreateInstanceRequest(
            pool_name=DEFAULT_POOL_NAME,
            profile=Profile(name="test_profile"),
            requirements=Requirements(resources=ResourcesSpec(cpu=1)),
            ssh_key=SSHKey(public="test_public_key"),
        )
        with patch(
            "dstack._internal.server.services.runs.get_offers_by_requirements"
        ) as run_plan_by_req:
            offer = InstanceOfferWithAvailability(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                ),
                region="eu",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )
            backend = Mock()
            backend.compute.return_value.get_offers.return_value = [offer]
            backend.compute.return_value.create_instance.return_value = LaunchedInstanceInfo(
                instance_id="test_instance",
                region="eu",
                ip_address="127.0.0.1",
                username="ubuntu",
                ssh_port=22,
                dockerized=False,
            )
            backend.TYPE = BackendType.AWS
            run_plan_by_req.return_value = [(backend, offer)]
            response = client.post(
                f"/api/project/{project.name}/runs/create_instance",
                headers=get_auth_headers(user.token),
                json=request.dict(),
            )
            assert response.status_code == 200
            result = response.json()
            expected = {
                "backend": "aws",
                "instance_type": {
                    "name": "instance",
                    "resources": {
                        "cpus": 1,
                        "memory_mib": 512,
                        "gpus": [],
                        "spot": False,
                        "disk": {"size_mib": 102400},
                        "description": "",
                    },
                },
                "name": result["name"],
                "job_name": None,
                "job_status": None,
                "hostname": "127.0.0.1",
                "status": "provisioning",
                "created": result["created"],
                "region": "eu",
                "price": 1.0,
            }
            assert result == expected

    @pytest.mark.asyncio
    async def test_returns_400_if_backends_do_not_support_create_instance(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        request = CreateInstanceRequest(
            pool_name=DEFAULT_POOL_NAME,
            profile=Profile(name="test_profile"),
            requirements=Requirements(resources=ResourcesSpec(cpu=1)),
            ssh_key=SSHKey(public="test_public_key"),
        )
        with patch(
            "dstack._internal.server.services.runs.get_offers_by_requirements"
        ) as run_plan_by_req:
            offer = InstanceOfferWithAvailability(
                backend=BackendType.AZURE,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                ),
                region="eu",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )
            backend = Mock()
            backend.TYPE = BackendType.AZURE
            backend.compute.return_value.get_offers.return_value = [offer]
            backend.compute.return_value.create_instance.side_effect = NotImplementedError()
            run_plan_by_req.return_value = [(backend, offer)]
            response = client.post(
                f"/api/project/{project.name}/runs/create_instance",
                headers=get_auth_headers(user.token),
                json=request.dict(),
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_backend_does_not_support_create_instance(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        request = CreateInstanceRequest(
            pool_name=DEFAULT_POOL_NAME,
            profile=Profile(name="test_profile"),
            requirements=Requirements(resources=ResourcesSpec(cpu=1)),
            ssh_key=SSHKey(public="test_public_key"),
        )

        with patch(
            "dstack._internal.server.services.runs.get_offers_by_requirements"
        ) as run_plan_by_req:
            offers = InstanceOfferWithAvailability(
                backend=BackendType.VASTAI,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
                ),
                region="eu",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
            )

            backend = Mock()
            backend.TYPE = BackendType.VASTAI
            backend.compute.return_value.get_offers.return_value = [offers]
            backend.compute.return_value.create_instance.side_effect = NotImplementedError()
            run_plan_by_req.return_value = [(backend, offers)]

            response = client.post(
                f"/api/project/{project.name}/runs/create_instance",
                headers=get_auth_headers(user.token),
                json=request.dict(),
            )

            assert response.status_code == 400

            result = response.json()
            expected = {
                "detail": [
                    {
                        "msg": "Backends  do not support create_instance. Try to select other backends.",
                        "code": "error",
                    }
                ]
            }
            assert result == expected
