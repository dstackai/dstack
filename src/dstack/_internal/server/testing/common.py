import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
)
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.core.models.instances import InstanceConfiguration, InstanceType, Resources
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_NAME,
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    Profile,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.resources import Memory, ResourcesSpec
from dstack._internal.core.models.runs import (
    InstanceStatus,
    JobProvisioningData,
    JobStatus,
    JobTerminationReason,
    Requirements,
    RunSpec,
    RunStatus,
)
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import (
    VolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.server.models import (
    BackendModel,
    GatewayComputeModel,
    GatewayModel,
    InstanceModel,
    JobModel,
    PoolModel,
    ProjectModel,
    RepoModel,
    RunModel,
    UserModel,
    VolumeModel,
)
from dstack._internal.server.services.jobs import get_job_specs_from_run_spec


def get_auth_headers(token: str) -> Dict:
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    session: AsyncSession,
    name: str = "test_user",
    global_role: GlobalRole = GlobalRole.ADMIN,
    token: Optional[str] = None,
    email: Optional[str] = None,
) -> UserModel:
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        name=name,
        global_role=global_role,
        token=token,
        email=email,
    )
    session.add(user)
    await session.commit()
    return user


async def create_project(
    session: AsyncSession,
    owner: Optional[UserModel] = None,
    name: str = "test_project",
    ssh_private_key: str = "",
    ssh_public_key: str = "",
) -> ProjectModel:
    if owner is None:
        owner = await create_user(session=session, name="test_owner")
    project = ProjectModel(
        name=name,
        owner_id=owner.id,
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
    profile: Optional[Profile] = None,
    configuration: Optional[AnyRunConfiguration] = None,
) -> RunSpec:
    if profile is None:
        profile = Profile(name="default")
    return RunSpec(
        run_name=run_name,
        repo_id=repo_id,
        repo_data=LocalRunRepoData(repo_dir="/"),
        repo_code_hash=None,
        working_dir=".",
        configuration_path="dstack.yaml",
        configuration=configuration or DevEnvironmentConfiguration(ide="vscode"),
        profile=profile,
        ssh_key_pub="user_ssh_key",
    )


async def create_run(
    session: AsyncSession,
    project: ProjectModel,
    repo: RepoModel,
    user: UserModel,
    run_name: str = "test-run",
    status: RunStatus = RunStatus.SUBMITTED,
    submitted_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    run_spec: Optional[RunSpec] = None,
    run_id: Optional[UUID] = None,
) -> RunModel:
    if run_spec is None:
        run_spec = get_run_spec(
            run_name=run_name,
            repo_id=repo.name,
        )
    if run_id is None:
        run_id = uuid.uuid4()
    run = RunModel(
        id=run_id,
        project_id=project.id,
        repo_id=repo.id,
        user_id=user.id,
        submitted_at=submitted_at,
        run_name=run_name,
        status=status,
        run_spec=run_spec.json(),
        last_processed_at=submitted_at,
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
    termination_reason: Optional[JobTerminationReason] = None,
    job_provisioning_data: Optional[JobProvisioningData] = None,
    instance: Optional[InstanceModel] = None,
    job_num: int = 0,
    replica_num: int = 0,
) -> JobModel:
    run_spec = RunSpec.parse_raw(run.run_spec)
    job_spec = (await get_job_specs_from_run_spec(run_spec, replica_num=replica_num))[0]
    job = JobModel(
        project_id=run.project_id,
        run_id=run.id,
        run_name=run.run_name,
        job_num=job_num,
        job_name=run.run_name + f"-0-{replica_num}",
        replica_num=replica_num,
        submission_num=submission_num,
        submitted_at=submitted_at,
        last_processed_at=last_processed_at,
        status=status,
        termination_reason=termination_reason,
        job_spec_data=job_spec.json(),
        job_provisioning_data=job_provisioning_data.json() if job_provisioning_data else None,
        instance=instance,
        used_instance_id=instance.id if instance is not None else None,
    )
    session.add(job)
    await session.commit()
    return job


def get_job_provisioning_data() -> JobProvisioningData:
    return JobProvisioningData(
        backend=BackendType.AWS,
        instance_type=InstanceType(
            name="instance",
            resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
        ),
        instance_id="instance_id",
        hostname="127.0.0.4",
        internal_ip="127.0.0.4",
        region="us-east-1",
        price=10.5,
        username="ubuntu",
        ssh_port=22,
        dockerized=False,
        backend_data=None,
        ssh_proxy=None,
    )


async def create_gateway(
    session: AsyncSession,
    project_id: UUID,
    backend_id: UUID,
    name: str = "test_gateway",
    region: str = "us",
    wildcard_domain: Optional[str] = None,
    gateway_compute_id: Optional[UUID] = None,
    status: Optional[GatewayStatus] = GatewayStatus.SUBMITTED,
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
) -> GatewayModel:
    gateway = GatewayModel(
        project_id=project_id,
        backend_id=backend_id,
        name=name,
        region=region,
        wildcard_domain=wildcard_domain,
        gateway_compute_id=gateway_compute_id,
        status=status,
        last_processed_at=last_processed_at,
    )
    session.add(gateway)
    await session.commit()
    return gateway


