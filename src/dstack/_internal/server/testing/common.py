import json
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Union
from uuid import UUID

import gpuhunt
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithCreateInstanceSupport,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithReservationSupport,
    ComputeWithVolumeSupport,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.fleets import (
    FleetConfiguration,
    FleetSpec,
    FleetStatus,
    InstanceGroupPlacement,
    SSHHostParams,
    SSHParams,
)
from dstack._internal.core.models.gateways import GatewayComputeConfiguration, GatewayStatus
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceType,
    RemoteConnectionInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.placement import (
    PlacementGroupConfiguration,
    PlacementGroupProvisioningData,
    PlacementStrategy,
)
from dstack._internal.core.models.profiles import (
    DEFAULT_FLEET_TERMINATION_IDLE_TIME,
    Profile,
    TerminationPolicy,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.resources import CPUSpec, Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobRuntimeData,
    JobStatus,
    JobTerminationReason,
    Requirements,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachment,
    VolumeConfiguration,
    VolumeProvisioningData,
    VolumeStatus,
)
from dstack._internal.server.models import (
    BackendModel,
    DecryptedString,
    FileArchiveModel,
    FleetModel,
    GatewayComputeModel,
    GatewayModel,
    InstanceHealthCheckModel,
    InstanceModel,
    JobMetricsPoint,
    JobModel,
    JobPrometheusMetrics,
    PlacementGroupModel,
    ProbeModel,
    ProjectModel,
    RepoCredsModel,
    RepoModel,
    RunModel,
    SecretModel,
    UserModel,
    VolumeAttachmentModel,
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
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    global_role: GlobalRole = GlobalRole.ADMIN,
    token: Optional[str] = None,
    email: Optional[str] = None,
    active: bool = True,
) -> UserModel:
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        name=name,
        created_at=created_at,
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
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    ssh_private_key: str = "",
    ssh_public_key: str = "",
    is_public: bool = False,
) -> ProjectModel:
    if owner is None:
        owner = await create_user(session=session, name="test_owner")
    project = ProjectModel(
        name=name,
        owner_id=owner.id,
        created_at=created_at,
        ssh_private_key=ssh_private_key,
        ssh_public_key=ssh_public_key,
        is_public=is_public,
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
            "repo_name": "dstack",
        }
    repo = RepoModel(
        project_id=project_id,
        name=repo_name,
        type=repo_type,
        info=json.dumps(info),
        creds=json.dumps(creds) if creds is not None else None,
    )
    session.add(repo)
    await session.commit()
    return repo


async def create_repo_creds(
    session: AsyncSession,
    repo_id: UUID,
    user_id: UUID,
    creds: Optional[dict] = None,
) -> RepoCredsModel:
    if creds is None:
        creds = {
            "clone_url": "https://github.com/dstackai/dstack.git",
            "private_key": None,
            "oauth_token": "test_token",
        }
    repo_creds = RepoCredsModel(
        repo_id=repo_id,
        user_id=user_id,
        creds=DecryptedString(plaintext=json.dumps(creds)),
    )
    session.add(repo_creds)
    await session.commit()
    return repo_creds


async def create_file_archive(
    session: AsyncSession,
    user_id: UUID,
    blob_hash: str = "blob_hash",
    blob: bytes = b"blob_content",
) -> FileArchiveModel:
    archive = FileArchiveModel(
        user_id=user_id,
        blob_hash=blob_hash,
        blob=blob,
    )
    session.add(archive)
    await session.commit()
    return archive


def get_run_spec(
    repo_id: str,
    run_name: str = "test-run",
    configuration_path: str = "dstack.yaml",
    profile: Union[Profile, Callable[[], Profile], None] = lambda: Profile(name="default"),
    configuration: Optional[AnyRunConfiguration] = None,
) -> RunSpec:
    if callable(profile):
        profile = profile()
    return RunSpec(
        run_name=run_name,
        repo_id=repo_id,
        repo_data=LocalRunRepoData(repo_dir="/"),
        repo_code_hash=None,
        working_dir=".",
        configuration_path=configuration_path,
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
    termination_reason: Optional[RunTerminationReason] = None,
    submitted_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    run_spec: Optional[RunSpec] = None,
    run_id: Optional[UUID] = None,
    deleted: bool = False,
    priority: int = 0,
    deployment_num: int = 0,
    resubmission_attempt: int = 0,
    next_triggered_at: Optional[datetime] = None,
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
        deleted=deleted,
        project_id=project.id,
        repo_id=repo.id,
        user_id=user.id,
        submitted_at=submitted_at,
        run_name=run_name,
        status=status,
        termination_reason=termination_reason,
        run_spec=run_spec.json(),
        last_processed_at=submitted_at,
        jobs=[],
        priority=priority,
        deployment_num=deployment_num,
        desired_replica_count=1,
        resubmission_attempt=resubmission_attempt,
        next_triggered_at=next_triggered_at,
    )
    session.add(run)
    await session.commit()
    return run


