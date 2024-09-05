import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
)
from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec, FleetStatus
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.core.models.instances import (
    InstanceConfiguration,
    InstanceStatus,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_NAME,
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    Profile,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.resources import Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import (
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
    DecryptedString,
    FleetModel,
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
from dstack._internal.server.services.permissions import (
    DefaultPermissions,
    get_default_permissions,
    set_default_permissions,
)
from dstack._internal.server.services.users import get_token_hash


def get_auth_headers(token: Union[DecryptedString, str]) -> Dict:
    if isinstance(token, DecryptedString):
        token = token.get_plaintext_or_error()
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    session: AsyncSession,
    name: str = "test_user",
    global_role: GlobalRole = GlobalRole.ADMIN,
    token: Optional[str] = None,
    email: Optional[str] = None,
    active: bool = True,
) -> UserModel:
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        name=name,
        global_role=global_role,
        token=DecryptedString(plaintext=token),
        token_hash=get_token_hash(token),
        email=email,
        active=active,
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
        auth=DecryptedString(plaintext=json.dumps(auth)),
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
            "repo_host_name": "",
            "repo_port": None,
            "repo_user_name": "",
            "repo_name": "dstack",
        }
    if creds is None:
        creds = {
            "protocol": "https",
            "clone_url": "https://github.com/dstackai/dstack.git",
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
    instance_assigned: bool = False,
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
        instance_assigned=instance_assigned,
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


async def create_fleet(
    session: AsyncSession,
    project: ProjectModel,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    spec: Optional[FleetSpec] = None,
    fleet_id: Optional[UUID] = None,
    status: FleetStatus = FleetStatus.ACTIVE,
) -> FleetModel:
    if fleet_id is None:
        fleet_id = uuid.uuid4()
    if spec is None:
        spec = get_fleet_spec()
    fm = FleetModel(
        id=fleet_id,
        project=project,
        name=spec.configuration.name,
        status=status,
        created_at=created_at,
        spec=spec.json(),
        instances=[],
        runs=[],
    )
    session.add(fm)
    await session.commit()
    return fm


def get_fleet_spec(conf: Optional[FleetConfiguration] = None) -> FleetSpec:
    if conf is None:
        conf = get_fleet_configuration()
    return FleetSpec(
        configuration=conf,
        profile=Profile(name=""),
    )


def get_fleet_configuration(
    name: str = "test-fleet",
    nodes: Range[int] = Range(min=1, max=1),
) -> FleetConfiguration:
    return FleetConfiguration(
        name=name,
        nodes=nodes,
    )


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
    job: Optional[JobModel] = None,
    instance_num: int = 0,
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
        instance_num=instance_num,
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
        job=job,
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


def get_private_key_string() -> str:
    return """
-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----
"""


@contextmanager
def default_permissions_context(default_permissions: DefaultPermissions):
    prev_default_permissions = get_default_permissions()
    set_default_permissions(default_permissions)
    try:
        yield
    finally:
        set_default_permissions(prev_default_permissions)


class AsyncContextManager:
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc, traceback):
        pass
