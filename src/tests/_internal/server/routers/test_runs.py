import copy
import json
from datetime import datetime, timezone
from typing import Dict, Generator, List, Optional, Tuple, Union
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
    ScalingSpec,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    ApplyRunPlanInput,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.core.models.volumes import InstanceMountPoint, MountPoint
from dstack._internal.server.main import app
from dstack._internal.server.models import JobModel, RunModel
from dstack._internal.server.schemas.runs import ApplyRunPlanRequest
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
    get_job_provisioning_data,
    get_run_spec,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")

client = TestClient(app)


def get_dev_env_run_plan_dict(
    project_name: str = "test_project",
    username: str = "test_user",
    run_name: str = "dry-run",
    repo_id: str = "test_repo",
    offers: List[InstanceOfferWithAvailability] = [],
    total_offers: int = 0,
    max_price: Optional[float] = None,
    action: ApplyAction = ApplyAction.CREATE,
    current_resource: Optional[Run] = None,
    privileged: bool = False,
    volumes: List[MountPoint] = [],
) -> Dict:
    run_spec = {
        "configuration": {
            "entrypoint": None,
            "env": {},
            "working_dir": None,
            "home_dir": "/root",
            "ide": "vscode",
            "inactivity_duration": None,
            "version": None,
            "image": None,
            "user": None,
            "shell": None,
            "privileged": privileged,
            "init": [],
            "ports": [],
            "python": "3.13",
            "nvcc": None,
            "registry_auth": None,
            "setup": [],
            "type": "dev-environment",
            "name": None,
            "resources": {
                "cpu": {"min": 2, "max": None},
                "memory": {"min": 8.0, "max": None},
                "disk": None,
                "gpu": None,
                "shm_size": None,
            },
            "volumes": [json.loads(v.json()) for v in volumes],
            "backends": ["local", "aws", "azure", "gcp", "lambda", "runpod"],
            "regions": ["us"],
            "availability_zones": None,
            "instance_types": None,
            "creation_policy": None,
            "single_branch": None,
            "max_duration": "off",
            "stop_duration": None,
            "max_price": None,
            "retry": None,
            "spot_policy": "spot",
            "idle_duration": None,
            "utilization_policy": None,
            "reservation": None,
            "fleets": None,
            "tags": None,
        },
        "configuration_path": "dstack.yaml",
        "profile": {
            "backends": ["local", "aws", "azure", "gcp", "lambda", "runpod"],
            "regions": ["us"],
            "availability_zones": None,
            "instance_types": None,
            "creation_policy": None,
            "default": False,
            "max_duration": "off",
            "stop_duration": None,
            "max_price": None,
            "name": "string",
            "retry": None,
            "spot_policy": "spot",
            "idle_duration": None,
            "utilization_policy": None,
            "reservation": None,
            "fleets": None,
            "tags": None,
        },
        "repo_code_hash": None,
        "repo_data": {"repo_dir": "/repo", "repo_type": "local"},
        "repo_id": repo_id,
        "run_name": run_name,
        "ssh_key_pub": "ssh_key",
        "working_dir": ".",
    }
    return {
        "project_name": project_name,
        "user": username,
        "run_spec": run_spec,
        "effective_run_spec": run_spec,
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
                    "home_dir": "/root",
                    "image_name": "dstackai/base:py3.13-0.7-cuda-12.1",
                    "user": None,
                    "privileged": privileged,
                    "job_name": f"{run_name}-0-0",
                    "replica_num": 0,
                    "job_num": 0,
                    "jobs_per_replica": 1,
                    "single_branch": False,
                    "max_duration": None,
                    "stop_duration": 300,
                    "utilization_policy": None,
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
                        "reservation": None,
                    },
                    "retry": None,
                    "volumes": volumes,
                    "ssh_key": None,
                    "working_dir": ".",
                },
                "offers": [json.loads(o.json()) for o in offers],
                "total_offers": total_offers,
                "max_price": max_price,
            }
        ],
        "current_resource": current_resource.dict() if current_resource else None,
        "action": action,
    }