async def create_job(
    session: AsyncSession,
    run: RunModel,
    fleet: Optional[FleetModel] = None,
    submission_num: int = 0,
    status: JobStatus = JobStatus.SUBMITTED,
    submitted_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    termination_reason: Optional[JobTerminationReason] = None,
    job_provisioning_data: Optional[JobProvisioningData] = None,
    job_runtime_data: Optional[JobRuntimeData] = None,
    instance: Optional[InstanceModel] = None,
    job_num: int = 0,
    replica_num: int = 0,
    deployment_num: Optional[int] = None,
    instance_assigned: bool = False,
    disconnected_at: Optional[datetime] = None,
    registered: bool = False,
) -> JobModel:
    if deployment_num is None:
        deployment_num = run.deployment_num
    run_spec = RunSpec.parse_raw(run.run_spec)
    job_spec = (
        await get_job_specs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=replica_num)
    )[0]
    job_spec.job_num = job_num
    job = JobModel(
        project_id=run.project_id,
        fleet=fleet,
        run_id=run.id,
        run_name=run.run_name,
        job_num=job_num,
        job_name=run.run_name + f"-{job_num}-{replica_num}",
        replica_num=replica_num,
        deployment_num=deployment_num,
        submission_num=submission_num,
        submitted_at=submitted_at,
        last_processed_at=last_processed_at,
        status=status,
        termination_reason=termination_reason,
        job_spec_data=job_spec.json(),
        job_provisioning_data=job_provisioning_data.json() if job_provisioning_data else None,
        job_runtime_data=job_runtime_data.json() if job_runtime_data else None,
        instance=instance,
        instance_assigned=instance_assigned,
        used_instance_id=instance.id if instance is not None else None,
        disconnected_at=disconnected_at,
        probes=[],
        registered=registered,
    )
    session.add(job)
    await session.commit()
    return job


def get_job_provisioning_data(
    dockerized: bool = False,
    backend: BackendType = BackendType.AWS,
    region: str = "us-east-1",
    gpu_count: int = 0,
    gpu_memory_gib: float = 16,
    gpu_name: str = "T4",
    cpu_count: int = 1,
    memory_gib: float = 0.5,
    spot: bool = False,
    hostname: str = "127.0.0.4",
    internal_ip: Optional[str] = "127.0.0.4",
    price: float = 10.5,
    instance_type: Optional[InstanceType] = None,
) -> JobProvisioningData:
    gpus = [
        Gpu(
            name=gpu_name,
            memory_mib=int(gpu_memory_gib * 1024),
            vendor=gpuhunt.AcceleratorVendor.NVIDIA,
        )
    ] * gpu_count
    if instance_type is None:
        instance_type = InstanceType(
            name="instance",
            resources=Resources(
                cpus=cpu_count, memory_mib=int(memory_gib * 1024), spot=spot, gpus=gpus
            ),
        )
    return JobProvisioningData(
        backend=backend,
        instance_type=instance_type,
        instance_id="instance_id",
        hostname=hostname,
        internal_ip=internal_ip,
        region=region,
        price=price,
        username="ubuntu",
        ssh_port=22,
        dockerized=dockerized,
        backend_data=None,
        ssh_proxy=None,
    )


def get_job_runtime_data(
    network_mode: str = NetworkMode.HOST,
    cpu: Optional[float] = None,
    gpu: Optional[int] = None,
    memory: Optional[float] = None,
    ports: Optional[dict[int, int]] = None,
    offer: Optional[InstanceOfferWithAvailability] = None,
    volume_names: Optional[list[str]] = None,
) -> JobRuntimeData:
    return JobRuntimeData(
        network_mode=NetworkMode(network_mode),
        cpu=cpu,
        gpu=gpu,
        memory=Memory(memory) if memory is not None else None,
        ports=ports,
        offer=offer,
        volume_names=volume_names,
    )


