import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.runs import (
    JobErrorCode,
    JobProvisioningData,
    JobSpec,
    JobStatus,
    Requirements,
    RetryPolicy,
    RunSpec,
)
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import (
    BackendModel,
    GatewayModel,
    JobModel,
    ProjectModel,
    RepoModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services.jobs import get_job_specs_from_run_spec


def get_auth_headers(token: str) -> Dict:
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    session: AsyncSession,
    name: str = "test_user",
    global_role: GlobalRole = GlobalRole.ADMIN,
    token: Optional[str] = None,
) -> UserModel:
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        name=name,
        global_role=global_role,
        token=token,
    )
    session.add(user)
    await session.commit()
    return user


async def create_project(
    session: AsyncSession,
    name: str = "test_project",
    ssh_private_key: str = "",
    ssh_public_key: str = "",
) -> ProjectModel:
    project = ProjectModel(
        name=name,
        ssh_private_key=ssh_private_key,
        ssh_public_key=ssh_public_key,
    )
    session.add(project)
    await session.commit()
    return project


async def create_backend(
    session: AsyncSession,
    project_id: UUID,
    backend_type: BackendType = BackendType.AWS,
    config: Optional[Dict] = None,
    auth: Optional[Dict] = None,
) -> BackendModel:
    if config is None:
        config = {
            "regions": ["eu-west-1"],
        }
    if auth is None:
        auth = {
            "type": "access_key",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
        }
    backend = BackendModel(
        project_id=project_id,
        type=backend_type,
        config=json.dumps(config),
        auth=json.dumps(auth),
    )
    session.add(backend)
    await session.commit()
    return backend


async def create_repo(
    session: AsyncSession,
    project_id: UUID,
    repo_name: str = "test_repo",
    repo_type: RepoType = RepoType.REMOTE,
    info: Optional[Dict] = None,
    creds: Optional[Dict] = None,
) -> RepoModel:
    if info is None:
        info = {
            "repo_type": "remote",
            "repo_host_name": "github.com",
            "repo_port": None,
            "repo_user_name": "dstackai",
            "repo_name": "dstack",
        }
    if creds is None:
        creds = {
            "protocol": "https",
            "private_key": None,
            "oauth_token": "test_token",
        }
    repo = RepoModel(
        project_id=project_id,
        name=repo_name,
        type=repo_type,
        info=json.dumps(info),
        creds=json.dumps(creds),
    )
    session.add(repo)
    await session.commit()
    return repo


def get_run_spec(
    run_name: str,
    repo_id: str,
    profile: Optional[Profile] = Profile(name="default"),
) -> RunSpec:
    return RunSpec(
        run_name=run_name,
        repo_id=repo_id,
        repo_data=LocalRunRepoData(repo_dir="/"),
        repo_code_hash=None,
        working_dir=".",
        configuration_path="dstack.yaml",
        configuration=DevEnvironmentConfiguration(ide="vscode"),
        profile=profile,
        ssh_key_pub="",
    )


async def create_run(
    session: AsyncSession,
    project: ProjectModel,
    repo: RepoModel,
    user: UserModel,
    run_name: str = "test-run",
    status: JobStatus = JobStatus.SUBMITTED,
    submitted_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    run_spec: Optional[RunSpec] = None,
) -> RunModel:
    if run_spec is None:
        run_spec = get_run_spec(
            run_name=run_name,
            repo_id=repo.name,
        )
    run = RunModel(
        project_id=project.id,
        repo_id=repo.id,
        user_id=user.id,
        submitted_at=submitted_at,
        run_name=run_name,
        status=status,
        run_spec=run_spec.json(),
    )
    session.add(run)
    await session.commit()
    return run


async def create_job(
    session: AsyncSession,
    run: RunModel,
    submission_num: int = 0,
    status: JobStatus = JobStatus.SUBMITTED,
    submitted_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    error_code: Optional[JobErrorCode] = None,
    job_provisioning_data: Optional[JobProvisioningData] = None,
) -> JobModel:
    run_spec = RunSpec.parse_raw(run.run_spec)
    job_spec = get_job_specs_from_run_spec(run_spec)[0]
    if job_provisioning_data is not None:
        job_provisioning_data = job_provisioning_data.json()
    job = JobModel(
        project_id=run.project_id,
        run_id=run.id,
        run_name=run.run_name,
        job_num=0,
        job_name=run.run_name + "-0",
        submission_num=submission_num,
        submitted_at=submitted_at,
        last_processed_at=last_processed_at,
        status=status,
        error_code=error_code,
        job_spec_data=job_spec.json(),
        job_provisioning_data=job_provisioning_data,
    )
    session.add(job)
    await session.commit()
    return job


async def create_gateway(
    session: AsyncSession,
    project_id: UUID,
    backend_id: UUID,
    name: str = "test_gateway",
    ip_address: Optional[str] = "1.1.1.1",
    region: str = "us",
    instance_id: Optional[str] = "i-1234567890",
    wildcard_domain: Optional[str] = None,
) -> GatewayModel:
    async with session.begin():
        gateway = GatewayModel(
            project_id=project_id,
            backend_id=backend_id,
            name=name,
            ip_address=ip_address,
            region=region,
            instance_id=instance_id,
            wildcard_domain=wildcard_domain,
        )
        session.add(gateway)
    return gateway