def get_dev_env_run_dict(
    run_id: str = "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
    job_id: str = "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e",
    project_name: str = "test_project",
    username: str = "test_user",
    run_name: Optional[str] = "run_name",
    repo_id: str = "test_repo",
    submitted_at: str = "2023-01-02T03:04:00+00:00",
    last_processed_at: str = "2023-01-02T03:04:00+00:00",
    finished_at: Optional[str] = "2023-01-02T03:04:00+00:00",
    privileged: bool = False,
    deleted: bool = False,
) -> Dict:
    return {
        "id": run_id,
        "project_name": project_name,
        "user": username,
        "submitted_at": submitted_at,
        "last_processed_at": last_processed_at,
        "status": "submitted",
        "run_spec": {
            "configuration": {
                "entrypoint": None,
                "env": {},
                "home_dir": "/root",
                "working_dir": None,
                "ide": "vscode",
                "inactivity_duration": None,
                "version": None,
                "image": None,
                "user": None,
                "shell": None,
                "privileged": privileged,
                "init": [],
                "ports": [],
                "python": "3.13",
                "nvcc": None,
                "registry_auth": None,
                "setup": [],
                "name": None,
                "type": "dev-environment",
                "resources": {
                    "cpu": {"min": 2, "max": None},
                    "memory": {"min": 8.0, "max": None},
                    "disk": None,
                    "gpu": None,
                    "shm_size": None,
                },
                "volumes": [],
                "backends": ["local", "aws", "azure", "gcp", "lambda"],
                "regions": ["us"],
                "availability_zones": None,
                "instance_types": None,
                "creation_policy": None,
                "single_branch": None,
                "max_duration": "off",
                "stop_duration": None,
                "max_price": None,
                "retry": None,
                "spot_policy": "spot",
                "idle_duration": None,
                "utilization_policy": None,
                "reservation": None,
                "fleets": None,
                "tags": None,
            },
            "configuration_path": "dstack.yaml",
            "profile": {
                "backends": ["local", "aws", "azure", "gcp", "lambda"],
                "regions": ["us"],
                "availability_zones": None,
                "instance_types": None,
                "creation_policy": None,
                "default": False,
                "max_duration": "off",
                "stop_duration": None,
                "max_price": None,
                "name": "string",
                "retry": None,
                "spot_policy": "spot",
                "idle_duration": None,
                "utilization_policy": None,
                "reservation": None,
                "fleets": None,
                "tags": None,
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
                    "home_dir": "/root",
                    "image_name": "dstackai/base:py3.13-0.7-cuda-12.1",
                    "user": None,
                    "privileged": privileged,
                    "job_name": f"{run_name}-0-0",
                    "replica_num": 0,
                    "job_num": 0,
                    "jobs_per_replica": 1,
                    "single_branch": False,
                    "max_duration": None,
                    "stop_duration": 300,
                    "utilization_policy": None,
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
                        "reservation": None,
                    },
                    "retry": None,
                    "volumes": [],
                    "ssh_key": None,
                    "working_dir": ".",
                },
                "job_submissions": [
                    {
                        "id": job_id,
                        "submission_num": 0,
                        "submitted_at": submitted_at,
                        "last_processed_at": last_processed_at,
                        "finished_at": finished_at,
                        "inactivity_secs": None,
                        "status": "submitted",
                        "termination_reason": None,
                        "termination_reason_message": None,
                        "job_provisioning_data": None,
                        "job_runtime_data": None,
                    }
                ],
            }
        ],
        "latest_job_submission": {
            "id": job_id,
            "submission_num": 0,
            "submitted_at": submitted_at,
            "last_processed_at": last_processed_at,
            "inactivity_secs": None,
            "finished_at": finished_at,
            "status": "submitted",
            "termination_reason": None,
            "termination_reason_message": None,
            "job_provisioning_data": None,
            "job_runtime_data": None,
        },
        "cost": 0.0,
        "service": None,
        "termination_reason": None,
        "error": "",
        "deleted": deleted,
    }