async def create_probe(
    session: AsyncSession,
    job: JobModel,
    probe_num: int = 0,
    due: datetime = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc),
    success_streak: int = 0,
) -> ProbeModel:
    probe = ProbeModel(
        name=f"{job.job_name}-{probe_num}",
        job=job,
        probe_num=probe_num,
        due=due,
        success_streak=success_streak,
        active=True,
    )
    session.add(probe)
    await session.commit()
    return probe


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


def get_gateway_compute_configuration(
    project_name: str = "test-project",
    instance_name: str = "test-instance",
    backend: BackendType = BackendType.AWS,
    region: str = "us",
    public_ip: bool = True,
) -> GatewayComputeConfiguration:
    return GatewayComputeConfiguration(
        project_name=project_name,
        instance_name=instance_name,
        backend=backend,
        region=region,
        public_ip=public_ip,
        ssh_key_pub="",
        certificate=None,
    )


async def create_fleet(
    session: AsyncSession,
    project: ProjectModel,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    spec: Optional[FleetSpec] = None,
    fleet_id: Optional[UUID] = None,
    status: FleetStatus = FleetStatus.ACTIVE,
    deleted: bool = False,
    name: Optional[str] = None,
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
) -> FleetModel:
    if fleet_id is None:
        fleet_id = uuid.uuid4()
    if spec is None:
        spec = get_fleet_spec()
    if name is not None:
        spec.configuration.name = name
    fm = FleetModel(
        id=fleet_id,
        project=project,
        deleted=deleted,
        name=spec.configuration.name,
        status=status,
        created_at=created_at,
        spec=spec.json(),
        instances=[],
        runs=[],
        last_processed_at=last_processed_at,
    )
    session.add(fm)
    await session.commit()
    return fm


def get_fleet_spec(conf: Optional[FleetConfiguration] = None) -> FleetSpec:
    if conf is None:
        conf = get_fleet_configuration()
    return FleetSpec(
        configuration=conf,
        configuration_path="fleet.dstack.yml",
        profile=Profile(),
    )


def get_fleet_configuration(
    name: str = "test-fleet",
    nodes: Range[int] = Range(min=1, max=1),
    placement: Optional[InstanceGroupPlacement] = None,
) -> FleetConfiguration:
    return FleetConfiguration(
        name=name,
        nodes=nodes,
        placement=placement,
    )


def get_ssh_fleet_configuration(
    name: str = "test-fleet",
    user: str = "ubuntu",
    ssh_key: Optional[SSHKey] = None,
    hosts: Optional[list[Union[SSHHostParams, str]]] = None,
    network: Optional[str] = None,
    placement: Optional[InstanceGroupPlacement] = None,
) -> FleetConfiguration:
    if ssh_key is None:
        ssh_key = SSHKey(public="", private=get_private_key_string())
    if hosts is None:
        hosts = ["10.0.0.100"]
    ssh_config = SSHParams(
        user=user,
        ssh_key=ssh_key,
        hosts=hosts,
        network=network,
    )
    return FleetConfiguration(
        name=name,
        ssh_config=ssh_config,
        placement=placement,
    )