async def create_gateway_compute(
    session: AsyncSession,
    backend_id: Optional[UUID] = None,
    ip_address: Optional[str] = "1.1.1.1",
    region: str = "us",
    instance_id: Optional[str] = "i-1234567890",
    ssh_private_key: str = "",
    ssh_public_key: str = "",
) -> GatewayComputeModel:
    gateway_compute = GatewayComputeModel(
        backend_id=backend_id,
        ip_address=ip_address,
        region=region,
        instance_id=instance_id,
        ssh_private_key=ssh_private_key,
        ssh_public_key=ssh_public_key,
    )
    session.add(gateway_compute)
    await session.commit()
    return gateway_compute


async def create_pool(
    session: AsyncSession,
    project: ProjectModel,
    pool_name: Optional[str] = None,
) -> PoolModel:
    pool_name = pool_name if pool_name is not None else DEFAULT_POOL_NAME
    pool = PoolModel(
        name=pool_name,
        project=project,
        project_id=project.id,
    )
    session.add(pool)
    await session.commit()
    return pool


async def create_instance(
    session: AsyncSession,
    project: ProjectModel,
    pool: PoolModel,
    status: InstanceStatus = InstanceStatus.IDLE,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    finished_at: Optional[datetime] = None,
    spot: bool = False,
    profile: Optional[Profile] = None,
    requirements: Optional[Requirements] = None,
    instance_configuration: Optional[InstanceConfiguration] = None,
    instance_id: Optional[UUID] = None,
) -> InstanceModel:
    if instance_id is None:
        instance_id = uuid.uuid4()
    job_provisioning_data = {
        "backend": "datacrunch",
        "instance_type": {
            "name": "instance",
            "resources": {
                "cpus": 1,
                "memory_mib": 512,
                "gpus": [],
                "spot": spot,
                "disk": {"size_mib": 102400},
                "description": "",
            },
        },
        "instance_id": "running_instance.id",
        "ssh_proxy": None,
        "hostname": "running_instance.ip",
        "region": "running_instance.location",
        "price": 0.1,
        "username": "root",
        "ssh_port": 22,
        "dockerized": True,
        "backend_data": None,
    }
    offer = {
        "backend": "datacrunch",
        "instance": {
            "name": "instance",
            "resources": {
                "cpus": 2,
                "memory_mib": 12000,
                "gpus": [],
                "spot": spot,
                "disk": {"size_mib": 102400},
                "description": "",
            },
        },
        "region": "en",
        "price": 1,
        "availability": "available",
    }

    if profile is None:
        profile = Profile(name="test_name")

    if requirements is None:
        requirements = Requirements(resources=ResourcesSpec(cpu=1))

    if instance_configuration is None:
        instance_configuration = InstanceConfiguration(
            project_name="test_proj",
            instance_name="test_instance_name",
            instance_id="test instance id",
            job_docker_config=None,
            ssh_keys=[],
            user="test_user",
        )

    im = InstanceModel(
        id=instance_id,
        name="test_instance",
        pool=pool,
        project=project,
        status=status,
        unreachable=False,
        created_at=created_at,
        started_at=created_at,
        finished_at=finished_at,
        job_provisioning_data=json.dumps(job_provisioning_data),
        offer=json.dumps(offer),
        price=1,
        region="eu-west",
        backend=BackendType.DATACRUNCH,
        termination_idle_time=DEFAULT_POOL_TERMINATION_IDLE_TIME,
        profile=profile.json(),
        requirements=requirements.json(),
        instance_configuration=instance_configuration.json(),
    )
    session.add(im)
    await session.commit()
    return im


async def create_volume(
    session: AsyncSession,
    project: ProjectModel,
    status: VolumeStatus = VolumeStatus.SUBMITTED,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    configuration: Optional[VolumeConfiguration] = None,
    volume_provisioning_data: Optional[VolumeProvisioningData] = None,
    deleted_at: Optional[datetime] = None,
) -> VolumeModel:
    if configuration is None:
        configuration = get_volume_configuration()
    vm = VolumeModel(
        project=project,
        name=configuration.name,
        status=status,
        created_at=created_at,
        configuration=configuration.json(),
        volume_provisioning_data=volume_provisioning_data.json()
        if volume_provisioning_data
        else None,
        instances=[],
        deleted_at=deleted_at,
    )
    session.add(vm)
    await session.commit()
    return vm


def get_volume_configuration(
    name: str = "test-volume",
    backend: BackendType = BackendType.AWS,
    region: str = "eu-west-1",
    size: Optional[Memory] = Memory(100),
    volume_id: Optional[str] = None,
) -> VolumeConfiguration:
    return VolumeConfiguration(
        name=name,
        backend=backend,
        region=region,
        size=size,
        volume_id=volume_id,
    )


def get_volume_provisioning_data(
    volume_id: str = "vol-1234",
    size_gb: int = 100,
    availability_zone: Optional[str] = None,
    backend_data: Optional[str] = None,
) -> VolumeProvisioningData:
    return VolumeProvisioningData(
        volume_id=volume_id,
        size_gb=size_gb,
        availability_zone=availability_zone,
        backend_data=backend_data,
    )


class AsyncContextManager:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc, traceback):
        pass