def get_service_run_spec(
    repo_id: str,
    run_name: Optional[str] = None,
    gateway: Optional[Union[bool, str]] = None,
) -> dict:
    return {
        "configuration": {
            "type": "service",
            "commands": ["python -m http.server"],
            "port": 8000,
            "gateway": gateway,
            "model": "test-model",
        },
        "configuration_path": "dstack.yaml",
        "profile": {
            "name": "string",
        },
        "repo_code_hash": None,
        "repo_data": {"repo_dir": "/repo", "repo_type": "local"},
        "repo_id": repo_id,
        "run_name": run_name,
        "ssh_key_pub": "ssh_key",
        "working_dir": ".",
    }


class TestListRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/runs/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_runs(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run1_submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        run1 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=run1_submitted_at,
        )
        run1_spec = RunSpec.parse_raw(run1.run_spec)
        job = await create_job(
            session=session,
            run=run1,
            submitted_at=run1_submitted_at,
            last_processed_at=run1_submitted_at,
        )
        job_spec = JobSpec.parse_raw(job.job_spec_data)
        run2_submitted_at = datetime(2023, 1, 1, 3, 4, tzinfo=timezone.utc)
        run2 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=run2_submitted_at,
        )
        run2_spec = RunSpec.parse_raw(run2.run_spec)
        response = await client.post(
            "/api/runs/list",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 200, response.json()
        assert response.json() == [
            {
                "id": str(run1.id),
                "project_name": project.name,
                "user": user.name,
                "submitted_at": run1_submitted_at.isoformat(),
                "last_processed_at": run1_submitted_at.isoformat(),
                "status": "submitted",
                "run_spec": run1_spec.dict(),
                "jobs": [
                    {
                        "job_spec": job_spec.dict(),
                        "job_submissions": [
                            {
                                "id": str(job.id),
                                "submission_num": 0,
                                "submitted_at": run1_submitted_at.isoformat(),
                                "last_processed_at": run1_submitted_at.isoformat(),
                                "finished_at": None,
                                "inactivity_secs": None,
                                "status": "submitted",
                                "termination_reason": None,
                                "termination_reason_message": None,
                                "job_provisioning_data": None,
                                "job_runtime_data": None,
                            }
                        ],
                    }
                ],
                "latest_job_submission": {
                    "id": str(job.id),
                    "submission_num": 0,
                    "submitted_at": run1_submitted_at.isoformat(),
                    "last_processed_at": run1_submitted_at.isoformat(),
                    "finished_at": None,
                    "inactivity_secs": None,
                    "status": "submitted",
                    "termination_reason_message": None,
                    "termination_reason": None,
                    "job_provisioning_data": None,
                    "job_runtime_data": None,
                },
                "cost": 0,
                "service": None,
                "termination_reason": None,
                "error": "",
                "deleted": False,
            },
            {
                "id": str(run2.id),
                "project_name": project.name,
                "user": user.name,
                "submitted_at": run2_submitted_at.isoformat(),
                "last_processed_at": run2_submitted_at.isoformat(),
                "status": "submitted",
                "run_spec": run2_spec.dict(),
                "jobs": [],
                "latest_job_submission": None,
                "cost": 0,
                "service": None,
                "termination_reason": None,
                "error": "",
                "deleted": False,
            },
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_runs_pagination(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run1 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=datetime(2023, 1, 2, 1, 4, tzinfo=timezone.utc),
            run_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0b"),
        )
        run2 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=datetime(2023, 1, 2, 1, 4, tzinfo=timezone.utc),
            run_id=UUID("2b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0b"),
        )
        run3 = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            submitted_at=datetime(2023, 1, 2, 5, 15, tzinfo=timezone.utc),
        )
        response1 = await client.post(
            "/api/runs/list",
            headers=get_auth_headers(user.token),
            json={"limit": 2},
        )
        response1_json = response1.json()
        assert response1.status_code == 200, response1_json
        assert len(response1_json) == 2
        assert response1_json[0]["id"] == str(run3.id)
        assert response1_json[1]["id"] == str(run1.id)
        response2 = await client.post(
            "/api/runs/list",
            headers=get_auth_headers(user.token),
            json={
                "limit": 2,
                "prev_submitted_at": str(run1.submitted_at),
                "prev_run_id": str(run1.id),
            },
        )
        response2_json = response2.json()
        assert response2.status_code == 200, response2_json
        assert len(response2_json) == 1
        assert response2_json[0]["id"] == str(run2.id)


class TestGetRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/get",
            headers=get_auth_headers(user.token),
            json={"run_name": "myrun"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_run_given_name(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
        response = await client.post(
            f"/api/project/{project.name}/runs/get",
            headers=get_auth_headers(user.token),
            json={"run_name": "nonexistent_run_name"},
        )
        assert response.status_code == 400
        response = await client.post(
            f"/api/project/{project.name}/runs/get",
            headers=get_auth_headers(user.token),
            json={"run_name": run.run_name},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["id"] == str(run.id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_deleted_run_given_id(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
            deleted=True,
        )
        response = await client.post(
            f"/api/project/{project.name}/runs/get",
            headers=get_auth_headers(user.token),
            json={"id": str(run.id)},
        )
        assert response.status_code == 200, response.json()
        assert response.json()["id"] == str(run.id)


class TestGetRunPlan:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/get_plan",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("privileged", [None, False])
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_run_plan_privileged_false(
        self, test_db, session: AsyncSession, client: AsyncClient, privileged: Optional[bool]
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        offer_aws = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=1.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        offer_runpod = InstanceOfferWithAvailability(
            backend=BackendType.RUNPOD,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=2.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        run_plan_dict = get_dev_env_run_plan_dict(
            project_name=project.name,
            username=user.name,
            repo_id=repo.name,
            offers=[offer_aws, offer_runpod],
            total_offers=2,
            max_price=2.0,
            privileged=False,
        )
        run_spec = copy.deepcopy(run_plan_dict["run_spec"])
        if privileged is None:
            del run_spec["configuration"]["privileged"]
        body = {"run_spec": run_spec}
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock_aws = Mock()
            backend_mock_aws.TYPE = BackendType.AWS
            backend_mock_aws.compute.return_value.get_offers_cached.return_value = [offer_aws]
            backend_mock_runpod = Mock()
            backend_mock_runpod.TYPE = BackendType.RUNPOD
            backend_mock_runpod.compute.return_value.get_offers_cached.return_value = [
                offer_runpod
            ]
            m.return_value = [backend_mock_aws, backend_mock_runpod]
            response = await client.post(
                f"/api/project/{project.name}/runs/get_plan",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == run_plan_dict

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_run_plan_privileged_true(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        offer_aws = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=1.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        offer_runpod = InstanceOfferWithAvailability(
            backend=BackendType.RUNPOD,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=2.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        run_plan_dict = get_dev_env_run_plan_dict(
            project_name=project.name,
            username=user.name,
            repo_id=repo.name,
            offers=[offer_aws],
            total_offers=1,
            max_price=1.0,
            privileged=True,
        )
        body = {"run_spec": run_plan_dict["run_spec"]}
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock_aws = Mock()
            backend_mock_aws.TYPE = BackendType.AWS
            backend_mock_aws.compute.return_value.get_offers_cached.return_value = [offer_aws]
            backend_mock_runpod = Mock()
            backend_mock_runpod.TYPE = BackendType.RUNPOD
            backend_mock_runpod.compute.return_value.get_offers_cached.return_value = [
                offer_runpod
            ]
            m.return_value = [backend_mock_aws, backend_mock_runpod]
            response = await client.post(
                f"/api/project/{project.name}/runs/get_plan",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == run_plan_dict

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_run_plan_instance_volumes(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        offer_aws = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=1.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        offer_runpod = InstanceOfferWithAvailability(
            backend=BackendType.RUNPOD,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=2.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        run_plan_dict = get_dev_env_run_plan_dict(
            project_name=project.name,
            username=user.name,
            repo_id=repo.name,
            offers=[offer_aws],
            total_offers=1,
            max_price=1.0,
            volumes=[InstanceMountPoint.parse("/data:/data")],
        )
        body = {"run_spec": run_plan_dict["run_spec"]}
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock_aws = Mock()
            backend_mock_aws.TYPE = BackendType.AWS
            backend_mock_aws.compute.return_value.get_offers_cached.return_value = [offer_aws]
            backend_mock_runpod = Mock()
            backend_mock_runpod.TYPE = BackendType.RUNPOD
            backend_mock_runpod.compute.return_value.get_offers_cached.return_value = [
                offer_runpod
            ]
            m.return_value = [backend_mock_aws, backend_mock_runpod]
            response = await client.post(
                f"/api/project/{project.name}/runs/get_plan",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == run_plan_dict

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("old_conf", "new_conf", "action"),
        [
            pytest.param(
                ServiceConfiguration(
                    commands=["one", "two"],
                    port=80,
                    replicas=1,
                    scaling=None,
                ),
                ServiceConfiguration(
                    commands=["one", "two"],
                    port=80,
                    replicas="2..4",
                    scaling=ScalingSpec(metric="rps", target=5),
                ),
                "update",
                id="update-service",
            ),
            pytest.param(
                ServiceConfiguration(
                    commands=["one", "two"],
                    port=80,
                    replicas=1,
                    scaling=None,
                ),
                ServiceConfiguration(
                    commands=["one", "two"],
                    port=8080,  # not updatable
                    replicas="2..4",
                    scaling=ScalingSpec(metric="rps", target=5),
                ),
                "create",
                id="no-update-service",
            ),
            pytest.param(
                DevEnvironmentConfiguration(ide="vscode", inactivity_duration=False),
                DevEnvironmentConfiguration(ide="vscode", inactivity_duration="30m"),
                "update",
                id="update-dev-env",
            ),
            pytest.param(
                TaskConfiguration(image="test-image-1"),
                TaskConfiguration(image="test-image-2"),
                "create",
                id="no-update-task",
            ),
            pytest.param(
                DevEnvironmentConfiguration(ide="vscode", image="test-image"),
                TaskConfiguration(image="test-image"),
                "create",
                id="no-update-on-type-change",
            ),
        ],
    )
    async def test_returns_update_or_create_action_on_conf_change(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        old_conf: AnyRunConfiguration,
        new_conf: AnyRunConfiguration,
        action: str,
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(run_name="test-run", repo_id=repo.name, configuration=old_conf)
        run_model = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_spec.run_name,
            run_spec=run_spec,
        )
        run = run_model_to_run(run_model)
        run_spec.configuration = new_conf
        response = await client.post(
            f"/api/project/{project.name}/runs/get_plan",
            headers=get_auth_headers(user.token),
            json={"run_spec": run_spec.dict()},
        )
        assert response.status_code == 200
        response_json = response.json()
        assert response_json["action"] == action
        assert response_json["current_resource"] == json.loads(run.json())


class TestApplyPlan:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/apply",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_submits_new_run_if_no_current_resource(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        run_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        submitted_at_formatted = "2023-01-02T03:04:00+00:00"
        last_processed_at_formatted = submitted_at_formatted
        repo = await create_repo(session=session, project_id=project.id)
        run_dict = get_dev_env_run_dict(
            run_id=str(run_id),
            job_id=str(run_id),
            project_name=project.name,
            username=user.name,
            submitted_at=submitted_at_formatted,
            last_processed_at=last_processed_at_formatted,
            finished_at=None,
            run_name="test-run",
            repo_id=repo.name,
        )
        with (
            patch("uuid.uuid4") as uuid_mock,
            patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock,
        ):
            uuid_mock.return_value = run_id
            datetime_mock.return_value = submitted_at
            response = await client.post(
                f"/api/project/{project.name}/runs/apply",
                headers=get_auth_headers(user.token),
                json={
                    "plan": {
                        "run_spec": run_dict["run_spec"],
                        "current_resource": None,
                    },
                    "force": False,
                },
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
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_run(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            run_name="test-service",
            repo_id=repo.name,
            configuration=ServiceConfiguration(
                type="service",
                commands=["one", "two"],
                port=80,
                replicas=1,
            ),
        )
        run_model = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_spec.run_name,
            run_spec=run_spec,
        )
        run = run_model_to_run(run_model)
        run_spec.configuration.replicas = 2
        response = await client.post(
            f"/api/project/{project.name}/runs/apply",
            headers=get_auth_headers(user.token),
            # Call json.loads to serialize UUID
            json=json.loads(
                ApplyRunPlanRequest(
                    plan=ApplyRunPlanInput(
                        run_spec=run_spec,
                        current_resource=run,
                    ),
                    force=False,
                ).json()
            ),
        )
        assert response.status_code == 200, response.json()
        await session.refresh(run_model)
        updated_run = run_model_to_run(run_model)
        assert updated_run.run_spec.configuration.replicas == Range(min=2, max=2)


class TestSubmitRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("privileged", [None, False, True])
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_submits_run(
        self, test_db, session: AsyncSession, client: AsyncClient, privileged: Optional[bool]
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        run_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        submitted_at = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        submitted_at_formatted = "2023-01-02T03:04:00+00:00"
        last_processed_at_formatted = submitted_at_formatted
        repo = await create_repo(session=session, project_id=project.id)
        run_dict = get_dev_env_run_dict(
            run_id=str(run_id),
            job_id=str(run_id),
            project_name=project.name,
            username=user.name,
            submitted_at=submitted_at_formatted,
            last_processed_at=last_processed_at_formatted,
            finished_at=None,
            run_name="test-run",
            repo_id=repo.name,
            privileged=bool(privileged),
        )
        run_spec = copy.deepcopy(run_dict["run_spec"])
        if privileged is None:
            del run_spec["configuration"]["privileged"]
        body = {"run_spec": run_spec}
        with (
            patch("uuid.uuid4") as uuid_mock,
            patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock,
        ):
            uuid_mock.return_value = run_id
            datetime_mock.return_value = submitted_at
            response = await client.post(
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
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_submits_run_without_run_name(
        self, test_db, session: AsyncSession, client: AsyncClient
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
            run_name=None,
            repo_id=repo.name,
        )
        body = {"run_spec": run_dict["run_spec"]}
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = run_dict["id"]
            response = await client.post(
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
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "run_name",
        [
            "run_with_underscores",
            "RunWithUppercase",
            "тест_ран",
        ],
    )
    async def test_returns_400_if_bad_run_name(
        self, test_db, session: AsyncSession, client: AsyncClient, run_name: str
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
        with patch("uuid.uuid4") as uuid_mock:
            uuid_mock.return_value = run_dict["id"]
            response = await client.post(
                f"/api/project/{project.name}/runs/submit",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_repo_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
        response = await client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400


class TestStopRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminates_submitted_run(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
        response = await client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name], "abort": False},
        )
        assert response.status_code == 200
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.STOPPED_BY_USER
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_USER

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminates_running_run(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
            status=RunStatus.RUNNING,
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            job_provisioning_data=get_job_provisioning_data(),
            status=JobStatus.RUNNING,
            instance=instance,
            instance_assigned=True,
        )
        with patch("dstack._internal.server.services.jobs._stop_runner") as stop_runner:
            response = await client.post(
                f"/api/project/{project.name}/runs/stop",
                headers=get_auth_headers(user.token),
                json={"runs_names": [run.run_name], "abort": False},
            )
            stop_runner.assert_called_once()
        assert response.status_code == 200
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.STOPPED_BY_USER
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_USER

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_leaves_finished_runs_unchanged(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
            status=RunStatus.FAILED,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
        )
        response = await client.post(
            f"/api/project/{project.name}/runs/stop",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name], "abort": False},
        )
        assert response.status_code == 200
        await session.refresh(job)
        assert job.status == JobStatus.FAILED


class TestDeleteRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/runs/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_runs(self, test_db, session: AsyncSession, client: AsyncClient):
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
            status=RunStatus.FAILED,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
        )
        session.add(run)
        await session.commit()
        response = await client.post(
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
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_runs_active(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
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
        response = await client.post(
            f"/api/project/{project.name}/runs/delete",
            headers=get_auth_headers(user.token),
            json={"runs_names": [run.run_name]},
        )
        assert response.status_code == 400
        res = await session.execute(select(RunModel))
        assert len(res.scalars().all()) == 1
        res = await session.execute(select(JobModel))
        assert len(res.scalars().all()) == 1


@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestSubmitService:
    @pytest.fixture(autouse=True)
    def mock_gateway_connections(self) -> Generator[None, None, None]:
        with patch(
            "dstack._internal.server.services.gateways.gateway_connections_pool.get_or_add"
        ) as get_conn_mock:
            get_conn_mock.return_value.client = Mock()
            get_conn_mock.return_value.client.return_value = AsyncMock()
            yield

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        (
            "existing_gateways",
            "specified_gateway_in_run_conf",
            "expected_service_url",
            "expected_model_url",
        ),
        [
            pytest.param(
                [("default-gateway", True), ("non-default-gateway", False)],
                None,
                "https://test-service.default-gateway.example",
                "https://gateway.default-gateway.example",
                id="submits-to-default-gateway",
            ),
            pytest.param(
                [("default-gateway", True), ("non-default-gateway", False)],
                "non-default-gateway",
                "https://test-service.non-default-gateway.example",
                "https://gateway.non-default-gateway.example",
                id="submits-to-specified-gateway",
            ),
            pytest.param(
                [("non-default-gateway", False)],
                None,
                "/proxy/services/test-project/test-service/",
                "/proxy/models/test-project/",
                id="submits-in-server-when-no-default-gateway",
            ),
            pytest.param(
                [("default-gateway", True)],
                False,
                "/proxy/services/test-project/test-service/",
                "/proxy/models/test-project/",
                id="submits-in-server-when-specified",
            ),
        ],
    )
    async def test_submit_to_correct_proxy(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        existing_gateways: List[Tuple[str, bool]],
        specified_gateway_in_run_conf: str,
        expected_service_url: str,
        expected_model_url: str,
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user, name="test-project")
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        backend = await create_backend(session=session, project_id=project.id)
        for gateway_name, is_default in existing_gateways:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
            )
            gateway = await create_gateway(
                session=session,
                project_id=project.id,
                backend_id=backend.id,
                gateway_compute_id=gateway_compute.id,
                status=GatewayStatus.RUNNING,
                name=gateway_name,
                wildcard_domain=f"{gateway_name}.example",
            )
            if is_default:
                project.default_gateway_id = gateway.id
                await session.commit()
        run_spec = get_service_run_spec(
            repo_id=repo.name,
            run_name="test-service",
            gateway=specified_gateway_in_run_conf,
        )
        response = await client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
            json={"run_spec": run_spec},
        )
        assert response.status_code == 200
        assert response.json()["service"]["url"] == expected_service_url
        assert response.json()["service"]["model"]["base_url"] == expected_model_url

    @pytest.mark.asyncio
    async def test_return_error_if_specified_gateway_not_exists(
        self, test_db, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_service_run_spec(repo_id=repo.name, gateway="nonexistent")
        response = await client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
            json={"run_spec": run_spec},
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": [
                {"msg": "Gateway nonexistent does not exist", "code": "resource_not_exists"}
            ]
        }

    @pytest.mark.asyncio
    async def test_return_error_if_specified_gateway_is_true(
        self, test_db, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_service_run_spec(repo_id=repo.name, gateway=True)
        response = await client.post(
            f"/api/project/{project.name}/runs/submit",
            headers=get_auth_headers(user.token),
            json={"run_spec": run_spec},
        )
        assert response.status_code == 422
        assert "must be a string or boolean `false`, not boolean `true`" in response.text