async def create_instance(
    session: AsyncSession,
    project: ProjectModel,
    fleet: Optional[FleetModel] = None,
    status: InstanceStatus = InstanceStatus.IDLE,
    unreachable: bool = False,
    health_status: HealthStatus = HealthStatus.HEALTHY,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    finished_at: Optional[datetime] = None,
    spot: bool = False,
    profile: Optional[Profile] = None,
    requirements: Optional[Requirements] = None,
    instance_configuration: Optional[InstanceConfiguration] = None,
    instance_id: Optional[UUID] = None,
    job: Optional[JobModel] = None,
    instance_num: int = 0,
    backend: BackendType = BackendType.DATACRUNCH,
    termination_policy: Optional[TerminationPolicy] = None,
    termination_idle_time: int = DEFAULT_FLEET_TERMINATION_IDLE_TIME,
    region: str = "eu-west",
    remote_connection_info: Optional[RemoteConnectionInfo] = None,
    offer: Optional[Union[InstanceOfferWithAvailability, Literal["auto"]]] = "auto",
    job_provisioning_data: Optional[Union[JobProvisioningData, Literal["auto"]]] = "auto",
    total_blocks: Optional[int] = 1,
    busy_blocks: int = 0,
    name: str = "test_instance",
    volumes: Optional[List[VolumeModel]] = None,
    price: float = 1.0,
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
) -> InstanceModel:
    if instance_id is None:
        instance_id = uuid.uuid4()
    if job_provisioning_data == "auto":
        job_provisioning_data = get_job_provisioning_data(
            dockerized=True,
            backend=backend,
            region=region,
            spot=spot,
            hostname="running_instance.ip",
            internal_ip=None,
        )
    if offer == "auto":
        offer = get_instance_offer_with_availability(
            backend=backend, region=region, spot=spot, price=price
        )
    if profile is None:
        profile = Profile(name="test_name")

    if requirements is None:
        requirements = Requirements(resources=ResourcesSpec(cpu=CPUSpec.parse("1")))

    if instance_configuration is None:
        instance_configuration = get_instance_configuration()

    if volumes is None:
        volumes = []
    volume_attachments = []
    for volume in volumes:
        volume_attachments.append(VolumeAttachmentModel(volume=volume))

    im = InstanceModel(
        id=instance_id,
        name=name,
        instance_num=instance_num,
        fleet=fleet,
        project=project,
        status=status,
        last_processed_at=last_processed_at,
        unreachable=unreachable,
        health=health_status,
        created_at=created_at,
        started_at=created_at,
        finished_at=finished_at,
        job_provisioning_data=job_provisioning_data.json() if job_provisioning_data else None,
        offer=offer.json() if offer else None,
        price=price,
        region=region,
        backend=backend,
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
        profile=profile.json(),
        requirements=requirements.json(),
        instance_configuration=instance_configuration.json(),
        remote_connection_info=remote_connection_info.json() if remote_connection_info else None,
        volume_attachments=volume_attachments,
        total_blocks=total_blocks,
        busy_blocks=busy_blocks,
    )
    if job:
        im.jobs.append(job)
    session.add(im)
    await session.commit()
    return im


def get_instance_configuration(
    project_name: str = "test-project",
    instance_name: str = "test-instance",
    user: str = "dstack-user",
) -> InstanceConfiguration:
    return InstanceConfiguration(
        project_name=project_name,
        instance_name=instance_name,
        user=user,
        ssh_keys=[],
    )


def get_instance_offer_with_availability(
    backend: BackendType = BackendType.AWS,
    region: str = "eu-west",
    gpu_count: int = 0,
    gpu_name: str = "T4",
    gpu_memory_gib: float = 16,
    cpu_count: int = 2,
    memory_gib: float = 12,
    disk_gib: float = 100.0,
    spot: bool = False,
    blocks: int = 1,
    total_blocks: int = 1,
    availability_zones: Optional[List[str]] = None,
    price: float = 1.0,
    instance_type: str = "instance",
    availability: InstanceAvailability = InstanceAvailability.AVAILABLE,
):
    gpus = [
        Gpu(
            name=gpu_name,
            memory_mib=int(gpu_memory_gib * 1024),
            vendor=gpuhunt.AcceleratorVendor.NVIDIA,
        )
    ] * gpu_count
    return InstanceOfferWithAvailability(
        backend=backend,
        instance=InstanceType(
            name=instance_type,
            resources=Resources(
                cpus=cpu_count,
                memory_mib=int(memory_gib * 1024),
                gpus=gpus,
                spot=spot,
                disk=Disk(size_mib=int(disk_gib * 1024)),
                description="",
            ),
        ),
        region=region,
        price=price,
        availability=availability,
        availability_zones=availability_zones,
        blocks=blocks,
        total_blocks=total_blocks,
    )


def get_remote_connection_info(
    host: str = "10.0.0.10",
    port: int = 22,
    ssh_user: str = "ubuntu",
    ssh_keys: Optional[list[SSHKey]] = None,
    env: Optional[Union[Env, dict]] = None,
):
    if ssh_keys is None:
        ssh_keys = [get_ssh_key()]
    if env is None:
        env = Env()
    elif isinstance(env, dict):
        env = Env.parse_obj(env)
    return RemoteConnectionInfo(
        host=host,
        port=port,
        ssh_user=ssh_user,
        ssh_keys=ssh_keys,
        env=env,
    )


def get_ssh_key() -> SSHKey:
    return SSHKey(
        public="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO6mJxVbNtm0zXgMLvByrhXJCmJRveSrJxLB5/OzcyCk",
        private="""
                    -----BEGIN OPENSSH PRIVATE KEY-----
                    b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
                    QyNTUxOQAAACDupicVWzbZtM14DC7wcq4VyQpiUb3kqycSwefzs3MgpAAAAJCiWa5Volmu
                    VQAAAAtzc2gtZWQyNTUxOQAAACDupicVWzbZtM14DC7wcq4VyQpiUb3kqycSwefzs3MgpA
                    AAAEAncHi4AhS6XdMp5Gzd+IMse/4ekyQ54UngByf0Sp0uH+6mJxVbNtm0zXgMLvByrhXJ
                    CmJRveSrJxLB5/OzcyCkAAAACWRlZkBkZWZwYwECAwQ=
                    -----END OPENSSH PRIVATE KEY-----
                """,
    )


async def create_instance_health_check(
    session: AsyncSession,
    instance: InstanceModel,
    collected_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    status: HealthStatus = HealthStatus.HEALTHY,
    response: str = "{}",
) -> InstanceHealthCheckModel:
    health_check = InstanceHealthCheckModel(
        instance_id=instance.id,
        collected_at=collected_at,
        status=status,
        response=response,
    )
    session.add(health_check)
    await session.commit()
    return health_check


async def create_volume(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    status: VolumeStatus = VolumeStatus.SUBMITTED,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    last_processed_at: Optional[datetime] = None,
    last_job_processed_at: Optional[datetime] = None,
    configuration: Optional[VolumeConfiguration] = None,
    volume_provisioning_data: Optional[VolumeProvisioningData] = None,
    deleted_at: Optional[datetime] = None,
    backend: BackendType = BackendType.AWS,
    region: str = "eu-west-1",
) -> VolumeModel:
    if configuration is None:
        configuration = get_volume_configuration(backend=backend, region=region)
    if last_processed_at is None:
        last_processed_at = created_at
    vm = VolumeModel(
        project=project,
        user_id=user.id,
        name=configuration.name,
        status=status,
        created_at=created_at,
        last_processed_at=last_processed_at,
        last_job_processed_at=last_job_processed_at,
        configuration=configuration.json(),
        volume_provisioning_data=volume_provisioning_data.json()
        if volume_provisioning_data
        else None,
        attachments=[],
        deleted_at=deleted_at,
        deleted=True if deleted_at else False,
    )
    session.add(vm)
    await session.commit()
    return vm


def get_volume(
    id_: Optional[UUID] = None,
    name: str = "test_volume",
    user: str = "test_user",
    project_name: str = "test_project",
    configuration: Optional[VolumeConfiguration] = None,
    external: bool = False,
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    last_processed_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    status: VolumeStatus = VolumeStatus.ACTIVE,
    status_message: Optional[str] = None,
    deleted: bool = False,
    deleted_at: Optional[datetime] = None,
    volume_id: Optional[str] = None,
    provisioning_data: Optional[VolumeProvisioningData] = None,
    attachments: Optional[List[VolumeAttachment]] = None,
) -> Volume:
    if id_ is None:
        id_ = uuid.uuid4()
    if configuration is None:
        configuration = get_volume_configuration()
    if attachments is None:
        attachments = []
    return Volume(
        id=id_,
        name=name,
        user=user,
        project_name=project_name,
        configuration=configuration,
        external=external,
        created_at=created_at,
        last_processed_at=last_processed_at,
        status=status,
        status_message=status_message,
        deleted=deleted,
        deleted_at=deleted_at,
        volume_id=volume_id,
        provisioning_data=provisioning_data,
        attachments=attachments,
    )


def get_volume_configuration(
    name: str = "test-volume",
    backend: BackendType = BackendType.AWS,
    region: str = "eu-west-1",
    size: Optional[Memory] = Memory(100),
    volume_id: Optional[str] = None,
    auto_cleanup_duration: Optional[Union[str, int]] = None,
) -> VolumeConfiguration:
    return VolumeConfiguration(
        name=name,
        backend=backend,
        region=region,
        size=size,
        volume_id=volume_id,
        auto_cleanup_duration=auto_cleanup_duration,
    )


def get_volume_provisioning_data(
    volume_id: str = "vol-1234",
    size_gb: int = 100,
    availability_zone: Optional[str] = None,
    price: Optional[float] = 1.0,
    backend_data: Optional[str] = None,
    backend: Optional[BackendType] = None,
) -> VolumeProvisioningData:
    return VolumeProvisioningData(
        backend=backend,
        volume_id=volume_id,
        size_gb=size_gb,
        availability_zone=availability_zone,
        price=price,
        backend_data=backend_data,
    )


async def create_placement_group(
    session: AsyncSession,
    project: ProjectModel,
    fleet: FleetModel,
    name: str = "test-pg",
    created_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    configuration: Optional[PlacementGroupConfiguration] = None,
    provisioning_data: Optional[PlacementGroupProvisioningData] = None,
    fleet_deleted: Optional[bool] = False,
    deleted: Optional[bool] = False,
    deleted_at: Optional[datetime] = None,
) -> PlacementGroupModel:
    if configuration is None:
        configuration = get_placement_group_configuration()
    if provisioning_data is None:
        provisioning_data = get_placement_group_provisioning_data()
    pg = PlacementGroupModel(
        project=project,
        fleet=fleet,
        name=name,
        created_at=created_at,
        configuration=configuration.json(),
        provisioning_data=provisioning_data.json(),
        fleet_deleted=fleet_deleted,
        deleted=deleted,
        deleted_at=deleted_at,
    )
    session.add(pg)
    await session.commit()
    return pg


def get_placement_group_configuration(
    backend: BackendType = BackendType.AWS,
    region: str = "eu-central-1",
    strategy: PlacementStrategy = PlacementStrategy.CLUSTER,
) -> PlacementGroupConfiguration:
    return PlacementGroupConfiguration(
        backend=backend,
        region=region,
        placement_strategy=strategy,
    )


def get_placement_group_provisioning_data(
    backend: BackendType = BackendType.AWS,
) -> PlacementGroupProvisioningData:
    return PlacementGroupProvisioningData(backend=backend)


async def create_job_metrics_point(
    session: AsyncSession,
    job_model: JobModel,
    timestamp: datetime,
    cpu_usage_micro: int = 1_000_000,
    memory_usage_bytes: int = 1024,
    memory_working_set_bytes: int = 1024,
    gpus_memory_usage_bytes: Optional[List[int]] = None,
    gpus_util_percent: Optional[List[int]] = None,
) -> JobMetricsPoint:
    timestamp_micro = int(timestamp.timestamp() * 1_000_000)
    if gpus_memory_usage_bytes is None:
        gpus_memory_usage_bytes = []
    if gpus_util_percent is None:
        gpus_util_percent = []
    jmp = JobMetricsPoint(
        job_id=job_model.id,
        timestamp_micro=timestamp_micro,
        cpu_usage_micro=cpu_usage_micro,
        memory_usage_bytes=memory_usage_bytes,
        memory_working_set_bytes=memory_working_set_bytes,
        gpus_memory_usage_bytes=json.dumps(gpus_memory_usage_bytes),
        gpus_util_percent=json.dumps(gpus_util_percent),
    )
    session.add(jmp)
    await session.commit()
    return jmp


async def create_job_prometheus_metrics(
    session: AsyncSession,
    job: JobModel,
    collected_at: datetime = datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    text: str = "# Prometheus metrics\n",
):
    metrics = JobPrometheusMetrics(
        job_id=job.id,
        collected_at=collected_at,
        text=text,
    )
    session.add(metrics)
    await session.commit()
    return metrics


async def create_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
):
    secret_model = SecretModel(
        project=project,
        name=name,
        value=DecryptedString(plaintext=value),
    )
    session.add(secret_model)
    await session.commit()
    return secret_model


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


class ComputeMockSpec(
    Compute,
    ComputeWithCreateInstanceSupport,
    ComputeWithMultinodeSupport,
    ComputeWithReservationSupport,
    ComputeWithPlacementGroupSupport,
    ComputeWithGatewaySupport,
    ComputeWithPrivateGatewaySupport,
    ComputeWithVolumeSupport,
):
    """
    Can be used to create Compute mocks that pass all `isinstance()` asserts.
    """

    pass
